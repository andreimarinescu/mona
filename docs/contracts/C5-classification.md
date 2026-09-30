# C5 · Extraction and classification

| | |
|---|---|
| Version | 1.0 |
| Status | **Frozen** (set A verdict: Andrei, 2026-09-30) |
| Freeze | 2026-09-30 |
| Change rule | Amend via `docs/contracts/amendments.md`, orchestrator only |
| Consumers | L1 (implements all of it), L2 (rule writes, previews), L4 (debrief reuses the grammar and `norm()`), L5 (seed files, fixtures, reset check), L3 (TemplateField tokens, rule DTOs) |
| Depends on | C1 (tables, DTOs), C7 (filing). Forward: C6 (rule drafts from answers), C8 (UI strings, locale) |

Evidence used: `docs/spikes/s1/` (S1/S2), `docs/spikes/s6/README.md` and its `results/` (S6), `docs/decisions.md` D4 (provider pins, thinking off), pdf.js 6.3.289 `web/viewer.mjs` (vendored by W0), and `classify/classify_llm.py` (v2).

**Changes in 0.2**
- Sub-units come only from a winning rule's `unit` or a correction; no addressee → sub-unit inference; `unit` never falls back (§4.5, §6.2.4, §8.2, §8.5 case 4; ruling on open question 1 = report OQ 3; F1, F3, F5).
- Learned rules outrank the rules they correct; preview and apply use the same precedence (§4.6.1; F18).
- Visitors: out of the model's enum and prompt, never a rule action; the visitor override scores like a rule-set entity (§4.5, §4.6.8, §5.2, §5.3, §9.2, §9.3; F21, F25, F36).
- Model-output cache `<sha>.model.<prompt_version>.json` (§1.3; open question 7 = report OQ 7; F34).
- Filing failures land in review; batch `done` ownership; drop order (§1.2; F13, F33, F37, F39, demo-script v1).
- Pins from D4; every model string bounded; page relocation only to exactly one other page; wider punctuation folding (§2, §5.1, §5.2, §6.1; S6, D4, F20, F46).
- Alias learning upserts and merges `extracted` counterparties (§6.2.5; F19).
- `fiscal_year` always computed (§8.2; F27, F42). Folder segments capped at 255 UTF-8 bytes (§8.3; F13).
- The AGIPI and Hello bank rules are learned live, not seeded (§10, §11 test 14; demo-script v1).
- Open questions 2–6 and 8–10 adopted as proposed; 1 per the orchestrator's ruling; 7 by the model-output cache.
- Post-verify fixes (orchestrator): a review outcome ends at `pipeline_stage='done'` and runs the batch-done check (F33); visitor documents keep the Visitors entity on the unreadable and failure paths; alias merges also repoint rule actions and accounts.

## 1. Pipeline

### 1.1 Order of decisions
The model always runs, and rules decide afterwards. **Why:** every document needs its dates, amounts and quotes for naming, `{fy}` and the viewer whether or not a rule matches, and most rule conditions (counterparty, addressee) need the extracted fields. "Rules first" means rules take precedence over the model, not that they run earlier.

`intake (C2/C4) → extract_text → [render_thumbnail] → classify_document → file_document (C7) | review`

Inside `classify_document`, in this order: build prompt (§5) → model call → schema validation → evidence verification (§6.1) → resolution (§6.2) → rules (§4) → fiscal year and templates (§8) → confidence, reasons, band (§9) → `findQuery` (§7) → persist → enqueue filing or open a review item.

### 1.2 Jobs and queues
Procrastinate 3.10, one job per document per stage. `queueing_lock` = `<job>:<document_id>` so a stage is never queued twice for one document.

| Job | Queue | Priority | Retries | Sets `pipeline_stage` | Does |
|---|---|---|---|---|---|
| `extract_text` | `cpu` (concurrency 3) | 0 | 2, backoff 10 s | `reading`, then `ocr` if OCR runs | §1.4; writes the text cache and the OCR'd PDF; sets `page_count`, `head_norm`, `fts` (page text part); enqueues `render_thumbnail` and `classify_document` |
| `render_thumbnail` | `cpu` | -10 | 1 | — | `pdftoppm -r 60 -f 1 -l 1 -png -singlefile` of the viewer PDF (OCR'd copy if it exists, else the original; images: the OCR'd copy) |
| `classify_document` | `llm` (concurrency 1) | 0 | 2, backoff 5 s then 20 s, on transport errors and schema-invalid output | `classifying` | §1.1 |
| `file_document` | `cpu` | 0 | 0 (C7 recovery handles crashes) | `filing`, then `done` | C7 §4 |
| `generate_interview`, `generate_draft` | `llm` | 10 | C6 / L4 | — | listed so `llm` priority is defined: they jump ahead of classification |

- The unreadable path: if `extract_text` ends with fewer than 50 non-whitespace characters across all pages, it sets `status='unreadable'`, `reasons={unreadable}`, `pipeline_stage='done'`, opens the review item, writes a `mark.unreadable` journal entry (`actor='mona'`, `via='pipeline'`, not undoable), and does not enqueue `classify_document`.
- Classification that ends in review (any reason, §9.4): `status='review'`, `pipeline_stage='done'`, the review item opened, then the batch-done check (C1 §4.1), in the same transaction. Only filing moves a document to `filing`.
- In a visitor batch, the unreadable path and both failure paths below also set the Visitors entity, so C1 §2.1's Visitors invariant holds for documents that never reach the model.
- Final failure of `classify_document` (retries exhausted): `pipeline_stage='failed'`, `status='review'`, `reasons={low}`, review item opened, `pipeline_error` holds the error class (never document text).
- Final failure of `extract_text`: same, with `reasons={unreadable}` and `status='unreadable'`.
- Failure of `file_document` other than a crash (C7 §4.2 filesystem errors, `forbidden_path`, `collision_exhausted`), and a pipeline `file` entry that C7 recovery marks `failed`: `pipeline_stage='failed'`, `status='review'`, `reasons={conflict}`, review item opened, `pipeline_error` = the error class or errno name (`ENOENT`, `EACCES`, `ENOSPC`, `forbidden_path`, `collision_exhausted`, …). The document stays in the inbox and never remains in `filing`.
- Every transaction that moves a document out of a running stage (to `done` or `failed`) applies C1 §4.1's batch-done check, and the pipeline's journal entries carry the batch's `intake_batch` group.
- Intake enqueues a batch's `extract_text` jobs in upload order, and Procrastinate runs equal priorities by job id, so documents reach `classify_document` in about the order they were dropped (`cpu` concurrency can swap neighbours). The demo relies on it: the live batch keeps running behind the evidence beat, which opens the batch's first document (demo-script v1).

### 1.3 Caches (key: document sha256)
Directory `/data/textcache/<sha[0:2]>/`:

| File | Content | Written by |
|---|---|---|
| `<sha>.pages.json` | `{"v": 1, "sha256": "<sha>", "method": "pdftotext" \| "ocr", "page_count": N, "pages": ["<page 1 text>", …]}`, all pages, text as produced by §1.4 | `extract_text` |
| `<sha>.ocr.pdf` | OCR'd copy, only when OCR ran (scans, images) | `extract_text` |
| `<sha>.p1.png` | page-1 thumbnail, 60 dpi | `render_thumbnail` |
| `<sha>.model.<prompt_version>.json` | `{"v": 1, "sha256": "<sha>", "prompt_version": "c5-v1", "model": "<model id>", "raw_output": {…}}`: the model's output after schema validation | `classify_document` |

