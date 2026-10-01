"""`classify_document` (C5 §1.1): prompt → model (or its cache) → §6–§9 → persist → hand off."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, func, insert, select, update

from mona.fileops.ops import keep_review
from mona.ids import new_id
from mona.pipeline import cache
from mona.pipeline import prompt as prompts
from mona.pipeline import schema as output_schema
from mona.pipeline.evidence import Checked, check, field_confidence
from mona.pipeline.extract import UNREADABLE_MIN, solid_chars
from mona.pipeline.findquery import find_query
from mona.pipeline.model import ModelClient, ModelResult
from mona.pipeline.queue import defer
from mona.pipeline.schema import PROMPT_VERSION, Output
from mona.rules import store
from mona.rules.engine import Subject, evaluate
from mona.rules.scoring import percent, score, tokens_used
from mona.services import registry
from mona.services.context import Ctx
from mona.services.corrections import resolve_counterparty
from mona.services.pipeline import finish_batch_if_done, settle_hooks
from mona.services.placement import place
from mona.services.registry import Snapshot, T
from mona.services.search_index import rebuild_fts
from mona.templates import document_fiscal_year
from mona.text import contains_word, norm, ro_comma_below

MONEY = ("EUR", "RON")


class TextMissing(Exception):
    """`classify_document` ran before the text cache existed."""


@dataclass
class Decision:
    """What classification decided for one document (the persisted row values)."""

    outcome: str  # file | review | skipped
    reasons: tuple[str, ...] = ()
    confidence: int | None = None
    band: str | None = None
    entity: str | None = None
    unit: str | None = None
    category: str | None = None
    subcategory: str | None = None
    rule_id: str | None = None
    path: str | None = None
    from_cache: bool = False
    checks: dict[str, Checked] = field(default_factory=dict)
    find_queries: dict[str, str | None] = field(default_factory=dict)


def request_schema(snap: Snapshot) -> dict[str, Any]:
    cats = sorted(snap.categories.values(), key=lambda c: (c["sort_order"], c["id"]))
    subs = sorted(snap.subcategories.values(), key=lambda s: (s["category_id"], s["sort_order"]))
    ents = sorted(snap.entities.values(), key=lambda e: (e["sort_order"], e["key"]))
    return output_schema.build(
        [c["id"] for c in cats],
        [f"{s['category_id']}.{s['key']}" for s in subs],
        [e["key"] for e in ents if e["key"] != snap.visitors],
    )


def addressee_person(snap: Snapshot, addressee: str | None) -> str | None:
    """C5 §6.2.3: the one person whose name or an alias the addressee whole-word matches."""
    if not addressee:
        return None
    a = norm(addressee)
    hits = [k for k, p in snap.world.people.items() if any(contains_word(a, n) for n in p.names())]
    return hits[0] if len(hits) == 1 else None


def _document(conn: Connection, document_id: str, lock: bool = False) -> Mapping[str, Any] | None:
    d = T["documents"]
    q = select(d).where(d.c.id == document_id)
    return conn.execute(q.with_for_update() if lock else q).mappings().first()


def _live(doc: Mapping[str, Any] | None) -> bool:
    return doc is not None and doc["status"] == "processing" and doc["deleted_at"] is None


def model_output(
    ctx: Ctx, doc: Mapping[str, Any], s: prompts.Sections, p: prompts.Prompt,
    schema: dict[str, Any], model: ModelClient, *, bypass_cache: bool = False,
) -> tuple[dict[str, Any], ModelResult | None, prompts.Prompt]:  # fmt: skip
    """C5 §1.3 model-output cache: a hit needs `v`, `prompt_version`, `model` and today's schema.

    A14: an empty answer for a readable document is asked once more with the first page only;
    the cache keeps the final answer. Returns the prompt the answer came from."""
    sha = doc["sha256"]
    if not bypass_cache:
        raw = cache.read_model(ctx.textcache, sha, PROMPT_VERSION, model.model)
        if raw is not None and not output_schema.errors(raw, schema):
            return raw, None, p
    result = model.complete(p.system, p.user, schema)
    readable = sum(solid_chars(page) for page in s.pages) >= UNREADABLE_MIN
    if readable and output_schema.empty_answer(result.raw):
        p = prompts.build(s, max_pages=1)
        result = model.complete(p.system, p.user, schema)
    cache.write_model(ctx.textcache, sha, PROMPT_VERSION, model.model, result.raw)
    return result.raw, result, p


def classify(
    ctx: Ctx, document_id: str, model: ModelClient, *, bypass_cache: bool = False
) -> Decision:
    with ctx.engine.begin() as conn:
        doc = _document(conn, document_id, lock=True)
        if not _live(doc):
            return Decision("skipped")
        assert doc is not None
        pages = cache.read_pages(ctx.textcache, doc["sha256"])
        if pages is None:
            raise TextMissing("text_missing")
        conn.execute(
            update(T["documents"]).where(T["documents"].c.id == document_id)
            .values(pipeline_stage="classifying", updated_at=ctx.clock())
        )  # fmt: skip
        snap = registry.load(conn)
        sections = prompts.sections(conn, snap, doc, pages.pages)
        p = prompts.build(sections)
        schema = request_schema(snap)
    raw, result, p = model_output(ctx, doc, sections, p, schema, model, bypass_cache=bypass_cache)
    with settle_hooks(ctx), ctx.engine.begin() as conn:
        doc = _document(conn, document_id, lock=True)
        if not _live(doc):
            return Decision("skipped")
        assert doc is not None
        decision, work = decide(conn, doc, pages.pages, p, raw)
        _persist(ctx, conn, doc, pages, raw, result, model.model, decision, work)
        if decision.outcome == "review":
            finish_batch_if_done(conn, doc["batch_id"], ctx.clock())
        else:
            defer(conn, "file_document", document_id)
    return decision


@dataclass
class _Work:
    """Intermediate values `decide` hands to `_persist`."""

    out: Output
    counterparty_id: str | None = None
    person: str | None = None
    snap: Snapshot | None = None
    values: dict[str, Any] = field(default_factory=dict)
    placement: Any = None
    conflicting: tuple[str, ...] = ()
    model_percent: int = 0
    fiscal_year: int | None = None


def decide(
    conn: Connection,
    doc: Mapping[str, Any],
    all_pages: tuple[str, ...],
    p: prompts.Prompt,
    raw: dict[str, Any],
) -> tuple[Decision, _Work]:
    """C5 §6.1 → §6.2 → §4 → §8 → §9 → §7, on the current database state."""
    out = output_schema.clean(raw)
    snap = registry.load(conn)
    model_entity = out.fields["entity"].value if "entity" in out.fields else None
    if model_entity not in snap.entities or model_entity == snap.visitors:
        model_entity = None
    fy_end = None
    if model_entity:
        e = snap.entities[model_entity]
        fy_end = (e["fy_end_month"], e["fy_end_day"])
    checks = {k: check(f, p.pages_sent, fy_end) for k, f in out.fields.items()}

    cp_id = None
    if "counterparty" in out.fields:
        cp_id = resolve_counterparty(conn, out.fields["counterparty"].value)
        snap = registry.load(conn)
    addressee = out.fields.get("addressee")
    person = addressee_person(snap, addressee.value if addressee else None)
    values = _extracted_values(out)
    amount = values["amount"] if values["currency"] in MONEY else None
    visitor = conn.execute(
        select(T["batches"].c.visitor).where(T["batches"].c.id == doc["batch_id"])
    ).scalar()
    model_category = out.category if out.category != "unknown" else None
    subject = Subject(
        text=" ".join(all_pages),
        counterparty=snap.counterparty_keys.get(cp_id),
        doc_type=values["doc_type"],
        category=out.category,
        subcategory=out.subcategory,
        entity=model_entity,
        addressee=values["addressee"],
        addressee_person=person,
        amount=amount,
    )
    winner, dest, conflicting = None, None, ()
    if not visitor:
        outcome = evaluate(registry.rule_specs(conn), subject, snap.world)
        winner, dest, conflicting = outcome.winner, outcome.destination, outcome.conflicting
    if winner is not None and dest is not None:
        entity, unit, unresolved = dest.entity, dest.unit, dest.unit_unresolved
        category, sub = dest.category, dest.subcategory
        path_t, file_t = dest.path_template, dest.file_template
        naming_cp = dest.counterparty or snap.counterparty_keys.get(cp_id)
        entity_set, review = winner.action.entity is not None, dest.review
    else:
        entity = snap.visitors if visitor else model_entity
        unit, unresolved, review = None, False, False
        category = model_category
        sub = out.subcategory if category else None
        if sub is not None and sub not in snap.world.subcategories.get(category or "", set()):
            sub = None
        tpl = snap.world.template(category, entity)
        path_t, file_t = tpl if tpl else (None, None)
        naming_cp = snap.counterparty_keys.get(cp_id)
        entity_set = bool(visitor)
    render_doc = {**doc, **values}
    placement = place(
        snap, render_doc, entity=entity, unit=unit, category=category, subcategory=sub,
        counterparty=naming_cp, path_template=path_t, file_template=file_t,
    )  # fmt: skip
    model_percent = percent(out.confidence)
    s = snap.settings
    sc = score(
        rule_won=winner is not None,
        entity_set=entity_set,
        model_confidence=out.confidence,
        category_unknown=category is None,
        fields={k: c.verified for k, c in checks.items()},
        tokens=tokens_used(path_t, file_t) if placement else set(),
        fallbacks=placement.rendered.fallbacks if placement else {},
        low=s["confidence_low"],
        high=s["confidence_high"],
        no_entity=entity is None or unresolved or (category is not None and placement is None),
        conflict=bool(conflicting),
        review=review,
    )
    finds = {
        k: find_query(c, all_pages[c.page - 1] if c.page <= len(all_pages) else "")
        for k, c in checks.items()
    }
    work = _Work(
        out, cp_id, person, snap, values, placement, tuple(conflicting), model_percent,
        document_fiscal_year(snap.entity_info(entity), values["period_end"], values["doc_date"],
                             doc["arrived_at"]),
    )  # fmt: skip
    decision = Decision(
        outcome="review" if sc.reasons else "file",
        reasons=sc.reasons,
        confidence=sc.confidence,
        band=sc.band,
        entity=entity,
        unit=unit if not unresolved else None,
        category=category,
        subcategory=sub,
        rule_id=winner.id if winner else None,
        path=placement.path if placement else None,
        checks=checks,
        find_queries=finds,
    )
    return decision, work


def _extracted_values(out: Output) -> dict[str, Any]:
    f = out.fields
    amount = f.get("amount")
    return {
        "issuer": f["issuer"].value if "issuer" in f else None,
        "reference": f["reference"].value if "reference" in f else None,
        "doc_type": f["doc_type"].value if "doc_type" in f else None,
        "addressee": f["addressee"].value if "addressee" in f else None,
        "doc_date": f["doc_date"].day if "doc_date" in f else None,
        "period_start": f["period_start"].day if "period_start" in f else None,
        "period_end": f["period_end"].day if "period_end" in f else None,
        "due_date": f["due_date"].day if "due_date" in f else None,
        "amount": amount.amount if amount else None,
        "currency": amount.currency if amount else None,
    }


def _persist(
    ctx: Ctx,
    conn: Connection,
    doc: Mapping[str, Any],
    pages: cache.Pages,
    raw: dict[str, Any],
    result: ModelResult | None,
    model: str,
    d: Decision,
    w: _Work,
) -> None:
    snap = w.snap
    assert snap is not None
    x, ef, c, docs = T["extractions"], T["extraction_fields"], T["classifications"], T["documents"]
    now = ctx.clock()
    version = conn.execute(
        select(func.coalesce(func.max(x.c.version), 0)).where(x.c.document_id == doc["id"])
    ).scalar_one() + 1  # fmt: skip
    ext_id, cls_id = new_id("ext"), new_id("cls")
    conn.execute(
        insert(x).values(
            id=ext_id, document_id=doc["id"], version=version, text_method=pages.method,
            text_cache_key=doc["sha256"], char_count=pages.char_count, model=model,
            prompt_version=PROMPT_VERSION, raw_output=raw, from_cache=result is None,
            duration_ms=result.duration_ms if result else None,
            prompt_tokens=result.prompt_tokens if result else None,
            completion_tokens=result.completion_tokens if result else None,
        )
    )  # fmt: skip
    for key, chk in d.checks.items():
        f = chk.field
        conn.execute(
            insert(ef).values(
                extraction_id=ext_id, key=key, value=f.value, currency=f.currency,
                quote=f.quote, page=chk.page, stated_page=chk.stated_page,
                verified=chk.verified, find_query=d.find_queries.get(key),
                confidence=field_confidence(w.model_percent, chk.verified),
            )
        )  # fmt: skip
    ent = snap.entities[d.entity]["id"] if d.entity else None
    unit = snap.sub_units[(d.entity, d.unit)]["id"] if d.entity and d.unit else None
    pl = w.placement
    conn.execute(
        insert(c).values(
            id=cls_id, document_id=doc["id"], extraction_id=ext_id,
            method="rule" if d.rule_id else "llm", rule_id=d.rule_id,
            conflicting_rule_ids=list(w.conflicting), entity_id=ent, sub_unit_id=unit,
            category_id=d.category, subcategory_key=d.subcategory,
            counterparty_id=w.counterparty_id, model_confidence=w.model_percent,
            confidence=d.confidence, band=d.band, reasons=list(d.reasons),
            proposed_path=pl.rendered.folder if pl else None,
            proposed_file_name=pl.rendered.file_name if pl else None, created_at=now,
        )
    )  # fmt: skip
    if d.rule_id:
        store.record_firing(conn, d.rule_id, now)
    title = w.out.title or None
    if title and snap.lang_for(d.entity) == "ro":
        title = ro_comma_below(title)
    v = w.values
    values: dict[str, Any] = {
        **{k: v[k] for k in ("issuer", "reference", "doc_type", "addressee", "doc_date",
                             "period_start", "period_end", "due_date")},
        "amount": v["amount"] if v["currency"] in MONEY else None,
        "currency": v["currency"] if v["currency"] in MONEY else None,
        "title": title,
        "addressee_person_id": {k: i for i, k in snap.people_keys.items()}.get(w.person),
        "counterparty_id": w.counterparty_id, "entity_id": ent, "sub_unit_id": unit,
        "category_id": d.category, "subcategory_key": d.subcategory,
        "fiscal_year": w.fiscal_year, "confidence": d.confidence, "band": d.band,
        "reasons": list(d.reasons), "extraction_id": ext_id, "classification_id": cls_id,
        "rule_id": d.rule_id, "updated_at": now,
    }  # fmt: skip
    if d.outcome == "review":
        values |= {"status": "review", "pipeline_stage": "done", "pipeline_error": None}
    conn.execute(update(docs).where(docs.c.id == doc["id"]).values(**values))
    rebuild_fts(conn, doc["id"], ctx.textcache)
    if d.outcome == "review":
        keep_review(conn, _document(conn, doc["id"]), "refiled", "mona", now)  # type: ignore[arg-type]
