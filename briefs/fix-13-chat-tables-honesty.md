# FIX-13: chat tables and honesty (A35, A36, SOUL)

Card **FIX-13**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-13`, branch `fix-13`, based on `main`.
- **Compose project:** `-p mona-fix13`. Export `WEB_PORT=7983 API_PORT=11275 POSTGRES_PORT=57942 HERMES_PORT=11152`. Never edit `.env`; the worktree has the `.env` symlink. Run `npm ci` first.

**Read first:**
- `briefs/common.md`;
- `docs/decisions.md` **D20** and **D21** (and D5, D15, D16, D18, D19);
- amendments **A30, A31, A34, A35, A36**;
- C3 §3.4, §5, §6;
- C2 §12;
- `~/DevFiles/mona-hq/orchestrator/reports/fix-12-report.md` (the honesty slips and the live-check method).

You are the only lane adding a migration (**0010**). FIX-14 runs in parallel and adds none (D11).

## Do

1. **SOUL** (`deploy/hermes/SOUL.md`, "What you can do here, and what you can't"), at most 3 short lines in SOUL's voice:
   - offer only what your tools do;
   - never offer to save, change or remember data your tools don't write (e.g. an IBAN pasted in chat);
   - never say a column or field has data your results didn't show; when `empty_columns` is not empty, say which columns came out blank;
   - "a table" means the inline table (A36); a file only when asked.

   Keep the file practice-agnostic (D12).
2. **A35:** `empty_columns` on `export_table`'s result, for the file and inline formats, plus the description line.
   - Tests: a column with no value in any row is listed, and a partly filled one is not.
   - **Mutation:** always return `[]` → a test fails.
3. **A36, backend** (`apps/api/src/mona/workflow/tables.py`, `workflow/tools.py`, `dto/`, `workflow/api.py`):
   - Migration **0010**:
     - `exports.format` allows `'table'`;
     - `exports.spec jsonb NULL`;
     - `card_events.kind` allows `'table'`.
     - Downgrade included.
     - Test it upgrades a database holding 0009-shaped exports and cards (A38's obligation; FIX-14 adds the restore side).
   - `format="table"`:
     - the `exports` row with `spec` (`columns`, `document_ids` in table order, ≤ 500, `lang`), plus the activity entry and the `table` card;
     - the result `{export_id, rows, shown, truncated, empty_columns, card_refs}`;
     - on Telegram, also `text`: a server-built list of ≤ 20 rows, C8 formats, IBAN masked (A30).
   - The `data-table` payload `TableView`, in `dto/load.py` `card_payload`:
     - the first 50 rows from current DB state for `spec.document_ids`, with channel visibility re-applied;
     - category labels in `lang`;
     - ISO dates and numeric amounts with `currency`.
   - C2:
     - `GET /api/exports/{id}/table`;
     - `POST /api/exports/{id}/file` `{format}`, reusing A31's `make` with actor `user`, via `ui`;
     - 404 for a non-table id; 409 `conflict` with `details.reason: "empty"` when no spec document is still visible.
     - It writes the `table.download` card-action note when the request carries a conversation, as `draft.download` does.
   - The tool description per A36: inline by default for "show/list/table"; a file only when the person asks for a file (Excel, Word, CSV) or when `rows > shown`.
   - `make api-client` (OpenAPI and TS client regenerated; parity test green).
4. **A36, web:**
   - `apps/web/src/chat/cards/TableCard.tsx` on the design system's `Table` (`design/mona-design-system/components/index.d.ts`):
     - tabular figures and amount/date formats as the Archive `ResultsTable` (`apps/web/src/routes/archive/ResultsTable.tsx`);
     - title; "showing 50 of N" when `rowsTotal > rows.length` or `truncated`;
     - a one-line note naming the empty columns;
     - a "Download as" control (CSV, Excel, Word) that POSTs, then downloads `fileUrl`;
     - a refresh through the GET.
   - Dispatch `table` in `apps/web/src/chat/Messages.tsx` next to `ExportCard`.
   - EN/FR/RO strings (the i18n missing-key check stays green).
   - vitest for the card.
   - A mock-suite e2e fixture so the card renders in `make e2e`.
   - Real elements only (HANDOFF: `table` for tables, `button` for actions).
5. **Live check** (a D9 quality run on Qwen 3.6, through **Mona's chat route**, as FIX-12 did):
   - Source `~/DevFiles/mona-hq/orchestrator/stage.env` (it sets Qwen 3.6 and the seed overlay).
   - Run `deploy/bin/mona stage-build --anchor today --yes` in your compose project only.
   - Then 3 times each:
     - "show me a table with all payables with the destination IBAN, due date and entity";
     - "make that an Excel file";
     - "now a Word document".
   - Then once each: "run a Python script to sum my invoices", "save this IBAN on the supplier: FR76 3000 6000 0112 3456 7890 189" (a synthetic IBAN), and "email this to my accountant".
   - Report per turn:
     - the tool calls (target: ≤ 2 for the payables table, `format="table"` 3 of 3);
     - the time;
     - whether the reply is non-empty and honest (no offers of tools Mona doesn't have, no claims about blank columns);
     - whether the file downloads;
     - breaker refusals (target 0).
   - Include the OpenRouter usage delta.

## Acceptance (fresh output in the report)

- `make check` green.
- `make e2e`: no worse than 128 passed / 19 skipped.
- The tests and the mutation above.
- The live table, with `stage-build`'s exit line.

## Don't

- No contract changes beyond A35 and A36. No showcase-only code (D16).
- No S7 recipes in SOUL (D20: deferred).
- Don't touch the main checkout's `data/` or its snapshots. Your stage-build writes only to your worktree's `data/`.
- Never edit `.env`.
