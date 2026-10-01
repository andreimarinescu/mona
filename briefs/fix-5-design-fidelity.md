# FIX-5: design fidelity from walkthrough 1 and the design-pass notes

Card **FIX-5**. Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-5`, branch `fix-5`, based on `main`.
- **Compose project:** `-p mona-fix5`. Export `WEB_PORT=7073 API_PORT=10365 POSTGRES_PORT=57032 HERMES_PORT=10242` (never edit `.env`).

Andrei's walkthrough 1 (`~/DevFiles/mona-hq/orchestrator/walkthrough-1.md` #5–#7). The design is the reference: `design/screens/mona-web-app.pdf` (page map in plan §9: p1 Unlock, p6 Intake, p3–p4 Chat), `design/mona-handoff/HANDOFF.md`. FIX-4 runs in parallel and touches `ReviewDetail.tsx`, the DocumentViewer's actions and the API, so stay off those.

## Do

1. **Intake stepper labels (#5):** the progress column shows the five step labels (Queued · Reading · OCR · Classifying · Result) in the header, each aligned over its dot, as on p6. Each dot also gets a visible hover label (the existing `intake.steps.*`), on the Intake and on the Document page's stepper. Works in EN/FR/RO, at mobile width too.
2. **Logo crispness (#6):** the logo looks blurry on Andrei's screen. Find the cause at DPR 1 and 2, e.g. rendering through `<img>` at fractional sizes or a CSS scale. Fix it, for example with an inline SVG component at whole-pixel sizes. Compare with `design/mona-design-system/assets/logo/`. Cover both Unlock and the Sidebar.
3. **The Unlock layout (#7), against p1:**
   - fluid sizing, so a ~2000 px wide screen keeps p1's proportions: the display-size headline (clamp), the left padding, the card width (~540 px at 1500);
   - the avatar with "Welcome back, {name}" from the profile;
   - the footer line "Mona runs on this computer. Unlocking doesn't use the internet." (use the machine name only if C2's system status already exposes it to a locked screen; otherwise no name);
   - the larger arches with the accent dot.

   The recovery-key line stays cut (design cut list).
4. **Design-pass notes** (`~/DevFiles/mona-hq/orchestrator/l3-screens-notes.md`):
   - the InterviewCard question in the voice font (Fraunces, HANDOFF §3);
   - the Settings language picker shows endonyms (Français, Română), a C8 catalogue value change;
   - the chat mock's "Affects 1 document" for 3 letters;
   - delete the unused `routes/Placeholder.tsx`;
   - the panel's "Mona can see…" line as a localised display string (the C3 summary sent to Hermes stays English).

## Acceptance (fresh output in the report)

- `make check` green; `make e2e` green.
- Playwright screenshots of Unlock and Intake at 1440×900 and 2000×1050, saved to `~/DevFiles/mona-hq/orchestrator/review/fix-5/` (synthetic data only), each next to the design page it matches.
- Each item: the change and the test or screenshot that pins it.

## Don't

- No contract changes beyond C8 catalogue values; no backend changes.
- Never edit `.env`.
