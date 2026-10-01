# L2-P3: intake upload, batches, `ingest_attachment`

Card **L2**, phase 3. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l2-p3`, branch `l2-p3`, based on `main`.
- **Compose project:** `-p mona-l2c`. Export `WEB_PORT=6273 API_PORT=9565 POSTGRES_PORT=56232 HERMES_PORT=9442` in your shell (D11: **never edit `.env`**). For live/browser specs, use `E2E_BASE_URL=http://localhost:6273`; `MONA_PUBLIC_ORIGIN` must match the browser origin, or writes get 403.

This closes the minimum viable demo's first step, **web upload → pipeline**, and the Telegram/attachment path for later. L1-M2's intake service (`mona.pipeline.intake.ingest_file`) and the whole backend are on `main`.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D14, D11 ownership).
- `docs/contracts/amendments.md`.
- **Contracts:**
  - C2 §5 (upload `POST /api/intake`: limits before the body is read, per-file results such as duplicate with restore, unsupported, empty, unreadable; the visitor flag; batches `GET /api/batches/{id}` with the polling shape of §1.5, the debrief summary, counts), §2.7 (enforcement order), §17 tests 5 and 16;
  - C4 §3.14 (`ingest_attachment`) and §4.2 with A13 (the path guard: realpath, trailing slash, `O_NOFOLLOW` and per-component `openat`, FIFO-safe, copy and never move);
  - C7 §8.4 (dedupe);
  - C9 §5 (visitor batches).
- **Code on `main`:** `mona/pipeline/intake.py` and `services/README.md` (Pipeline section), `mona/api/` (guard, errors, auth patterns from L2-P2), `mona/mcp/` (tool conventions, cards).
- The web side already calls these endpoints through MSW (`apps/web/src/data/intake*`). Match the contract so the web works unchanged against the real API.

## Build

1. `POST /api/intake`: multipart, the limits enforced before and while reading (C2 §2.7, §5.1), the visitor flag, and per-file results exactly per C2 §5.1. It calls `ingest_file`, one batch per request.
2. `GET /api/batches/{id}` (and any list C2 §5.2 names): status, counts, items with `pipeline_stage`, the debrief summary (status / interview id / question count; from L4's tables), `finishedAt`.
3. `ingest_attachment` (C4 §3.14): the full path guard (C4 §4.2 + A13), copy into the inbox, `source: telegram`, a card, journaled as `mona` / `via: telegram`.
4. Regenerate OpenAPI and the TS client. Switch the web's intake data hooks from MSW to the real client **only if** the contract types line up without component changes; otherwise leave the web as is and report the deltas.

## Acceptance (fresh output in the report)

- `make check` green.
- C2 §17 tests 5 and 16 (upload results, body limits before auth [M]).
- C4 §5 path-guard tests [M]: trailing slash, symlink escape, directory swap, FIFO.
- **End to end on the dev stack** (cheap model): upload the 12 synthetic documents through `POST /api/intake` → the batch reaches `done` → the expected outcomes per `demo/expectations.yaml` for the synthetic ones → the duplicate is detected.
- A Playwright spec against the real stack (not MSW): drop 3 synthetic PDFs on `/intake` → progress → summary.
- Report the spend delta.

## Don't

- No pipeline changes. If `ingest_file` needs a change, stop and report.
- No new web screens.
- Never edit `.env`.
