# S7: curated Hermes skills as recipes for Qwen 3.6

Run on 2026-10-01 on the laptop (compose project `mona-s7`). Hermes 0.21.5, model `qwen/qwen3.6-35b-a3b` on OpenRouter with the D4 pins and `reasoning_effort: medium`. Data: the `demo-prefiled` stage snapshot, restored with `--anchor today` (29 documents). Drafts and packs ran in the background on the default worker model (`qwen/qwen3.7-flash`).

**Question (D18).** Do curated Hermes skills (recipes we write and version) help Qwen 3.6 answer common asks in ≤ 2 tool calls? Are they better than the same recipes as SOUL lines, and at what prompt cost and latency?

## Answer

**Don't adopt B (skills). Adopting C (recipes as SOUL lines) is optional: it is cheap and slightly tighter, but it fixes nothing that is broken today.**

| | A: today | B: skills | C: SOUL lines |
|---|---|---|---|
| Correct | 30/30 | 30/30 | 30/30 |
| Matching recipe loaded | n/a | **4/24** | n/a |
| Recipe tool path followed | 17/24 | 13/24 | 19/24 |
| Turns with ≤ 2 tool calls | 25/30 | 24/30 | 28/30 |
| Prompt tokens per LLM call: greeting / turn median | 8,993 / 9,269 | 10,695 / 11,034 | 9,493 / 9,735 |
| Close, median (max) | 5.9 s (12.9) | 5.3 s (18.0) | 6.0 s (10.9) |

