# C1 · Domain model and DB schema

| | |
|---|---|
| Version | 1.0 |
| Status | **Frozen** (set A verdict: Andrei, 2026-09-30) |
| Freeze | 2026-09-30 |
| Change rule | Amend via `docs/contracts/amendments.md`, orchestrator only |
| Consumers | L1 (pipeline, filing), L2 (API, MCP, adapter), L3 (web, DTOs only), L4 (intelligence), L5 (seed, demo-reset) |
| Depends on | C5 (rule grammar, template grammar, `norm()`), C7 (journal semantics). Forward: C2 (REST paths, auth sessions), C6 (interview semantics), C8 (i18n), C9 (visibility, purge) |

Postgres 17, SQLAlchemy 2 (async, psycopg 3), Alembic. The schema listing in §4–§10 is normative: names, types, nullability, constraints and indexes are the contract. Lanes may add indexes; anything else is an amendment.

**Changes in 0.2**
- Enum values are identical in the DB, MCP and DTOs; `FieldKey` is snake_case (§1.1, §11.1; F14).
- Journal actor = who executed (§5; D5, closes open question 3 = report OQ 4, and F17).
- Batches: the `intake_batch` group is created with the batch, one per batch; who marks a batch `done`; the visitor flag's setters (§4.1, §5; F15, F30, F33, F37).
- Visitors: only visitor batches reach the Visitors entity; C9 purges by `batches.visitor` (§2.1, §4.2; F21, F36).
- Counterparty alias invariant with alias learning and merge (§2.5; F19).
- `fiscal_year` is always computed (§4.2; F27, F42). `extractions.from_cache` for the model-output cache (§4.3; report OQ 7, F34).
- Review resolution writers (§4.5; F44). A failed undo no longer blocks a later one (§5; F50).
- Interview answers produce one rule per branch; `RuleDraft` takes the S6 branch shape (§6.1, §11.5; F10, F28, S6).
- Extracted deadlines only for documents that arrive before their due date (§6.2; F4).
- Chat: the Hermes session id is the conversation id; `user_ordinal` is gone; each turn stores its user text and streamed parts for reload (§7; F8, F9, F24, F35, S5, D4).
- Seed files carry accounts and counterparties; demo-reset pointers for L5b/C9 (§9; F29, F43, refuted `reanchor-columns-undefined` note).
- DTOs: `Evidence.documentTitle`, `RulePreview` once applied, `InterviewQuestion.answer.ruleIds` (§11; F7, F45).
- Open questions 1, 2, 5, 6 adopted as proposed; 3 resolved by D5; 4 adopted with a stateless `get_brief` window (C4 §3.15; F16, F31, F38).
- Post-verify fixes (orchestrator): RuleDraft personal branches may stay at household level; the debrief-threshold comment defers to C6; test 9 covers a review and an unreadable document.

## 1. Conventions

### 1.1 Names
1. DB tables and columns, MCP tool names, parameters and results, `rules.yaml`, and Procrastinate job arguments use `snake_case`.
2. JSON DTOs served to the web (REST and `data-*` card payloads) use `camelCase`. The mapping is mechanical: split on `_`, capitalise every part after the first (`sub_unit_id` → `subUnitId`, `fiscal_year` → `fiscalYear`). Pydantic models use `alias_generator=to_camel`, `populate_by_name=True`, and serialise by alias.
3. The rule grammar (C5 §4: `conditions[]`, `action`, `rule_draft`) uses single-word keys only, so it is identical in the DB, MCP, `rules.yaml` and the DTOs.
4. Enum *values* are never re-cased, anywhere: the DB, MCP, `rules.yaml` and the DTOs carry the same strings (`contains_any`, `due_date`, `not_undoable`, `rulePreview`). Only object keys follow rule 2.
5. Enum values are stored as `text` with a `CHECK` constraint (no Postgres enum types, so migrations stay additive).

### 1.2 IDs
1. Every row id is `text`: a type prefix, `_`, and a 26-character ULID in lower-case Crockford base32 (`doc_01j9zq3k8e6y4v2m7c5r1t0b9a`). **Why:** sortable by creation time, safe in URLs, logs and model prompts, and the prefix makes an id from the wrong table fail loudly at the REST and MCP boundary.
2. Each id column carries `CHECK (id ~ '^<prefix>_[0-9a-hjkmnp-tv-z]{26}$')`.
3. Exceptions:
   - `file_ops.id` is `bigint GENERATED ALWAYS AS IDENTITY`: the journal number the UI shows (`JournalEntry.id: number`).
   - `categories.id` is the canonical category slug (`^[a-z][a-z0-9_]{1,39}$`, R14), because it is the enum the model sees and the key `rules.yaml` uses.
   - Subcategories are keyed by `(category_id, key)`.
   - `settings` and `profile` are single-row tables keyed by `singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton)`.
4. Registry rows that seed files or `rules.yaml` refer to (entities, sub-units, people, accounts, counterparties, rules) also carry a `key` slug (`^[a-z][a-z0-9-]{1,39}$`), unique within its scope. Seeds and exports reference keys, never ULIDs.

| Prefix | Table | Prefix | Table |
|---|---|---|---|
| `ent` | entities | `rev` | review_items |
| `sub` | sub_units | `grp` | op_groups |
| `per` | people | `int` | interviews |
| `acc` | accounts | `qst` | interview_questions |
| `cpt` | counterparties | `ans` | interview_answers |
| `tpl` | templates | `ddl` | deadlines |
| `rul` | rules | `rem` | reminders |
| `doc` | documents | `cnv` | conversations |
| `ext` | extractions | `trn` | chat_turns |
| `cls` | classifications | `crd` | card_events (the id *is* the `card_ref`) |
| `bat` | batches | `not` | card_action_notes |
| `itm` | intake_items | `drf` | drafts |
| `exp` | exports | | |

### 1.3 Types
1. Timestamps: `timestamptz`, written in UTC. DTOs: ISO 8601 with `Z` (`2026-10-14T07:02:00Z`).
2. Calendar dates: `date`. DTOs: `YYYY-MM-DD`.
3. Money: `numeric(14,2)` plus `currency text CHECK (currency IN ('EUR','RON'))`, both null or both set. DTOs: `Money = {value: number, currency: 'EUR'|'RON'}`, `value` rounded to 2 decimals.
4. Confidence: `smallint` 0–100 in the DB and DTOs. The model's 0–1 value is multiplied by 100 and rounded half-up before storage.
5. Paths: `text`, relative to their root (C7 §1), POSIX separators, Unicode NFC, no leading `/`, no `.` or `..` segment, no empty segment.
6. Normalised text columns (`*_norm`) hold `norm(x)` from C5 §2. They are written by the application, never by triggers.
7. Every table has `created_at timestamptz NOT NULL DEFAULT now()`; mutable tables also have `updated_at timestamptz NOT NULL DEFAULT now()`, set by the application on every update.

### 1.4 Extensions and search configuration
Migration `0001` (W0) created `unaccent` and `pg_trgm`. C1's first migration adds:

```sql
CREATE TEXT SEARCH CONFIGURATION mona (COPY = simple);
ALTER TEXT SEARCH CONFIGURATION mona
  ALTER MAPPING FOR hword, hword_part, word WITH unaccent, simple;
```

No stemming: FR/RO/EN are mixed in one archive and exact tokens are more predictable on stage. Inputs to `to_tsvector('mona', …)` and `websearch_to_tsquery('mona', …)` are always passed through `norm()` first, so ș/ş/ț/ţ and accents fold identically on both sides (`unaccent` is the second line of defence).

## 2. Registry

