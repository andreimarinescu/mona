"""`mona perf`: the Oct 8 budgets measured on the stack's own model endpoint, as a report file.

Practice text goes only where the pipeline and Hermes already send it: the configured model
endpoint through `mona.llm`'s guard, and Hermes on the compose network. Documents appear in the
report as `sha256[:12]` only."""

import asyncio
import hashlib
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from mona import llm
from mona.chat.hermes import HermesClient, HermesError
from mona.settings import Settings

BUDGETS = {
    "classify_median_s": 8.0,
    "first_token_s": 10.0,
    "vram_free_mib": 1024,
}
DEFAULT_BEATS = [
    {"id": "sum", "prompt": "How much did we pay Example Insurance last year?"},
    {"id": "due", "prompt": "What is due this month?"},
    {"id": "find", "prompt": "Find the latest letter from the tax office."},
    {"id": "draft", "prompt": "Rédigez une réponse au SIE pour demander un échéancier."},
]  # fmt: skip
BEAT_TIMEOUT_S = 120.0
WATCH_EVERY_S = 0.5


@dataclass(frozen=True)
class Beat:
    id: str
    prompt: str


def load_beats(path: Path | None) -> list[Beat]:
    raw = json.loads(path.read_text()) if path else DEFAULT_BEATS
    return [Beat(str(b["id"]), str(b["prompt"])) for b in raw]


def sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def batch_files(directory: Path, order: Path | None = None) -> list[Path]:
    if order:
        names = [n.strip() for n in order.read_text().splitlines() if n.strip()]
        return [directory / n for n in names]
    return sorted(p for p in directory.iterdir() if p.is_file())


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def classification_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-document classification time from the batch report; cache hits are counted apart."""
    timed = [r for r in rows if r.get("stages", {}).get("classify_document") is not None]
    live = [r["stages"]["classify_document"] for r in timed if not r.get("from_cache")]
    documents = [
        {
            "sha12": r["sha12"], "outcome": r["outcome"],
            "classify_s": r["stages"].get("classify_document"), "model_ms": r.get("model_ms"),
            "from_cache": bool(r.get("from_cache")),
        }
        for r in rows
        if "stages" in r
    ]  # fmt: skip
    return {
        "documents": documents,
        "model_calls": len(live),
        "cache_hits": len(timed) - len(live),
        "median_s": round(statistics.median(live), 2) if live else None,
        "p95_s": percentile(live, 0.95),
        "max_s": max(live) if live else None,
    }


def vram_stats(csv_text: str) -> dict[str, Any]:
    """`nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits` samples."""
    used, total = [], None
    for line in csv_text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        try:
            used.append(float(parts[-2]))
            total = float(parts[-1])
        except (IndexError, ValueError):
            continue
    if not used or total is None:
        return {"samples": 0}
    return {
        "samples": len(used), "total_mib": total, "peak_used_mib": max(used),
        "min_free_mib": total - max(used),
    }  # fmt: skip


async def stream_beat(hermes: HermesClient, session_id: str, prompt: str) -> dict[str, Any]:
    """One chat turn through Hermes' completions stream: seconds to the first reasoning delta and
    the first text delta."""
    start = time.monotonic()
    out: dict[str, Any] = {"first_reasoning_s": None, "first_text_s": None, "total_s": None}
    try:
        await hermes.ensure_session(session_id)
        async with asyncio.timeout(BEAT_TIMEOUT_S):
            async with hermes.stream_completion(
                session_id, [{"role": "user", "content": prompt}]
            ) as lines:
                async for line in lines:
                    if not line.startswith("data:") or line.endswith("[DONE]"):
                        continue
                    try:
                        delta = json.loads(line[5:])["choices"][0]["delta"]
                    except (ValueError, KeyError, IndexError):
                        continue
                    now = round(time.monotonic() - start, 2)
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    if reasoning and out["first_reasoning_s"] is None:
                        out["first_reasoning_s"] = now
                    if delta.get("content") and out["first_text_s"] is None:
                        out["first_text_s"] = now
    except HermesError as e:
        out["error"] = e.code
    except TimeoutError:
        out["error"] = "timeout"
    out["total_s"] = round(time.monotonic() - start, 2)
    firsts = [v for v in (out["first_reasoning_s"], out["first_text_s"]) if v is not None]
    out["first_token_s"] = min(firsts) if firsts else None
    return out


def llama_root(settings: Settings) -> str | None:
    endpoint = llm.endpoint(settings)
    return endpoint.base_url.rstrip("/").removesuffix("/v1") if endpoint.local else None


async def running_models(client: httpx.AsyncClient, root: str) -> dict[str, str] | None:
    try:
        res = await client.get(f"{root}/running")
        body = res.json() if res.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None
    items = body.get("running") if isinstance(body, dict) else body
    return {m.get("model"): m.get("state") for m in items or [] if isinstance(m, dict)}


class SwapWatch:
    """Polls llama-swap `/running` and records any change of the loaded set or a non-ready state."""

    def __init__(self, client: httpx.AsyncClient, root: str) -> None:
        self.client, self.root = client, root
        self.events: list[str] = []
        self.samples = 0
        self._task: asyncio.Task | None = None
        self._last: dict[str, str] | None = None

    async def _loop(self) -> None:
        while True:
            now = await running_models(self.client, self.root)
            if now is not None:
                self.samples += 1
                if self._last is not None and now != self._last:
                    self.events.append(f"{sorted(self._last.items())} -> {sorted(now.items())}")
                self._last = now
            await asyncio.sleep(WATCH_EVERY_S)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> dict[str, Any]:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        return {
            "samples": self.samples,
            "events": self.events,
            "reload_detected": bool(self.events),
        }


def skeleton(
    settings: Settings, beats: list[Beat], files: list[Path], *, dry_run: bool
) -> dict[str, Any]:
    endpoint = llm.endpoint(settings)
    return {
        "v": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "env": settings.mona_env,
        "endpoint": "local" if endpoint.local else "openrouter",
        "endpoint_host": urlsplit(endpoint.base_url).netloc,
        "model": settings.mona_llm_model,
        "budgets": BUDGETS,
        "plan": {
            "batch": [sha12(f) for f in files],
            "beats": [b.id for b in beats],
            "phases": ["cold beats", "warm beats", "batch with beats during it"],
        },
        "classification": None,
        "chat": {"cold": None, "warm": None, "during_batch": None},
        "swaps": None,
        "vram": None,
        "verdicts": None,
    }


def _verdict(ok: bool | None) -> str:
    return "pass" if ok else "fail" if ok is not None else "not measured"


def verdicts(report: dict[str, Any]) -> dict[str, str]:
    median = (report.get("classification") or {}).get("median_s")
    during = (report.get("chat") or {}).get("during_batch") or []
    firsts = [b.get("first_token_s") for b in during]
    chat_ok = None
    if during and None not in firsts:
        chat_ok = max(firsts) <= BUDGETS["first_token_s"] and not any(
            b.get("error") for b in during
        )
    swaps = report.get("swaps")
    free = (report.get("vram") or {}).get("min_free_mib")
    return {
        "classification": _verdict(
            None if median is None else median <= BUDGETS["classify_median_s"]
        ),
        "chat_during_batch": _verdict(chat_ok),
        "no_reload": _verdict(None if swaps is None else not swaps["reload_detected"]),
        "vram_headroom": _verdict(None if free is None else free >= BUDGETS["vram_free_mib"]),
    }


def _results(report: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    cls = report.get("classification")
    during = (report.get("chat") or {}).get("during_batch") or []
    swaps = report.get("swaps")
    vram = report.get("vram") or {}
    v = report.get("verdicts") or {}
    classification = "-"
    if cls and cls["median_s"] is not None:
        classification = (
            f"{cls['median_s']} s (p95 {cls['p95_s']}, max {cls['max_s']}, "
            f"{cls['cache_hits']} cache hits)"
        )
    swap_text = f"{len(swaps['events'])} changes in {swaps['samples']} samples" if swaps else "-"
    vram_text = "-"
    if "min_free_mib" in vram:
        vram_text = f"{vram['min_free_mib']:.0f} MiB free of {vram['total_mib']:.0f}"
    return [
        ("Classification, median per document", f"<= {BUDGETS['classify_median_s']} s",
         classification, v.get("classification", "")),
        ("Chat during a running batch, time to first token", f"<= {BUDGETS['first_token_s']} s",
         ", ".join(f"{b['id']} {b.get('first_token_s')} s" for b in during) or "-",
         v.get("chat_during_batch", "")),
        ("llama-swap reloads", "none", swap_text, v.get("no_reload", "")),
        ("VRAM headroom at peak", f">= {BUDGETS['vram_free_mib']} MiB", vram_text,
         v.get("vram_headroom", "")),
    ]  # fmt: skip


def markdown(report: dict[str, Any]) -> str:
    note = " (dry run: nothing measured)" if report["dry_run"] else ""
    lines = [
        f"# mona perf, {report['generated_at']}{note}",
        "",
        f"Environment `{report['env']}`, endpoint {report['endpoint']} "
        f"({report['endpoint_host']}), model `{report['model']}`.",
        "",
        "| Measure | Budget | Result | Verdict |",
        "|---|---|---|---|",
    ]
    lines += [f"| {m} | {b} | {r} | {x or 'not measured'} |" for m, b, r, x in _results(report)]
    for phase in ("cold", "warm", "during_batch"):
        beats = (report.get("chat") or {}).get(phase) or [
            {"id": i} for i in report["plan"]["beats"]
        ]
        lines += [
            "", f"## Chat beats, {phase.replace('_', ' ')}", "",
            "| Beat | First reasoning | First text | Total |", "|---|---|---|---|",
        ]  # fmt: skip
        for b in beats:
            cells = [b.get(k, "-") for k in ("first_reasoning_s", "first_text_s", "total_s")]
            lines.append(f"| {b['id']} | " + " | ".join(str(c) for c in cells) + " |")
    batch = report["plan"]["batch"]
    lines += ["", f"Batch: {len(batch)} documents (sha256[:12]): " + ", ".join(batch)]
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base = out_dir / f"perf-{stamp}{'-dry' if report['dry_run'] else ''}"
    base.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    base.with_suffix(".md").write_text(markdown(report))
    return base.with_suffix(".md")


async def wait_until(done: Callable[[], bool], timeout_s: float, every_s: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while not done():
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(every_s)
    return True


async def run_beats(hermes: HermesClient, beats: list[Beat], tag: str) -> list[dict[str, Any]]:
    out = []
    for i, beat in enumerate(beats):
        out.append({"id": beat.id, **await stream_beat(hermes, f"perf-{tag}-{i}", beat.prompt)})
    return out


async def measure(
    settings: Settings,
    beats: list[Beat],
    start_batch: Callable[[], str],
    batch_done: Callable[[str], bool],
    batch_rows: Callable[[str], list[dict[str, Any]]],
    *,
    hermes: HermesClient,
    cold: bool,
    delay_s: float,
    batch_timeout_s: float,
    report: dict[str, Any],
    probe: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """The three phases; `start_batch` ingests the live batch and returns its id."""
    tag = datetime.now(UTC).strftime("%H%M%S")
    root = llama_root(settings)
    client = probe or llm.guarded_http_client(settings, timeout=5.0)
    async with client:
        if cold and root:
            try:
                await client.get(f"{root}/unload")
            except httpx.HTTPError:
                report["cold_note"] = "unload failed: the cold pass ran on whatever was loaded"
        report["chat"]["cold"] = await run_beats(hermes, beats, f"{tag}c")
        report["chat"]["warm"] = await run_beats(hermes, beats, f"{tag}w")
        watch = SwapWatch(client, root) if root else None
        if watch:
            watch.start()
        batch_id = start_batch()
        await asyncio.sleep(delay_s)
        during = []
        for i, beat in enumerate(beats):
            row = {"id": beat.id, "batch_running": not batch_done(batch_id)}
            during.append({**row, **await stream_beat(hermes, f"perf-{tag}-d{i}", beat.prompt)})
        report["chat"]["during_batch"] = during
        await wait_until(lambda: batch_done(batch_id), batch_timeout_s)
        report["swaps"] = await watch.stop() if watch else None
    report["classification"] = classification_stats(batch_rows(batch_id))
    report["classification"]["batch_finished"] = batch_done(batch_id)
    return report
