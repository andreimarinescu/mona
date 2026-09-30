from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from mona.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
