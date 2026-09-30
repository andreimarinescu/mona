# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""S2: tool-call reliability, page-context overlay and card-action notes through the Hermes API server."""
import json
import os
import sys
import time

import httpx

BASE = os.environ.get("HERMES_URL", "http://localhost:8642")
H = {"Authorization": f"Bearer {os.environ['HERMES_API_KEY']}"}
MCP_LOG = os.environ.get("SPIKE_LOG", "/tmp/hermes-s1/mcp-calls.jsonl")
OUT = sys.argv[1]

PROMPTS = [
    ("How much did we pay AGIPI in total?", ["search_documents", "sum_amounts"], "1"),
    ("What's due in the next 30 days?", ["list_deadlines"], "14"),
    ("Find the EDF invoice and tell me the amount.", ["search_documents"], "214"),
    ("Combien avons-nous payé à l'URSSAF ?", ["search_documents"], "1"),
    ("Câte documente AGIPI avem în arhivă?", ["search_documents"], "2"),
    ("Is the URSSAF payment due before the EDF one?", ["search_documents"], "EDF"),
    ("Sum the EDF and URSSAF amounts.", ["sum_amounts"], "1"),
    ("Which documents are filed under Personnel?", ["search_documents"], "AGIPI"),
    ("Give me the due date of the URSSAF letter.", ["search_documents"], "14"),
    ("List every deadline with its amount.", ["list_deadlines"], "1"),
]


def new_session(title):
    r = httpx.post(f"{BASE}/api/sessions", headers=H, json={"title": title}, timeout=30)
    r.raise_for_status()
    return r.json()["session"]["id"]


def turn(sid, messages):
    t0 = time.time()
    first_reasoning = first_content = None
    content, reasoning, tools = "", "", []
    with httpx.stream("POST", f"{BASE}/v1/chat/completions", timeout=180,
                      headers={**H, "X-Hermes-Session-Id": sid},
                      json={"model": "mona", "stream": True, "messages": messages}) as r:
        event = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
                continue
            if not line.startswith("data: {"):
                event = None if not line else event
                continue
            d = json.loads(line[6:])
            if event == "hermes.tool.progress":
                if d.get("status") == "running":
                    tools.append(d["tool"])
                event = None
                continue
            for c in d.get("choices", []):
                delta = c.get("delta", {})
                if delta.get("reasoning_content"):
                    reasoning += delta["reasoning_content"]
                    first_reasoning = first_reasoning or time.time() - t0
                if delta.get("content"):
                    content += delta["content"]
                    first_content = first_content or time.time() - t0
    return {"tools": tools, "content": content.strip(), "reasoning_chars": len(reasoning),
            "first_reasoning_s": round(first_reasoning or -1, 2), "first_content_s": round(first_content or -1, 2),
            "total_s": round(time.time() - t0, 2)}


def main():
    results = {"reliability": [], "notes": {}}
    for i, (prompt, expected_tools, must_contain) in enumerate(PROMPTS):
        sid = new_session(f"s2-rel-{i}")
        r = turn(sid, [{"role": "user", "content": prompt}])
        called = [t.removeprefix("mcp__mona__") for t in r["tools"]]
        r.update(prompt=prompt, ok_tools=all(t in called for t in expected_tools),
                 ok_answer=must_contain.lower() in r["content"].lower())
        results["reliability"].append(r)
        print(f"[{i}] tools={called} ok_tools={r['ok_tools']} ok_answer={r['ok_answer']} "
              f"t_reason={r['first_reasoning_s']} t_content={r['first_content_s']} total={r['total_s']}", flush=True)

    sid = new_session("s2-notes")
    t1 = turn(sid, [{"role": "user", "content": "Are the AGIPI documents personal or business?"}])
    note = ("Card actions since your last reply (the user did these in the app; treat them as done and don't contradict them): "
            "Answered interview question Q2 'Who holds the AGIPI contracts?' with 'Always personal, split by insured person'. "
            "A rule was created and applied: AGIPI -> Personnel / Assurances / {insured}.")
    t2 = turn(sid, [{"role": "system", "content": note},
                    {"role": "user", "content": "OK. So where will the next AGIPI letter go?"}])
    sid_b = new_session("s2-notes-prefixed")
    t3 = turn(sid_b, [{"role": "user", "content": f"[{note}]\n\nSo where will the next AGIPI letter go?"}])
    results["notes"] = {"turn1": t1, "turn2_system_overlay": t2, "prefixed_user_message": t3, "note": note}
    for k in ("turn2_system_overlay", "prefixed_user_message"):
        print(k, "->", results["notes"][k]["content"][:300].replace("\n", " "), flush=True)
    json.dump(results, open(OUT, "w"), indent=1, ensure_ascii=False)
    rel = results["reliability"]
    print(f"tools ok {sum(r['ok_tools'] for r in rel)}/{len(rel)}, answers ok {sum(r['ok_answer'] for r in rel)}/{len(rel)}")


if __name__ == "__main__":
    main()
