# Contract amendments

Changes to frozen contracts C1–C9, numbered A1, A2, … in the order they're made. An amendment wins over the contract text it amends until the contract document is updated; a brief never wins over either.

Each entry: number, date, contract and section, the change, the reason, and the lanes it affects.

Set A (C1, C3 shape, C4, C5, C7) froze at v1.0 on 2026-09-30. Set B (C2, C6, C8, C9) froze at v1.0 on 2026-10-01.

## A1 · 2026-09-30 · C1 §8 `settings.iban_salt`: created by the seed loader

- **Change:** C1 says the migration generates `settings.iban_salt`. But the settings row can't exist before the profile's `practice_name` is known, so the **seed loader** creates it on first load. The value is `MONA_IBAN_PEPPER` when that is set, else 32 random bytes. The hash formula is unchanged.
- **Why:** F0 found the migration wording unbuildable (NOT NULL `practice_name`).
- **Lanes:** F0 (done), L1, L2 (read the salt from settings, never from env), L5c (`demo-reset` keeps the settings row).

## A2 · 2026-09-30 · C4 §3.8/§3.9, C5 §4.6.9: Visitors documents are never rule candidates

- **Change:** documents from a visitor batch are excluded from `preview_rule` / `apply_rule` candidates and from rule application in the pipeline.
- **Why:** as written, applying a rule could move a Visitors document into a practice entity. That breaks C1 §2.1's Visitors invariant and takes the document out of the 24 h purge (W1-B P1).
- **Lanes:** L1 (candidates), L2 (tools).

## A3 · 2026-09-30 · C4 §3.7: an "ask me each time" answer

- **Change:** `answer_question` with an `ask` option returns `rules: [{id, state: "active"}]` (the `review: true` rule, C1 §11.5) with `previews: []` and no card.
- **Why:** it makes explicit what C6 §6.2 records (W1-B P3).
- **Lanes:** L2, L4.

## A4 · 2026-09-30 · C4 §3.9: the activating rule change joins the apply group

- **Change:** when `apply_rule` creates a group, the rule's activating `rule.change` journal entry carries that `group_id`.
- **Why:** undoing a whole Apply group must revert the rule to draft (C6 §7.3) (W1-B P4).
- **Lanes:** L1, L2.

## A5 · 2026-09-30 · C1 §1.2: id prefix `ses`

- **Change:** add `ses` → `auth_sessions` to the prefix table (C2 §2.2 owns the table). Editorial (W1-B P5).
- **Lanes:** L2.

## A6 · 2026-09-30 · C5 §3/§5.2: Romanian titles use comma-below

- **Change:** generated titles stored for a practice filing in Romanian pass through `ro_comma_below` (C8 §7 rule 2). No effect on the demo (FR filing) (W1-B P6).
- **Lanes:** L1.

## A8 · 2026-10-01 · C1 §4.1 batch-done check: `FOR NO KEY UPDATE`

- **Change:** the batch-done check locks the batch row with `SELECT … FOR NO KEY UPDATE`, not `FOR UPDATE`.
- **Why:** L1-M1 reproduced a deadlock between two concurrent filings under `FOR UPDATE`. The file-op transactions touch rows referencing the batch, and their FK `KEY SHARE` locks conflict with `FOR UPDATE`. `FOR NO KEY UPDATE` still serialises the check, and a race test fails without the lock.
- **Lanes:** L1 (done), L1-M2.

## A7 · 2026-10-01 · C5 §4.7: Romanian and French `condition_text` wording, amounts

