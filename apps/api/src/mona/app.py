from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mona import __version__
from mona.chat.router import router as chat_router
from mona.db import get_engine
from mona.spike.mcp import build_mcp_app


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


def create_app() -> FastAPI:
    mcp_app = build_mcp_app()
    app = FastAPI(title="Mona", version=__version__, lifespan=mcp_app.lifespan)
    app.include_router(router)
    app.include_router(chat_router)
    app.add_route("/mcp", mcp_app)
    return app


app = create_app()
