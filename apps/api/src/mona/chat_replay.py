"""`mona chat-replay`: recorded chat turns replayed straight at the model endpoint (D23).

It never runs a tool and writes only under `--out`. Summaries hold counts, never message text."""

import asyncio
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import yaml

from mona import llm
from mona.chat.overlay import build_overlay
from mona.i18n import detect_language
from mona.perf import percentile
from mona.settings import Settings

HERMES_PREFIX = "mcp__mona__"
WEB_EXCLUDED = {"ingest_attachment"}
PRIVATE_ROOTS = (Path("/app"), Path("/hermes-seed"), Path("/seed"))
DEFAULT_HERMES_DB = Path("/hermes/state.db")
DEFAULT_CONFIG = Path("/hermes/config.yaml")
SOUL_NAME = "SOUL.md"
REPEAT_MIN_CHARS, REPEAT_TIMES = 40, 5
USAGE_OPTIONS = {"stream_options": {"include_usage": True}}
PROPS_TIMEOUT_S = 5.0


class ReplayError(Exception):
    """A refused or unusable input; the message names files and keys, never text."""


def repo_root() -> Path | None:
    parents = Path(__file__).resolve().parents
    root = parents[4] if len(parents) > 4 else None
    return root if root and (root / "compose.yaml").is_file() else None


def private_out(path: Path) -> Path:
    """`--out` holds practice data: refuse the repo and the ops container's code and seed mounts."""
    resolved = path.expanduser().resolve()
    roots = [*PRIVATE_ROOTS, *([repo_root()] if repo_root() else [])]
    for root in roots:
        if resolved.is_relative_to(root.resolve()):
            raise ReplayError(f"--out {resolved} is inside {root}: choose a private directory")
    return resolved


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


def soul_path(explicit: Path | None = None) -> Path:
    candidates = [explicit] if explicit else []
    seed = os.environ.get("MONA_HERMES_SEED")
    candidates += [Path(seed) / SOUL_NAME] if seed else []
    candidates += [Path("/hermes-seed") / SOUL_NAME]
    if root := repo_root():
        candidates.append(root / "deploy" / "hermes" / SOUL_NAME)
    for p in candidates:
        if p.is_file():
            return p
    raise ReplayError(f"{SOUL_NAME} not found: pass --soul")


async def mona_tools() -> list[dict[str, Any]]:
    """Mona's MCP tools as Hermes' web chat sends them (`ingest_attachment` is Telegram's)."""
    from mona.mcp.server import mcp

    return [
        {
            "type": "function",
            "function": {
                "name": f"{HERMES_PREFIX}{t.name}",
                "description": t.description or "",
                "parameters": t.parameters,
            },
        }
        for t in await mcp.list_tools()
        if t.name not in WEB_EXCLUDED
    ]


def load_cut(path: Path) -> Callable[[str], tuple[str, list[str]]]:
    """`cut_system_prompt` from a file, loaded by path without leaving bytecode beside it."""
    if not path.is_file():
        raise ReplayError(f"--cut {path}: no such file")
    spec = importlib.util.spec_from_file_location("mona_replay_cut", path)
    if spec is None or spec.loader is None:
        raise ReplayError(f"--cut {path}: not a Python file")
    module = importlib.util.module_from_spec(spec)
    keep = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = keep
    fn = getattr(module, "cut_system_prompt", None)
    if not callable(fn):
        raise ReplayError(f"--cut {path}: no cut_system_prompt(text)")
    return fn


# --- build ---


def _hermes_rows(db: Path, session_id: str) -> tuple[str, list[sqlite3.Row]]:
    if not db.is_file():
        raise ReplayError(f"--hermes-db {db}: no such file")
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        head = conn.execute(
            "SELECT s.system_prompt AS legacy, p.prompt AS prompt FROM sessions s "
            "LEFT JOIN system_prompts p ON p.hash = s.system_prompt_hash WHERE s.id = ?",
            (session_id,),
        ).fetchone()
        if head is None:
            raise ReplayError(f"session {session_id}: not in {db}")
        prompt = head["prompt"] or head["legacy"]
        if not prompt:
            raise ReplayError(f"session {session_id}: no stored system prompt")
        rows = conn.execute(
            "SELECT role, content, tool_call_id, tool_calls FROM messages "
            "WHERE session_id = ? AND active = 1 ORDER BY id",
            (session_id,),
        ).fetchall()
    return prompt, rows


