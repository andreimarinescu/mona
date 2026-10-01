"""C6 §6–§7.1: answers (options, ask, free text), skip, and Apply all."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, func, insert, select, update

from mona.chat.notes import interview_answer, note_value, rule_apply
from mona.db.models import Base
from mona.dto import RulePreview
from mona.ids import new_id
from mona.rules import store
from mona.rules.engine import learned_priority
from mona.rules.grammar import Condition, RuleBody
from mona.rules.text import ALIASES, AND, OR, PHRASES, QUOTES, _join, _money, _name
from mona.services import Applied, Ctx, ServiceError, apply_rule, preview_rule, registry
from mona.services.placement import subject
from mona.services.rules import Visible
from mona.workflow.common import add_note, write_cards

T = Base.metadata.tables
NAME_MAX = 120
FALLBACK_NAME = 60
NOT_READY = ("generating", "failed", "cancelled")


@dataclass
class AnswerOutcome:
    question_id: str
    interview_id: str
    interview_status: str
    rule_ids: list[str]
    previews: list[RulePreview] = field(default_factory=list)
    card_refs: list[str] = field(default_factory=list)


def _cut(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    cut = s[:n]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip()


def render_value(c: Condition, lang: str, names: Any) -> str:
    """A condition's value as C5 §4.7 renders it (quoted text, names, money)."""
    if c.field == "amount":
        if c.op == "between":
            return f"{_money(c.value[0], lang)} – {_money(c.value[1], lang)}"
        return _money(c.value, lang)
    values = c.value if isinstance(c.value, list) else [c.value]
    conj = AND if c.op == "contains_all" else OR
    key = ALIASES.get((c.field, c.op), (c.field, c.op))
    if "{q}" in PHRASES[key][lang][0]:
        o, e = QUOTES[lang]
        return _join([f"{o}{v}{e}" for v in values], lang, conj)
    return _join([_name(c, v, lang, names) for v in values], lang, conj)


def question_row(conn: Connection, question_id: str, *, lock: bool = False) -> Mapping[str, Any]:
    q = T["interview_questions"]
    stmt = select(q).where(q.c.id == question_id)
    row = conn.execute(stmt.with_for_update() if lock else stmt).mappings().first()
    if row is None:
        raise ServiceError("not_found", "No interview question with that id.")
    return row


def question_counterparty(conn: Connection, question: Mapping[str, Any], kind: str) -> str | None:
    """The affected documents' shared counterparty; for seed, the one its branches name (§4.6)."""
    d = T["documents"]
    ids = list(question["affected_document_ids"])
    if ids:
        cps = set(conn.execute(select(d.c.counterparty_id).where(d.c.id.in_(ids))).scalars())
        return next(iter(cps)) if len(cps) == 1 and None not in cps else None
    if kind != "seed":
        return None
    keys = {
        c["value"]
        for o in question["options"]
        for b in (o.get("rule_draft") or {}).get("branches", [])
        for c in b["conditions"]
        if c["field"] == "counterparty" and c["op"] == "equals"
    }
    if len(keys) != 1:
        return None
    cp = T["counterparties"]
    return conn.execute(select(cp.c.id).where(cp.c.key == next(iter(keys)))).scalar()


def _rules_of(conn: Connection, question_id: str) -> list[Mapping[str, Any]]:
    r = T["rules"]
    return list(
        conn.execute(
            select(r).where(r.c.origin_question_id == question_id).order_by(r.c.created_at, r.c.id)
        ).mappings()
    )


def _source_priority(conn: Connection, ctx: Ctx, doc_ids: list[str]) -> list[int]:
    """C5 §4.6.1 `P`: priorities of active rules that hold on any source document."""
    if not doc_ids:
        return []
    snap = registry.load(conn)
    specs = [s for s in registry.rule_specs(conn) if s.state == "active"]
    d = T["documents"]
    out = []
    for doc in conn.execute(select(d).where(d.c.id.in_(doc_ids))).mappings():
        s = subject(conn, snap, doc, ctx.textcache)
        out += [r.priority for r in specs if r.matches(s, snap.world)]
    return out


def _draft_rules(
    conn: Connection,
    ctx: Ctx,
    question: Mapping[str, Any],
    option: Mapping[str, Any],
    base_name: str,
    lang: str,
    *,
    actor: str,
    via: str,
) -> list[str]:
    """§6.1 steps 2–3: one draft rule per branch, journaled `rule.create`."""
    draft = option["rule_draft"]
    snap = registry.load(conn)
    source = _source_priority(conn, ctx, list(question["affected_document_ids"]))
    ids = []
    for branch in draft["branches"]:
        body = RuleBody.model_validate(branch)
        name = f"{base_name} · {option['label']}"
        if draft["kind"] == "depends":
            on = next(c for c in body.conditions if c.field == draft["discriminator"])
            name += f" ({render_value(on, lang, snap.names)})"
        name = _cut(name, NAME_MAX)
        row, _ = store.save_rule(
            conn,
            key=store.unique_key(conn, name),
            name=name,
            state="draft",
            source="interview",
            body=body,
            priority=learned_priority(len(body.conditions), source),
            names=snap.names,
            origin_question_id=question["id"],
        )
        store.journal_rule(conn, "rule.create", None, row, actor=actor, via=via, at=ctx.clock())
        ids.append(row["id"])
    return ids


