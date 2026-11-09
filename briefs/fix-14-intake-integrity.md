# FIX-14: intake integrity and migrated restore (C2 §5.1, A37, A38, the folder-tree test)

Card **FIX-14**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-14`, branch `fix-14`, based on `main`.
- **Compose project:** `-p mona-fix14`. Export `WEB_PORT=7993 API_PORT=11285 POSTGRES_PORT=57952 HERMES_PORT=11162`. Never edit `.env`; the worktree has the `.env` symlink. Run `npm ci` first.

**Read first:**
- `briefs/common.md`;
- `docs/decisions.md` **D20** (and D11, D16, D17);
- amendments **A24, A37, A38**;
- C2 §5.1;
- C7 §4.1 and §8.4;
- C9 §5.3, §6.2, §6.3 and §6.6;
- `~/DevFiles/mona-hq/orchestrator/backend-followups.md` (the source of items 1–4).

Check each item against the code first. If one is already done, prove it with a test or command and say so in the report.

**No migrations.** FIX-13 adds 0010 in parallel (D11). Your A38 test must not depend on a specific revision; derive it from the migration chain.

## Do

1. **C2 §5.1 per-file limits** (`apps/api/src/mona/pipeline/intake.py` `MAX_BYTES`, `apps/api/src/mona/api/intake.py`):
   - each file is ≤ 25 MB, refused as it streams past the cap, 413 `too_large`;
   - bytes that fail to open (a truncated PDF) → a per-file `rejected` with `unreadable_file`, no document created.
   - Flip the strict xfail in `apps/api/tests/test_api_intake.py` to a passing test. Add a truncated-JPEG/PNG case if the sniffer covers images.
   - Composer attachments and `ingest_attachment` use the same path (C2 §5.1, C4 §3.14). Check that they agree.
2. **The Intake summary counts each document once** (`apps/web/src/routes/intake/summary.ts`, `BatchProgress.tsx`):
   - a document that is both `failed` and `unreadable` is no longer in two buckets;
   - precedence: unreadable > review > failed;
   - the totals match C2's batch counts (`apps/api/src/mona/api/views.py`).
   - Fix the existing `intake.test.tsx` expectation, and add a case where the sum of the buckets equals the number of documents.
3. **A37:**
   - In `apps/api/src/mona/fileops/purge.py`, skip the textcache unlink while another `documents` row (live or deleted) has the same sha256. The document's own file is still unlinked.
   - The per-sha256 transaction-scoped advisory lock goes in the intake dedupe-and-insert (`pipeline/intake.py`) and in the A24 undo-of-delete check-and-restore (`fileops/ops.py`, `api/registry.py`).
   - A unique violation that still reaches the A24 index maps to `duplicate` or 409 `conflict` (`details.reason: "duplicate"`), never a 500.
   - **Tests:**
     - purging a visitor document whose bytes a deleted practice twin shares keeps the caches; with no twin, they go;
     - a concurrent upload of the same bytes and an undo-of-delete, in two connections with a barrier, give one winner and no 500 (loop it 20 times);
     - mutations: drop the twin check → a test fails; drop the lock → the race test fails.
4. **A38: an older snapshot restores and migrates** (`apps/api/src/mona/demo/snapshot.py` `verify`; `restore_db` already runs `migrate`):
   - accept a manifest revision that is the head or an ancestor of the head (alembic `ScriptDirectory`); refuse anything else with A38's message;
   - the reset report line names the migration.
   - Covers `demo-reset`, `--refresh-textcache` and the C9 §6.6 restore.
   - **Test:** migrate a scratch database to head-1, put minimal synthetic data in it, write a snapshot whose manifest says head-1, run the restore → the database is at head, the data is intact, and the §6.2 checks pass. A future or unknown revision is refused.
   - **Live proof (no OpenRouter needed):**
     - copy the main checkout's snapshot **`demo`** read-only into your worktree's `data/snapshots/` (`cp -a`, never move, never write into `~/DevFiles/mona-hq/mona/data/`);
     - temporarily add a throwaway no-op revision on top of head, uncommitted, so the copy is one revision old;
     - run `deploy/bin/mona demo-reset --anchor today --yes`, then `deploy/bin/mona doctor` in `mona-fix14`;
     - show the migration line and an all-green doctor;
     - delete the throwaway revision afterwards, and say so in the report.
5. **The folder-tree keyboard e2e test** (`apps/web/e2e/archive-viewer.spec.ts:157`, flaky 1 in 6 to 1 in 12): fix the focus timing in the test, with a web-first assertion on focus before each key press and no sleeps.
   - Run it 20 times on its own (`--repeat-each=20`) and paste the tail.

## Acceptance (fresh output in the report)

- `make check` green.
- `make e2e`: no worse than 128 passed / 19 skipped.
- The tests, loops and mutations above.
- The A38 live proof.

## Don't

- No contract changes beyond A37 and A38. No showcase-only code (D16).
- No migrations committed.
- Don't write to the main checkout's `data/` or snapshots.
- Never edit `.env`.
