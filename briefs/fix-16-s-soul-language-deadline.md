# FIX-16 S: SOUL states what Mona can't do; filenames don't vote on the reply language; Done on a deadline card is journaled and noted (A59, A60)

Card **FIX-16-S**. Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-16-s`, branch `fix-16-s`, on top of `bugfixes`.
- **Compose project:** `-p mona-fix16s`. Export `WEB_PORT=7993 API_PORT=11283 POSTGRES_PORT=57953 HERMES_PORT=11163 E2E_PORT=5193`. Never edit `.env`.

**Read first:**
- `briefs/common.md`;
- amendments **A28, A29, A35, A59, A60, A62** (only A62's tool name and description);
- C8 §4; C2 §10; C7 §2.1, §5.1; C3 §6; C4 §3.10;
- `docs/decisions.md` **D15, D20, D23**.
- Code:
  - `apps/api/src/mona/i18n/__init__.py` (`detect_language`, the word lists);
  - `apps/api/tests/test_i18n_server.py`;
  - `deploy/hermes/SOUL.md`;
  - `apps/api/src/mona/workflow/deadlines.py` (`set_status`, the `reminder.add` entry and note as the pattern), `workflow/api.py` (`update_deadline`);
  - `chat/notes.py`;
  - `mcp/read.py` (`list_deadlines`);
  - `apps/web/src/chat/cards/DeadlineCard.tsx`.

## Do

1. **`detect_language` (A59 items 1–3).**
   - Step 0 token filter.
   - The `ro` and `fr` word additions exactly as A59 item 2 lists them.
   - The trailing-punctuation strip before the extension test.
   - Add A59's five new §4.3 vectors to the parametrised test. Every existing vector must still pass.
2. **SOUL (A59 item 4).**
   - Add A59's lines to `deploy/hermes/SOUL.md` in its voice, each as short as it can be, in the sections where they belong ("What you can do here, and what you can't" and Principles).
   - Remove nothing else, except wording a new line makes redundant; list each removal in the report.
   - Report the byte size before and after. Stay under +1,200 bytes.
   - `rename_documents` doesn't exist in your worktree (FIX-16-N builds it); write its line anyway, as A59 gives it.
3. **Deadline Done (A60).**
   - **Migration `0011_deadline_status`** (down_revision: the current head, `0010`): add `deadline.status` to `file_ops.action`'s check, and to `dto/enums.py`.
     - Add an `_a60_deadline_status()` helper to `tests/c1_sql.py` (as `_a31_exports`/`_a36_tables` do), so `test_schema_parity` passes.
   - `set_status` writes the entry and the note per A60. It writes nothing when the status is unchanged.
   - The PATCH takes an optional `conversationId`; `DeadlineCard` sends `card.conversationId()` as it already does for reminders.
   - Regenerate `apps/api/openapi.json` and the web client with `npm run gen:api -w apps/web` (`make api-client` only checks).
   - The Activity log must render a `deadline.status` entry. Labels are keyed by actor:

     | Key | en | fr | ro |
     |---|---|---|---|
     | `activity.action.deadline.status_done_user` | You marked a deadline done | Vous avez marqué une échéance comme faite | Ați marcat o scadență ca rezolvată |
     | `activity.action.deadline.status_open_user` | You reopened a deadline | Vous avez rouvert une échéance | Ați redeschis o scadență |
     | `activity.action.deadline.status_dismissed_user` | You dismissed a deadline | Vous avez écarté une échéance | Ați ignorat o scadență |
     | `activity.kind.deadline.status` | Deadline status | Statut des échéances | Starea scadențelor |

     Add the kind to `routes/activity/kinds.ts`.
4. **`list_deadlines` `document_id` (A60 item 3):** any status, with `within_days` and `include_overdue` ignored and the cursor hash covering `document_id`. Still visible-filtered (C9), still cards when there are 1–5 results. The tool description gets A60's sentence.
5. **Tests.**
   - The vectors.
   - The PATCH writes one entry, one note (with a conversation) or none (without one), and a repeat writes nothing.
   - The migration up and down.
   - `list_deadlines` by document, including a done deadline.
   - The web: `DeadlineCard` sends the conversation id.
   - **Mutation:** step 0 removed → the vector "Open the file Releve_de_la_banque_des_comptes.pdf" fails.

## Acceptance (fresh output in the report)

- `make check` and `make ci-py` green; `make e2e` no worse than 129 passed / 19 skipped.
- The tests and the mutation.
- `SOUL.md`'s size before and after.

## Don't

- Don't touch the Hermes configs or plugin (FIX-16-H), the chat adapter (FIX-16-W), or naming (FIX-16-N).
- No tool that changes a deadline's status.
- No contract changes beyond A59–A60, and no showcase-only code (D16).
- Test sentences are synthetic: never Claudiu's words or practice names.
- Never edit `.env`. Don't touch the mona box.

Report: `~/DevFiles/mona-hq/orchestrator/reports/fix-16-s-report.md`.
