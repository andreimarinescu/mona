"""S7 probe: curated recipes as Hermes skills (B) or SOUL lines (C) against today's config (A).

Run from apps/api with its venv (it imports Mona's overlay builder):
  python ../../docs/spikes/s7/s7_probe.py run --config A [--reps 3] [--only due-1,owe-1]
  python ../../docs/spikes/s7/s7_probe.py baseline --config A
  python ../../docs/spikes/s7/s7_probe.py report
The asks and their checks are private (names, amounts): demo-data/spikes/s7/asks.yaml. Raw turns
(reply text included) go to demo-data/spikes/s7/turns.jsonl; the report prints ids and numbers only.
"""

import json
import pathlib
import re
import statistics
import subprocess
import sys
import time
import uuid

import httpx
import yaml

from mona.chat.overlay import build_overlay, reply_language
from mona.i18n import detect_language

HERE = pathlib.Path(__file__).resolve().parent
ENV_FILE = pathlib.Path("~/DevFiles/mona-hq/mona/.env").expanduser()
PRIVATE = pathlib.Path("~/DevFiles/mona-hq/demo-data/spikes/s7").expanduser()
TURNS = PRIVATE / "turns.jsonl"
HERMES = "http://localhost:11042"
CONTAINER = "mona-s7-hermes-1"
BUDGET_USD = 1.0
SKILL_TOOLS = {"skills_list", "skill_view", "skill_manage"}
NOT_MONA = SKILL_TOOLS | {"memory", "todo"}


def env(key: str) -> str:
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{key} missing from .env")


def or_usage() -> float:
    r = httpx.get(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": f"Bearer {env('OPENROUTER_API_KEY')}"},
        timeout=30,
    )
    r.raise_for_status()
    return float(r.json()["data"]["usage"])


def recipes() -> list[tuple[str, str, str]]:
    out = []
    for f in sorted((HERE / "recipes").glob("*/SKILL.md")):
        _, front, body = f.read_text().split("---", 2)
        meta = yaml.safe_load(front)
        out.append((meta["name"], meta["description"], body.strip()))
    return out


def soul_c() -> str:
    lines = ["", "## Procedures for common asks", "When an ask matches one, follow its steps."]
    for name, desc, body in recipes():
        lines += ["", f"### {name}: {desc}", body]
    return "\n".join(lines) + "\n"


