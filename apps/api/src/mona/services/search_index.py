"""`documents.fts` (C1 §4.2), rebuilt in the transaction that changes the fields it covers."""

from pathlib import Path

from sqlalchemy import Connection, select, text

from mona.services.placement import page_text
from mona.services.registry import T
from mona.text import norm

PAGE_CHARS = 50_000
UPDATE = text(
    "UPDATE documents SET fts = setweight(to_tsvector('mona', :a), 'A')"
    " || setweight(to_tsvector('mona', :b), 'B') || setweight(to_tsvector('mona', :c), 'C')"
    " WHERE id = :id"
)


def rebuild_fts(conn: Connection, document_id: str, textcache: Path) -> None:
    d = T["documents"]
    doc = conn.execute(select(d).where(d.c.id == document_id)).mappings().one()
    a_parts = [doc["title"] or ""]
    if doc["counterparty_id"]:
        cp, al = T["counterparties"], T["counterparty_aliases"]
        a_parts.append(
            conn.execute(select(cp.c.name).where(cp.c.id == doc["counterparty_id"])).scalar() or ""
        )
        a_parts += conn.execute(
            select(al.c.alias_norm).where(al.c.counterparty_id == doc["counterparty_id"])
        ).scalars()
    b_parts = []
    if doc["entity_id"]:
        e = T["entities"]
        b_parts.append(
            conn.execute(select(e.c.display_name).where(e.c.id == doc["entity_id"])).scalar()
        )
    if doc["category_id"]:
        c, sc = T["categories"], T["subcategories"]
        b_parts += (
            conn.execute(select(c.c.labels).where(c.c.id == doc["category_id"])).scalar().values()
        )
        if doc["subcategory_key"]:
            labels = conn.execute(
                select(sc.c.labels).where(
                    sc.c.category_id == doc["category_id"], sc.c.key == doc["subcategory_key"]
                )
            ).scalar()
            b_parts += (labels or {}).values()
    b_parts += [doc["doc_type"] or "", doc["reference"] or "", doc["original_name"]]
    conn.execute(
        UPDATE,
        {
            "id": document_id,
            "a": norm(" ".join(a_parts)),
            "b": norm(" ".join(p for p in b_parts if p)),
            "c": norm(page_text(textcache, doc["sha256"])[:PAGE_CHARS]),
        },
    )
