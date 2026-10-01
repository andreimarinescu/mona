# L3-S3: the chat, its cards, the panel (the demo's 4:00 and 7:00 beats)

Card **L3**, screens part 3 (HANDOFF build order step 5). Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l3-s3`, branch `l3-s3`, based on `main`.
- **Compose:** `-p mona-l3`, with `WEB_PORT=6073 API_PORT=9465 POSTGRES_PORT=56132 HERMES_PORT=9342`, only for the live specs (D9 cheap model). Unit and e2e otherwise use MSW.

The chat plumbing exists: the C3 adapter (L2-P1), `ConversationThread` with `ThinkingBlock`/`ToolActivityChip`/`DocCard`/`DeadlineCard`/`InterviewCard` dev renderers (S5, L2-P1, shell), and the panel frame (shell). This card turns it into the designed chat:
- every card;
- card actions through C2 §14, which write C3 notes;
- the full `/chat` page;
- the slide-over panel.

The interview card is where the debrief happens on stage.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D14).
- `docs/contracts/amendments.md` (A3, A11).
- **Contracts:**
  - **C3 in full** (parts, cards, notes, conversations, transcript reload);
  - C2 §1.5 (polling), §11 (interviews: answer, skip, apply / Apply all), §12 (drafts and exports), §13 (conversations), §14 (card actions);
  - C6 §5 (questions and options on the card), §6 (answers), §7 (preview, apply, undo), §9 (notes);
  - C1 §11.5 (`RulePreview`, applied state), §11.7;
  - C8 §5.1, §5.2, §5.5 (keys), §3.2 (`LanguageDivider`).
- **Design:**
  - `design/mona-handoff/HANDOFF.md` §2 (panel behaviour, keyboard 1/2/3 on interview cards, `Esc`), §3 Chat (every component: `ConversationList`, `ChatThread`, `UserMessage`, `MonaMessage`, `StreamingText`, `ThinkingBlock`, `ToolActivityChip`, `DocCard`, `DeadlineCard`, `InterviewCard`, `EvidenceSnippet`, `RulePreviewCard`, `PathDiff`, `DraftCard`, `LanguageDivider`, `ChatComposer`, `AttachmentChip`), §4, §5;
  - `design/screens/mona-web-app.pdf` p3 (Chat, AGIPI interview), p4 (Chat + RulePreview), p5 (ChatPanel over Archive); the HTML canvas Mobile page (Chat at 390).
- **Code:** `apps/web/src/chat/` (`ConversationThread`, parts, transport, types), `apps/web/src/data/` (typed C2 layer + MSW; L3-S1/S2 patterns), `@mona/ui`, the shell's app state (panel, conversation id, `registerChatEntry`).
- **Notes:** `~/DevFiles/mona-hq/orchestrator/l3-screens-notes.md`.

## Build

1. **The thread:** `UserMessage`, `MonaMessage` with `Citation`s and a `SourceList`, `StreamingText` (caret, `aria-busy`), `ThinkingBlock` (live and done; "Thought for N seconds" per block, not the turn total), `ToolActivityChip` (C3 §4.5 labels, i18n), `LanguageDivider` with "Keep English" (C3/C8). The error and offline states per C3 §4.4.
2. **Cards**, from `data-*` parts with stable ids so updates replace in place:
   - `DocCard`;
   - `DeadlineCard` (Remind me via C2 §10);
   - **`InterviewCard`**: question in the voice font, "affects N documents", 2–3 `EvidenceSnippet`s opening the viewer deep link, three answers with the suggested one primary plus "Suggested", keys 1/2/3, skip, "It depends; let me explain" puts the cursor in the composer with the question quoted;
   - **`RulePreviewCard`**: "N move · M stay", `PathDiff` rows, Apply and Adjust; several branch previews from one answer with **Apply all**; the applied state per C1 §11.5;
   - `DraftCard` (Copy, Download .docx, "Mona never sends anything", never Send);
   - `ExportCard`.

   Card actions POST to C2 §11/§12/§14, the cards poll per §1.5, and the action's note shows up in Mona's next turn (C3 §6).
3. **`/chat` and `/chat/:conversationId`:** `ConversationList` with search (C2 §13), the thread, and `ChatComposer` (idle, typing, drag-over, sending with Stop, disabled when offline; attachments go to Intake per C3 OQ5). Transcript reload from C2 §13.
4. **Panel:** the slide-over panel (shell frame) hosts the same thread; the page context line is localised (from L3-S2); opening on the debrief from `BatchQuestionsBanner` (A11). Mobile Chat at 390.

## Acceptance (fresh output in the report)

- `make web-check` green.
- **vitest:** each card renders from a fixture part (C1 DTOs), including the applied `RulePreview` and two-branch Apply all; card-action → POST → polling → updated card; `ThinkingBlock` seconds per block; keyboard 1/2/3.
- **Playwright** (MSW unless noted, `E2E_PORT=6074`):
  - the **AGIPI debrief flow**: banner → panel → `InterviewCard` → answer 1 → two `RulePreviewCard`s → Apply all → applied state → undo from the toast → back to draft;
  - the draft flow (`DraftCard` Copy and Download);
  - `/chat` list and reload;
  - Chat at 390;
  - no console errors; axe with 0 serious or critical violations.
- **Live** (`MONA_LIVE=1`, cheap model, on the `mona-l3` stack with `main`'s backend): the existing 4 chat beats still pass with the designed thread.
- Screenshots of p3, p4 and p5 equivalents at 1440, compared in the report.
- **Mutation:** Apply all only applies the first preview → a spec fails.

## Don't

- No backend changes. If an endpoint is missing or wrong on `main`, mock it per the contract and report it.
- No Home (L3-S4).
- No restyling of `@mona/ui`; nothing from the cut list.