- Files are written to `<name>.tmp` and renamed into place, so a reader never sees a partial file.
- A cache hit (file present with the current `v`) skips the work; this is how the demo's pre-extracted batch skips OCR. Bumping `v` invalidates every entry.
- **Model-output cache.** `classify_document` reads `<sha>.model.<prompt_version>.json` before calling the model. It is a hit when `v`, `prompt_version` and `model` equal the current ones and `raw_output` validates against this request's schema (§5.2; the registry may have changed). A hit skips only the model call: verification, resolution, rules, templates, confidence and `findQuery` (§6–§9) still run live on the current DB state. The extraction row records `from_cache = true`. A miss calls the model and writes the file. A user-requested re-extraction bypasses the cache and overwrites it. `demo-reset` restores these files with the other caches (C1 §9).
- The archive never holds cache files; the cache never holds original bytes.

### 1.4 Text extraction
1. **PDF, per page** `n`: `pdftotext -layout -enc UTF-8 -f n -l n <file> -`. Strip U+0000 and form feeds; strip trailing whitespace per line. (S6: `-layout` + page markers verified 91% of quotes vs 88% for raw.)
2. **OCR decision:** a page needs OCR when its text has fewer than 20 non-whitespace characters. If any page needs it, run once for the whole file:
   `ocrmypdf --skip-text -l fra+eng+ron --rotate-pages --rotate-pages-threshold 0.3 --deskew --output-type pdf --jobs 1 <in> <sha>.ocr.pdf.tmp`
   then redo step 1 on the OCR'd copy for every page. `method = 'ocr'`. Timeout 300 s. If ocrmypdf rejects `--deskew` together with `--skip-text` in the pinned image, drop `--deskew` and say so in the L1 report.
3. **Images** (JPEG, PNG): `img2pdf <in> -o <tmp>.pdf`, then step 2 on it (every page needs OCR). The archive keeps the image; the viewer shows the OCR'd PDF.
4. Timeouts: `pdftotext` 60 s per page. A timeout counts as a failure of the job (retries apply).

### 1.5 Page-delimited text sent to the model
The first 3 pages, each cut to 4,000 characters, in this exact form (S6 variant `p1_markers_layout`):

```
Document text, {k} of {N} page(s):
=== PAGE 1 ===
{page 1 text}
=== PAGE 2 ===
{page 2 text}
```
`{k}` = pages sent, `{N}` = `page_count`. Page numbers are the PDF's physical pages, 1-based, so a quote's `page` is the page the viewer opens.

## 2. Text normalisation: `norm()`

One function, `mona.text.norm(s: str) -> str`, used by evidence verification, rules, counterparty resolution, search (C1 §1.4) and exemplar retrieval. C8 references it; nothing else normalises differently.

1. Unicode NFKC. (Maps U+00A0 and U+202F to U+0020, ligatures to letters.)
2. Remove U+00AD (soft hyphen).
3. Map punctuation variants: U+2018 U+2019 U+201A U+201B U+02BC U+0060 U+2032 → `'`; U+201C U+201D U+201E U+201F U+00AB U+00BB U+2039 U+203A → `"`; U+2010 U+2011 U+2012 U+2013 U+2014 U+2015 U+2212 → `-`; U+2026 → `...`. (S6: typographic punctuation was a residual cause of unverified quotes.)
4. Unicode NFD, then drop every combining mark (category `Mn`). This folds é→e, ç→c, and both Romanian forms: ș/ş → s, ț/ţ → t.
5. `casefold()`.
6. Replace every run of whitespace (`\s`, including newlines) with one U+0020; strip both ends.

**Whole-word match** of a needle in a haystack (both already normalised): the regex `(?<![0-9a-z])` + `re.escape(needle)` + `(?![0-9a-z])` finds a match.

## 3. What the pipeline stores
- `extractions` + `extraction_fields` (C1 §4.3): the model output and one row per returned field, with `verified`, `page`, `stated_page`, `find_query`, `confidence`.
- `classifications` (C1 §4.4): the decision.
- `documents`: the applied values (entity, sub-unit, category, subcategory, counterparty, fields, `fiscal_year`, `confidence`, `band`, `reasons`, `rule_id`, `title`).
- Amounts in a currency other than EUR/RON stay in `extraction_fields` and are not copied to `documents.amount`.

## 4. Rules

### 4.1 Shape
A rule is `{conditions[], action}` plus metadata (C1 §3). All conditions must hold (AND). `conditions` has 1–8 items. The grammar is validated on every write (REST, MCP, seed, import); invalid input is rejected with the validator's message.

### 4.2 Conditions
`{"field": <field>, "op": <op>, "value": <value>, "negate"?: true}`

| field | Subject compared | ops | value |
|---|---|---|---|
| `counterparty` | the resolved counterparty: its `name_norm` and every `alias_norm` (§6.2) | `equals`, `in`, `contains` | string (a name, an alias or a counterparty key); `in`: string[] |
| `text` | `norm()` of all pages joined with a space | `contains`, `contains_any`, `contains_all` | string; string[] for `_any`/`_all` |
| `doc_type` | `norm(doc_type)` | `equals`, `in`, `contains` | string / string[] |
| `category` | the model's `category` value | `equals`, `in` | category id / ids |
| `entity` | the model's `entity` value | `equals`, `in` | entity key / keys |
| `addressee` | `norm(addressee)` | `contains`, `is_person`, `is_entity` | string / person key / entity key |
| `person` | the page text | `mentions` | person key |
| `iban` | IBAN candidates in the page text (§4.3) | `account`, `entity` | account key / entity key |
| `siren` | SIREN candidates in the page text (§4.3) | `equals`, `in`, `entity` | 9 digits / list / entity key |
| `amount` | `documents.amount` (EUR/RON only) | `gt`, `gte`, `lt`, `lte`, `between` | number; `between`: [min, max] inclusive |

Semantics:
1. Every string comparison is on `norm()` of both sides.
2. `equals`: equality. For `counterparty`, true if the value equals the counterparty's key, its `name_norm` or any alias.
3. `contains`, `contains_any`, `contains_all`: whole-word match (§2). `contains_any` needs one needle, `contains_all` all.
4. `is_person`: the addressee whole-word matches the person's `display_name` or any alias (not `short_name`). `is_entity`: the same against the entity's `display_name` and aliases.
5. `person mentions`: the page text whole-word matches the person's `display_name` or any alias.
6. `iban account`: some candidate hashes (C1 §2.4) to that account's `iban_hash`. `iban entity`: to any account of that entity.
7. `siren equals|in`: a candidate equals the value(s). `siren entity`: a candidate equals the entity's `siren` (false if the entity has none).
8. **A missing subject makes the condition false** (null addressee, no counterparty, no amount). `negate: true` inverts the result *after* that, so a negated condition on a missing subject is true.
9. References (person, entity, account keys) that don't resolve make the rule invalid on write. If a referenced row is deleted later, the condition evaluates false and the Rules list shows the rule as invalid (C2).

### 4.3 Identifier candidates
- **IBAN:** in the NFKC, upper-cased page text, match `\b[A-Z]{2}[0-9]{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b`; drop spaces; keep candidates whose length fits the country (FR 27, RO 24, others 15–34) and whose ISO 13616 mod-97 check equals 1. Hash each with the settings salt. Candidates are never stored or logged in clear.
- **SIREN:** 9-digit groups `\b[0-9]{3}[ .]?[0-9]{3}[ .]?[0-9]{3}\b` that pass the Luhn check, plus the first 9 digits of 14-digit SIRETs (`\b[0-9]{3}[ .]?[0-9]{3}[ .]?[0-9]{3}[ .]?[0-9]{5}\b`, Luhn over 14 digits).

