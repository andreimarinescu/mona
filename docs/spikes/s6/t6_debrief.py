# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx", "jsonschema"]
# ///
"""T6: two-pass debrief on a synthetic cluster (pass 1 thinking, pass 2 no-think json_schema)."""
import argparse
import json
import pathlib
import time

import jsonschema
from _evidence import norm
from _or import NO_THINK, PROVIDER_PIN, RESULTS, chat, message, stream_chat, usage_summary, write_json

HERE = pathlib.Path(__file__).resolve().parent
LOCALES = {"en": "English", "fr": "French", "ro": "Romanian"}
ROUTE = {"provider": PROVIDER_PIN, "branches": False}


def question_schema(cluster: dict, branches: bool = False) -> dict:
    doc_ids = [d["doc_id"] for d in cluster["documents"]]
    entities = [e["id"] for e in cluster["registry"]["entities"]]
    categories = cluster["registry"]["categories"]
    s = lambda **kw: {"type": "string", **kw}
    nullable = lambda schema: {"anyOf": [schema, {"type": "null"}]}
    obj = lambda props: {"type": "object", "properties": props, "required": list(props),
                         "additionalProperties": False}
    condition = obj({
        "field": s(enum=["counterparty", "doc_type", "addressee", "insured_person", "iban",
                         "site_address", "keyword", "subscriber"]),
        "op": s(enum=["equals", "contains", "matches"]),
        "value": s(maxLength=120),
    })
    action = obj({"entity": nullable(s(enum=entities)),
                  "category": nullable(s(enum=categories)),
                  "subcategory": nullable(s(maxLength=60))})
    conditions = {"type": "array", "items": condition, "maxItems": 4}
    if branches:
        rule_draft = obj({
            "kind": s(enum=["always", "depends", "ask"]),
            "discriminator": nullable(s(maxLength=80)),
            "branches": {"type": "array", "minItems": 0, "maxItems": 4,
                         "items": obj({"conditions": conditions, "action": action})},
        })
    else:
        rule_draft = obj({
            "kind": s(enum=["always", "depends", "ask"]),
            "discriminator": nullable(s(maxLength=80)),
            "conditions": conditions,
            "action": action,
        })
    option = obj({"id": s(enum=["a", "b", "c"]), "label": s(maxLength=90), "rule_draft": rule_draft})
    question = obj({
        "id": s(pattern="^q[1-7]$"),
        "text": s(maxLength=300),
        "evidence": {"type": "array", "minItems": 1, "maxItems": 4,
                     "items": obj({"doc_id": s(enum=doc_ids), "quote": s(maxLength=160)})},
        "affected_doc_ids": {"type": "array", "minItems": 1, "items": s(enum=doc_ids)},
        "impact": s(enum=["high", "medium", "low"]),
        "options": {"type": "array", "minItems": 2, "maxItems": 3, "items": option},
        "suggested_option_id": s(enum=["a", "b", "c"]),
    })
    return obj({"questions": {"type": "array", "minItems": 1, "maxItems": 7, "items": question}})


PASS1_SYSTEM = """You are Mona, the back-office assistant of a dental practice. After a filing batch, some documents could not be filed with confidence. Analyse them for the owner:
- For each document, say what makes it ambiguous and which facts would settle it.
- Group documents that one answer from the owner would settle together (same counterparty, same ambiguity).
- For each group, draft the question you would ask, the 2-3 realistic answers, and the filing rule each answer implies (always X; depends on a discriminator such as the insured person or the site address; or ask each time).
- Rank the groups by how many documents and how much money they affect. At most 7 questions.
Be concrete and brief; cite the document ids and the exact snippet that supports each point."""
CONCISE = "\nWrite the final analysis as a compact bullet list, under 250 words; no tables, no per-document walkthrough."

PASS2_SYSTEM = """Turn the analysis into interview question cards for the owner, as JSON matching the schema.
- "text" is written in {language}, addressed to the owner, one short question.
- "evidence" quotes are copied exactly from the document snippets, with their doc_id.
- "affected_doc_ids" lists every document the answer settles.
- Each option has a short label in {language} and a rule_draft: kind "always" (a fixed action), "depends" (name the discriminator and give one condition set per option), or "ask" (no rule, ask each time).
- Actions use only the entity ids and category ids from the registry.
- "suggested_option_id" is the option the analysis supports best.
- At most 7 questions, highest impact first."""
PASS2_BRANCHES = """
- A rule_draft is a list of branches, each {conditions, action}. Every branch includes a counterparty condition so the rule stays scoped. "always": one branch. "depends": one branch per value of the discriminator (e.g. insured_person = X -> entity A; insured_person = Y -> entity B). "ask": no branches.
- Personal documents go to the person's entity id, never null."""


