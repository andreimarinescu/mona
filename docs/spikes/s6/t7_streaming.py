# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""T7: streaming time-to-first reasoning/content token and decode speed, thinking on vs off."""
import argparse
import statistics

from _or import NO_THINK, PROVIDER_PIN, RESULTS, stream_chat, write_json

PROMPT = ("A patient asks whether they can pay a 1,850 EUR treatment in three instalments. "
          "Draft a two-sentence friendly reply from the practice manager.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", default="pin,parasail,deepinfra,akashml")
    ap.add_argument("--reps", type=int, default=3)
    args = ap.parse_args()
    rows = []
    for rep in range(args.reps):
        for route in args.routes.split(","):
            prov = PROVIDER_PIN if route == "pin" else {"only": [route], "allow_fallbacks": False,
                                                        "require_parameters": True}
            for mode, reasoning in (("think", {"enabled": True}), ("no_think", NO_THINK)):
                out = stream_chat("t7", {"messages": [{"role": "user", "content": PROMPT}],
                                         "max_tokens": 4000, "temperature": 0.6,
                                         "reasoning": reasoning, "provider": prov})
                u = out["usage"] or {}
                first = out["t_first_reasoning"] or out["t_first_content"]
                tok = u.get("completion_tokens") or 0
                rows.append({
                    "route": route, "mode": mode, "rep": rep, "served_by": out["provider"],
                    "error": out.get("error", {}).get("message") if out.get("error") else None,
                    "t_first_reasoning": out["t_first_reasoning"] and round(out["t_first_reasoning"], 2),
                    "t_first_content": out["t_first_content"] and round(out["t_first_content"], 2),
                    "wall_s": round(out["wall"], 2), "completion_tokens": tok,
                    "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                    "tok_per_s": round(tok / (out["wall"] - first), 1) if first and out["wall"] > first else None,
                    "delta_keys": out["delta_keys"],
                })
    write_json(RESULTS / "t7_streaming.json", {"prompt": PROMPT, "rows": rows})
    med = lambda xs: round(statistics.median(xs), 2) if xs else None
    print("| route | mode | served by | first reasoning s | first content s | total s | completion tok | decode tok/s | delta keys |")
    print("|---|---|---|---|---|---|---|---|---|")
    for route in args.routes.split(","):
        for mode in ("think", "no_think"):
            rs = [r for r in rows if r["route"] == route and r["mode"] == mode and not r["error"]]
            print(f"| {route} | {mode} | {sorted({r['served_by'] for r in rs})} | "
                  f"{med([r['t_first_reasoning'] for r in rs if r['t_first_reasoning']])} | "
                  f"{med([r['t_first_content'] for r in rs if r['t_first_content']])} | "
                  f"{med([r['wall_s'] for r in rs])} | {med([r['completion_tokens'] for r in rs])} | "
                  f"{med([r['tok_per_s'] for r in rs if r['tok_per_s']])} | "
                  f"{sorted({k for r in rs for k in r['delta_keys']})} |")
    errs = [r for r in rows if r["error"]]
    for r in errs:
        print("  error:", r["route"], r["mode"], r["error"])


if __name__ == "__main__":
    main()
