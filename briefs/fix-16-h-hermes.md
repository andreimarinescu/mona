# FIX-16 H: chat sampling, thinking budget and the `mona_prompt` Hermes plugin (A57)

Card **FIX-16-H**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-16-h`, branch `fix-16-h`, on top of `bugfixes` (main plus the FIX-16 orchestration commit).
- **Compose project:** `-p mona-fix16h`. Export `WEB_PORT=7991 API_PORT=11281 POSTGRES_PORT=57951 HERMES_PORT=11161 E2E_PORT=5191`. Never edit `.env`.

**Read first:**
- `briefs/common.md`;
- amendments **A28, A33, A57**, plus C9 §4.1's check A5 (`privacy.py` `hermes_config_problems`);
- C9 §4 and §6.5; C4 §1.3;
- `docs/decisions.md` **D18, D20, D23**.
- In the repo: `deploy/hermes/` (both configs), the `hermes-seed` services in `compose.yaml` and `deploy/compose.prod.yaml`, `apps/api/src/mona/privacy.py` (`hermes_config_problems`), `apps/api/src/mona/doctor.py`, `deploy/bin/doctor-host`, and demo-reset's Hermes install (grep `MONA_HERMES_SEED`).
- **Hermes source**, in the pinned image (`nousresearch/hermes-agent:v2026.9.24@sha256:fca358…`, under `/opt/hermes`). Read it with `docker run --rm --entrypoint sh <image> -c 'sed -n …'`:
  - `hermes_cli/middleware.py` (`llm_request` middleware) and `hermes_cli/plugins.py` (`register_middleware`, plugin discovery, `plugins.enabled`, user plugins under `$HERMES_HOME/plugins`);
  - `agent/system_prompt.py` (`build_system_prompt_parts`, `_guidance_parts`, `_post_workspace_parts`);
  - `agent/prompt_builder.py` (`RUNTIME_ENVIRONMENT_HEADING`/`_END`, `HERMES_AGENT_HELP_GUIDANCE*`, `STEER_CHANNEL_NOTE`, `WSL_ENVIRONMENT_HINT`, `_remote_backend_hint`);
  - `agent/agent_init.py` (`_apply_agent_section`, `_custom_provider_extra_body_for_agent`).

## Do

1. **Config (A57 items 1–2).**
   - `config.prod.yaml`: the `custom_providers` entry and its `extra_body` exactly as A57.
   - Both configs: the three `agent.*` switches, `platform_hints.api_server.replace`, and `plugins.enabled: [mona_prompt]` (the exact key shape the pinned image reads).
   - Also update C9 §4.1's table in your report's "contract text to fold" list. Don't edit the contracts.
2. **Plugin (A57 item 3).** `deploy/hermes/plugins/mona_prompt/`, with the manifest and layout the pinned image's discovery expects.
   - **Put the cut in its own module** `cut.py`, exposing `cut_system_prompt(text: str) -> tuple[str, list[str]]` (the new text, plus the names of the sections removed). It must have no Hermes or Mona imports: FIX-16-R and the prompt check load this file by path.
   - The plugin's `llm_request` middleware applies `cut_system_prompt` to the system message(s) of each request and leaves everything else byte-identical.
   - A shape it doesn't recognize is left whole, with one warning per process.
   - Cut every section A57 item 3 lists. That includes `# Finishing the job`, `# Parallel tool calls` and the default api_server hint, because conversations started before the release keep their stored prompt (`conversation_loop.py` ~681-753).
   - Build fixtures from the pinned image's real prompt text: render the system prompt the image builds for the prod config, both with and without the WSL hint, plus the docker-remote variant.
3. **Check A5 (A57 item 4).** `hermes_config_problems` expects every new key and value, plus the `custom_providers` entry's `base_url` equal to `model.base_url` and no `model` key. Tests go in the style of the existing ones.
4. **Capture test.** An automated test that runs the pinned Hermes image with `config.prod.yaml`, the plugin and `SOUL.md`. Point `MONA_LLM_BASE_URL` at a small capture server that answers like an OpenAI-compatible streaming endpoint. Send one `/v1/chat/completions` request to Hermes' API server, then assert on the captured upstream request:
   - `presence_penalty`, `reasoning_budget_tokens` and `reasoning_budget_message` are present;
   - the system message contains SOUL's first line and none of A57's markers;
   - the plugin is loaded.
   - If Hermes needs the MCP server to start a turn, stub it or let it degrade. Report how.
   - Also a **render test, for both configs, with no turn**: have the pinned image build the system prompt and run the prompt check on it. The dev config is pinned to OpenRouter, so never send a real turn with it.
   - It must run in `make check` and in the CI py job (CI has docker). It must fail rather than skip when the image is missing locally: pull it.
5. **Prompt check in `mona doctor` (A57 item 4).** Extend `deploy/bin/doctor-host` or the doctor flow.
   - Read the prompt of the newest web session, read-only (`file:…?mode=ro`), via `docker exec` on the Hermes container: `sessions` (source = the api_server value) ordered by `started_at`, joined on `system_prompt_hash` → `system_prompts`.
   - Apply `cut.py` and fail on any of A57's exact markers. Also check that Hermes lists the plugin as loaded.
   - With no web session started since the installed `config.yaml`'s mtime, warn "no conversation since the release" and keep the plugin check.
   - Output names markers and sections only, never prompt text (C9 §7).
   - The checker itself is a pure Mona function, shared with the tests.
6. **Seeding (A57 item 5).**
   - Both `hermes-seed` services install `SOUL.md`, the config and `plugins/mona_prompt/` on every start (owner and mode as today).
   - demo-reset installs the plugin too.
   - demo-reset's restore (`demo/hermes.py`, `restore_part` mirrors with `--delete` everything except `INSTALLED`) must keep `/plugins/`.
   - Install the plugin read-only (root-owned, 0644 files) so no `__pycache__` lands next to it and the Hermes fingerprint (`fingerprint.py`) doesn't drift. Otherwise add `plugins/*/__pycache__` to its `RUNTIME` skip list; report which.
   - Memories and sessions are untouched.
   - Test it the way the existing seed and reset behaviour is tested.

## Acceptance (fresh output in the report)

- `make check` and `make ci-py` green; `make e2e` no worse than 129 passed / 19 skipped.
- The capture test, the `cut.py` unit tests (both WSL variants) and the A5 tests.
- **Mutations:**
  - plugin disabled in the config → the capture test goes red;
  - one `extra_body` key removed → A5 and the capture test go red;
  - `cut.py` returning its input → the unit tests go red.
- The doctor check's output on your stack, before and after one chat turn.
- **For the orchestrator's integration:** `cut.py`'s exact path and signature, and the marker list, in the report.

## Don't

- Don't touch `SOUL.md`'s wording (FIX-16-S owns it), the chat adapter, or llama-swap's config.
- Never add `--reasoning-budget` to llama-server.
- No other Hermes behaviour changes, and no showcase-only code (D16).
- Never edit `.env`. Don't touch the mona box.

Report: `~/DevFiles/mona-hq/orchestrator/reports/fix-16-h-report.md`.
