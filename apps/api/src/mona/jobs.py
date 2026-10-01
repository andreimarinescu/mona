import logging

from procrastinate import App, BaseRetryStrategy, JobContext, PsycopgConnector, RetryDecision
from procrastinate.jobs import Job

from mona.settings import get_settings

logger = logging.getLogger(__name__)

app = App(
    connector=PsycopgConnector(conninfo=get_settings().libpq_url),
    import_paths=["mona.interviews.jobs", "mona.workflow.jobs"],
)


@app.task(name="ping_llm", queue="llm")
async def ping_llm() -> str:
    logger.info("pong from queue llm")
    return "pong"


@app.task(name="ping_cpu", queue="cpu")
async def ping_cpu() -> str:
    logger.info("pong from queue cpu")
    return "pong"


class PipelineRetry(BaseRetryStrategy):
    """C5 §1.2 retries; the job body takes the failure path when this returns None."""

    def __init__(self, job: str):
        self.job = job

    def get_retry_decision(self, *, exception: BaseException, job: Job) -> RetryDecision | None:
        from mona.pipeline.stages import RETRY

        r = RETRY[self.job]
        if not r.will_retry(exception, job.attempts):
            return None
        return RetryDecision(retry_in={"seconds": r.waits[job.attempts]})


def _run(job: str, context: JobContext, document_id: str) -> str:
    from mona.pipeline.runtime import run_job

    assert context.job is not None
    return run_job(job, document_id, context.job.attempts)


@app.task(name="extract_text", queue="cpu", pass_context=True, retry=PipelineRetry("extract_text"))
def extract_text(context: JobContext, document_id: str) -> str:
    return _run("extract_text", context, document_id)


@app.task(
    name="render_thumbnail", queue="cpu", pass_context=True,
    retry=PipelineRetry("render_thumbnail"),
)  # fmt: skip
def render_thumbnail(context: JobContext, document_id: str) -> str:
    return _run("render_thumbnail", context, document_id)


@app.task(
    name="classify_document", queue="llm", pass_context=True,
    retry=PipelineRetry("classify_document"),
)  # fmt: skip
def classify_document(context: JobContext, document_id: str) -> str:
    return _run("classify_document", context, document_id)


@app.task(name="file_document", queue="cpu", pass_context=True)
def file_document(context: JobContext, document_id: str) -> str:
    return _run("file_document", context, document_id)


@app.periodic(cron="* * * * *")
@app.task(name="recover_pending", queue="cpu", queueing_lock="recover_pending")
def recover_pending(timestamp: int) -> int:
    """C7 §4.3 every 60 s, for entries pending more than 30 s."""
    from mona.pipeline.runtime import get_context
    from mona.pipeline.stages import recover

    return len(recover(get_context()))


@app.periodic(cron="*/15 * * * *")
@app.task(name="purge_visitors", queue="cpu", queueing_lock="purge_visitors")
def purge_visitors(timestamp: int) -> int:
    """C9 §5.2: the Visitors purge every 15 minutes."""
    from mona.fileops.purge import purge_visitors as purge
    from mona.pipeline.runtime import get_context

    return len(purge(get_context().ops).purged)


@app.periodic(cron="23 4 * * *")
@app.task(name="purge_auth_sessions", queue="cpu")
async def purge_auth_sessions(timestamp: int) -> int:
    """C2 §2.2: expired and revoked sessions older than 7 days."""
    from mona.api.session import delete_stale
    from mona.db import get_engine

    async with get_engine().begin() as conn:
        n = await delete_stale(conn)
    logger.info("deleted %d stale sessions", n)
    return n
