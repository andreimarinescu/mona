import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Depends, FastAPI, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mona import __version__
from mona.api import auth, documents, home, journal, registry, rules, system
from mona.api.errors import install as install_errors
from mona.api.guard import ApiGuard, RequestLog
from mona.chat.router import router as chat_router
from mona.db import get_engine, get_sync_engine
from mona.dto.models import Person
from mona.http import BodyLimit
from mona.interviews.api import router as interviews_router
from mona.logs import configure_logging
from mona.mcp.server import MAX_MCP_BODY, ServiceKeyAuth, build_mcp_app
from mona.settings import get_settings
from mona.workflow.api import router as workflow_router


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


def contract_schema(app: FastAPI) -> None:
    """C2 §16: validation errors are 400 envelopes, so FastAPI's default 422 goes; C1 §11 DTOs
    no route returns as such are still components."""
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = build()
        for item in schema["paths"].values():
            for op in item.values():
                default = op.get("responses", {}).get("422", {})
                if "HTTPValidationError" in json.dumps(default):
                    del op["responses"]["422"]
        components = schema["components"]["schemas"]
        for name in ("HTTPValidationError", "ValidationError"):
            components.pop(name, None)
        for model in (Person,):
            components.setdefault(
                model.__name__, model.model_json_schema(ref_template="#/components/schemas/{model}")
            )
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def pipeline_startup(app: FastAPI) -> None:
    """C7 §1.2 single-filesystem check and §4.3 recovery before serving."""
    from mona.pipeline.hooks import interview_hooks
    from mona.pipeline.stages import recover
    from mona.services import make_context

    ctx = make_context(get_sync_engine(), get_settings().mona_data_dir, **interview_hooks())
    recover(ctx, timedelta(0))
    app.state.pipeline = ctx


def create_app() -> FastAPI:
    get_settings()
    configure_logging()
    mcp_app = build_mcp_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await anyio.to_thread.run_sync(pipeline_startup, app)
        async with mcp_app.lifespan(app):
            yield

    app = FastAPI(
        title="Mona",
        version=__version__,
        lifespan=lifespan,
        separate_input_output_schemas=False,
    )
    install_errors(app)
    contract_schema(app)
    app.include_router(router)
    app.include_router(auth.router)
    app.include_router(chat_router)
    app.include_router(documents.router)
    app.include_router(rules.router)
    app.include_router(journal.router)
    app.include_router(home.router)
    app.include_router(system.router)
    app.include_router(registry.router)
    app.include_router(interviews_router)
    app.include_router(workflow_router)
    too_large = {"error": "payload_too_large"}
    app.add_route(
        "/mcp",
        ServiceKeyAuth(BodyLimit(mcp_app, {"/mcp": (MAX_MCP_BODY, 413, too_large)})),
        include_in_schema=False,
    )
    app.add_middleware(ApiGuard)
    app.add_middleware(RequestLog)
    return app


app = create_app()
