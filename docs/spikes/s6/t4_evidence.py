# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx", "jsonschema"]
# ///
"""T4: page-delimited text + extended {value, quote, page} schema; quote verification per field."""
import argparse
import collections
import json
from concurrent.futures import ThreadPoolExecutor

import jsonschema
from _docs import page_texts, sample_docs, v2_definitions
from _evidence import FIELD_GUIDE, FIELDS, QUOTE_RULES, evidence_schema, page_block, verify
from _or import NO_THINK, PRIVATE, PROVIDER_PIN, RESULTS, chat, message, pct, usage_summary, write_json

PAGE_CHARS = 4000
VARIANTS = {
    "p0_markers_layout": {"rules": "p0", "style": "markers", "layout": True},
    "p1_markers_layout": {"rules": "p1", "style": "markers", "layout": True},
    "p1_xml_layout": {"rules": "p1", "style": "xml", "layout": True},
    "p1_markers_raw": {"rules": "p1", "style": "markers", "layout": False},
    "p1_xml_maxlen": {"rules": "p1", "style": "xml", "layout": True, "max_len": 160},
    "p1_xml_maxlen_evfirst": {"rules": "p1", "style": "xml", "layout": True, "max_len": 160,
                              "evidence_first": True},
}


def extract(doc, v2, variant, pages, rep):
    cfg = VARIANTS[variant]
    schema = evidence_schema(v2["CATEGORIES"], cfg.get("max_len"), cfg.get("evidence_first", False))
    system = v2["SYSTEM"] + "\n" + FIELD_GUIDE + QUOTE_RULES[cfg["rules"]]
    user = (f"Filename: {doc['path'].name}\n\nDocument text, {len(pages)} page(s):\n"
            + page_block([p[:PAGE_CHARS] for p in pages], cfg["style"]))
    body = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": 2000, "temperature": 0,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "extraction", "strict": True, "schema": schema}},
        "reasoning": NO_THINK, "provider": PROVIDER_PIN,
    }
    data, wall = chat("t4", body)
    write_json(PRIVATE / "t4" / variant / f"{doc['sha12']}.r{rep}.json", data)
    row = {"variant": variant, "rep": rep, "sha12": doc["sha12"], "label": doc["label"],
           "served_by": data.get("provider"), "wall_s": round(wall, 2), **usage_summary(data)}
    if "error" in data:
        return {**row, "valid": False, "error": f"http {data['error'].get('code')}", "fields": {}}
    try:
        obj = json.loads(message(data).get("content") or "")
        jsonschema.validate(obj, schema)
    except (json.JSONDecodeError, jsonschema.ValidationError) as e:
        return {**row, "valid": False, "error": type(e).__name__, "fields": {}}
    return {**row, "valid": True, "error": None,
            "category_ok": obj["category"]["value"] == doc["gt"],
            "fields": {f: verify(obj.get(f), [p[:PAGE_CHARS] for p in pages])
                       for f in FIELDS}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--reps", type=int, default=2)
    args = ap.parse_args()
    v2, docs = v2_definitions(), sample_docs()
    variants = args.variants.split(",")
    pages = {(d["sha12"], lay): page_texts(d["path"], 3, layout=lay) for d in docs for lay in (True, False)}
    write_json(PRIVATE / "t4" / "pages.json",
               {f"{s}:{'layout' if lay else 'raw'}": p for (s, lay), p in pages.items()})

    def per_variant(v):
        return [extract(d, v2, v, pages[(d["sha12"], VARIANTS[v]["layout"])], rep)
                for rep in range(args.reps) for d in docs]

    with ThreadPoolExecutor(len(variants)) as ex:
        rows = [r for rs in ex.map(per_variant, variants) for r in rs]

    summary = {}
    for v in variants:
        rs = [r for r in rows if r["variant"] == v]
        per_field = {}
        for f in FIELDS:
            c = collections.Counter(r["fields"].get(f) for r in rs if r["valid"])
            present = sum(n for k, n in c.items() if k != "null")
            per_field[f] = {"present": present, "ok": c["ok"],
                            "rate": round(c["ok"] / present, 2) if present else None,
                            "causes": {k: n for k, n in c.items() if k not in ("ok", "null")}}
        allc = collections.Counter(s for r in rs if r["valid"] for s in r["fields"].values())
        present = sum(n for k, n in allc.items() if k != "null")
        walls = [r["wall_s"] for r in rs if r["valid"]]
        summary[v] = {"valid": sum(r["valid"] for r in rs), "n": len(rs),
                      "category_ok": sum(r.get("category_ok", False) for r in rs),
                      "verified": allc["ok"], "present": present,
                      "rate": round(allc["ok"] / present, 3) if present else None,
                      "causes": {k: n for k, n in allc.items() if k not in ("ok", "null")},
                      "p50_s": round(pct(walls, 50), 2), "p95_s": round(pct(walls, 95), 2),
                      "cost_usd": round(sum(r["cost"] or 0 for r in rs), 5), "per_field": per_field}
    write_json(RESULTS / "t4_evidence.json", {"summary": summary, "rows": rows})

    print("| variant | schema-valid | category ok | quotes verified | failure causes | p50 s | p95 s | cost $ |")
    print("|---|---|---|---|---|---|---|---|")
    for v, s in summary.items():
        print(f"| {v} | {s['valid']}/{s['n']} | {s['category_ok']} | {s['verified']}/{s['present']} ({s['rate']}) | "
              f"{s['causes']} | {s['p50_s']} | {s['p95_s']} | {s['cost_usd']} |")
    print("\n| field | " + " | ".join(variants) + " |\n|---|" + "---|" * len(variants))
    for f in FIELDS:
        cells = [f"{summary[v]['per_field'][f]['ok']}/{summary[v]['per_field'][f]['present']}" for v in variants]
        print(f"| {f} | " + " | ".join(cells) + " |")
    for r in rows:
        if not r["valid"]:
            print("  invalid:", r["variant"], r["rep"], r["sha12"], r["served_by"], r["error"])


if __name__ == "__main__":
    main()
