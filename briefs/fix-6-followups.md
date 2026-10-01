# FIX-6: FIX-4 follow-ups (cache page budget, Delete errors, re-upload after delete, visitor scope prompt)

Card **FIX-6**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-6`, branch `fix-6`, based on `main`.
- **Compose project:** `-p mona-fix6`. Export `WEB_PORT=7273 API_PORT=10565 POSTGRES_PORT=57232 HERMES_PORT=10442` (never edit `.env`; symlink the main checkout's `.env` if the worktree has none).

Read `docs/decisions.md` **D17** (and D15/D16), then amendments **A22, A23, A24**. Background: `~/DevFiles/mona-hq/orchestrator/reports/fix-4-report.md` (6b, open questions 3, 5, 6).

## Do

1. **A22:** `pages_sent` in the model-output cache file; a hit rebuilds the prompt with that budget before verification. Test: an A14 retry, then a cache hit, gives the same confidence and verification. **Mutation:** ignore `pages_sent` → the test fails.
2. **A23:** Delete with a mismatched `fileName` → 422 `invalid_value` (`field: "fileName"`). The web dialog shows the server's message if it ever gets one. Tests on both sides.
3. **A24:**
   - Migration 0007: drop the `sha256` unique constraint, add a partial unique index on `sha256 WHERE deleted_at IS NULL`.
   - Intake dedupe compares with live documents only. Undo of a delete is refused with 409 `conflict` (`reason: "duplicate"`) while a live twin exists.
   - Check every other place that assumes one row per sha256: the caches are keyed by sha256 and shared (fine); demo fingerprints and snapshot checks (C9 §6.2); the debrief cache's sha256 binding (C6 §4.7); and `get_document`/search. List them in the report with what you did.
   - Tests: upload → delete → re-upload with Visitor ticked gives a new visitor document; undo of the old delete is refused while the twin lives; a duplicate of a live document is still "Already had".
   - **Mutation:** dedupe including deleted rows → a test fails.
4. **Visitor scope prompt:** after correcting a visitor document, the Review page doesn't offer "Every document like this" (it 400s today; Visitors can't be a rule action). Test it.

## Acceptance (fresh output in the report)

- `make check` green, and `make e2e` green.
- Each item: the change and the test that pins it, plus both mutations.
- `mona stage-build` still succeeds after migration 0007. Cheap model is fine; report its last lines.

## Don't

- No contract changes beyond A22–A24.
- No showcase-only code (D16).
- Never edit `.env`.