### 2.1 entities
```sql
entities (
  id                text PRIMARY KEY,                    -- ent_
  key               text NOT NULL UNIQUE,
  display_name      text NOT NULL,                       -- "Cabinet Marchand SELARL"
  folder_name       text NOT NULL UNIQUE,                -- on-disk top folder, accents kept (C5 §8.3)
  legal_form        text NULL,                           -- SELARL, SASU, LMNP, SCI, EI, Association
  siren             text NULL CHECK (siren ~ '^[0-9]{9}$'),
  visibility        text NOT NULL DEFAULT 'practice' CHECK (visibility IN ('practice','personal')),
  fy_end_month      smallint NOT NULL DEFAULT 12 CHECK (fy_end_month BETWEEN 1 AND 12),
  fy_end_day        smallint NOT NULL DEFAULT 31,
  filing_language   text NULL CHECK (filing_language IN ('fr','en','ro')),   -- null = settings.filing_language
  aliases           text[] NOT NULL DEFAULT '{}',        -- names as printed on documents
  addresses         text[] NOT NULL DEFAULT '{}',        -- postal address lines, for addressee matching
  purge_after_hours integer NULL CHECK (purge_after_hours > 0),   -- Visitors only; semantics in C9
  sort_order        integer NOT NULL DEFAULT 0,
  created_at, updated_at,
  CHECK (fy_end_day BETWEEN 1 AND CASE fy_end_month WHEN 2 THEN 28
                                    WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END)
)
CREATE UNIQUE INDEX entities_one_visitors ON entities ((true)) WHERE purge_after_hours IS NOT NULL;
```
- A fiscal-year end of 12-31 makes `{fy}` equal the calendar year of the period end (C5 §8.2), so an unknown FY end is stored as the default, not null.
- `aliases_norm`/`addresses_norm` are not stored; matching normalises at read time (the registry is small).
- **The Visitors entity** is the one entity with `purge_after_hours` set (at most one). A document has the Visitors entity **iff** its batch has `visitor = true` (§4.1). It is never offered to the model, never a rule action, and never a correction target (C5 §4.6.8, §5.2; C4 §3.5). C9 selects purge candidates by `batches.visitor`, never by entity alone.

### 2.2 sub_units
```sql
sub_units (
  id          text PRIMARY KEY,                           -- sub_
  entity_id   text NOT NULL REFERENCES entities ON DELETE RESTRICT,
  key         text NOT NULL,
  label       text NOT NULL,                              -- folder name, accents kept
  person_id   text NULL REFERENCES people ON DELETE SET NULL,  -- per-person split (AGIPI by insured person)
  created_at, updated_at,
  UNIQUE (entity_id, key), UNIQUE (entity_id, label)
)
```

### 2.3 people and entity_people
```sql
people (
  id            text PRIMARY KEY,                         -- per_
  key           text NOT NULL UNIQUE,
  display_name  text NOT NULL,
  short_name    text NULL,
  aliases       text[] NOT NULL DEFAULT '{}',             -- spellings on documents: "M. PAUL MARCHAND", "Marchand Paul"
  created_at, updated_at
)
entity_people (
  entity_id  text REFERENCES entities ON DELETE CASCADE,
  person_id  text REFERENCES people ON DELETE CASCADE,
  role       text NULL,                                   -- free text: "gérante", "insured", "associé"
  PRIMARY KEY (entity_id, person_id)
)
```

### 2.4 accounts
```sql
accounts (
  id            text PRIMARY KEY,                         -- acc_
  key           text NOT NULL UNIQUE,
  entity_id     text NOT NULL REFERENCES entities ON DELETE RESTRICT,
  sub_unit_id   text NULL REFERENCES sub_units ON DELETE SET NULL,
  bank_counterparty_id text NULL REFERENCES counterparties ON DELETE SET NULL,
  label         text NOT NULL,                            -- "Hello bank · LMNP"
  iban_hash     text NOT NULL UNIQUE CHECK (iban_hash ~ '^[0-9a-f]{64}$'),
  iban_last4    text NOT NULL CHECK (iban_last4 ~ '^[0-9A-Z]{4}$'),
  currency      text NOT NULL DEFAULT 'EUR' CHECK (currency IN ('EUR','RON')),
  created_at, updated_at
)
```
- **IBANs are never stored, logged, exported or returned in clear.** `iban_hash = hex(HMAC-SHA256(settings.iban_salt, normalize_iban(iban)))`, where `normalize_iban` upper-cases and drops every character outside `[0-9A-Z]`. The salt is 32 random bytes generated by the first migration that creates `settings`.
- DTOs show `ibanLast4` only (rendered `•• 4821` by the UI).
- Document text and quotes may contain an IBAN; that is document content (C9 governs where it may go). The rules engine matches IBANs by hashing candidates found in the text (C5 §4.3).

### 2.5 counterparties
```sql
counterparties (
  id          text PRIMARY KEY,                           -- cpt_
  key         text NOT NULL UNIQUE,
  name        text NOT NULL,                              -- canonical display name, used by {counterparty}
  name_norm   text NOT NULL UNIQUE,
  kind        text NULL CHECK (kind IN ('supplier','bank','insurer','administration','social','accountant','client','other')),
  siren       text NULL CHECK (siren ~ '^[0-9]{9}$'),
  origin      text NOT NULL CHECK (origin IN ('seed','extracted','user')),
  created_at, updated_at
)
counterparty_aliases (
  alias_norm       text PRIMARY KEY,                      -- norm(alias); an alias belongs to one counterparty
  counterparty_id  text NOT NULL REFERENCES counterparties ON DELETE CASCADE
)
CREATE INDEX counterparties_name_trgm ON counterparties USING gin (name_norm gin_trgm_ops);
```
- Every counterparty's own `name_norm` is also a row in `counterparty_aliases`, pointing to that counterparty.
- Resolution of an extracted counterparty string, alias learning on correction, and the merge of `extracted` counterparties are specified in C5 §6.2. Learning never moves another counterparty's own `name_norm` alias unless that counterparty is `extracted`, in which case it is merged away in the same transaction, so the invariant above always holds.

### 2.6 categories and subcategories
```sql
categories (
  id                text PRIMARY KEY,                     -- canonical slug, e.g. payment_calls
  labels            jsonb NOT NULL,                       -- {"en": "...", "fr": "...", "ro": "..."}, all three required
  icon              text NOT NULL DEFAULT 'invoice'
                    CHECK (icon IN ('bank','invoice','tax','insurance','payroll','training','travel','personal')),
  model_definition  text NOT NULL,                        -- English, one paragraph, feeds the prompt (C5 §5.3)
  sort_order        integer NOT NULL DEFAULT 0,
  created_at, updated_at,
  CHECK (labels ?& array['en','fr','ro'])
)
subcategories (
  category_id  text NOT NULL REFERENCES categories ON DELETE CASCADE,
  key          text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{0,39}$'),
  labels       jsonb NOT NULL CHECK (labels ?& array['en','fr','ro']),
  sort_order   integer NOT NULL DEFAULT 0,
  PRIMARY KEY (category_id, key)
)
```
- `icon` is exactly the DS `Category` union (`design/mona-design-system/components/index.d.ts`).
- `unknown` is not a category row; it only exists as a model output value (C5 §5.2).

### 2.7 templates
```sql
templates (
  id             text PRIMARY KEY,                        -- tpl_
  category_id    text NOT NULL REFERENCES categories ON DELETE CASCADE,
  entity_id      text NULL REFERENCES entities ON DELETE CASCADE,   -- null = the category default
  path_template  text NOT NULL,                           -- C5 §8 grammar
  file_template  text NOT NULL,                           -- C5 §8 grammar; must start with a {date…} token
  created_at, updated_at,
  UNIQUE NULLS NOT DISTINCT (category_id, entity_id)
)
```
- Every category has exactly one default row (`entity_id IS NULL`). Lookup order: entity override → category default → rule action override wins over both (C5 §4.5).
- Templates are validated on write by the C5 §8 parser; an invalid template is rejected with the parser's error (C2 maps it to 422).

## 3. Rules