### 4.4 Persons and sub-units
`unit: {"from": "person"}` in an action resolves, within the action's entity:
1. the sub-unit linked to `addressee_person_id` (§6.2), if there is one;
2. else the one sub-unit whose linked person the page text mentions (as `person mentions`), if exactly one does;
3. else unresolved: reason `entity` (§9.3).

### 4.5 Actions
```json
{
  "entity": "<entity key>",
  "unit": "<sub-unit key>" | {"from": "person"},
  "category": "<category id>",
  "subcategory": "<key within the resulting category>",
  "counterparty": "<counterparty key>",
  "path": "<path template>",
  "filename": "<file template>",
  "review": true
}
```
- All keys optional; at least one of `entity`, `category`, `review` is required. `unit` requires `entity`. `subcategory` must exist under the action's `category`, or under the model's category when the action has none. `entity` can't be the Visitors entity (C1 §2.1): such an action is invalid on write.
- A key the action omits falls back to the model's resolved value, **except `unit`**: a rule without `unit` gives the document no sub-unit. A sub-unit comes only from the winning rule's `unit` (a key, or `{from: person}` per §4.4) or from a correction; nothing infers it (§6.2.4). `counterparty` overrides the resolved counterparty for naming only.
- `path`/`filename` override the template lookup (C1 §2.7) for documents this rule files.
- `review: true` ("ask me each time") sends matching documents to the queue whatever the confidence (§9.3).

