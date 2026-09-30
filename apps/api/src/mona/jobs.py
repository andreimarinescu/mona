import logging

from procrastinate import App, PsycopgConnector

from mona.settings import get_settings

logger = logging.getLogger(__name__)

app = App(connector=PsycopgConnector(conninfo=get_settings().libpq_url))


@app.task(name="ping_llm", queue="llm")
async def ping_llm() -> str:
    logger.info("pong from queue llm")
    return "pong"


@app.task(name="ping_cpu", queue="cpu")
async def ping_cpu() -> str:
    logger.info("pong from queue cpu")
    return "pong"
