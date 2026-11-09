# FIX-13d: the adapter drops markdown-table lines in a table-card turn (A40)

Card **FIX-13d**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-13`, branch `fix-13` (FIX-13, 13b and 13c on top of `main`). Commit on top.
- **Compose project:** `-p mona-fix13`. Export `WEB_PORT=7983 API_PORT=11275 POSTGRES_PORT=57942 HERMES_PORT=11152`. Never edit `.env`.

**Read first:**
- `briefs/common.md`;
- amendments **A28, A36, A39, A40**;
- C3 §3.2–§3.3, §4.3, §5.1, §7.2;
- `docs/decisions.md` **D15, D20**;
- `~/DevFiles/mona-hq/orchestrator/reports/fix-13b-report.md` (the FIX-13b and FIX-13c sections: the slip, the harness, the runs).

## Do

1. **A40 in `apps/api/src/mona/chat/stream.py` `run_turn`**, between the translator's chunks and `out()` (a small filter class, e.g. in `chat/parts.py` or a new `chat/guard.py`):
   - it activates when a `table` card has been emitted in this turn;
   - it holds and judges text line by line across `text-delta` chunks (a line can span deltas, and a delta can hold several lines);
   - it drops lines whose first non-blank character is `|`, together with their newline;
   - it flushes held non-table text at `text-end` and at the turn's end;
   - `text-start`/`text-end` stay paired with the same ids;
   - a dropped line is never recorded in `parts`.
   - If the turn ends with a table card and no text, it emits `chat.table.intro` in the reply language (EN/FR/RO, i18n check green) instead of the A28 fallback.
   - It logs one line with the dropped-line count only.
2. **Tests** (unit plus the adapter's stream tests):
   - a table split across deltas;
   - prose before and after a table kept byte-identical;
   - a `|` inside a prose line kept;
   - no table card in the turn → nothing dropped;
   - an all-table reply → `chat.table.intro` and not the fallback;
   - transcript reload (§7.2) shows the filtered text.
   - **Mutations:** filter always off → a test fails; the intro replaced by the fallback → a test fails.
3. **Live check** (D9 quality run, Qwen 3.6, through `/api/chat`, the FIX-13 harness, fresh conversation per turn):
   - the payables table ask 12 times. Targets:
     - 0 of 12 replies show a table or placeholder in the **streamed and stored** text;
     - 0 of 12 show row values that aren't in the tool result;
     - every reply is non-empty and honest.
   - Report how many turns had lines dropped (from the log line), plus the spend.
   - Tear down the stack and keep the volumes.

## Acceptance (fresh output in the report)

- `make check` green.
- `make e2e`: no worse than 128 passed / 19 skipped.
- The tests, the mutations and the live table.

## Don't

- No contract changes beyond A40. Don't touch SOUL or A39's note. No showcase-only code (D16).
- Never edit `.env`. Don't touch the main checkout or its `data/`.

Report: `~/DevFiles/mona-hq/orchestrator/reports/fix-13d-report.md`.
