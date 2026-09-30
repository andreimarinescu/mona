# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""T2: which request knob turns Qwen 3.6 hybrid thinking off, per pinned provider."""
import argparse
import statistics
from concurrent.futures import ThreadPoolExecutor

from _or import MODEL, RESULTS, chat, message, usage_summary, write_json

PROMPT = ("A clinic pays 3 invoices of 1,240.50 EUR, 318.20 EUR and 97.75 EUR, then receives a "
          "credit note of 212.00 EUR. What is the net amount paid? Reply with the amount only.")

VARIANTS = {
    "default": {},
    "enabled_false": {"reasoning": {"enabled": False}},
    "effort_none": {"reasoning": {"effort": "none"}},
    "effort_low": {"reasoning": {"effort": "low"}},
    "exclude_true": {"reasoning": {"exclude": True}},
    "include_reasoning_false": {"include_reasoning": False},
    "chat_template_kwargs": {"chat_template_kwargs": {"enable_thinking": False}},
    "no_think_soft_switch": {"_suffix": " /no_think"},
    "reasoning_max_tokens_256": {"reasoning": {"max_tokens": 256}},
}


def run_one(provider: str, name: str, rep: int) -> dict:
    extra = dict(VARIANTS[name])
    suffix = extra.pop("_suffix", "")
    body = {
        "messages": [{"role": "user", "content": PROMPT + suffix}],
        "max_tokens": 6000, "temperature": 0,
        "provider": {"only": [provider], "allow_fallbacks": False, "require_parameters": True},
        **extra,
    }
    data, wall = chat("t2", body)
    msg = message(data)
    content = msg.get("content") or ""
    return {
        "provider": provider, "variant": name, "rep": rep, "wall_s": round(wall, 2),
        "served_by": data.get("provider"), "error": (data.get("error") or {}).get("message"),
        "reasoning_text_chars": len(msg.get("reasoning") or ""),
        "content_chars": len(content), "think_tag_in_content": "<think>" in content,
        "content_head": content.strip()[:40],
        **usage_summary(data),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="parasail,deepinfra,akashml")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--out", default="t2_thinking.json")
    args = ap.parse_args()
    providers = args.providers.split(",")
    variants = args.variants.split(",")

    def per_provider(p):
        return [run_one(p, v, r) for r in range(args.reps) for v in variants]

    with ThreadPoolExecutor(len(providers)) as ex:
        rows = [row for rows in ex.map(per_provider, providers) for row in rows]
    write_json(RESULTS / args.out, {"model": MODEL, "prompt": PROMPT, "rows": rows})

    print("| provider | variant | reasoning tok (per rep) | reasoning text chars | wall s median | answer | error |")
    print("|---|---|---|---|---|---|---|")
    for p in providers:
        for v in variants:
            rs = [r for r in rows if r["provider"] == p and r["variant"] == v]
            print(f"| {p} | {v} | {[r['reasoning_tokens'] for r in rs]} | "
                  f"{[r['reasoning_text_chars'] for r in rs]} | "
                  f"{statistics.median(r['wall_s'] for r in rs):.2f} | "
                  f"{rs[0]['content_head']!r} | {rs[0]['error'] or ''} |")


if __name__ == "__main__":
    main()
