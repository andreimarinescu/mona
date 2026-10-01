# FIX-11: `payment_iban` (A30) and `export_table` (A31)

Card **FIX-11**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-11`, branch `fix-11`, based on `main`.
- **Compose project:** `-p mona-fix11`. Export `WEB_PORT=7773 API_PORT=11065 POSTGRES_PORT=57732 HERMES_PORT=10942` (never edit `.env`; the worktree has the `.env` symlink; `npm ci` first).

Read `docs/decisions.md` **D18**, amendments **A30, A31**, then:
- C5 §4.3 (IBAN candidates), §5–§7;
- C4 §2–§3 (the §3.13 export pattern, §2.6 visibility);
- C2's exports and `DocumentSummary`;
- C3's `export` card.

Evidence: `~/DevFiles/mona-hq/orchestrator/walkthrough-1.md`, "Evening session". FIX-10 runs in parallel and **owns SOUL and the Hermes config**: don't edit them.

## Do

1. **`payment_iban` (A30):**
   - Deterministic at classification: valid mod-97 candidates, excluding the registry's own accounts, the first in page order, with verified evidence and `findQuery`.
   - Exposed in `DocumentSummary.paymentIban` (regenerate OpenAPI and the TS client), in `get_document`/`search_documents`/`list_deadlines` items, in the DocumentViewer's fields panel (an `EvidenceSnippet`, i18n label), and as the accountant-export CSV column.
   - Masked on the telegram channel.
   - A `mona pipeline backfill-iban` step that fills existing documents idempotently.
   - **Tests:** a supplier invoice with its own IBAN plus the practice's IBAN → the supplier's; a bad checksum is ignored; no candidate → null; the telegram masking; the backfill is idempotent.
   - **Mutation:** stop excluding the practice's accounts → a test fails.
2. **`export_table` (A31):**
   - The MCP tool (description verbatim from A31), the schema and the visibility filter.
   - The file builders: CSV with the §3.13 formula guard; XLSX (openpyxl) with typed cells; DOCX (python-docx) with a locale-formatted table and title.
   - The `export` card and download through the existing C2 export route; an activity entry.
   - Recapture the Hermes tool surface if the repo keeps one.
   - **Tests:** each format opens and holds the rows and columns asked for; a hidden personal document is left out on telegram; more than 500 rows → `truncated`; formula-looking cells are guarded.
   - **Mutation:** drop the visibility filter → a test fails.
3. **Live check** (cheap model, D9), on a stage with these documents:
   - "show me a table with all payables with the destination IBAN, due date and entity";
   - "make that an Excel file";
   - "now a Word document".

   Report the tool calls per turn (target ≤ 2), whether the file downloads and opens, and the time.

## Acceptance (fresh output in the report)

- `make check` green; `make e2e` green (a viewer field and the export card render).
- The tests and mutations above, and the live table.

## Don't

- No contract changes beyond A30/A31.
- No showcase-only code (D16).
- Never edit `.env`.
