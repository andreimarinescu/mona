from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mona import __version__
from mona.chat.router import MAX_BODY, ApiFailure
from mona.chat.router import router as chat_router
from mona.db import get_engine
from mona.http import BodyLimit
from mona.mcp.server import MAX_MCP_BODY, ServiceKeyAuth, build_mcp_app

INVALID_REQUEST = {"error": {"code": "invalid_request", "message": "The request is invalid."}}


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "error"]
    version: str


router = APIRouter(prefix="/api")


@router.get("/health", operation_id="getHealth", responses={503: {"model": Health}})
async def health(response: Response, engine: Annotated[AsyncEngine, Depends(get_engine)]) -> Health:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return Health(status="degraded", db="error", version=__version__)
    return Health(status="ok", db="ok", version=__version__)


async def _api_failure(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiFailure)
    return exc.response()


async def _invalid(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(INVALID_REQUEST, status_code=400)


def create_app() -> FastAPI:
    mcp_app = build_mcp_app()
    app = FastAPI(title="Mona", version=__version__, lifespan=mcp_app.lifespan)
    app.include_router(router)
    app.include_router(chat_router)
    app.add_exception_handler(ApiFailure, _api_failure)
    app.add_exception_handler(RequestValidationError, _invalid)
    too_large = {"error": "payload_too_large"}
    app.add_route(
        "/mcp", ServiceKeyAuth(BodyLimit(mcp_app, {"/mcp": (MAX_MCP_BODY, 413, too_large)}))
    )
    app.add_middleware(BodyLimit, limits={"/api/chat": (MAX_BODY, 400, INVALID_REQUEST)})
    return app


app = create_app()
