"""L4 test world: synthetic documents over the C5 §8.5 seed, a recorded model, a clock."""

import hashlib
import json
import secrets
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select, update

from mona.ids import new_id
from mona.interviews.model import ModelError
from mona.services.registry import T
from mona.text import contains_word, norm
from mona.workflow.common import get_ctx

FIXTURES = Path(__file__).parent / "fixtures" / "interviews"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Clock:
    """A settable clock; the recorded model advances it to simulate slow passes."""

    def __init__(self, start: datetime | None = None):
        self.now = start or datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: Any) -> None:
        self.now += timedelta(**kw)


class World:
    def __init__(self, clock: Clock | None = None):
        self.ctx = get_ctx()
        self.engine = self.ctx.engine
        self.clock = clock or Clock()
        self.ctx.clock = self.clock
        self.ctx.ops.clock = self.clock
        self.tags: dict[str, str] = {}
        self._n = 0

    def ids(self, table: str, column: str = "key") -> dict[str, str]:
        t = T[table]
        with self.engine.connect() as conn:
            return dict(conn.execute(select(t.c[column], t.c.id)).all())

    def row(self, table: str, id_: str) -> Any:
        t = T[table]
        with self.engine.connect() as conn:
            return conn.execute(select(t).where(t.c.id == id_)).mappings().one()

    def set_settings(self, **values: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(T["settings"]).values(**values))

    def batch(self, *, status: str = "done", source: str = "drop", visitor: bool = False) -> str:
        b = new_id("bat")
        with self.engine.begin() as conn:
            conn.execute(
                insert(T["batches"]).values(id=b, source=source, status=status, visitor=visitor)
            )
            conn.execute(
                insert(T["op_groups"]).values(
                    id=new_id("grp"), kind="intake_batch", actor="mona", via="pipeline", batch_id=b
                )
            )
        return b

    def doc(
        self,
        title: str,
        *,
        batch: str,
        counterparty: str | None = None,
        extracted_counterparty: str | None = None,
        reasons: tuple[str, ...] | list[str] = ("entity",),
        status: str = "review",
        stage: str = "done",
        entity: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        addressee: str | None = None,
        pages: list[str] | tuple[str, ...] = ("",),
        amount: float | None = None,
        doc_date: date | str | None = None,
        rule: str | None = None,
        path: str | None = None,
        tag: str | None = None,
        content: bytes | None = None,
        **fields: Any,
    ) -> str:
        """A document as classification leaves it: extraction, classification, text cache."""
        self._n += 1
        doc_id = new_id("doc")
        data = content or secrets.token_bytes(32)
        sha = hashlib.sha256(data).hexdigest()
        roots = self.ctx.ops.roots
        filed = status == "filed"
        location = "archive" if filed else "inbox"
        current = path or f"{doc_id}.pdf"
        target = (roots.archive if filed else roots.inbox) / current
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        cache = self.ctx.textcache / sha[:2]
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{sha}.pages.json").write_text(
            json.dumps(
                {
                    "v": 1,
                    "sha256": sha,
                    "method": "pdftotext",
                    "page_count": len(pages),
                    "pages": list(pages),
                }
            ),
            encoding="utf-8",
        )
        ents, cps, rules = self.ids("entities"), self.ids("counterparties"), self.ids("rules")
        person = None
        if addressee:
            with self.engine.connect() as conn:
                hits = [
                    p["id"]
                    for p in conn.execute(select(T["people"])).mappings()
                    if any(
                        contains_word(norm(addressee), norm(n))
                        for n in (p["display_name"], *p["aliases"])
                    )
                ]
            person = hits[0] if len(hits) == 1 else None
        if isinstance(doc_date, str):
            doc_date = date.fromisoformat(doc_date)
        money = {"amount": Decimal(str(amount)), "currency": "EUR"} if amount is not None else {}
        ext_id, cls_id = new_id("ext"), new_id("cls")
        raw = {
            "category": category or "unknown",
            "subcategory": f"{category}.{subcategory}" if category and subcategory else None,
            "entity": {"value": entity, "quote": entity, "page": 1} if entity else None,
        }
        arrived = self.clock() + timedelta(seconds=self._n)
        with self.engine.begin() as conn:
            conn.execute(
                insert(T["documents"]).values(
                    id=doc_id,
                    sha256=sha,
                    original_name=f"{title}.pdf",
                    mime_type="application/pdf",
                    size_bytes=len(data),
                    source="drop",
                    batch_id=batch,
                    arrived_at=arrived,
                    location=location,
                    current_path=current,
                    status=status,
                    pipeline_stage=stage,
                    reasons=list(reasons),
                    title=title,
                    entity_id=ents.get(entity) if entity else None,
                    category_id=category,
                    subcategory_key=subcategory,
                    counterparty_id=cps.get(counterparty) if counterparty else None,
                    addressee=addressee,
                    addressee_person_id=person,
                    doc_date=doc_date,
                    confidence=50,
                    band="low",
                    filed_at=arrived if filed else None,
                    filed_by="mona" if filed else None,
                    rule_id=rules.get(rule) if rule else None,
                    **money,
                    **fields,
                )
            )
            conn.execute(
                insert(T["extractions"]).values(
                    id=ext_id,
                    document_id=doc_id,
                    version=1,
                    text_method="pdftotext",
                    text_cache_key=sha,
                    char_count=sum(len(p) for p in pages),
                    model="test",
                    raw_output=raw,
                )
            )
            quote = extracted_counterparty or counterparty
            if quote:
                conn.execute(
                    insert(T["extraction_fields"]).values(
                        extraction_id=ext_id,
                        key="counterparty",
                        value=quote,
                        quote=quote,
                        page=1,
                        stated_page=1,
                        verified=True,
                        confidence=90,
                    )
                )
            conn.execute(
                insert(T["classifications"]).values(
                    id=cls_id,
                    document_id=doc_id,
                    extraction_id=ext_id,
                    method="rule" if rule else "llm",
                    rule_id=rules.get(rule) if rule else None,
                    entity_id=ents.get(entity) if entity else None,
                    category_id=category,
                    subcategory_key=subcategory,
                    counterparty_id=cps.get(counterparty) if counterparty else None,
                    model_confidence=50,
                    confidence=50,
                    band="low",
                    reasons=list(reasons),
                )
            )
            d = T["documents"]
            conn.execute(
                update(d)
                .where(d.c.id == doc_id)
                .values(extraction_id=ext_id, classification_id=cls_id)
            )
            if status in ("review", "unreadable"):
                conn.execute(
                    insert(T["review_items"]).values(
                        id=new_id("rev"), document_id=doc_id, reasons=list(reasons) or ["low"]
                    )
                )
        if tag:
            self.tags[tag] = doc_id
        return doc_id

    def cluster(self, batch: str, spec: dict[str, Any] | None = None) -> dict[str, str]:
        """The recorded cluster's documents (tags → ids), all in review."""
        spec = spec or fixture("cluster.json")
        for d in spec["docs"]:
            d = dict(d)
            self.doc(d.pop("title"), batch=batch, **d)
        return dict(self.tags)

    def settle(self, doc_id: str, *, status: str = "review", reasons: tuple = ("entity",)) -> None:
        d = T["documents"]
        with self.engine.begin() as conn:
            conn.execute(
                update(d)
                .where(d.c.id == doc_id)
                .values(status=status, pipeline_stage="done", reasons=list(reasons))
            )

    def interviews(self) -> list[Any]:
        i = T["interviews"]
        with self.engine.connect() as conn:
            return list(conn.execute(select(i).order_by(i.c.created_at, i.c.id)).mappings())

    def questions(self, interview_id: str) -> list[Any]:
        q = T["interview_questions"]
        with self.engine.connect() as conn:
            return list(
                conn.execute(
                    select(q).where(q.c.interview_id == interview_id).order_by(q.c.ordinal)
                ).mappings()
            )

    def job_rows(self, task: str) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    text(
                        "SELECT id, status, args, priority, queue_name, queueing_lock"
                        " FROM procrastinate_jobs WHERE task_name = :t ORDER BY id"
                    ),
                    {"t": task},
                ).mappings()
            ]