def _openai_message(row: sqlite3.Row) -> dict[str, Any] | None:
    role, content = row["role"], row["content"]
    if role == "user":
        return {"role": "user", "content": content or ""}
    if role == "assistant":
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        if row["tool_calls"]:
            msg["tool_calls"] = json.loads(row["tool_calls"])
        return msg
    if role == "tool":
        return {"role": "tool", "tool_call_id": row["tool_call_id"], "content": content or ""}
    return None


def turn_languages(session_id: str) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from mona.db import get_sync_engine
    from mona.db.models import ChatTurn

    engine = get_sync_engine()
    try:
        with engine.connect() as conn:
            query = (
                select(ChatTurn.user_text, ChatTurn.reply_language)
                .where(ChatTurn.conversation_id == session_id)
                .order_by(ChatTurn.opened_at)
            )
            return [(r.user_text, r.reply_language) for r in conn.execute(query)]
    finally:
        engine.dispose()


def build_scenarios(
    db: Path,
    session_id: str,
    turns: Sequence[int],
    tools: list[dict[str, Any]],
    languages: Callable[[str], list[tuple[str, str]]] = turn_languages,
) -> dict[str, dict[str, Any]]:
    """One scenario per selected user message (1-based among the session's user messages)."""
    prompt, rows = _hermes_rows(db, session_id)
    messages = [(r, _openai_message(r)) for r in rows]
    user_at = [i for i, (_, m) in enumerate(messages) if m and m["role"] == "user"]
    recorded = languages(session_id)
    out = {}
    for n in turns:
        if not 1 <= n <= len(user_at):
            raise ReplayError(f"--turn {n}: the session has {len(user_at)} user messages")
        at = user_at[n - 1]
        text = messages[at][1]["content"]
        same = sum(1 for i in user_at[: n - 1] if messages[i][1]["content"] == text)
        found = [lang for t, lang in recorded if t == text]
        language = found[same] if same < len(found) else detect_language(text) or "en"
        out[f"{session_id}-t{n}"] = {
            "v": 1,
            "system": {"prompt": prompt},
            "overlay": {"language": language, "text": build_overlay("/chat", "Chat", language)},
            "history": [m for _, m in messages[:at] if m],
            "user": text,
            "tools": tools,
        }
    return out


# --- run ---


def load_scenarios(directory: Path) -> dict[str, dict[str, Any]]:
    files = sorted(directory.glob("*.json"))
    if not files:
        raise ReplayError(f"--scenarios {directory}: no .json scenarios")
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in files}


def _normal_line(line: str) -> str:
    return " ".join(line.lower().split())


