# L3-S2: Archive, document viewer v1, accountant export dialog

Card **L3**, screens part 2 (HANDOFF build order step 4). Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l3-s2`, branch `l3-s2`, based on `main`.
- **Ports:** Playwright with `E2E_PORT=5974`. No compose stack is needed (API mocked).

L3-S1 (on `main`) built the journal and undo UI, Intake and Review on a typed C2 data layer (`apps/web/src/data/`) with an MSW mock API. Extend that same layer and mock. This card builds the demo's **evidence moment**: the Archive and Document viewer v1. The backend is being built in parallel (L2-P2, L4), so code against the frozen contracts.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D14).
- **Contracts:**
  - C2 §1, §4 (archive search, document detail, files, **the viewer deep link** §4.4, folders), §12 (exports: the dialog only);
  - C5 §7 (`findQuery`) and amendment A15;
  - C1 §11.2–§11.3 (`Evidence`, `ExtractedField`, `DocumentSummary`, `DocumentDetail`), §11.7 (`Export`);
  - C8 §5–§6;
  - C9 §3.3 (what the accountant pack includes).
- **Design:**
  - `design/mona-handoff/HANDOFF.md` §3 (Archive and documents: `FacetPanel`, `ActiveFilters`, `ResultsTable`, `FolderTree`, `FolderContents`, `DocumentViewer`, `DocumentSidePanel`, `JournalTimeline`, `AccountantExportDialog`), §4, §5, **§7 (viewer v1, step by step)**;
  - `design/screens/mona-web-app.pdf` p9 (Archive search), p10 (Archive folders), **p11 (Viewer v1)**, p13 (Accountant export).
- **Code:**
  - `apps/web/src/data/` and the MSW handlers (L3-S1);
  - `apps/web/src/pdfjs/find.ts` and the `/dev/pdf` route (`findHash`, `dispatchFind`, and L1-M2's "open a given PDF at a page");
  - `apps/web/public/pdfjs/` (vendored 6.3.289);
  - `@mona/ui`.

## Build

1. **Archive** (`/archive`, `/archive/folders/*path`):
   - search with `FacetPanel` (entity, year, category, counterparty, amount range, status), `ActiveFilters`, and `ResultsTable` (ledger table, tabular figures, status per row, pagination per C2 §1.3);
   - `FolderTree` (ARIA tree, counts) and `FolderContents` (on-disk path; "Show in Explorer" is informational in v1);
   - the entity scope from the shell applies;
   - "Mona can see" summaries per C3/C8, with a localised display string (shell notes).
2. **Document viewer v1** (`/documents/:id?page=&q=`), HANDOFF §7 v1 exactly:
   - `PdfFrame` embeds the vendored `pdfjs/web/viewer.html?file=<C2 PDF endpoint>` same-origin, opening at `page` and, when `q` is set, driving find;
   - `DocumentSidePanel` shows `ExtractedFields`, each with an `EvidenceSnippet` (quote, page, `verified` state; the French quote marked `lang="fr"`) and a **"Show on page"** action that dispatches the pdf.js find with the field's `findQuery`, falling back to the value;
   - the Filed section (path as breadcrumbs, file name, the rule that fired);
   - `JournalTimeline` (from L3-S1) with Undo/Redo;
   - the reminder affordance (C2 §10 contract, mocked);
   - the processing and unreadable states.
3. **`AccountantExportDialog`** over `/archive`: entity and fiscal year → what's included (C9 §3.3) → build → ready with download (C2 §12, polling per §1.5); personal entities are not offered.
4. Every string in en/fr/ro; formatting through `format`; accessibility per HANDOFF §5.

## Acceptance (fresh output in the report)

- `make web-check` green.
- **vitest:** facet → query mapping; the deep-link parser; "Show on page" sends `findQuery` (not the raw quote) with the value fallback; the export dialog's states.
- **Playwright** (`E2E_PORT=5974`, MSW serving `/api`, and a synthetic PDF for the file endpoint, e.g. the dev sample):
  - search and filter;
  - the folder tree;
  - open a document from results;
  - "Show on page" produces a pdf.js highlight (`.textLayer .highlight`) for a verified field;
  - the deep link with `q` highlights on load;
  - export dialog end to end;
  - no console errors; axe with 0 serious or critical violations.
- **Mutation:** send the raw quote instead of `findQuery` → the find spec fails (use a fixture where they differ).
- Screenshots of Archive search, folders, the viewer with a highlight, and the export dialog at 1440, compared with p9, p10, p11 and p13 in the report.

## Don't

- No backend code.
- No viewer v2 (no overlay): cut.
- No chat cards (a later card).
- No restyling of `@mona/ui`.
- Nothing from the cut list.
