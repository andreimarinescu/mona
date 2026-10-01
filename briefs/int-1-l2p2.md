# INT-1: integrate L2-P2 onto main (finish the in-progress rebase)

Card **INT-1**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l2-p2`, branch `l2-p2`. **A rebase is in progress there:** L2-P2 is squashed into one commit, being replayed onto `main`. 14 files conflict.
- **Exception to the standing rules:** for this card you **may** finish this one rebase (`git add` + `GIT_EDITOR=true git -c commit.gpgsign=false rebase --continue`). Nothing else: no new rebases, no push, no fetch.
- **Compose project:** `-p mona-l2`. Export `WEB_PORT=5173 API_PORT=8765 POSTGRES_PORT=55432 HERMES_PORT=8642` in your shell. **Never edit `.env`** (D11).

`main` gained L1-M2 (pipeline, `mona.llm`-style model client in `mona/pipeline`), L1-M3 (hooks, purge, rule revert in `services/undo.py`), L4 (interviews, `mona/workflow`, its own server i18n catalog with formatting helpers, routers in the app) and L3-S1/S2 (web), while L2-P2 built auth, the C2 REST surface, MCP write tools, prod lockdown and *its* server catalog. Your job: one integrated tree that keeps **both sides' behaviour**, with `make check` green.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D14; D11 ownership).
- `docs/contracts/amendments.md`.
- **The two reports:** `~/DevFiles/mona-hq/orchestrator/reports/l2-p2-report.md` (its merge notes: the LLM guard wiring, worker logging, A12 shape) and `l4-report.md`.
- `~/DevFiles/mona-hq/orchestrator/l4-merge-notes.md`.
- The contracts as needed: C2 §1.2 (one error envelope), C8 §1.1 (one server catalog, i18next semantics, a key lives in exactly one catalog), C9 §1.2 (one LLM client, fail closed).

## Resolve

1. **`app.py`.** It must have:
   - L2-P2's error envelope (`install_errors`), `ApiGuard`/`RequestLog`, the auth router and `configure_logging`;
   - `main`'s lifespan with `pipeline_startup` (recovery + hooks) composed with the MCP lifespan;
   - L4's `interviews` and `workflow` routers;
   - `separate_input_output_schemas=False`.

   L4's `mona/workflow/common.py` imports `ApiFailure, ErrorBody` from `mona.chat.router`, but `ErrorBody` no longer exists there. Point it at `mona.api.errors` (`ApiError` is the envelope model).
2. **Server i18n:** **one** module and one catalog per language.
   - Keep L2-P2's i18next semantics (`{{name}}`, plurals, contexts) and L4's formatting helpers (months, money, comma-below, NBSP).
   - Deep-merge the JSON catalogs. Any key present in both with different text: keep C8's wording, and list it in the report.
   - Both sides' tests pass against the merged module.
3. **`settings.py`, `cli.py`, `jobs.py`:** union of both sides (L2-P2's settings, `profile set-password`, `check-prod`; `main`'s `mona worker`, pipeline, purge, hermes commands and periodic jobs).
4. **`mcp/read.py`, `tests/test_mcp_server.py`:** keep A12 (`documents: [{id, title}]` for the first 10, `truncated`) and `main`'s changes.
5. **`conftest.py`:** both sides' fixtures, with lane-prefixed names (D11).
6. **Generated files:** regenerate rather than hand-merge:
   - `apps/api/openapi.json` via `mona openapi`;
   - `apps/web/src/api/schema.gen.ts` via `npm run gen:api -w apps/web`;
   - `tests/fixtures/hermes/surface.json` re-captured as its test explains (needs the stack). If the capture needs Hermes, run it on `-p mona-l2`.
7. **L2-P2's merge notes:**
   - `LlmClient.from_settings` in L1-M2's client passes `base_url=mona.llm.endpoint(s).base_url` and `http_client=mona.llm.guarded_http_client(s)` (fail closed in prod);
   - `mona worker` calls `configure_logging()`;
   - `UndoResult.ruleStates` maps from L1-M3's `rule_states` (C2 shape).

## Acceptance (fresh output in the report)

- The rebase finished: `git log --oneline main..HEAD` shows one L2-P2 commit, plus fixups if you made them.
- `make check COMPOSE="docker compose -p mona-l2"` exit 0, with the Python and web test counts.
- The live e2e (cheap model, `MONA_LIVE=1`) on `-p mona-l2` still passes 5/5. Run `mona seed load` with the fixture seed and the live fixtures as in L2-P1's report.
- The C9 prod-guard test: in prod settings, a model call to a non-local endpoint is refused.
- The report lists every conflict and how it was resolved, and every i18n key collision.

## Don't

- No new features.
- No contract changes.
- Never edit `.env`.
