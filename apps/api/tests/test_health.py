import httpx
from sqlalchemy.ext.asyncio import create_async_engine

from mona import __version__
from mona.app import create_app
from mona.db import get_engine


async def get(app, path: str) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path)


async def test_health_reports_db_ok_and_package_version():
    res = await get(create_app(), "/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok", "version": __version__}


async def test_health_reports_db_error_when_unreachable():
    app = create_app()
    dead = create_async_engine(
        "postgresql+psycopg://nobody:x@127.0.0.1:9/none", connect_args={"connect_timeout": 1}
    )
    app.dependency_overrides[get_engine] = lambda: dead
    res = await get(app, "/api/health")
    assert res.status_code == 503
    assert res.json()["db"] == "error"