class RepeatWatch:
    """A58 (b): one normalised line of REPEAT_MIN_CHARS or more seen REPEAT_TIMES times."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._partial = ""
        self._seen: Counter[str] = Counter()

    def _count(self, line: str) -> bool:
        line = _normal_line(line)
        if len(line) < REPEAT_MIN_CHARS:
            return False
        self._seen[line] += 1
        return self._seen[line] >= REPEAT_TIMES

    def feed(self, text: str) -> bool:
        *whole, self._partial = (self._partial + text).split("\n")
        return any([self._count(line) for line in whole])

    def finish(self) -> bool:
        line, self._partial = self._partial, ""
        return self._count(line)


def merge_extra(
    config: Path | None, extra: dict[str, Any] | None, *, none: bool
) -> tuple[dict[str, Any], str]:
    """The request's extra body: the config's `custom_providers` entry, then `--extra` on top."""
    if none:
        return {}, "none"
    body: dict[str, Any] = {}
    source = "inline" if extra else "none"
    if config is not None:
        try:
            cfg = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        except OSError as e:
            raise ReplayError(f"--extra-from {config}: {e.strerror}") from None
        body = dict(_provider_extra(cfg))
        source = "config+inline" if extra else "config"
    body.update(extra or {})
    return body, source


def _provider_extra(cfg: dict[str, Any]) -> dict[str, Any]:
    target = str((cfg.get("model") or {}).get("base_url") or "").rstrip("/")
    for entry in cfg.get("custom_providers") or []:
        extra = entry.get("extra_body") if isinstance(entry, dict) else None
        if not isinstance(extra, dict) or not extra:
            continue
        if not target or str(entry.get("base_url") or "").rstrip("/") == target:
            return extra
    return {}


def _new_record() -> dict[str, Any]:
    return {
        "reasoning_chars": 0, "reasoning_tokens": None, "content_chars": 0, "tools": [],
        "acted": False, "first_reasoning_s": None, "first_act_s": None, "reasoning_s": None,
        "total_s": None, "runaway": False, "runaway_reason": None, "budget_hit": False,
        "language": None, "error": None,
    }  # fmt: skip


async def replay_once(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    *,
    max_seconds: float,
    budget_message: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(counts, texts) of one streamed request, closed at `max_seconds`."""
    rec = _new_record()
    reasoning: list[str] = []
    content: list[str] = []
    calls: dict[int, dict[str, str]] = {}
    watch = RepeatWatch()
    t0 = time.monotonic()
    last_reasoning = None
    repeat = timed_out = False

    def now() -> float:
        return round(time.monotonic() - t0, 3)

    def act() -> None:
        rec["acted"] = True
        if rec["first_act_s"] is None:
            rec["first_act_s"] = now()
        watch.reset()

    try:
        async with asyncio.timeout(max_seconds):
            async with client.stream("POST", url, json=body, headers=headers) as res:
                if res.status_code >= 400:
                    rec["error"] = f"http_{res.status_code}"
                    return _finish(rec, t0, None, False, False), {}
                async for line in res.aiter_lines():
                    if not line.startswith("data:") or line.endswith("[DONE]"):
                        continue
                    try:
                        chunk = json.loads(line[5:])
                    except ValueError:
                        continue
                    usage = chunk.get("usage")
                    if isinstance(usage, dict):
                        details = usage.get("completion_tokens_details") or {}
                        rec["reasoning_tokens"] = details.get("reasoning_tokens") or None
                    delta = ((chunk.get("choices") or [{}])[0]).get("delta") or {}
                    text = delta.get("reasoning_content") or delta.get("reasoning")
                    if text:
                        last_reasoning = now()
                        if rec["first_reasoning_s"] is None:
                            rec["first_reasoning_s"] = last_reasoning
                        reasoning.append(text)
                        if watch.feed(text):
                            repeat = True
                            break
                    if (delta.get("content") or "").strip():
                        act()
                    if delta.get("content"):
                        content.append(delta["content"])
                    for call in delta.get("tool_calls") or []:
                        act()
                        slot = calls.setdefault(call.get("index", 0), {"name": "", "arguments": ""})
                        fn = call.get("function") or {}
                        slot["name"] = slot["name"] or fn.get("name") or ""
                        slot["arguments"] += fn.get("arguments") or ""
                if not repeat and watch.finish():
                    repeat = True
    except TimeoutError:
        timed_out = True
    except httpx.HTTPError as e:
        rec["error"] = type(e).__name__
    reasoning_text, content_text = "".join(reasoning), "".join(content)
    rec["reasoning_chars"], rec["content_chars"] = len(reasoning_text), len(content_text)
    rec["tools"] = [c["name"] for _, c in sorted(calls.items()) if c["name"]]
    rec["language"] = detect_language(content_text) if content_text.strip() else None
    if budget_message:
        rec["budget_hit"] = reasoning_text.rstrip().endswith(budget_message.strip())
    texts = {
        "reasoning": reasoning_text,
        "content": content_text,
        "tool_calls": [calls[i] for i in sorted(calls)],
    }
    return _finish(rec, t0, last_reasoning, repeat, timed_out), texts