- **Change:** the Romanian column of C5 §4.7 takes C8 §8's reviewed phrases (gender agreement with "lui"/"îl … pe", the missing genitive nouns, fewer calques), with Romanian closing quotes `”` (U+201D) and French U+00A0 inside « ».
- **Amounts:** `{money}`, `{a}` and `{b}` are the number part of `format_money` (C8 §6.4): two decimals, no currency, and each language's own marks. EN groups with `,` and uses `.` for decimals (`1,284.60`); FR groups with U+00A0 and uses `,` (`1 284,60`); RO groups with `.` and uses `,` (`1.284,60`).
- **Test:** C5 §11 test 16 gains one amount row per language.
- **Why:** W1-B P2 and gate G19. F0's `mona/rules/text.py` groups French with a plain space.
- **Lanes:** L1.

## A9 · 2026-10-01 · C1 §8 `settings`: the early-debrief setting

- **Change:** replace the `debrief_queue_threshold` line with:
  ```
  debrief_queue_threshold smallint NOT NULL DEFAULT 5,    -- C6 §3.3: uncovered candidates of done batches that start a queue debrief
  debrief_early_min  smallint NOT NULL DEFAULT 5 CHECK (debrief_early_min BETWEEN 1 AND 50),   -- C6 §3.2: candidates that start a running batch's debrief early
  ```
- **Why:** the orchestrator's early-debrief ruling (set B G9, G31, G37). The stage snapshot sets 7 (C9 §6.7).
- **Lanes:**
  - L2: the migration, `SettingsView.debriefEarlyMin`, and the seed loader's `practice.debrief_early_min`;
  - L4: the trigger;
  - L5c: the stage value.

## A10 · 2026-10-01 · C1 §6.2: no extracted deadline for a visitor document

- **Change:** append to the bullet that begins "A filed document with a verified `due_date` gets an `extracted` deadline": *A document of a visitor batch (`batches.visitor`, §4.1) never gets one: a visitor's bill is not the practice's obligation (C9 §5.5).*
- **Why:** set B G53.
- **Lanes:** L1 (the filing transaction).

## A11 · 2026-10-01 · C3 §2: the banner's page summary

- **Change:** `summary: "Intake, batch bat_… {state}, N questions"`, where `{state}` is `running` while the batch runs, else `finished`.
- **Why:** set B G9. An early debrief can be ready while the batch still runs.
- **Lanes:** L3.

## A12 · 2026-10-01 · C4 §3.3 `sum_amounts`: titles in the result

- **Change:** each summed document in the result carries its `title` (for up to 10 documents; beyond that, ids only with `"truncated": true`), within the §2.3 cap.
- **Why:** L2-P1's live runs showed the model following a sum with two `get_document` calls just to name the documents, against the ≤2-calls budget (C4 §2.9).
- **Lanes:** L2.

## A13 · 2026-10-01 · C4 §4.2 and C7 §1: two narrower attachment mounts

- **Change:** instead of the whole `/opt/data/cache`, the api mounts only `cache/documents` and `cache/images`, read-only, as two volume subpaths at the same absolute paths. `ATTACH_ROOT` and the guard are unchanged.
- **Why:** the single mount also exposed Hermes' own cache files to the api (L2-P1).
- **Lanes:** L2.

## A14 · 2026-10-01 · C5 §1.2/§5: retry an empty model answer once

- **Change:** if a schema-valid model output has every field null and `confidence = 0` for a document with readable text (≥ 50 non-whitespace characters), `classify_document` retries the model call once with the page budget reduced to the first page. If the retry is also empty, the document goes to review with reason `low` as today. The model-output cache stores only the final output.
- **Why:** L1-M2's quality run. Qwen 3.6 returned all-null answers for two long (21-page) statements, which then queue without a counterparty, so the debrief can't group them.
- **Lanes:** L1.

## A15 · 2026-10-01 · C5 §6.1/§7: quotes that span layout columns

- **Change:** in the page-delimited `-layout` text, a run of ≥ 2 spaces inside a line is a column break.
  - Verification (§6.1) still matches the quote against the line with breaks folded.
  - `findQuery` (§7) never crosses a column break: it uses the longest segment of the quote that lies within one column (≥ 2 words), else the field value.
