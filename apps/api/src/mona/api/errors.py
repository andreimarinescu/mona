"""C2 §1.2: one error envelope for every non-2xx JSON response."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from mona.fileops.errors import FileOpError
from mona.naming import to_camel

logger = logging.getLogger(__name__)


class ApiErrorInfo(BaseModel):
    code: str
    message: str
    field: str | None = None
    details: dict[str, Any] | None = None


class ApiError(BaseModel):
    error: ApiErrorInfo


def envelope(
    code: str,
    message: str,
    *,
    field: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        body["field"] = field
    if details is not None:
        body["details"] = details
    return {"error": body}


class ApiFailure(Exception):
    """Raised by handlers; rendered as the envelope with its status."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.field, self.details, self.headers = field, details, headers

    def response(self) -> JSONResponse:
        body = envelope(self.code, self.message, field=self.field, details=self.details)
        return JSONResponse(body, status_code=self.status, headers=self.headers)


def not_found(what: str = "item") -> ApiFailure:
    return ApiFailure(404, "not_found", f"No {what} with that id.")


def camel_path(loc: tuple[Any, ...] | list[Any]) -> str:
    return ".".join(to_camel(p) if isinstance(p, str) else str(p) for p in loc)


def field_of(name: str | None) -> str | None:
    return to_camel(name) if name else None


def from_service(err: FileOpError) -> ApiFailure:
    """C4 §2.4 service codes → C2 §1.2 statuses."""
    code, hint = err.code, err.hint
    field = field_of(getattr(err, "field", None))
    if code == "not_found":
        return ApiFailure(404, "not_found", "Not found.")
    if code == "invalid_argument":
        return ApiFailure(400, "invalid_request", err.message, field=field)
    if code == "not_allowed":
        return ApiFailure(403, "not_allowed", "That is not allowed here.", field=field)
    if code in ("already_undone", "superseded"):
        return ApiFailure(409, code, "The entry can't be undone now.")
    if code == "not_undoable":
        return ApiFailure(422, "not_undoable", "The entry can't be undone.")
    if hint == "stale":
        return ApiFailure(409, "stale", "The document changed meanwhile; re-read and retry.")
    reason = hint or code
    return ApiFailure(409, "conflict", "The change conflicts with the current state.",
                      details={"reason": reason})  # fmt: skip


async def _failure(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiFailure)
    return exc.response()


async def _validation(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = []
    for e in exc.errors():
        loc = [p for p in e.get("loc", ()) if p not in ("body", "query", "path", "header")]
        errors.append({"field": camel_path(loc) or None, "message": str(e.get("msg", ""))})
    first = errors[0]["field"] if errors else None
    body = envelope(
        "invalid_request", "The request is invalid.", field=first, details={"errors": errors}
    )
    return JSONResponse(body, status_code=400)


async def _http(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 404:
        body = envelope("not_found", "Not found.")
    else:
        body = envelope("invalid_request", "The request is invalid.")
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


def install(app: FastAPI) -> None:
    app.add_exception_handler(ApiFailure, _failure)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(StarletteHTTPException, _http)


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    s: {"model": ApiError} for s in (400, 401, 403, 404, 409, 413, 415, 422, 423, 500, 503)
}


def errors(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` declaring `ApiError` for these statuses (C2 §16 item 4)."""
    return {s: {"model": ApiError} for s in statuses}
