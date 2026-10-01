"""Shared plumbing for the L4 vertical: the services context, job deferral, cards, notes, errors."""

from collections.abc import Iterable, Mapping
from functools import lru_cache
from typing import Any

from fastapi.responses import JSONResponse
from procrastinate import App, SyncPsycopgConnector
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import Connection, func, insert, select, text

from mona.chat.router import ApiFailure, ErrorBody
from mona.db import get_sync_engine
from mona.db.models import Base
from mona.ids import is_id, new_id
from mona.services import Ctx, ServiceError, make_context
from mona.settings import get_settings

T = Base.metadata.tables

# Never opened: every defer passes the caller's connection, so it commits with its transaction.
_deferrer = App(connector=SyncPsycopgConnector())


@lru_cache
def get_ctx() -> Ctx:
    return make_context(get_sync_engine(), get_settings().mona_data_dir)


def defer(
    conn: Connection, task: str, *, queue: str, priority: int, lock: str, **kwargs: Any
) -> bool:
    """Queue `task` in the caller's transaction; False when one with `lock` is already waiting."""
    raw = conn.connection.driver_connection
    try:
        with conn.begin_nested():
            _deferrer.configure_task(
                name=task, queue=queue, priority=priority, queueing_lock=lock, connection=raw
            ).defer(**kwargs)
    except AlreadyEnqueued:
        return False
    return True


def settings_row(conn: Connection) -> dict[str, Any]:
    """The settings row as a dict, whatever columns the current migration has."""
    return conn.execute(text("SELECT to_jsonb(s) FROM settings s")).scalar_one()


def profile_locale(conn: Connection) -> str:
    return conn.execute(select(T["profile"].c.locale)).scalar() or "en"


def attributed_turn(conn: Connection, channel: str) -> Mapping[str, Any] | None:
    """C3 §5.2: the one open, unexpired web turn in the database, else none."""
    if channel != "web":
        return None
    t = T["chat_turns"]
    rows = conn.execute(
        select(t.c.id, t.c.reply_language)
        .where(t.c.status == "open", t.c.lease_expires_at > func.now())
        .limit(2)
    ).all()
    return rows[0]._mapping if len(rows) == 1 else None


def write_cards(
    conn: Connection, channel: str, tool: str, cards: Iterable[tuple[str, dict[str, str]]]
) -> list[str]:
    """C4 §2.5: one `card_events` row per card, in the caller's transaction."""
    cards = list(cards)
    if not cards:
        return []
    turn = attributed_turn(conn, channel)
    refs = sorted(new_id("crd") for _ in cards)
    conn.execute(
        insert(T["card_events"]),
        [
            {
                "id": ref,
                "tool": tool,
                "kind": kind,
                "subject": subject,
                "channel": channel,
                "turn_id": turn["id"] if turn else None,
            }
            for ref, (kind, subject) in zip(refs, cards, strict=True)
        ],
    )
    return refs


def add_note(conn: Connection, conversation_id: str | None, kind: str, note: str) -> str | None:
    """C2 §14: a card-action note in the caller's transaction; unknown conversations are ignored."""
    if not conversation_id or not is_id(conversation_id, "cnv"):
        return None
    c = T["conversations"]
    if conn.execute(select(c.c.id).where(c.c.id == conversation_id)).first() is None:
        return None
    note_id = new_id("not")
    conn.execute(
        insert(T["card_action_notes"]).values(
            id=note_id, conversation_id=conversation_id, kind=kind, text=note[:300]
        )
    )
    return note_id


class RestError(ApiFailure):
    """The C2 §1.2 envelope, with `field` and `details`."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status, code, message)
        self.field, self.details = field, details

    def response(self) -> JSONResponse:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field is not None:
            body["field"] = self.field
        if self.details is not None:
            body["details"] = self.details
        return JSONResponse({"error": body}, status_code=self.status)


def not_found(what: str = "resource") -> RestError:
    return RestError(404, "not_found", f"Unknown {what}.")


def from_service(err: ServiceError) -> RestError:
    """C4 §2.4 codes from the services, as C2 §1.2 statuses."""
    if err.code == "not_found":
        return RestError(404, "not_found", err.message)
    if err.code == "not_allowed":
        return RestError(403, "not_allowed", err.message)
    if err.code == "invalid_argument":
        return RestError(422, "invalid_value", err.message, field=err.field)
    return RestError(409, "conflict", err.message, details={"reason": err.hint or err.code})


def errors(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {s: {"model": ErrorBody} for s in statuses}
