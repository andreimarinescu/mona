"""`ingest_attachment` (C4 §3.14): a Telegram attachment from Hermes' media cache into intake."""

import logging
import os
from typing import Annotated

import anyio.to_thread
from pydantic import Field
from sqlalchemy import select

from mona.api.intake import MAX_FILE_BYTES, get_intake_ctx
from mona.attachments import HERMES_PREFIX, Refused, open_attachment, read_all
from mona.db import get_engine
from mona.db.models import Document
from mona.mcp.core import ToolFailure, channel, scope_for, tool, write_cards
from mona.mcp.write import call_service
from mona.pipeline.intake import Upload, ingest_files
from mona.settings import get_settings

logger = logging.getLogger(__name__)


def _read(path: str) -> tuple[str, bytes]:
    root = os.path.realpath(get_settings().mona_attach_root)
    try:
        att = open_attachment(root, path)
    except Refused as e:
        raise ToolFailure(e.code, str(e), field="path") from None
    logger.info("ingest_attachment: %s", att.rel)
    if att.size > MAX_FILE_BYTES:
        os.close(att.fd)
        data = None
    else:
        data = read_all(att.fd, MAX_FILE_BYTES)
    if data is None:
        raise ToolFailure("invalid_argument", "The file is over 25 MB.", field="path")
    return att.rel, data


def original_name(rel: str) -> str:
    """Hermes saves `doc_<12 hex>_<original name>`; images keep their generated name."""
    name = rel.rsplit("/", 1)[-1]
    m = HERMES_PREFIX.match(name)
    if m is None or not name.startswith("doc_"):
        return name
    return name[m.end() :] or name


@tool(
    "Add a file the person sent you on Telegram to Mona's intake, using the exact path the "
    "attachment was saved to. Set for_visitor when the person says the document belongs to a "
    "visitor at an event; it is kept apart and removed after 24 hours. Tell the person it is "
    "being read; it shows up in Intake."
)
async def ingest_attachment(
    path: Annotated[str, Field(min_length=1, max_length=1024)],
    for_visitor: bool = False,
) -> dict:
    rel, data = await anyio.to_thread.run_sync(_read, path)
    intake = await call_service(
        ingest_files, get_intake_ctx(), [Upload(data, original_name(rel))],
        source="telegram", visitor=for_visitor,
    )  # fmt: skip
    item = intake.items[0]
    async with get_engine().begin() as conn:
        s = await scope_for(conn, channel())
        document_id = item.document_id
        card = item.outcome == "accepted"
        if item.outcome == "duplicate":
            seen = (
                await conn.execute(
                    select(Document.id).where(Document.id == document_id, *s.document_clauses())
                )
            ).first()
            card = seen is not None
            if not card and s.channel != "web":
                document_id = None
        cards = [("doc", {"document_id": item.document_id})] if card else []
        refs = await write_cards(s, "ingest_attachment", cards)
    return {
        "batch_id": intake.batch_id,
        "outcome": item.outcome,
        "document_id": document_id,
        "deleted": item.deleted,
        "reject_reason": item.reject_reason,
        "card_refs": refs,
    }
