# C9 · Privacy and operations

| | |
|---|---|
| Version | 1.0 |
| Status | **Frozen** (set B verdict: Andrei, 2026-10-01) |
| Freeze | 2026-10-01 |
| Change rule | Until the freeze, edits by the W1-B fold only. After it, amend via `docs/contracts/amendments.md`, orchestrator only |
| Consumers | L2 (settings assertion, visibility filter, Hermes config, SOUL line, logging), L6 (prod compose, Caddy, egress test, backups, `mona doctor --privacy`), L5 (`demo-snapshot`, `demo-reset`, re-anchoring), L1 (the purge inside `mona.fileops`), L4 (export contents), L3 (Settings › Privacy) |
| Depends on | C1 (`entities.visibility`, `purge_after_hours`, `batches.visitor`, §9 reset pointers, §10; amendment A1), C4 (§1.3 toolsets, §2.6 the filter point, §3.13 exports, §3.15 the brief, §4.3), C5 (§1.3 caches, §5.1 the model request), C6 (§4.7 the debrief cache), C7 (§1 roots, §3 guard, §4.1 lock, §4.3 recovery, invariants 1–2), C2 (proxy headers, sessions), decisions D3 (the egress trap), D4, D5; S1 key map (`docs/spikes/s1/README.md`) |

Rulings this contract implements: R30 (dev may use the cloud; the deployed product may not), R32 (Mona never sends anything outside), R38 (volunteered documents go to Visitors and are purged after 24 h), R3 (the stage fallback is laptop + OpenRouter), plan §0 success criterion 5 (zero cloud-AI calls in prod: a config assertion plus an egress test in which only the Telegram API appears), plan §9 and §12b (personal entities stay out of Telegram notifications and accountant exports; Telegram first lines carry no names or amounts).

## 1. Environments and egress

### 1.1 Two environments
`MONA_ENV` (exists in `mona.settings`) is `dev` or `prod`; there is no other value, no default and no switch at run time. A process started without it refuses to start: L2 removes today's `dev` default, and the dev compose file and the test configuration set it explicitly. So a service or one-off container on mona that forgets it can't run as `dev`, where the cloud is allowed.

| | `dev` (laptop, and the stage fallback, R3) | `prod` (mona) |
|---|---|---|
| Typed model calls (C5, C6, L4 drafts) | OpenRouter, C5 §5.1's model and D4 pin | llama-swap on mona, `MONA_LLM_BASE_URL` |
| Hermes model | `provider: openrouter` + D4 `provider_routing` | `provider: custom`, `base_url` = llama-swap |
| Cloud AI | allowed, practice documents included (R30) | **none** |
| Leaves the box | OpenRouter, Telegram (once the bot is set up) | Telegram only |

The fallback on stage is the `dev` environment on the laptop, presented as "cloud demo mode" (plan §15). Prod never falls back to the cloud.

Under the fallback the phone can't reach the app: dev binds every port to `127.0.0.1` (D1, §4.3), and the dev stack is never bound beyond loopback. The 9:30 volunteered-document beat then runs on the laptop: the photo reaches the laptop by the runbook's route (L6) and is dropped in Intake with "Visitor document" checked (C1 §4.1).

### 1.2 One LLM client, fail closed
- All typed model calls go through one module, `mona.llm`, built once from settings. Nothing else in the api package opens an HTTP connection to a model (C4 §4.3). The chat adapter talks to Hermes only (C3).
- `MONA_LLM_BASE_URL` (+ `MONA_LLM_MODEL`) selects the endpoint. In `dev` it may be unset, meaning OpenRouter with `OPENROUTER_API_KEY`. In `prod` it is required.
- In `prod`, `mona.llm` refuses to start (and so does the process importing it) unless the base URL's host is a compose service name or resolves only to loopback, RFC 1918, link-local or `fc00::/7` addresses, and isn't one of the cloud API hosts (`openrouter.ai`, `api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com`, `api.mistral.ai`, `api.deepseek.com`, `api.x.ai`, `api.groq.com`, `api.together.xyz`, or a subdomain of one). The address check is the control; the host list is a readable backstop.
- C2 §15.2's status probes use the same base URL and its root (the URL minus a trailing `/v1`); there is no other LLM URL variable, so nothing reaches a host this check didn't pass.