- **Why:** L1-M2's pdf.js check. 1 of 90 verified quotes didn't highlight, because the model joined two columns of one line and pdf.js orders that text differently.
- **Lanes:** L1.

## A16 · 2026-10-01 · C3 §1/§3.4: the web renders AI SDK messages with its own components

- **Change:** the web consumes the UI Message Stream with `ai` / `@ai-sdk/react` (`useChat`) and renders `UIMessage` parts with its own DS components. `@assistant-ui/*` is no longer a dependency. The stream protocol, part types, mapping and card design are unchanged.
- **Why:** L3-S3 needed per-block reasoning timing, the `LanguageDivider` and stable card ids, which assistant-ui's primitives hide. INT-3 removed the unused packages. Editorial for every lane except L3.
- **Lanes:** L3.

## A17 · 2026-10-01 · C5 §9.3/§9.4 and C8 §5.4: a first-seen counterparty asks

- **Change:**
  - §9.3 reason `entity` also fires when no rule won (§4.6) and the document's resolved counterparty (§5.1) has **no other document with `status='filed'`** (any entity, any batch).
  - Visitor batches are exempt (§4.6.8; test 12 unchanged). A document with no counterparty is unaffected.
  - Documents of one new counterparty in one batch all queue (none is filed yet), so the debrief groups them into one question.
  - When `entity` comes only from this trigger, the Suggestion sentence uses the new server key `review.sentence.first` ("First document from {counterparty}: where should it go?"), in EN/FR/RO. The chip stays `entity`.
- **Why:** Andrei's ruling (D15). On Qwen 3.6, the AGIPI and Hello bank documents file confidently as `personal` at 0.95. The debrief never asks about them, and Hello bank lands in the wrong entity (plan §0 criterion 2). A practice manager asks the first time a supplier appears, and the signal holds for any practice and supplier (D12).
- **Lanes:** L1 (FIX-3). The web renders the server sentence unchanged.

## A18 · 2026-10-01 · C1 §8 `settings`: confidence defaults 90/75

- **Change:**
  - `confidence_high` defaults to 90 and `confidence_low` to 75 (migration 0006 alters the column defaults; existing rows are untouched).
  - The demo seed sets both explicitly.
  - Tests that depend on bands set their thresholds explicitly.
- **Why:** Andrei's ruling (D15) on L5c's histogram. At 90/75 the live batch queues about 6 documents, the plan's target of 5–7 per batch.
- **Lanes:** L1, L5 (FIX-3).

## A19 · 2026-10-01 · C9 §5.3: the purge removes orphaned extracted counterparties

- **Change:** the Visitors purge also deletes counterparties with `origin='extracted'` that no document, classification, account or rule references once the visitor documents are gone. It never deletes a counterparty that anything else still references.
- **Why:** integrated review 1 (R12). Settings › Privacy and the stage line promise that everything Mona derived from a visitor's document is deleted. FIX-2 built it; this ratifies it.
- **Lanes:** L1 (done in FIX-2).

## A20 · 2026-10-01 · C5 §9.3: a visitor upload never queues on confidence

- **Change:**
  - In a visitor batch, `low` from `confidence < settings.confidence_low` (or category `unknown`) doesn't queue. The document files to `Visitors/…`, and the journal entry carries its band.
  - `unreadable` still queues, and so does a model step that failed after retries.
  - Practice documents are unaffected.
- **Why:** Andrei's ruling (D16, walkthrough 1 #11). A visitor document goes to Visitors whatever the model says, and it's purged after 24 h, so a review adds nothing. The phone photo scored 70% and queued at the 9:30 beat.
- **Lanes:** L1 (FIX-4).

## A21 · 2026-10-01 · C4 §3.6: `start_interview` returns the questions it shows

