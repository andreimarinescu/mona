"""C2 §2.2–§2.5: session tokens, CSRF tokens, the lock state and the unlock throttle."""

import asyncio
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from mona import clock
from mona.db.models import AuthSession, Profile
from mona.ids import new_id

COOKIE = "mona_session"
SESSION_DAYS = 30
CSRF_MESSAGE = b"mona-csrf-v1"
THROTTLE_FAILURES = 5
THROTTLE_SECONDS = 60
STALE_DAYS = 7


def new_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    mac = hmac.new(token.encode(), CSRF_MESSAGE, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def csrf_ok(token: str, given: str | None) -> bool:
    return given is not None and hmac.compare_digest(csrf_token(token), given)


@dataclass
class Session:
    id: str
    token: str
    last_active_at: datetime
    locked: bool

    @property
    def csrf(self) -> str:
        return csrf_token(self.token)


def is_locked(locked_at: datetime | None, last_active_at: datetime, minutes: int) -> bool:
    """§2.3: someone pressed Lock, or the session is idle past the auto-lock."""
    return locked_at is not None or last_active_at + timedelta(minutes=minutes) <= clock.now()


async def live_session(conn: AsyncConnection, token: str | None) -> Session | None:
    if not token:
        return None
    now = clock.now()
    row = (
        await conn.execute(
            select(
                AuthSession.id,
                AuthSession.last_active_at,
                Profile.locked_at,
                Profile.auto_lock_minutes,
            )
            .join(Profile, Profile.singleton.is_(True))
            .where(
                AuthSession.token_hash == token_hash(token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
    ).first()
    if row is None:
        return None
    locked = is_locked(row.locked_at, row.last_active_at, row.auto_lock_minutes)
    return Session(row.id, token, row.last_active_at, locked)


async def touch(conn: AsyncConnection, session_id: str) -> None:
    """§2.3 activity: a successful write or a heartbeat."""
    now = clock.now()
    await conn.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(last_active_at=now, updated_at=now)
    )


async def create_session(conn: AsyncConnection, user_agent: str | None) -> tuple[str, str]:
    """A new live session; returns (id, cookie token). Only the token's sha256 is stored."""
    token, sid, now = new_token(), new_id("ses"), clock.now()
    await conn.execute(
        insert(AuthSession).values(
            id=sid,
            token_hash=token_hash(token),
            created_at=now,
            expires_at=now + timedelta(days=SESSION_DAYS),
            last_active_at=now,
            updated_at=now,
            user_agent=user_agent[:300] if user_agent else None,
        )
    )
    return sid, token


async def revoke(conn: AsyncConnection, *, only: str | None = None, but: str | None = None) -> None:
    now = clock.now()
    stmt = update(AuthSession).where(AuthSession.revoked_at.is_(None))
    if only is not None:
        stmt = stmt.where(AuthSession.id == only)
    if but is not None:
        stmt = stmt.where(AuthSession.id != but)
    await conn.execute(stmt.values(revoked_at=now, updated_at=now))


async def delete_stale(conn: AsyncConnection) -> int:
    """§2.2 housekeeping: expired or revoked rows older than 7 days."""
    cutoff = clock.now() - timedelta(days=STALE_DAYS)
    res = await conn.execute(
        delete(AuthSession).where(
            or_(AuthSession.expires_at < cutoff, AuthSession.revoked_at < cutoff)
        )
    )
    return res.rowcount or 0


class TooManyAttempts(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("too many attempts")
        self.retry_after = retry_after


class UnlockThrottle:
    """§2.5: 5 consecutive failures block every unlock for 60 s. One verify at a time; an
    attempt is counted before its verify starts."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.failures = 0
        self.blocked_until: datetime | None = None

    def reset(self) -> None:
        self.failures, self.blocked_until = 0, None

    async def attempt(self, verify) -> bool:  # type: ignore[no-untyped-def]
        async with self.lock:
            now = clock.now()
            if self.blocked_until is not None:
                if now < self.blocked_until:
                    raise TooManyAttempts(THROTTLE_SECONDS)
                self.reset()
            self.failures += 1
            ok = await verify()
            if ok:
                self.reset()
            elif self.failures >= THROTTLE_FAILURES:
                self.blocked_until = clock.now() + timedelta(seconds=THROTTLE_SECONDS)
            return ok


throttle = UnlockThrottle()
