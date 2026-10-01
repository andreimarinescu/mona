"""C2 §15 settings and system status."""

import os
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter
from sqlalchemy import select, text, update

from mona import __version__, clock
from mona.api.deps import Engine, run
from mona.api.errors import ApiFailure, errors
from mona.api.home import hermes_health, queue_counts
from mona.api.models import SettingsPatch, SettingsView, SystemStatus
from mona.db import get_sync_engine
from mona.db.models import PracticeSettings, Profile
from mona.privacy import model_endpoint
from mona.settings import get_settings

router = APIRouter(prefix="/api", tags=["settings"])

PROFILE_FIELDS = {
    "profile_name": "name",
    "locale": "locale",
    "auto_lock_minutes": "auto_lock_minutes",
}
RANGES = {
    "auto_lock_minutes": (1, 1440),
    "badge_hours": (1, 168),
    "debrief_queue_threshold": (1, 50),
    "debrief_early_min": (1, 50),
}
NAMES = ("profile_name", "practice_name")
PROBE_TIMEOUT_S = 2.0
STATUS_CACHE_S = 30.0
QUANT = re.compile(r"(?i)[-_.]((?:I?Q\d+(?:_[A-Z0-9]+)*)|BF16|F16|F32)\.gguf$")

_status: dict[str, Any] = {"at": float("-inf"), "body": None}


def _view(conn: Any) -> dict[str, Any]:
    p = conn.execute(select(Profile.__table__)).one()
    s = conn.execute(select(PracticeSettings.__table__)).one()
    return {
        "profile_name": p.name, "locale": p.locale, "auto_lock_minutes": p.auto_lock_minutes,
        "practice_name": s.practice_name, "filing_language": s.filing_language,
        "confidence_high": s.confidence_high, "confidence_low": s.confidence_low,
        "badge_hours": s.badge_hours, "debrief_queue_threshold": s.debrief_queue_threshold,
        "debrief_early_min": s.debrief_early_min,
    }  # fmt: skip


def _read() -> dict[str, Any]:
    with get_sync_engine().connect() as conn:
        return _view(conn)


@router.get(
    "/settings", operation_id="getSettings", response_model=SettingsView,
    responses=errors(401, 423),
)  # fmt: skip
async def get_settings_view() -> dict[str, Any]:
    return await run(_read)


def invalid(field: str, message: str) -> ApiFailure:
    from mona.naming import to_camel

    return ApiFailure(422, "invalid_value", message, field=to_camel(field))


def validate(current: dict[str, Any], given: dict[str, Any]) -> None:
    """§15.1: 422 `invalid_value` naming the field; the merged view must hold."""
    for name, value in given.items():
        if value is None:
            raise invalid(name, "This value can't be empty.")
    for name in NAMES:
        if name in given and not 1 <= len(given[name].strip()) <= 120:
            raise invalid(name, "Use 1 to 120 characters.")
    for name, (lo, hi) in RANGES.items():
        if name in given and not lo <= given[name] <= hi:
            raise invalid(name, f"Use a whole number from {lo} to {hi}.")
    merged = {**current, **given}
    low, high = merged["confidence_low"], merged["confidence_high"]
    if not 0 < low < high <= 100:
        field = "confidence_low" if "confidence_low" in given else "confidence_high"
        raise invalid(field, "Keep 0 < low < high <= 100.")


def _patch(body: SettingsPatch) -> dict[str, Any]:
    given = {k: getattr(body, k) for k in body.model_fields_set}
    now = clock.now()
    with get_sync_engine().begin() as conn:
        current = _view(conn)
        validate(current, given)
        for name in NAMES:
            if name in given:
                given[name] = given[name].strip()
        profile = {PROFILE_FIELDS[k]: v for k, v in given.items() if k in PROFILE_FIELDS}
        practice = {k: v for k, v in given.items() if k not in PROFILE_FIELDS}
        if profile:
            conn.execute(update(Profile).values(**profile, updated_at=now))
        if practice:
            conn.execute(update(PracticeSettings).values(**practice, updated_at=now))
        return _view(conn)


@router.patch(
    "/settings", operation_id="patchSettings", response_model=SettingsView,
    responses=errors(400, 401, 403, 415, 422, 423),
)  # fmt: skip
async def patch_settings(body: SettingsPatch) -> dict[str, Any]:
    return await run(_patch, body)


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    try:
        res = await client.get(url)
        return res.json() if res.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def quantization(model_path: str | None) -> str | None:
    m = QUANT.search(model_path or "")
    return m.group(1).upper() if m else None


async def llm_status() -> dict[str, Any]:
    """§15.2: prod probes llama-swap through the checked base URL; dev reads configuration."""
    s = get_settings()
    endpoint = model_endpoint(s)
    out: dict[str, Any] = {
        "endpoint": "local" if endpoint.local else "openrouter",
        "model": None if s.mona_env == "prod" else s.mona_llm_model,
        "quantization": None, "context_per_slot": None, "slots": None, "vram_bytes": None,
    }  # fmt: skip
    if s.mona_env != "prod":
        return out
    base = endpoint.base_url.rstrip("/")
    root = base.removesuffix("/v1")
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
        models = await _get_json(client, f"{base}/models")
        ids = [m.get("id") for m in (models or {}).get("data", []) if isinstance(m, dict)]
        model = s.mona_llm_model if s.mona_llm_model in ids else (ids[0] if ids else None)
        out["model"] = model
        if model:
            props = await _get_json(client, f"{root}/upstream/{model}/props") or {}
            gen = props.get("default_generation_settings") or {}
            out["quantization"] = quantization(props.get("model_path"))
            out["context_per_slot"] = gen.get("n_ctx") or props.get("n_ctx")
            out["slots"] = props.get("total_slots")
    return out


def _db_and_queues() -> tuple[str, dict[str, Any]]:
    empty = {q: {"todo": 0, "doing": 0} for q in ("llm", "cpu")}
    try:
        with get_sync_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            return "ok", queue_counts(conn)
    except Exception:  # noqa: BLE001
        return "error", empty


def disk() -> dict[str, int]:
    st = os.statvfs(get_settings().mona_data_dir)
    return {
        "data_free_bytes": st.f_bavail * st.f_frsize,
        "data_total_bytes": st.f_blocks * st.f_frsize,
    }


@router.get(
    "/system/status", operation_id="getSystemStatus", response_model=SystemStatus,
    responses=errors(401, 423),
)  # fmt: skip
async def system_status(engine: Engine) -> dict[str, Any]:
    now = time.monotonic()
    if _status["body"] is not None and now - _status["at"] < STATUS_CACHE_S:
        return _status["body"]
    s = get_settings()
    health = await hermes_health()
    database, queues = await run(_db_and_queues)
    body = {
        "version": __version__,
        "build": s.mona_build,
        "env": s.mona_env,
        "mona": {
            "status": "online" if health is not None else "offline",
            "hermes_version": (health or {}).get("version"),
        },
        "llm": await llm_status(),
        "queues": queues,
        "database": database,
        "disk": disk(),
        "privacy": {"cloud_ai": s.mona_env == "dev", "telegram": bool(s.telegram_bot_token)},
    }
    _status.update(at=now, body=body)
    return body
