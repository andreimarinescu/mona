# mona.services

The functions L2's MCP tools and REST endpoints call. No web or MCP code here. All functions are synchronous (SQLAlchemy Core on a sync `Engine`, plus filesystem work); from async handlers call them through `anyio.to_thread.run_sync`.

`actor`/`via` follow D5: web UI clicks are `user`/`ui`; MCP tools are `mona`/`chat` or `mona`/`telegram`; the pipeline is `mona`/`pipeline`. Visibility ([V], C4 §2.6) is the caller's filter; these functions see everything.

Errors are `ServiceError(code, message, field=, valid=, hint=)` with C4 §2.4 codes (`invalid_argument`, `not_found`, `not_allowed`, `conflict`, `forbidden_path`); `hint` carries `stale`, `collision_exhausted`, `rule_invalid` or an errno name.

## Setup

| Function | Contract |
|---|---|
| `make_context(engine, data_dir, *, clock=utcnow, fs=None, on_batch_done=None, on_document_settled=None) -> Ctx` | C7 §1: resolves the roots with `realpath`, refuses to start if inbox/archive/trash differ in `st_dev` (`RootsError`), wires the step-C hooks. `on_document_settled(batch_id)` runs after every commit that moves a document of a running batch out of a running stage, `on_batch_done(batch_id)` once after the commit that marks a batch `done` (C6 §3.1); a hook that raises is logged, never raised. The api and the workers pass `**mona.pipeline.hooks.interview_hooks()`, which call `mona.interviews.hooks` |
| `ctx.ops.recover_pending(older_than=timedelta(0)) -> {entry_id: outcome}` | C7 §4.3. Call at API and `cpu` worker startup, before `demo-reset` snapshots, and every 60 s with `older_than=timedelta(seconds=30)` |

## Functions

