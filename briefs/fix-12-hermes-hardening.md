# FIX-12: Hermes hardening from FIX-10, FIX-11 and S7 (A32, A33, A34, config)

Card **FIX-12**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-12`, branch `fix-12`, based on `main`.
- **Compose project:** `-p mona-fix12`. Export `WEB_PORT=7973 API_PORT=11265 POSTGRES_PORT=57932 HERMES_PORT=11142` (never edit `.env`; the worktree has the `.env` symlink; `npm ci` first).

Read `docs/decisions.md` **D19** (and D15, D16, D18), amendments **A32, A33, A34**, `docs/spikes/s7/README.md`, and the reports `~/DevFiles/mona-hq/orchestrator/reports/{fix-10,fix-11,s7}-report.md`.

## Do

1. **A32:** every C4 error is an ordinary result with the same envelope, middleware errors included.
   - Update the tests that assert `isError`, and add one: three failing calls in a row, then a valid call that succeeds in the same Hermes process. Use the real stack, or the S7 probe if it fits.
   - **Mutation:** turn the validation middleware back into an error result → a test fails.
2. **Hermes config:**
   - `agent.tool_use_enforcement: false` and `agent.execution_guidance: false` in `deploy/hermes/config.yaml` and `config.prod.yaml` (check the keys on the pinned 0.21.5, as S7 did).
   - Remove `ingest_attachment` from the web channel's tool list (keep it for Telegram).
   - Recapture the Hermes tool surface if the repo keeps one.
3. **A33:**
   - `demo-reset` installs `deploy/hermes/SOUL.md`; the snapshot no longer carries SOUL.
   - The C9 §6.2 checks and the identical-twice proof still pass.
   - Test that a reset with an old snapshot SOUL ends with the repo's.
4. **A34:** `has_due_date` on `search_documents`, `sum_amounts` and `export_table`, with tests, and in their descriptions.
5. **The accountant pack writes the `export` activity entry.** Test it.
6. **Live check** (D9 quality run on Qwen 3.6, through **Mona's chat route**, not Hermes directly):
   - run `mona stage-build` (Qwen 3.6), then the evening asks 3 times each: "show me a table with all payables with the destination IBAN, due date and entity"; "make that an Excel file"; "now a Word document"; "can you try to read the iban from the PDF?";
   - plus 2 out-of-scope asks: "run a Python script to sum my invoices" and "email this to my accountant".

   Report per turn: the tool calls (target ≤ 2 for the payables table), the time, a non-empty and honest reply, whether the file downloads, and breaker refusals (target 0).

## Acceptance (fresh output in the report)

- `make check` green.
- The tests and the mutation.
- The live table, with `stage-build`'s exit line.

## Don't

- No contract changes beyond A32–A34; no showcase-only code (D16).
- Don't adopt skills or SOUL recipes (held for Andrei).
- Never edit `.env`.
