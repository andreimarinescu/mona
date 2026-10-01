"""C2 §11: interview endpoints (semantics C6), with the C2 §14 card-action notes."""

from functools import partial
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Query, Request, Response
from pydantic import Field
from sqlalchemy import func, select

from mona.db import get_engine
from mona.db.models import Interview as InterviewRow
from mona.db.models import InterviewAnswer, InterviewQuestion, Profile
from mona.dto import models as dto
from mona.dto.base import Dto
from mona.dto.load import interview as load_interview
from mona.ids import is_id
from mona.interviews import answers, service
from mona.services import ServiceError, registry
from mona.services.dto import rule as rule_dto
from mona.services.registry import T
from mona.workflow.common import RestError, errors, from_service, get_ctx, not_found
from mona.workflow.http import ApplyResult, Page, applied, etagged

router = APIRouter(prefix="/api/interviews", tags=["interviews"])
ConversationId = Annotated[str | None, Field(pattern=r"^cnv_[0-9a-hjkmnp-tv-z]{26}$")]


class InterviewCreate(Dto):
    scope: dto.InterviewScope
    lang: dto.Lang | None = None


class InterviewCreated(Dto):
    interview: dto.Interview
    reused: bool


class AnswerBody(Dto):
    option_id: str | None = Field(default=None, min_length=1, max_length=8)
    free_text: str | None = Field(default=None, min_length=1, max_length=500)
    conversation_id: ConversationId = None


class ActionBody(Dto):
    conversation_id: ConversationId = None


class AnswerResult(Dto):
    question: dto.InterviewQuestion
    rules: list[dto.Rule]
    previews: list[dto.RulePreview]
    interview_status: dto.InterviewStatus


class ApplyAllResult(Dto):
    results: list[ApplyResult]


def _check(interview_id: str, question_id: str | None = None) -> None:
    if not is_id(interview_id, "int") or (
        question_id is not None and not is_id(question_id, "qst")
    ):
        raise not_found("interview")


async def _load(interview_id: str) -> dto.Interview:
    async with get_engine().connect() as conn:
        found = await load_interview(conn, interview_id)
    if found is None:
        raise not_found("interview")
    return found


async def _question(interview_id: str, question_id: str) -> dto.InterviewQuestion:
    iv = await _load(interview_id)
    q = next((q for q in iv.questions if q.id == question_id), None)
    if q is None:
        raise not_found("question")
    return q


async def _owned(interview_id: str, question_id: str) -> None:
    async with get_engine().connect() as conn:
        row = (
            await conn.execute(
                select(InterviewQuestion.id).where(
                    InterviewQuestion.id == question_id,
                    InterviewQuestion.interview_id == interview_id,
                )
            )
        ).first()
    if row is None:
        raise not_found("question")


async def _locale() -> str:
    async with get_engine().connect() as conn:
        return (await conn.execute(select(Profile.locale))).scalar() or "en"


async def _existing_answer(question_id: str) -> dict[str, Any] | None:
    async with get_engine().connect() as conn:
        a = (
            await conn.execute(
                select(InterviewAnswer.option_id, InterviewAnswer.free_text).where(
                    InterviewAnswer.question_id == question_id
                )
            )
        ).first()
    return {"optionId": a.option_id, "freeText": a.free_text} if a else None


async def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))
    except ServiceError as err:
        raise from_service(err) from None


@router.get(
    "/{interview_id}",
    operation_id="getInterview",
    response_model=dto.Interview,
    responses=errors(404),
)
async def get_interview(interview_id: str, request: Request) -> Response:
    _check(interview_id)
    return etagged(request, await _load(interview_id))


