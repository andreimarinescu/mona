# FIX-1: demo-critical seams from integrated review 1

Card **FIX-1**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-1`, branch `fix-1`, based on `main`.
- **Compose project:** `-p mona-fix1`. Export `WEB_PORT=6673 API_PORT=9965 POSTGRES_PORT=56632 HERMES_PORT=9842` (never edit `.env`). Browser specs use `E2E_BASE_URL=http://localhost:6673`, matching `MONA_PUBLIC_ORIGIN`.

Fix the findings below from `~/DevFiles/mona-hq/orchestrator/review/integrated-review-1-findings.md` (each has where, scenario, fix and the skeptic's note). **R1/R2 is a P0**: every chat turn from the real UI gets 403, and the live e2e hid it by injecting the CSRF header itself.

## Do

1. **R1/R2, chat CSRF (P0):**
   - the web chat transport sends `X-CSRF-Token` from the auth state like every other write, and refreshes it after unlock;
   - audit **every** web write path (fetch calls outside the typed client) for the same gap;
   - **remove the header injection from `e2e/chat.live.spec.ts`** so the live spec tests what users get;
   - add a real-stack Playwright spec that unlocks through the UI and sends a chat turn.
2. **R3:** `POST /api/documents/{id}/correct` accepts the C2-nullable fields (`subcategoryKey`, `subUnitId`, `dueDate`, `amount`) as null with C2's meaning. Replace the 400 test with one sending the exact ReviewDetail body.
3. **R5:** correcting a `processing` document is refused (`conflict`, hint `processing`) in the service, so REST and MCP agree, with a test.
4. **R6:** `sum_amounts` accepts the common `status` filter (C4 §3), extending the C4 §5.5 filter test.
5. **R8:** the Home brief's "questions" link opens the panel on the right batch debrief (batch and interview ids), like `BatchQuestionsBanner`.
6. **R9/R15:** `pageContext.route` never carries document text: strip `q` (and any evidence quote) from the route and summary sent to Hermes. Pin this with a test on the overlay.
7. **R10:** a filed row on Intake links to its DocumentViewer, so the key-moment beat (1:30) is one click from the pile.
8. **R14:** the guard parses cookies robustly. A foreign or malformed cookie on the same host must not drop `mona_session`. Test with a hostile Cookie header.

## Acceptance (fresh output in the report)

- `make check` green.
- **Live e2e** (cheap model, `MONA_LIVE=1`, `-p mona-fix1`, fixture seed + live fixtures as in L2-P1's report, `MONA_OWNER_PASSWORD` exported): 5/5 **with no header injection**.
- The new UI-unlock chat spec green on the real stack.
- **Mutation:** the chat transport without the CSRF header → the new real-stack spec fails.
- Each item: the change and the test that pins it.

## Don't

- No contract changes: if a fix needs one, stop and report.
- Never edit `.env`.