def _ask_rule(
    conn: Connection,
    ctx: Ctx,
    question: Mapping[str, Any],
    cp_id: str,
    name: str,
    *,
    actor: str,
    via: str,
) -> str:
    """§6.2: one active `review: true` rule scoped to the counterparty."""
    snap = registry.load(conn)
    body = RuleBody.model_validate(
        {
            "conditions": [
                {"field": "counterparty", "op": "equals", "value": snap.counterparty_keys[cp_id]}
            ],
            "action": {"review": True},
        }
    )
    name = _cut(name, NAME_MAX)
    row, _ = store.save_rule(
        conn,
        key=store.unique_key(conn, name),
        name=name,
        state="active",
        source="interview",
        body=body,
        priority=None,
        names=snap.names,
        origin_question_id=question["id"],
    )
    store.journal_rule(conn, "rule.create", None, row, actor=actor, via=via, at=ctx.clock())
    return row["id"]


def _finish_if_done(conn: Connection, ctx: Ctx, interview_id: str) -> str:
    i, q = T["interviews"], T["interview_questions"]
    status = conn.execute(select(i.c.status).where(i.c.id == interview_id)).scalar_one()
    open_n = conn.execute(
        select(func.count()).where(q.c.interview_id == interview_id, q.c.status == "open")
    ).scalar_one()
    if status == "ready" and open_n == 0:
        conn.execute(
            update(i).where(i.c.id == interview_id).values(status="done", finished_at=ctx.clock())
        )
        return "done"
    return status


def _existing_answer(conn: Connection, question_id: str) -> Mapping[str, Any] | None:
    a = T["interview_answers"]
    return conn.execute(select(a).where(a.c.question_id == question_id)).mappings().first()


def _interview(conn: Connection, interview_id: str, *, lock: bool = False) -> Mapping[str, Any]:
    i = T["interviews"]
    stmt = select(i).where(i.c.id == interview_id)
    return conn.execute(stmt.with_for_update() if lock else stmt).mappings().one()


def _outcome(
    ctx: Ctx, question_id: str, preview_lang: str, visible: Visible = None
) -> AnswerOutcome:
    with ctx.engine.connect() as conn:
        q = question_row(conn, question_id)
        status = _interview(conn, q["interview_id"])["status"]
        rules = _rules_of(conn, question_id)
    previews = [
        preview_rule(ctx, r["id"], lang=preview_lang, visible=visible)
        for r in rules
        if not r["action"].get("review")
    ]
    return AnswerOutcome(question_id, q["interview_id"], status, [r["id"] for r in rules], previews)


