# FIX-16 R: `mona chat-replay`, the probe that measures chat thinking on the local model

Card **FIX-16-R**. Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-16-r`, branch `fix-16-r`, on top of `bugfixes`.
- **Compose project:** `-p mona-fix16r`. Export `WEB_PORT=7995 API_PORT=11285 POSTGRES_PORT=57955 HERMES_PORT=11165 E2E_PORT=5195`. Never edit `.env`.

**Read first:**
- `briefs/common.md`;
- amendments **A57, A58**;
- C3 §4.1–§4.2 (the upstream request and the overlay); C9 §7 (what logs and reports may hold);
- `docs/decisions.md` **D9, D15, D23**.
- Code:
  - `apps/api/src/mona/cli.py` (Typer; the `ops` sub-app as the pattern);
  - `deploy/bin/mona` (how `mona <cmd>` reaches the `ops` container: `/hermes` is Hermes' data, `/data` Mona's, `/hermes-seed` the repo's `deploy/hermes`);
  - `chat/overlay.py` (`build_overlay`);
  - `mcp/server.py` and `mcp/core.py` (the tool registry);
  - `i18n` (`detect_language`);
  - `perf.py` (an existing streaming probe);
  - `llm.py` (the guarded client: use it, so prod's fail-closed host check applies).

## What it is for

The orchestrator runs it **on the mona box**, then again at every later release. It ships with the release, so both runs happen right after the deploy:
- **Baseline:** the recorded turns as they were: stored prompt, `--no-extra`, no `--cut`.
- **After:** `--system` set to a prompt stored after the release, `--extra-from` the installed config, and `--cut`.

It replays recorded chat turns many times **directly against llama-swap**, with or without A57's sampling and thinking budget, and reports how often the model acts and how long it thinks. It never executes a tool and never writes to Mona or Hermes.

## Do

1. **`mona chat-replay build --session <id> --turn <n> [--turn …] --out <dir>`.**
   - Read Hermes `state.db` read-only (default `/hermes/state.db`, flag `--hermes-db`).
   - One scenario per selected user message, a JSON file holding:
     - the system prompt Hermes stored for the session (`sessions.system_prompt_hash` → `system_prompts`);
     - the overlay rebuilt with `build_overlay("/chat", "Chat", <reply_language of that turn in chat_turns>)`;
     - every message before the selected one, converted to OpenAI chat format (assistant `tool_calls` and `tool` results as stored);
     - the selected user message;
     - the tool list: Mona's MCP tools from the in-process registry as Hermes names them (`mcp__mona__<name>`, description, input schema), minus Hermes' web exclusion (`ingest_attachment`).
   - Hermes' own `memory` tool is not included; say so in `--help`.
   - Scenario files hold practice data: `--out` is required, and the command refuses a path inside the repo.
2. **`mona chat-replay run --scenarios <dir> --runs N [--extra-from <hermes config>] [--extra '<json>'] [--no-extra] [--cut <path to cut.py>] [--system <file>] [--max-seconds 150] [--out <dir>] [--keep-text]`.**
   - **Request:** `POST {base}/chat/completions` with `stream: true`. Base URL and model come from `mona.llm.endpoint()`: prod gives llama-swap; dev gives OpenRouter with its key, since `MONA_LLM_BASE_URL` is unset in dev.
   - **Messages, as Hermes sends them:** **one** leading system message, `(prompt_after_cut + "\n\n" + overlay).strip()`, then the history and the user message. `--system <file>` replaces the stored prompt before the cut.
   - **Extra body:**
     - `--extra-from` (default `/hermes/config.yaml`): reads the `custom_providers` entry's `extra_body` and merges it into the body;
     - `--extra` overrides keys;
     - `--no-extra` sends none (the baseline).
   - **`--cut`:** loads `cut_system_prompt(text) -> (text, removed)` from that file (FIX-16-H writes it at `deploy/hermes/plugins/mona_prompt/cut.py`; in your worktree, test with a stub of that signature) and applies it to the stored system prompt.
   - **Per run, record:**
     - reasoning characters, and reasoning tokens when the usage says;
     - content characters;
     - tool-call names;
     - `acted` (any tool call or non-blank content);
     - seconds to first reasoning and to the first act;
     - total seconds;
     - `runaway`: no act within `--max-seconds`, or one line of at least 40 characters repeated 5 times in the reasoning (A58's normalisation; at the merge the orchestrator may switch this to FIX-16-W's module);
     - whether the reasoning ends with the injected budget message;
     - the reply language (`detect_language`).
     - Cut a run at `--max-seconds` by closing the stream.
   - **Output:** `summary.json` plus a short `summary.md`. Per scenario: n, acted, runaway, p50/p95/max of reasoning tokens, of reasoning seconds and of seconds to act, a tool-name histogram, a language histogram. Plus the run settings (the extra body, whether the cut was used), the model id and the llama-server build (`/props` if available).
   - **Counts only:** the summary holds no message text, tool argument or reasoning. `--keep-text` writes texts to `<out>/texts/` only, for the private run directory.
   - Runs are sequential.
3. **Synthetic scenarios** in `apps/api/tests/fixtures/replay/`: six fictional ones. They hold `system: {"soul": true}`, an overlay language, and **no tool list**. At run time, `run` fills the prompt from `deploy/hermes/SOUL.md` (`/hermes-seed/SOUL.md` in the ops container) and the tools from the in-process registry, so they always replay the current SOUL and tools. They mirror D23's failures:
   - a "mark it paid" ask after a brief result;
   - a "What app?" follow-up;
   - a Romanian watched-folder ask;
   - a Romanian rename-to-a-pattern ask over fictional statements;
   - a bare "confirm";
   - a plain "what's due this month" as the control.
   - They must replay on any OpenAI-compatible endpoint, e.g. the dev OpenRouter key with `--no-extra`.
4. **Tests** (no network):
   - `build` from a synthetic `state.db` fixture plus a test DB row;
   - `run` against a fake streaming endpoint (httpx `MockTransport`) covering: reasoning-only runaway, repeat runaway, a tool call, content, a budget message at the end of the reasoning;
   - `--extra-from`, `--extra` and `--no-extra` merging;
   - `--cut` loading;
   - **the summary holds none of the fixture texts** (assert on strings planted in the fixtures);
   - `--out` inside the repo is refused: in the ops container that means `/app`, `/hermes-seed` and `/seed` too.
   - Fixture names must pass `scripts/no-practice-names.py`. Don't use demo-seed names such as "Hello bank" in `tests/fixtures/replay/`; invent new fictional ones.

## Acceptance (fresh output in the report)

- `make check` and `make ci-py` green; `make e2e` no worse than 129 passed / 19 skipped.
- The tests above.
- One real run of the synthetic set on your dev stack (OpenRouter, the cheap model, `--no-extra`, `--runs 2`): `summary.md` in the report, plus the spend.

## Don't

- No writes to Mona's DB, Hermes, or any file outside `--out`. No tool execution.
- Don't touch the Hermes configs or plugin (FIX-16-H), the adapter (FIX-16-W), SOUL or `detect_language` (FIX-16-S).
- Never edit `.env`. Don't touch the mona box (the orchestrator runs it there).

Report: `~/DevFiles/mona-hq/orchestrator/reports/fix-16-r-report.md`.
