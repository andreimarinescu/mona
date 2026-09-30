from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated, Literal

import anyio
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mona import __version__
from mona.chat.router import MAX_BODY, ApiFailure
from mona.chat.router import router as chat_router
from mona.db import get_engine, get_sync_engine
from mona.http import BodyLimit
from mona.mcp.server import MAX_MCP_BODY, ServiceKeyAuth, build_mcp_app
from mona.settings import get_settings

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


def pipeline_startup(app: FastAPI) -> None:
    """C7 §1.2 single-filesystem check and §4.3 recovery before serving."""
    from mona.pipeline.stages import recover
    from mona.services import make_context

    ctx = make_context(get_sync_engine(), get_settings().mona_data_dir)
    recover(ctx, timedelta(0))
    app.state.pipeline = ctx


def create_app() -> FastAPI:
    mcp_app = build_mcp_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await anyio.to_thread.run_sync(pipeline_startup, app)
        async with mcp_app.lifespan(app):
            yield

    app = FastAPI(title="Mona", version=__version__, lifespan=lifespan)
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