class RecordedModel:
    """Replays recorded passes; `@tag` in pass-2 output becomes the input's alias for it."""

    model = "recorded"

    def __init__(
        self,
        world: World,
        *,
        pass1: list[tuple[str, str]] | str | None = None,
        pass2: dict[str, Any] | Callable[[str], dict[str, Any]] | None = None,
        step_s: float = 0.0,
        pass2_errors: int = 0,
        on_pass2: Callable[[], None] | None = None,
    ):
        spec = fixture("cluster.json")
        self.world = world
        self.pass1 = [("content", pass1)] if isinstance(pass1, str) else pass1
        if self.pass1 is None:
            self.pass1 = [("reasoning", "Thinking about the cluster. "), ("content", spec["pass1"])]
        self.pass2 = pass2 if pass2 is not None else spec["pass2"]
        self.step_s = step_s
        self.pass2_errors = pass2_errors
        self.on_pass2 = on_pass2
        self.calls: list[dict[str, Any]] = []

    def stream(self, system: str, user: str, **kw: Any) -> Iterator[tuple[str, str]]:
        self.calls.append({"pass": 1, "system": system, "user": user, **kw})
        for kind, text in self.pass1:  # type: ignore[union-attr]
            if self.step_s:
                self.world.clock.advance(seconds=self.step_s)
            if kind == "error":
                raise ModelError(text)
            yield kind, text

    def complete_json(self, system: str, user: str, schema: dict, **kw: Any) -> dict[str, Any]:
        self.calls.append({"pass": 2, "system": system, "user": user, "schema": schema, **kw})
        if self.on_pass2:
            self.on_pass2()
        if self.pass2_errors:
            self.pass2_errors -= 1
            raise ModelError("transport")
        out = self.pass2(user) if callable(self.pass2) else self.pass2
        return resolve_tags(out, user, self.world.tags)


def input_of(user: str) -> dict[str, Any]:
    return json.JSONDecoder().raw_decode(user)[0]


def resolve_tags(out: Any, user: str, tags: dict[str, str]) -> Any:
    """Replace `@tag` strings with the alias the input gave that document."""
    inp = input_of(user)
    by_title = {d["title"]: d["alias"] for d in inp.get("documents", [])}
    with_ids = {}
    from mona.workflow.common import get_ctx

    t = T["documents"]
    with get_ctx().engine.connect() as conn:
        titles = dict(conn.execute(select(t.c.id, t.c.title)).all())
    for tag, doc_id in tags.items():
        if titles.get(doc_id) in by_title:
            with_ids["@" + tag] = by_title[titles[doc_id]]

    def walk(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str) and x.startswith("@"):
            return with_ids.get(x, "d99")
        return x

    return walk(out)
