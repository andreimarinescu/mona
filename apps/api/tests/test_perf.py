"""`mona perf` (L6): the dry-run skeleton, the stream timing, the swap watch and the verdicts."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from mona import llm
from mona import perf as p
from mona.chat.hermes import HermesClient
from mona.cli import app
from mona.settings import Settings

LOCAL = "http://llama-swap:8080/v1"
MODEL = "qwen-test"


def settings(**kw) -> Settings:
    base = {
        "database_url": "postgresql+psycopg://x:y@h/d",
        "mona_env": "dev",
        "mona_llm_model": MODEL,
    }
    return Settings(**{**base, **kw})


def sse(*deltas: dict) -> bytes:
    body = "".join(f"data: {json.dumps({'choices': [{'delta': d}]})}\n\n" for d in deltas)
    return (body + "data: [DONE]\n\n").encode()


def hermes(handler) -> HermesClient:
    return HermesClient("http://hermes:8642", "k", transport=httpx.MockTransport(handler))


def sessions_ok(request: httpx.Request) -> httpx.Response | None:
    if request.url.path == "/api/sessions":
        return httpx.Response(201, json={})
    return None


# --- dry run ---


def test_dry_run_writes_a_skeleton_and_touches_nothing_else(tmp_path, monkeypatch):
    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "private-name-one.pdf").write_bytes(b"one")
    (batch / "private-name-two.pdf").write_bytes(b"two")

    def no_network(*a, **k):
        raise AssertionError("dry run opened a connection")

    monkeypatch.setattr(httpx.Client, "send", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    out = tmp_path / "out"
    res = CliRunner().invoke(app, ["perf", "--dry-run", "--batch", str(batch), "--out", str(out)])
    assert res.exit_code == 0, res.output
    (md,) = out.glob("perf-*-dry.md")
    report = json.loads(md.with_suffix(".json").read_text())
    assert report["dry_run"] is True and report["classification"] is None
    assert report["verdicts"] is None and report["budgets"]["first_token_s"] == 10.0
    assert len(report["plan"]["batch"]) == 2 and all(len(s) == 12 for s in report["plan"]["batch"])
    text = md.read_text() + md.with_suffix(".json").read_text()
    assert "private-name" not in text and "dry run: nothing measured" in text
    assert report["plan"]["beats"] == ["sum", "due", "find", "draft"]


def test_a_real_run_needs_the_batch_folder(tmp_path):
    res = CliRunner().invoke(app, ["perf", "--out", str(tmp_path)])
    assert res.exit_code == 2 and "--batch" in res.output


def test_batch_order_file_sets_the_drop_order(tmp_path):
    for n in ("b.pdf", "a.pdf", "c.pdf"):
        (tmp_path / n).write_bytes(n.encode())
    order = tmp_path / "order.txt"
    order.write_text("c.pdf\n\na.pdf\n")
    assert [f.name for f in p.batch_files(tmp_path, order)] == ["c.pdf", "a.pdf"]
    assert [f.name for f in p.batch_files(tmp_path)] == ["a.pdf", "b.pdf", "c.pdf", "order.txt"]


# --- measurements ---


async def test_stream_beat_times_the_first_reasoning_and_first_text_deltas():
    def handler(request: httpx.Request) -> httpx.Response:
        if (r := sessions_ok(request)) is not None:
            return r
        return httpx.Response(
            200, content=sse({"role": "assistant"}, {"reasoning_content": "hm"}, {"content": "42"})
        )

    out = await p.stream_beat(hermes(handler), "perf-1", "How much?")
    assert out["first_reasoning_s"] is not None and out["first_text_s"] is not None
    assert out["first_reasoning_s"] <= out["first_text_s"] <= out["total_s"]
    assert out["first_token_s"] == out["first_reasoning_s"] and "error" not in out


async def test_stream_beat_reports_a_hermes_failure_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return sessions_ok(request) or httpx.Response(500)

    out = await p.stream_beat(hermes(handler), "perf-1", "x")
    assert out["error"] == "hermes_http_500" and out["first_token_s"] is None


def test_classification_stats_split_model_calls_from_cache_hits():
    rows = [
        {"sha12": "a" * 12, "outcome": "accepted", "stages": {"classify_document": s},
         "model_ms": int(s * 1000), "from_cache": False}
        for s in (4.0, 6.0, 8.0, 20.0)
    ] + [
        {"sha12": "b" * 12, "outcome": "accepted", "stages": {"classify_document": 0.1},
         "from_cache": True},
        {"sha12": "c" * 12, "outcome": "duplicate"},
    ]  # fmt: skip
    stats = p.classification_stats(rows)
    assert (stats["model_calls"], stats["cache_hits"]) == (4, 1)
    assert stats["median_s"] == 7.0 and stats["max_s"] == 20.0 and stats["p95_s"] == 20.0
    assert len(stats["documents"]) == 5


def test_vram_stats_from_nvidia_smi_samples():
    csv = "9000, 16311\n12500, 16311\ngarbage\n11000, 16311\n"
    assert p.vram_stats(csv) == {
        "samples": 3, "total_mib": 16311.0, "peak_used_mib": 12500.0, "min_free_mib": 3811.0,
    }  # fmt: skip
    assert p.vram_stats("") == {"samples": 0}


@pytest.mark.parametrize(
    ("median", "firsts", "swaps", "free", "expected"),
    [
        (7.9, [3.0, 9.9], False, 2000, ["pass"] * 4),
        (8.1, [3.0, 10.1], True, 500, ["fail"] * 4),
        (None, [], None, None, ["not measured"] * 4),
    ],
)
def test_verdicts_against_the_budgets(median, firsts, swaps, free, expected):
    report = {
        "classification": {"median_s": median} if median is not None else None,
        "chat": {
            "during_batch": [{"id": str(i), "first_token_s": s} for i, s in enumerate(firsts)]
        },
        "swaps": None if swaps is None else {"reload_detected": swaps},
        "vram": {} if free is None else {"min_free_mib": free},
    }
    assert list(p.verdicts(report).values()) == expected


async def test_a_chat_turn_that_failed_during_the_batch_fails_the_verdict():
    report = {"chat": {"during_batch": [{"id": "a", "first_token_s": 1.0, "error": "timeout"}]}}
    assert p.verdicts(report)["chat_during_batch"] == "fail"


class FakeSwap:
    def __init__(self, states: list[dict | None]) -> None:
        self.states = iter(states)

    async def get(self, url: str) -> httpx.Response:
        state = next(self.states, None)
        if state is None:
            raise httpx.ConnectError("down")
        return httpx.Response(
            200, json={"running": [{"model": m, "state": s} for m, s in state.items()]}
        )


async def test_the_swap_watch_flags_a_state_change_and_ignores_a_steady_model(monkeypatch):
    monkeypatch.setattr(p, "WATCH_EVERY_S", 0.001)
    ready, starting = {MODEL: "ready"}, {MODEL: "starting"}
    steady = p.SwapWatch(FakeSwap([ready] * 50), "http://x")
    steady.start()
    await asyncio.sleep(0.05)
    assert (await steady.stop())["reload_detected"] is False
    swapped = p.SwapWatch(FakeSwap([ready, ready, starting, ready] + [ready] * 50), "http://x")
    swapped.start()
    await asyncio.sleep(0.05)
    out = await swapped.stop()
    assert out["reload_detected"] is True and len(out["events"]) == 2


async def test_measure_runs_cold_warm_and_during_batch_and_unloads_only_when_cold(monkeypatch):
    calls: list[str] = []

    def api(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/running":
            return httpx.Response(200, json={"running": [{"model": MODEL, "state": "ready"}]})
        return httpx.Response(200, json={})

    def hermes_handler(request: httpx.Request) -> httpx.Response:
        return sessions_ok(request) or httpx.Response(200, content=sse({"content": "ok"}))

    finished = iter([False, False, False, False, False, True, True, True, True, True, True])
    s = settings(mona_llm_base_url=LOCAL)
    report = p.skeleton(s, p.load_beats(None)[:2], [], dry_run=False)
    monkeypatch.setattr(p, "WATCH_EVERY_S", 0.01)
    out = await p.measure(
        s, p.load_beats(None)[:2], lambda: "bat_1", lambda _b: next(finished, True),
        lambda _b: [{"sha12": "a" * 12, "outcome": "ok", "stages": {"classify_document": 5.0}}],
        hermes=hermes(hermes_handler), cold=True, delay_s=0, batch_timeout_s=5, report=report,
        probe=httpx.AsyncClient(transport=httpx.MockTransport(api)),
    )  # fmt: skip
    assert "/unload" in calls
    assert [b["id"] for b in out["chat"]["during_batch"]] == ["sum", "due"]
    assert out["chat"]["during_batch"][0]["batch_running"] is True
    assert out["classification"]["median_s"] == 5.0 and out["swaps"]["reload_detected"] is False
    assert all(b["first_text_s"] is not None for b in out["chat"]["cold"] + out["chat"]["warm"])
    assert "| sum |" in p.markdown({**out, "verdicts": p.verdicts(out)})


async def test_measure_probes_llama_swap_only_through_the_guarded_client(monkeypatch):
    used = []
    real = llm.guarded_http_client

    def spy(s, **kw):
        used.append(s.mona_env)
        return real(s, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), **kw)

    monkeypatch.setattr(llm, "guarded_http_client", spy)
    s = settings(mona_env="prod", mona_llm_base_url=LOCAL)
    report = p.skeleton(s, [], [], dry_run=False)
    await p.measure(
        s, [], lambda: "b", lambda _b: True, lambda _b: [],
        hermes=hermes(lambda r: httpx.Response(200)), cold=False, delay_s=0, batch_timeout_s=1,
        report=report,
    )  # fmt: skip
    assert used == ["prod"]


def test_the_report_file_pair_is_named_by_time_and_flags_a_dry_run(tmp_path):
    report = p.skeleton(settings(), p.load_beats(None), [], dry_run=True)
    path = p.write_report(report, tmp_path)
    assert (
        path.suffix == ".md" and path.with_suffix(".json").exists() and path.stem.endswith("-dry")
    )
    assert isinstance(path, Path)