| Function | Returns | Contract |
|---|---|---|
| `file_document(ctx, document_id)` | `DocumentSummary` | C5 §1.2, C7 §4. Files a classified `processing` document to its classification's `proposed_path/proposed_file_name` in the batch's `intake_batch` group; sets `pipeline_stage='done'`, writes the extracted deadline (C1 §6.2), runs the batch-done check (C1 §4.1). Failures (errno, `forbidden_path`, `collision_exhausted`) → `review`, reason `conflict`, `pipeline_stage='failed'`, the code in `pipeline_error`. Idempotent on a document no longer `processing` |
| `correct_document(ctx, document_id, *, actor, via, entity=, sub_unit=, category=, subcategory=, counterparty=, doc_date=, period_end=, due_date=, amount=, currency=, scope='one', lang='en')` | `Correction(document_id, outcome, document, journal_ids, group_id, rule, preview)` | C4 §3.5: `user` classification, `doc.update` for field values, `file`/`move`/`rename` in a `correction` group, review item closed `corrected`, `corrections_since` of the previous rule, alias learning and merge (C5 §6.2.5). `scope='all'` drafts a `counterparty equals` rule at C5 §4.6.1 priority (or returns the existing draft) and its `RulePreview`. Same correction again → `outcome='unchanged'`, no entries |
| `preview_rule(ctx, rule_id, *, lang='en', visible=None)` | `RulePreview` | C4 §3.8, C5 §4.6.9, A2; C1 §11.5 "Applied" once a live `rule_apply` group exists. `moves` is not capped here (C4 §2.3 caps are the tool's). `visible(document_row)` drops documents the channel can't see from moves, stays and counts (C4 §2.6) |
| `apply_rule(ctx, rule_id, *, actor, via, lang='en', visible=None)` | `Applied(rule_id, group_id, moved, unchanged, failed, preview)` | C4 §3.9: `state='active'` (its `rule.change` carries the group id, A4), every move in one `rule_apply` group, `rule` classifications, review items closed `rule_applied`, one firing per moved document. Second call: `moved=0`, `group_id=None`. A document `visible` rejects is neither moved nor counted |
| `undo(ctx, *, actor, via, journal_id=None, group_id=None)` | `Undone(group_id, undone=[{journal_id, entry_id, document_id, title, to, location}], skipped=[{journal_id, state}], rule_states=[{rule_id, state}])` | C4 §3.16, C7 §5.3/§5.4. Exactly one id. Undo acts on the chain's tip; undo of an undo is a redo. `state` in `undone`, `superseded`, `not_undoable`, `not_allowed`, `already_undone`. A group undo in a `rule_apply` group's chain moves the rule with it (C6 §7.3): back to the activating entry's `before` state while the Apply is undone, `active` after a redo, unless the rule changed outside the chain since; the `rule.change` joins the new group and `rule_states` reports it (C2 `UndoResult.ruleStates`) |
| `delete_document(ctx, document_id, *, actor, via)` | `JournalEntry` | C7 §7: `trash/<id>/<basename>`, review item closed `deleted`. `not_allowed` for `actor='mona'` |
| `restore_document(ctx, document_id, *, actor, via)` | `JournalEntry` | C7 §8.4: the undo of the document's `delete` entry |
| `add_extracted_deadline(conn, doc, *, actor, via, at)` | `ddl_…` or `None` | C1 §6.2 (already called inside every `file` step C) |
| `resolve_counterparty(conn, value)`, `learn_alias(conn, extracted, counterparty_id, *, actor, via, at, group_id)` | id / outcome | C5 §6.2.1, §6.2.5 |

DTO builders for other read paths: `mona.services.dto.document_summary`, `journal_entry`, `journal_group`, `rule`, `path_state`. Rule rows: `mona.rules.store` (`save_rule`, `set_state`, `journal_rule`, `record_firing`, `record_correction`, `write_export` for `/data/config/rules.yaml` after every committed rule write). CLI: `mona rules import <file>`, `mona rules export`.

## Pipeline (`mona.pipeline`, C5 §1)

| Function | Returns | Contract |
|---|---|---|
| `ingest_files(ctx, [Upload(bytes_or_path, original_name)], *, source='drop', visitor=False, title=None, batch_id=None)` | `Intake(batch_id, items=[IntakeItem(id, original_name, sha256, size_bytes, outcome, document_id, reject_reason, deleted)], batch_done)` | C1 §4.1, C7 §8.4. One batch per call (created with its `intake_batch` group), files written to `inbox/<id>.<ext>`, `extract_text` queued in upload order in the same transaction, after every row exists. `duplicate` points to the existing document (`deleted=True` when it is in the trash); `rejected` carries `empty`, `too_large`, `unsupported_type` or `unreadable_file`. A batch with no accepted document is `done` at once and the batch-end hook runs |
| `ingest_file(ctx, content, original_name, *, source, visitor, batch_id=None)` | `Intake` | One file; its own batch unless `batch_id` names a running one. The upload endpoint uses `ingest_files` for a multi-file drop so the batch can't finish between two files |
| `mona.pipeline.runtime.get_context()`, `runtime.startup()` | `Ctx` / recovered entries | The process context from settings, and C7 §4.3 recovery; the api lifespan does the same and keeps the context on `app.state.pipeline` |
| `mona.pipeline.model.LlmClient` | `complete(system, user, schema) -> ModelResult`; `stream(system, user, *, temperature, max_tokens, timeout_s)` (thinking on, reasoning/content deltas); `complete_json(system, user, schema, *, name, temperature, max_tokens, timeout_s) -> dict` | C5 §5.1, D9, D11: the one model client. OpenRouter (`reasoning.enabled=false`; D4 pins only for Qwen 3.6) or llama-server (`chat_template_kwargs.enable_thinking=false`) by `MONA_LLM_BACKEND`; `:free` models refused |
| `mona.pipeline.hooks.interview_hooks()` | `make_context` kwargs | C6 §3.1: `on_batch_done` / `on_document_settled` → `mona.interviews.hooks`; `mona.services.pipeline.settle_hooks(ctx)` calls them after the enclosed commits |

Jobs (`mona.jobs`): `extract_text`, `render_thumbnail`, `classify_document` (queue `llm`), `file_document`, and `recover_pending` every minute. Workers start with `mona worker --queues cpu|llm`. `mona pipeline run <files…> [--inline] [--visitor] [--report out.json]` ingests one batch and prints each document's outcome and stage timings; `mona pipeline evidence --out cases.json` lists every verified quote's `findQuery` for the pdf.js check (`apps/web/e2e/findquery.spec.ts`).

## Visitors purge (`mona.fileops.purge`, C9 §5)

`purge_visitors(ops, *, ignore_age=False, dry_run=False) -> Purged(due, purged, batches, failed)` deletes every document of a visitor batch whose `arrived_at + purge_after_hours` (the Visitors entity's) has passed: per document under its lock, files first (its file, a live adoption's trash copy, every `<sha>.*` cache), then one transaction (journal rows including deadline/reminder entries named only by subject, card events, deadlines, the document; the batch's intake items, empty op groups children first and the batch with its last document). A failed transaction is logged with its class and constraint and listed in `failed`. Runs as the `purge_visitors` periodic job (`cpu`, every 15 minutes) and as `mona purge-visitors [--now] [--dry-run]`.
