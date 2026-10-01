"""C2 conventions the L4 endpoints share: pages, weak ETags (§1.5), ApplyResult (§7)."""

import hashlib

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from mona.dto import models as dto
from mona.dto.base import Dto
from mona.services import Applied


class Page[T](Dto):
    items: list[T]
    total: int
    offset: int
    limit: int


class FailedMove(Dto):
    document_id: str
    code: str


class ApplyResult(Dto):
    preview: dto.RulePreview
    group_id: str | None
    moved: int
    unchanged: int
    failed: list[FailedMove]


def applied(a: Applied) -> ApplyResult:
    assert a.preview is not None
    return ApplyResult(
        preview=a.preview,
        group_id=a.group_id,
        moved=a.moved,
        unchanged=a.unchanged,
        failed=[FailedMove(document_id=f["document_id"], code=f["code"]) for f in a.failed],
    )


def etagged(request: Request, model: Dto) -> Response:
    """A polled body with a weak ETag; 304 when `If-None-Match` already has it."""
    body = model.model_dump_json().encode()
    tag = 'W/"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"etag": tag})
    return JSONResponse(content=model.model_dump(mode="json"), headers={"etag": tag})
