# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""T1: model metadata and per-provider endpoints for the Qwen 35B-A3B models."""
import httpx
from _or import API, FALLBACK_MODEL, MODEL, RESULTS, write_json

NEEDED = {"response_format", "structured_outputs", "reasoning", "tools"}
FP8_OR_BETTER = {"fp8", "fp16", "bf16"}


def main():
    models = {m["id"]: m for m in httpx.get(f"{API}/models", timeout=60).json()["data"]}
    out = {}
    for mid in (MODEL, FALLBACK_MODEL):
        m = models[mid]
        eps = httpx.get(f"{API}/models/{mid}/endpoints", timeout=60).json()["data"]["endpoints"]
        rows = []
        for e in eps:
            sp = set(e.get("supported_parameters") or [])
            rows.append({
                "provider": e["provider_name"], "tag": e.get("tag"),
                "quantization": e.get("quantization"),
                "context_length": e.get("context_length"),
                "max_completion_tokens": e.get("max_completion_tokens"),
                "prompt_per_mtok": round(float(e["pricing"]["prompt"]) * 1e6, 4),
                "completion_per_mtok": round(float(e["pricing"]["completion"]) * 1e6, 4),
                "response_format": "response_format" in sp,
                "structured_outputs": "structured_outputs" in sp,
                "reasoning": "reasoning" in sp,
                "tools": "tools" in sp,
                "uptime_last_1d": e.get("uptime_last_1d"),
                "pin_candidate": NEEDED <= sp and e.get("quantization") in FP8_OR_BETTER,
            })
        out[mid] = {
            "context_length": m["context_length"],
            "pricing_per_mtok": {k: round(float(v) * 1e6, 4) for k, v in m["pricing"].items()},
            "reasoning": m.get("reasoning"),
            "default_parameters": m.get("default_parameters"),
            "supported_parameters": m["supported_parameters"],
            "endpoints": rows,
        }
        print(f"\n{mid}  ctx={m['context_length']}  reasoning={m.get('reasoning')}")
        print("| provider | quant | ctx | max out | $/M in | $/M out | rf | so | reasoning | tools | pin |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            yn = lambda b: "y" if b else "-"
            print(f"| {r['tag'] or r['provider']} | {r['quantization']} | {r['context_length']} | "
                  f"{r['max_completion_tokens']} | {r['prompt_per_mtok']} | {r['completion_per_mtok']} | "
                  f"{yn(r['response_format'])} | {yn(r['structured_outputs'])} | {yn(r['reasoning'])} | "
                  f"{yn(r['tools'])} | {yn(r['pin_candidate'])} |")
    write_json(RESULTS / "t1_models.json", out)


if __name__ == "__main__":
    main()
