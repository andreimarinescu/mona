# W1-A: draft contract set A (C1, C3 shape, C4, C5, C7)

Card **W1**, set A (plan §5). Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/w1-contracts-a`, branch `w1-contracts-a`, based on `main`.
- **Output:** `docs/contracts/C1-domain.md`, `C3-chat-stream.md`, `C4-mcp-tools.md`, `C5-classification.md`, `C7-file-ops.md`.

Next come a gate review workflow, Andrei's verdict, and a freeze on Oct 2. After that, lanes L1 (pipeline and filing), L2 (API and Mona), L3 (web) and L4 (intelligence) build against these documents in parallel, without talking to each other. **Write for them:** precise, testable, no prose padding. Anything a lane could reasonably interpret two ways is a defect.

## Read first

- `briefs/common.md` and `docs/decisions.md`. D1 is the stack; **D3 is the Hermes facts**.
- `docs/spikes/s1/README.md`, the S1/S2 evidence, and its `fixtures/`.
- The master plan `~/Obsidian/dev-docs/mona-hq/specs/mona-mvp-master-plan.md`: §1 rulings (binding), §2 product spec, §3 architecture, §5 (contract list and the "contract details added by the delta review"), §9 (design implementation decisions: confidence bands, file names, journal semantics, visibility, viewer v1), §10c demo script, §11 seed, §12b.
- `design/mona-handoff/HANDOFF.md`, especially §3 component names, §4 behaviour, §6 data shapes (the starting DTOs) and §7 viewer v1.
- `design/mona-design-system/components/index.d.ts`: the `Category` union, `DocStatus`, and the props the cards need.
- `~/DevFiles/mona-hq/classify/classify_llm.py`: the v2 taxonomy, prompt and request.
- If `~/DevFiles/mona-hq/orchestrator/reports/w0-s6-report.md` exists when you reach C5, read it and `docs/spikes/s6/` in the `w0-s6` worktree for the evidence and json_schema findings.

## Every contract

- Header: version (0.1-draft), status, freeze date (Oct 2), change rule ("amend via `docs/contracts/amendments.md`, orchestrator only"), consumers (lanes), and depends-on (other contracts).
- Numbered sections, so amendments can cite them ("C4 §3.2").
- A "Test obligations" section: the acceptance tests the implementing lane must write. Mark the ones that need mutation checks.
- An "Open questions" section for anything a ruling doesn't settle. Don't invent product behaviour; propose an answer there and let the gate decide.
- Names: snake_case in the DB and in MCP; camelCase in the JSON DTOs the web sees (HANDOFF §6). State the mapping once in C1.

## C1: domain model and DB schema (Postgres 17, SQLAlchemy 2 + Alembic)

Tables, columns, types, constraints and indexes for everything plan §5 C1 lists, plus the delta-review additions:
- **Registry:** entities (with sub-units, `visibility practice|personal`, fiscal-year end, filing language), people, accounts (IBAN stored as a salted hash + last 4, never in clear), and categories with per-language labels and `icon` from the DS `Category` union (default `invoice`).
- **Templates** (path and file name per category).
- **Rules:** structured `conditions[]` plus `action`, the rendered `condition_text`, source, version, enabled, fired count, last fired, corrections since.
- **Documents:** sha256 unique; the current path; status per the DS `DocStatus`; the classified fields; reasons; batch; FTS `tsvector` with `unaccent` and ș/ț normalisation; `pg_trgm` on counterparty. Extractions (versioned, per-field evidence) and classifications.
- **Journal:** the `file_ops` table. The integer journal number, actor `mona|user`, before and after, batch, rule, confidence, undoable, `undone_by`, `undo_of`.
- **Workflow:** batches, review items, interviews / questions / answers, deadlines and reminders.
- **Chat:** `conversations` (our id ↔ the Hermes session id, title, pending card-action notes), `chat_turns` (the turn lease), `card_events`.
- **Profile and settings:** the single profile (name, argon2 hash, locale, auto-lock minutes, `locked_at`) and the settings, including the confidence thresholds (85/60 defaults, plan §9).
- The `DocumentSummary`, `Suggestion`, `Rule`, `JournalEntry`, `Deadline`, `Interview` and `Evidence` DTOs derived from HANDOFF §6, **extended** per plan §12b P2-3: template tokens, structured conditions, `ruleDraft`, and `DocumentSummary` fields for the viewer and the cards.

  This is the shape C2 (set B) will serve; define it here as the canonical DTO layer.
- **IDs:** prefixed ULIDs as text (`doc_…`, `rul_…`, `ent_…`), except the journal number. Say why in one line.
- **Seed-loading invariants.** The seed YAML under `demo/seed/` is a draft and will be re-keyed to this schema.

## C3: chat stream, shape (set A); the sync details come in set B

- **Request.** `POST /api/chat`: `{conversationId?, message, pageContext: {route, summary}, locale}` → a response in the AI SDK **UI Message Stream** protocol, header `x-vercel-ai-ui-message-stream: v1`. Pin the `ai` package major version the web will use, and list the exact part types.
- **Hermes → UI part mapping** from the S1 fixtures (D3):
  - `delta.reasoning_content` → `reasoning-*`;
  - `delta.content` → `text-*`;
  - `hermes.tool.progress` running/completed → tool parts that the `ToolActivityChip` renders, with a human label per tool, in EN/FR/RO via i18n keys;
  - `hermes.status` and keepalives → dropped;
  - errors and Hermes unreachable → an error part that the UI renders as the "Mona is offline" state;
  - finish.
- **The overlay the adapter sends** as a `system` message: the page context, the reply-language instruction, and the pending card-action notes (then cleared). The exact text template goes in the contract.
- **Cards (plan §2.3, D3: no stream carries tool results).** Specify this design:
  1. The adapter opens a `chat_turns` lease at turn start and closes it at finish.
  2. A card-producing MCP tool writes a `card_events` row (`card_ref`, tool, entity ids, and the web turn it's attributed to) and includes `card_ref` in its tool result. It's attributed to the single open web turn, or to none when zero or several are open.
  3. The adapter emits `data-<card>` parts for its turn's `card_events` as they appear: checked on each `hermes.tool.progress completed` and at finish.
  4. At finish, the adapter reconciles against `GET /api/sessions/{id}/messages` (tool results carry `card_ref`s) and emits anything missed. Transcript reload rehydrates the cards the same way.
- **Card payload types:** `data-doc` (DocumentSummary), `data-deadline`, `data-interview`, `data-rulePreview`, `data-draft`, `data-export`. Each has a stable part `id` so later updates reconcile.
- **Conversation list and transcript reload** (from Hermes session messages plus cards).
- Card-action notes (the sync mechanism, S2-proven) are defined in shape here; C6 details the interview ones.

## C4: MCP tool catalog (FastMCP at `/mcp` on the api, `Authorization: Bearer $MONA_SERVICE_KEY`)

- **Every tool in plan §2.3:** name, description (English, written for the model: when to use it, when not), parameters (JSON Schema), result shape, errors, side effects (journal entries, `card_events`) and idempotency.
- **Results return IDs** plus the compact facts the model needs to answer: titles, amounts, dates, totals. Never full documents or OCR text. Include `card_ref`s where a card is produced.
- **Limits:** result size caps and pagination.
- **Guards:**
  - Visibility: personal entities are excluded where C9 will say so; for now, mark which tools take a `channel` hint.
  - `ingest_attachment(path)` accepts only paths under the attachment volume, after resolving symlinks and `..`. The model-supplied path is untrusted.
  - Write tools never send anything outside the box (R32).
- **Hermes-side config:** `tools: {resources: false, prompts: false}`, sampling off (D3).
- **Tool-call budget guidance** for the descriptions: ≤2 calls per typical demo turn. Keep `search_documents` filterable by entity, category, year, counterparty and amount range, so the model doesn't loop (S2 outlier).

## C5: extraction and classification (plan §2.1, §9, §12b)

- **Pipeline stages and the queue** each runs on (`llm` concurrency 1, `cpu` 2–4), with the cache keys (sha256): text (page-delimited), OCR'd PDF, page-1 thumbnail (`pdftoppm -r 60`).
- **Page-delimited text format** sent to the model.
- **Rules first:** the `conditions[]` grammar (fields, operators, including IBAN/SIREN/addressee/insured-person matchers) and `action`, plus how rule conflicts are detected.
- **The LLM step:**
  - the exact output schema: every field `{value, quote, page}` + `confidence`;
  - no-think json_schema;
  - the prompt skeleton built from the v2 definitions, re-keyed to canonical category ids;
  - the context budget (<20k tokens; registry + active rules + ≤5 exemplars).
- **Evidence verification:** normalise (whitespace including U+00A0/U+202F, case, diacritics, ș/ț) → substring on the stated page → `verified`. How an unverified field lowers confidence.
- **`findQuery` computation** (plan §12b P1-6): the longest normalised substring that the pdf.js text layer will match.
- **Confidence → band** (≥85 file silently, 60–84 file + mark, <60 or unknown entity / conflict / unreadable → queue with a `ReasonChip`). Thresholds come from settings.
- **Template grammar:** tokens `{entity} {year} {fy} {category} {sub} {counterparty} {issuer} {reference} {date:FMT}`.
  - `{fy}` = the fiscal year of `period_end` under the entity's FY end.
  - File names: date first, diacritics dropped, unsafe characters replaced, a length cap. Folders keep French accents.
  - The rendering is deterministic, with worked examples for the six feedback cases in plan §0 success criterion 2.
- **The `rules.yaml` export schema.**

## C7: file-ops invariants

- The archive root and the move-inside-root guard (resolve and compare; no symlink escapes).
- Move + rename is atomic per document: it writes the journal entry in the same transaction as the DB path update, with crash recovery (what happens if the process dies between the filesystem move and the commit).
- **Collision suffix policy:** ` (2)`, ` (3)` or `-2`: pick one and state it. Identical sha256 at the target means duplicate, not collision.
- **Undo:**
  - single, batch (group ordering: reverse journal order);
  - undo-of-undo = redo;
  - **supersede rule:** an entry is undoable only if the document's current path equals `entry.after`; otherwise it's shown as "superseded", disabled.
- The 24 h "filed by Mona" badge, and when it expires.
- Delete is user-only, behind a danger confirmation, and journaled.
- **Invariants as testable statements**, e.g. "the archive tree equals the DB paths after any sequence of file/undo/redo", which is property-test material. Mark them for mutation checks.

## Deliverable

- The five documents, committed unsigned in your worktree.
- The report at `~/DevFiles/mona-hq/orchestrator/reports/w1-contracts-a-report.md`: a summary per contract, the cross-contract dependencies, and the open questions consolidated and ranked by how much they block lanes.

## Don't

- No code.
- Don't touch set B contracts (C2 REST details, C6 interview, C8 i18n, C9 privacy/ops). Where set A needs something from them, write a one-line forward reference.
- Don't re-open rulings R1–R59.