def pass1(cluster: dict, reasoning: dict | None, concise: bool, budget: float | None) -> dict:
    body = {"messages": [{"role": "system", "content": PASS1_SYSTEM + (CONCISE if concise else "")},
                         {"role": "user", "content": json.dumps(cluster, ensure_ascii=False)}],
            "max_tokens": 12000, "temperature": 0.6, "provider": ROUTE["provider"]}
    if reasoning is not None:
        body["reasoning"] = reasoning
    return stream_chat("t6", body, deadline=budget)


def pass2(cluster: dict, analysis: str, locale: str, reasoning: dict, branches: bool = False) -> tuple[dict, float]:
    user = (f"Registry and documents:\n{json.dumps(cluster, ensure_ascii=False)}\n\n"
            f"Analysis:\n{analysis}")
    system = PASS2_SYSTEM.format(language=LOCALES[locale]) + (PASS2_BRANCHES if branches else "")
    body = {"messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": 6000, "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "interview_questions", "strict": True, "schema": question_schema(cluster, branches)}},
            "reasoning": reasoning, "provider": ROUTE["provider"]}
    return chat("t6", body)


def check(obj: dict, cluster: dict) -> dict:
    """Semantic checks the schema cannot express."""
    snippets = {d["doc_id"]: norm(" | ".join(d["snippets"] + [d["addressee"] or ""]))
                for d in cluster["documents"]}
    qs = obj["questions"]
    ev = [(e["doc_id"], e["quote"]) for q in qs for e in q["evidence"]]
    return {
        "n_questions": len(qs),
        "evidence_quotes_verified": f"{sum(norm(qt) in snippets[d] for d, qt in ev)}/{len(ev)}",
        "suggested_in_options": all(q["suggested_option_id"] in {o["id"] for o in q["options"]} for q in qs),
        "depends_have_discriminator": all(o["rule_draft"]["discriminator"] for q in qs for o in q["options"]
                                          if o["rule_draft"]["kind"] == "depends"),
        "docs_covered": sorted({d for q in qs for d in q["affected_doc_ids"]}),
    }


def parse(data: dict, schema: dict) -> tuple[dict | None, str | None]:
    if "error" in data:
        return None, f"http {data['error'].get('code')}: {data['error'].get('message', '')[:120]}"
    msg = message(data)
    content = msg.get("content") or ""
    if not content.strip():
        fr = (data.get("choices") or [{}])[0].get("finish_reason")
        return None, f"empty content (finish_reason={fr}, reasoning chars={len(msg.get('reasoning') or '')})"
    try:
        obj = json.loads(content)
        jsonschema.validate(obj, schema)
        return obj, None
    except (json.JSONDecodeError, jsonschema.ValidationError) as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}"


