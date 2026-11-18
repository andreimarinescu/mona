# FIX-16 fix round 1

Five cards, one per lane, each on a **fresh branch off the integrated `bugfixes`**, which now holds all five FIX-16 lanes. Each card reads only its own section, plus `briefs/common.md`, its first-round brief, the review named in its section, and the amendments as they now stand: A57, A59, A60 and A62 were updated after the reviews.

Every card: fix each finding listed, add the test that pins it, and mutation-check the new guard. Re-run `make check` and `make ci-py`, and `make e2e` if you touched web or e2e (no worse than 129 passed / 19 skipped, plus new tests). Commit unsigned. Report to `~/DevFiles/mona-hq/orchestrator/reports/<card>-report.md`.

| Card | Agent | Worktree / branch | Compose `-p` | Ports (WEB API PG HERMES E2E) |
|---|---|---|---|---|
| FIX-16-H2 | coder | `.worktrees/fix-16-h2` / `fix-16-h2` | `mona-fix16h` | 7991 11281 57951 11161 5191 |
| FIX-16-W2 | coder-light | `.worktrees/fix-16-w2` / `fix-16-w2` | `mona-fix16w` | 7992 11282 57952 11162 5192 |
| FIX-16-S2 | coder-light | `.worktrees/fix-16-s2` / `fix-16-s2` | `mona-fix16s` | 7993 11283 57953 11163 5193 |
| FIX-16-N2 | coder | `.worktrees/fix-16-n2` / `fix-16-n2` | `mona-fix16n` | 7994 11284 57954 11164 5194 |
| FIX-16-R2 | coder | `.worktrees/fix-16-r2` / `fix-16-r2` | `mona-fix16r` | 7995 11285 57955 11165 5195 |

Worktrees live under `~/DevFiles/mona-hq/`. Never edit `.env`.

## FIX-16-H2 (review: `orchestrator/review/fix-16-h-review.md`)

1. **Blocker: the plugin must be live after a release** (A57 item 5 as updated).
   - Add `restart: true` under `hermes.depends_on.hermes-seed`. Pin it with a test on the rendered compose config, dev and prod overlay.
   - The doctor's `plugin` line goes red ("Hermes started before the installed plugin: restart Hermes") when the running gateway's start time is older than the newest installed `plugins/mona_prompt/*` file.
     - Use the gateway PID's `/proc/<pid>/stat` start time, or the `gateway.pid` mtime.
     - Never use `config.yaml`'s mtime: the boot migration rewrites it.
   - Add a regression test shaped like the review's reproduction: re-seed under a running gateway, and the probe must not be green; after a restart it is.
2. **Nits:**
   - `deploy/README.md` lines 8, 14, 21 and 27 (review nit 3);
   - the read-only test asserts `mode=ro` (review nit 4).
3. In the report, the C9 §4.1 fold text includes the restart requirement.
4. Don't touch `privacy.py`: FIX-16-R2 owns the `provider_extra_body` helper in this round.

## FIX-16-W2 (review: `orchestrator/review/fix-16-w-review.md`)

1. **The text caret on a stopped turn:** `Messages.tsx` passes `streaming={streaming && part.state === 'streaming'}` to `MonaText`. Extend the Stop test with an open text part: after Stop, no `.mona-caret`.
2. **The watchdog on keepalives:** add the review's keepalive-only stream test (a time trip with no further deltas).
3. **The live label for screen readers:** the polite region's text stays static. The seconds counter goes in an `aria-hidden` span next to an sr-only "Mona is thinking…" (`chat.thinking.live`). Test it.

## FIX-16-S2 (review: `orchestrator/review/fix-16-s-review.md`)

1. **Review nit 1:** a real deadline on the deleted document before the visibility assertion; drop the default-vs-30 comparison.
2. **Review nit 2:** `test_soul_states_a59_limits` pins A59's lines.
3. **A59's deadline line as updated:** web app versus Telegram wording in `SOUL.md`. Update the pin.
4. **A60 item 5:** a dismissed deadline's card shows the "Dismissed" badge (`deadline.dismissed`, strings in A60) and no due badge or buttons. Add a web test.

## FIX-16-N2 (review: `orchestrator/review/fix-16-n-review.md`)

1. **The leading date counts in full** (A62 item 1.1 as updated). Apply the review's guard. It must still accept `2026-10_2025-A-118`. Add the review's three rows to the test, then mutation-check.
2. **Visibility-aware refusal counts** (A62 as updated): pass `visible` into `_check`. When every offender is hidden, the message has no number. Add the Telegram test the review describes.
3. **The 4000-character cap:** a test with titles at the clip limit, long names and 10 collisions, asserting `len(json) <= 4000` and `truncated`.
4. **The offset in `hint`** is now the contract (A62). Nothing to change; keep the test.

## FIX-16-R2 (review: `orchestrator/review/fix-16-r-review.md`)

1. **The request as Hermes sends it.**
   - Tool schemas go through a port of the pinned image's `_convert_mcp_schema` / `_normalize_mcp_input_schema` (nullable `anyOf` → `nullable: true`, `required` pruned, object shape repaired). Apply it at build time and in the registry fallback.
   - Send `reasoning_effort` from the config's `agent.reasoning_effort` (default `medium`), even under `--no-extra`.
   - Pin both with a fixture that the pinned image produces (the H render-test pattern), so a Hermes bump that changes the shape goes red.
2. **`privacy.provider_extra_body(cfg, env)`, and `--extra-from` uses it** (A57 as updated).
   - A public helper built on `privacy._custom_providers`. It returns the `extra_body` of the entry whose normalised `base_url` equals `model.base_url`, in the `custom_providers` or the migrated `providers.<key>` form.
   - A5 (`hermes_config_problems`) uses the same helper.
   - Build a fixture of a config migrated by the pinned image (`scripts/docker_config_migrate.py` there), and test both forms for A5 and `--extra-from`.
3. **Use W's normalisation:** import `mona.chat.watchdog`'s line rule instead of R's own copy.
4. **Review nits 2–7:**
   - the wrapper's edge cases;
   - scenario-file validation;
   - keep a reported 0, and print n beside the token and act-seconds triples;
   - tests for the surviving mutations;
   - fixture result shapes per C4, with the mark-paid history after a `get_brief` result;
   - the `--extra-from` default and its workaround in `--help`.