def _finish(
    rec: dict[str, Any],
    t0: float,
    last_reasoning: float | None,
    repeat: bool,
    timed_out: bool,
) -> dict[str, Any]:
    rec["total_s"] = round(time.monotonic() - t0, 3)
    if last_reasoning is not None and rec["first_reasoning_s"] is not None:
        rec["reasoning_s"] = round(last_reasoning - rec["first_reasoning_s"], 3)
    if repeat:
        rec["runaway"], rec["runaway_reason"] = True, "repeat"
    elif timed_out and not rec["acted"]:
        rec["runaway"], rec["runaway_reason"] = True, "no_act"
    return rec


def system_message(
    scenario: dict[str, Any],
    *,
    system: str | None,
    soul: Path | None,
    cut: Callable[[str], tuple[str, list[str]]] | None,
) -> tuple[str, list[str]]:
    """(the one leading system message, names of the sections the cut removed)."""
    spec = scenario.get("system") or {}
    if system is not None:
        prompt = system
    elif spec.get("soul"):
        prompt = soul_path(soul).read_text(encoding="utf-8")
    else:
        prompt = spec["prompt"]
    removed: list[str] = []
    if cut is not None:
        prompt, removed = cut(prompt)
    overlay = scenario["overlay"]
    text = overlay.get("text") or build_overlay("/chat", "Chat", overlay["language"])
    return (prompt + "\n\n" + text).strip(), list(removed)


def request_body(
    model: str,
    scenario: dict[str, Any],
    system_text: str,
    tools: list[dict[str, Any]],
    extra: dict[str, Any],
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": system_text},
        *scenario.get("history", []),
        {"role": "user", "content": scenario["user"]},
    ]
    body: dict[str, Any] = {"model": model, "stream": True, "messages": messages, **USAGE_OPTIONS}
    if tools:
        body["tools"] = tools
    return {**body, **extra}


def stats(values: list[float | int]) -> dict[str, Any]:
    return {
        "n": len(values),
        "p50": percentile(sorted(values), 0.5),
        "p95": percentile(sorted(values), 0.95),
        "max": max(values) if values else None,
    }


def summarize_scenario(records: list[dict[str, Any]]) -> dict[str, Any]:
    def col(key: str) -> list[float | int]:
        return [r[key] for r in records if r[key] is not None]

    return {
        "n": len(records),
        "acted": sum(r["acted"] for r in records),
        "runaway": sum(r["runaway"] for r in records),
        "runaway_reasons": dict(Counter(r["runaway_reason"] for r in records if r["runaway"])),
        "errors": sum(r["error"] is not None for r in records),
        "budget_hit": sum(r["budget_hit"] for r in records),
        "reasoning_tokens": stats(col("reasoning_tokens")),
        "reasoning_chars": stats(col("reasoning_chars")),
        "reasoning_s": stats(col("reasoning_s")),
        "act_s": stats(col("first_act_s")),
        "tools": dict(Counter(t for r in records for t in r["tools"])),
        "languages": dict(Counter(r["language"] or "none" for r in records)),
    }


async def llama_props(
    client: httpx.AsyncClient, base_url: str, model: str
) -> dict[str, Any] | None:
    root = base_url.rstrip("/").removesuffix("/v1")
    for url in (f"{root}/props", f"{root}/upstream/{model}/props"):
        try:
            res = await client.get(url, timeout=PROPS_TIMEOUT_S)
            body = res.json() if res.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            continue
        if isinstance(body, dict) and body.get("build_info"):
            return {"build_info": body["build_info"]}
    return None