```sql
rules (
  id                 text PRIMARY KEY,                    -- rul_
  key                text NOT NULL UNIQUE,                -- slug; seed/export identity (C5 §10); generated from name on creation, "-2", "-3" on clash
  name               text NOT NULL,
  state              text NOT NULL DEFAULT 'active' CHECK (state IN ('draft','active','disabled')),
  source             text NOT NULL CHECK (source IN ('seed','interview','correction')),
  priority           integer NOT NULL,                    -- C5 §4.6
  conditions         jsonb NOT NULL,                      -- C5 §4.2, validated on write
  action             jsonb NOT NULL,                      -- C5 §4.5, validated on write
  condition_text     jsonb NOT NULL CHECK (condition_text ?& array['en','fr','ro']),  -- rendered, C5 §4.7
  version            integer NOT NULL DEFAULT 1,
  fired_count        integer NOT NULL DEFAULT 0,
  last_fired_at      timestamptz NULL,
  corrections_since  integer NOT NULL DEFAULT 0,
  origin_question_id text NULL REFERENCES interview_questions ON DELETE SET NULL,
  origin_document_id text NULL REFERENCES documents ON DELETE SET NULL,    -- correction that created it
  created_at, updated_at
)
rule_versions (
  rule_id        text REFERENCES rules ON DELETE CASCADE,
  version        integer,
  conditions     jsonb NOT NULL,
  action         jsonb NOT NULL,
  condition_text jsonb NOT NULL,
  priority       integer NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (rule_id, version)
)
CREATE INDEX rules_active ON rules (priority DESC) WHERE state = 'active';
```
- Any change to `conditions`, `action` or `priority` increments `version`, writes a `rule_versions` row (the history UI is later; the data is kept now), and resets `corrections_since` to 0.
- `state` changes don't bump the version.
- `fired_count`, `last_fired_at`, `corrections_since`: C5 §4.8.
- DTO `enabled` = `state = 'active'`.

## 4. Documents

### 4.1 batches and intake_items
```sql
batches (
  id            text PRIMARY KEY,                         -- bat_
  source        text NOT NULL CHECK (source IN ('drop','telegram','reclassify')),
  status        text NOT NULL DEFAULT 'running' CHECK (status IN ('running','done')),
  title         text NULL,                                -- "Tuesday's post", set by the UI or null
  visitor       boolean NOT NULL DEFAULT false,           -- R38 volunteered documents: C5 §4.6.8 forces the Visitors entity
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz NULL,
  debrief_interview_id text NULL REFERENCES interviews ON DELETE SET NULL,
  created_at
)
intake_items (
  id              text PRIMARY KEY,                       -- itm_
  batch_id        text NOT NULL REFERENCES batches ON DELETE CASCADE,
  original_name   text NOT NULL,
  sha256          text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes      bigint NOT NULL,
  outcome         text NOT NULL CHECK (outcome IN ('accepted','duplicate','rejected')),
  document_id     text NULL REFERENCES documents ON DELETE SET NULL,  -- new doc, or the existing one for 'duplicate'
  reject_reason   text NULL CHECK (reject_reason IN ('unsupported_type','too_large','empty','unreadable_file')),
  created_at
)
```
- Batch counts are computed from `intake_items` and `documents`, not stored.
- **Who sets `visitor`.** `ingest_attachment(for_visitor)` (C4 §3.14) or the `visitor` flag of the web upload (C2). Until Telegram lands, the volunteered-document beat is a phone-browser upload with that flag (demo-script v1; L3 puts "Visitor document" on an upload the phone can reach).
- **The batch's journal group.** The transaction that creates a batch also creates its one `intake_batch` op group (`actor='mona'`, `via='pipeline'`, `batch_id` set; unique per batch, §5). Every pipeline journal entry for the batch's documents (`file`, `mark.unreadable`) carries that `group_id` and `batch_id`.
- **When a batch is `done`.** A running stage is `pipeline_stage IN ('queued','reading','ocr','classifying','filing')`. Every transaction that moves one of a batch's documents out of a running stage first locks the batch row (`SELECT … FOR UPDATE`); if no accepted document of the batch is left in a running stage, it sets `status='done'` and `finished_at = now()` in the same transaction. A batch with no accepted document is `done` at creation. After that commit, L1 calls the C6-owned batch-end hook once (it enqueues the debrief).

### 4.2 documents
```sql
documents (
  id                text PRIMARY KEY,                     -- doc_
  sha256            text NOT NULL UNIQUE CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  original_name     text NOT NULL,
  mime_type         text NOT NULL CHECK (mime_type IN ('application/pdf','image/jpeg','image/png')),
  size_bytes        bigint NOT NULL,
  page_count        integer NULL,
  source            text NOT NULL CHECK (source IN ('drop','telegram')),
  batch_id          text NOT NULL REFERENCES batches ON DELETE RESTRICT,
  arrived_at        timestamptz NOT NULL DEFAULT now(),

  location          text NOT NULL CHECK (location IN ('inbox','archive','trash')),   -- C7 §1
  current_path      text NOT NULL,                        -- relative to the location's root
  status            text NOT NULL CHECK (status IN ('processing','filed','review','unreadable')),
  pipeline_stage    text NOT NULL DEFAULT 'queued'
                    CHECK (pipeline_stage IN ('queued','reading','ocr','classifying','filing','done','failed')),
  pipeline_error    text NULL,
  reasons           text[] NOT NULL DEFAULT '{}'
                    CHECK (reasons <@ array['low','entity','conflict','unreadable']),

  title             text NULL,
  entity_id         text NULL REFERENCES entities ON DELETE RESTRICT,
  sub_unit_id       text NULL REFERENCES sub_units ON DELETE SET NULL,
  category_id       text NULL REFERENCES categories ON DELETE RESTRICT,
  subcategory_key   text NULL,
  counterparty_id   text NULL REFERENCES counterparties ON DELETE SET NULL,
  issuer            text NULL,
  reference         text NULL,
  doc_type          text NULL,
  doc_date          date NULL,
  period_start      date NULL,
  period_end        date NULL,
  fiscal_year       integer NULL,                         -- C5 §8.2: computed for every document with an entity, whatever its template
  amount            numeric(14,2) NULL,
  currency          text NULL CHECK (currency IN ('EUR','RON')),
  due_date          date NULL,
  addressee         text NULL,
  addressee_person_id text NULL REFERENCES people ON DELETE SET NULL,
  confidence        smallint NULL CHECK (confidence BETWEEN 0 AND 100),
  band              text NULL CHECK (band IN ('high','medium','low')),

  extraction_id     text NULL REFERENCES extractions ON DELETE SET NULL,      -- current
  classification_id text NULL REFERENCES classifications ON DELETE SET NULL,  -- current (last applied)
  rule_id           text NULL REFERENCES rules ON DELETE SET NULL,            -- the rule that decided the filing
  filed_at          timestamptz NULL,
  filed_by          text NULL CHECK (filed_by IN ('mona','user')),
  filed_op_id       bigint NULL REFERENCES file_ops,     -- the entry that last put it where it is (C7 §6)
  deleted_at        timestamptz NULL,

  head_norm         text NULL,                            -- norm(first 500 chars of page 1), exemplar retrieval (C5 §5.5)
  fts               tsvector NULL,
  created_at, updated_at,

  FOREIGN KEY (category_id, subcategory_key) REFERENCES subcategories (category_id, key) ON DELETE SET NULL (subcategory_key),
  CHECK ((amount IS NULL) = (currency IS NULL)),
  CHECK ((location = 'trash') = (deleted_at IS NOT NULL)),
  CHECK (status <> 'filed' OR location IN ('archive','trash')),   -- delete keeps the status (C7 §7)
  CHECK (status <> 'unreadable' OR 'unreadable' = ANY (reasons)),
  UNIQUE (location, current_path)
)
CREATE INDEX documents_fts      ON documents USING gin (fts);
CREATE INDEX documents_head     ON documents USING gin (head_norm gin_trgm_ops);
CREATE INDEX documents_facets   ON documents (entity_id, category_id, fiscal_year) WHERE deleted_at IS NULL;
CREATE INDEX documents_status   ON documents (status, arrived_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX documents_cpt      ON documents (counterparty_id) WHERE deleted_at IS NULL;
CREATE INDEX documents_doc_date ON documents (doc_date) WHERE deleted_at IS NULL;
```

