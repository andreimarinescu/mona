# FIX-4: grounding Mona in tool output, visitor uploads, Delete, walkthrough-1 correctness

Card **FIX-4**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-4`, branch `fix-4`, based on `main`.
- **Compose project:** `-p mona-fix4`. Export `WEB_PORT=6973 API_PORT=10265 POSTGRES_PORT=56932 HERMES_PORT=10142` (never edit `.env`).

From Andrei's walkthrough 1 (`~/DevFiles/mona-hq/orchestrator/walkthrough-1.md`, findings #2, #9, #10, #11, #12 and the timings). Read `docs/decisions.md` **D15 and D16** first: control the model through tool output, checks and instructions, and write **no showcase-only code**. Every fix here is a product fix.

## Do

1. **A21, grounding (#2/#9):**
   - `start_interview` returns the open questions as A21 describes, and its description carries the new sentence.
   - Then audit **every** card-producing tool (C4, C3 `card_events`). Wherever the model gets only ids for something it will narrate, add the few fields A21 allows, and list the audit in the report.
   - Add the matching line to the Hermes instructions or SOUL if C3/C9 allow it there (a card carries its own content; Mona introduces it in one line and never invents titles, questions or amounts). If neither allows it, report instead of editing.
   - **Live check (cheap model, D9):** run the banner turn ("Let's go through your questions about this batch.") 5 times on a stage with a ready debrief. Every document title or question Mona mentions must exist. Report it as a table.
2. **A20, visitor uploads (#11):** in a visitor batch, confidence alone never queues, as A20 says. Tests:
   - a 70% visitor document files to Visitors with its band;
   - an unreadable one queues;
   - a practice document at 70% still queues.

   **Mutation:** apply the rule to every batch → a test fails.
3. **The Review form for a visitor document (#12):** the entity shows as a read-only "Visitors" field with the purge note, never as a select that can't hold Visitors (`ReviewDetail.tsx:158`). A correction can't move a visitor document into a practice entity from this form unless C2/C5 allow it. Check them, and test that whichever behaviour they define holds.
4. **Delete in the web UI (#10):**
   - The DocumentViewer gets the C2 Delete action behind a danger dialog. The dialog shows the exact current file name to type and posts `/api/documents/{id}/delete`. Undo via the toast and the Activity log, as for other journal entries.
   - Check C2 for the error on a mismatched name. If it is `stale`, report it as an amendment candidate instead of changing it, since the message misled the walkthrough.
   - Add an e2e: delete, then undo.
5. **The tool budget on the French draft:** « Rédigez une réponse au SIE pour demander un échéancier » took 3 tool calls (2× search + `draft_reply`), over C4 §2.9's ≤2. Bring it within budget through the tool descriptions or `draft_reply`'s inputs, within C4. Live check, cheap model, 5 runs: ≤2 calls each.
6. **From FIX-3's report (open questions 3, 4, 7):**
   - the model-output cache must not keep an all-null final answer (A14), so a rebuild retries it;
   - investigate why one document scored 95 live and 75 from the cache, and fix it if it's a defect;
   - investigate why `demo-reset` went from ~32 s to ~149 s, and fix it if it's a regression.

## Acceptance (fresh output in the report)

- `make check` green.
- Each item: the change and the test that pins it. The mutations for items 1 and 2: drop `questions` from the result → a test fails; the A20 mutation above.
- The two live-check tables (items 1 and 5).

## Don't

- No contract changes beyond A20/A21; report any other need.
- No showcase-only code (D16).
- Never edit `.env`.
