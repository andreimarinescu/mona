# INT-3: integration cleanup

Card **INT-3**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/int-3`, branch `int-3`, based on `main`.
- **Compose project:** `-p mona-int3`. Export `WEB_PORT=6373 API_PORT=9665 POSTGRES_PORT=56332 HERMES_PORT=9542` (never edit `.env`).

The parallel lanes left a few seams. Close them without changing behaviour that the contracts fix. Each item below names where it came from; read that report section.

## Read first

- `briefs/common.md` and `docs/decisions.md`.
- `~/DevFiles/mona-hq/orchestrator/reports/{l4,int-1,l2-p2,l1-m2,l1-m3,l3-s3,l3-s4,l5c}-report.md`, the sections named below.

## Do

1. **One `findQuery`** (C5 §7 + A15): L4's `interviews/compile.find_query` becomes a call to L1's implementation (`l4-report` question 2). Keep L4's tests and point them at L1's.
2. **`LlmClient` public API** (`l4-report`, "Model client internals"): L1-M2's client gains public `stream(...)` and `complete_json(...)`; L4's interview binding uses them instead of subclassing internals. The prod guard wiring from INT-1 stays.
3. **Logging:** every CLI entry point (`pipeline run`, `purge-visitors`, `seed load`, `ops …`) calls `configure_logging()` (`int-1-report`).
4. **Error declarations:** L4's routes declare the guard's statuses (401/423, plus 403/415 on writes) like L2-P2's routes; regenerate OpenAPI and the TS client (`int-1-report`).
5. **One deadlines query:** the REST list and the MCP tool share L2-P2's visibility-filtered query (C9 §3), so web and Telegram behave the same, with tests (`int-1-report`).
6. **Web dependencies:** remove `@assistant-ui/*` if nothing imports it (`l3-s3-report` question 1). The C3 rendering mapping is unchanged; leave the contract wording to the orchestrator.
7. **E2E robustness:** `make e2e` and the CI e2e job run Playwright with `--workers=2` (`l3-s2`, `l3-s4` reports).
8. **The web container runs as the host user** (`MONA_UID`/`MONA_GID`) like the Python ones, and `node_modules` mountpoints stay host-owned after `make up` (`l1-m3-report`).
9. **The D12 guard on mocks:** older web mocks use names that match seed counterparties (e.g. "Personnel"). Rename them to fictional ones, and extend `scripts/no-practice-names.py` to also scan `apps/web/src/mocks` and the API test fixtures **excluding** the demo fixtures that legitimately carry the seed (`demo-overlay.yaml`, `synthetic.json`, `model_outputs.json`). Product words such as "Visitors" stay exempt (`l3-s3-report` question 3, `l5c-report`).

## Acceptance (fresh output in the report)

- `make check` green (Python and web counts).
- `make e2e` green at 2 workers.
- For each item: the change and the test that pins it.
- Mutation: break item 5's shared query (drop the visibility filter) → a Telegram-channel test fails.

## Don't

- No behaviour changes beyond the items; no contract changes; never edit `.env`.
