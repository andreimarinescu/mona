# FIX-8: a targeted debrief question is about its own cluster (A26)

Card **FIX-8**. Agent: `coder`. **Andrei is waiting on this card before sitting 5: keep it tight.**

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-8`, branch `fix-8`, based on `main`.
- **Compose project:** `-p mona-fix8`. Export `WEB_PORT=7473 API_PORT=10765 POSTGRES_PORT=57432 HERMES_PORT=10642` (never edit `.env`; the worktree has the `.env` symlink).

Read amendments **A25 and A26**, then `apps/api/src/mona/interviews/coverage.py` and `generate.py` (`_cover`, `targeted_pass2`).

**What happened:** the stage's cached debrief has a targeted question, "Do these statements belong to the LMNP Hello bank (…6187) or a personal joint account?", whose only affected document is the La Médicale insurance notice (83ef9c3e34b2).

## Do

1. **No analysis in the targeted call:** the targeted pass 2's user message is the reduced input only (A26).
2. **The counterparty check (A26):** a targeted question is kept only if its normalised text contains the cluster's counterparty name or an alias (or the extracted string when unresolved). Otherwise fall through to the deterministic question. The generation log line records `targeted-rejected` when the check drops one.
3. **Tests** (recorded outputs; extend `tests/test_interviews_coverage.py`):
   - a targeted answer naming another counterparty → the deterministic question for the cluster;
   - an answer naming the cluster's counterparty by its alias → kept;
   - the targeted request body carries no analysis.

   **Mutations:** drop the check → a test fails; put the analysis back → a test fails.

## Acceptance (fresh output in the report)

- `make check` green.
- The tests and the two mutations.
- No live run needed; the orchestrator rebuilds the stage after the merge.

## Don't

- No contract changes beyond A26.
- Never edit `.env`.
