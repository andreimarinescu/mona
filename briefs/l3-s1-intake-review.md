# L3-S1: journal and undo UI, Intake, Review queue

Card **L3**, screens part 1 (HANDOFF build order steps 2–3). Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l3-s1`, branch `l3-s1`, based on `main`.
- **Ports:** Playwright with `E2E_PORT=5774`. No compose stack is needed (API mocked).

The shell and `@mona/ui` are on `main`. This card builds the screens of the daily loop, the demo's pile beat:
- the journal and undo everywhere (toasts, the Activity log, `JournalTimeline`);
- **Intake**;
- the **Review queue** with correction.

The backend endpoints (C2) are being built in parallel by L2-P2, so code against the **frozen C2 contract and the C1 §11 TypeScript DTOs**. Put typed hooks in `apps/web/src/data/` and mock HTTP with MSW in tests and e2e. When the generated client lands, swapping it in should touch only `src/data/`.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D10).
- `docs/contracts/amendments.md` (A11 banner summary).
- **Contracts:**
  - C2 §1 (errors, lists, idempotency, **polling** §1.5), §5 (intake: upload and batches), §6 (review and document actions), §9 (journal, activity, undo/redo), §14 (card actions);
  - C1 §11 (DTOs; the §11.9 shape deltas);
  - C7 §5 (undo states: live, superseded, redo) and §6 (badge);
  - C8 §5 (keys named here) and §6 (formatting).
- **Design:**
  - `design/mona-handoff/HANDOFF.md` §3 (Intake and review, Archive and documents: `JournalTimeline`; Rules, entities, activity: `ActivityBatch`/`ActivityItem`), §4 (behaviour: every change through the journal, toasts, confidence thresholds), §5 (accessibility);
  - `design/screens/mona-web-app.pdf` p6 (Intake), p7 (Review), p8 (correction + scope prompt), p17 (Activity log); the HTML canvas for States and Mobile (Review at 390).
- **Notes:** `~/DevFiles/mona-hq/orchestrator/l3-screens-notes.md` (from the shell lane).
- **Code:** `apps/web/src` (shell, toast store, data layer, `@mona/ui` incl. `ReasonChip`).

## Build

1. **Journal and undo UI:**
   - toasts with Undo (the shell's store) wired to C2 §9.2 undo/redo;
   - `JournalTimeline`;
   - **Activity log** (`/activity`): `ActivityFilters`, and `ActivityBatch` with "Undo whole batch" and expandable children;
   - `ActivityItem` with Undo or Redo, and superseded shown disabled (C7 §5.2);
   - the 24 h "filed by Mona" badge (C7 §6).
2. **Intake** (`/intake`):
   - `DropZone` (a real button, keyboard-operable, drag-over state), multi-file upload per C2 §5.1 (limits, per-file results: duplicate, unsupported, …);
   - the "Visitor document" checkbox (C2 §5.1);
   - `BatchProgress`, `PipelineRow`/`PipelineStepper` (words plus an `aria-label` step);
   - polling per C2 §1.5, including the 30 s grace after `finishedAt`;
   - `BatchQuestionsBanner` ("Mona has N questions") opening the chat panel on the debrief (A11 summary);
   - the summary line "N filed, N need you, N unreadable, N already had".
3. **Review queue** (`/review`, `/review/:documentId`):
   - `ReviewList`/`ReviewListItem` (thumbnail, title, `ReasonChip`, arrival);
   - `ReviewDetail` with prev/next, `J`/`K`/`Enter`, the page thumbnail, `SuggestionPanel` (sentence, `ConfidenceMeter` with settings thresholds, numbered evidence);
   - entity, category and subcategory pickers;
   - confirm, correct, mark unreadable;
   - **`CorrectionScopePrompt`** ("Just this one" / "Every document like this") → a `RulePreviewCard`-style preview → apply.
   - Mobile Review at 390 wide.
4. **Formatting and i18n:** all numbers and dates through `format`; every string in en/fr/ro (FR/RO drafts are fine); the i18n check green.

## Acceptance (fresh output in the report)

- `make web-check` green.
- **vitest:** undo/redo state rendering (live / superseded / redo); polling stop rules, including the grace; the scope prompt → preview → apply flow; the reason chip per reason. Mutation: poll stops at `done` without the grace → a test fails.
- **Playwright** (`E2E_PORT=5774`, MSW-backed):
  - drop 3 files → progress → summary → the banner;
  - review a document with `J`/`K`, correct it with "every document like this", preview, apply;
  - undo from the toast and from the Activity log;
  - Review at 390 wide;
  - no console errors; axe with 0 serious or critical violations on the new screens.
- Screenshots of Intake, Review with correction, and Activity at 1440, compared against PDF pages p6, p8 and p17 in the report (note any deviation).

## Don't

- No backend code.
- No chat cards (a later card); the banner only opens the panel.
- No Archive or viewer (L3-S2).
- No restyling of `@mona/ui`; nothing from the cut list.
