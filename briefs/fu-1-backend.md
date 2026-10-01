# FU-1: backend follow-ups (error declarations, note ordering)

Card **FU-1**. Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fu-1`, branch `fu-1`, based on `main`.
- **Compose project:** `-p mona-fu1`. Export `WEB_PORT=6573 API_PORT=9865 POSTGRES_PORT=56532 HERMES_PORT=9742` (never edit `.env`).

Two small fixes found during integration (`~/DevFiles/mona-hq/orchestrator/backend-followups.md`, `~/DevFiles/mona-hq/orchestrator/reports/int-3-report.md` questions 1–2). L2-P3 (intake) runs in parallel; don't touch intake files.

## Do

1. **Error declarations:** L2-P2's routes in `mona/api/` declare the guard's statuses the way INT-3 did for L4's routes:
   - 401/423 everywhere;
   - 403 on writes;
   - 415 on writes that take a body, plus whatever INT-3's pattern says for bodiless writes.

   Then regenerate `openapi.json` and the TS client. The OpenAPI parity test stays green.
2. **Card-action note ordering:** notes written in one transaction share `created_at`, so their order is random, and `test_card_actions_write_their_notes_in_the_conversation` is flaky. Make the order deterministic: order by `(created_at, id)` with ULIDs monotonic within a transaction, or an explicit sequence. Whatever the fix, notes reach Mona's overlay in the order they were written (C3 §6.1). Add a test that writes several notes in one transaction and asserts their order, and run it 20× in a loop.

## Acceptance (fresh output in the report)

- `make check` green.
- The 20× loop green.
- Mutation: order by `created_at` only → the new test fails in the loop.

## Don't

- No behaviour changes beyond the two items.
- Never edit `.env`.