**Status semantics** (DS `DocStatus`):

| status | location | meaning |
|---|---|---|
| `processing` | inbox | the pipeline hasn't reached a decision |
| `filed` | archive | moved and renamed by Mona or by you |
| `review` | inbox | in the review queue; `reasons` is non-empty |
| `unreadable` | inbox | no usable text after OCR; `reasons = {unreadable}`; also listed in the review queue |

- Documents with `deleted_at IS NOT NULL` are invisible to every read path except the journal and undo.
- Images keep their original bytes and extension in the archive (a phone photo is filed as `.jpg`); the viewer shows the cached OCR'd PDF (C5 §1.3, §1.4).
- `fts` is rebuilt by the application in the same transaction as any change to the fields it covers:

  ```
  setweight(to_tsvector('mona', norm(title || ' ' || counterparty.name || ' ' || aliases)), 'A')
  || setweight(to_tsvector('mona', norm(entity.display_name || ' ' || category labels (all 3) || ' ' || subcategory labels || ' ' || doc_type || ' ' || reference || ' ' || original_name)), 'B')
  || setweight(to_tsvector('mona', norm(page text, first 50 000 chars across pages))), 'C')
  ```

### 4.3 extractions and extraction_fields
```sql
extractions (
  id             text PRIMARY KEY,                        -- ext_
  document_id    text NOT NULL REFERENCES documents ON DELETE CASCADE,
  version        integer NOT NULL,                        -- 1, 2, … per document
  text_method    text NOT NULL CHECK (text_method IN ('pdftotext','ocr','none')),
  text_cache_key text NOT NULL,                           -- = documents.sha256 (C5 §1.3)
  char_count     integer NOT NULL,
  model          text NULL,                               -- null when no LLM call (unreadable)
  prompt_version text NULL,
  raw_output     jsonb NULL,                              -- the validated model JSON, verbatim
  from_cache     boolean NOT NULL DEFAULT false,          -- raw_output came from the model-output cache (C5 §1.3)
  duration_ms    integer NULL,
  prompt_tokens  integer NULL,
  completion_tokens integer NULL,
  created_at,
  UNIQUE (document_id, version)
)
extraction_fields (
  extraction_id  text REFERENCES extractions ON DELETE CASCADE,
  key            text CHECK (key IN ('entity','counterparty','issuer','reference','doc_type','doc_date',
                                     'period_start','period_end','amount','due_date','addressee')),
  value          text NOT NULL,                           -- canonical text form, C5 §5.2
  currency       text NULL CHECK (currency ~ '^[A-Z]{3}$'),     -- amount only; any ISO 4217 code (documents.amount keeps EUR/RON only)
  quote          text NOT NULL,
  page           integer NOT NULL CHECK (page >= 1),
  stated_page    integer NOT NULL,                        -- the page the model said; differs when C5 §6.1 corrected it
  verified       boolean NOT NULL,
  find_query     text NULL,                               -- C5 §7
  confidence     smallint NOT NULL CHECK (confidence BETWEEN 0 AND 100),
  PRIMARY KEY (extraction_id, key)
)
```
- A field the model returned as `null` has no row.
- Extractions are append-only. Re-extraction (new prompt, user request) writes `version + 1` and repoints `documents.extraction_id`.

### 4.4 classifications
```sql
classifications (
  id                  text PRIMARY KEY,                   -- cls_
  document_id         text NOT NULL REFERENCES documents ON DELETE CASCADE,
  extraction_id       text NULL REFERENCES extractions ON DELETE SET NULL,
  method              text NOT NULL CHECK (method IN ('llm','rule','user')),
  rule_id             text NULL REFERENCES rules ON DELETE SET NULL,
  conflicting_rule_ids text[] NOT NULL DEFAULT '{}',
  entity_id           text NULL REFERENCES entities,
  sub_unit_id         text NULL REFERENCES sub_units,
  category_id         text NULL REFERENCES categories,
  subcategory_key     text NULL,
  counterparty_id     text NULL REFERENCES counterparties,
  model_confidence    smallint NULL,                      -- the model's own number ×100
  confidence          smallint NOT NULL CHECK (confidence BETWEEN 0 AND 100),   -- after C5 §9 adjustments
  band                text NOT NULL CHECK (band IN ('high','medium','low')),
  reasons             text[] NOT NULL DEFAULT '{}' CHECK (reasons <@ array['low','entity','conflict','unreadable']),
  proposed_path       text NULL,                          -- rendered archive path (folders), C5 §8
  proposed_file_name  text NULL,
  created_at
)
CREATE INDEX classifications_doc ON classifications (document_id, created_at DESC);
```
- Every pipeline decision and every user correction writes a new row; `documents.classification_id` points to the one that was applied.

### 4.5 review_items
```sql
review_items (
  id            text PRIMARY KEY,                         -- rev_
  document_id   text NOT NULL REFERENCES documents ON DELETE CASCADE,
  reasons       text[] NOT NULL CHECK (cardinality(reasons) > 0),
  status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','dismissed')),
  resolution    text NULL CHECK (resolution IN ('confirmed','corrected','rule_applied','deleted','refiled')),
  scope         text NULL CHECK (scope IN ('one','all')),    -- CorrectionScopePrompt answer
  rule_id       text NULL REFERENCES rules ON DELETE SET NULL,
  resolved_by   text NULL CHECK (resolved_by IN ('mona','user')),
  created_at, resolved_at timestamptz NULL
)
CREATE UNIQUE INDEX review_items_one_open ON review_items (document_id) WHERE status = 'open';
```
Invariant: a non-deleted document has an open review item **iff** its status is `review` or `unreadable`.

`resolution` is written by the operation that closes the item, which passes it to `mona.fileops` (C7 §4.2 C.3): `confirmed` (you accepted the suggestion, C2), `corrected` (a correction, C4 §3.5 or C2), `rule_applied` (`apply_rule`), `deleted` (delete), `refiled` (any other file op, the default). It is stored for the journal and history; no DTO reads it in v1.

## 5. Journal

Semantics are C7's; the shape is here.