def answer(
    ctx: Ctx,
    question_id: str,
    *,
    option_id: str | None = None,
    free_text: str | None = None,
    actor: str,
    via: str,
    conversation_id: str | None = None,
    channel: str | None = None,
    tool: str | None = None,
    preview_lang: str = "en",
    visible: Visible = None,
) -> AnswerOutcome:
    """§6.1–§6.4 in one transaction; the same answer again returns the existing result.
    `visible` drops documents the channel can't see from the previews (C4 §2.6)."""
    if (option_id is None) == (free_text is None):
        raise ServiceError(
            "invalid_argument", "Give option_id or free_text, not both.", field="option_id"
        )
    if free_text is not None and not 1 <= len(free_text) <= 500:
        raise ServiceError(
            "invalid_argument", "free_text is 1 to 500 characters.", field="free_text"
        )
    refs: list[str] = []
    with ctx.engine.begin() as conn:
        q = question_row(conn, question_id, lock=True)
        existing = _existing_answer(conn, question_id)
        if existing is not None:
            if existing["option_id"] == option_id and existing["free_text"] == free_text:
                return _outcome(ctx, question_id, preview_lang, visible)
            raise ServiceError(
                "conflict", "The question already has a different answer.", hint="already_answered"
            )
        if q["status"] == "skipped":
            raise ServiceError(
                "conflict", "A skipped question can't be answered.", hint="question_skipped"
            )
        iv = _interview(conn, q["interview_id"], lock=True)
        if iv["status"] in NOT_READY:
            raise ServiceError("conflict", "The interview isn't ready.", hint="interview_not_ready")
        option = None
        if option_id is not None:
            option = next((o for o in q["options"] if o["id"] == option_id), None)
            if option is None:
                raise ServiceError(
                    "invalid_argument",
                    f"Unknown option '{option_id}'.",
                    field="option_id",
                    valid=[o["id"] for o in q["options"]],
                )
        conn.execute(
            insert(T["interview_answers"]).values(
                id=new_id("ans"),
                question_id=question_id,
                option_id=option_id,
                free_text=free_text,
                actor=actor,
                via=via,
            )
        )
        iq = T["interview_questions"]
        conn.execute(update(iq).where(iq.c.id == question_id).values(status="answered"))
        cp_id = question_counterparty(conn, q, iv["kind"])
        rule_ids: list[str] = []
        ask_rule = False
        if option is not None and option["rule_draft"]["kind"] == "ask":
            if cp_id is not None:
                name = f"{_cp_name(conn, cp_id)} · {option['label']}"
                rule_ids = [_ask_rule(conn, ctx, q, cp_id, name, actor=actor, via=via)]
                ask_rule = True
        elif option is not None:
            base = _cp_name(conn, cp_id) if cp_id else _cut(q["text"], FALLBACK_NAME)
            rule_ids = _draft_rules(conn, ctx, q, option, base, iv["lang"], actor=actor, via=via)
        _finish_if_done(conn, ctx, q["interview_id"])
        names = [store.rule_row(conn, r)["name"] for r in rule_ids]  # type: ignore[index]
        if option is not None:
            text = interview_answer(q["text"], option["label"], [] if ask_rule else names)
            if ask_rule:
                text += (
                    f' 1 rule created: "{note_value(names[0])}" (documents like these will'
                    " always come to review)."
                )
            add_note(conn, conversation_id, "interview.answer", text)
        else:
            add_note(
                conn,
                conversation_id,
                "interview.answer_text",
                f'Answered interview question "{note_value(q["text"])}" in their own words: '
                f'"{note_value(free_text or "")}". No rule was drafted.',
            )
        if tool is not None and channel is not None and not ask_rule:
            refs = write_cards(
                conn, channel, tool, [("rulePreview", {"rule_id": r}) for r in rule_ids]
            )
    if rule_ids:
        with ctx.engine.connect() as conn:
            store.write_export(conn, ctx.config_dir, now=ctx.clock())
    out = _outcome(ctx, question_id, preview_lang, visible)
    out.card_refs = refs
    return out


def _cp_name(conn: Connection, cp_id: str) -> str:
    cp = T["counterparties"]
    return conn.execute(select(cp.c.name).where(cp.c.id == cp_id)).scalar_one()


def skip(ctx: Ctx, question_id: str, *, conversation_id: str | None = None) -> str:
    """§6.5; skipping a skipped question changes nothing."""
    with ctx.engine.begin() as conn:
        q = question_row(conn, question_id, lock=True)
        if q["status"] == "skipped":
            return q["interview_id"]
        if q["status"] == "answered":
            raise ServiceError(
                "conflict", "An answered question can't be skipped.", hint="already_answered"
            )
        iv = _interview(conn, q["interview_id"], lock=True)
        if iv["status"] in NOT_READY:
            raise ServiceError("conflict", "The interview isn't ready.", hint="interview_not_ready")
        iq = T["interview_questions"]
        conn.execute(update(iq).where(iq.c.id == question_id).values(status="skipped"))
        _finish_if_done(conn, ctx, q["interview_id"])
        add_note(
            conn,
            conversation_id,
            "interview.skip",
            f'Skipped interview question "{note_value(q["text"])}".',
        )
    return q["interview_id"]


def apply_all(
    ctx: Ctx,
    question_id: str,
    *,
    actor: str,
    via: str,
    conversation_id: str | None = None,
    lang: str = "en",
) -> list[Applied]:
    """§7.1: each `draft`/`active` rule of an answered question, in branch order."""
    with ctx.engine.connect() as conn:
        q = question_row(conn, question_id)
        if q["status"] != "answered":
            raise ServiceError(
                "conflict", "The question has no answer yet.", hint="nothing_to_apply"
            )
        rules = [
            r
            for r in _rules_of(conn, question_id)
            if r["state"] in ("draft", "active") and not r["action"].get("review")
        ]
    if not rules:
        raise ServiceError("conflict", "No rule to apply.", hint="nothing_to_apply")
    results = [apply_rule(ctx, r["id"], actor=actor, via=via, lang=lang) for r in rules]
    if conversation_id:
        with ctx.engine.begin() as conn:
            for r, res in zip(rules, results, strict=True):
                add_note(
                    conn,
                    conversation_id,
                    "rule.apply",
                    rule_apply(r["name"], res.moved, res.unchanged),
                )
    return results