- **B: Qwen mostly ignores the skills.** Hermes adds an index and a "you MUST load a matching skill" preamble to the system prompt. Qwen loaded the matching recipe in only 4 of 24 recipe turns, and each load added a tool call and an LLM round trip.
  - Turning the toolset on costs +1.7k prompt tokens on every LLM call (+19%), whether or not a skill is used.
  - It also brings Hermes' own text into the prompt: "offer to save as a skill", "fix it with skill_manage", and "load the skill even if you could handle the task with basic tools like terminal".
  - On a spreadsheet ask, Qwen called `skill_manage` 5 times to write an `export-spreadsheet` skill whose procedure is "write a Python script using `python3 -c` … `openpyxl`" (a tool Mona doesn't have). It then ended with an empty reply. `write_approval: true` staged 4 of those writes for approval, and one more call tried to delete the `mona` category.
  - In another rep, Qwen put a Python script that builds the spreadsheet into a `skill_manage` call.
  - `skill_manage` can't be removed without removing the whole `skills` toolset.
- **C** costs +500 tokens per call (+5.6%). Correctness and latency are unchanged. Path adherence improves a little: 19/24 against 17/24, and 28/30 turns with ≤ 2 calls against 25/30. These are 3 reps per ask, so treat the gain as small.
- **Today's config already answers all ten asks (30/30), in a median of 1 tool call.** The recipes only duplicate what SOUL and the tool descriptions already say.

### Findings beyond the three configurations (for Andrei's decision)

1. **Hermes adds model-gated "Tool-use enforcement" and "Execution discipline" blocks for any model whose name contains `qwen`.** They make up 7.4k of A's 15k system-prompt characters. They tell the model:
   - "Keep calling tools until the task is complete AND verified";
   - "if results are partial, retry broader";
   - "Arithmetic → use terminal or execute_code";
   - "Current time → run `date`";
   - "File contents → read_file".

   None of those tools exist for Mona. This text is in A today: it is a plausible source of the evening session's terminal claims (A28 "why"). The hard asks in A and C included calls to `terminal`, `mcp__terminal__run` and `read_file`; D and CD had none.

   With the extra configuration D (A plus `agent.tool_use_enforcement: false` and `agent.execution_guidance: false`):
   - the prompt drops by 1.05k tokens per call (−12%), and "terminal" disappears from it;
   - 30/30 correct, and median close 3.6 s against 5.9 s (time-of-day caveat below);
   - 0 calls to tools that don't exist.

   CD (C plus the same two keys): 29/30 correct, 3.3 s median. The miss was an "owe" ask answered with the total but no due date.
2. **Hermes' MCP circuit breaker spreads one bad turn to everyone.**
   - After 3 consecutive tool errors from the `mona` server, Hermes 0.21.5 refuses every `mona` call for 60 s, process-wide and across sessions.
   - The errors here were Mona's own `invalid_argument`: `limit: 50 > 25`, `category: "payable"`.
   - Threshold and cooldown are hard-coded (`tools/mcp_tool.py`); no config key changes them.
   - In 16 of the 30 hard turns, the **first** tool call was refused by a breaker that the previous turn had opened. Mona then told the person "the archive server is down / rejecting calls", which was false.

   FIX-10 already returns `budget_exhausted` as a non-error for this reason. `invalid_argument`, `not_found` and the other C4 errors still trip the breaker.
3. **Requests beyond Mona's tools fail in every configuration** (2 extra asks: "payables with IBAN as CSV" and "an Excel sheet of a year's declarations").
   - Loops reached 38 tool calls in 12 LLM iterations: Hermes `max_turns` counts iterations, not parallel calls.
   - Up to 111 s per turn.
   - Several turns ended on "Let me build the Excel file now." with nothing after it, and 2 replies were empty.

   Recipes don't change this. The fixes are A28 (the server-side budget and the fallback text, measured here before FIX-10 merged) and A31 (`export_table`).
4. **The stage runs an older SOUL.**
   - The `demo` and `demo-prefiled` snapshots hold a 3,036-byte SOUL.md, and `demo-reset` restores it over `deploy/hermes/SOUL.md`: `restore_part` mirrors the snapshot and installs only `config.yaml`, `.env` and `cron/`.
   - So two Principles lines added since (the card line and the few-tools/draft line) and FIX-10's capabilities section don't reach the stage until the snapshots are refreshed. The running dev stack has the 3,036-byte file too.
   - These runs installed the worktree's `deploy/hermes/SOUL.md` explicitly.
5. **Skill descriptions are cut to 60 characters in Hermes' index** (`SKILL_PROMPT_DESC_LIMIT`).
   - A first B attempt with "Asks like …" descriptions loaded no skill in 13 turns. It was discarded, and the run used trigger-first descriptions of ≤ 60 characters.
   - Any future skill has to put its trigger words first.
6. **Telegram-only tools are offered on the web.**
   - `ingest_attachment` was called with made-up paths (`forbidden_path`) in A and B.
   - Hermes supports `mcp_servers.mona.tools.exclude`, so the web server entry could drop it.

## Configurations (spike stack only; none merged)

| Config | Change from `deploy/hermes` at the base commit |
|---|---|
| A | none (config.yaml and SOUL.md as committed) |
| B | `platform_toolsets.api_server: [memory, skills, mona]`; `skills.guard_agent_created: true` (`write_approval: true` and `project_discovery: false` are already set). `$HERMES_HOME/.no-bundled-skills` plus the bundled skill folders deleted (the manifest keeps them, so the sync treats them as user-deleted and doesn't restore them). The 4 recipes in `skills/mona/` |
| B0 | B with the profile's 53 bundled skills left in place: one greeting, prompt size only |
| C | A plus a `## Procedures for common asks` section appended to SOUL.md, generated from the same 4 recipe files (`s7_probe.py soul-c`) |
| D (extra) | A plus `agent.tool_use_enforcement: false` and `agent.execution_guidance: false` |
| CD (extra) | C plus D's two keys |

Each switch restored `memories/` from the snapshot and restarted Hermes, so every configuration started with a fresh process and a closed breaker.

**0.21.5 skill keys, checked in source.**
- `skills.write_approval` stages every `skill_manage` mutation under `pending/skills/`; `/skills approve` applies it.
- There is no agent-facing hub tool: hub installs are CLI-only (`hermes skills install`), so there is no hub key to turn off.
- `curator.enabled: false` and `auxiliary.background_review.enabled: false` are already set; they keep the background self-improvement off.
- The `skills` toolset is `skills_list`, `skill_view` and `skill_manage`, and there is no per-tool disable.
- The essential `hermes-agent` skill can't be disabled through `skills.disabled`. After deletion the sync recreates only its category folder, which holds no SKILL.md and isn't listed.

## Asks and ground truth

Fresh Hermes session per turn. The request is the adapter's: a `system` overlay from `build_overlay("/chat", "Chat page", <detected language>)` plus the user message. Ground truth came from direct MCP calls on the stage. The checks (amount and date patterns, expected arguments) are kept with the ask texts in `demo-data/spikes/s7/asks.yaml`.

| Ask | Recipe | Lang | Accepted path | Ground truth |
|---|---|---|---|---|
| due-1 | due-this-month | EN | `list_deadlines` | 1 deadline this month: `doc_01m3vtjrj4pq8391q1pm0pqb38`; must not list `doc_01m3vtp0ywt3pwy9qtpf2jbeze`, `doc_01m3vtp10yng37546521dsbkkr` (due next month) |
| due-2 | due-this-month (paraphrase) | FR | `list_deadlines` | same |
| owe-1 | owed-or-paid | EN | `search_documents` or `sum_amounts` | `doc_01m3vtp12yrdzr3mzkkz221ery`: amount and due date (2 more of that insurer's documents have no amount) |
| paid-1 | owed-or-paid (paraphrase) | EN | `sum_amounts` | total of 9 documents for one public body and one year, checked to the cent: `doc_01m3vtjrhveqaqrrw152qt5n8m`, `…hq8artawcwhw5j57c8`, `…hjkkk3dpd5mk724swt`, `…hd3aj9ra9vw2xegppm`, `…j0jtzaregn0wpeb5pz`, `…h7zb23y8m8tv0y2p72`, `…gvwcndc7dkyahqrb21`, `…h381k6txr1f6w8grpx`, `doc_01m3vtp10st46vdjjs7rp814gv` |
| draft-1 | draft-reply | FR | `search_documents → draft_reply` | `draft_reply(document_id=doc_01m3vtp0ywt3pwy9qtpf2jbeze)` |
| draft-2 | draft-reply (paraphrase) | EN | `search_documents → draft_reply` | `draft_reply(document_id=doc_01m3vtjrj4pq8391q1pm0pqb38)` |
| pack-1 | accountant-pack | EN | `export_accountant_pack` | company entity 1, FY 2024 (checked in the tool result) |
| pack-2 | accountant-pack (paraphrase) | RO | `export_accountant_pack` | company entity 2, FY 2025 |
| none-1 | none ("what needs my attention") | EN | `list_review_queue` | 9 in the queue; no skill should load |
| none-2 | none (find one bank's statements of a year) | EN | `search_documents` | `doc_01m3vtp13fbn4rtmsmhg89bqrj`, `doc_01m3vtp139w3t3whvf83hqchkc`, `doc_01m3vtp13498q1bn3q0n8hm9gp`; no skill should load |
| hard-1 (extra) | none | EN | — | no tool returns an IBAN or writes a CSV at the base commit |
| hard-2 (extra) | none | EN | — | no tool writes XLSX at the base commit |

"Correct" means a non-empty reply that passes the ask's text checks, with the expected tool called with the expected arguments or result. "Recipe path followed" counts the Mona tools, in order, against the accepted path; `skill_view` is not counted. "Right skill loaded" means `skill_view(<recipe>)` was called; for the `none` asks, it means no skill was loaded (6/6 in B).

## Results (10 asks × 3 reps per configuration)

### Prompt size: a one-word greeting

| Config | Prompt tokens per LLM call (each run) | System prompt chars | Skills listed | Skill-authoring guidance | "terminal" in the prompt |
|---|---|---|---|---|---|
| A | 8,993; 9,193 | 14,993 | 0 | no | yes |
| B | 10,695; 10,695 | 17,032 | 4 | yes | yes |
| B0 | 11,526 | 21,602 | 50 | yes | yes |
| C | 9,493; 9,493 | 17,007 | 0 | no | yes |
| D | 7,943; 7,943 | 10,213 | 0 | no | no |
| CD | 8,541; 8,443 | 12,227 | 0 | no | no |

The A system prompt, by section (characters):
- SOUL with the memory blocks: 4,136;
- Finishing the job: 770;
- Parallel tool calls and steering: 2,358;
- **Tool-use enforcement: 825**;
- **Execution discipline: 6,561**;
- runtime environment: 338.

B adds a `## Skills` block (3,052) and a Skill Safety Rule (353).

### Per configuration

| Config | Correct | Recipe path followed | Right skill loaded | Tool calls/turn (median, max) | Mona calls/turn | Turns ≤ 2 calls | LLM calls/turn | Prompt tokens/turn (median) | Prompt tokens/LLM call | First text s (median) | Close s (median, max) | Empty replies | Wrong language |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 30/30 | 17/24 | n/a | 1, 3 | 1 | 25/30 | 2 | 18,631 | 9,269 | 4.7 | 5.9, 12.9 | 0 | 0 |
| B | 30/30 | 13/24 | 4/24 | 2, 7 | 1 | 24/30 | 2 | 22,417 | 11,034 | 3.9 | 5.3, 18.0 | 0 | 1 |
| C | 30/30 | 19/24 | n/a | 1, 3 | 1 | 28/30 | 2 | 19,634 | 9,735 | 4.8 | 6.0, 10.9 | 0 | 0 |
| D | 30/30 | 18/24 | n/a | 1, 3 | 1 | 26/30 | 2 | 16,501 | 8,250 | 3.1 | 3.6, 10.0 | 0 | 0 |
| CD | 29/30 | 20/24 | n/a | 1, 3 | 1 | 27/30 | 2 | 17,372 | 8,686 | 2.8 | 3.3, 8.3 | 0 | 2* |

\* One of the two is a false positive: an English reply quoting French document titles. The real ones (B and CD, both pack-1) are English asks answered in French, the A29 failure. It also happened once in an A smoke run that isn't counted.

First reasoning token: median 0.68–0.81 s in every configuration. Prompt-cache hits (OpenRouter `cache_read`): 86–91% of the prompt tokens.

### Per ask (correct / 3; tool calls per rep; median close)

| Ask | Recipe | A | B (skill loaded per rep) | C | D | CD |
|---|---|---|---|---|---|---|
| due-1 | due-this-month | 3/3; 1,1,1; 3.9 s | 3/3; 2,2,2 (−,+,+); 4.8 s | 3/3; 1,1,1; 3.4 s | 3/3; 1,1,1; 3.5 s | 3/3; 1,1,1; 3.1 s |
| due-2 | due-this-month | 3/3; 1,1,1; 4.9 s | 3/3; 1,1,1 (−,−,−); 5.1 s | 3/3; 1,2,1; 3.9 s | 3/3; 1,1,1; 3.1 s | 3/3; 1,1,1; 3.3 s |
| owe-1 | owed-or-paid | 3/3; 1,2,1; 6.1 s | 3/3; 3,2,2 (−,−,−); 7.2 s | 3/3; 1,2,1; 7.2 s | 3/3; 1,2,2; 4.6 s | 2/3; 1,1,1; 2.7 s |
| paid-1 | owed-or-paid | 3/3; 2,1,1; 9.4 s | 3/3; 1,2,2 (−,−,−); 10.7 s | 3/3; 1,2,1; 4.1 s | 3/3; 1,2,1; 3.1 s | 3/3; 1,1,2; 3.0 s |
| draft-1 | draft-reply | 3/3; 2,3,3; 10.7 s | 3/3; 2,3,7 (−,−,−); 14.8 s | 3/3; 2,2,2; 7.1 s | 3/3; 2,2,2; 5.9 s | 3/3; 2,2,2; 4.8 s |
| draft-2 | draft-reply | 3/3; 3,3,3; 9.6 s | 3/3; 4,3,4 (−,−,−); 14.5 s | 3/3; 3,3,2; 6.6 s | 3/3; 3,3,3; 7.4 s | 3/3; 3,3,3; 6.1 s |
| pack-1 | accountant-pack | 3/3; 1,1,1; 5.2 s | 3/3; 1,1,1 (−,−,−); 2.9 s | 3/3; 1,1,1; 6.5 s | 3/3; 1,1,1; 2.7 s | 3/3; 1,1,1; 2.5 s |
| pack-2 | accountant-pack | 3/3; 1,1,1; 3.7 s | 3/3; 1,2,2 (−,+,+); 4.4 s | 3/3; 1,1,1; 5.3 s | 3/3; 1,1,1; 3.0 s | 3/3; 1,1,1; 3.0 s |
| none-1 | none | 3/3; 2,2,1; 8.0 s | 3/3; 1,1,2 (none: ok); 3.7 s | 3/3; 1,1,1; 7.8 s | 3/3; 1,1,1; 2.7 s | 3/3; 1,1,1; 4.0 s |
| none-2 | none | 3/3; 1,1,1; 4.6 s | 3/3; 1,1,1 (none: ok); 3.8 s | 3/3; 1,1,1; 3.6 s | 3/3; 1,2,3; 4.6 s | 3/3; 1,1,1; 2.7 s |

The paraphrase asks that most need a procedure are the drafts. In A, draft-1 took a detour through `list_review_queue` in 2 of 3 reps. In B, draft-1 took 7 calls once and draft-2 fetched `get_document` before the draft (twice), against the recipe. In C, draft-1 was 2 calls every time. draft-2 searches twice in almost every rep, because the first search has no subject word.

### Extra: asks beyond Mona's tools (3 reps each)

| Ask | A | B | C | D | CD |
|---|---|---|---|---|---|
| hard-1 | calls 38, 6, 16; 71, 14, 36 s; tool errors 15 (breaker 12) | calls 30, 27, 8; 78, 39, 14 s; errors 12 (8) | calls 21, 17, 6; 29, 32, 9 s; errors 24 (20) | calls 12, 7, 10; 23, 14, 33 s; errors 29 (25) | calls 35, 12, 6; 39, 28, 10 s; 1 empty; errors 20 (15) |
| hard-2 | calls 9, 8, 23; 31, 16, 60 s; errors 15 (9) | calls 13, 21, 14; 62, 86, 111 s; 1 empty; errors 9 (2) | calls 21, 8, 11; 37, 14, 27 s; errors 14 (13) | calls 5, 6, 6; 11, 15, 20 s; errors 17 (17) | calls 12, 5, 5; 28, 10, 18 s; errors 10 (10) |

**Error kinds over all 30 hard turns:**
- breaker refusals: 131;
- `invalid_argument`: 29;
- calls to tools that don't exist: 4 (A 2, B 1, C 1; D and CD 0);
- `forbidden_path` from `ingest_attachment`: 4 (A 1, B 3);
- `skill_manage` misuse: 5 calls in B.

**How the 30 replies ended** (read by hand):

| | A | B | C | D | CD |
|---|---|---|---|---|---|
| "the archive server is down / rejecting calls" (false: the breaker) | 3 | 1 | 2 | 6 | 4 |
| announced a next step and stopped (12 LLM calls, the iteration cap) | 1 | 2 | 2 | 0 | 1 |
| empty | 0 | 1 | 0 | 0 | 1 |
| answered within the limits (a table in the text with "no file tool", "no IBAN field", or a clarifying question) | 2 | 2 | 2 | 0 | 0 |

D's short loops come from the breaker, not from better behaviour: 5 of its 6 hard turns met an open breaker on the first call. The hard-ask rows therefore say little about D.

### Cost

| | A | B | C | D | CD |
|---|---|---|---|---|---|
| Hermes' estimated cost, 30 asks | $0.054 | $0.068 | $0.056 | $0.046 | $0.047 |
| per turn | $0.0018 | $0.0023 | $0.0019 | $0.0016 | $0.0016 |
| hard asks, per turn | $0.012 | $0.017 | $0.011 | $0.005 | $0.008 |

OpenRouter usage delta for the whole spike: **$0.63** (budget $1). It includes the discarded first B attempt, the smoke turns and the background drafts on the flash model.

On mona (local llama.cpp), prompt tokens are prefill. B costs +1.7k tokens on every LLM call, plus a whole extra call (≈ 11k tokens) for every skill it loads. C costs +0.5k per call. D saves 1.05k per call.

## Caveats

- **Sample size:** 3 reps per ask. Differences of 2–3 turns out of 24–30 are within noise; the skill-load rate (4/24) and the prompt sizes are not.
- **Latency:** the configurations ran one after another over about 2 hours on shared OpenRouter providers. The time to first text mostly reflects provider load, so the faster D/CD numbers are suggestive, not proven.
- **The harness bypasses Mona's chat route.** No `chat_turns` row is open, so cards aren't attributed to a turn. It also means FIX-10's turn budget wouldn't apply, which doesn't matter here because the base commit predates FIX-10. The overlay and the reply language are the adapter's.
- **Prompt tokens vary run to run** (±300 for the same configuration), probably because of the date line and the provider.

## Reproduce

```sh
# stack: compose project mona-s7, Qwen 3.6 for Hermes
export COMPOSE_PROJECT_NAME=mona-s7 WEB_PORT=7873 API_PORT=11165 POSTGRES_PORT=57832 HERMES_PORT=11042 \
       MONA_CHAT_MODEL=qwen/qwen3.6-35b-a3b MONA_COMPOSE="docker compose -p mona-s7"
mkdir -p data/snapshots && cp -a ~/DevFiles/mona-hq/mona/data/snapshots/demo-prefiled data/snapshots/
docker compose -p mona-s7 up -d --build postgres api worker-llm worker-cpu hermes
deploy/bin/mona demo-reset --prefiled --anchor today --yes
# per configuration
docs/spikes/s7/switch.sh B
cd apps/api && .venv/bin/python ../../docs/spikes/s7/s7_probe.py baseline --config B
.venv/bin/python ../../docs/spikes/s7/s7_probe.py run --config B --reps 3
.venv/bin/python ../../docs/spikes/s7/s7_probe.py report   # tables; `csv` writes results/turns.csv
```

## Files

- `recipes/`: the 4 curated recipes (SKILL.md) and the category description. B installs them; C appends them to SOUL.
- `switch.sh`: installs a configuration into the `mona-s7` Hermes profile and restarts Hermes.
- `s7_probe.py`: runs the asks, grades them, and writes the report and the CSV. Raw turns, reply texts included, stay in `demo-data/spikes/s7/`.
- `results/turns.csv`: one row per turn (ids, tool names and numbers; no reply text).