```sql
op_groups (
  id            text PRIMARY KEY,                         -- grp_
  kind          text NOT NULL CHECK (kind IN ('intake_batch','rule_apply','correction','undo','redo','refile')),
  actor         text NOT NULL CHECK (actor IN ('mona','user')),
  via           text NOT NULL CHECK (via IN ('ui','chat','telegram','pipeline')),
  batch_id      text NULL REFERENCES batches ON DELETE SET NULL,
  rule_id       text NULL REFERENCES rules ON DELETE SET NULL,
  target_group_id text NULL REFERENCES op_groups,         -- undo/redo groups: the group they reverse
  created_at
)
CREATE UNIQUE INDEX op_groups_intake ON op_groups (batch_id) WHERE kind = 'intake_batch';
file_ops (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,   -- the journal number
  at            timestamptz NOT NULL DEFAULT now(),
  actor         text NOT NULL CHECK (actor IN ('mona','user')),
  via           text NOT NULL CHECK (via IN ('ui','chat','telegram','pipeline')),
  action        text NOT NULL CHECK (action IN (
                  'file','move','rename','unfile','delete','undo','redo',
                  'doc.update','rule.create','rule.change','deadline.add','reminder.add','mark.unreadable')),
  document_id   text NULL REFERENCES documents ON DELETE RESTRICT,
  subject_id    text NULL,                                -- rul_/ddl_/rem_ for non-document actions
  sha256        text NULL,                                -- document sha at the time, for forensics
  before        jsonb NULL,                               -- C7 §2.2 PathState, or the changed fields
  after         jsonb NULL,
  fs_state      text NOT NULL DEFAULT 'done' CHECK (fs_state IN ('pending','done','failed')),   -- C7 §4
  batch_id      text NULL REFERENCES batches ON DELETE SET NULL,
  group_id      text NULL REFERENCES op_groups ON DELETE SET NULL,
  rule_id       text NULL REFERENCES rules ON DELETE SET NULL,
  confidence    smallint NULL,
  band          text NULL CHECK (band IN ('high','medium','low')),   -- 'medium' is the "marked in the journal" state
  undoable      boolean NOT NULL,                         -- the action kind supports undo (C7 §5.1); not the live state
  undone_by     bigint NULL UNIQUE REFERENCES file_ops,
  undo_of       bigint NULL REFERENCES file_ops,
  CHECK ((action IN ('undo','redo')) = (undo_of IS NOT NULL))
)
CREATE INDEX file_ops_doc     ON file_ops (document_id, id DESC);
CREATE INDEX file_ops_group   ON file_ops (group_id, id DESC);
CREATE INDEX file_ops_pending ON file_ops (id) WHERE fs_state = 'pending';
CREATE UNIQUE INDEX file_ops_undo_of_live ON file_ops (undo_of) WHERE fs_state <> 'failed';
```
- `file_ops` is the whole journal, including non-file actions; the name follows the plan.
- Entries with `fs_state <> 'done'` are hidden from every read path except recovery (C7 §4).
- An entry has at most one pending or done undo; a `failed` undo attempt doesn't block the next one. A violation of `file_ops_undo_of_live` is reported as `already_undone` (C7 §5.3).
- **The activity log is `file_ops` + `op_groups`.** There is no separate activity table.
- **Actor = who executed (D5).** `user` only for direct actions in the web UI (`via='ui'`: clicks, card buttons, forms). Everything done through Mona's tools or the pipeline is `mona`: `via='chat'` (web chat), `'telegram'` (Telegram and Hermes cron) or `'pipeline'`. The Activity log's "by you" means "done by you in the app". This amends plan §9 / HANDOFF §6 ("Telegram owner actions count as user").

## 6. Workflow

### 6.1 Interviews (semantics: C6)
```sql
interviews (
  id              text PRIMARY KEY,                       -- int_
  kind            text NOT NULL CHECK (kind IN ('seed','debrief','on_demand')),
  status          text NOT NULL DEFAULT 'generating' CHECK (status IN ('generating','ready','done','failed','cancelled')),
  scope           jsonb NOT NULL,                         -- C6
  lang            text NOT NULL CHECK (lang IN ('en','fr','ro')),
  batch_id        text NULL REFERENCES batches ON DELETE SET NULL,
  conversation_id text NULL REFERENCES conversations ON DELETE SET NULL,
  analysis        text NULL,                              -- pass 1 output, never sent to the web
  error           text NULL,
  created_at, ready_at timestamptz NULL, finished_at timestamptz NULL
)
interview_questions (
  id                    text PRIMARY KEY,                 -- qst_
  interview_id          text NOT NULL REFERENCES interviews ON DELETE CASCADE,
  ordinal               smallint NOT NULL CHECK (ordinal BETWEEN 1 AND 7),
  text                  text NOT NULL,                    -- in interviews.lang
  impact                integer NOT NULL,
  affected_document_ids text[] NOT NULL,
  evidence              jsonb NOT NULL,                   -- Evidence[] (§11.2) with snake_case keys; documentTitle is filled at serve time
  options               jsonb NOT NULL,                   -- [{id, label, suggested, rule_draft}]; rule_draft = §11.5 RuleDraft, snake_case keys; C6
  suggestion_confidence smallint NOT NULL,
  status                text NOT NULL DEFAULT 'open' CHECK (status IN ('open','answered','skipped')),
  created_at,
  UNIQUE (interview_id, ordinal)
)
interview_answers (
  id            text PRIMARY KEY,                         -- ans_
  question_id   text NOT NULL UNIQUE REFERENCES interview_questions ON DELETE CASCADE,
  option_id     text NULL,
  free_text     text NULL,
  actor         text NOT NULL CHECK (actor IN ('mona','user')),
  via           text NOT NULL CHECK (via IN ('ui','chat','telegram','pipeline')),
  created_at,
  CHECK (option_id IS NOT NULL OR free_text IS NOT NULL)
)
```
- An answer yields zero or more rules, one per branch of the chosen option's `rule_draft` (§11.5). They are the rows `rules WHERE origin_question_id = <question id>`; each rule's applications are its `rule_apply` op groups (`op_groups.rule_id`). There is no rule or group column on the answer.

### 6.2 Deadlines and reminders
```sql
deadlines (
  id            text PRIMARY KEY,                         -- ddl_
  document_id   text NULL REFERENCES documents ON DELETE SET NULL,
  entity_id     text NOT NULL REFERENCES entities ON DELETE RESTRICT,
  label         text NOT NULL,
  due_date      date NOT NULL,
  amount        numeric(14,2) NULL,
  currency      text NULL CHECK (currency IN ('EUR','RON')),
  paid_by_account_id text NULL REFERENCES accounts ON DELETE SET NULL,
  status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','dismissed')),
  origin        text NOT NULL CHECK (origin IN ('extracted','mona','user')),
  created_at, updated_at,
  CHECK ((amount IS NULL) = (currency IS NULL))
)
CREATE UNIQUE INDEX deadlines_doc_date ON deadlines (document_id, due_date) WHERE document_id IS NOT NULL;
reminders (
  id           text PRIMARY KEY,                          -- rem_
  deadline_id  text NULL REFERENCES deadlines ON DELETE CASCADE,
  document_id  text NULL REFERENCES documents ON DELETE CASCADE,
  remind_on    date NOT NULL,
  note         text NULL,
  status       text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','delivered','cancelled')),
  created_by   text NOT NULL CHECK (created_by IN ('mona','user')),
  created_at, delivered_at timestamptz NULL,
  CHECK (deadline_id IS NOT NULL OR document_id IS NOT NULL)
)
CREATE UNIQUE INDEX reminders_once ON reminders (coalesce(deadline_id, document_id), remind_on) WHERE status = 'scheduled';
```
- A filed document with a verified `due_date` gets an `extracted` deadline (L1 writes it in the filing transaction) **only if `due_date` ≥ the document's arrival date** (`arrived_at` as a Europe/Paris calendar date). A document that arrives after its due date is history, not a deadline; this keeps an ingested archive from flooding "what's due" and the brief with stale overdue items.

### 6.3 Drafts and exports (L4)
```sql
drafts (
  id           text PRIMARY KEY,                          -- drf_
  document_id  text NOT NULL REFERENCES documents ON DELETE CASCADE,
  lang         text NOT NULL CHECK (lang IN ('en','fr','ro')),
  instructions text NULL,
  status       text NOT NULL DEFAULT 'generating' CHECK (status IN ('generating','ready','failed')),
  title        text NULL,
  body         text NULL,
  error        text NULL,
  created_at, updated_at
)
exports (
  id            text PRIMARY KEY,                         -- exp_
  entity_id     text NOT NULL REFERENCES entities ON DELETE RESTRICT,
  fiscal_year   integer NOT NULL,
  status        text NOT NULL DEFAULT 'building' CHECK (status IN ('building','ready','failed')),
  document_count integer NULL,
  zip_path      text NULL,                                -- relative to /data/exports
  csv_path      text NULL,
  error         text NULL,
  created_at, updated_at
)
```

## 7. Chat (semantics: C3)

