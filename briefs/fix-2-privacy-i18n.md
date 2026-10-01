# FIX-2: privacy and i18n findings from integrated review 1

Card **FIX-2**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-2`, branch `fix-2`, based on `main`.
- **Compose project:** `-p mona-fix2`. Export `WEB_PORT=6773 API_PORT=10065 POSTGRES_PORT=56732 HERMES_PORT=9942` (never edit `.env`).

Fix the findings below from `~/DevFiles/mona-hq/orchestrator/review/integrated-review-1-findings.md` (each has where, scenario, fix and the skeptic's note). FIX-1 runs in parallel on the chat transport, corrections, `sum_amounts`, the guard and Intake/Home. Stay out of those.

## Do

1. **R4/R13, Telegram rule previews (C4 §2.6, C9 §3):** `preview_rule`, `apply_rule` and `correct_document(scope=all)` on the telegram channel drop documents not visible on that channel. They're left out of `moves`, `stays` and the counts, and are never moved from Telegram. Add a C4 §5.7 test with a personal-entity candidate of a practice rule.
2. **R16:** documents of visitor batches are never used as classifier exemplars (C5 §5.5, C9 §5.5), with a test.
3. **R12:** a counterparty created from a visitor document (origin `extracted`, used only by visitor documents) is removed by the Visitors purge (C9 §5.3), with a test. Never remove a counterparty that any practice document or rule references.
4. **R17:** the generated Hermes memory (D12, `mona hermes-memory`) doesn't name personal entities or family members. C9 §3.4: memory is shared with Telegram. Describe the household generically ("a personal household entity") and keep practice entities as now. Update `test_demo_memory`.
5. **R18:** implement C9 §8 test 4, the Telegram first-line checker: notification first lines carry no names or amounts. Build it as the check C9 describes, over the brief and notification templates.
6. **R7:** implement C8 §4's `detect_language` (algorithm, word lists, the §4.3 vectors) and use it where C3 used the interim detector (the adapter's reply-language line), with the vectors as tests and the C8 mutation.

## Acceptance (fresh output in the report)

- `make check` green.
- Each item: the change and the test that pins it.
- **Mutations:** remove the channel filter from `preview_rule` → the new test fails; drop a C8 cue → a vector fails.

## Don't

- No contract changes: if a fix needs one, stop and report.
- Stay off FIX-1's files.
- Never edit `.env`.