- **Change:**
  - When the interview is `ready`, the result also carries `questions`: `[{"n", "text", "affected": <count>, "options": [<label>…]}]`, the open questions in card order, in the interview language. It is `[]` while `generating`.
  - The description adds: "The card shows the questions; introduce them in one line and never restate or invent them."
  - Any other tool whose result renders as a card and gives the model only ids gets the same treatment: the few fields it needs to mention the card accurately, within §2.3's cap.
- **Why:** walkthrough 1 #2/#9. The tool returned only a count, so Qwen 3.6 invented three questions about a document that doesn't exist, and kept referring to them in the next turn. D15: ground the model in tool output instead of trusting it.
- **Lanes:** L2 (FIX-4).

## A22 · 2026-10-01 · C5 §1.3: the model-output cache records the page budget

- **Change:** the model-output file also records `"pages_sent": n`, the page budget of the prompt the stored answer came from; absent means the full budget. A cache hit rebuilds the prompt with `max_pages = pages_sent` before evidence verification, so the result is the same live or cached.
- **Why:** FIX-4, item 6b. A document whose answer came from the A14 one-page retry scored 95 live and 75 from the cache: the cached answer was verified against the 3-page prompt, and one quote became ambiguous (−20).
- **Lanes:** L1 (FIX-6).

## A23 · 2026-10-01 · C2 §8: Delete with a mismatched file name

- **Change:** `POST /api/documents/{id}/delete` whose `fileName` doesn't equal the document's current file name returns **422 `invalid_value`** with `details: {field: "fileName"}`, not 409 `stale`. `stale` stays for a document that changed under the operation.
- **Why:** walkthrough 1 #10. The `stale` message ("the document changed meanwhile") hid that the typed name was wrong.
- **Lanes:** L2 (FIX-6).

## A24 · 2026-10-01 · C1 §4 `documents.sha256`, C1 §4.1 intake: a deleted document doesn't block a re-upload

- **Change:**
  - `sha256` is unique among documents with `deleted_at IS NULL` (a partial unique index, migration 0007), not across all rows.
  - Intake dedupe (C7 §8.4) compares only against those.
  - A re-upload of a deleted file's bytes becomes a fresh document with the new upload's settings (e.g. visitor). The deleted row and its journal stay as they are.
  - Undo of the old delete is refused with 409 `conflict` (`details.reason: "duplicate"`) while a live document with the same sha256 exists.
- **Why:** Andrei's ruling (D17, walkthrough 1 #10). A mis-tagged upload, deleted, couldn't be uploaded again.
- **Lanes:** L1, L2 (FIX-6).

## A25 · 2026-10-01 · C6 §4.5–§4.6: every candidate cluster gets a question

