# FIX-7: every candidate cluster gets a debrief question (A25)

Card **FIX-7**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-7`, branch `fix-7`, based on `main`.
- **Compose project:** `-p mona-fix7`. Export `WEB_PORT=7373 API_PORT=10665 POSTGRES_PORT=57332 HERMES_PORT=10542` (never edit `.env`; the worktree has the `.env` symlink).

Read `docs/decisions.md` D15/D16, then amendment **A25** and C6 §4 (generation) and §10 (tests). FIX-6 runs in parallel on the model-output cache, intake and Delete; stay out of those.

**What happened:** `mona stage-build` on Qwen 3.6 queued 8 documents (AGIPI ×3, Hello bank ×3, La Médicale, UNIM). In 3 of 3 live debriefs, pass 2 returned 2 questions and none about AGIPI ("no question asks about 110c37b2aaa1, 86c269dd3165, f5a32d43f306", `/tmp/fold4/stage-build.log`).

## Do

1. **Implement A25 in the interview job:**
   - the targeted pass 2 per uncovered cluster (at most 3; 30 s; no retry; the reduced input; pass 1's analysis);
   - then the deterministic question for any cluster still uncovered;
   - `interview.question.where` in the server catalog (EN/FR/RO; native-quality FR, best-effort RO);
   - the generation log line records how each question was made (`pass2`, `targeted`, `deterministic`).
2. **Tests (C6 §10 style, recorded model outputs):**
   - pass 2 skips a cluster → the targeted call covers it;
   - the targeted call fails → a deterministic question with options `always` (Mona's proposed destination, counterparty condition prepended) + `ask`;
   - a cluster with no proposed entity stays uncovered;
   - the 7-question cap holds;
   - `impact` ordering.

   **Mutation:** skip the coverage step → a test fails.
3. **Live (D9 quality run, Qwen 3.6; Andrei has approved quality runs for this):**
   - run the stage's live batch 3 times on a stage from `mona stage-build`, or the scenario in `tests/live_l4.py`;
   - report per run: the questions, how each was made, whether AGIPI and Hello bank are covered, the shape of the AGIPI option (`depends` on text with `from_person`, or not), and the time to `ready` (the §4.8 budget).
   - **Target:** AGIPI and Hello bank covered in 3/3, with ready ≤ 60 s.
4. Then `mona stage-build` must pass on Qwen 3.6. Report its last lines.

## Acceptance (fresh output in the report)

- `make check` green.
- The tests and the mutation above.
- The live table.
- `stage-build`'s exit code and summary.

## Don't

- No contract changes beyond A25.
- No showcase-only code (D16): the coverage rule applies to every debrief, on any practice.
- Never edit `.env`.
