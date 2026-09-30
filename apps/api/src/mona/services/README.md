# mona.services

The functions L2's MCP tools and REST endpoints call. No web or MCP code here. All functions are synchronous (SQLAlchemy Core on a sync `Engine`, plus filesystem work); from async handlers call them through `anyio.to_thread.run_sync`.

`actor`/`via` follow D5: web UI clicks are `user`/`ui`; MCP tools are `mona`/`chat` or `mona`/`telegram`; the pipeline is `mona`/`pipeline`. Visibility ([V], C4 §2.6) is the caller's filter; these functions see everything.

Errors are `ServiceError(code, message, field=, valid=, hint=)` with C4 §2.4 codes (`invalid_argument`, `not_found`, `not_allowed`, `conflict`, `forbidden_path`); `hint` carries `stale`, `collision_exhausted`, `rule_invalid` or an errno name.

## Setup

| Function | Contract |
|---|---|
| `make_context(engine, data_dir, *, clock=utcnow, fs=None, on_batch_done=None) -> Ctx` | C7 §1: resolves the roots with `realpath`, refuses to start if inbox/archive/trash differ in `st_dev` (`RootsError`), wires the step-C hooks. `on_batch_done(batch_id)` is the C6 batch-end hook, called once after the commit that marks a batch `done` |
| `ctx.ops.recover_pending(older_than=timedelta(0)) -> {entry_id: outcome}` | C7 §4.3. Call at API and `cpu` worker startup, before `demo-reset` snapshots, and every 60 s with `older_than=timedelta(seconds=30)` |

## Functions

| Function | Returns | Contract |
|---|---|---|
| `file_document(ctx, document_id)` | `DocumentSummary` | C5 §1.2, C7 §4. Files a classified `processing` document to its classification's `proposed_path/proposed_file_name` in the batch's `intake_batch` group; sets `pipeline_stage='done'`, writes the extracted deadline (C1 §6.2), runs the batch-done check (C1 §4.1). Failures (errno, `forbidden_path`, `collision_exhausted`) → `review`, reason `conflict`, `pipeline_stage='failed'`, the code in `pipeline_error`. Idempotent on a document no longer `processing` |
| `correct_document(ctx, document_id, *, actor, via, entity=, sub_unit=, category=, subcategory=, counterparty=, doc_date=, period_end=, due_date=, amount=, currency=, scope='one', lang='en')` | `Correction(document_id, outcome, document, journal_ids, group_id, rule, preview)` | C4 §3.5: `user` classification, `doc.update` for field values, `file`/`move`/`rename` in a `correction` group, review item closed `corrected`, `corrections_since` of the previous rule, alias learning and merge (C5 §6.2.5). `scope='all'` drafts a `counterparty equals` rule at C5 §4.6.1 priority (or returns the existing draft) and its `RulePreview`. Same correction again → `outcome='unchanged'`, no entries |
| `preview_rule(ctx, rule_id, *, lang='en')` | `RulePreview` | C4 §3.8, C5 §4.6.9, A2; C1 §11.5 "Applied" once a live `rule_apply` group exists. `moves` is not capped here (C4 §2.3 caps are the tool's) |
| `apply_rule(ctx, rule_id, *, actor, via, lang='en')` | `Applied(rule_id, group_id, moved, unchanged, failed, preview)` | C4 §3.9: `state='active'` (its `rule.change` carries the group id, A4), every move in one `rule_apply` group, `rule` classifications, review items closed `rule_applied`, one firing per moved document. Second call: `moved=0`, `group_id=None` |
| `undo(ctx, *, actor, via, journal_id=None, group_id=None)` | `Undone(group_id, undone=[{journal_id, entry_id, document_id, title, to, location}], skipped=[{journal_id, state}])` | C4 §3.16, C7 §5.3/§5.4. Exactly one id. Undo acts on the chain's tip; undo of an undo is a redo. `state` in `undone`, `superseded`, `not_undoable`, `not_allowed`, `already_undone` |
| `delete_document(ctx, document_id, *, actor, via)` | `JournalEntry` | C7 §7: `trash/<id>/<basename>`, review item closed `deleted`. `not_allowed` for `actor='mona'` |
| `restore_document(ctx, document_id, *, actor, via)` | `JournalEntry` | C7 §8.4: the undo of the document's `delete` entry |
| `add_extracted_deadline(conn, doc, *, actor, via, at)` | `ddl_…` or `None` | C1 §6.2 (already called inside every `file` step C) |
| `resolve_counterparty(conn, value)`, `learn_alias(conn, extracted, counterparty_id, *, actor, via, at, group_id)` | id / outcome | C5 §6.2.1, §6.2.5 |

DTO builders for other read paths: `mona.services.dto.document_summary`, `journal_entry`, `journal_group`, `rule`, `path_state`. Rule rows: `mona.rules.store` (`save_rule`, `set_state`, `journal_rule`, `record_firing`, `record_correction`, `write_export` for `/data/config/rules.yaml` after every committed rule write). CLI: `mona rules import <file>`, `mona rules export`.
