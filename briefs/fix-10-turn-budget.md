# FIX-10: an enforced turn budget, an honest fallback, capabilities, reply-language check (A28, A29)

Card **FIX-10**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-10`, branch `fix-10`, based on `main`.
- **Compose project:** `-p mona-fix10`. Export `WEB_PORT=7673 API_PORT=10965 POSTGRES_PORT=57632 HERMES_PORT=10842` (never edit `.env`; the worktree has the `.env` symlink; `npm ci` first).

Read `docs/decisions.md` **D18** (and D15/D16), amendments **A28, A29**, then C3 §5, C4 §2. Evidence: `~/DevFiles/mona-hq/orchestrator/walkthrough-1.md`, "Evening session". FIX-11 runs in parallel and adds `export_table` and `payment_iban`. **You own SOUL and the Hermes config**; FIX-11 doesn't touch them. Your capability list already names "export a table of documents (CSV, Excel, Word)" and "IBANs printed on documents".

## Do

1. **The A28 budget** in the MCP server, per attributed turn (web and telegram): the 7th and later calls return `budget_exhausted` without running. `MONA_TURN_TOOL_BUDGET` (default 6); Hermes `agent.max_turns: 8` in `deploy/hermes/config.yaml` and the prod config. Tests: 6 calls run; the 7th is refused and has no side effect (a write tool too); a new turn resets the count.
2. **The A28 fallback text:** a web turn with no text part gets `chat.fallback.too_complex` in the reply language (EN/FR/RO; native-quality FR). Covers an empty reply, the iteration cap and an abort after tools. Tests on the adapter with recorded Hermes streams, including one from the evening session's shape (many tool events, no text).
3. **The A28 capabilities section** in `deploy/hermes/SOUL.md`. Keep it short and in Mona's voice.
4. **A29:** the reply-language check and the next-turn overlay line, with tests.
5. **Live check** (cheap model, D9): replay the evening's asks on a stage (`mona stage-build` with the cheap model, or FIX-3's snapshot):
   - "show me a table with all payables with the destination IBAN, due date and entity";
   - "please extract the ibans and create a csv or xlsx";
   - "can you try to read the iban from the PDF?".

   Report per ask: the tool calls (≤ 6), the time, and whether the reply is non-empty and honest about what can't be done. FIX-11's tools may not be merged yet, which is fine: an honest "can't yet" is the expected answer here.

## Acceptance (fresh output in the report)

- `make check` green.
- The tests above. **Mutations:** remove the budget check → a test fails; remove the fallback → a test fails.
- The live table.

## Don't

- No contract changes beyond A28/A29; no showcase-only code (D16).
- Don't touch FIX-11's tools.
- Never edit `.env`.
