# FIX-9: no internal labels in debrief questions (A27)

Card **FIX-9**. Agent: `coder`. **Andrei is waiting on this card before sitting 5: keep it tight.**

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-9`, branch `fix-9`, based on `main`.
- **Compose project:** `-p mona-fix9`. Export `WEB_PORT=7573 API_PORT=10865 POSTGRES_PORT=57532 HERMES_PORT=10742` (never edit `.env`; the worktree has the `.env` symlink; run `npm ci` in the worktree first).

Read amendment **A27** (with A25/A26), then `apps/api/src/mona/interviews/` (`compile.py` §4.5, `coverage.py`, `cache.py`, `prompt.py`, `config.py`).

**What happened:** the stage's debrief on Qwen 3.6 asked "For d1 and d2, should they be filed as assurance_vie or per, and do the addressees match child-1 and child-2?", with options such as "d1 assurance_vie, d2 PER".

## Do

1. **The A27 check:** for pass-2 questions, targeted questions and cache replay. Match whole words after `norm()`. The allow-list is every key that reads the same as a display name. Record `labels-rejected` in the log line.
2. **The A27 instruction line** in pass 2's system message (exact text from A27), with `PROMPT_VERSION = "c6-v2"`. Update any test that pins the exact prompt text.
3. **Tests:**
   - the incident's question and options → dropped, and the cluster gets a coverage question;
   - "LMNP" in a label → kept;
   - a counterparty name that contains a key-like token as part of a longer word → kept;
   - cache replay drops a labelled question;
   - the prompt contains the new line, and the version is `c6-v2`.

   **Mutations:** drop the check → a test fails; drop the allow-list → the "LMNP" test fails.

## Acceptance (fresh output in the report)

- `make check` green.
- The tests and mutations. No live run: the orchestrator rebuilds the stage.

## Don't

- No contract changes beyond A27.
- Never edit `.env`.
