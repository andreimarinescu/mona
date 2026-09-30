"""Synthetic documents over the seeded C5 §8.5 registry, for the services tests."""

import hashlib
import json
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, insert, select

from mona.ids import new_id
from mona.seed.loader import load_seed
from mona.services import make_context
from mona.services.registry import T
from mona.settings import Settings
from mona.text import norm
from tests.fileops_world import Clock

SEED = Path(__file__).parent / "fixtures" / "seed"
IBAN_SPACED = "FR76 3000 6000 0112 3456 7890 189"
ARRIVED = datetime(2026, 10, 14, 7, 0, tzinfo=UTC)


def load_fixture_seed(engine: Engine, url: str, tier: str = "all") -> None:
    settings = Settings(database_url=url, mona_owner_password="correct horse battery staple")
    with engine.begin() as conn:
        load_seed(conn, SEED, settings=settings, tier=tier, overlay=SEED / "overlay.yaml")  # type: ignore[arg-type]


class Services:
    def __init__(self, engine: Engine, data_dir: Path, **kw: Any):
        self.engine = engine
        self.clock = kw.pop("clock", None) or Clock(ARRIVED)
        self.batches: list[str] = []
        self.ctx = make_context(engine, data_dir, clock=self.clock, **kw)
        self.batch = self.new_batch()

    def new_batch(self, *, visitor: bool = False) -> str:
        b = new_id("bat")
        with self.engine.begin() as conn:
            conn.execute(
                insert(T["batches"]).values(
                    id=b, source="drop", visitor=visitor, started_at=ARRIVED
                )
            )
            conn.execute(
                insert(T["op_groups"]).values(
                    id=new_id("grp"), kind="intake_batch", actor="mona", via="pipeline", batch_id=b
                )
            )
        self.batches.append(b)
        return b

    def ids(self, table: str, column: str = "key") -> dict[str, str]:
        t = T[table]
        with self.engine.connect() as conn:
            return dict(conn.execute(select(t.c[column], t.c.id)).all())

    def doc(
        self,
        *,
        counterparty: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        entity: str | None = None,
        text: str = "",
        status: str = "review",
        batch: str | None = None,
        extracted_counterparty: str | None = None,
        verified: dict[str, bool] | None = None,
        content: bytes | None = None,
        arrived_at: datetime = ARRIVED,
        **fields: Any,
    ) -> str:
        """A document in the inbox, as classification would leave it (model values stored)."""
        doc_id = new_id("doc")
        data = content or secrets.token_bytes(48)
        sha = hashlib.sha256(data).hexdigest()
        root = self.ctx.ops.roots
        (root.inbox / f"{doc_id}.pdf").write_bytes(data)
        cache = self.ctx.textcache / sha[:2]
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{sha}.pages.json").write_text(
            json.dumps({"v": 1, "sha256": sha, "method": "pdftotext", "page_count": 1,
                        "pages": [text]})
        )  # fmt: skip
        cps = self.ids("counterparties")
        ext_id = new_id("ext")
        raw = {
            "category": category or "unknown",
            "subcategory": f"{category}.{subcategory}" if subcategory else None,
            "entity": {"value": entity, "quote": entity, "page": 1} if entity else None,
        }
        if "amount" in fields and fields["amount"] is not None:
            fields["amount"] = Decimal(str(fields["amount"]))
            fields.setdefault("currency", "EUR")
        addressee = fields.get("addressee")
        people = {}
        if addressee:
            with self.engine.connect() as conn:
                for p in conn.execute(select(T["people"])).mappings():
                    names = [norm(x) for x in (p["display_name"], *p["aliases"])]
                    from mona.text import contains_word

                    if any(contains_word(norm(addressee), n) for n in names):
                        people[p["id"]] = True
        with self.engine.begin() as conn:
            batch = batch or self.batch
            conn.execute(
                insert(T["documents"]).values(
                    id=doc_id, sha256=sha, original_name=f"{doc_id}.pdf",
                    mime_type="application/pdf", size_bytes=len(data), source="drop",
                    batch_id=batch, arrived_at=arrived_at, location="inbox",
                    current_path=f"{doc_id}.pdf", status=status,
                    pipeline_stage="done" if status == "review" else "classifying",
                    reasons=["low"] if status == "review" else [],
                    counterparty_id=cps.get(counterparty) if counterparty else None,
                    entity_id=self.ids("entities").get(entity) if entity else None,
                    category_id=category,
                    subcategory_key=subcategory,
                    addressee_person_id=next(iter(people)) if len(people) == 1 else None,
                    **fields,
                )
            )  # fmt: skip
            conn.execute(
                insert(T["extractions"]).values(
                    id=ext_id, document_id=doc_id, version=1, text_method="pdftotext",
                    text_cache_key=sha, char_count=len(text), model="test", raw_output=raw,
                )
            )  # fmt: skip
            for key, ok in (verified or {}).items():
                value = str(fields.get(key) or extracted_counterparty or counterparty or "x")
                if isinstance(fields.get(key), date):
                    value = fields[key].isoformat()
                conn.execute(
                    insert(T["extraction_fields"]).values(
                        extraction_id=ext_id, key=key, value=value, quote=value, page=1,
                        stated_page=1, verified=ok, confidence=90 if ok else 40,
                    )
                )  # fmt: skip
            if extracted_counterparty and "counterparty" not in (verified or {}):
                conn.execute(
                    insert(T["extraction_fields"]).values(
                        extraction_id=ext_id, key="counterparty", value=extracted_counterparty,
                        quote=extracted_counterparty, page=1, stated_page=1, verified=True,
                        confidence=90,
                    )
                )  # fmt: skip
            d = T["documents"]
            conn.execute(d.update().where(d.c.id == doc_id).values(extraction_id=ext_id))
            if status == "review":
                conn.execute(
                    insert(T["review_items"]).values(
                        id=new_id("rev"), document_id=doc_id, reasons=["low"]
                    )
                )
        return doc_id

    def row(self, doc_id: str) -> Any:
        d = T["documents"]
        with self.engine.connect() as conn:
            return conn.execute(select(d).where(d.c.id == doc_id)).mappings().one()

    def rule_id(self, key: str) -> str:
        return self.ids("rules")[key]

    def disk_path(self, doc_id: str) -> Path:
        r = self.row(doc_id)
        return self.ctx.ops.roots.root(r["location"]) / r["current_path"]