### 1.3 Who may connect where (prod)
| Service | Outbound connections allowed |
|---|---|
| `api` | postgres; hermes (chat adapter); llama-swap (status probes) |
| `worker-llm` | postgres; llama-swap |
| `worker-cpu` | postgres |
| `hermes` | api `/mcp`; llama-swap; `api.telegram.org` (and DNS to resolve it) |
| `postgres`, the static web build, Caddy | none (Caddy's TLS is local or through the tunnel; L6) |

## 2. The prod assertion and the egress test

### 2.1 Checks
The **cloud-key names** are `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `GROQ_API_KEY`, `TOGETHER_API_KEY`, `NOUS_API_KEY` and `HF_TOKEN`. In `prod`:

| # | Check | Why |
|---|---|---|
| A1 | no cloud-key name is set (non-empty) in the api's or a worker's environment | the dev `env_file: .env` carries `OPENROUTER_API_KEY` |
| A2 | `MONA_LLM_BASE_URL` passes §1.2 | fail closed on the endpoint |
| A3 | no cloud-key name is in the Hermes container's environment | D3: Hermes pulls `OPENROUTER_API_KEY` from its environment into a credential pool whatever the config says |
| A4 | no cloud-key name has a non-empty value in `$HERMES_HOME/.env` (the profile volume's `/opt/data/.env`) | D3, the same trap through the profile file |
| A5 | Hermes `config.yaml` equals §4.1's prod settings for every key §4.1 lists | the S1 key map plus the lockdown |

A failed check stops the process with a message naming the check and the variable or key, **never its value**.

### 2.2 Where they run
- **A1, A2**: settings validation at the start of `api`, `worker-llm`, `worker-cpu` and every `mona` CLI command when `MONA_ENV=prod`.
- **A4, A5**: the one-shot `hermes-seed` service (exists, D4) in prod. It always installs the prod `config.yaml` from `deploy/hermes/` (overwriting: S5 assumption 2), creates `cache/documents/` and `cache/images/` (C4 §4.2), then checks A4 and A5. Hermes `depends_on` it with `service_completed_successfully`, so a failed check keeps Hermes down.
- **A3**: a CI test that renders the prod compose file (`docker compose -f compose.prod.yaml config --format json`, parsed; only variable names are compared or printed, D4), and `mona doctor --privacy` on mona, which reads the running container's variable names with `docker inspect` (names only).
- `mona doctor --privacy` (L6) runs A1–A5 together and reports each line green or red. It runs through the host wrapper (§6.3), since it reads `docker inspect`.

### 2.3 The egress test (plan §0 criterion 5)
On mona, with the prod stack, L6 starts the capture **before** `mona demo-reset` and runs: the reset (so every service cold-starts inside the window), the demo flow end to end (a drop batch through filing, the debrief, the scripted chat turns: search, sum, deadlines, draft; an accountant export, a photo sent to the owner bot, and the 07:30 brief triggered by hand), then 30 minutes idle so the purge and housekeeping jobs run. Whatever a service does only at boot (a credential-pool load, a models list fetched on start) is inside the window. Throughout it captures:
- packets leaving the Docker bridge networks for any address other than the compose subnets, the llama-swap address and the DNS resolver (`tcpdump -n` on the bridge interfaces, headers only);
- the resolver's query log.

**Pass**: every captured destination belongs to `api.telegram.org` (its DNS answers during the run, or Telegram's published ranges at test time), and every DNS query is for `api.telegram.org`. The destination list (no payloads) goes into the L6 report as the evidence.

Recommended hardening (L6 decides after Oct 8): an nftables rule on mona that drops and logs forwarded traffic from the Docker bridges to anything but the compose subnets, llama-swap, the resolver and Telegram's ranges; the egress test then also asserts zero logged drops.

In CI, the complements are C4 test 9 (no socket other than Postgres from tool code), §8 test 1 (the prod settings refuse a public LLM URL) and §8 test 2.

## 3. Visibility

### 3.1 `visible(row, channel)`
The one function behind C4 §2.6's filter point, used by MCP tools, the brief and exports. Channels: `web`, `telegram`, `export`. Invisible rows behave as absent: `not_found`, left out of lists, counts and sums (C4 §2.6).

| Row | `web` | `telegram` | `export` (a pack for entity E, fiscal year Y) |
|---|---|---|---|
| document | not deleted | not deleted, **and** its entity is set, is not `personal`, and is not the Visitors entity | not deleted, `status='filed'`, entity = E, `fiscal_year` = Y |
| deadline | yes, unless its document is a Visitors one (§5.5) | its entity is not `personal` or Visitors, and its document (if any) is visible | not exported |
| entity | yes | not `personal`, not Visitors | E only; E may not be `personal` or Visitors (refused on every channel, C4 §3.13) |
| rule | yes | C4 §2.6's rule (action or any condition names a personal entity, its account, or a person linked to it → invisible) | not exported |
| journal entry / group | yes | C4 §2.6's rule (any document or rule of it invisible → invisible) | not exported |
| reminder (`get_brief.reminders_today`, `list_deadlines`) | yes, unless its deadline or document is a Visitors one (§5.5) | visible iff its deadline or document is visible | not exported |
| interview (`get_brief.pending_interview`) | yes | counts only questions with at least one visible affected document; the questions themselves are answered in the web app | — |
| conversation, chat turn | yes | no (web chat stays in the web app) | no |

- `web` sees everything: one owner, one profile (R5). One nuance: Visitors documents are listed and opened like any other (Intake, Archive › Visitors, document detail, search), but they are left out of every aggregate: `sum_amounts` totals, `get_brief` and Home's `BriefFacts`, and deadline and reminder lists (§5.5). A stranger's bill is never the practice's figure or obligation.
- The Telegram column extends C4 §2.6's interim rule with two cases: Visitors documents (third-party paperwork) and documents with no entity yet (they may turn out personal). Both still reach the web app.

### 3.2 On Telegram
- The owner bot answers only allowlisted Telegram user ids (Hermes gateway allowlist; S4 names the key). Mona's tools reach Mona through `mona_tg` with `X-Mona-Channel: telegram` (C4 §1.2–§1.3), so §3.1's Telegram column applies to every reply and to the cron brief.
- Documents sent to the bot are ingested with `ingest_attachment` (C4 §3.14); a visitor's document is `for_visitor` and never appears in a later Telegram answer.

### 3.3 In the accountant pack
- Contents are exactly the `export` column: the entity's filed, non-deleted documents of that fiscal year (C4 §3.13 selects by `documents.fiscal_year`). Documents still in review are left out and counted in the dialog (C2 §12 `ExportPreview.inReview`).
- The zip holds the document files as archived; the CSV index holds one row per file with no text beyond titles, counterparties and references, escaped against formulas (C4 §3.13). No IBAN, no quote, no extracted text is written into the CSV.
- Packs are written under `/data/exports` and downloaded by the person (C2 §12). Nothing is sent. `demo-reset` empties the folder.

### 3.4 Memory on Telegram
- The Hermes profile has one memory for all platforms. `telegram: [memory, mona_tg]` stays (C4 §1.3, plan §3), and the cron brief has no memory tool (`cron: [mona_tg]`).
- So memory holds nothing that Telegram mustn't show. L2 adds this line to SOUL.md's Principles, and the memory seeds (plan §10) comply:
  > Memory is for preferences and how the practice works: how people like to be addressed, languages, formats, who does what. Never save document contents, amounts, account numbers, health details, or anything about the personal entities' paperwork.
- `mona doctor --privacy` scans the profile's memory files with §3.5's checker plus the IBAN pattern (C5 §4.3) and reports any hit.

### 3.5 The Telegram first line
Every message Mona sends on Telegram, replies and the brief alike, starts with a line that could show on a locked phone (`voice-and-tone.md`: "Telegram, locked-screen line"). The **first line** is the text up to the first newline, or the first 100 characters. It carries **no names** (people, entities, counterparties, including aliases), **no amounts**, **no dates**, **no document titles** and **nothing medical**: "Two documents need your review." Details, still subject to §3.1, follow on the next lines.

Enforcement in v1:
- the SOUL principle (Discretion, plan §10) and the cron brief's prompt: "Start with one line that says only how many things need attention, with no names, amounts or dates; details follow on the next lines.";
- `get_brief` on `telegram` returns only visible facts (§3.1);
- the check in §8 test 4.

Hermes sends Telegram messages itself and 0.21.5 offers no outbound hook we've verified, so there is no server-side filter; a first line that breaks the rule is a prompt failure, caught by the test.

## 4. Hermes lockdown (prod)

### 4.1 Configuration
`deploy/hermes/` holds the dev `config.yaml` (exists) and the prod `config.prod.yaml`; `hermes-seed` installs the one for `MONA_ENV` as `/opt/data/config.yaml`. The prod file sets, and A5 checks:

| Key | Prod value | Source |
|---|---|---|
| `model.provider` / `model.base_url` / `model.default` | `custom` / llama-swap's `/v1` URL on a private address / the loaded model id | S1, §1.2 |
| `model.context_length` | `65536` (the per-slot context) | S1, plan §3 |
| `agent.reasoning_effort` | `medium` | S1 |
| `agent.disabled_toolsets` | §4.2 | this contract |
| `platform_toolsets` | `api_server: [memory, mona]`, `telegram: [memory, mona_tg]`, `cron: [mona_tg]` | D5, C4 §1.3 |
| `mcp_servers` | exactly `mona` and `mona_tg` at `http://api:8765/mcp`, as C4 §1.3 | C4 |
| `tools.tool_search.enabled` | `false` | S1 |
| `skills.write_approval` / `skills.project_discovery` | `true` / `false` | S1 |
| `memory.write_approval` | `false` | S1 |
| `auxiliary.<every task>.provider` | `main` | S1 |
| `auxiliary.title_generation.enabled`, `auxiliary.background_review.enabled` | `false` | S1 |
| `curator.enabled` | `false` | S1 |
| `updates.check` | `false` | S1, R40 |
| `openrouter.response_cache` | `false` | S1 |
| `telemetry.shared_metrics.enabled` | `false` | S1 |

Environment of the prod Hermes container: `API_SERVER_KEY` (≥ 32 random characters), `API_SERVER_HOST=0.0.0.0` (the compose network only, §4.3), `API_SERVER_PORT=8642`, `API_SERVER_MODEL_NAME=mona`, `MONA_SERVICE_KEY`, the Telegram bot token and allowlist (S4), `HERMES_UID`/`HERMES_GID`. No cloud key (A3); `API_SERVER_CORS_ORIGINS` unset.

### 4.2 Toolset backstop and the terminal warning
- `agent.disabled_toolsets: [terminal, code_execution, file, web, browser, computer_use, delegation, image_gen, tts, vision, session_search, cronjob, skills, todo]`. None of these is in a platform list (§4.1); the backstop keeps them off if a platform list is ever edited or a platform falls back to its defaults (F12: an unset `cron` got the whole CLI bundle). `skills` and `todo` come back after the demo by a decision (D5), not by editing this list quietly.
- Hermes logs that the API server listens on `0.0.0.0` with the `local`, unsandboxed terminal backend (S5 finding 6). The controls: the terminal toolset is in no platform list and is disabled (above), and the API server is reachable only from the compose network (§4.3). L2 reads the pinned image for a terminal-backend setting; if one exists, the prod file sets its most restrictive value. The warning itself may stay in the log.
- `mona_tg`, `mona` and `memory` are never in `disabled_toolsets`.
- The 07:30 brief job is installed by L2's install step, not by the model, so disabling `cronjob` (the model's tool for managing jobs) must not stop the scheduler from running it; §8 test 5 checks that on the prod file.

