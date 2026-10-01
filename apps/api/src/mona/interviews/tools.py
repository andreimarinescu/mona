"""C4 §3.6 `start_interview` and §3.7 `answer_question`."""

from typing import Annotated, Any, Literal

from pydantic import Field

from mona.db import get_engine
from mona.dto.models import RulePreview
from mona.interviews import answers, service
from mona.mcp.core import ToolFailure, channel, clip, fit, tool
from mona.mcp.filters import matching_counterparties
from mona.mcp.write import candidate_filter
from mona.visibility import scope_for
from mona.workflow.common import get_ctx
from mona.workflow.mcp import run, via

PREVIEW_MOVES = 2
BatchIdParam = Annotated[str | None, Field(pattern=r"^bat_[0-9a-hjkmnp-tv-z]{26}$")]
DocIds = Annotated[
    list[Annotated[str, Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")]] | None,
    Field(min_length=1, max_length=50),
]


def preview_result(p: RulePreview, moves_max: int) -> dict[str, Any]:
    """C4 §3.8's result shape from a RulePreview."""
    moves = [
        {
            "document_id": m.document_id,
            "title": clip(m.title),
            "from": "/".join([*m.from_, m.from_file_name]),
            "to": "/".join([*m.to, m.to_file_name]),
        }
        for m in p.moves[:moves_max]
    ]
    out: dict[str, Any] = {
        "rule_id": p.rule.id,
        "name": p.rule.name,
        "state": p.rule.state,
        "condition_text": p.rule.condition_text,
        "moves_total": p.moves_total,
        "stays_total": p.stays_total,
        "moves": moves,
    }
    if len(p.moves) > moves_max:
        out["truncated"] = True
    return out


@tool(
    "Show or start a short interview (at most seven grouped questions) about documents you were "
    "unsure of: after a batch, for the review queue, or for one counterparty. If questions for "
    "that scope are ready or being prepared, this shows them instead of starting again. It "
    "appears as an interview card that fills in by itself; tell the person the questions are "
    "here or coming, and don't wait for them. The card shows the questions; introduce them in "
    "one line and never restate or invent them."
)
async def start_interview(
    batch_id: BatchIdParam = None,
    queue: Literal[True] | None = None,
    counterparty: Annotated[str | None, Field(min_length=1, max_length=160)] = None,
    document_ids: DocIds = None,
    lang: Literal["en", "fr", "ro"] | None = None,
) -> dict:
    given = [x for x in (batch_id, queue, counterparty, document_ids) if x is not None]
    if len(given) != 1:
        raise ToolFailure(
            "invalid_argument",
            "Give exactly one of batch_id, queue, counterparty or document_ids.",
            field="batch_id",
        )
    if batch_id is not None:
        scope: dict[str, Any] = {"type": "batch", "batch_id": batch_id}
    elif queue:
        scope = {"type": "queue"}
    elif document_ids is not None:
        scope = {"type": "documents", "document_ids": document_ids}
    else:
        async with get_engine().connect() as conn:
            ids = await matching_counterparties(conn, counterparty or "")
        if len(ids) != 1:
            raise ToolFailure(
                "invalid_argument",
                f"'{counterparty}' names {'no' if not ids else 'several'} counterparties.",
                field="counterparty",
            )
        scope = {"type": "counterparty", "counterparty_id": ids[0]}
    ch = channel()
    started = await run(
        service.start, get_ctx(), scope, lang=lang, channel=ch, tool="start_interview"
    )
    result = {
        "interview_id": started.interview_id,
        "status": started.status,
        "open_questions": started.open_questions,
        "questions": [
            {**q, "text": clip(q["text"], 300), "options": [clip(o, 120) for o in q["options"]]}
            for q in started.questions
        ],
        "reused": started.reused,
        "card_refs": started.card_refs,
    }
    return fit(result, "questions")


@tool(
    "Record the person's answer to an interview question when they give it in words instead of "
    "pressing a button. Pass the option they chose, or their own words if none fits. The "
    "resulting rule is shown as a preview; nothing moves until it is applied."
)
async def answer_question(
    question_id: Annotated[str, Field(pattern=r"^qst_[0-9a-hjkmnp-tv-z]{26}$")],
    option_id: Annotated[str | None, Field(min_length=1, max_length=8)] = None,
    free_text: Annotated[str | None, Field(min_length=1, max_length=500)] = None,
) -> dict:
    if (option_id is None) == (free_text is None):
        raise ToolFailure(
            "invalid_argument", "Give option_id or free_text, not both.", field="option_id"
        )
    ch = channel()
    async with get_engine().connect() as conn:
        keep = candidate_filter(await scope_for(conn, ch))
    try:
        out = await run(
            answers.answer,
            get_ctx(),
            question_id,
            option_id=option_id,
            free_text=free_text,
            actor="mona",
            via=via(ch),
            channel=ch,
            tool="answer_question",
            visible=keep,
        )
    except ToolFailure as e:
        if e.extra.get("hint") == "already_answered":
            existing = await run(_existing, question_id)
            raise ToolFailure("conflict", e.message, hint=existing) from None
        raise
    states = await run(_states, out.rule_ids)
    result = {
        "question_id": question_id,
        "status": "answered",
        "rules": [{"id": r, "state": states[r]} for r in out.rule_ids],
        "previews": [preview_result(p, PREVIEW_MOVES) for p in out.previews],
        "card_refs": out.card_refs,
    }
    return fit(result, "previews")


def _existing(question_id: str) -> str:
    from sqlalchemy import select

    from mona.services.registry import T

    a = T["interview_answers"]
    with get_ctx().engine.connect() as conn:
        row = conn.execute(select(a).where(a.c.question_id == question_id)).first()
    if row is None:
        return "The question has another answer."
    if row.option_id:
        return f"Already answered with option '{row.option_id}'."
    return f'Already answered in the person\'s own words: "{clip(row.free_text, 120)}".'


def _states(rule_ids: list[str]) -> dict[str, str]:
    from sqlalchemy import select

    from mona.services.registry import T

    r = T["rules"]
    with get_ctx().engine.connect() as conn:
        return dict(conn.execute(select(r.c.id, r.c.state).where(r.c.id.in_(rule_ids))).all())