def state(session_id: str) -> dict:
    code = f"""
import json, sqlite3
c = sqlite3.connect('file:/opt/data/state.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
s = c.execute('select * from sessions where id=?', ({session_id!r},)).fetchone()
m = c.execute('select role, content, tool_calls, tool_name from messages where session_id=? order by id',
              ({session_id!r},)).fetchall()
sp = (s['system_prompt'] or '') if s else ''
if s and not sp and s['system_prompt_hash']:
    row = c.execute('select prompt from system_prompts where hash=?', (s['system_prompt_hash'],)).fetchone()
    sp = row['prompt'] if row else ''
print(json.dumps({{
  'session': {{k: s[k] for k in ('api_call_count', 'tool_call_count', 'input_tokens', 'output_tokens',
              'reasoning_tokens', 'cache_read_tokens', 'estimated_cost_usd', 'actual_cost_usd')}} if s else None,
  'system_prompt_chars': len(sp),
  'system_prompt_hash': s['system_prompt_hash'] if s else None,
  'markers': {{'available_skills': '<available_skills>' in sp, 'procedures': 'Procedures for common asks' in sp,
              'skill_guidance': 'skill_manage' in sp, 'terminal': 'terminal' in sp,
              'skills_listed': sp.count('\\n    - ') if '<available_skills>' in sp else 0}},
  'messages': [dict(r) for r in m],
}}))
"""
    out = subprocess.run(
        ["docker", "exec", CONTAINER, "/opt/hermes/.venv/bin/python", "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def tool_errors(messages: list[dict]) -> dict:
    tool = [m["content"] or "" for m in messages if m["role"] == "tool"]
    return {
        "tool_errors": sum('{"error"' in c for c in tool),
        "breaker_hits": sum("rejected the last" in c or "unreachable after" in c for c in tool),
        "unknown_tools": sum("does not exist. Available tools" in c for c in tool),
    }


def unwrap(content: str | None) -> object:
    """Hermes wraps MCP results in an <untrusted_tool_result> block around {"result": "<json>"}."""
    body = re.search(r"\n\n(\{.*\})\s*</untrusted_tool_result>", content or "", re.S)
    try:
        value = json.loads(body.group(1) if body else content or "null")
        if isinstance(value, dict) and isinstance(value.get("result"), str):
            value = json.loads(value["result"])
        return value
    except (json.JSONDecodeError, TypeError):
        return content


def turn(client: httpx.Client, cfg: str, ask: dict, rep: int) -> dict:
    sid = f"s7-{cfg}-{ask['id']}-{rep}-{uuid.uuid4().hex[:6]}"
    client.post("/api/sessions", json={"id": sid, "title": sid}).raise_for_status()
    lang, pinned = reply_language(ask["text"], None, None, "en")
    overlay = build_overlay("/chat", "Chat page", lang, pinned=pinned)
    body = {
        "model": "mona",
        "stream": True,
        "messages": [
            {"role": "system", "content": overlay},
            {"role": "user", "content": ask["text"]},
        ],
    }
    t0 = time.monotonic()
    first_reasoning = first_text = None
    text, progress, usage, finish, event, error = [], [], None, None, None, None
    try:
        with client.stream(
            "POST", "/v1/chat/completions", json=body, headers={"X-Hermes-Session-Id": sid}
        ) as res:
            res.raise_for_status()
            for line in res.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                payload = json.loads(data)
                if event == "hermes.tool.progress":
                    progress.append({**payload, "t": round(time.monotonic() - t0, 2)})
                elif event is None:
                    for ch in payload.get("choices", []):
                        d = ch.get("delta") or {}
                        if d.get("reasoning_content") and first_reasoning is None:
                            first_reasoning = time.monotonic() - t0
                        if d.get("content"):
                            if first_text is None:
                                first_text = time.monotonic() - t0
                            text.append(d["content"])
                        finish = ch.get("finish_reason") or finish
                    usage = payload.get("usage") or usage
                event = None
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        error = repr(e)
    close = time.monotonic() - t0
    st = state(sid)
    calls = []
    for m in st["messages"]:
        for tc in json.loads(m["tool_calls"] or "[]"):
            fn = tc.get("function", tc)
            args = fn.get("arguments")
            try:
                args = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                pass
            calls.append({"name": re.sub(r"^mcp__mona__", "", fn.get("name") or ""), "args": args})
    results = {}
    for m in st["messages"]:
        if m["role"] == "tool" and m["tool_name"]:
            results.setdefault(re.sub(r"^mcp__mona__", "", m["tool_name"]), unwrap(m["content"]))
    return {
        **tool_errors(st["messages"]),
        "cfg": cfg,
        "ask": ask["id"],
        "recipe": ask["recipe"],
        "rep": rep,
        "session": sid,
        "lang": lang,
        "t_first_reasoning": first_reasoning,
        "t_first_text": first_text,
        "t_close": close,
        "finish": finish,
        "error": error,
        "usage": usage,
        "state": st["session"],
        "system_prompt_chars": st["system_prompt_chars"],
        "system_prompt_hash": st["system_prompt_hash"],
        "markers": st["markers"],
        "calls": calls,
        "results": results,
        "text": "".join(text),
    }


def regrade() -> None:
    """Re-apply the checks in asks.yaml to the recorded turns (after a check is corrected)."""
    data = {a["id"]: a for a in yaml.safe_load((PRIVATE / "asks.yaml").read_text())}
    rows = [json.loads(x) for x in TURNS.read_text().splitlines()]
    for r in rows:
        if "tool_errors" not in r:
            r.update(tool_errors(state(r["session"])["messages"]))
        if not r["baseline"]:
            r["grade"] = grade(r, data[r["ask"]])
    TURNS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def grade(t: dict, ask: dict) -> dict:
    names = [c["name"] for c in t["calls"]]
    mona = [n for n in names if n not in NOT_MONA]
    views = [
        str(c["args"].get("name")).split(":")[-1]
        for c in t["calls"]
        if c["name"] == "skill_view" and isinstance(c["args"], dict)
    ]
    paths = [ask["path"], *ask.get("alt_paths", [])]
    ok_tools = mona in paths
    ok_args = True
    for tool, want in (ask.get("args") or {}).items():
        got = [c["args"] for c in t["calls"] if c["name"] == tool and isinstance(c["args"], dict)]
        ok_args &= any(all(g.get(k) == v for k, v in want.items()) for g in got)
    for tool, want in (ask.get("result") or {}).items():
        r = t["results"].get(tool)
        ok_args &= (
            isinstance(r, dict)
            and (r.get("entity") or {}).get("key") == want["entity_key"]
            and r.get("fiscal_year") == want["fiscal_year"]
        )
        ok_args &= tool in mona
    text = t["text"]
    ok_text = all(re.search(p, text, re.I) for p in ask.get("text_all", [])) and not any(
        re.search(p, text, re.I) for p in ask.get("text_none", [])
    )
    if ask["recipe"] in ("none", "hard"):
        skill_ok = not views
    elif t["cfg"].startswith("B"):
        skill_ok = ask["recipe"] in views
    else:
        skill_ok = None
    return {
        "mona_calls": len(mona),
        "all_calls": len(names),
        "skill_views": views,
        "skill_ok": skill_ok,
        "path_ok": ok_tools,
        "correct": bool(text.strip())
        and ok_args
        and ok_text
        and (not ask["path"] or any(p[-1] in mona for p in paths)),
        "empty": not text.strip(),
        "reply_lang": detect_language(text) if text.strip() else None,
        "wrong_lang": bool(text.strip()) and detect_language(text) not in (None, t["lang"]),
    }


def asks(only: str | None) -> list[dict]:
    data = yaml.safe_load((PRIVATE / "asks.yaml").read_text())
    return [a for a in data if not only or a["id"] in only.split(",")]


def run(cfg: str, reps: int, only: str | None, baseline: bool = False) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    before = or_usage()
    ledger = PRIVATE / "spend.jsonl"
    spent = (
        sum(json.loads(x)["usd"] for x in ledger.read_text().splitlines())
        if ledger.exists()
        else 0.0
    )
    if spent >= BUDGET_USD:
        raise SystemExit(f"budget: ${spent:.4f} spent")
    client = httpx.Client(
        base_url=HERMES,
        headers={"Authorization": f"Bearer {env('HERMES_API_KEY')}"},
        timeout=httpx.Timeout(connect=5, read=240, write=30, pool=5),
    )
    items = (
        [{"id": "hello", "recipe": "none", "text": "Hello!", "path": []}]
        if baseline
        else asks(only)
    )
    done = set()
    if TURNS.exists() and not baseline:
        done = {
            (r["cfg"], r["ask"], r["rep"])
            for r in map(json.loads, TURNS.read_text().splitlines())
            if not r["baseline"]
        }
    with TURNS.open("a") as out:
        for rep in range(1, reps + 1):
            for ask in items:
                if (cfg, ask["id"], rep) in done:
                    continue
                t = turn(client, cfg, ask, rep)
                t["grade"] = grade(t, ask)
                t["baseline"] = baseline
                out.write(json.dumps(t, ensure_ascii=False) + "\n")
                out.flush()
                g = t["grade"]
                print(
                    f"{cfg} {ask['id']:7} r{rep} calls={g['all_calls']}/{g['mona_calls']} "
                    f"skill={g['skill_views']} path={g['path_ok']} ok={g['correct']} "
                    f"text={t['t_first_text'] and round(t['t_first_text'], 1)} "
                    f"close={round(t['t_close'], 1)} prompt={(t['usage'] or {}).get('prompt_tokens')}",
                    flush=True,
                )
    time.sleep(5)
    after = or_usage()
    with ledger.open("a") as f:
        f.write(
            json.dumps({"cfg": cfg, "baseline": baseline, "usd": after - before, "ts": time.time()})
            + "\n"
        )
    print(f"OpenRouter usage delta {cfg}: ${after - before:.4f}")


def prompt_tokens(r: dict) -> int:
    """Hermes' stream usage: every LLM call's prompt, cached prefix included."""
    return (r["usage"] or {}).get("prompt_tokens") or r["state"]["input_tokens"] + r["state"][
        "cache_read_tokens"
    ]


def med(xs: list) -> str:
    xs = [x for x in xs if x is not None]
    return f"{statistics.median(xs):.1f}" if xs else "–"


def report() -> None:
    rows = [json.loads(x) for x in TURNS.read_text().splitlines()]
    hard = [r for r in rows if not r["baseline"] and r["recipe"] == "hard"]
    turns = [r for r in rows if not r["baseline"] and r["recipe"] != "hard"]
    base = [r for r in rows if r["baseline"]]
    cfgs = sorted({r["cfg"] for r in turns})
    print("### Baseline: one-word greeting, one LLM call\n")
    print(
        "| Config | Prompt tokens per LLM call (each run) | System prompt chars | Skills listed "
        "| Skill-authoring guidance | 'terminal' in prompt |"
    )
    print("|---|---|---|---|---|---|")
    for cfg in sorted({r["cfg"] for r in base}):
        bs = [r for r in base if r["cfg"] == cfg]
        b = bs[-1]
        m = b["markers"]
        per = ", ".join(str(prompt_tokens(x) // max(1, x["state"]["api_call_count"])) for x in bs)
        print(
            f"| {cfg} | {per} | {b['system_prompt_chars']} | {m['skills_listed']} "
            f"| {'yes' if m['skill_guidance'] else 'no'} | {'yes' if m['terminal'] else 'no'} |"
        )
    print("\n### Per configuration (30 turns each)\n")
    print(
        "| Config | Correct | Recipe path followed | Right skill loaded | Tool calls/turn (median, max) "
        "| Mona calls/turn | Turns ≤ 2 calls | LLM calls/turn | Prompt tokens/turn (median) "
        "| Prompt tokens/LLM call | First text s (median) | Close s (median, max) | Empty replies | Wrong language |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for cfg in cfgs:
        ts = [r for r in turns if r["cfg"] == cfg]
        n = len(ts)
        rec = [r for r in ts if r["recipe"] != "none"]
        skill = [r["grade"]["skill_ok"] for r in rec if r["grade"]["skill_ok"] is not None]
        calls = [r["grade"]["all_calls"] for r in ts]
        llm = [r["state"]["api_call_count"] for r in ts]
        ins = [prompt_tokens(r) for r in ts]
        per = [i / c for i, c in zip(ins, llm) if c]
        print(
            f"| {cfg} | {sum(r['grade']['correct'] for r in ts)}/{n} "
            f"| {sum(r['grade']['path_ok'] for r in rec)}/{len(rec)} "
            f"| {f'{sum(skill)}/{len(skill)}' if skill else 'n/a'} "
            f"| {med(calls)}, {max(calls)} | {med([r['grade']['mona_calls'] for r in ts])} "
            f"| {sum(c <= 2 for c in calls)}/{n} | {med(llm)} | {med(ins)} | {med(per)} "
            f"| {med([r['t_first_text'] for r in ts])} | {med([r['t_close'] for r in ts])}, "
            f"{max(r['t_close'] for r in ts):.1f} | {sum(r['grade']['empty'] for r in ts)} "
            f"| {sum(r['grade'].get('wrong_lang', False) for r in ts)} |"
        )
    print("\n### Per ask (correct / 3; tool calls per rep; close s median)\n")
    print("| Ask | Recipe | " + " | ".join(cfgs) + " |")
    print("|---|---|" + "---|" * len(cfgs))
    for ask in dict.fromkeys(r["ask"] for r in turns):
        cells = []
        for cfg in cfgs:
            ts = [r for r in turns if r["cfg"] == cfg and r["ask"] == ask]
            seq = ",".join(str(r["grade"]["all_calls"]) for r in ts)
            extra = ""
            if cfg.startswith("B"):
                extra = " skill " + ",".join("+" if r["grade"]["skill_ok"] else "-" for r in ts)
            cells.append(
                f"{sum(r['grade']['correct'] for r in ts)}/{len(ts)}; calls {seq}{extra}; "
                f"{med([r['t_close'] for r in ts])} s"
            )
        recipe = next(r["recipe"] for r in turns if r["ask"] == ask)
        print(f"| {ask} | {recipe} | " + " | ".join(cells) + " |")
    if hard:
        print("\n### Extra: asks beyond Mona's tools (3 reps each; calls, close s, empty)\n")
        print("| Ask | " + " | ".join(sorted({r["cfg"] for r in hard})) + " |")
        print("|---|" + "---|" * len({r["cfg"] for r in hard}))
        for ask in dict.fromkeys(r["ask"] for r in hard):
            cells = []
            for cfg in sorted({r["cfg"] for r in hard}):
                ts = [r for r in hard if r["cfg"] == cfg and r["ask"] == ask]
                cells.append(
                    "calls "
                    + ",".join(str(r["grade"]["all_calls"]) for r in ts)
                    + "; "
                    + ",".join(f"{r['t_close']:.0f}" for r in ts)
                    + " s"
                    + f"; empty {sum(r['grade']['empty'] for r in ts)}"
                    + f"; tool errors {sum(r['tool_errors'] for r in ts)}"
                    + f", breaker {sum(r['breaker_hits'] for r in ts)}"
                )
            print(f"| {ask} | " + " | ".join(cells) + " |")
    print("\n### Tool sequences (ids and tool names only)\n")
    for cfg in cfgs:
        print(f"**{cfg}**\n")
        for r in [r for r in turns + hard if r["cfg"] == cfg]:
            seq = " → ".join(
                c["name"]
                + (
                    f"({c['args'].get('name')})"
                    if c["name"] == "skill_view" and isinstance(c["args"], dict)
                    else ""
                )
                for c in r["calls"]
            )
            err = (
                f" [tool errors {r['tool_errors']}, breaker {r['breaker_hits']}]"
                if r["tool_errors"]
                else ""
            )
            print(
                f"- {r['ask']} r{r['rep']}: {seq or '(none)'}{' ✗' if not r['grade']['correct'] else ''}{err}"
            )
        print()
    print("### Hermes' estimated model cost (sum over the turns)\n")
    for cfg in sorted({r["cfg"] for r in rows}):
        est = sum(
            (r["state"] or {}).get("estimated_cost_usd") or 0 for r in rows if r["cfg"] == cfg
        )
        print(f"- {cfg}: ${est:.4f}")
    print()
    ledger = PRIVATE / "spend.jsonl"
    if ledger.exists():
        spend = [json.loads(x) for x in ledger.read_text().splitlines()]
        print("### OpenRouter usage delta\n")
        for s in spend:
            print(f"- {s['cfg']}{' baseline' if s['baseline'] else ''}: ${s['usd']:.4f}")
        print(f"- total: ${sum(s['usd'] for s in spend):.4f}")


def to_csv() -> None:
    """Per-turn numbers for the repo: ids, tool names and measurements, no reply text."""
    import csv

    w = csv.writer(sys.stdout)
    w.writerow(
        ["cfg", "ask", "recipe", "rep", "tools", "skill_views", "all_calls", "mona_calls",
         "llm_calls", "prompt_tokens", "cache_read_tokens", "output_tokens", "reasoning_tokens",
         "t_first_reasoning", "t_first_text", "t_close", "correct", "path_ok", "empty",
         "wrong_lang", "tool_errors", "breaker_hits", "unknown_tools", "est_cost_usd"]
    )  # fmt: skip
    for r in map(json.loads, TURNS.read_text().splitlines()):
        g, s = r.get("grade") or {}, r["state"]
        rnd = lambda x: None if x is None else round(x, 2)  # noqa: E731
        w.writerow(
            [r["cfg"], r["ask"], r["recipe"], r["rep"], " ".join(c["name"] for c in r["calls"]),
             " ".join(g.get("skill_views", [])), g.get("all_calls", 0), g.get("mona_calls", 0),
             s["api_call_count"], prompt_tokens(r), s["cache_read_tokens"], s["output_tokens"],
             s["reasoning_tokens"], rnd(r["t_first_reasoning"]), rnd(r["t_first_text"]),
             rnd(r["t_close"]), g.get("correct"), g.get("path_ok"), g.get("empty"),
             g.get("wrong_lang"), r["tool_errors"], r["breaker_hits"], r["unknown_tools"],
             s["estimated_cost_usd"]]
        )  # fmt: skip


def main() -> None:
    args = sys.argv[1:]
    opt = {k.lstrip("-"): v for k, v in zip(args[1::2], args[2::2])}
    match args[0]:
        case "soul-c":
            sys.stdout.write(soul_c())
        case "run":
            run(opt["config"], int(opt.get("reps", 3)), opt.get("only"))
        case "baseline":
            run(opt["config"], 1, None, baseline=True)
        case "regrade":
            regrade()
        case "report":
            report()
        case "csv":
            to_csv()


if __name__ == "__main__":
    main()
