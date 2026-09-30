"""C4 §2 conventions: errors, channel, size caps, cursors, card events, visibility."""

import asyncio
import base64
import binascii
import functools
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, insert, select, true
from sqlalchemy.ext.asyncio import AsyncConnection

from mona.db.models import (
    Account,
    CardEvent,
    ChatTurn,
    Entity,
    EntityPerson,
    Person,
    SubUnit,
)
from mona.ids import new_id

logger = logging.getLogger(__name__)

Channel = Literal["web", "telegram"]

MAX_RESULT_CHARS = 4000
TOOL_BUDGET_S = 10.0
DEFAULT_LIMIT, MAX_LIMIT = 10, 25


class ToolFailure(Exception):
    """A C4 §2.4 error; its envelope is the text of the MCP error result."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        field: str | None = None,
        valid: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message = code, message
        self.extra = {"hint": hint, "field": field, "valid": valid}

    def envelope(self) -> str:
        body = {"code": self.code, "message": self.message}
        body.update({k: v for k, v in self.extra.items() if v is not None})
        return json.dumps({"error": body}, ensure_ascii=False)


def not_found(what: str) -> ToolFailure:
    return ToolFailure("not_found", f"No {what} with that id.")


INTERNAL = ToolFailure("internal", "Something went wrong on Mona's side; try again later.")


class ArgumentErrors(Middleware):
    """Schema validation failures become `invalid_argument` envelopes (C4 §4.1)."""

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ValidationError as e:
            cause = e.__cause__
            errors = cause.errors() if isinstance(cause, PydanticValidationError) else []
            field = str(errors[0]["loc"][-1]) if errors and errors[0]["loc"] else None
            msg = errors[0]["msg"] if errors else "Invalid arguments."
            raise ToolError(
                ToolFailure(
                    "invalid_argument", f"Invalid {field or 'argument'}: {msg}.", field=field
                ).envelope()
            ) from None


mcp = FastMCP("mona", middleware=[ArgumentErrors()], mask_error_details=True)


def channel() -> Channel:
    """C4 §1.2: from `X-Mona-Channel`; missing or unknown is the stricter `telegram`."""
    return "web" if get_http_headers().get("x-mona-channel") == "web" else "telegram"


def tool(description: str) -> Callable[[Callable[..., Awaitable[dict]]], Any]:
    """Register a Mona tool: envelope errors, the 10 s budget (§2.8), internal masking."""

    def register(fn: Callable[..., Awaitable[dict]]) -> Any:
        @functools.wraps(fn)
        async def run(*args: Any, **kwargs: Any) -> dict:
            try:
                async with asyncio.timeout(TOOL_BUDGET_S):
                    return await fn(*args, **kwargs)
            except ToolFailure as e:
                raise ToolError(e.envelope()) from None
            except TimeoutError:
                logger.error("tool %s exceeded its %ss budget", fn.__name__, TOOL_BUDGET_S)
                raise ToolError(INTERNAL.envelope()) from None
            except Exception:
                logger.exception("tool %s failed", fn.__name__)
                raise ToolError(INTERNAL.envelope()) from None

        return mcp.tool(run, description=description)

    return register


def size(result: dict) -> int:
    return len(json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str))


def fit(result: dict, key: str) -> dict:
    """§2.3: drop list items from the end until the result fits; flag it."""
    items = result[key]
    while size(result) > MAX_RESULT_CHARS and items:
        items.pop()
        result["truncated"] = True
    return result


def clip(value: str | None, limit: int = 160) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


# --- cursors (§2.3) ---


def _params_hash(params: dict[str, Any]) -> str:
    raw = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def encode_cursor(offset: int, params: dict[str, Any]) -> str:
    raw = json.dumps({"o": offset, "h": _params_hash(params)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None, params: dict[str, Any]) -> int:
    if cursor is None:
        return 0
    bad = ToolFailure(
        "invalid_argument",
        "This cursor belongs to a different query.",
        hint="Repeat the call with the same parameters, or drop the cursor.",
        field="cursor",
    )
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        offset, digest = int(data["o"]), data["h"]
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise bad from None
    if digest != _params_hash(params) or offset < 0:
        raise bad
    return offset


def page_of(total: int, offset: int, limit: int, params: dict[str, Any]) -> str | None:
    return encode_cursor(offset + limit, params) if offset + limit < total else None


# --- scope: channel + visibility (§2.6) ---


@dataclass
class Scope:
    conn: AsyncConnection
    channel: Channel
    hidden_entities: frozenset[str]

    def entity_visible(self, entity_id: str | None) -> bool:
        return entity_id is None or entity_id not in self.hidden_entities

    def visible_entity_clause(self, column: Any) -> Any:
        """SQL: rows whose entity column is null or visible on this channel."""
        if not self.hidden_entities:
            return true()
        return column.is_(None) | column.not_in(self.hidden_entities)


async def scope_for(conn: AsyncConnection, ch: Channel) -> Scope:
    hidden: frozenset[str] = frozenset()
    if ch != "web":
        hidden = frozenset(
            (await conn.execute(select(Entity.id).where(Entity.visibility == "personal")))
            .scalars()
            .all()
        )
    return Scope(conn, ch, hidden)


@dataclass
class RuleVisibility:
    """§2.6 rules: hidden when the action or any condition points at a personal entity."""

    personal_keys: frozenset[str]
    personal_accounts: frozenset[str]
    personal_people: frozenset[str]

    def visible(self, conditions: list[dict[str, Any]], action: dict[str, Any]) -> bool:
        if action.get("entity") in self.personal_keys:
            return False
        for c in conditions:
            field, op, value = c.get("field"), c.get("op"), c.get("value")
            values = value if isinstance(value, list) else [value]
            if field == "entity" and any(v in self.personal_keys for v in values):
                return False
            if (field, op) in {("addressee", "is_entity"), ("iban", "entity"), ("siren", "entity")}:
                if value in self.personal_keys:
                    return False
            if (field, op) == ("iban", "account") and value in self.personal_accounts:
                return False
            if (field, op) in {("addressee", "is_person"), ("person", "mentions")}:
                if value in self.personal_people:
                    return False
        return True


async def rule_visibility(scope: Scope) -> RuleVisibility | None:
    """None on `web`, where every rule is visible."""
    if not scope.hidden_entities:
        return None
    conn, hidden = scope.conn, scope.hidden_entities
    keys = (await conn.execute(select(Entity.key).where(Entity.id.in_(hidden)))).scalars()
    accounts = (
        await conn.execute(select(Account.key).where(Account.entity_id.in_(hidden)))
    ).scalars()
    linked = select(EntityPerson.person_id).where(EntityPerson.entity_id.in_(hidden))
    units = select(SubUnit.person_id).where(
        SubUnit.entity_id.in_(hidden), SubUnit.person_id.is_not(None)
    )
    people = (
        await conn.execute(select(Person.key).where(Person.id.in_(linked.union(units))))
    ).scalars()
    return RuleVisibility(frozenset(keys), frozenset(accounts), frozenset(people))


# --- card events (§2.5, C3 §5.2) ---


async def attributed_turn(conn: AsyncConnection, ch: Channel) -> str | None:
    """The one open, unexpired web turn in the database, else none."""
    if ch != "web":
        return None
    rows = (
        await conn.execute(
            select(ChatTurn.id)
            .where(ChatTurn.status == "open", ChatTurn.lease_expires_at > func.now())
            .limit(2)
        )
    ).all()
    return rows[0].id if len(rows) == 1 else None


async def write_cards(
    scope: Scope, tool_name: str, cards: Iterable[tuple[str, dict[str, str]]]
) -> list[str]:
    cards = list(cards)
    if not cards:
        return []
    turn_id = await attributed_turn(scope.conn, scope.channel)
    refs = sorted(new_id("crd") for _ in cards)
    await scope.conn.execute(
        insert(CardEvent),
        [
            {
                "id": ref,
                "tool": tool_name,
                "kind": kind,
                "subject": subject,
                "channel": scope.channel,
                "turn_id": turn_id,
            }
            for ref, (kind, subject) in zip(refs, cards, strict=True)
        ],
    )
    return refs


PLACEHOLDER_REF = "crd_" + "0" * 26