### 4.6 Priority and conflicts
1. `priority` defaults to `10 × len(conditions)`, so more specific rules win by default; seeds may set it. A rule created from a correction or an interview answer gets `max(10 × len(conditions), 1 + P)`, where `P` is the highest priority among the other active rules whose conditions hold on any of its source documents (the corrected document; the question's affected documents), so what you just taught outranks the rules it corrects. `P` is computed when the rule is created.
2. `M` = active rules whose conditions all hold. Empty → no rule applies.
3. `T` = the rules in `M` with the highest priority.
4. Each rule in `T` yields a destination: (entity, unit, category, subcategory, path template, file template) after fallbacks.
5. All destinations in `T` equal → the winner is the oldest rule in `T` (`created_at`, then `id`). Lower-priority matches are simply overridden.
6. Destinations differ → **conflict**: no winner, `reasons += conflict`, `conflicting_rule_ids` = ids in `T`, and the suggestion uses the model's values.
7. Rule-vs-model disagreement is not a conflict: the rule wins.
8. **Visitor batches** (`batches.visitor`, R38): rules are not evaluated; the entity is the one entity with `purge_after_hours` set (the Visitors entity), and the model's category stands. For scoring (§9.2, §9.3) this override counts as a rule-set entity. Documents of other batches never get the Visitors entity (C1 §2.1). Purge semantics are C9's.
9. **Preview and apply** (C4 §3.8, §3.9) use the same precedence: a document is a candidate for a rule only if, with that rule treated as active, the rule is in `T` and `T` has no conflict.

### 4.7 Rendered texts
**`condition_text`** is rendered in EN, FR and RO on every write (C1 §3), by joining the condition phrases below with ", " and " and " / « et » / „și": `When {c1}, {c2} and {c3}.` / `Quand {…}.` / `Când {…}.` Values in quotes use “…” (EN), « … » (FR), „…" (RO). `{person}`, `{entity}` and `{account}` render the display name / label (accounts: label + ` •• ` + last 4). Lists render as `a, b or c` / `a, b ou c` / `a, b sau c` (`contains_all`: and / et / și).

| field · op | EN | FR | RO |
|---|---|---|---|
| counterparty · equals | the counterparty is {v} | l'émetteur est {v} | emitentul este {v} |
| counterparty · in | the counterparty is {list} | l'émetteur est {list} | emitentul este {list} |
| counterparty · contains | the counterparty's name contains “{v}” | le nom de l'émetteur contient « {v} » | numele emitentului conține „{v}" |
| text · contains / _any / _all | the text mentions “{v}” / {list} | le texte mentionne « {v} » / {list} | textul menționează „{v}" / {list} |
| doc_type · equals / in | it is a {v} / {list} | c'est un(e) {v} / {list} | este {v} / {list} |
| doc_type · contains | its type contains “{v}” | son type contient « {v} » | tipul conține „{v}" |
| category · equals / in | Mona reads it as {category label} / {list} | Mona le lit comme {…} | Mona îl citește ca {…} |
| entity · equals / in | Mona reads it as {entity}'s / {list} | Mona l'attribue à {entity} | Mona îl atribuie lui {entity} |
| addressee · contains | it is addressed to “{v}” | il est adressé à « {v} » | este adresat către „{v}" |
| addressee · is_person / is_entity | it is addressed to {person} / {entity} | il est adressé à {…} | este adresat lui {…} |
| person · mentions | it names {person} | il mentionne {person} | îl menționează pe {person} |
| iban · account | it shows the {account} account | il porte le compte {account} | apare contul {account} |
| iban · entity | it shows one of {entity}'s accounts | il porte un compte de {entity} | apare un cont al {entity} |
| siren · equals / in | it shows SIREN {v} / {list} | il porte le SIREN {v} | apare SIREN {v} |
| siren · entity | it shows {entity}'s SIREN | il porte le SIREN de {entity} | apare SIREN-ul {entity} |
| amount · gt / gte / lt / lte | the amount is over / at least / under / at most {money} | le montant dépasse / est d'au moins / est inférieur à / est d'au plus {money} | suma depășește / este de cel puțin / este sub / este de cel mult {money} |
| amount · between | the amount is between {a} and {b} | le montant est entre {a} et {b} | suma este între {a} și {b} |

Negation: EN inserts "not"/"doesn't" (`the text doesn't mention …`, `the counterparty is not …`, `it isn't addressed to …`); FR `ne … pas`; RO `nu`. L1 writes the negated forms per row, and the test in §11 covers every row in both polarities.

**`destination`** (Rule DTO, C1 §11.5): the rule's effective path template (action `path` → entity template → category default; the model-fallback parts unknown) split on `/`, with `{entity}` (plus the fixed `unit` label), `{category}`, `{sub}` and `{counterparty}` (from the action, or from a single-value `counterparty equals` condition) filled in; `unit: {from: person}` renders as the literal segment `{person}`; every other token stays literal (`{fy}`, `{year}`). Example: `["Personnel", "{person}", "Assurances", "AGIPI", "PER", "{year}"]`.

### 4.8 Rule statistics
- `fired_count += 1`, `last_fired_at = now()` when a rule wins (§4.6) for a classification, in the classification's transaction, whatever the outcome (filed or queued).
- `corrections_since += 1` when you correct entity, sub-unit, category, subcategory or the path of a document whose `rule_id` is that rule. Reset to 0 when the rule's version changes.
- Applying a rule to existing documents (C4 `apply_rule`) counts one firing per document moved.

## 5. The model step

### 5.1 Request
- Output: strict JSON Schema, thinking off. Through pydantic-ai `NativeOutput` (S6 test 5 validated it).
- Dev (OpenRouter): model `qwen/qwen3.6-35b-a3b`, `reasoning: {"enabled": false}` (S6 T2: 0 reasoning tokens, 0.75 s median on a short prompt; `effort: "low"` did *not* turn thinking off), and the D4 provider pin, verbatim:
  `"provider": {"order": ["akashml", "coreweave", "siliconflow", "parasail", "deepinfra"], "allow_fallbacks": false, "require_parameters": true, "quantizations": ["fp8", "fp16", "bf16"]}`.
  The pin is D4's; a later entry in `docs/decisions.md` supersedes this copy.
- Prod (llama-server): `chat_template_kwargs: {"enable_thinking": false}` (plan §3, D4). Each backend ignores the other's knob.
- Both: `temperature: 0`, `max_tokens: 2000`, `response_format: {"type": "json_schema", "json_schema": {"name": "mona_extraction", "strict": true, "schema": <§5.2>}}`, timeout 90 s.
- `prompt_version` stored on the extraction: `c5-v1`. Any prompt or schema change bumps it.

### 5.2 Output schema
Built per request from the registry. Every string in it has an `enum` or a `maxLength` (S6 T4: a no-think model once ran away inside an unbounded string). `Ev(T)` is `{"type": "object", "properties": {"value": T, "quote": {"type": "string", "maxLength": 160}, "page": {"type": "integer", "minimum": 1}}, "required": ["value", "quote", "page"], "additionalProperties": false}`; `Ev?(T)` is `anyOf [Ev(T), null]`.

| Property | Type | Meaning given to the model |
|---|---|---|
| `title` | string, maxLength 120 | short title in the filing language: issuer, kind, period ("URSSAF appel de cotisation T3 2026") |
| `category` | enum: category ids + `"unknown"` | §5.6 definitions |
| `subcategory` | enum `"<category_id>.<key>"` for every subcategory, or null | must belong to `category` (else dropped at validation) |
| `entity` | `Ev?(enum: entity keys, without the Visitors entity)` | the practice entity or person the document concerns; null if none fits |
| `counterparty` | `Ev?(string ≤160)` | the other party: supplier, bank, insurer, administration |
| `issuer` | `Ev?(string ≤160)` | the issuing office as printed, when it differs from the counterparty ("SIE de Laval") |
| `reference` | `Ev?(string ≤60)` | invoice, contract, notice or file number |
| `doc_type` | `Ev?(string ≤80)` | the document's own title or kind ("avis d'échéance") |
| `doc_date` | `Ev?(date)` | issue date |
| `period_start`, `period_end` | `Ev?(date)` | period covered |
| `amount` | `Ev?(number)` + `"currency": {"type": "string", "pattern": "^[A-Z]{3}$", "maxLength": 3}` inside the object | main amount due or paid |
| `due_date` | `Ev?(date)` | payment or reply deadline |
| `addressee` | `Ev?(string ≤160)` | person or company the document is addressed to, as written |
| `confidence` | number 0–1 | confidence in `category` + `entity` |
| `reason` | string, maxLength 250 | the decisive evidence, one sentence (stored, not shown) |

`date` = `{"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$", "maxLength": 10}`; values that don't parse as real dates are treated as absent.

Stored `extraction_fields.value` forms: dates `YYYY-MM-DD`; amounts as a decimal string with 2 places (`"1284.00"`); text trimmed, whitespace runs collapsed (not `norm`ed). `entity.value` is the entity key.

### 5.3 Prompt skeleton
System message (exact structure; `{…}` filled from the DB):

```
You read the paperwork of {settings.practice_name}, a French dental practice, and of the companies and family of its owners. For each document, decide which entity it belongs to and which category it is, and extract the fields below with evidence.

## Entities
- {key}: {display_name} ({legal_form or "private household"}). Names on documents: {aliases, "; "-joined}. People: {linked people display names}.
…one line per entity, except the Visitors entity (§4.6.8)…

## Categories
- {id}: {model_definition} Subcategories: {key} ({en label}); …
…one line per category…
- unknown: the text is garbled, handwritten or too short to decide. A readable document always has a real category.

## House rules
The practice files documents by these rules. They are applied after you answer; use them to understand the practice.
- {condition_text.en} → {destination, " / "-joined}
…active rules, highest priority first, at most 30…

## Fields
Return one JSON object. Each field is {"value", "quote", "page"}, or null when the document does not state it.
- entity: the entity above the document concerns or is addressed to; null if none fits
- counterparty: the issuer or other party (supplier, bank, insurer, administration)
- issuer: the issuing office as printed, only if it differs from the counterparty
- reference: the invoice, contract, notice or file number
- doc_type: the document's own title or kind
- doc_date: the issue date, as YYYY-MM-DD
- period_start / period_end: the period covered (statement period, fiscal year, contract term), as YYYY-MM-DD
- amount: the main amount due or paid, as a number, plus "currency" (ISO 4217)
- due_date: the payment or reply deadline, as YYYY-MM-DD
- addressee: the person or company the document is addressed to, as written
- title: a short title in {filing language name}: issuer, kind, period
- confidence: 0 to 1, for category and entity together
- reason: one sentence quoting the decisive evidence

## Quotes
- Copy a short span (3 to 12 words) character for character from ONE line of the document text: same spelling, accents, capitals, punctuation and odd spacing, even if the OCR looks wrong.
- Never translate, reformat, abbreviate or join text from different lines. Dates and amounts are quoted as printed, even though "value" is normalised.
- "page" is the number in the nearest "=== PAGE n ===" marker above the quoted line.
- If you cannot find a supporting span, return null for the field.

Respond with JSON only.
```

User message:
```
Documents already filed here, for reference:
- "{title}" from {counterparty} → {entity key} / {category id}[.{subcategory key}]
…0 to 5 exemplars (§5.5); the whole block is omitted when there are none…

Filename: {original_name}

{§1.5 page block}
```

The "Quotes" block is S6's rule set `p1` verbatim (it raised verification from 61% to 91% against `p0`).

### 5.4 Context budget
- Estimate tokens as `ceil(len(text) / 3.2)` over system + user message; the schema is not counted (≤ 1,500 tokens).
- Ceiling: **20,000** estimated tokens. When over, cut in this order until under: exemplars (to 0) → house rules (30 → 15 → 0) → page text (4,000 → 2,500 characters per page) → page 3 → page 2. The entity and category sections are never cut.
- If still over after all cuts (a registry larger than the demo's), the job fails with `pipeline_error='prompt_budget'`.

### 5.5 Exemplars
Up to 5 filed, non-deleted documents, most similar first by `similarity(head_norm, :head_norm)` (pg_trgm) ≥ 0.2, at most 2 per counterparty, excluding the document itself. Only documents whose applied classification is `method IN ('user','rule')` or `band = 'high'`. Only title, counterparty name, entity key, category and subcategory; never text.

### 5.6 Category definitions (v2 re-keyed)
The seed's `categories.model_definition` values. They are v2's definitions (94% on the hard sample) with the entity dimension moved out: v2's `PERSONAL/*` vs `BUSINESS/*` split becomes the entity, and v2's per-person category becomes entity `personal` + a person sub-unit.

| v2 | Canonical id | `model_definition` |
|---|---|---|
| BUSINESS/Documente-Anuale | `annual_accounts` | The annual accounting and tax package of a company: balance sheet (bilan), income statement (compte de résultat), soldes intermédiaires de gestion, liasse fiscale, corporate tax returns and their preparatory checklists, and the accountant's approval-of-accounts letters. Not payment demands. |
| BUSINESS/Factures-IN/Apeluri-de-Plata | `payment_calls` | Payment calls and payment demands from social bodies and the tax office: URSSAF, CARCDSF, OPCO, appel de cotisation, SIE avis de mise en recouvrement, lettre de majoration, saisie administrative à tiers détenteur. |
| BUSINESS/Factures-IN/Furnizor | `supplier_invoices` | Recurring supplier invoices and letters: dental and medical suppliers and their delivery notes, water, electricity and telecom bills and meter letters. |
| BUSINESS/Factures-IN/Cheltuieli-Diverse | `misc_expenses` | One-off local purchases not from a recurring supplier: shop and DIY receipts, local fuel and parking, post office, contractor quotes and payment reminders, shipping labels. |
| BUSINESS/Factures-OUT | `sales_invoices` | Invoices issued by the practice or one of its companies to its clients (the entity is the seller). |
| BUSINESS/Bank | `bank` | Bank statements and bank letters: relevé de compte, relevé de frais, bank notices. |
| BUSINESS/Payroll | `payroll` | Payroll documents: déclaration sociale nominative (DSN), bulletins de salaire or de paie. |
| BUSINESS/Assurances | `insurance` | Insurance and pension contracts and notices: AGIPI, Abeille, MAE, La Médicale, UNIM, mutuelle, prévoyance, PER, assurance vie. |
| BUSINESS/Formations | `training` | Training, courses, certifications and course handouts. |
| BUSINESS/Travel | `travel` | Travel expenses: car rental, hotels, transport, and any receipt from a trip away from home (airport shops, duty-free, restaurants, fuel and souvenirs abroad, airport parking, receipts in Spanish or English). |
| (new; v2 put these under annual documents or personal/other) | `tax` | Tax documents of a person or household that are not payment demands: avis d'imposition, taxe foncière, taxe d'habitation, income-tax preparation documents from a tax adviser. A company's tax package is annual_accounts; tax payment demands are payment_calls. |
| PERSONAL/Medical | `health` | Personal medical and wellness documents: prescriptions, care instructions, health questionnaires, and health-insurance letters (CPAM, Assurance Maladie). |
| (new, R7 showcase) | `patient_documents` | Documents about the practice's patients: treatment quotes (devis), prescriptions and post-care instructions the practice gave to a patient. |
| PERSONAL/Other, PERSONAL/<person> | `general` | Other readable documents that fit no category above: contracts, general letters, civil-status certificates, personal letters, real-estate estimates, notes, magazine pages, catalogues. A readable private document belongs here, not in unknown. |
| UNKNOWN | `unknown` (output only) | The text is garbled, handwritten or too short to decide. |

`health` is new relative to the L5 draft seed (icon `personal`); L5 adds it.

## 6. After the model

### 6.1 Evidence verification
For each returned field `{value, quote, page}`:
1. `q = norm(quote)`. If `len(q) < 3` → not found.
2. If `1 ≤ page ≤ k` (pages sent) and `q` is a substring of `norm(pages[page])` → found.
3. Else, if `q` is a substring of `norm(pages[p])` for **exactly one** other sent page `p` → found, and `page := p`; `stated_page` keeps the model's number. On two or more other pages → not found (the page can't be told). (S6: 5 of 13 residual failures were wrong pages with verbatim quotes; relocation took p1 from 91% to 95%.)
4. **Value check** for `doc_date`, `period_start`, `period_end`, `due_date` and `amount`: the quote must contain the value (§6.1.1). Other fields have no value check.
5. `verified = found ∧ value check`.

Field confidence (`ExtractedField.confidence`): the model's confidence ×100 if verified; otherwise `min(that, 40)`.

Near-miss quotes (the model "corrected" OCR noise) stay unverified; there is no fuzzy matching in v1.

**6.1.1 Value in quote.**
- Amount: every number token in the quote (digits with optional thousands separators — space, U+00A0, U+202F, `.`, `,`, `'`, U+2019 — and an optional 1–2 digit decimal part after `.` or `,`) is parsed both ways (comma decimal with space/dot/apostrophe thousands; dot decimal with comma thousands). A parse equal to the value to the cent passes.
- Dates: parse `dd/mm/yyyy`, `dd.mm.yyyy`, `dd-mm-yyyy`, `yyyy-mm-dd`, `dd/mm/yy` (→ 20yy), and `d[er] <month> yyyy` with month names and abbreviations in FR (janvier, janv., février, févr., mars, avril, avr., mai, juin, juillet, juil., août, septembre, sept., octobre, oct., novembre, nov., décembre, déc.), EN (full, 3-letter) and RO (ianuarie … decembrie, ian., feb., mar., apr., iun., iul., aug., sept., oct., nov., dec.), after `norm()`. Any parse equal to the value passes.
- `period_start` also passes on `<month> yyyy` when the value is that month's first day; `period_end` when it is that month's last day. Both pass on a bare `yyyy` (e.g. "exercice 2025") when the value is 01-01 / 12-31 of that year, or the entity's FY start/end in that year.

### 6.2 Resolution
1. **Counterparty.** `n = norm(counterparty.value)`. Exact `counterparty_aliases.alias_norm = n` → that counterparty. Else the counterparty with the highest `similarity(name_norm, n)` if ≥ 0.6 → it. Else insert a counterparty (`origin='extracted'`, `name` = the value trimmed, `name_norm = n`, `key` = slug of the value, deduplicated with `-2`, `-3`), plus its alias row. Concurrent inserts of the same `n` resolve to one row (`ON CONFLICT (name_norm)`).
2. **Entity.** The model's `entity.value` (already a valid key) → entity; null → unresolved.
3. **Addressee person.** People whose `display_name` or aliases whole-word match `norm(addressee.value)`: exactly one → `addressee_person_id`; else null.
4. **Sub-unit.** Resolution sets none. A sub-unit comes only from the winning rule's `unit` (§4.4, §4.5) or from a correction, so a personal document addressed to one family member still files under `Personnel/<category>/…` unless a rule splits it (§8.5 case 4). `addressee_person_id` feeds `unit: {from: person}` and the `addressee is_person` condition only.
5. **Alias learning.** When you correct a document's counterparty (C2/C4) to counterparty `C`, `a = norm(<the extracted counterparty string>)` becomes an alias of `C`, so the same spelling resolves next time. In the correction's transaction:
   - `a` is no alias yet → insert `(a, C)`.
   - `a` already points to `C` → nothing.
   - `a` points to another counterparty `X` with `origin='extracted'` → **merge `X` into `C`**: repoint `documents.counterparty_id` and `classifications.counterparty_id` from `X` to `C`, move all of `X`'s aliases to `C` (`UPDATE … SET counterparty_id = C`), rewrite rule conditions and rule actions that name `X`'s key to `C`'s key (a `rule.change` each), repoint `accounts.bank_counterparty_id` from `X` to `C`, then delete `X`.
   - `a` points to a `seed` or `user` counterparty `X` → learning is skipped: another curated counterparty's name is never taken over.
   To serialise concurrent corrections, the transaction first runs `INSERT INTO counterparty_aliases VALUES (a, C) ON CONFLICT (alias_norm) DO NOTHING`, then reads the row for `a` with `FOR UPDATE` and applies the cases above.

## 7. `findQuery`

What the viewer sends to pdf.js find (C1 §11.2): `PDFViewerApplication.eventBus.dispatch('find', {source: null, type: '', query: findQuery, caseSensitive: false, entireWord: false, highlightAll: false, findPrevious: false, matchDiacritics: false})` after opening `evidence.page`. Computed at classification for every **verified** field; unverified fields get `null` (the side panel shows the quote only).

pdf.js 6.3.289 find (vendored `web/viewer.mjs`, `normalize` and `#convertToRegExpString`) behaves like this, and the choice below depends on it:
- page text and query both go through NFKC (so U+00A0/U+202F become spaces), curly quotes and U+2010 map to ASCII, a line end in the page text becomes a space, and a lower-case word broken by `-` at a line end is joined;
- with `matchDiacritics: false`, marks are ignored on both sides (ș/ş/ț/ţ fold to s/t);
- whitespace in the query becomes `[ ]+`; punctuation gets optional spaces around it;
- matching is case-insensitive.

Computation (`lines` = the page's text from §1.4 split on `\n`):
1. If `norm(quote)` is a substring of `norm(line)` for some line, the candidate is the whole quote.
2. Else the longest run of consecutive whole words of the quote, at least 2 words and 6 normalised characters long, whose `norm` is a substring of some line's `norm`.
3. Else the value's printed form: for amounts and dates, the number or date token in the quote that passed §6.1.1; for text fields, the value itself if its `norm` is within one line.
4. Else `null`.

Output form: the candidate as it appears **in the quote's original characters** (not normalised), trimmed of whitespace and of `.,;:` at both ends, internal whitespace runs replaced by one U+0020, at most 120 characters (cut at a word boundary).

`pdftotext -layout` and pdf.js order text differently on multi-column pages, so this is a best effort; the binding check is L5's reset fixture (plan §6.3): every rehearsed document's `findQuery` values produce at least one pdf.js match in the real viewer.

## 8. Templates

### 8.1 Grammar
```
template := part*
part     := literal | token
token    := "{" name [ ":" format ] "}"
name     := "entity" | "year" | "fy" | "category" | "sub" | "counterparty" | "issuer" | "reference" | "date"
format   := only after "date": a non-empty string over the units YYYY, YY, MM, DD and the separators - _ .
literal  := any characters except "{" and "}"
```
- **Path templates:** `/` in a literal separates segments. No leading or trailing `/`, no empty segment, no segment that is `.` or `..`.
- **File templates:** no `/`; must begin with a `date` token (R17, date first); no extension (it comes from the file).
- Parse errors (unknown token, format on a non-date token, bad format, stray brace, rule above broken) reject the template on write with the error and its character offset.
- There is no `{amount}` token: design §9's example names carry none, which amends R17's example.

### 8.2 Token values
Language = `entity.filing_language ?? settings.filing_language`. Dates are calendar dates; `arrived_at` is converted to Europe/Paris first.

| Token | Value | Fallback (and its §9 penalty) |
|---|---|---|
| `{entity}` | `entity.folder_name`. **When the whole segment is exactly `{entity}` and the document has a sub-unit (from the winning rule's `unit` or a correction, never inferred: §6.2.4), it renders two segments: `folder_name/sub_unit.label`.** Inside a longer segment it renders `folder_name` only | none: no entity → no path; reason `entity` |
| `{year}` | `doc_date.year` | `period_end.year` (−10), then `arrived_at` year (−20) |
| `{fy}` | fiscal year of `period_end` under the entity's FY end (below) | of `doc_date` (−10), then of `arrived_at` (−20) |
| `{category}` | category label in the language | none (category required) |
| `{sub}` | subcategory label in the language | empty |
| `{counterparty}` | counterparty `name` (a rule's `counterparty` override wins) | empty |
| `{issuer}` | `issuer` value | counterparty name, then empty |
| `{reference}` | `reference` value | empty |
| `{date:FMT}` | `doc_date` formatted (`YYYY` 4 digits, `YY` 2, `MM`, `DD` zero-padded) | `arrived_at` date (−20) |

**Fiscal year.** For a date `d` and an entity FY end `(M, D)`: `fy = d.year` if `(d.month, d.day) ≤ (M, D)`, else `d.year + 1`. The fiscal year is named after the calendar year it ends in. With FY end 12-31 this is `d.year`. Examples, FY end 09-30: 2025-09-30 → 2025; 2025-10-01 → 2026; 2026-03-31 → 2026.

`documents.fiscal_year` is computed at classification for **every** document that has an entity, whatever its templates use: the fiscal year of `period_end`, else of `doc_date`, else of `arrived_at` (the `{fy}` chain above). A correction that changes the entity or those dates recomputes it. So the `fiscal_year` search filter and the accountant export (C4 §3.1, §3.13) see `{year}`-templated documents too. No entity → null.

### 8.3 Folder segments (keep accents)
After substitution, each path segment:
1. Unicode NFC.
2. Each of `\ / : * ? " < > |` and each control character (U+0000–U+001F, U+007F) → `-`. A `/` inside a token value is replaced like this; it never creates a segment. Only template literals and the `{entity}` expansion split segments.
3. Whitespace runs → one space; strip leading and trailing spaces and dots.
4. At most 80 characters and at most 255 bytes in UTF-8 (`NAME_MAX`); cut at a character boundary, then strip again.
5. An empty segment is dropped. A path with no segment left is not renderable (reason `entity`).
Case and accents are kept: `Impôts et taxes`, `Assurances`.

### 8.4 File names (drop diacritics)
1. Each token value is **slugged**: NFKD, drop combining marks (ș→s, é→e), every run of characters outside `[A-Za-z0-9.]` → `-`, collapse `-` runs, strip `-` and `.` at both ends.
2. Template literals: every character outside `[A-Za-z0-9._-]` → `-`.
3. Concatenate. Then: any run of `_` and `-` that contains at least one `_` → `_`; runs of `-` → `-`; strip `_`, `-`, `.` at both ends. (So an empty `{reference}` leaves no `__` and no trailing `_`.)
4. Stem length ≤ 116 characters (4 are reserved for the C7 collision suffix): cut at the last `_` or `-` at or before 116 if that keeps ≥ 40 characters, else at 116; strip again.
5. Extension from `mime_type`: `.pdf`, `.jpg`, `.png`.
6. Case is kept (`URSSAF`, `Releve`).

Rendering is a pure function of (template, document values, registry rows, settings): same inputs, same bytes. The C7 collision suffix is the only filesystem-dependent step and comes after.

### 8.5 Worked examples
Fictional registry (filing language `fr`):

| Entity key | folder_name | FY end | Sub-units |
|---|---|---|---|
| `cabinet` | Cabinet Marchand | 12-31 | — |
| `studio` | Studio Numérique | 09-30 | — |
| `lmnp` | LMNP | 12-31 | `angers-strasbourg` "Angers-Strasbourg" |
| `personal` (visibility personal) | Personnel | 12-31 | `anna` "Anna" (person Anna Marchand), `paul` "Paul" (person Paul Marchand) |

| Category | Path template | File template | Subcategories used |
|---|---|---|---|
| `insurance` | `{entity}/Assurances/{counterparty}/{sub}/{year}` | `{date:YYYY-MM-DD}_{counterparty}_{sub}_{reference}` | `per` PER, `assurance_vie` Assurance vie, `prevoyance` Prévoyance |
| `bank` | `{entity}/Banque/{fy}` | `{date:YYYY-MM-DD}_{counterparty}_{sub}` | `releve` Relevé de compte |
| `annual_accounts` | `{entity}/Documents annuels/{fy}` | `{date:YYYY-MM-DD}_{counterparty}_{sub}` | `bilan` Bilan, `approbation` Approbation des comptes |
| `tax` | `{entity}/Impôts et taxes/{year}` | `{date:YYYY-MM-DD}_{issuer}_{sub}` | `preparation` Éléments préparatoires |
| `payment_calls` | `{entity}/Appels de paiement/{fy}` | `{date:YYYY-MM-DD}_{counterparty}_{sub}_{reference}` | `contribution_opco` Contribution OPCO |

| # | Case (plan §0 criterion 2) | Rule (conditions → action) | Document values | Path | File name |
|---|---|---|---|---|---|
| 1a | AGIPI → personal, PER, by insured person | counterparty equals AGIPI; text contains_any ["plan d'épargne retraite", "PER"] → entity personal, unit {from: person}, category insurance, subcategory per | addressee "M. Paul Marchand" (→ Paul), doc_date 2025-04-14, reference "C-48213" | `Personnel/Paul/Assurances/AGIPI/PER/2025` | `2025-04-14_AGIPI_PER_C-48213.pdf` |
| 1b | AGIPI, same insurer, other person, Assurance vie | counterparty equals AGIPI; text contains_any ["assurance vie", "situation annuelle"] → entity personal, unit {from: person}, category insurance, subcategory assurance_vie | addressee "Mme Anna Marchand", doc_date 2025-03-02, no reference | `Personnel/Anna/Assurances/AGIPI/Assurance vie/2025` | `2025-03-02_AGIPI_Assurance-vie.pdf` |
| 2 | Hello bank → LMNP/Angers-Strasbourg/Banque/{fy} | counterparty equals Hello bank; iban account lmnp-hello → entity lmnp, unit angers-strasbourg, category bank | period 2024-12-16 → 2025-01-15, doc_date 2025-01-16, subcategory releve | `LMNP/Angers-Strasbourg/Banque/2025` | `2025-01-16_Hello-bank_Releve-de-compte.pdf` |
| 3 | TALENZ → per company, Documents annuels/{fy} | counterparty equals TALENZ; siren entity studio → entity studio, category annual_accounts | period_end 2025-09-30 (FY end 09-30 → 2025), doc_date 2026-01-20, subcategory approbation | `Studio Numérique/Documents annuels/2025` | `2026-01-20_TALENZ_Approbation-des-comptes.pdf` |
| 4 | OXYLEO → Personnel/Impôts et taxes/{year} | counterparty equals OXYLEO → entity personal, category tax (no `unit`) | addressee "M. Paul Marchand" (→ Paul, who has the `paul` sub-unit), doc_date 2026-05-12, issuer null (→ counterparty), subcategory preparation | `Personnel/Impôts et taxes/2026` | `2026-05-12_OXYLEO_Elements-preparatoires.pdf` |
| 5 | OPCO → SELARL/Appels de paiement/{fy} | counterparty equals OPCO → entity cabinet, category payment_calls | period_end 2025-12-31, doc_date 2026-02-27, reference "2025-A-118", subcategory contribution_opco | `Cabinet Marchand/Appels de paiement/2025` | `2026-02-27_OPCO_Contribution-OPCO_2025-A-118.pdf` |
| 6 | UNIM → business | counterparty equals UNIM → entity cabinet, category insurance | doc_date 2025-11-03, model subcategory prevoyance, no reference | `Cabinet Marchand/Assurances/UNIM/Prévoyance/2025` | `2025-11-03_UNIM_Prevoyance.pdf` |
| 7 | FY-crossing bilan (`{year}` ≠ `{fy}`) | as 3 | period 2024-10-01 → 2025-09-30, doc_date 2026-01-10, subcategory bilan | `Studio Numérique/Documents annuels/2025` | `2026-01-10_TALENZ_Bilan.pdf` |
| 8 | Unsafe characters | none (model) | counterparty "AXA / AGIPI", category insurance, entity cabinet, subcategory prevoyance, doc_date 2025-06-01, reference "N° 77/12" | `Cabinet Marchand/Assurances/AXA - AGIPI/Prévoyance/2025` | `2025-06-01_AXA-AGIPI_Prevoyance_N-77-12.pdf` |
| 9 | `{entity}` inside a segment (HANDOFF TemplateField example) | path `{entity}/{fy} {entity}/Documents annuels` | entity cabinet, period_end 2025-12-31 | `Cabinet Marchand/2025 Cabinet Marchand/Documents annuels` | — |

Case 2's IBAN condition refers to account key `lmnp-hello`, whose IBAN lives only in the private overlay (C1 §9).

Case 4 pins §6.2.4: the addressee resolves to a person with a Personnel sub-unit, and the path still has no person folder, because the rule has no `unit`. Cases 1a, 1b and 2 are rules the demo learns live (not seeded, demo-script v1); here they are renderer fixtures.

## 9. Confidence, reasons and bands

### 9.1 Base
- A rule won (§4.6, no conflict): `base = 95`.
- Otherwise `base = round(model confidence × 100)`.
- `category = "unknown"` (and no rule set one): `base = min(base, confidence_low − 1)`.

### 9.2 Penalties
- **Path-critical** fields are those whose values fill a token of the templates actually used: `doc_date` ({year}, {date}), `period_end` ({fy}), `counterparty` ({counterparty}), `issuer` ({issuer}), `reference` ({reference}), plus `entity` when neither a rule nor the visitor override (§4.6.8) set the entity. Each one returned but unverified: **−20**.
- Token fallbacks: the amounts in §8.2 (−10 or −20), once per token.
- Other unverified fields (`amount`, `due_date`, `addressee`, `doc_type`, `period_start`, and path-irrelevant ones): −5 each, at most −15 in total.
- `confidence = clamp(base − penalties, 0, 100)`.
- The numbers in §9.1–§9.2 are v1 constants, not settings. L5b's confidence histogram may recalibrate them before Oct 7, by amendment.

### 9.3 Reasons (`ReasonChip`)
| Reason | When |
|---|---|
| `unreadable` | set by `extract_text` (§1.2); no model call |
| `entity` | no entity (model null, and neither a rule nor the visitor override set one); a rule's `unit: {from: person}` unresolved (§4.4); or the path renders no segment |
| `conflict` | §4.6 |
| `low` | `confidence < settings.confidence_low`; or category `unknown`; or the winning rule has `review: true`; or the model step failed after retries |

### 9.4 Outcome
- `band`: `high` if `confidence ≥ settings.confidence_high`; `medium` if `≥ settings.confidence_low`; else `low`.
- **Any reason → review** (the document stays in the inbox, `status='review'`, a review item opens). No reason → `file_document`. `high` files silently; `medium` files and the journal entry carries `band='medium'` (plan §9: "file + mark").
- Threshold changes in settings apply to classifications made after the change.
- The Suggestion `sentence` is rendered at serve time in the request locale from the i18n keys `review.sentence.default|entity|conflict|low|asked|unreadable` (C8 owns the strings) with the placeholders `{counterparty}`, `{docType}`, `{entity}`, `{category}`. `asked` is used when `low` comes only from the winning rule's `review: true` ("you asked to see these"); `review: true` shows the `low` chip, since the DS has four reasons. The model's `reason` is stored, not shown.

## 10. `rules.yaml`

One schema for the seed file (`demo/seed/rules.yaml`), import (`mona rules import`) and export.

```yaml
schema: mona.rules/v1          # required, exact
revision: 42                   # export only: number of committed rule writes so far; ignored on load
exported_at: 2026-10-14T07:02:00Z   # export only; ignored on load
rules:
  - key: agipi-per-by-person   # required; slug; unique in the file; the identity on load
    name: AGIPI PER, filed under the insured person
    state: active              # draft | active | disabled; default active
    source: seed               # seed | interview | correction; default seed on load
    priority: 20               # optional; default 10 × len(conditions)
    conditions:
      - {field: counterparty, op: equals, value: AGIPI}
      - {field: text, op: contains_any, value: ["plan d'épargne retraite", PER]}
    action: {entity: personal, unit: {from: person}, category: insurance, subcategory: per}
    # export only, ignored on load:
    version: 3
    condition_text: {en: "…", fr: "…", ro: "…"}
    stats: {fired_count: 12, last_fired_at: 2026-10-14T06:58:11Z, corrections_since: 0}
```
- The rule above is an illustration. The demo seed leaves the AGIPI and Hello bank rules out: they are learned live on stage (demo-script v1).
- References are keys (entity, sub-unit, person, account, counterparty) and category/subcategory ids; never ULIDs, never IBANs.
- Load = upsert by `key` in one transaction; a changed `conditions`/`action`/`priority` bumps the version (C1 §3). Rules absent from the file are left alone.
- Export: after every committed rule write, `/data/config/rules.yaml` is rewritten atomically (temp + rename); the previous file is kept as `/data/config/rules.history/rules-<previous revision>.yaml`. Rules sorted by priority descending, then key. UTF-8, block style, keys in the order shown.
- `load(export(db))` leaves the DB unchanged (round-trip, C1 §9).

## 11. Test obligations

**[M]** = mutation-checked: break the code, watch the test fail, restore.

1. **`norm()`** table test: NBSP, NNBSP, soft hyphen, curly quotes, en dash, ligature `ﬁ`, `ș`/`ş`/`ț`/`ţ`, `É`, mixed whitespace and newlines → expected outputs. **[M]** (drop the mark-stripping step).
2. **Rules engine [M]**, one test per (field, op) in §4.2 in both polarities, plus: missing subject false / negated true; whole-word (`OPCO` doesn't match `OPCOMMERCE`); IBAN candidate with a bad checksum ignored; SIREN via SIRET; `unit: {from: person}` via addressee, via single mention, unresolved with two mentions; a rule without `unit` gives no sub-unit even when the addressee has one; priority winner; equal-destination tie (oldest wins); conflict (reason `conflict`, both ids listed); a correction rule over a seed rule with the same conditions gets priority 11 and wins (§4.6.1); an action naming the Visitors entity is rejected. Mutations: flip `negate` handling; take the lowest priority; skip the destination-equality check; let `unit` fall back to a resolved value.
3. **Template renderer [M]:** every row of §8.5 renders exactly the path and file name shown (case 4 with its addressee); the grammar errors of §8.1 each raise with an offset; empty `{reference}` leaves no `__`; the 116-character cap; a folder segment of 80 four-byte characters is cut to ≤ 255 UTF-8 bytes on a character boundary; determinism (render twice, same output). Mutations: keep diacritics in file names; drop empty-segment removal; `≤` → `<` in the FY comparison.
4. **Fiscal year [M]:** FY end 12-31 and 09-30, boundary days on both sides, and a 02-28 FY end; `documents.fiscal_year` is set for a `{year}`-templated document (period_end → doc_date → arrived_at chain) and null without an entity.
5. **Evidence verification [M]:** verbatim quote on the stated page; on exactly one other page (page corrected, `stated_page` kept); on two other pages (not found); quote with NBSP vs space; `’` vs `'` and `−` vs `-`; paraphrase fails; amount quote "1 284,00 €" with value 1284.00 passes and with 1248.00 fails; each date form of §6.1.1; `exercice 2025` for a period end. Mutation: skip the value check; relocate to the lowest of several pages.
6. **`findQuery`:** single-line quote → whole quote; quote spanning two lines → longest single-line run; amount fallback; unverified → null; output keeps the original accents and has no leading/trailing punctuation.
7. **Confidence and bands [M]:** a matrix over (rule won or not) × (unverified path-critical field or not) × (fallback used or not) → expected confidence and band with thresholds 85/60; each reason trigger of §9.3 queues the document even at confidence 100. Mutation: `≥` → `>` at the high threshold.
8. **Prompt:** the built prompt for the §8.5 registry contains every entity key except the Visitors entity's, and every category id; the schema enums equal the registry minus Visitors; every string in the schema has an `enum` or a `maxLength`; the budget cutter applied to an oversized input ends ≤ 20,000 estimated tokens and cuts in the stated order.
9. **Schema round-trip:** model outputs from the S6 fixtures (synthetic ones only in the repo) validate; a subcategory from another category is dropped; an impossible date (`2025-02-30`) is treated as absent.
10. **Pipeline:** cache hit skips `pdftotext`/OCR (assert no subprocess call); unreadable path (image with no text) ends `unreadable` with no model call; classification failure after retries lands in review with reason `low`; a `file_document` failure (`ENOENT` twice, `EACCES`, `forbidden_path`) lands in review with reason `conflict` and the errno in `pipeline_error`, and the batch still reaches `done`; a document classified into review ends at `pipeline_stage='done'` and counts toward the batch's `done` (mutation: leave it at `classifying` → the batch-done assertion fails); an unreadable document in a visitor batch carries the Visitors entity.
11. **Model-output cache [M]:** a second classification of the same bytes with the same `prompt_version` and model makes no model call, records `from_cache = true`, and still applies a rule created in between; a different model id or an output that fails today's schema is a miss. Mutation: skip the rules step on a hit.
12. **Visitors:** in a visitor batch a document whose model entity is null files to `Visitors/…` with no `entity` reason and no entity penalty.
13. **Alias learning:** correcting an `extracted` "AGIPI Assurance" to the seed AGIPI merges it (documents repointed, extracted row gone, the alias resolves to AGIPI next time, C1 §2.5 invariant holds); correcting a document whose string matched the seed UNIM's own name leaves UNIM's alias alone.
14. **Six feedback cases end to end** (L5 synthetic fixtures + the seed, plus the AGIPI and Hello bank rules loaded as test fixtures, since the demo seed leaves them out): each files to its expected path (plan §14), including syn-oxyleo-prep with its person addressee → `Personnel/Impôts et taxes/{year}`.
15. **`rules.yaml` round-trip** and rejection of an IBAN literal anywhere in the file.
16. **`condition_text`:** every §4.7 row renders in EN, FR and RO, affirmative and negated, with no unreplaced `{…}`.

## 12. Open questions

Resolved in 0.2:
- 1 (sub-units): per the orchestrator's ruling, the whole-segment `{entity}` expansion stays, and sub-units come only from a winning rule's `unit` (§4.5, §6.2.4, §8.2).
- 2 (model always runs, §1.1), 3 (`health`, §5.6), 4 (`review: true` → `low` chip, `asked` sentence, §9.4), 5 (penalties are v1 constants, §9.2), 6 (first 3 pages, §1.5), 8 (fiscal year named by its closing year, §8.2), 9 (near-misses unverified, §6.1) and 10 (no `{amount}`, §8.1): adopted as proposed.
- 7 (latency): the model-output cache (§1.3), the D4 fast-provider pin (§5.1) and demo-script v1's stance (the batch runs behind the evidence beat; cut it to 12 documents rather than fake results). mona's per-document time is measured on Oct 8 (L1/L6).

No question is still open.