async def run_replay(
    settings: Settings,
    scenarios: dict[str, dict[str, Any]],
    *,
    runs: int,
    extra: dict[str, Any],
    extra_source: str,
    system: str | None = None,
    soul: Path | None = None,
    cut: Callable[[str], tuple[str, list[str]]] | None = None,
    max_seconds: float = 150.0,
    transport: httpx.AsyncBaseTransport | None = None,
    on_run: Callable[[str, int, dict[str, Any]], None] | None = None,
    keep_text: Callable[[str, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    endpoint = llm.endpoint(settings)
    key = settings.openrouter_api_key
    headers = (
        {"Authorization": f"Bearer {key.get_secret_value()}"} if key and not endpoint.local else {}
    )
    url = f"{endpoint.base_url.rstrip('/')}/chat/completions"
    registry = await mona_tools()
    budget_message = extra.get("reasoning_budget_message")
    per: dict[str, list[dict[str, Any]]] = {}
    removed: Counter[str] = Counter()
    extra_kwargs = {"transport": transport} if transport else {}
    async with llm.guarded_http_client(settings, timeout=None, **extra_kwargs) as client:
        props = (
            await llama_props(client, endpoint.base_url, settings.mona_llm_model)
            if endpoint.local
            else None
        )
        for name, scenario in scenarios.items():
            text, cut_names = system_message(scenario, system=system, soul=soul, cut=cut)
            removed.update(cut_names)
            body = request_body(
                settings.mona_llm_model,
                scenario,
                text,
                scenario["tools"] if "tools" in scenario else registry,
                extra,
            )
            records = per.setdefault(name, [])
            for i in range(runs):
                rec, texts = await replay_once(
                    client, url, headers, body, max_seconds=max_seconds,
                    budget_message=budget_message,
                )  # fmt: skip
                records.append(rec)
                if on_run:
                    on_run(name, i, rec)
                if keep_text:
                    keep_text(name, i, texts)
    return {
        "v": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": settings.mona_llm_model,
        "endpoint": "local" if endpoint.local else "openrouter",
        "endpoint_host": urlsplit(endpoint.base_url).netloc,
        "llama_server": props,
        "settings": {
            "runs": runs,
            "max_seconds": max_seconds,
            "extra_body": extra,
            "extra_source": extra_source,
            "cut": cut is not None,
            "cut_removed": dict(removed),
            "system_override": system is not None,
        },
        "scenarios": {name: summarize_scenario(r) for name, r in per.items()},
        "runs": per,
    }


# --- report ---


def _triple(s: dict[str, Any]) -> str:
    if not s["n"]:
        return "-"
    return f"{s['p50']} / {s['p95']} / {s['max']}"


def markdown(summary: dict[str, Any]) -> str:
    cfg = summary["settings"]
    server = (summary.get("llama_server") or {}).get("build_info")
    extra_body = json.dumps(cfg["extra_body"], ensure_ascii=False)
    lines = [
        f"# mona chat-replay, {summary['generated_at']}",
        "",
        f"Model `{summary['model']}` on {summary['endpoint']} ({summary['endpoint_host']})"
        + (f", llama-server `{server}`." if server else "."),
        f"{cfg['runs']} runs per scenario, cut at {cfg['max_seconds']} s. "
        f"Extra body ({cfg['extra_source']}): `{extra_body}`. "
        f"Prompt cut: {'yes' if cfg['cut'] else 'no'}"
        + (f" ({json.dumps(cfg['cut_removed'])})" if cfg["cut_removed"] else "")
        + f"; stored prompt replaced: {'yes' if cfg['system_override'] else 'no'}.",
        "",
        "| Scenario | n | Acted | Runaway | Errors | Budget msg | Reasoning tokens p50/p95/max "
        "| Reasoning chars p50/p95/max | Reasoning s p50/p95/max | Act s p50/p95/max "
        "| Tools | Languages |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in summary["scenarios"].items():
        tools = ", ".join(f"{k} x{v}" for k, v in sorted(s["tools"].items())) or "-"
        langs = ", ".join(f"{k} x{v}" for k, v in sorted(s["languages"].items()))
        lines.append(
            f"| {name} | {s['n']} | {s['acted']} | {s['runaway']} | {s['errors']} "
            f"| {s['budget_hit']} | {_triple(s['reasoning_tokens'])} "
            f"| {_triple(s['reasoning_chars'])} | {_triple(s['reasoning_s'])} "
            f"| {_triple(s['act_s'])} | {tools} | {langs} |"
        )
    return "\n".join(lines) + "\n"


_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def safe_name(name: str) -> str:
    return _SAFE.sub("_", name)