def run(cluster: dict, locale: str, tag: str, pass2_reasoning: dict, concise: bool,
        budget: float | None = None) -> dict:
    schema = question_schema(cluster, ROUTE["branches"])
    t0 = time.monotonic()
    p1 = pass1(cluster, {"enabled": True}, concise, budget)
    t1 = time.monotonic()
    analysis = p1["content"]
    if p1["stopped_early"] or not analysis.strip():
        analysis = f"(Working notes, cut at the time budget)\n{p1['reasoning']}\n{p1['content']}"
    data, _ = pass2(cluster, analysis, locale, pass2_reasoning, ROUTE["branches"])
    t2 = time.monotonic()
    obj, err = parse(data, schema)
    out = {
        "tag": tag, "locale": locale, "order": ROUTE["provider"]["order"], "concise": concise,
        "rule_shape": "branches" if ROUTE["branches"] else "single_action",
        "pass2_reasoning": pass2_reasoning,
        "pass1": {"wall_s": round(t1 - t0, 2), "provider": p1["provider"],
                  "budget_s": budget, "stopped_early": p1["stopped_early"],
                  "t_first_reasoning": p1["t_first_reasoning"] and round(p1["t_first_reasoning"], 2),
                  "t_first_content": p1["t_first_content"] and round(p1["t_first_content"], 2),
                  "reasoning_chars": len(p1["reasoning"]), "content_chars": len(p1["content"]),
                  "usage": {k: (p1["usage"] or {}).get(k) for k in ("prompt_tokens", "completion_tokens", "cost")}
                  | {"reasoning_tokens": ((p1["usage"] or {}).get("completion_tokens_details") or {}).get("reasoning_tokens")}},
        "pass2": {"wall_s": round(t2 - t1, 2), "provider": data.get("provider"),
                  "finish_reason": (data.get("choices") or [{}])[0].get("finish_reason"),
                  "reasoning_chars": len(message(data).get("reasoning") or ""), **usage_summary(data)},
        "total_wall_s": round(t2 - t0, 2),
        "valid": obj is not None, "error": err,
        "checks": check(obj, cluster) if obj else None,
        "analysis": analysis, "questions": obj,
        "raw_pass2_content": None if obj else (message(data).get("content") or "")[:4000],
    }
    write_json(HERE / "debrief" / "outputs" / f"{tag}.json", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="en,en,en,fr")
    ap.add_argument("--think-pass2", action="store_true", help="also run pass 2 with thinking on")
    ap.add_argument("--order", default=None, help="comma-separated provider order (default: PROVIDER_PIN)")
    ap.add_argument("--concise", action="store_true")
    ap.add_argument("--branches", action="store_true", help="rule_draft as branches[{conditions, action}]")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--pass1-budget", type=float, default=None, help="stop pass 1 after N seconds")
    args = ap.parse_args()
    ROUTE["branches"] = args.branches
    if args.order:
        ROUTE["provider"] = {**PROVIDER_PIN, "order": args.order.split(",")}
    cluster = json.loads((HERE / "debrief" / "cluster.json").read_text())
    rows = []
    for i, loc in enumerate(args.runs.split(",") if args.runs else []):
        rows.append(run(cluster, loc, f"{args.prefix}run{i + 1}-{loc}", NO_THINK, args.concise,
                        args.pass1_budget))
    if args.think_pass2:
        rows.append(run(cluster, "en", f"{args.prefix}pass2-thinking-on", {"enabled": True}, args.concise))
    summary = [{k: r[k] for k in ("tag", "locale", "order", "concise", "rule_shape", "total_wall_s", "valid", "error", "checks")}
               | {"pass1_budget_s": r["pass1"]["budget_s"], "pass1_stopped_early": r["pass1"]["stopped_early"]}
               | {"pass1_wall_s": r["pass1"]["wall_s"], "pass2_wall_s": r["pass2"]["wall_s"],
                  "pass1_provider": r["pass1"]["provider"], "pass2_provider": r["pass2"]["provider"],
                  "pass1_reasoning_tokens": r["pass1"]["usage"]["reasoning_tokens"],
                  "pass1_completion_tokens": r["pass1"]["usage"]["completion_tokens"],
                  "pass2_reasoning_tokens": r["pass2"]["reasoning_tokens"],
                  "cost": round((r["pass1"]["usage"]["cost"] or 0) + (r["pass2"]["cost"] or 0), 5),
                  "pass1_cost_known": r["pass1"]["usage"]["cost"] is not None}
               for r in rows]
    prev = RESULTS / "t6_debrief.json"
    history = json.loads(prev.read_text())["runs"] if prev.exists() else []
    write_json(prev, {"runs": history + summary})
    print("| run | pass 1 s (provider, completion/reasoning tok) | pass 2 s (provider) | total s | valid | questions | evidence verified | cost $ |")
    print("|---|---|---|---|---|---|---|---|")
    for s in summary:
        c = s["checks"] or {}
        cut = " cut" if s["pass1_stopped_early"] else ""
        print(f"| {s['tag']} | {s['pass1_wall_s']}{cut} ({s['pass1_provider']}, {s['pass1_completion_tokens']}/{s['pass1_reasoning_tokens']}) | "
              f"{s['pass2_wall_s']} ({s['pass2_provider']}) | {s['total_wall_s']} | {s['valid']} | "
              f"{c.get('n_questions', '-')} | {c.get('evidence_quotes_verified', '-')} | {s['cost']} |")
        if s["error"]:
            print("   error:", s["error"])


if __name__ == "__main__":
    main()
