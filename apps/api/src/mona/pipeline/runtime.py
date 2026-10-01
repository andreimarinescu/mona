"""The process-wide pipeline context for the api and the workers (settings-driven)."""

import logging
from datetime import timedelta
from functools import lru_cache

from mona.db import get_sync_engine
from mona.pipeline import stages
from mona.pipeline.hooks import interview_hooks
from mona.pipeline.model import LlmClient, ModelClient
from mona.services.context import Ctx, make_context
from mona.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_context() -> Ctx:
    """`make_context` once per process: resolves the roots, refuses split filesystems, and
    wires the C6 hooks."""
    return make_context(get_sync_engine(), get_settings().mona_data_dir, **interview_hooks())


@lru_cache
def get_model() -> ModelClient:
    return LlmClient.from_settings(get_settings())


def startup() -> dict[int, str]:
    """At api and worker startup: the context, then C7 §4.3 recovery of every pending entry."""
    out = stages.recover(get_context(), older_than=timedelta(0))
    if out:
        logger.info("recovered %d pending file operations", len(out))
    return out


def run_job(job: str, document_id: str, attempts: int) -> str:
    return stages.run(get_context(), job, document_id, attempts=attempts, model=get_model)
