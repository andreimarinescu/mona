"""Shared helpers for the S6 OpenRouter spike scripts."""
import json
import pathlib
import time

import httpx

API = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen3.6-35b-a3b"
FALLBACK_MODEL = "qwen/qwen3.5-35b-a3b"
ENV_FILE = pathlib.Path("~/DevFiles/mona-hq/mona/.env").expanduser()
PRIVATE = pathlib.Path("~/DevFiles/mona-hq/demo-data/spikes/s6").expanduser()
RESULTS = pathlib.Path(__file__).resolve().parent / "results"
LEDGER = PRIVATE / "spend.jsonl"
BUDGET_STOP = 2.50

PROVIDER_PIN = {
    "order": ["parasail", "deepinfra", "akashml"],
    "allow_fallbacks": False,
    "require_parameters": True,
    "quantizations": ["fp8", "fp16", "bf16"],
}
NO_THINK = {"enabled": False}


class BudgetExceeded(RuntimeError):
    pass


def api_key() -> str:
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"OPENROUTER_API_KEY missing from {ENV_FILE}")


def headers() -> dict:
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def spent() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(line)["cost"] for line in LEDGER.read_text().splitlines() if line.strip())


def record(test: str, cost: float, **meta) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps({"ts": time.time(), "test": test, "cost": cost or 0.0, **meta}) + "\n")


def guard() -> None:
    if spent() >= BUDGET_STOP:
        raise BudgetExceeded(f"ledger at ${spent():.4f} >= ${BUDGET_STOP}")


def chat(test: str, body: dict, timeout: float = 180) -> tuple[dict, float]:
    """POST a non-streaming chat completion; returns (response json, wall seconds)."""
    guard()
    body = {"model": MODEL, **body}
    t0 = time.monotonic()
    r = httpx.post(f"{API}/chat/completions", headers=headers(), json=body, timeout=timeout)
    wall = time.monotonic() - t0
    try:
        data = r.json()
    except ValueError:
        data = {"error": {"code": r.status_code, "message": r.text[:500]}}
    if r.status_code >= 400 and "error" not in data:
        data["error"] = {"code": r.status_code}
    record(test, (data.get("usage") or {}).get("cost", 0.0), provider=data.get("provider"))
    return data, wall


def stream_chat(test: str, body: dict, timeout: float = 180, deadline: float | None = None) -> dict:
    """Stream a chat completion; returns timings, texts and usage. Stops early at `deadline` seconds."""
    guard()
    body = {"model": MODEL, **body, "stream": True, "usage": {"include": True}}
    out = {"t_first_reasoning": None, "t_first_content": None, "reasoning": "", "content": "",
           "usage": None, "provider": None, "delta_keys": set(), "stopped_early": False}
    t0 = time.monotonic()
    with httpx.stream("POST", f"{API}/chat/completions", headers=headers(), json=body,
                      timeout=timeout) as r:
        for line in r.iter_lines():
            if deadline and time.monotonic() - t0 > deadline:
                out["stopped_early"] = True
                break
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            if "error" in chunk:
                out["error"] = chunk["error"]
                break
            out["provider"] = chunk.get("provider") or out["provider"]
            if chunk.get("usage"):
                out["usage"] = chunk["usage"]
            for ch in chunk.get("choices", []):
                d = ch.get("delta") or {}
                out["delta_keys"] |= {k for k, v in d.items() if v}
                now = time.monotonic() - t0
                if d.get("reasoning"):
                    out["t_first_reasoning"] = out["t_first_reasoning"] or now
                    out["reasoning"] += d["reasoning"]
                if d.get("content"):
                    out["t_first_content"] = out["t_first_content"] or now
                    out["content"] += d["content"]
    out["wall"] = time.monotonic() - t0
    out["delta_keys"] = sorted(out["delta_keys"])
    cost = (out["usage"] or {}).get("cost")
    if cost is None:
        cost = (len(out["reasoning"]) + len(out["content"])) / 3 * 2e-6
    record(test, cost, provider=out["provider"], estimated=out["usage"] is None)
    return out


def usage_summary(data: dict) -> dict:
    u = data.get("usage") or {}
    return {
        "prompt_tokens": u.get("prompt_tokens"),
        "completion_tokens": u.get("completion_tokens"),
        "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "cost": u.get("cost"),
    }


def message(data: dict) -> dict:
    return ((data.get("choices") or [{}])[0]).get("message") or {}


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    if not s:
        return float("nan")
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n")
