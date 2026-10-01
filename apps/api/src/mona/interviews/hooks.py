"""C6 §3.1: the two hooks L1 calls after its pipeline commits. Cheap, and never raise."""

import logging

from sqlalchemy import Engine

from mona.db import get_sync_engine
from mona.workflow.common import defer

logger = logging.getLogger(__name__)


def _enqueue_check(batch_id: str, engine: Engine | None = None) -> bool:
    """Queue `debrief_check(batch_id)`; False when one is already waiting (AlreadyEnqueued)."""
    try:
        with (engine or get_sync_engine()).begin() as conn:
            return defer(
                conn,
                "debrief_check",
                queue="cpu",
                priority=0,
                lock=f"debrief_check:{batch_id}",
                batch_id=batch_id,
            )
    except Exception as e:
        logger.error("debrief_check for %s not queued: %s", batch_id, type(e).__name__)
        return False


def on_batch_done(batch_id: str) -> None:
    """Once, after the commit that set the batch `done` (C1 §4.1)."""
    _enqueue_check(batch_id)


def on_document_settled(batch_id: str) -> None:
    """After every commit that moved a document of a running batch out of a running stage."""
    _enqueue_check(batch_id)
