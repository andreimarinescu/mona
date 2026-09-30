"""C5 §1.2 jobs: deferred inside the caller's transaction, one queued job per document and stage."""

from dataclasses import dataclass

from procrastinate import App, SyncPsycopgConnector
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import Connection


@dataclass(frozen=True)
class Job:
    name: str
    queue: str
    priority: int


JOBS = {
    j.name: j
    for j in (
        Job("extract_text", "cpu", 0),
        Job("render_thumbnail", "cpu", -10),
        Job("classify_document", "llm", 0),
        Job("file_document", "cpu", 0),
    )
}

# Never opened: every defer passes the caller's connection, so it commits with its transaction.
_deferrer = App(connector=SyncPsycopgConnector())


def queueing_lock(job: str, document_id: str) -> str:
    return f"{job}:{document_id}"


def defer(conn: Connection, job: str, document_id: str) -> bool:
    """Queue `job` for the document; False when that stage is already waiting (queueing lock)."""
    j = JOBS[job]
    raw = conn.connection.driver_connection
    try:
        with conn.begin_nested():
            _deferrer.configure_task(
                name=j.name, queue=j.queue, priority=j.priority,
                queueing_lock=queueing_lock(job, document_id), connection=raw,
            ).defer(document_id=document_id)  # fmt: skip
    except AlreadyEnqueued:
        return False
    return True