- **Change:** a new step after §4.5. While there are fewer than 7 kept questions, each input cluster (§4.2) none of whose documents a kept question affects, taken largest first, gets:
  1. **A targeted pass 2:**
     - the §4.4 system message unchanged; the user message carries the §4.2 input reduced to that cluster's documents (registry unchanged) and pass 1's analysis;
     - the schema with `questions: array[1..1]`; thinking off; timeout 30 s; no retry;
     - §4.5 runs on its output, and a surviving question is kept.
  2. **Otherwise, a deterministic question** built from the cluster's own classifications, with no model call:
     - `text` = C8 key `interview.question.where` ("Where should the documents from {counterparty} go?", in the interview's language);
     - `affected` = the cluster's documents; `evidence` = the cluster's verified counterparty quotes (at most 3);
     - option `a` = `always` to the destination Mona proposed (the entity and category of the cluster's most common current classification, with the counterparty condition prepended as §4.5 step 2 does), marked `suggested`, `suggestion_confidence` = that classification's confidence;
     - option `b` = "Ask me each time" (§4.5 step 4).
     - If the cluster has no proposed entity or category, only the "It depends; let me explain" path applies, and the cluster stays uncovered.

  At most 3 targeted calls per interview; any later uncovered clusters go straight to step 2. The questions are persisted with the rest in `impact` order (§4.6). The §4.5 sentence "Candidates left uncovered by every question are not an error" now holds only beyond the 7-question cap.
- **Why:**
  - Walkthrough 2 preparation: in 3 of 3 live debriefs on Qwen 3.6, pass 2 asked nothing about the three AGIPI documents queued as first-seen (A17). They would have stayed in review with no question.
  - D15: a check guarantees coverage instead of trusting the model. D16: a product fix, not a stage fix.
- **Lanes:** L4 (FIX-7).

## A26 · 2026-10-01 · A25: a targeted question is about its own cluster

- **Change** (A25 step 1):
  - The targeted pass 2's user message carries the reduced §4.2 input **without pass 1's analysis**: no `\n\nAnalysis:\n` part.
  - After §4.5, the targeted question is kept only if its `text`, after `norm()` (C5 §2), contains the `norm()` of the cluster's counterparty: its registry `name` or any of its aliases (`counterparty_aliases.alias_norm`), or, for a cluster without a resolved counterparty, its extracted counterparty string.
  - Otherwise the targeted question is dropped and step 2's deterministic question is used.
- **Why:** the stage build on Qwen 3.6 produced a targeted question about the Hello bank statements ("…LMNP Hello bank (…6187) or a personal joint account?") whose only affected document was the La Médicale insurance notice. Pass 1's analysis of the whole batch leaked into the one-cluster call. An answer would have filed the notice under the wrong entity. D15: a check, not trust.
- **Lanes:** L4 (FIX-8).

## A27 · 2026-10-01 · C6 §4.4–§4.5: no internal labels in what the owner reads

- **Change:**
  1. **Check** (a new §4.5 step 0, also applied to targeted questions and on cache replay). A question is dropped when its `text` or any option `label`, after `norm()` (C5 §2), contains as a whole word:
     - a document alias of the input (`d1`, `d2`, …);
     - a registry key that contains `_`, `-` or a digit and whose `norm()` differs from the `norm()` of every display name or label in the registry: an entity key, sub-unit key, category id, subcategory key or person key (e.g. `assurance_vie`, `child-1`, `selarl-simina`).

     Plain-word keys (`personal`, `tax`, `frais`) never count, since they read as ordinary words in questions. A key that reads the same as a display name (e.g. `lmnp` / "LMNP", `angers-strasbourg` / "Angers-Strasbourg") is allowed. A dropped question's cluster then goes through A25's coverage (targeted, then deterministic), and the generation log records `labels-rejected`.
  2. **Instruction.** Pass 2's system message (§4.4) gains one line before "At most 7 questions": "- Write text and labels for the owner: name documents by their title or counterparty and use the registry's display names; never write aliases (d1, d2) or keys." `PROMPT_VERSION` becomes `c6-v2`, so earlier cached debriefs no longer match.
- **Why:** the rebuilt stage's AGIPI question read "For d1 and d2, should they be filed as assurance_vie or per, and do the addressees match child-1 and child-2?". D15: an instruction to prevent it, and a check to guarantee it.
- **Lanes:** L4 (FIX-9).

## A28 · 2026-10-01 · C4 §2.9, C3 §5: an enforced turn budget and an honest fallback

- **Change:**
  1. **Budget.** The MCP server counts the tool calls attributed to one chat turn (C3 §5.2 attribution; a Telegram turn likewise).
     - From the 7th call of a turn (`MONA_TURN_TOOL_BUDGET`, default 6), every tool returns `{"error": "budget_exhausted", "message": "Answer now with what you already have, and say plainly what you couldn't do."}` without running.
     - Hermes `agent.max_turns` becomes 8.
  2. **Fallback text.** A web turn that ends with no text part (an empty reply, Hermes' iteration cap, or an abort after tool calls) gets a text part from the C8 key `chat.fallback.too_complex` (EN/FR/RO) in the reply language. It says that the request needs more steps than Mona can take at once, and lists what she can do.
  3. **Capabilities in SOUL.** A short "What I can do here / what I can't" section:
     - **can:** search and open documents; total amounts; list what's due; draft a letter; export a table of documents; prepare the accountant pack; answer debrief questions;
     - **can't:** run programs, open arbitrary files, browse, send anything.

     When asked for something outside it, Mona says so in one line and offers the nearest thing she can do.
- **Why:** Andrei's evening session (2026-10-01). Asks for an IBAN table and spreadsheet files drove Qwen 3.6 into 12–23-call loops and empty replies, and it claimed a terminal it doesn't have. D15: enforce with a check, don't trust the model.
- **Lanes:** L2 (FIX-10).

## A29 · 2026-10-01 · C3 §5, C8 §4: the reply language is checked

- **Change:**
  - After a web turn, `detect_language` (C8 §4) runs on the reply text. When it detects a language other than the turn's `reply_language` on a reply of ≥ 20 words, the adapter logs it (no text), and the next turn's overlay adds: "Your previous reply was in {detected}; reply in {Language}."
  - No schema change.
- **Why:** an English banner turn (`reply_language` `en`) was answered in French. D15.
- **Lanes:** L2 (FIX-10).

## A30 · 2026-10-01 · C5 §4.3/§5, C2 `DocumentSummary`, C4 results: `payment_iban`, a deterministic field

- **Change:**
  - At classification, `payment_iban` is filled deterministically: no model field and no model call.
    - **Candidates:** the §4.3 IBAN candidates in the page text with a valid mod-97 checksum, excluding every IBAN of the registry's own `accounts` (the practice's accounts, never a payee's).
    - **Value:** the first remaining candidate in page order, normalised (upper case, no spaces).
    - **Evidence:** the matched text as the quote, its page, `verified: true`, and `findQuery` as C5 §7.
  - **Exposed:** `DocumentSummary.paymentIban`; `get_document`, `search_documents` and `list_deadlines` items; the DocumentViewer's fields panel; and an accountant-export CSV column `payment_iban`.
  - On the telegram channel it is masked to the country code and the last 4 characters.
  - Re-running classification fills it for existing documents (a `mona pipeline backfill-iban` CLI step, idempotent).
- **Why:** Andrei asked for "all payables with the destination IBAN". The IBAN is printed on the documents, but no tool could return it, so Qwen looped over `get_document`. A checksum makes it exact without the model.
- **Lanes:** L1, L2, L3 (FIX-11).

## A31 · 2026-10-01 · C4 §3.17 `export_table` [V], C2 exports, C3 `export` card

- **Change:** a new tool.
  - **Description:** "Make a table file of documents (CSV, Excel or Word) from a search or a list of documents, with the columns the person asks for. It appears as a card with a download; nothing is sent."
  - **Params:**
    - `document_ids` (1–500) or the §3 common filters (as `search_documents`);
    - `columns`: a list, 1–10, of `title, counterparty, entity, category, doc_date, due_date, amount, currency, payment_iban, reference, status, path`;
    - `format`: `csv` | `xlsx` | `docx`;
    - `title`: ≤ 80, optional;
    - `lang`: optional, as C4 §3.6.
  - **Result:** `{"export_id", "file_name", "rows", "truncated", "card_refs"}`. The `export` card offers Download through C2's export download route.
  - **The file:**
    - built synchronously (≤ 500 rows, within §2.8's 10 s) under `/data/exports`;
    - CSV is machine-friendly (ISO dates, dot decimals, §3.13's formula guard);
    - XLSX has typed cells;
    - DOCX has a titled table formatted for the request locale (C8).
  - **Visibility (C9 §3):** a channel's hidden documents are left out. On Telegram, `payment_iban` is masked as A30 says.
  - **Activity:** an activity entry, as for the accountant pack. It is never sent anywhere.
- **Why:** Andrei asked for a payables table as CSV, then XLSX, then DOCX. With this tool, Qwen only chooses the documents and the columns.
- **Lanes:** L2, L4 (FIX-11).

## A32 · 2026-10-01 · C4 §2.4: tool errors come back as ordinary results

- **Change:**
  - Every C4 §2.4 error is returned as an ordinary tool result (`isError: false`) whose text and structured content are the same `{"error": {…}}` envelope, as A28's `budget_exhausted` already is.
  - Schema validation (`invalid_argument` from the middleware) and `internal` included. The codes, messages, hints and `valid` lists are unchanged.
- **Why:**
  - Hermes 0.21.5 opens a process-wide circuit breaker after 3 consecutive MCP error results from one server: every `mona` call fails for 60 s, in every session, and the threshold is hard-coded.
  - FIX-10 and S7 both measured it. In S7, 16 of 30 hard turns started blocked by the previous turn's errors, and Mona told the person the archive was down.
- **Lanes:** L2 (FIX-12).

## A33 · 2026-10-01 · C9 §6.5: the reset installs SOUL from the repo

- **Change:**
  - `demo-reset` (and `stage-build`'s resets) also installs `deploy/hermes/SOUL.md` into the Hermes profile, as it does `config.yaml`. The snapshot's Hermes part no longer carries SOUL; the restore leaves memories and sessions as they are.
  - SOUL is code, versioned with the release, never stage state.
- **Why:** S7 found that both stage snapshots hold an old SOUL (3,036 bytes), which the reset restored over the repo's, so FIX-4's and FIX-10's SOUL lines never reached the stage.
- **Lanes:** L5/L6 (FIX-12).

## A34 · 2026-10-01 · C4 §3 common filters: `has_due_date`

- **Change:** the common filter parameters gain `has_due_date: boolean`, meaning documents with a non-null `due_date` (payables, demands, notices). It is accepted by `search_documents`, `sum_amounts` and `export_table`, and listed in the tools' descriptions.
- **Why:** FIX-11's live check. "All payables" isn't a category, so the model searched category by category (5–10 calls) before exporting. One filter makes it one call.
- **Lanes:** L2 (FIX-12).

## A35 · 2026-11-09 · C4 §3.17 `export_table` (A31): the result names its empty columns

- **Change:**
  - The result gains `empty_columns`: the requested columns with no value in any row, in request order (`[]` when every column has data). It appears in the file and the inline mode (A36).
  - The description adds: "When `empty_columns` is not empty, tell the person which columns came out blank."
- **Why:** in FIX-12's live check, Mona said IBANs were included when the column was empty (D20, honesty).
- **Lanes:** L2/L4 (FIX-13).

## A36 · 2026-11-09 · C4 §3.17, C1 §6.3, C2 §12, C3 §3.4/§5.5/§6.2: an inline table card

- **Change:**
  - **C4:** `format` also takes `"table"`. The tool resolves the documents as it does for a file (same filters, visibility and order, ≤ 500) and writes **no file**:
    - an `exports` row with `format = 'table'`, `status = 'ready'`, `title`, `document_count`, `truncated`, and `spec` (jsonb): `{"columns", "document_ids", "lang"}` (the ids in table order, ≤ 500);
    - its activity entry, as A31's;
    - a `table` card (subject `{"export_id"}`).
  - **Result:** `{"export_id", "rows", "shown", "truncated", "empty_columns", "card_refs"}`, where `shown` = min(rows, 50). On Telegram, which has no cards, the result also carries `text`: a plain-text list built by the server, at most 20 rows, one line per row, with the requested columns in C8 formats and `payment_iban` masked (A30). Mona relays it as it is.
  - **The description:** "For a table the person wants to see, use format `table`; it appears in the chat. Make a file (csv, xlsx, docx) only when the person asks for a file, Excel, Word or CSV, or when `rows` exceeds `shown`."
  - **C1:** `exports.format` allows `'table'`; `exports.spec jsonb NULL`; `card_events.kind` allows `'table'` (migration 0010).
  - **C3:**
    - `data-table` | export id | `TableView`: `{id, title, columns: {key, label}[], rows: Record<key, string | number | null>[], rowsTotal, truncated, emptyColumns, lang}`;
    - `rows` holds the first 50, built at emit time from current DB state for `spec.document_ids`, with the channel's visibility applied again;
    - dates are ISO strings and amounts are numbers with `currency` alongside; the web formats both per C8;
    - the web renders it as `TableCard` on the design system's `Table` (tabular figures, as the Archive `ResultsTable`);
    - a document row whose subject is gone is left out.
  - **C2:**
    - `GET /api/exports/{id}/table` returns `TableView` (the card's refresh);
    - `POST /api/exports/{id}/file` with `{format: 'csv' | 'xlsx' | 'docx'}` builds a file from the stored spec, using A31's builders and up to 500 rows. It returns 201 with the new `ExportPack` (with `fileUrl`) and writes the activity entry with actor `user`, via `ui` (D5);
    - `404` for an id that isn't a table; `409 conflict` with `details.reason: "empty"` when no spec document is still visible.
  - **C3 §6.2:** a new note kind `table.download`: `Downloaded the table "{title}" as {FORMAT} ({n} rows).`
  - **SOUL:** "a table" means the inline card; a file only on request.
- **Why:** "show me a table" made an Excel file 3 times out of 3 (FIX-12). Andrei wants the table in chat, built by the server so that no value is copied out by the model (D20, D18).
- **Lanes:** L2/L4/L3 (FIX-13).

## A37 · 2026-11-09 · C9 §5.3, C7 §8.4, C1 §4 (A24): purge vs a sha256 twin; a per-sha256 lock

- **Change:**
  - **C9 §5.3 step 1:** the cache unlink (`<sha>.pages.json`, `.ocr.pdf`, `.p1.png`, `.model.*.json`) is skipped while another `documents` row has the same sha256, live or deleted (an undo can restore a deleted one). The document's own file is still unlinked.
  - **The lock:** the intake dedupe-and-insert for one file (C2 §5.1, C7 §8.4) and the A24 undo-of-delete check-and-restore both take a transaction-scoped advisory lock on the sha256 first (`pg_advisory_xact_lock` on a stable 64-bit hash of `'sha256:' || sha256`).
    - The loser of a race sees the winner's row: intake gives `duplicate`, and undo gives A24's 409 `conflict` (`details.reason: "duplicate"`).
    - A unique violation on the A24 index that still occurs maps to those outcomes, never a 500.
- **Why:**
  - FIX-6 found that purging a visitor document deletes caches a same-bytes twin still uses.
  - An upload landing between the undo check and its write gave a 500.
- **Lanes:** L1/L2 (FIX-14).

## A38 · 2026-11-09 · C9 §6.3 step 1, §6.6: a snapshot from an older schema is restored and migrated forward

- **Change:**
  - Every snapshot verify (`demo-reset`, `demo-snapshot --refresh-textcache`, the §6.6 restore) accepts an `alembic_revision` that is the head **or an ancestor of the head** in the migration chain.
  - The restore is otherwise unchanged. Step 3's `mona migrate` brings the database to head, and the snapshot on disk is not rewritten.
  - The reset report names the step (`schema 0009 → 0010`).
  - A revision outside the chain (newer than this release, or unknown) is refused: "the snapshot is from a newer or unknown schema version; update Mona or rebuild it".
  - The §6.2 checks and the identical-twice proof hold for a migrated restore.
  - **Test obligation:** every new migration upgrades a database restored from a snapshot one revision older.
- **Why:**
  - FIX-13's migration 0010 would have made the Oct 6 stage snapshots refuse to restore, and a rebuild means a newly approved debrief (D16).
  - Early-adopter deployments need backups that restore across upgrades (D21). Andrei's ruling, 2026-11-09.
- **Lanes:** L5/L6 (FIX-14).
