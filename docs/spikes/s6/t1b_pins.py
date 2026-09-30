# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""T1b: do the provider pins hold? Routing trail per request, plus negative controls."""
import collections
import time

import httpx
from _or import API, NO_THINK, PROVIDER_PIN, RESULTS, chat, headers, write_json

SCHEMA = {"type": "object", "properties": {"answer": {"type": "integer"}},
          "required": ["answer"], "additionalProperties": False}
UNIFIED_PIN = {**PROVIDER_PIN, "order": ["coreweave", "siliconflow", "akashml", "parasail", "deepinfra"]}
JSON_SCHEMA = {"type": "json_schema", "json_schema": {"name": "a", "strict": True, "schema": SCHEMA}}


def body(provider: dict, **extra) -> dict:
    return {"messages": [{"role": "user", "content": "What is 6*7? JSON only."}], "max_tokens": 50,
            "temperature": 0, "reasoning": NO_THINK, "response_format": JSON_SCHEMA,
            "provider": provider, **extra}


def trail(gen_id: str) -> list[dict]:
    for _ in range(10):
        r = httpx.get(f"{API}/generation", params={"id": gen_id}, headers=headers(), timeout=30)
        if r.status_code == 200:
            return [{"provider": p["provider_name"], "status": p.get("status")}
                    for p in r.json()["data"].get("provider_responses") or []]
        time.sleep(2)
    return []


def main():
    allowed = {"Parasail", "DeepInfra", "AkashML"}
    runs = []
    for _ in range(12):
        data, wall = chat("t1b", body(PROVIDER_PIN))
        runs.append({"served_by": data.get("provider"), "error": (data.get("error") or {}).get("code"),
                     "id": data.get("id"), "wall_s": round(wall, 2)})
    for r in runs:
        r["trail"] = trail(r.pop("id")) if r["served_by"] else []
    tried = collections.Counter(t["provider"] for r in runs for t in r["trail"])
    served = collections.Counter(r["served_by"] for r in runs)

    negatives = {}
    cases = {
        "only venice (no response_format) + require_parameters": {"only": ["venice"], "require_parameters": True, "allow_fallbacks": False},
        "only atlas-cloud (no structured_outputs) + json_schema + require_parameters": {"only": ["atlas-cloud"], "require_parameters": True, "allow_fallbacks": False},
        "only reka (quantization unknown) + quantizations fp8+": {"only": ["reka"], "quantizations": ["fp8", "fp16", "bf16"], "allow_fallbacks": False},
        "only darkbloom (fp4) + quantizations fp8+": {"only": ["darkbloom"], "quantizations": ["fp8", "fp16", "bf16"], "allow_fallbacks": False},
    }
    for name, prov in cases.items():
        data, _ = chat("t1b", body(prov))
        negatives[name] = {"served_by": data.get("provider"),
                           "error": (data.get("error") or {}).get("code"),
                           "message": ((data.get("error") or {}).get("message") or "")[:160]}

    tool = {"type": "function", "function": {"name": "get_document", "description": "Fetch a document",
                                             "parameters": {"type": "object", "properties": {"id": {"type": "string"}},
                                                            "required": ["id"]}}}
    tools_runs = []
    for _ in range(3):
        data, _ = chat("t1b", {"messages": [{"role": "user", "content": "Open document 42."}], "max_tokens": 200,
                               "reasoning": NO_THINK, "tools": [tool], "provider": UNIFIED_PIN})
        tools_runs.append({"served_by": data.get("provider"), "id": data.get("id"),
                           "tool_call": bool((data.get("choices") or [{}])[0].get("message", {}).get("tool_calls"))})
    for r in tools_runs:
        r["trail"] = trail(r.pop("id")) if r["served_by"] else []

    ok = set(served) - {None} <= allowed and set(tried) <= allowed
    write_json(RESULTS / "t1b_pins.json", {"pin": PROVIDER_PIN, "runs": runs, "tried": tried,
                                           "served": served, "pins_hold": ok, "negatives": negatives,
                                           "unified_pin": UNIFIED_PIN, "tools_runs": tools_runs})
    print(f"pin runs: served={dict(served)} tried={dict(tried)} pins_hold={ok}")
    for r in runs:
        print("  ", r["served_by"], r["error"], r["wall_s"], [f"{t['provider']}:{t['status']}" for t in r["trail"]])
    print("| negative control | served by | error |\n|---|---|---|")
    for name, n in negatives.items():
        print(f"| {name} | {n['served_by']} | {n['error']} {n['message']} |")
    print("tools request on the unified pin (non-tool providers first in order):")
    for r in tools_runs:
        print("  ", r["served_by"], "tool_call" if r["tool_call"] else "no tool call",
              [f"{t['provider']}:{t['status']}" for t in r["trail"]])


if __name__ == "__main__":
    main()
