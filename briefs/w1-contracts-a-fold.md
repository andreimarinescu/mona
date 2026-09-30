# W1-A fold: contract set A v0.1 → v0.2

Card **W1-A fold**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/w1-contracts-a`, branch `w1-contracts-a`, rebased on `main`.
- **Edit:** `docs/contracts/C1-domain.md`, `C3-chat-stream.md`, `C4-mcp-tools.md`, `C5-classification.md`, `C7-file-ops.md`.

Next come a reviewer's verification pass, Andrei's verdict, and the freeze on Oct 2. Lanes L1–L4 then build from these documents without talking to each other.

## Inputs, in precedence order

1. **`docs/decisions.md` D1–D5** on `main` (binding). New since v0.1:
   - **D4:** the OpenRouter pins and thinking-off knobs; Hermes session titles must be unique.
   - **D5:**
     - **journal actor = who executed.** Every write made through Mona's tools, including from chat, Telegram and cron, is `mona` with a channel tag; only direct web-UI actions are `user`. This amends plan §9 / HANDOFF; cite D5.
     - Demo Hermes toolsets are `[memory, mona]`.
2. **The gate findings,** `~/DevFiles/mona-hq/orchestrator/review/w1a-gate-findings.md`. Fold **every confirmed finding** (F1…F58): apply the fix, or a better one that the skeptic's note or the evidence supports. If you conclude that a confirmed finding needs no change, say why in the fold report. Don't fold refuted findings, except that the L5b notes in the refuted `reanchor-columns-undefined` go into C1 §9 as a one-line pointer: event timestamps shift and printed dates never do.
3. **Orchestrator decisions on the v0.1 open questions** (from `~/DevFiles/mona-hq/orchestrator/reports/w1-contracts-a-report.md`):
   - **Adopt the drafter's proposal** for OQ 1, 2, 5, 6, 8–13 and 15–33, as amended by any confirmed finding on the same point.
   - **OQ3 (sub-units):** keep the whole-segment `{entity}` expansion, but sub-units come **only** from a winning rule's `unit` (a key or `{from: person}`). There's no implicit addressee → sub-unit link, and `unit` never falls back to a model-resolved value (the OXYLEO findings). Add an addressee to the §8.5 case-4 example so the test pins this.
   - **OQ4:** resolved by D5. The drafter's proposal matches it; cite D5.
   - **OQ7:** add the model-output cache (`<sha>.model.<prompt_version>.json`). Every step after the model still runs live. `demo-reset` restores the cache.
   - **OQ14:** leave it to C6 (set B), as a forward reference.
4. **S6** (`docs/spikes/s6/README.md` on `main`):
   - C5 verifier:
     - move `page` when the quote is found on exactly one other page;
     - normalise typographic punctuation;
     - put a `maxLength` on every model string.
   - Refresh the pins from D4.
   - RuleDraft (C1/C4) takes the **branch shape** S6 recommends: `branches: [{conditions, action}]`, `discriminator` an enum of condition fields, and "personal" resolving to a person entity or sub-unit rather than null. This fixes the confirmed RuleDraft findings.
5. **S5** (`docs/spikes/s5/` and `apps/api/src/mona/chat/` on `main`): the working adapter is the reference implementation of C3's mapping.
   - Hermes session identity follows what S5 proved and the gate finding: our conversation id, never the first message.
   - The session-messages fixture S5 captured (`docs/spikes/s5/fixtures/`, paged at 500) replaces the assumed shape.
   - Hermes interrupts a run on client disconnect and stores "Operation interrupted…" as the reply. Reload must handle that.
6. **`docs/demo-script.md` v1** landed after the drafts. Reconcile the contracts with it:
   - the live batch runs behind the evidence beat;
   - a cached debrief is surfaced by `start_interview` reuse;
   - the AGIPI and Hello bank rules are *not* in the seed (they're learned live);
   - Visitors intake happens via web upload until Telegram lands.

## Every contract

- Bump the header to **0.2-draft**.
- Add a short "Changes in 0.2" list citing F-ids, OQ numbers and D-numbers.
- Keep section numbers stable where you can. If you must renumber, fix every cross-reference: run the drafter's cross-reference scan again.
- Keep the test-obligation and open-question sections current. Close the open questions you resolved; leave only what is truly still open, with a proposal.
- Re-run the drafter's throwaway checks that your changes touch: the C1 DDL on a throwaway `postgres:17` (named `w1f-*`, removed afterwards), the C5 worked examples through a throwaway renderer, and the cross-reference scan.

## Deliverable

- Commits in the worktree, unsigned, one or more per contract.
- The fold report at `~/DevFiles/mona-hq/orchestrator/reports/w1-contracts-a-fold-report.md`:
  - a table F-id → contract § changed (or "no change: why");
  - OQ → resolution;
  - the checks re-run, with fresh output;
  - anything still open, ranked.

## Don't

- No code outside throwaway checks.
- No set B contracts (C2, C6, C8, C9): forward-reference them.
- No re-opening rulings R1–R59 or D1–D5.
