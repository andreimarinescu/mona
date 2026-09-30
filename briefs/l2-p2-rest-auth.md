# L2-P2: auth, the REST API, write tools, prod lockdown

Card **L2**, phase 2. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l2-p2`, branch `l2-p2`, based on `main`.
- **Compose project:** `-p mona-l2`, with default ports (5173 / 8765 / 55432 / 8642). `make check COMPOSE="docker compose -p mona-l2"`.

Phase 1 (on `main`) built the chat adapter, the MCP server and six read tools, and the Hermes profile. Phase 2 is the rest of the backend the web and Mona need, **except** the intelligence vertical (interviews, deadlines and reminders, drafts, exports), which L4 builds end to end in parallel, including its endpoints and tools. Intake upload and `ingest_attachment` come in a small follow-up card once L1-M2's `mona.pipeline.intake` lands.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D10; D5 actor, D9 cheap model).
- `docs/contracts/amendments.md` A1–A13 (A5 `ses` prefix, A9 `debrief_early_min`, A12 `sum_amounts` titles, A13 mounts).
- **Contracts:**
  - **C2 in full**, except §10–§12 (L4's) and §5 (the follow-up card);
  - **C9 §1, §2, §3, §4, §7** (your parts: `mona.llm` checks, the prod assertion, visibility, the Hermes lockdown, secrets and logs);
  - C8 §1.1 (the server catalog), §5.3/§5.4/§5.7;
  - C4 §3.5, §3.8, §3.9, §3.16 (write tools) and §3.3 (A12);
  - C1 §11 (DTOs).
- **Code on `main`:** `mona/services/README.md` (L1-M1 services: call them, never reimplement), `mona/chat`, `mona/mcp`, `mona/dto`.
- **Notes:** `~/DevFiles/mona-hq/orchestrator/l2-p2-notes.md`, and the fold reports' "also needed on set A lanes" lists (`~/DevFiles/mona-hq/orchestrator/reports/w1-contracts-b-fold-report.md`).

## Build, in this order (Tier A first)

1. **Migrations:**
   - `auth_sessions` (C2 §2.2 DDL);
   - `settings.debrief_early_min` (A9);
   - the seed loader gains `practice.debrief_early_min` and `practice.auto_lock_minutes` (C9 §6.7).
2. **Auth and middleware** (C2 §2, §2.7): unlock with argon2, sessions, CSRF with the `Origin` check, the lock with 423 on reads and writes, auto-lock, lock/logout, the exception list exactly as §2.7 states, body limits before auth. The service key only on `/mcp` (§2.6).
3. **Errors and conventions** (C2 §1): one envelope, lists, idempotency, polling. Align `/api/chat`'s pre-stream errors with the envelope (C3's 400 stays).
4. **REST** (C2 §3, §4, §6, §7, §8, §9, §13, §14, §15):
   - shell and Home;
   - documents: archive search, detail, files through the viewer deep link (`/api/documents/{id}/pdf`: the cached OCR'd copy, else the archive bytes resolved at request time, with the guard), folders;
   - review and document actions (corrections call `correct_document`);
   - rules: list, detail, preview/apply, enable/disable, calling L1 services;
   - registry;
   - journal, activity, undo/redo;
   - conversations;
   - card actions that write C3 notes;
   - settings and system status.
   - Regenerate the OpenAPI → TS client (C2 §16).
5. **Write MCP tools** (C4 §3.5, §3.8, §3.9, §3.16): thin wrappers over L1's services, with the actor per D5 and cards per C3. `sum_amounts` gets titles (A12).
6. **Prod and ops** (C9):
   - `deploy/hermes/config.prod.yaml` (custom provider → llama-swap, auxiliary pinned, `agent.disabled_toolsets` backstop, no OpenRouter);
   - the prod assertion (§2.1) as `mona check-prod` plus a test;
   - a `mona.llm` guard: model calls fail closed in prod unless the endpoint is the configured local one. Extend the client L1-M2 is writing if it has landed on `main`, else add the guard as a function L1 can call, and say which in the report;
   - log redaction; uvicorn `--no-access-log`; Postgres `log_error_verbosity=terse`; `MONA_ENV` with no default;
   - the SOUL memory-policy line (C9 §3.4) and a SOUL line: "never show internal ids (`doc_…`); name documents by title";
   - the narrower mounts (A13);
   - the server i18n catalog (C8 §1.1) for `review.sentence.*`, errors and auth strings.

## Acceptance (fresh output in the report)

- `make check` green; the OpenAPI client is fresh.
- **C2 §17 test obligations** for everything above, with every [M] mutation-checked (at least: the session check moved into a route dependency, CSRF skipped, 423 on reads removed, the §2.7 exceptions widened, the deep-link path guard).
- **C4 §5** for the write tools; **C9 §8** for the prod assertion and visibility.
- **Live e2e** (cheap model, `MONA_LIVE=1`) still 4/4, plus one new beat: "move the URSSAF letter to the SCI" via chat → `correct_document`, a card, and an undo that restores it.
- Report the OpenRouter spend delta.

## Don't

- No interviews, deadlines and reminders, drafts or exports (L4); no upload or `ingest_attachment` (the follow-up card).
- No web screens (L3).
- No contract changes: stop and report.
