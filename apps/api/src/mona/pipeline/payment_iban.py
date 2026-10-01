"""A30 `payment_iban`: the first valid IBAN in page order that isn't one of the practice's own."""

import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, delete, insert, select, update

from mona.iban import IBAN_PATTERN, iban_hash, is_valid_iban, normalize_iban
from mona.pipeline import cache
from mona.pipeline.findquery import quote_query
from mona.services.registry import T

KEY = "payment_iban"


@dataclass(frozen=True)
class PaymentIban:
    value: str
    quote: str
    page: int
    find_query: str | None


def find(pages: Sequence[str], own_hashes: Collection[str], salt: bytes) -> PaymentIban | None:
    """C5 §4.3 candidates (mod-97, country length) minus the registry's accounts, by hash."""
    for n, page in enumerate(pages, 1):
        text = unicodedata.normalize("NFKC", page)
        upper = text.upper()
        source = text if len(text) == len(upper) else upper
        for m in IBAN_PATTERN.finditer(upper):
            value = normalize_iban(m.group(0))
            if not is_valid_iban(value) or iban_hash(value, salt) in own_hashes:
                continue
            quote = source[m.start() : m.end()]
            return PaymentIban(value, quote, n, quote_query(quote, page))
    return None


def own_hashes(conn: Connection) -> set[str]:
    return set(conn.execute(select(T["accounts"].c.iban_hash)).scalars())


def salt(conn: Connection) -> bytes:
    return bytes(conn.execute(select(T["settings"].c.iban_salt)).scalar_one())


def mask(value: str | None) -> str | None:
    """A30 on Telegram: the country code and the last 4 characters."""
    return f"{value[:2]} •• {value[-4:]}" if value else None


def field_row(extraction_id: str, found: PaymentIban) -> dict[str, Any]:
    return {
        "extraction_id": extraction_id, "key": KEY, "value": found.value, "currency": None,
        "quote": found.quote, "page": found.page, "stated_page": found.page, "verified": True,
        "find_query": found.find_query, "confidence": 100,
    }  # fmt: skip


def store(conn: Connection, doc: Any, found: PaymentIban | None) -> bool:
    """Set the document's value and its evidence row on its current extraction; True if changed."""
    ef, d = T["extraction_fields"], T["documents"]
    ext = doc["extraction_id"]
    mine = (ef.c.extraction_id == ext) & (ef.c.key == KEY)
    current = conn.execute(select(ef).where(mine)).mappings().first()
    wanted = field_row(ext, found) if found else None
    value = found.value if found else None
    if (dict(current) if current else None) == wanted and doc["payment_iban"] == value:
        return False
    conn.execute(delete(ef).where(mine))
    if wanted is not None:
        conn.execute(insert(ef).values(**wanted))
    conn.execute(update(d).where(d.c.id == doc["id"]).values(payment_iban=value))
    return True


@dataclass
class Backfill:
    checked: int = 0
    changed: int = 0
    no_text: int = 0


def backfill(ctx: Any) -> Backfill:
    """Fill every classified, live document from its cached text; a second run changes nothing."""
    d = T["documents"]
    out = Backfill()
    with ctx.engine.connect() as conn:
        ids = conn.execute(
            select(d.c.id).where(d.c.deleted_at.is_(None), d.c.extraction_id.is_not(None))
            .order_by(d.c.arrived_at, d.c.id)
        ).scalars().all()  # fmt: skip
    for doc_id in ids:
        with ctx.engine.begin() as conn:
            doc = conn.execute(
                select(d).where(d.c.id == doc_id, d.c.deleted_at.is_(None)).with_for_update()
            ).mappings().first()  # fmt: skip
            if doc is None or doc["extraction_id"] is None:
                continue
            pages = cache.read_pages(ctx.textcache, doc["sha256"])
            if pages is None:
                out.no_text += 1
                continue
            out.checked += 1
            found = find(pages.pages, own_hashes(conn), salt(conn))
            out.changed += store(conn, doc, found)
    return out
