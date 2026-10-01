# L1-M3: debrief hooks, Visitors purge, apply-group rule revert, amendments

Card **L1**, milestone 3. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l1-m3`, branch `l1-m3`, based on `main`.
- **Compose project:** `-p mona-l1c`, with `WEB_PORT=5873 API_PORT=9365 POSTGRES_PORT=56032 HERMES_PORT=9242`. Run `make check COMPOSE="docker compose -p mona-l1c"`.

M1 (rules, templates, file ops, services) and M2 (the pipeline) are on `main`. This milestone wires the set B obligations into L1's code, plus the amendments routed to L1.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D14; **D14: you own the apply-group rule revert**).
- `docs/contracts/amendments.md`: A4, A7, A10, A14, A15.
- Contracts:
  - C6 §3.1 (the hooks L1 calls), §7.2–§7.3 (the activating `rule.change` and the revert on undo);
  - C9 §5 (the Visitors purge: selection, timing, what one purge does, what it doesn't reach), §8 test 6;
  - C5 §4.7 with A7 (`condition_text`), §6.1/§7 with A15, §1.2/§5 with A14;
  - C1 §6.2 with A10;
  - C7 §5 (undo) and §9 (invariants).
- **Code on `main`:** `mona/services/README.md` (M1 + M2), `mona/pipeline`, `mona/fileops`, `mona/rules` (including F0's `text.py` renderer).
- **Reports:** `~/DevFiles/mona-hq/orchestrator/reports/l1-m1-report.md` and `l1-m2-report.md` (open items).

## Build

1. **Hooks** (C6 §3.1): call `mona.interviews.hooks.on_document_settled(batch_id)` after each settling transaction and `on_batch_done(batch_id)` after the batch-done transition, both outside the filing transaction, as C6 says.
   - L4 is building that module in parallel. If it isn't on `main` when you start, add `mona/interviews/hooks.py` with exactly those two signatures as no-ops (L4's version replaces it at merge) and test that your call sites invoke them (a spy).
2. **Visitors purge** (C9 §5): in `mona.fileops`, a periodic Procrastinate task (every 15 min) plus `mona purge-visitors [--dry-run]`.
   - Follow C9 §5.3's order exactly, including the undo-chain handling and the `deadline.add`/`reminder.add` entries.
   - C9 §8 test 6 in full: an undone-and-redone visitor batch, a deadline journaled only by subject, caches, thumbnails, the model-output cache.
   - Mutation: delete groups before their undo/redo groups → the FK failure is caught by the test.
3. **Apply-group rule revert** (C6 §7.3, A4, D14): group undo of a `rule_apply` group returns the rule to `draft` (a `rule.change` journal entry), and redo re-activates it.
   - Tests: apply → group undo → rule draft and files back; redo → rule active and files moved again.
   - Mutation: skip the revert → a test fails.
4. **A7:** the `condition_text` renderer takes C8 §8's Romanian wording and quotes, and French U+00A0 in amounts and inside « ». Extend C5 §11 test 16 with an amount row per language.
5. **A10:** no extracted deadline for a document of a visitor batch.
6. **A14:** retry an all-null answer once with the first page only, plus a test with a recorded empty output then a good one.
7. **A15:** column-aware verification and `findQuery`. Re-run `mona pipeline evidence` and the pdf.js check (`/dev/pdf`, from M2) on the synthetic set: the column case must now highlight.
8. **Root-owned files:** the Python containers write `./data` as root. Run api and workers as the host user (`user: "${UID:-1000}:${GID:-1000}"` or equivalent) so `./data` stays host-owned, and prove it after a pipeline run. Check that OCR, `HOME` and the uv venv still work.

## Acceptance (fresh output in the report)

- `make check` green.
- Every [M] above mutation-checked, with the failing test named.
- The pdf.js check result before and after A15.
- `ls -ln ./data` after a pipeline run shows the host uid.

## Don't

- No interview logic (L4), REST or MCP (L2).
- No contract changes beyond the amendments listed: stop and report.
- No practice documents in fixtures.
