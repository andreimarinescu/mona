# W1-B fold: contract set B v0.1 → v0.2

Card **W1-B fold**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/w1-contracts-b`, branch `w1-contracts-b`, rebased on `main`.
- **Edit:** `docs/contracts/C2-rest-api.md`, `C6-interview.md`, `C8-i18n.md`, `C9-privacy-ops.md`.

After the fold come a reviewer's verification pass, Andrei's verdict and the freeze. L2-P2, L3 screens, L4 and L1-M2 then build from these documents in parallel.

## Inputs, in precedence order

1. **Set A frozen v1.0 + amendments A1–A6** (`docs/contracts/`) and **`docs/decisions.md` D1–D9**. Set B must not contradict them. If a finding's best fix needs a set A change, don't edit set A: write it as a proposed amendment in the fold report, with the exact replacement text.
2. **The gate findings** `~/DevFiles/mona-hq/orchestrator/review/w1b-gate-findings.md`. Fold **every confirmed finding** (G1…G63): apply the fix, or a better one the skeptic's note or the evidence supports. If a confirmed finding needs no change, say why in the fold report. Don't fold refuted findings.
3. **Orchestrator rulings:**
   - **Open questions 1–21** from `~/DevFiles/mona-hq/orchestrator/reports/w1-contracts-b-report.md`: adopt the drafter's proposal for every one, as amended by any confirmed finding on the same point.
     - OQ 7: pass 1 gets 35 s, the cache mode is `fallback`, and both are settings, re-measured Oct 8.
     - OQ 11: the Visitors purge doesn't scrub chat transcripts in v1. The stage wording is "the document and everything Mona derived from it"; state that limit in C9.
   - **AGIPI compiles to a branch-shaped RuleDraft,** not one `always` rule. Two branches (PER / Assurance Vie, told apart by text conditions), each with `unit: {from: person}`. This matches C5 §8.5 cases 1a/1b and `demo/seed/rules.learned.yaml`.
     - C6 §7.1 and the pass-2 prompt say so.
     - A branch's fixed `subcategory` is dropped when the documents it settles differ (the skeptic's fix).
     - Test 12 asserts the preview holds both PER and Assurance vie paths.
   - **Early debrief vs the queue debrief:**
     - The queue-threshold debrief never counts documents of a batch that isn't `done`, so AGIPI is never asked twice.
     - The early start gets its own setting (`debrief_early_min`, default 5).
     - The stage snapshot sets it to the planned review count (7), so the banner reads "3 questions" at 3:15.
     - Say so in C6 §3 and C9 §6, and give demo-script v2 a note.
   - **Romanian `condition_text` wording** (the drafter's P2): keep the table in C8 §8. The orchestrator turns it into set A amendment A7 at the freeze.
4. **Code on `main`:**
   - F0: `apps/api/src/mona/dto`, `db`, `seed`;
   - the i18n check, now plural-aware (`scripts/i18n-check.mjs`);
   - `demo/seed/` with its two tiers and `demo/expectations.yaml`;
   - the web shell (`apps/web/src/data/` is the stub layer C2 will replace).
   Use them to check that endpoints, DTOs and keys line up with what exists.

## Every contract

- Bump to **0.2-draft** and add a "Changes in 0.2" list citing G-ids and OQ numbers.
- Keep section numbers stable; if you renumber, fix every cross-reference and re-run the drafter's scanner (`/tmp/w1b/xref.py`, or rewrite it).
- Keep "Test obligations" ([M] marks) and "Open questions" current.
- Re-run the throwaway checks your changes touch: C2 DDL on `postgres:17` (`w1bf-*`, removed afterwards), the `detect_language` vectors, the plural categories, the typography scans.

## Deliverable

- Unsigned commits in the worktree.
- The fold report at `~/DevFiles/mona-hq/orchestrator/reports/w1-contracts-b-fold-report.md`:
  - a G-id → § changed table (or "no change: why");
  - the rulings applied;
  - proposed set A amendments with their exact text;
  - the checks re-run, with fresh output;
  - what's still open, ranked.

## Don't

- No code.
- No edits to set A files.
- Don't re-open R1–R59 or D1–D9.
