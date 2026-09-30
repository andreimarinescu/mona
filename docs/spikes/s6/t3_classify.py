# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx", "jsonschema"]
# ///
"""T3: v2 classification prompt, strict json_schema, thinking off, on 10 practice docs."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor

import jsonschema
from _docs import cache_text, sample_docs, v2_definitions
from _or import NO_THINK, PRIVATE, PROVIDER_PIN, RESULTS, chat, message, pct, usage_summary, write_json


def classify(doc: dict, v2: dict, provider: dict) -> tuple[dict, dict]:
    user = f"Filename: {doc['path'].name}\n\nDocument text (first pages):\n{cache_text(doc['path'])[:3000]}"
    body = {
        "messages": [{"role": "system", "content": v2["SYSTEM"]}, {"role": "user", "content": user}],
        "max_tokens": 600, "temperature": 0,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "classification", "strict": True, "schema": v2["SCHEMA"]}},
        "reasoning": NO_THINK, "provider": provider,
    }
    data, wall = chat("t3", body)
    content = message(data).get("content") or ""
    valid, err, obj = False, None, None
    if "error" in data:
        e = data["error"]
        err = f"http {e.get('code')} {(e.get('metadata') or {}).get('provider_error_code', '')}".strip()
    else:
        try:
            obj = json.loads(content)
            jsonschema.validate(obj, v2["SCHEMA"])
            valid = True
        except (json.JSONDecodeError, jsonschema.ValidationError) as e:
            err = type(e).__name__
    row = {"sha12": doc["sha12"], "label": doc["label"], "served_by": data.get("provider"),
           "valid": valid, "error": err, "answered": "error" not in data,
           "category_ok": bool(obj and obj.get("category") == doc["gt"]),
           "wall_s": round(wall, 2), **usage_summary(data)}
    return row, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="pin,parasail,deepinfra,akashml")
    args = ap.parse_args()
    v2, docs = v2_definitions(), sample_docs()

    def per_provider(p):
        pin = PROVIDER_PIN if p == "pin" else {"only": [p], "allow_fallbacks": False,
                                                "require_parameters": True}
        rows = []
        for d in docs:
            row, raw = classify(d, v2, pin)
            write_json(PRIVATE / "t3" / p / f"{d['sha12']}.json", raw)
            rows.append({"route": p, **row})
        return rows

    routes = args.providers.split(",")
    with ThreadPoolExecutor(len(routes)) as ex:
        rows = [r for rs in ex.map(per_provider, routes) for r in rs]
    summary = []
    for p in routes:
        rs = [r for r in rows if r["route"] == p]
        walls = [r["wall_s"] for r in rs if r["answered"]]
        served = sorted({r["served_by"] for r in rs if r["served_by"]})
        summary.append({"route": p, "n": len(rs), "answered": sum(r["answered"] for r in rs),
                        "schema_valid": sum(r["valid"] for r in rs), "served_by": served,
                        "category_ok": sum(r["category_ok"] for r in rs),
                        "p50_s": round(pct(walls, 50), 2), "p95_s": round(pct(walls, 95), 2),
                        "cost_usd": round(sum(r["cost"] or 0 for r in rs), 5),
                        "reasoning_tokens": sum(r["reasoning_tokens"] or 0 for r in rs)})
    write_json(RESULTS / "t3_classify.json", {"summary": summary, "rows": rows})
    print("| route | served by | n | answered | schema-valid | category = ground truth | p50 s | p95 s | cost $ | reasoning tok |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in summary:
        print(f"| {s['route']} | {', '.join(s['served_by'])} | {s['n']} | {s['answered']} | {s['schema_valid']} | {s['category_ok']} | {s['p50_s']} | "
              f"{s['p95_s']} | {s['cost_usd']} | {s['reasoning_tokens']} |")
    for r in rows:
        if not r["valid"] or not r["category_ok"]:
            print("  miss:", r["route"], r["sha12"], r["label"], r["error"] or "category")


if __name__ == "__main__":
    main()
