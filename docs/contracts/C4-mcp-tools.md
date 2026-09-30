# C4 · MCP tool catalog

| | |
|---|---|
| Version | 1.0 |
| Status | **Frozen** (set A verdict: Andrei, 2026-09-30) |
| Freeze | 2026-09-30 |
| Change rule | Amend via `docs/contracts/amendments.md`, orchestrator only |
| Consumers | L2 (implements the server and the Hermes config), L4 (implements the intelligence tools' jobs), L1 (file ops, pipeline entry), L3 (card payloads it will render) |
| Depends on | C1 (tables, DTOs), C3 (`card_events`, cards), C5 (rules, templates), C7 (file ops, undo). Forward: C2 (REST equivalents), C6 (interview semantics), C9 (visibility filter, egress) |

Evidence: S1/S2 (`docs/spikes/s1/`): Hermes 0.21.5 names our tools `mcp__<server>__<tool>`, wraps each result as `{"result": "<JSON string>"}` inside an `<untrusted_tool_result>` block, and never streams results. S2's 12-call outlier came from a toy search without an entity filter plus the Hermes utility `list_resources`. D5 sets the demo toolsets and the journal actor.

**Changes in 0.2**
- Hermes toolsets: `api_server: [memory, mona]` (D5), `telegram: [memory, mona_tg]`, and `cron: [mona_tg]` so the 07:30 brief runs on the Telegram channel with no other tools (§1.3; F11, F12, F22, F32).
- Journal actor = who executed: every MCP write is `mona` (§2.7; D5, closes F17).
- `start_interview` and `export_accountant_pack` return the existing job for the same scope with a fresh card; `busy` is gone (§2.4, §3.6, §3.13; F2, F6).
- `answer_question` returns one rule and one preview per branch (§3.7; F10, S6). Preview and apply follow C5's precedence; an applied preview keeps its numbers (§3.8, §3.9; F7, F18).
- `get_brief` is stateless: `since` defaults to 24 h ago (§3.15; F16, F31, F38).
- Telegram visibility covers rules, undo and the Visitors export (§2.6; F51).
- Attachments: `ATTACH_ROOT` is Hermes' media cache; the guard walks components with `openat` and never blocks on a FIFO (§3.14, §4.2; F23, F52, F54).
- CSV cells can't start a formula (§3.13; F58). Corrections can't target Visitors (§3.5; F21).
- Open questions 1–5 adopted as proposed; 6 answered with C1's; 7 is L2's measurement.
- Post-verify fixes (orchestrator): the seeded Hermes profile ships `cache/documents/` and `cache/images/` for the subpath mount; `answer_question` previews list at most 2 moves each.

## 1. Server

### 1.1 Transport and auth
- FastMCP 4.0.10, streamable HTTP, mounted at `/mcp` on the api service (port 8765, compose network only; C9 keeps it off the public proxy).
- Every request needs `Authorization: Bearer $MONA_SERVICE_KEY` (≥ 32 characters), compared with `hmac.compare_digest`. Missing or wrong → HTTP 401 `{"error": "unauthorized"}` before MCP handling, and a log line without the header value.
- The service key bypasses the screen lock (C2's 423 applies to browser sessions only).
- Request bodies over 64 KiB → 413.
- The server registers tools only: no resources, no prompts, no sampling.

### 1.2 Channel
Each request carries `X-Mona-Channel: web | telegram`, set per MCP server entry in the Hermes config (§1.3), never by the model. A missing or unknown value is treated as `telegram` (the more restrictive one). Hermes cron jobs (the 07:30 brief) use the `mona_tg` entry, so they are `telegram`. The channel:
- decides `via` on journal entries (`chat` for web, `telegram`) and `card_events.channel`;
- is the input to the visibility filter (§2.6);
- makes Telegram-originated `card_events` never attach to a web turn (C3 §5.2).

### 1.3 Hermes-side config (`deploy/hermes/config.yaml`, from `docs/spikes/s1/config.spike.yaml`)
```yaml
mcp_servers:
  mona:
    url: "http://api:8765/mcp"
    headers:
      Authorization: "Bearer ${MONA_SERVICE_KEY}"
      X-Mona-Channel: "web"
    sampling: {enabled: false}
    tools: {resources: false, prompts: false}
  mona_tg:                      # added with the owner bot (S4)
    url: "http://api:8765/mcp"
    headers:
      Authorization: "Bearer ${MONA_SERVICE_KEY}"
      X-Mona-Channel: "telegram"
    sampling: {enabled: false}
    tools: {resources: false, prompts: false}
platform_toolsets:
  api_server: [memory, mona]    # D5: skills and todo off for the demo
  telegram: [memory, mona_tg]
  cron: [mona_tg]               # naming an MCP server makes the list an allowlist
tools:
  tool_search: {enabled: false}
```
- `tools: {resources: false, prompts: false}` was read from Hermes source in S1, not exercised; L2 verifies that `list_resources`/`read_resource`/`list_prompts` no longer appear in the model's tool list (§5 item 2).
- **Cron.** Without a `cron` entry, Hermes 0.21.5 gives cron jobs its default CLI bundle (terminal, web, browser, code execution, …) plus every MCP server, including the web-channel `mona` (gate finding F12, reproduced with `_get_platform_tools` on the pinned image). With `cron: [mona_tg]` a cron turn resolves to exactly `mona_tg` (re-checked at the fold). Hermes then logs once "platform 'cron' has no valid toolsets configured (unknown name(s): mona_tg)": that warning is about native toolsets and is expected; the MCP server still resolves. The brief's cron job is created without its own `enabled_toolsets`, or with exactly `[mona_tg]`. §5 item 13 is the binding check that the cron agent can call `get_brief`; if it can't, the fallback is `cron: [memory, mona_tg]`, which resolves to exactly those two.
- `memory` on Telegram follows plan §3; whether Telegram sessions may see memories written from web chat is C9's call.
- The model and provider keys of the same file follow D4 (`provider_routing.only`/`order`/`require_parameters`); they are not C4's.

## 2. Conventions

### 2.1 Names and shapes
- Tool names and every parameter and result key are `snake_case` (C1 §1.1). The model sees them prefixed (`mcp__mona__search_documents`); the adapter strips `mcp__<server>__` (C3 §4.3).
- Every result is one JSON object, returned as MCP structured content and as its JSON text.
- Dates `YYYY-MM-DD`; timestamps ISO 8601 UTC; amounts as JSON numbers with `currency`; confidence 0–100.
- `entity` values in results are `{"key", "name"}`; categories are `{"id", "label"}` with the label in English (the model translates when it answers).

### 2.2 Results carry ids and facts, never documents
Results return ids plus the compact facts needed to answer: titles, entity and category names, counterparty, dates, amounts, totals, counts, statuses, paths. **Never** page text, OCR text, quotes longer than 160 characters, raw model output, IBANs or file bytes. Evidence quotes appear only where a tool says so (at most 3 per result).

### 2.3 Size caps and pagination
- A serialised result is at most **4,000 characters**. List tools drop items from the end to fit and set `"truncated": true`.
- List tools take `limit` (default 10, max 25) and `cursor` (opaque string from a previous `next_cursor`), and return `total`, `next_cursor` (null when done).
- A cursor encodes the offset and a hash of the other parameters; a cursor reused with different parameters → `invalid_argument`.

### 2.4 Errors
A failed call returns an MCP error result (`isError: true`) whose text is:
```json
{"error": {"code": "invalid_argument", "message": "Unknown entity 'SCI Marchand'.", "hint": "Use one of the valid values.", "field": "entity", "valid": [{"key": "cabinet", "name": "Cabinet Marchand"}]}}
```
| code | When | Notes |
|---|---|---|
| `invalid_argument` | bad or unresolvable parameter | `field`; `valid` lists the accepted values when the set is small (entities, categories, ≤ 30 items) |
| `not_found` | unknown id; deleted; or not visible on this channel | the same code for all three, so visibility never leaks |
| `forbidden_path` | `ingest_attachment` path outside the attachment volume | §4.2 |
| `not_allowed` | the action is not allowed for this entity or channel | e.g. export of a personal entity |
| `conflict` | the state changed under the call (`stale`), a rule is invalid, `collision_exhausted`, a filesystem error (C7 §4.2; the errno name in `hint`) | `hint` says what to re-read |
| `internal` | anything unexpected | generic message; details only in the server log |

Messages are one English sentence for the model. They never contain document text or identifiers beyond ids and names.

### 2.5 Cards
A card-producing tool writes one `card_events` row per card (C1 §7, C3 §5.2) in the same transaction as its effects, and returns the ids in `"card_refs": ["crd_…", …]` (always present on those tools, possibly empty). The card thresholds in §3 keep chat readable.

### 2.6 Visibility (filter point for C9)
Tools marked **[V]** pass every document, deadline, entity, rule and journal entry through `visible(row, channel)` before counting, summing or listing. Until C9 freezes, on `web` everything is visible; on `telegram`:
- a document, deadline or entity is invisible when its entity has `visibility='personal'`;
- a rule is invisible when its action's entity is personal, or any condition names a personal entity (`entity`, `addressee is_entity`, `iban entity`, `siren entity`), an account of a personal entity, or a person linked to a personal entity (`entity_people` or a sub-unit's `person_id`);
- a journal entry or group is invisible when any of its documents or its rule is invisible (so `undo` can't act on it or reveal its paths).

Invisible rows behave as if absent (`not_found`, excluded from totals). The accountant export refuses personal entities and the Visitors entity on every channel (plan §9, C1 §2.1).

### 2.7 Side effects and egress
- Write tools journal every change (C7) with `actor='mona'` and `via` from the channel (`chat` or `telegram`): the actor is who executed (D5, C1 §5), even when the person asked for it in words. Answers given through a tool (`answer_question`) are `actor='mona'` too.
- **No tool sends anything outside the box (R32).** No tool opens a network connection other than to Postgres and the local LLM endpoint used by the jobs they enqueue. Drafts are never sent; exports are written under `/data/exports`.
- There is no delete tool (C7 §7).

### 2.8 Time budget
Every tool returns within 10 s. Work that takes longer (interview generation, drafting, export building) is enqueued and returns `status: "generating"|"building"`; the card follows progress through REST polling (C2/C6). Hermes' own MCP tool-call timeout is unknown; L2 measures it on the pinned image and reports it (it must stay well above 10 s).

### 2.9 Call-budget guidance
Descriptions steer the model to **≤ 2 calls for a typical demo turn**: filters on `search_documents` and `sum_amounts` so one call answers "how much did we pay X in 2025"; list results already carry the facts `get_document` would add; errors list valid values so the model doesn't guess again.

## 3. Tools

Each tool lists: the description the model sees (verbatim, English), parameters (JSON Schema, `additionalProperties: false`), result, cards, errors beyond `internal`, side effects and idempotency. **[V]** = visibility filter (§2.6).

Common filter parameters (§3.1 and §3.3 share them):

| Param | Type | Meaning |
|---|---|---|
| `entity` | string | entity key, display name, folder name or alias: `norm()` equality with any of them, else a unique trigram match ≥ 0.5 on display name; unresolvable → `invalid_argument` with `valid` = all visible entities |
| `category` | string | category id or a label in any language; unresolvable → `invalid_argument` with `valid` |
| `counterparty` | string | matches every counterparty whose `name_norm` or an alias whole-word contains `norm(value)` (C5 §2); none → empty result, not an error |
| `year` | integer 2000–2100 | year of `doc_date` |
| `fiscal_year` | integer 2000–2100 | `documents.fiscal_year` |
| `date_from`, `date_to` | date | inclusive bounds on `doc_date` |
| `amount_min`, `amount_max` | number ≥ 0 | inclusive bounds on `amount` (EUR/RON only) |
| `status` | `"filed" \| "review" \| "any"` | default `"any"`; `processing` documents are always excluded |

### 3.1 `search_documents` [V]
**Description:** "Search the practice's archive. Filter by entity, category, counterparty, year or fiscal year, date range and amount range; add a free-text query for words in the documents. Results already include title, entity, category, counterparty, date, amount and status, so call get_document only when you need a field not listed here. If you need a total, call sum_amounts with the same filters instead of summing yourself. Up to three results are shown to the person as document cards."

| Param | Type | Req |
|---|---|---|
| `query` | string, 1–200 chars | no |
| common filters | | no |
| `limit`, `cursor` | §2.3 | no |

Result:
```json
{"total": 2, "next_cursor": null,
 "results": [{"id": "doc_…", "title": "AGIPI PER avis d'échéance", "entity": {"key": "personal", "name": "Personnel"},
              "category": {"id": "insurance", "label": "Insurance"}, "counterparty": "AGIPI",
              "date": "2025-04-14", "amount": 520.0, "currency": "EUR", "due_date": null, "status": "filed"}],
 "card_refs": ["crd_…", "crd_…"]}
```
- Order: `ts_rank` on `fts` when `query` is set, else `doc_date` descending (nulls last).
- Cards: one `doc` card per result when `1 ≤ total ≤ 3`.
- Errors: `invalid_argument`.
- Read-only.

### 3.2 `get_document` [V]
**Description:** "Get one document's facts: fields with whether each was verified on the page, where it is filed, the rule that filed it, and its deadlines. Use it when the person asks about a specific document or you need a field the search results don't have. Shows the document as a card."

| Param | Type | Req |
|---|---|---|
| `document_id` | string `doc_…` | yes |

Result:
```json
{"id": "doc_…", "title": "…", "status": "filed", "entity": {"key": "…", "name": "…"}, "sub_unit": "Paul",
 "category": {"id": "insurance", "label": "Insurance"}, "subcategory": "PER", "counterparty": "AGIPI", "issuer": null,
 "reference": "C-48213", "doc_type": "avis d'échéance", "doc_date": "2025-04-14", "period_start": null, "period_end": null,
 "fiscal_year": 2025, "amount": 520.0, "currency": "EUR", "due_date": null, "addressee": "M. Paul Marchand",
 "path": "Personnel/Paul/Assurances/AGIPI/PER/2025/2025-04-14_AGIPI_PER_C-48213.pdf",
 "filed_by": "mona", "filed_at": "…", "rule": {"id": "rul_…", "name": "…"}, "confidence": 95, "band": "high",
 "reasons": [], "unverified_fields": ["due_date"], "deadline_ids": [], "page_count": 2,
 "card_refs": ["crd_…"]}
```
- Cards: one `doc` card.
- Errors: `not_found`.
- Read-only.

### 3.3 `sum_amounts` [V]
**Description:** "Add up document amounts, either for a list of document ids or for the same filters as search_documents (entity, category, counterparty, year, fiscal year, dates, amounts). One call answers 'how much did we pay X in 2025'. Amounts are what the documents state (billed or due); the archive doesn't record whether they were paid, so say so when it matters. Documents without an amount are listed as excluded. Up to five documents are shown as cards."

| Param | Type | Req |
|---|---|---|
| `document_ids` | string[] of `doc_…`, 1–100 | no |
| common filters | | no |

Exactly one of `document_ids` or at least one filter; neither or both → `invalid_argument`.

Result:
```json
{"count": 2, "totals": [{"currency": "EUR", "total": 1720.0}],
 "document_ids": ["doc_…", "doc_…"], "listed": 2,
 "excluded": [{"id": "doc_…", "reason": "no_amount"}],
 "card_refs": ["crd_…", "crd_…"]}
```
- Summed in SQL over `numeric`; `totals` has one entry per currency (EUR, RON).
- `document_ids` lists at most 25 (`listed` says how many); `excluded` at most 10, reasons `no_amount | not_found | other_currency`.
- Cards: one `doc` card per document when `1 ≤ count ≤ 5`.
- Errors: `invalid_argument`. Read-only.

### 3.4 `list_review_queue` [V]
**Description:** "List documents waiting for the person's review, with why each is waiting (low confidence, unknown entity, conflicting rules, unreadable) and your current suggestion. Use it for 'what needs my attention'. Up to three are shown as cards; the Review page has the rest."

| Param | Type | Req |
|---|---|---|
| `reason` | `"low" \| "entity" \| "conflict" \| "unreadable"` | no |
| `limit`, `cursor` | §2.3 | no |

Result: `{"total", "next_cursor", "items": [{"document_id", "title", "reasons": [...], "suggestion": {"entity": {...} | null, "category": {...} | null, "confidence": 48}, "arrived_at"}], "card_refs"}`. Oldest first.
- Cards: one `doc` card per item when `1 ≤ total ≤ 3`. Read-only.

### 3.5 `correct_document` [V]
**Description:** "Apply a correction the person has stated for one document (entity, category, subcategory, counterparty or a field value), then re-file it with its new name. Use it only for a correction the person gave you, not to change your own mind. With scope 'all', also prepare a rule for every document from the same counterparty and show its preview; the rule is not active until applied."

| Param | Type | Req |
|---|---|---|
| `document_id` | `doc_…` | yes |
| `entity` | string (as §3 common filter) | no |
| `sub_unit` | string: sub-unit key or label within the entity | no |
| `category` | string | no |
| `subcategory` | string: key or label within the category | no |
| `counterparty` | string ≤ 160 | no |
| `doc_date`, `period_end`, `due_date` | date | no |
| `amount` | number ≥ 0, with `currency` `"EUR" \| "RON"` | no |
| `scope` | `"one" \| "all"`, default `"one"` | no |

At least one correction field is required.

Behaviour:
1. Writes a classification with `method='user'` (the person's correction, executed by Mona: the journal actor is still `mona`, §2.7) and the corrected values (fields the call omits are kept); a counterparty correction resolves through C5 §6.2 and teaches the alias (C5 §6.2.5); field values → `doc.update` entry. `fiscal_year` is recomputed (C5 §8.2).
2. Re-renders and moves (C7): `file` if the document was in the inbox, else `move`/`rename`; group kind `correction`. The document ends `filed`; its open review item closes with `resolution='corrected'`, passed to `mona.fileops` (C7 §4.2 C.3).
3. The previous `rule_id`'s `corrections_since` increments (C5 §4.8).
4. `scope: "all"`: creates a rule, `state='draft'`, `source='correction'`, conditions `[{"field": "counterparty", "op": "equals", "value": <counterparty key>}]`, action = the corrected entity/sub-unit/category/subcategory, priority per C5 §4.6.1 (above the rules that matched this document); then computes its preview (§3.8). No counterparty → `invalid_argument` (`field: "scope"`).
5. The Visitors entity is never a valid `entity` value here, and a document of a visitor batch can't change entity: `not_allowed` (C1 §2.1).

Result: `{"document_id", "outcome": "moved" | "unchanged", "path", "journal_ids": [...], "group_id", "rule": {"id", "state": "draft"} | null, "preview": {§3.8 result} | null, "card_refs"}`.
- Cards: `doc` card (scope one) or `rulePreview` card (scope all; its part id is the rule's, C3 §5.5).
- Errors: `not_found`, `invalid_argument`, `not_allowed`, `conflict` (`stale`, `collision_exhausted`, filesystem errors).
- Idempotent: the same correction again → `outcome: "unchanged"`, no entries; scope `all` again → returns the existing draft rule for that counterparty and action.

### 3.6 `start_interview`
**Description:** "Show or start a short interview (at most seven grouped questions) about documents you were unsure of: after a batch, for the review queue, or for one counterparty. If questions for that scope are ready or being prepared, this shows them instead of starting again. It appears as an interview card that fills in by itself; tell the person the questions are here or coming, and don't wait for them."

| Param | Type | Req |
|---|---|---|
| `batch_id` | `bat_…` | one of the four |
| `queue` | `true` (the whole review queue) | |
| `counterparty` | string | |
| `document_ids` | `doc_…`[] 1–50 | |
| `lang` | `"en" \| "fr" \| "ro"`, default the `reply_language` of the web turn this call is attributed to (C3 §5.2), else the profile locale | no |

Result: `{"interview_id": "int_…", "status": "generating" | "ready", "open_questions": 5 | null, "reused": true | false, "card_refs": ["crd_…"]}`.
- **Reuse first.** If an interview for the same scope has `status='generating'`, or `status='ready'` with at least one open question, the tool returns it (same `interview_id`, its current status) and writes a fresh `interview` card; it never enqueues a second job. For a batch scope, the batch's `debrief_interview_id` is checked first. Scope equality is C6's; for `batch_id` it is the same batch.
- Otherwise it creates the interview and enqueues `generate_interview` (C5 §1.2 priority 10). Semantics, scope rules and the question schema are C6's.
- This is how the batch debrief generated at the end of the batch reaches chat: the `BatchQuestionsBanner` opens chat with a fixed message and a `pageContext` naming the batch id (C3 §2), and the model calls `start_interview(batch_id)`. A debrief cached in the demo snapshot is bound to the live batch by C6/L5b through document sha256s, since document ids are fresh ULIDs on every run (C1 §1.2).
- Cards: `interview` card (part id = interview id; the card polls C2 until `ready`).
- Errors: `invalid_argument` (zero or several scopes; empty scope).
- Idempotent per scope while the interview is generating or has open questions.

### 3.7 `answer_question`
**Description:** "Record the person's answer to an interview question when they give it in words instead of pressing a button. Pass the option they chose, or their own words if none fits. The resulting rule is shown as a preview; nothing moves until it is applied."

| Param | Type | Req |
|---|---|---|
| `question_id` | `qst_…` | yes |
| `option_id` | string | one of the two |
| `free_text` | string ≤ 500 | |

Result: `{"question_id", "status": "answered", "rules": [{"id", "state": "draft"}], "previews": [{§3.8 result}], "card_refs"}`: one rule and one preview per branch of the chosen option's `rule_draft` (C1 §11.5), in branch order; both lists empty when no rule results.
- Semantics (option → rule draft, "ask me each time", free-text handling) are C6's. Journals one `rule.create` per rule. Each rule's `origin_question_id` is the question (C1 §6.1); its priority follows C5 §4.6.1.
- Cards: one `rulePreview` per rule (part id = rule id).
- Size: each preview here lists at most 2 `moves` (`moves_total` kept, `"truncated": true` when cut) so a multi-branch answer stays under the §2.3 cap; the cards fetch the full lists through C2.
- Errors: `not_found`, `invalid_argument`, `conflict` (already answered: the existing answer is in `hint`).
- Idempotent: the same answer again → the existing result.

### 3.8 `preview_rule` [V]
**Description:** "Show what a rule would move: how many documents would move, how many already match, and a few before → after paths. Use it before apply_rule when the person hasn't seen a preview yet."

| Param | Type | Req |
|---|---|---|
| `rule_id` | `rul_…` | yes |

Result:
```json
{"rule_id": "rul_…", "name": "…", "state": "draft", "condition_text": "When the counterparty is AGIPI and …",
 "moves_total": 4, "stays_total": 2,
 "moves": [{"document_id": "doc_…", "title": "…", "from": "Personnel/Assurances/AGIPI/2025/…pdf", "to": "Personnel/Paul/Assurances/AGIPI/PER/2025/…pdf"}],
 "card_refs": ["crd_…"]}
```
- Candidates: non-deleted documents with status `filed` or `review` whose conditions hold (C5 §4.2) and for which this rule, treated as active, would win without conflict (C5 §4.6.9). A candidate whose rendered target equals its current path "stays"; otherwise it "moves" (inbox documents move into the archive).
- Once the rule has been applied, the result (and the card) describe that application instead: C1 §11.5 `RulePreview` "Applied".
- `moves` lists at most 5 (the card fetches the full list through C2).
- Cards: `rulePreview` (part id = rule id). Read-only.

### 3.9 `apply_rule` [V]
**Description:** "Activate a rule and re-file the documents it matches, as shown by its preview. Every move is journaled and the whole application can be undone in one step. Use it only after the person has agreed to the preview."

| Param | Type | Req |
|---|---|---|
| `rule_id` | `rul_…` | yes |

Behaviour: sets `state='active'` (`rule.change` entry if it changed), then files/moves every "moves" candidate of §3.8 (C7) in one group, kind `rule_apply`, `rule_id` = this rule; each moved document gets `rule_id` = this rule and counts a firing (C5 §4.8); review items close with `resolution='rule_applied'`.

Result: `{"rule_id", "group_id": "grp_…" | null, "moved": 4, "unchanged": 2, "failed": [{"document_id", "code"}], "card_refs": ["crd_…"]}`.
- Cards: the same `rulePreview` card (same part id), now `applied: true`, with `moves` and `movesTotal` from the group and `staysTotal` = the candidates outside it (C1 §11.5), so it keeps showing "4 move · 2 stay".
- Errors: `not_found`, `conflict` (rule invalid).
- Idempotent: a second call moves nothing (`moved: 0`, `group_id: null`).

### 3.10 `list_deadlines` [V]
**Description:** "List upcoming payment and reply deadlines with amount, entity and days left, including overdue ones. Use it for 'what's due'. Up to five are shown as cards."

| Param | Type | Req |
|---|---|---|
| `within_days` | integer 0–366, default 30 | no |
| `entity` | string (§3 common) | no |
| `include_overdue` | boolean, default true | no |
| `limit`, `cursor` | §2.3 | no |

Result: `{"total", "next_cursor", "items": [{"deadline_id", "document_id", "label", "entity": {...}, "due_date", "days_left", "amount", "currency", "status": "open", "reminder_on": null}], "card_refs"}`. Open deadlines only, soonest first; `days_left` in Europe/Paris.
- Cards: one `deadline` card per item when `1 ≤ total ≤ 5`. Read-only.

### 3.11 `schedule_reminder` [V]
**Description:** "Schedule a reminder for a deadline or a document on a given day; it appears in the morning brief that day. Offer it after mentioning a deadline; schedule it when the person agrees."

| Param | Type | Req |
|---|---|---|
| `deadline_id` | `ddl_…` | one of the two |
| `document_id` | `doc_…` | |
| `remind_on` | date, today or later | yes |
| `note` | string ≤ 200 | no |

Result: `{"reminder_id", "remind_on", "deadline_id" | null, "document_id" | null, "created": true | false, "card_refs"}`.
- Side effects: `reminders` row (`created_by='mona'`), `reminder.add` entry.
- Cards: the `deadline` card when a deadline is involved, else the `doc` card.
- Errors: `not_found`, `invalid_argument` (date in the past).
- Idempotent on (target, `remind_on`): returns the existing reminder, `created: false`.

### 3.12 `draft_reply` [V]
**Description:** "Draft a reply to a letter (for example asking the tax office for a payment schedule). The draft is written in the background and appears as a card the person can copy or download; you never send anything, and neither does the app. Unknown details stay as [BRACKETS]."

| Param | Type | Req |
|---|---|---|
| `document_id` | `doc_…` | yes |
| `lang` | `"en" \| "fr" \| "ro"`, default `settings.filing_language` | no |
| `instructions` | string ≤ 500 | no |

Result: `{"draft_id": "drf_…", "status": "generating", "card_refs": ["crd_…"]}`.
- Enqueues `generate_draft` (L4); the job reads the document's cached text, which never enters the tool result.
- Cards: `draft` card (part id = draft id; polls C2).
- Errors: `not_found`.
- Not idempotent: each call is a new draft.

### 3.13 `export_accountant_pack` [V]
**Description:** "Build the accountant pack for one company entity and fiscal year: a zip of its documents and a CSV index, written to the exports folder on this computer. It runs in the background and appears as a card; nothing is sent. Personal entities and Visitors can't be exported."

| Param | Type | Req |
|---|---|---|
| `entity` | string (§3 common) | yes |
| `fiscal_year` | integer 2000–2100 | yes |

Result: `{"export_id": "exp_…", "status": "building", "document_count": 37, "card_refs": ["crd_…"]}`.
- Contents and layout are L4's; files go under `/data/exports` only. Documents are selected by `documents.fiscal_year`, which every classified document has (C5 §8.2).
- **CSV cells are data, never formulas:** any cell whose first character is `=`, `+`, `-`, `@`, TAB or CR is prefixed with `'`. Titles, counterparties and references come from document text and could otherwise run as formulas in the accountant's spreadsheet.
- If an export for the same entity and fiscal year is `building`, the tool returns it (same `export_id`) with a fresh card instead of starting another.
- Cards: `export` card (part id = export id).
- Errors: `invalid_argument`, `not_allowed` (personal entity or the Visitors entity, any channel).
- Idempotent while building.

### 3.14 `ingest_attachment`
**Description:** "Add a file the person sent you on Telegram to Mona's intake, using the exact path the attachment was saved to. Set for_visitor when the person says the document belongs to a visitor at an event; it is kept apart and removed after 24 hours. Tell the person it is being read; it shows up in Intake."

| Param | Type | Req |
|---|---|---|
| `path` | string ≤ 1024: absolute (under `ATTACH_ROOT`, §4.2), or relative to it | yes |
| `for_visitor` | boolean, default false | no |

Behaviour: the path guard (§4.2) → size ≤ 25 MB → type sniffed from the bytes (PDF, JPEG, PNG) → copy (never move) into the inbox → the C2 intake path (sha256, dedupe, document, `extract_text`), in a new batch with `source='telegram'` and `visitor = for_visitor`.

Result: `{"batch_id", "outcome": "accepted" | "duplicate" | "rejected", "document_id" | null, "deleted": true | false, "reject_reason" | null, "card_refs"}`. `deleted` is true when the duplicate is a document in the trash (C7 §8.4); Mona says so, and the person can restore it from Intake or the Activity log.
- Cards: `doc` card when accepted, or duplicate of a visible, non-deleted document.
- Errors: `forbidden_path`, `invalid_argument` (not a file).
- Idempotent by content: the same bytes again → `duplicate` with the existing document.

### 3.15 `get_brief` [V]
**Description:** "Get the facts for the morning brief: what was filed in the last 24 hours (or since a time you pass), what needs review, what is due soon, what you learned, and pending questions. Write the brief from these facts, amounts and due dates first, one short paragraph."

| Param | Type | Req |
|---|---|---|
| `since` | timestamp; default: 24 h before the call | no |

Result:
```json
{"generated_at": "…", "since": "…",
 "filed": {"count": 12, "by_entity": [{"key": "cabinet", "name": "Cabinet Marchand", "count": 9}]},
 "needs_review": {"count": 2, "by_reason": {"low": 1, "entity": 1}},
 "due_soon": [{"deadline_id", "label", "entity": {...}, "due_date", "days_left", "amount", "currency"}],
 "reminders_today": [{"reminder_id", "label", "note"}],
 "learned": [{"rule_id", "name", "created_at", "fired_since": 3}],
 "pending_interview": {"interview_id", "open_questions": 5} | null}
```
- `due_soon`: open deadlines due within 7 days plus overdue ones, at most 5.
- **Stateless.** No call time is stored; every caller gets the same answer for the same `since`. The 07:30 cron uses the 24 h default; C2's Home endpoint passes its own window (e.g. since the previous local midnight) so a warm-up turn or a page load never changes what the next brief says.
- Home's `MonaBrief` is rendered by the web from these facts with i18n templates, no stored prose (C1 §13); Hermes' cron uses them for the Telegram brief (C9: no names or amounts on its first line), through `mona_tg`, so on `telegram` (§1.3).
- `learned` lists rules visible on the channel (§2.6).
- Read-only.

### 3.16 `undo` [V]
**Description:** "Undo one journal entry or a whole group (a batch, a rule application) when the person asks you to. Entries that were changed again since are skipped and reported. Undoing an undo redoes it. Say exactly what was undone."

| Param | Type | Req |
|---|---|---|
| `journal_id` | integer ≥ 1 | one of the two |
| `group_id` | `grp_…` | |

Result: `{"group_id": "grp_…" | null, "undone": [{"journal_id", "document_id", "title", "to": "<path>"}], "skipped": [{"journal_id", "state": "superseded" | "already_undone" | "not_undoable" | "not_allowed"}]}`.
- Semantics: C7 §5.3 (entry; undo acts on the tip of the entry's undo chain), §5.4 (group). `actor='mona'`. [V]: on `telegram`, an entry or group touching an invisible document or rule is `not_found` (§2.6).
- A step whose target is the trash (undoing the restore of a deleted document) is refused by C7 (`not_allowed`, reported under `skipped` for a group): Mona never deletes.
- No cards.
- Errors: `not_found`, `invalid_argument` (neither or both ids), `not_allowed`.
- Idempotent: undoing an undone entry returns it under `skipped` with `already_undone`; nothing changes.

## 4. Guards

### 4.1 Untrusted input
Every parameter is validated against the schema before any work (FastMCP + pydantic). Ids must match their prefix pattern (C1 §1.2). String parameters are never interpolated into SQL, shell commands or paths except through §4.2.

### 4.2 `ingest_attachment` path guard
The model-supplied path is untrusted.

**Where attachments are.** Hermes 0.21.5 caches Telegram media under `$HERMES_HOME/cache/` (D3: `/opt/data`), as `documents/doc_<uuid12>_<original name>` and `images/img_<uuid12>.<ext>`, and hands the model that absolute path; the directory isn't configurable. So `ATTACH_ROOT = /opt/data/cache`, mounted **read-only** into the api container at that same absolute path through a subpath of the Hermes profile volume (never the whole profile: it holds `.env` and `state.db`). Hermes prunes both subtrees hourly after 24 h, which also covers R38 for the attachment copy. Hermes creates `cache/documents/` and `cache/images/` lazily, and a volume-subpath mount of a missing path stops the api from starting, so the seeded profile (`deploy/hermes/`) ships both directories empty and the seed step creates them on a fresh volume. S4 verifies the mount, the names and a fresh-volume start on the pinned image.

1. Reject NUL and `\`; reject length > 1024.
2. If relative, join it to `ATTACH_ROOT` (resolved with `realpath` at startup).
3. `real = os.path.realpath(candidate)`. It must start with `ATTACH_ROOT + "/documents/"` or `ATTACH_ROOT + "/images/"`; otherwise `forbidden_path`. This rejects `..`, absolute paths elsewhere, other cache subtrees, and symlinks (anywhere in the chain) pointing outside.
4. If `real` doesn't exist and its file name starts with `doc_<12 hex>_` or `img_<12 hex>`, look that prefix up in its directory; exactly one match is used (the model often re-types an NFD file name in NFC). Otherwise → `invalid_argument`.
5. Open without following anything: from a descriptor of `ATTACH_ROOT`, `openat` each directory component with `O_NOFOLLOW | O_DIRECTORY`, then the file with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK`; `fstat` must show a regular file (a FIFO or device is `forbidden_path`, and `O_NONBLOCK` keeps a FIFO from blocking the open). A component swapped for a symlink after step 3 fails the `openat`.
6. Copy from that file descriptor into the inbox; the attachment is never moved, modified or deleted.
7. Log the relative path only.

### 4.3 Egress
The MCP server process has no HTTP client in its tool code paths. The LLM calls happen in the `llm` worker jobs the tools enqueue (C5 §1.2), against the configured endpoint only (C9).

## 5. Test obligations

**[M]** = mutation-checked.

1. **Auth:** no header, wrong key, key with a trailing space → 401 and no tool runs; the right key → 200.
2. **Hermes surface (L2, against the pinned image):** with §1.3's config, the model-visible tools from the `mona` server are exactly the 16 below, prefixed `mcp__mona__`, and there is no `list_resources`, `read_resource`, `list_prompts` or `get_prompt`. Hermes' own resolver (`_get_platform_tools(cfg, platform)`) gives exactly `[memory, mona]` for `api_server`, `[memory, mona_tg]` for `telegram` and `[mona_tg]` for `cron`. Captured as a fixture.
3. **Path guard [M]:** accepted: a file under `documents/` and under `images/`, relative and absolute; an NFC re-typing of an NFD name, found by its `doc_<uuid12>_` prefix. Rejected with `forbidden_path`: `../x`, an absolute path outside, a path in another cache subtree, a symlink inside the volume pointing outside, a directory symlink in the chain, a file swapped for a symlink after the realpath check, an intermediate directory swapped for a symlink after the realpath check, and a FIFO (the call returns without blocking). Mutation: compare without the trailing `/` (so `/opt/data/cache/documents-evil` passes) → a test must fail; open with plain `open(real)` → the directory-swap test must fail.
4. **Schemas:** each tool's input schema rejects unknown keys and wrong id prefixes; each result validates against a pydantic model in the test suite; every result for the C5 §8.5 fixture registry is ≤ 4,000 characters.
5. **Filters:** `search_documents` and `sum_amounts` with each common filter alone and combined, over a fixture set; `entity` by key, name and alias; an unknown entity returns `valid` with all visible entities.
6. **Cards:** each card-producing tool writes the stated number of `card_events` rows with the right `kind`, `subject`, `channel`, and returns their ids in `card_refs`; below/above each threshold.
7. **Visibility [M]:** on `telegram`, a personal-entity document is `not_found` in `get_document`, absent from search totals and sums, and absent from `get_brief`; a rule whose action is personal (or that names a personal person or account) is absent from `get_brief.learned`; `undo` of an entry or group touching a personal document is `not_found`; on `web` all are present. Export of a personal entity or of Visitors → `not_allowed` on both channels. Mutation: invert the channel default → a test fails.
8. **Write tools journal:** `correct_document`, `apply_rule`, `schedule_reminder`, `undo` each write the C7 entries with `actor='mona'` and the channel's `via` (D5); `apply_rule` twice → second `moved: 0`; the `rulePreview` card after `apply_rule` shows the same move and stay counts as before it.
9. **No egress:** run every tool with `socket.connect` patched to fail for any address other than Postgres; all pass (enqueueing jobs is not egress).
10. **No delete:** no tool produces a `delete` entry or any entry that moves a document to the trash, including `undo` of a restored document's restore (asserted by running each write tool and checking the journal; C7 §9 invariant 12).
11. **Budget replay (L2, dev stack):** the S2 prompt set plus the demo script's chat prompts (plan §10c): median ≤ 2 tool calls per turn, no turn above 4; recorded as a fixture with the tool names called.
12. **Reuse [M]:** `start_interview(batch_id)` on a batch whose debrief is `ready` with open questions → the same `interview_id`, a new `card_ref`, and no `generate_interview` job enqueued; the same while it is `generating`; once every question is answered, a new interview starts. `export_accountant_pack` twice while building → one export. Mutation: drop the reuse lookup → a second job appears.
13. **Cron channel (L2, dev stack):** a Hermes cron job running the brief prompt over a fixture with a personal-entity deadline calls `get_brief` with `X-Mona-Channel: telegram`, and its output names no personal document, deadline or amount.
14. **`get_brief` is stateless:** two calls in a row with no `since` return the same `filed` counts (clock injected); no table is written.
15. **CSV index:** a document titled `=HYPERLINK("http://x","OPCO")` appears in the pack's CSV as `'=HYPERLINK(…`; the same for `+`, `-`, `@`, TAB and CR.
16. **`answer_question` with a `depends` option** of two branches → two draft rules with `origin_question_id` set, two previews, two `rulePreview` cards.

## 6. Open questions

Resolved in 0.2:
- 1 (channel from the per-entry `X-Mona-Channel` header, §1.2): adopted; the gate confirmed on the pinned image that the configured `headers` dict is sent verbatim.
- 2 (personal entities invisible on Telegram until C9, §2.6): adopted, extended to rules and journal entries (F51).
- 3 (card thresholds: search ≤ 3, sums ≤ 5, deadlines ≤ 5, queue ≤ 3): adopted as stated in §3; the Oct 7 walkthrough may tune them by amendment.
- 4 ("every document like this" = same counterparty, §3.5): adopted; richer conditions come from interviews (C6).
- 5 (`draft_reply` is asynchronous, §3.12): adopted.
- 6 (brief facts, not stored prose): adopted with C1 §13; `get_brief` is stateless (§3.15).
- 7 (Hermes-side tool-call timeout): an L2 measurement (§2.8), not a gate question.

No question is still open.