### 4.3 Network exposure
- **Caddy is the only published port** in prod (L6: 443, or the tunnel's port, R3). Routes: `/api/*` → `api:8765`; `/mcp` and `/mcp/*` → an explicit `respond 404`; everything else → the static web build (with `/pdfjs/`). There is no route to Hermes, Postgres or the workers.
- `api`, `hermes` and `postgres` publish no host port in prod. (In dev they bind `127.0.0.1` only, D1.)
- `/mcp` is kept off the proxy **and** still requires the service key (C4 §1.1), so a routing mistake fails closed.
- **llama-swap** (the `llm` stack, outside the compose file; L6) is reachable from the compose network only: joined to it, or bound to the Docker bridge's gateway address. It is never published on the host's `0.0.0.0` or the LAN: it has no auth, and the prompts it serves carry document text. (On mona today it listens on `127.0.0.1:9292`, which the containers can't reach; L6 re-binds it on Oct 8.)
- The api trusts `X-Forwarded-Proto` and `X-Forwarded-For` only from Caddy's address (C2 §2.2).

## 5. The Visitors purge (R38)

### 5.1 Selection
A document is purged when its batch has `visitor = true` and `arrived_at + purge_after_hours ≤ now()`, where `purge_after_hours` is the Visitors entity's (C1 §2.1; 24 in the seed). Selection is by `batches.visitor`, never by entity alone (C1 §2.1). A duplicate intake item in a visitor batch points to someone else's document; that document is not the batch's and is never purged.

### 5.2 When
- The periodic `purge_visitors` job on the `cpu` queue, every 15 minutes.
- `mona purge-visitors [--now]` for the runbook; `--now` ignores the age (after the event, or before a snapshot).
- Snapshots never contain visitor batches (§6.2), so `demo-reset` restores none.

### 5.3 What one purge does
Per document, holding its lock (C7 §4.1), inside `mona.fileops` (C7: the one library that touches document files; this is its only hard delete, C1 §10, C7 §7.5):
1. **Files first.** Unlink `root(location)/current_path` through the C7 §3 guard, and an adoption's trash copy if one is live (C7 §8.3); tidy empty archive folders (C7 §4.2 D). Unlink the caches for its sha256: `<sha>.pages.json`, `<sha>.ocr.pdf`, `<sha>.p1.png`, `<sha>.model.*.json` (C5 §1.3), and its drafts' `.docx` files if L4 stores any. A file that is already gone is not an error.
2. **Then one transaction**, in this order:
   1. Collect `E`: the document's `file_ops` rows (`document_id` = it), plus the rows whose `subject_id` is one of its deadlines or reminders (a `deadline.add` or `reminder.add` entry may name only its subject, C1 §5). Collect `G`: their `group_id`s.
   2. Clear `documents.filed_op_id`, then delete `E` in **one** `DELETE` statement. The `undone_by`/`undo_of` self-references are checked at the end of the statement, so links inside `E` need no clearing (nulling `undo_of` on an undo row would break C1 §5's `CHECK`).
   3. Delete `card_events` whose `subject->>'document_id'` is the document; delete `deadlines` whose `document_id` is it (their reminders cascade); delete the `documents` row (extractions, fields, classifications, review items, drafts and document reminders cascade, C1).
   4. If the batch has no document left, delete its `intake_items` and add its groups (`op_groups.batch_id`) to `G`.
   5. Delete every group of `G` that has no entry left, together with each undo or redo group whose `target_group_id` chain leads to one of them and that has no entry left, **children first**: a redo group before the undo group it targets, that one before its own target (`op_groups.target_group_id` has no `ON DELETE`, C1 §5). A group that still has entries, or is targeted by one that does, stays for a later document's run.
   6. Delete the batch if it has no document left.
3. Log one line with ids only: `purged visitor document doc_… (batch bat_…)`.

Files go before rows: a crash in between leaves a row without a file, which the next run deletes. The other order could leave an untracked file behind (C7 invariant 2). A step-2 failure rolls back the whole transaction and is logged with its class and constraint name (§7); the row it leaves without a file turns C7 invariant 1 red in `mona doctor`, so a purge that keeps failing is seen.

### 5.4 What the purge doesn't reach
- Chat transcripts (`chat_turns`: the person's words and Mona's replies), card-action notes, and Hermes' session history and tool results in which the document was discussed. v1 doesn't scrub them (orchestrator ruling at the W1-B fold); a conversation delete can come later.
- Telegram's own copy of any message: the Privacy section says Telegram messages pass through Telegram (SOUL, plan §15).
- Hermes' attachment cache, which Hermes prunes itself after 24 h (C4 §4.2).

The promise on stage is: **"the document and everything Mona derived from it are deleted after 24 hours"**. Its limit, stated here so the runbook and the Privacy section keep to it: "everything Mona derived from it" means the document's files, caches, extracted fields and quotes, classifications, suggestions, journal rows, deadlines, reminders and cards. It doesn't reach a conversation about the document: whatever was said about it in chat stays in that conversation. The sentence is exact on the phone-browser upload path, which is the 9:30 beat until Telegram lands. On the Telegram path, Hermes' own session history of that chat keeps the exchange, so the Telegram runbook line names it. demo-script v1's 9:30 beat doesn't discuss the visitor's letter in chat; if a presenter does, the sentence is no longer exact for that letter.

### 5.5 Visitors elsewhere
Excluded from the model's entity choice (C5 §5.2), rules and corrections (C5 §4.5, C4 §3.5), rule previews and applies (amendment A2), interviews (C6 §2.2), exports (C4 §3.13) and Telegram (§3.1).

On every channel, the web included, they are also left out of the practice's figures: deadlines and reminders, `sum_amounts` totals, `get_brief` facts and Home's brief (§3.1). No extracted deadline is written for a visitor-batch document (amendment A10); a deadline or reminder someone adds by hand on one is kept but hidden from those lists. The web app shows the documents themselves (Intake, Archive under Visitors, document detail) until the purge.

## 6. The demo snapshot and `mona demo-reset`

### 6.1 What a snapshot holds and what reset restores
A snapshot is a directory `/data/snapshots/<name>/`, restored as one unit (C1 §9):

| Part | In the snapshot | Restore |
|---|---|---|
| Postgres, the whole database | `db.dump`: `pg_dump -Fc --exclude-table-data=auth_sessions --exclude-table-data='procrastinate_*'`. Every schema object travels, including the `unaccent` and `pg_trgm` extensions, the `mona` text-search configuration and Procrastinate's tables (which `mona migrate` puts in `public`); session and queue rows don't | `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`, then `pg_restore --exit-on-error --no-owner`, then `mona migrate` (a no-op at the same head, §6.3 step 1). The queue comes back empty |
| `/data/inbox`, `/data/archive`, `/data/trash` | `data/inbox/`, `data/archive/`, `data/trash/` | `rsync -a --delete` each |
| `/data/textcache` (text, OCR, thumbnails, model outputs, the debrief cache `debrief/`, C5 §1.3, C6 §4.7) | `data/textcache/` | `rsync -a --delete` |
| `/data/config` (`rules.yaml` and its history) | `data/config/` | `rsync -a --delete` |
| `/data/exports` | not included | emptied |
| Hermes profile (`/opt/data`): `SOUL.md`, `memories/`, `skills/`, `state.db` with no rows in `sessions`, `messages` or `system_prompts`, empty `cache/documents/` and `cache/images/` | `hermes/` | `rsync -a --delete` into the volume, owned by `HERMES_UID:HERMES_GID`, except `config.yaml`, `.env` and `cron/`, which §6.3 step 5 installs (§6.5) |
| `manifest.json`, `sha256sums` | always | read first |

The `settings` row, `iban_salt` included (amendment A1), travels with `accounts` in the dump, so every stored IBAN hash stays valid after a reset; `MONA_IBAN_PEPPER` only matters when the seed loader first creates the row.

Never in a snapshot: `.env` files and other secrets, `auth_sessions` rows, queue rows, `/data/snapshots` itself, logs, llama-swap state, and from the Hermes profile `config.yaml`, `.env`, `cron/` (the jobs, `output/` with past brief texts, `deliveries.db`), `response_store.db`, `sessions/`, `logs/` and every cache but the two empty attachment folders. Restoring the archive without the inbox would lose the files of documents in review (C7 invariant 1), which is why all three roots travel together.

`data/textcache/` may hold entries for sha256s with no document row: the cache is content-addressed, and `demo` carries the live batch's caches before the batch exists (§6.3).

### 6.2 What a snapshot must be
`mona demo-snapshot` refuses to write one, and `demo-reset` re-checks after restoring, unless all hold:
1. taken after `recover_pending()` (C7 §4.3): no `pending` journal entry;
2. no `conversations`, `chat_turns`, `card_events` or `card_action_notes` rows (C1 §9); `auth_sessions` rows may exist (the build unlocks the app) and are never dumped (§6.1);
3. no `running` batch, no visitor batch, no `generating` interview; the workers are stopped (§6.3), and no Procrastinate job is `doing`, nor `todo` except the periodic ones (queue rows aren't dumped anyway);
4. only the pre-seeded rule tier (demo-script v1): every rule has `source = 'seed'`, and there are no `interview_answers` rows. A rule learned live gets its key from its name (C6 §6.1), so comparing keys with `demo/seed/rules.learned.yaml` would miss it;
5. C7 invariants 1 and 2 hold for inbox, archive and trash;
6. the Hermes part holds no conversation: `state.db` has no rows in `sessions`, `messages` or `system_prompts`, there is no `cron/output/`, and `cache/documents/` and `cache/images/` are empty;
7. `manifest.json` (written last, atomically): `{v: 1, name, created_at, reference_instant, alembic_revision, prompt_versions: {c5, c6}, mona_version, counts: {documents, rules, batches, journal_entries}}`; `sha256sums` covers every other file.
8. a stage snapshot (`demo`, `demo-prefiled`) holds the §6.7 stage settings.

### 6.3 Commands
**Where they run.** `mona` in the api image is the in-container CLI (`seed load`, `migrate`, `purge-visitors`, `profile set-password`, …). `demo-snapshot`, `demo-reset` and `doctor` also stop and start services, write into the Hermes volume and read `docker inspect`, which no service container can do without the Docker socket. So each host has a **host wrapper** named `mona` (`deploy/bin/mona`, L5c and L6):
- it runs `docker compose stop|start` itself;
- it runs every DB and file step as `mona ops <step>` in a one-shot container of the api image (`docker compose run --rm --no-deps`), on the compose network (prod publishes no Postgres port, §4.3), with `/data` (and so `/data/snapshots`) and the Hermes volume mounted;
- it forwards any other subcommand to such a one-shot container unchanged.

No service mounts the Docker socket. A1 and A2 run inside the one-shot container like any `mona` command (§2.2).

- `mona demo-snapshot --name <name> [--reference <ISO datetime>]`: stops `worker-llm`, `worker-cpu` and `hermes` (waiting for `doing` jobs to end), checks §6.2, copies, and starts them again. `reference` (default now) is the instant the snapshot stands for (§6.4). The stage keeps two: `demo` (the pre-batch state) and `demo-prefiled` (the same with the live batch filed, demo-script v1's fallback).
- `mona demo-snapshot --refresh-textcache --name <name>`: replaces an existing snapshot's `data/textcache/` with the current `/data/textcache` (the debrief cache included), rewrites `sha256sums` and the manifest's `created_at`, and leaves the DB, the file trees and the Hermes part alone.
- **Stage build order.** `demo` is pre-batch, but the live batch's text, OCR, model-output and debrief caches exist only once the batch has run:
  1. build the pre-batch state (seed, overnight history, §6.7 settings; L5b) and run `mona demo-snapshot --name demo`;
  2. `mona demo-reset --name demo`, drop the live batch and let its debrief reach `ready` from a live run (a D9 quality run), without opening chat or answering;
  3. `mona demo-snapshot --name demo-prefiled`;
  4. `mona demo-snapshot --refresh-textcache --name demo`;
  5. `mona demo-reset --name demo` and check that the cached debrief matches (§8 test 8).
- `mona demo-reset [--name demo] [--prefiled] [--anchor today|YYYY-MM-DD] [--yes]`: `--prefiled` means `--name demo-prefiled`; without `--yes` it asks before destroying the current state. Steps:
  1. Verify `sha256sums` and that `alembic_revision` is the current head (otherwise refuse: "the snapshot is from another schema version; rebuild it").
  2. Stop `worker-llm`, `worker-cpu`, `hermes`, `api`. Postgres keeps running.
  3. Restore §6.1, then run `mona migrate`.
  4. Re-anchor (§6.4) in one transaction.
  5. Install Hermes' `config.yaml` and `.env` for this environment (§6.5); empty `cron/` and re-run L2's brief-job install (the 07:30 job, C8 §3.3), so a reset never loses it; in prod, run A4–A5.
  6. Start `api`, the workers and Hermes; wait for health (2 minutes at most).
  7. Post-checks: C7 invariants 1–2; `recover_pending()` finds nothing; the brief job is installed; the `findQuery` fixture check on the rehearsed documents (L5c, plan §6.3); `mona doctor`. Any failure ends the command non-zero, naming the check.
  8. Print counts, the anchor and the shift. No document names.
- **Idempotent:** two resets with the same snapshot and anchor, both run after 07:05 on the same day, leave the same database (compared by dump), the same file trees (compared by hash) and the same Hermes profile, excluding the files Hermes writes at start and the brief job's run stamps in `cron/jobs.json` (logs, pid files, SQLite `-wal`/`-shm`; L5c lists them). Plan §14.

### 6.4 Re-anchoring
- `T0` is the manifest's `reference_instant`. `T1` is the anchor day at 07:00 Europe/Paris, but no later than the reset's own time minus 5 minutes (so nothing lands in the future). An anchor after today is refused. `Δ = T1 − T0`, whole seconds.
- **Shifted by Δ:** every non-null `timestamp with time zone` column in schema `public` (enumerated from `information_schema.columns`, so later columns are covered): `created_at`, `updated_at`, `arrived_at`, `filed_at`, `deleted_at`, `started_at`, `finished_at`, `ready_at`, `resolved_at`, `file_ops.at`, `last_fired_at`, `delivered_at`, `password_changed_at`, …; plus the timestamps inside JSON: `file_ops.before.filed_at` and `file_ops.after.filed_at` (C7 §2.2 PathState).
- **Never shifted:** `date` columns (`doc_date`, `due_date`, `period_start`, `period_end`, `remind_on`), `fiscal_year`, extracted values, printed text, paths and file names (C1 §9). `profile.locked_at` is set to null.
- So facts tied to printed dates ("URSSAF due in 3 days") are exact only on the day the snapshot was built for. L5 builds the stage snapshot for the stage day (the synthetic documents generated with that `--anchor`, L5a); rehearsals on other days use `--anchor` and see different "days left".
- L5b builds the stage snapshots with `reference` at 07:00 Europe/Paris and the overnight history between 00:00 and 07:00 of that same day. After re-anchoring (`T1` = 07:00 of the anchor day) the history falls inside Home's since-midnight window (C2 §3.2); a reset before 07:05 shifts it earlier by the difference.

### 6.5 Hermes profile across environments
The snapshot's Hermes part never contains `config.yaml` or `.env`. `demo-reset` installs `deploy/hermes/config.yaml` (dev) or `config.prod.yaml` (prod) and writes `.env` from the environment (prod: no cloud key). One snapshot therefore serves mona and the laptop fallback, and a prod reset always ends with A4–A5 green.

### 6.6 Backup and restore of the demo state
- **Backup** = the snapshot directories. On the Oct 16 freeze (plan §6.4) and after every change to a stage snapshot, L6 copies `/data/snapshots/<name>/` from mona to the laptop's `~/DevFiles/mona-hq/demo-data/snapshots/<name>/` over SSH and verifies `sha256sums` on arrival.
- **Restore** = copy back if needed, then `mona demo-reset --name <name>`.
- **Verified** by restoring the laptop copy on the dev stack, running §6.3 step 7, and walking the evidence beat once.
- Snapshots contain practice documents and model outputs: they live only in `/data/snapshots` on mona and in `demo-data/` on the laptop, never in the repo, the vault or a cloud drive. No encryption at rest in v1 (roadmap: encrypted backups with a practice-held key).

### 6.7 Stage settings
The stage snapshots hold these values; §6.2 item 8 checks them. L5b sets them through the seed (`practice.owner_name`; `practice.debrief_early_min` and `practice.auto_lock_minutes`, loader fields L2 adds) or with `PATCH /api/settings` before `demo-snapshot`.

| Setting | Stage value | Why |
|---|---|---|
| `settings.debrief_early_min` | the live batch's planned review count from L5b's histogram: 7 (8 if the La Médicale notice queues) | the early start fires on the last candidate, so the debrief covers all of them and the banner reads "Mona has 3 questions" at 3:15 (C6 §3.2) |
| `settings.debrief_queue_threshold` | 5 (the default) | unchanged: the running batch never counts toward it (C6 §3.3) |
| `profile.auto_lock_minutes` | 120 | the phone is unlocked at pre-flight (T−10) and first used at 9:30, and reads don't count as activity (C2 §2.3); 120 also covers a late start on the laptop. Lock still works by hand |
| `profile.name` | the owner's form of address | the 0:00 greeting (C8 §5.6) |

`MONA_INTERVIEW_PASS1_BUDGET_S` and `MONA_DEBRIEF_CACHE` (C6 §4.3, §4.7) are environment settings in each host's `.env`, set from the Oct 8 mona timings (demo-script v2); they aren't in the snapshot.

## 7. Secrets and logs

- **Secrets:** `MONA_SERVICE_KEY`, `HERMES_API_KEY` (Hermes' `API_SERVER_KEY`), `POSTGRES_PASSWORD`, `MONA_OWNER_PASSWORD` (seed only), `MONA_IBAN_PEPPER` (seed only, A1; afterwards the salt lives in `settings` and is never exported, C1 §8), `OPENROUTER_API_KEY` (dev only), the Telegram bot token. They live in each host's `.env` (gitignored) and nowhere else: not the repo, logs, reports, the vault or snapshots. `docker compose config` is printed only through a filter (D4).
- **Logs never contain:** secrets, session cookies, CSRF tokens, passwords, the bodies of `/api/auth/*` and account creation (C2 §8), IBANs (C1 §2.4), document text, quotes, OCR or model output, original file names, search queries (`q`), chat messages or note texts. They carry ids, route templates, status codes and durations. Two frozen set A lines are the only exception for file names: C4 §4.2 step 7 logs an attachment's relative path, and C7 §3 logs the rejected relative path on `forbidden_path`. Both stay in the box's logs.
- **Default sinks** that would break this, and what each does instead:
  - uvicorn's access log writes each path with its query string: the api runs with `--no-access-log`, and the app's own request logger writes the route template, status and duration.
  - A database error's message and its `DETAIL` quote the failing row: the app logs DB errors, job failures and C2's 500s as the exception class plus `diag.constraint_name`, never `str(exc)`; Procrastinate's job-failure log line is filtered the same way; Postgres runs with `log_error_verbosity = terse` in both compose files.
  - An exception whose message could hold document text (model-output validation) is logged by class name.
  - Caddy (L6): access logs off, or only method, path without the query string, status and duration; never request headers (they carry `X-CSRF-Token`).
- **Where document content may go** (C1 §2.4 leaves this to C9), including any IBAN printed in it:

| Destination | Document content allowed? |
|---|---|
| the environment's LLM endpoint (§1) | yes (prod: on the box; dev: OpenRouter, R30) |
| the web app | yes |
| an accountant pack of the document's own practice entity | the file itself, yes; the CSV only titles, counterparties, references (§3.3) |
| a Telegram reply | only for documents visible on `telegram` (§3.1), never in the first line (§3.5) |
| MCP results | no text beyond C4 §2.2's facts; never an IBAN |
| card-action notes | titles, labels and question text only, as C3 §6.2 builds them; never quotes, extracted values or page text |
| logs, memory, `pageContext` | no |

## 8. Test obligations

**[M]** = mutation-checked (break the code, watch the test fail, restore).

1. **Prod assertion [M].** Without `MONA_ENV` → the api, a worker and a `mona` command refuse to start. With `MONA_ENV=prod`: `OPENROUTER_API_KEY` set → the api exits naming the variable, and the output doesn't contain the fixture value; `MONA_LLM_BASE_URL=https://openrouter.ai/api/v1` → exits; a public IP literal → exits; `http://llama-swap:8080/v1` → starts. `hermes-seed` with a fixture `.env` holding a cloud key → non-zero, names the key, not the value; a `config.yaml` with `model.provider: openrouter` or a missing `disabled_toolsets` entry → non-zero. Mutation: skip the `.env` check → the test fails.
2. **Prod compose (L6).** In the rendered prod compose file: every Python service (`api`, both workers, `hermes-seed`, any one-shot) sets `MONA_ENV=prod`; no cloud-key name in any service's environment; `api`, `hermes`, `postgres` publish no ports; no service mounts `/var/run/docker.sock`; the Caddyfile answers `/mcp` and `/mcp/x` with 404 and refuses a 300 MB body on `/api/intake` (Caddy run in a test container). On mona, llama-swap's listening addresses are only the Docker bridge's or the compose network's (§4.3).
3. **Visibility [M].** On `telegram`: a personal document, a Visitors document and a document with no entity are `not_found` in `get_document` and missing from search totals, sums and `get_brief`; a deadline of a personal entity is missing from `list_deadlines`; a reminder on a personal document is missing from `get_brief.reminders_today`; `pending_interview` counts only questions with a visible document. On `export`: only filed documents of the entity and year; a review document is left out and counted in `ExportPreview.inReview`. On `web`: all present, but a filed Visitors bill with an amount and a hand-added deadline is missing from `sum_amounts`, `BriefFacts`, `GET /api/deadlines` and `list_deadlines`. C4 test 7 still passes. Mutation: treat the Visitors entity as practice on `telegram` → a test fails.
4. **First line.** The checker (registry names and aliases through `norm()`, a money pattern, a date pattern, the C5 §4.3 IBAN pattern) flags crafted lines with each; C4 test 13's cron output passes it.
5. **Toolset lockdown (L2, pinned image).** With the prod file, `_get_platform_tools(cfg, platform)` for every platform Hermes 0.21.5 defines contains none of §4.2's disabled toolsets; `api_server`, `telegram` and `cron` resolve exactly as C4 §5 item 2; and a cron job installed the L2 way still runs and calls `get_brief` with the prod file (C4 §5 item 13).
6. **Purge [M].** A visitor batch holding a filed document (with a hand-added deadline and its `deadline.add` entry naming only the subject, a reminder, a card event, an adopted trash copy), a review document and a duplicate item pointing to a practice document. The batch was group-undone, then redone, then one entry undone again, so undo and redo groups target its intake group. At +23 h nothing changes; at +24 h both visitor documents, their files, caches, journal rows (the subject-only entry included), deadline, reminder, card event, intake items, every op group of the chain and the batch are gone; the practice document is untouched; C7 invariants 1–2 hold. A crash injected after step 1 → the next run completes. Mutations: delete the rows before the files → the crash test leaves a stray file and fails; delete the intake group before its undo group → the FK stops the run and the test fails.
7. **Memory hygiene (L2, dev stack).** After the demo script's chat turns, the profile's memory files hold no amount, IBAN, or title of a personal-entity document.
8. **Snapshot and reset [M] (L5c).** Build a snapshot; reset twice with the same anchor → identical dump, tree hashes and Hermes files (runtime files excluded); after the reset the extensions, the `mona` text-search configuration and an empty Procrastinate queue are there, and a search and a deferred job work; a review document resolved during a rehearsal is back in the inbox with its file after reset; every timestamp moved by exactly Δ and every date column unchanged, including PathState `filed_at`; no conversation or session rows after reset; the 07:30 brief job is installed after every reset; the §6.3 build order leaves a debrief cache file in `demo` that survives a reset and matches the live batch. Refused at build: a snapshot with a visitor batch, a pending entry, a rule loaded from `rules.learned.yaml`, and one taken after answering one debrief question through REST (a rule with `source = 'interview'`). Mutation: leave the inbox out of the restore → the review-document test fails.
9. **Egress (L6, prod on mona, Oct 8–10).** §2.3, with the capture started before `mona demo-reset` and kept through 30 minutes idle; the destination list is recorded.
10. **Logs [M].** Against the compose stack with a real uvicorn (not the ASGI test transport): a fixture batch, a search with a fixture query, a request carrying a CSRF token, and one forced constraint violation on a row holding a fixture quote. The api, worker and Postgres container logs contain no fixture IBAN, owner password, session cookie value, CSRF token, fixture document text, quote or search query. Mutation: turn uvicorn's access log back on → the query is found and the test fails.

## 9. Open questions

Settled at the fold (W1-B report numbers in brackets): documents with no entity are invisible on Telegram, and the Telegram review count leaves them out [4]; chat transcripts aren't scrubbed by the purge, and the stage line keeps its wording with §5.4's limit [11]; the Telegram first line is enforced by prompt and test [13]; memory stays shared across web and Telegram under the SOUL policy [14].

Open, ranked by how much they block L5/L6:
Nothing is open. Settled at the set B verdict (Andrei, 2026-10-01):
1. **The stage sentence** (§5.4): "the document and everything Mona derived from it are deleted after 24 hours", with §5.4's limit. The stage instance is a throwaway database, and volunteered documents are unlikely to carry PII.
2. **The phone under the stage fallback** (§1.1): out of scope for the lanes. Andrei handles it on site if needed (a laptop stack on OpenRouter that the presenter's phone connects to). The dev stack stays on loopback by default, and L6's runbook has no fallback-network procedure.

Follow-ups, decided and waiting on a lane or a measurement:
1. **The nftables egress rule** [15]: recommended, not required; L6 decides after Oct 8. The capture (§2.3) is the binding test.
2. **The terminal backend key** [16] isn't in the S1 key map (§4.2): L2 looks it up in the pinned image. The disabled toolset is the control either way.

## Changes in 0.2

- Purge step 2: one `DELETE` for the document's journal rows and those naming its deadlines and reminders, then empty groups children first along `target_group_id` (§5.3, test 6) (G6, G23, G30, G52).
- The Hermes part keeps `cron/` out and each reset reinstalls the brief job; the no-conversation check names `sessions`, `messages`, `system_prompts` and `cron/output` (§6.1, §6.2, §6.3, test 8) (G8).
- `demo-snapshot --refresh-textcache` and the stage build order bring the live batch's caches and the debrief cache into the pre-batch `demo` (§6.1, §6.3, test 8) (G10, G28).
- The snapshot's rule check is `source = 'seed'` plus no `interview_answers` (§6.2 item 4) (G11, G32).
- Whole-database dump without session and queue rows; restore by recreating `public`, then `mona migrate`; the snapshot stops the workers (§6.1, §6.2 item 3, §6.3) (G12, G47).
- The ops commands run through a host wrapper plus a one-shot api container; no service mounts the Docker socket (§6.3, §2.2) (G35, G48).
- Stage settings: `debrief_early_min` 7, auto-lock 120 min, the owner's form of address (§6.7) (G26, G29, G50; orchestrator ruling on the early debrief).
- The phone under the stage fallback (§1.1, open question 2) (G26).
- Visitors documents are left out of deadlines, sums and the brief on every channel; C1 §6.2 amendment proposed (§3.1, §5.5, test 3) (G53); reminders get a visibility row (§3.1, test 3) (G54).
- Logs: uvicorn's access log off, DB errors by class and constraint, Postgres terse, Caddy without queries or headers; test 10 runs on a real uvicorn; the two set A file-path log lines allowed; notes carry titles only (§7, test 10) (G21, G55).
- `MONA_ENV` has no default (§1.1, tests 1–2) (G56); the egress capture starts before the reset and runs 30 min idle (§2.3, test 9) (G57); llama-swap is never published on the host (§4.3, test 2) (G62); the status probes derive their root from `MONA_LLM_BASE_URL` (§1.2) (G24).
- The stage sentence's limit is stated (§5.4) (G63, OQ 11 ruling); A2 cited (§5.5); the overnight window is 00:00–07:00 of the reference day (§6.4) (G27).
- Open questions settled per the orchestrator [4, 11, 13, 14, 15, 16].
- Post-verify fixes (orchestrator): the snapshot check tolerates `auth_sessions` rows (never dumped); the deadline row hides Visitors documents on the web; the stage sentence is exact on the phone-upload path, and the Telegram path names Hermes' history; the visitor deadline rule is amendment A10.