```sql
conversations (
  id                text PRIMARY KEY,                     -- cnv_; also the Hermes session id (C3 §4.1)
  title             text NOT NULL,                        -- first user message, C3 §7.1
  created_at, updated_at,
  last_message_at   timestamptz NOT NULL DEFAULT now()
)
chat_turns (
  id                text PRIMARY KEY,                     -- trn_
  conversation_id   text NOT NULL REFERENCES conversations ON DELETE CASCADE,
  status            text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','failed','aborted')),
  user_text         text NOT NULL,                        -- the person's message as sent upstream (trimmed)
  ui_message_id     text NOT NULL,                        -- the assistant UIMessage id sent in `start`
  reply_language    text NOT NULL CHECK (reply_language IN ('en','fr','ro')),
  opened_at         timestamptz NOT NULL DEFAULT now(),
  lease_expires_at  timestamptz NOT NULL,
  closed_at         timestamptz NULL,
  reasoning_ms      integer NULL,
  finish_reason     text NULL,
  error_code        text NULL,
  usage             jsonb NULL,
  parts             jsonb NOT NULL DEFAULT '[]'           -- the assistant parts as streamed (C3 §7.2); written when the turn ends
)
CREATE UNIQUE INDEX chat_turns_one_open ON chat_turns (conversation_id) WHERE status = 'open';
CREATE INDEX chat_turns_conv ON chat_turns (conversation_id, opened_at);
card_events (
  id               text PRIMARY KEY,                      -- crd_; this is the card_ref
  tool             text NOT NULL,                         -- MCP tool name without the Hermes prefix
  kind             text NOT NULL CHECK (kind IN ('doc','deadline','interview','rulePreview','draft','export')),
  subject          jsonb NOT NULL,                        -- ids only, C3 §5.2
  channel          text NOT NULL CHECK (channel IN ('web','telegram')),
  turn_id          text NULL REFERENCES chat_turns ON DELETE SET NULL,
  emitted_at       timestamptz NULL,                      -- first time the adapter streamed it
  created_at
)
CREATE INDEX card_events_turn ON card_events (turn_id, created_at);
card_action_notes (
  id               text PRIMARY KEY,                      -- not_
  conversation_id  text NOT NULL REFERENCES conversations ON DELETE CASCADE,
  kind             text NOT NULL,                         -- C3 §6.2
  text             text NOT NULL CHECK (length(text) <= 300),
  created_at,
  consumed_turn_id text NULL REFERENCES chat_turns ON DELETE SET NULL
)
CREATE INDEX card_action_notes_pending ON card_action_notes (conversation_id, created_at) WHERE consumed_turn_id IS NULL;
```
- The transcript is served from `chat_turns` (C3 §7.2), not from Hermes: Hermes compression forks sessions and its messages endpoint pages at 500, so it can't rebuild a long conversation.

## 8. Profile and settings

```sql
profile (
  singleton          boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  name               text NOT NULL,
  password_hash      text NOT NULL,                       -- argon2id, PHC string
  locale             text NOT NULL DEFAULT 'en' CHECK (locale IN ('en','fr','ro')),
  auto_lock_minutes  integer NOT NULL DEFAULT 15 CHECK (auto_lock_minutes BETWEEN 1 AND 1440),
  locked_at          timestamptz NULL,                    -- non-null = locked; C2 returns 423 on writes
  password_changed_at timestamptz NOT NULL DEFAULT now(),
  created_at, updated_at
)
settings (
  singleton          boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  practice_name      text NOT NULL,
  filing_language    text NOT NULL DEFAULT 'fr' CHECK (filing_language IN ('fr','en','ro')),
  confidence_high    smallint NOT NULL DEFAULT 85,
  confidence_low     smallint NOT NULL DEFAULT 60,
  badge_hours        smallint NOT NULL DEFAULT 24 CHECK (badge_hours BETWEEN 1 AND 168),
  debrief_queue_threshold smallint NOT NULL DEFAULT 5,    -- C6 decides the trigger; it may start a batch debrief before the batch is done (demo-script v1)
  iban_salt          bytea NOT NULL,                      -- 32 bytes, generated at creation, never exported
  created_at, updated_at,
  CHECK (0 < confidence_low AND confidence_low < confidence_high AND confidence_high <= 100)
)
```
- Browser sessions and CSRF tokens are C2's (table name `auth_sessions` is reserved for it).
- The profile and settings rows are created by `mona migrate` + the seed loader; they always exist after seeding.

## 9. Seed loading

The seed loader (`mona seed load <dir>`, L5 owns the files, L2 owns the loader) reads:
- `demo/seed/practice.yaml`: practice, people, entities (with sub-units), categories (with subcategories, labels, icon, model definition), templates, and:
  - `accounts`: `{key, entity, sub_unit?, label, currency, bank_counterparty?, iban: {ref}}` (§2.4; the IBAN only through the overlay);
  - `counterparties`: `{key, name, kind?, siren?: {ref} | null, aliases: [..]}` (§2.5, `origin='seed'`; `name_norm` and every alias are normalised by the loader);
- `demo/seed/rules.yaml`: the C5 §10 schema (the same schema the export writes);
- an optional identifier overlay outside the repo (`~/DevFiles/mona-hq/demo-data/seed/identifiers.yaml` in dev, mounted read-only at `/seed-private/identifiers.yaml` in the container): IBANs, SIRENs, addresses, private display names, referenced by key from the committed files (`iban: {ref: ...}`).

Invariants (each is a test obligation, §12):
1. **Keys, not ids.** Files reference registry rows by `key` (categories by id). Every reference resolves or the load fails with the full list of unresolved references, and nothing is written (one transaction).
2. **Idempotent.** Loading the same files twice yields the same rows (upsert by key); ids are generated once and kept.
3. **No clear IBAN.** The loader hashes IBANs from the overlay (§2.4) and never writes them anywhere else, including logs and error messages (errors name the key, not the value).
4. **Complete labels.** Every category and subcategory has `en`, `fr` and `ro` labels; every `icon` is in the DS union.
5. **Templates parse** with the C5 §8 parser, and every file template starts with a `{date…}` token.
6. **Rules validate** against C5 §4 and `rules.yaml` round-trips: `export(load(f))` equals `f` modulo stats and ordering.
7. **One default template** per category.
8. The loader never touches documents, the journal, chat or Hermes; demo-reset restores those from the snapshot (L5).