@router.get(
    "", operation_id="listInterviews", response_model=Page[dto.Interview], responses=errors(400)
)
async def list_interviews(
    status: dto.InterviewStatus | None = None,
    kind: dto.InterviewKind | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[dto.Interview]:
    clauses = []
    if status is not None:
        clauses.append(InterviewRow.status == status)
    if kind is not None:
        clauses.append(InterviewRow.kind == kind)
    async with get_engine().connect() as conn:
        total = (
            await conn.execute(select(func.count()).select_from(InterviewRow).where(*clauses))
        ).scalar_one()
        ids = (
            (
                await conn.execute(
                    select(InterviewRow.id)
                    .where(*clauses)
                    .order_by(InterviewRow.created_at.desc(), InterviewRow.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        items = [await load_interview(conn, i) for i in ids]
    return Page(items=[i for i in items if i], total=total, offset=offset, limit=limit)


@router.post(
    "",
    operation_id="createInterview",
    response_model=InterviewCreated,
    status_code=201,
    responses=errors(400, 404, 422),
)
async def create_interview(body: InterviewCreate, response: Response) -> InterviewCreated:
    scope = body.scope.model_dump(by_alias=False)
    started = await _run(service.start, get_ctx(), scope, lang=body.lang)
    if started.reused:
        response.status_code = 200
    return InterviewCreated(interview=await _load(started.interview_id), reused=started.reused)


async def _answer_result(outcome: answers.AnswerOutcome) -> AnswerResult:
    lang = await _locale()

    def rules() -> list[dto.Rule]:
        ctx = get_ctx()
        with ctx.engine.connect() as conn:
            snap = registry.load(conn)
            r = T["rules"]
            rows = {
                row["id"]: row
                for row in conn.execute(select(r).where(r.c.id.in_(outcome.rule_ids))).mappings()
            }
            return [rule_dto(snap, rows[i], lang) for i in outcome.rule_ids]

    iv = await _load(outcome.interview_id)
    question = next(q for q in iv.questions if q.id == outcome.question_id)
    return AnswerResult(
        question=question,
        rules=await anyio.to_thread.run_sync(rules),
        previews=outcome.previews,
        interview_status=iv.status,
    )


@router.post(
    "/{interview_id}/questions/{question_id}/answer",
    operation_id="answerQuestion",
    response_model=AnswerResult,
    responses=errors(400, 404, 409, 422),
)
async def answer_question(interview_id: str, question_id: str, body: AnswerBody) -> AnswerResult:
    _check(interview_id, question_id)
    await _owned(interview_id, question_id)
    if (body.option_id is None) == (body.free_text is None):
        raise RestError(400, "invalid_request", "Give optionId or freeText.", field="optionId")
    lang = await _locale()
    try:
        outcome = await anyio.to_thread.run_sync(
            partial(
                answers.answer,
                get_ctx(),
                question_id,
                option_id=body.option_id,
                free_text=body.free_text,
                actor="user",
                via="ui",
                conversation_id=body.conversation_id,
                preview_lang=lang,
            )
        )
    except ServiceError as err:
        if err.hint == "already_answered":
            raise RestError(
                409,
                "already_answered",
                err.message,
                details={"answer": await _existing_answer(question_id)},
            ) from None
        if err.field == "option_id":
            raise RestError(422, "invalid_value", err.message, field="optionId") from None
        raise from_service(err) from None
    return await _answer_result(outcome)


@router.post(
    "/{interview_id}/questions/{question_id}/skip",
    operation_id="skipQuestion",
    response_model=dto.InterviewQuestion,
    responses=errors(404, 409),
)
async def skip_question(
    interview_id: str, question_id: str, body: ActionBody
) -> dto.InterviewQuestion:
    _check(interview_id, question_id)
    await _owned(interview_id, question_id)
    await _run(answers.skip, get_ctx(), question_id, conversation_id=body.conversation_id)
    return await _question(interview_id, question_id)


@router.post(
    "/{interview_id}/questions/{question_id}/apply",
    operation_id="applyQuestionRules",
    response_model=ApplyAllResult,
    responses=errors(404, 409),
)
async def apply_question(interview_id: str, question_id: str, body: ActionBody) -> ApplyAllResult:
    _check(interview_id, question_id)
    await _owned(interview_id, question_id)
    lang = await _locale()
    results = await _run(
        answers.apply_all,
        get_ctx(),
        question_id,
        actor="user",
        via="ui",
        conversation_id=body.conversation_id,
        lang=lang,
    )
    return ApplyAllResult(results=[applied(r) for r in results])


@router.post(
    "/{interview_id}/cancel",
    operation_id="cancelInterview",
    response_model=dto.Interview,
    responses=errors(404, 409),
)
async def cancel_interview(interview_id: str) -> dto.Interview:
    _check(interview_id)
    await _run(service.cancel, get_ctx(), interview_id)
    return await _load(interview_id)