**Demo reset (pointers for L5b and C9; not the loader's job):**
- The snapshot is taken after `recover_pending()` (C7 §4.3) and restored as one unit: the DB, `/data/inbox`, `/data/archive`, `/data/trash`, `/data/textcache` (text, OCR, thumbnail and model-output caches, C5 §1.3), `/data/config` and the Hermes profile. Restoring the archive without the inbox loses the files of documents in review (C7 §9 invariant 1).
- The snapshot DB has no `conversations`, `chat_turns`, `card_events` or `card_action_notes` rows (the restored Hermes profile has no sessions).
- `--anchor` shifts event timestamps (`arrived_at`, `filed_at`, `file_ops.at`, batch and interview times, …) and never printed dates (`doc_date`, `due_date`, `period_*`, extracted values).
- The demo seed leaves out the rules learned live on stage (AGIPI split, Hello bank; demo-script v1).

## 10. Deletion and retention (shape only)

- Registry rows referenced by documents are `ON DELETE RESTRICT`; the UI disables delete for them (C2).
- Document deletion is a move to trash (C7 §7); rows are never hard-deleted by the application, except the Visitors purge (C9).

## 11. DTOs (canonical; C2 serves them, C3 cards embed them)

TypeScript is the notation; the Pydantic models mirror it. Fields marked *ext.* extend HANDOFF §6 (plan §12b P2-3); fields marked *delta* change a HANDOFF type. The web's shape-delta table (`briefs/l3.md`) copies §11.9.

### 11.1 Shared
```ts
type Lang = 'en' | 'fr' | 'ro';
type Currency = 'EUR' | 'RON';
interface Money { value: number; currency: Currency }
type DocStatus = 'filed' | 'review' | 'processing' | 'unreadable';
type Reason = 'low' | 'entity' | 'conflict' | 'unreadable';
type Band = 'high' | 'medium' | 'low';
type Actor = 'mona' | 'user';
type Via = 'ui' | 'chat' | 'telegram' | 'pipeline';
type FieldKey = 'entity' | 'counterparty' | 'issuer' | 'reference' | 'doc_type' | 'doc_date'
              | 'period_start' | 'period_end' | 'amount' | 'due_date' | 'addressee';   // = extraction_fields.key (§1.1.4)
type ConditionField = 'counterparty' | 'text' | 'doc_type' | 'category' | 'entity' | 'addressee'
                    | 'person' | 'iban' | 'siren' | 'amount';                            // C5 §4.2
```

### 11.2 Evidence and ExtractedField
```ts
interface Evidence {
  documentId: string;
  documentTitle: string;         // ext. documents.title, else originalName; EvidenceSnippet shows it with the page
  field: FieldKey | null;        // ext. null for interview clues
  page: number;                  // 1-based, after C5 §6.1 page correction
  quote: string;                 // verbatim, as the model returned it
  verified: boolean;
  findQuery: string | null;      // ext. what the viewer sends to pdf.js find (C5 §7); null = show the snippet only
}
interface ExtractedField {
  key: FieldKey;
  value: string;                 // dates YYYY-MM-DD; amounts "1284.00"; text as extracted
  money?: Money;                 // ext. amount only
  evidence: Evidence;
  confidence: number;            // 0–100
}
```

### 11.3 DocumentSummary and DocumentDetail
```ts
interface DocumentSummary {
  id: string;
  title: string;                 // documents.title, else originalName
  originalName: string;
  fileName: string;              // current basename (the inbox name while not filed)
  path: string[];                // archive folder segments; [] unless location = 'archive'
  location: 'inbox' | 'archive'; // ext.
  entityId: string | null;       // delta: nullable
  entityName: string | null;     // ext.
  subUnitId: string | null;      // ext.
  categoryId: string | null;     // delta: nullable
  subcategoryKey: string | null; // ext.
  counterpartyId: string | null; // ext.
  counterparty: string | null;   // ext. canonical name
  docType: string | null;        // ext.
  reference: string | null;      // ext.
  date: string | null;           // delta: nullable; = doc_date
  periodStart: string | null;    // ext.
  periodEnd: string | null;      // ext.
  fiscalYear: number | null;     // ext.
  amount?: Money;
  dueDate: string | null;        // ext.
  status: DocStatus;
  reasons: Reason[];             // delta: always present, [] when none
  confidence: number | null;     // delta: nullable while processing
  band: Band | null;             // ext.
  pipelineStage: 'queued' | 'reading' | 'ocr' | 'classifying' | 'filing' | 'done' | 'failed';  // ext.
  arrivedAt: string;
  source: 'drop' | 'telegram';
  filedAt: string | null;        // ext.
  filedBy: Actor | null;         // ext.
  badgeUntil: string | null;     // ext. non-null only while the "filed by Mona" badge shows (C7 §6)
  rule: { id: string; name: string } | null;   // ext. rule that fired
  batchId: string;               // ext.
  pageCount: number | null;      // ext.
  thumbnailUrl: string | null;   // ext. C2 path; null until the thumbnail exists
  pdfUrl: string;                // ext. C2 `/api/documents/{id}/pdf`
}
interface DocumentDetail extends DocumentSummary {
  fields: ExtractedField[];
  suggestion: Suggestion | null; // present while status is review/unreadable
  journal: JournalEntry[];       // this document's entries, newest first
  deadlines: Deadline[];
}
```

### 11.4 Suggestion
```ts
interface Suggestion {
  entityId: string | null; subUnitId: string | null;
  categoryId: string | null; subcategoryKey: string | null;
  fileName: string | null;       // delta: nullable when no template can render
  path: string[];
  confidence: number; band: Band;               // ext. band
  reasons: Reason[];                            // ext.
  sentence: string;              // rendered at serve time in the request locale (C5 §9.4)
  evidence: Evidence[];
  ruleId: string | null;                        // ext.
  conflictingRuleIds: string[];                 // ext.
}
```

### 11.5 Rule, RuleDraft, RulePreview
```ts
interface Rule {
  id: string; name: string;
  condition: string;             // = conditionText in the request locale (HANDOFF name kept)
  conditionText: string;         // ext.
  conditions: Condition[];       // ext. C5 §4.2
  action: RuleAction;            // ext. C5 §4.5
  destination: string[];         // C5 §4.7: action path template with resolvable tokens filled
  enabled: boolean;
  state: 'draft' | 'active' | 'disabled';   // ext.
  source: 'interview' | 'correction' | 'seed';
  version: number; priority: number;        // ext. priority
  firedCount: number; lastFiredAt?: string; correctionsSince: number;
}
interface RuleDraft {            // ext. S6 branch shape; C6 owns semantics
  kind: 'always' | 'depends' | 'ask';
  discriminator: ConditionField | null;         // required for 'depends', null otherwise
  branches: { conditions: Condition[]; action: RuleAction }[];
}
interface RulePreview {
  rule: Rule;
  moves: { documentId: string; title: string; from: string[]; fromFileName: string; to: string[]; toFileName: string }[];
  movesTotal: number;            // ext. moves[] is capped (C4 §2)
  stays: string[];               // document ids
  staysTotal: number;            // ext.
  applied: boolean;              // ext.
  groupId: string | null;        // ext. set once applied
}
```
**RuleDraft** (validated on write, C5 §4 for each branch):
- `always`: exactly one branch. `depends`: 2–4 branches and a `discriminator`; the branches differ in a condition on that field. `ask`: no branches (whether C6 records it as a `review: true` rule, C5 §4.5, is C6's).
- Every branch action names an entity, never null (S6 T6). A personal branch may add a person sub-unit (`unit` key or `{from: person}`) when the answer splits by person; without one it files at the household level (C5 §4.5). Stricter rules are C6's.
- Accepting an option creates one rule per branch (§6.1).

**RulePreview** (`applied` and the lists):
- `applied` = the rule has a `rule_apply` op group (`op_groups.rule_id`) whose live state (C7 §5.4) is not `undone`; `groupId` = the latest such group.
- Not applied: `moves`/`stays` are the C4 §3.8 candidates computed from current state.
- Applied: `moves` are the `done` entries of `groupId` (`from` = `before`, `to` = `after`), `movesTotal` their count; `stays` are the C4 §3.8 candidates whose documents are not in that group, `staysTotal` their count. So the card keeps showing "4 move · 2 stay" after Apply, whether it comes from the tool, from the card button or from a C2 refresh.

### 11.6 Journal
```ts
interface PathState { location: 'inbox' | 'archive' | 'trash'; path: string[]; fileName: string; status: DocStatus }
interface JournalEntry {
  id: number; at: string; actor: Actor;
  via: Via;                                     // ext.
  action: 'file' | 'move' | 'rename' | 'unfile' | 'delete' | 'undo' | 'redo'
        | 'doc.update' | 'rule.create' | 'rule.change' | 'deadline.add' | 'reminder.add' | 'mark.unreadable';
  documentIds: string[];                        // 0 or 1 element (HANDOFF shape kept)
  subjectId: string | null;                     // ext.
  before: PathState | Record<string, unknown> | null;
  after: PathState | Record<string, unknown> | null;
  batchId?: string; groupId: string | null;     // ext. groupId
  ruleId: string | null; confidence: number | null; band: Band | null;   // ext.
  undoable: boolean;                            // delta: the LIVE state, = undoState === 'undoable'
  undoState: 'undoable' | 'undone' | 'superseded' | 'not_undoable';      // ext. C7 §5.2
  undoneBy?: number; undoOf: number | null;     // ext. undoOf
}
interface JournalGroup {                        // ext. ActivityBatch
  id: string; kind: 'intake_batch' | 'rule_apply' | 'correction' | 'undo' | 'redo' | 'refile';
  at: string; actor: Actor; via: Via; batchId: string | null; ruleId: string | null;
  counts: { entries: number; undoable: number; superseded: number; undone: number };
  undoState: 'undoable' | 'partial' | 'undone' | 'not_undoable';        // C7 §5.4
  targetGroupId: string | null;
}
```

### 11.7 Deadline, Interview, Draft, Export
```ts
interface Deadline {
  id: string; documentId: string | null;        // delta: nullable
  label: string; entityId: string; entityName: string;   // ext. entityName
  dueDate: string; amount?: Money;
  paidBy?: string;                              // account label + " •• " + last4
  status: 'open' | 'done' | 'dismissed';        // ext.
  daysLeft: number;                             // ext. negative when overdue, relative to the server's date (Europe/Paris)
  reminder: { id: string; remindOn: string } | null;     // ext.
}
interface InterviewQuestion {                   // = HANDOFF `Interview` (one question)
  id: string; ordinal: number;
  question: string; lang: Lang;
  affects: string[];                            // document ids
  affectsCount: number;                         // ext.
  evidence: Evidence[];
  options: { id: string; label: string; suggested?: boolean; ruleDraft: RuleDraft | null }[];   // ext. ruleDraft
  suggestionConfidence: number;
  status: 'open' | 'answered' | 'skipped';      // ext.
  answer: { optionId: string | null; freeText: string | null; ruleIds: string[] } | null;  // ext. one rule per branch (§6.1)
}
interface Interview {                           // ext. container; C6 may extend
  id: string; kind: 'seed' | 'debrief' | 'on_demand';
  status: 'generating' | 'ready' | 'done' | 'failed' | 'cancelled';
  questions: InterviewQuestion[];               // [] while generating
  batchId: string | null; createdAt: string;
}
interface Draft { id: string; documentId: string; lang: Lang; status: 'generating' | 'ready' | 'failed'; title: string | null; body: string | null; docxUrl: string | null }
interface ExportPack { id: string; entityId: string; entityName: string; fiscalYear: number; status: 'building' | 'ready' | 'failed'; documentCount: number | null; zipUrl: string | null; csvUrl: string | null }
```

### 11.8 Registry DTOs (C2 serves; listed so C3/C4 agree)
```ts
interface Entity { id: string; key: string; displayName: string; folderName: string; legalForm: string | null; siren: string | null;
  visibility: 'practice' | 'personal'; fiscalYearEnd: string /* "MM-DD" */; filingLanguage: Lang | null;
  subUnits: { id: string; key: string; label: string; personId: string | null }[];
  people: { personId: string; role: string | null }[];
  accounts: { id: string; key: string; label: string; ibanLast4: string; subUnitId: string | null }[] }
interface Person { id: string; key: string; displayName: string; shortName: string | null }
interface Category { id: string; labels: Record<Lang, string>; icon: 'bank' | 'invoice' | 'tax' | 'insurance' | 'payroll' | 'training' | 'travel' | 'personal';
  subcategories: { key: string; labels: Record<Lang, string> }[];
  template: { pathTemplate: string; fileTemplate: string };
  entityTemplates: { entityId: string; pathTemplate: string; fileTemplate: string }[] }
interface Counterparty { id: string; key: string; name: string; kind: string | null }
```

### 11.9 Shape deltas against HANDOFF §6 (summary for L3)
| HANDOFF | Change |
|---|---|
| `DocumentSummary.entityId`, `categoryId`, `date`, `confidence` | nullable |
| `DocumentSummary.reasons` | always present |
| `DocumentSummary` | + location, entityName, subUnitId, subcategoryKey, counterpartyId, counterparty, docType, reference, periodStart, periodEnd, fiscalYear, dueDate, band, pipelineStage, filedAt, filedBy, badgeUntil, rule, batchId, pageCount, thumbnailUrl, pdfUrl |
| `Evidence` | + documentTitle, field, findQuery; `boxes` not served (v2) |
| `ExtractedField.key` | closed `FieldKey` set, snake_case values (`due_date`, not `dueDate`); + money |
| `Suggestion` | + band, reasons, ruleId, conflictingRuleIds; fileName nullable |
| `Rule` | + conditionText, conditions, action, state, priority |
| `RuleDraft`, `RulePreview` | new (§11.5); RuleDraft is branch-shaped |
| `JournalEntry` | + via, subjectId, groupId, ruleId, confidence, band, undoState, undoOf; `undoable` is the live state |
| `Deadline` | documentId nullable; + entityName, status, daysLeft, reminder |
| `Interview` | renamed `InterviewQuestion`; + ordinal, lang, affectsCount, options[].ruleDraft, status, answer (with `ruleIds`); new container `Interview` |
| `ChatItem` | replaced by AI SDK UI message parts (C3 §3) |

## 12. Test obligations

Mutation-checked items are marked **[M]** (break the code, watch the test fail, restore).

1. **Migration round-trip.** `alembic upgrade head` on an empty DB, `downgrade base`, `upgrade head` again: no errors; the schema dump after the second upgrade equals the first.
2. **Constraint tests**, one per constraint class, each asserting the insert fails: bad id prefix; `amount` without `currency`; `status='filed'` with `location='inbox'`; `reasons` outside the set; `fy_end_day=31` with month 4; two open review items for one document; two open chat turns in one conversation; `confidence_low >= confidence_high`; category `icon` outside the DS union; category labels missing `ro`; a `file_ops` row with `action='undo'` and null `undo_of`; a second `intake_batch` group for one batch; a second entity with `purge_after_hours`; a second live undo of one entry. And one that must succeed: a new undo of an entry whose earlier undo is `failed`.
3. **IBAN never in clear [M].** Load a seed overlay with a known synthetic IBAN; then `pg_dump --data-only` of the database, the loader's log output and the rules export contain neither the IBAN nor its space-grouped form. Mutation: store the IBAN in `label` → the test fails.
4. **Seed invariants (§9) [M]:** unresolved reference fails the whole load and names the key; loading twice leaves identical rows (ids included); rules export round-trips. Mutation: skip the reference check → test fails.
5. **FTS folding.** A document whose title contains "Societatea Științifică" is found by the query "stiintifica" and by "ştiinţifică" (cedilla forms); "Échéance" is found by "echeance".
6. **DTO naming [M].** For every DTO model, serialising a fully populated instance yields only camelCase keys, except the contents of `conditions`, `action` and `ruleDraft`, whose keys are all single words. Every enum value in a DTO equals its DB value (`ExtractedField.key` = `extraction_fields.key`, `Evidence.field`, `undoState`). Mutation: re-case `FieldKey` values → the test fails.
7. **Review invariant.** After each pipeline outcome and each correction path in L1/L2 tests, `status IN ('review','unreadable')` ⇔ one open review item.
8. **Extracted deadlines [M]** (L1): a verified `due_date` one day before the arrival date (Europe/Paris) → no deadline; on the arrival date or later → one `extracted` deadline. Mutation: drop the date comparison.
9. **Batch lifecycle [M]** (L1): three documents of one batch (one filed, one classified into review, one unreadable) finishing concurrently on three `cpu` workers → exactly one transition to `done`, one `finished_at`, one batch-end hook call, one `intake_batch` group holding every pipeline entry of the batch. Mutation: skip the batch-row lock → the test fails (run it in a loop).
10. **Visitors invariant:** a visitor batch's documents all end with the Visitors entity; a non-visitor document never does, whatever the model or a rule returns.
11. **RuleDraft validation:** `always` with two branches, `depends` without a discriminator, `ask` with a branch, and a branch action without an entity are each rejected; the S6 T6 branch outputs, re-keyed to the C5 §8.5 registry, validate.

## 13. Open questions

Resolved in 0.2: 1 (categories keyed by slug), 2 (counterparty registry), 5 (delete to trash, C7 §7) and 6 (images keep original bytes, §4.2) adopted as proposed; 3 resolved by D5 (§5); 4 adopted: Home renders `MonaBrief` from `get_brief` facts with i18n templates, no stored prose, and C2 passes an explicit window (C4 §3.15).

Still open:
1. **Nothing closes an extracted deadline.** `deadlines.status` has `done` and `dismissed`, but no set A tool or card action writes them, so a paid deadline stays open (and overdue) forever. Proposed: C2 gives `DeadlineCard` and Home a "Done" action that sets `done` (`user`/`ui`); Mona doesn't close deadlines in v1. Low block (L2, L3; not on the demo path after §6.2's arrival-date rule).
