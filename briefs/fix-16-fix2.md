# FIX-16 fix round 2

Four cards, each on a **fresh branch off the integrated `bugfixes`**, which now holds fix round 1. Each card reads only its own section, plus `briefs/common.md`, its first-round brief, the round-1 fix review named in its section, and the amendments as they now stand. A57 items 4–5, A58 item 4 and A62 item 1 (the leading date, the month-name literals) were updated after the round-1 fix reviews.

Every card: fix each item, add the test that pins it, and mutation-check the new guard. Re-run `make check` and `make ci-py`, and `make e2e` if you touched web or e2e (no worse than 130 passed / 19 skipped). When the host is loaded by the other lanes, re-run an e2e or web failure alone before calling it a flake, and say so. Commit unsigned. Report to `~/DevFiles/mona-hq/orchestrator/reports/<card>-report.md`.

| Card | Agent | Worktree / branch | Compose `-p` | Ports (WEB API PG HERMES E2E) |
|---|---|---|---|---|
| FIX-16-H3 | coder-light | `.worktrees/fix-16-h3` / `fix-16-h3` | `mona-fix16h` | 7991 11281 57951 11161 5191 |
| FIX-16-W3 | coder | `.worktrees/fix-16-w3` / `fix-16-w3` | `mona-fix16w` | 7992 11282 57952 11162 5192 |
| FIX-16-N3 | coder | `.worktrees/fix-16-n3` / `fix-16-n3` | `mona-fix16n` | 7994 11284 57954 11164 5194 |
| FIX-16-R3 | coder-light | `.worktrees/fix-16-r3` / `fix-16-r3` | `mona-fix16r` | 7995 11285 57955 11165 5195 |

Worktrees live under `~/DevFiles/mona-hq/`. Never edit `.env`.

## FIX-16-H3 (review: `orchestrator/review/fix-16-h2-review.md`)

1. **`mona restart hermes`** (A57 item 5 as updated): a `deploy/bin/mona` subcommand that restarts Hermes through the wrapper's own `compose` (so the prod overlay and `MONA_TAG` apply on the box), then waits for health as `up` does.
   - The doctor's red plugin message and `deploy/README.md` line 27 point to it.
   - Add it to the wrapper's usage header and the README's `bin/mona` row.
   - Test it the way the wrapper's other subcommands are tested.
2. **The prompt warning's anchor** (A57 item 4 as updated): "no conversation since the release" compares the newest web session with the running gateway's start (the plugin line's source), never the config's mtime. Pin it: a no-op seed re-run under a running gateway with a web session since its start stays green. Update README line 21 to match.
3. **Review nit 1:** pin the mode half of the seed's drift guard. A `chmod 666` on an installed plugin file is repaired to `0:0 644` with a newer mtime, and the same for a directory at `777`.

## FIX-16-W3 (review: `orchestrator/review/fix-16-w2-review.md`)

1. **A tool chip running at Stop** (A58 item 4 as updated). In `Messages.tsx`, when the chat is not streaming, a tool part's `running` state shows as `interrupted`, matching what a reload shows (`transcript.py`). Add a held-stream Stop test: `tool-input-start` plus `tool-input-available`, then Stop, then assert `data-state="interrupted"` and no `.mona-spin`.
2. **The `thread.test.tsx` flake under load.** W2 saw one chat-stream test fail in 3 of 4 full web runs while other lanes loaded the host, and S2's reviewer saw it once.
   - Reproduce it under load: run the web suite while `make ci-py` runs, or with `--maxWorkers` raised, or with the CPU pinned.
   - Name the test and the root cause in the report: a timer race, a missing `await`, the 50 ms throttle against a fixed wait, or something else.
   - Fix the cause. A longer timeout is not a fix unless the report shows the wait is legitimately bounded by something slow, such as the throttle.
   - If it won't reproduce in 10 loaded runs, say so with the commands, and add no change.

## FIX-16-N3 (review: `orchestrator/review/fix-16-n2-review.md`)

1. **The leading-date exceptions** (A62 item 1.1 as updated):
   - a complete leading date (year, month and day) is never followed by the wrong-date error;
   - after a partial date, the run is not the error when an inferred token starts there.
   - The review's rows become tests: `2026-10_25-A-118` and `2026-10-05_25-A-118` with reference `25-A-118`; `2026-01-16_13-Habitat` with counterparty "13 Habitat"; `2026-01-16_01_x` keeps `01` as a literal.
   - The three wrong-date rows from round 1 stay refused.
   - Mutation-check each exception.
2. **Month abbreviations** (A62 errors as updated): a whole literal segment equal to a listed abbreviation, case- and accent-insensitively, is the month-name error. `2026-janv-16 HB` is refused.
   - Test one abbreviation per language.
   - Test that a literal "Marchand" or "Decor" still passes: whole segments only.

## FIX-16-R3 (review: `orchestrator/review/fix-16-r2-review.md`)

1. **Review nit 1:** the image probe builds `AIAgent` with the gateway's `reasoning_config` (`GatewayRunner._load_reasoning_config`, or whatever the pinned image uses to load it). Add one image case with a non-default effort (`high`).
   - Port Hermes' mapping of edge values exactly: YAML `false` and an unknown string give what Hermes sends.
   - The probe and `config_effort` must agree on every case the test lists.
2. **Review nit 2:** without `--no-extra`, if `--extra-from` yields no extra body (a missing file, an unset `${VAR}`, or no entry matching `model.base_url`) and `--extra` adds none, `run` stops with a `ReplayError` that names which. `--no-extra` stays the only way to send none.
3. **Review nit 3:** the summary records the `reasoning_effort` actually sent. When `--extra` overrides it, the source is `inline`.
4. **Review nit 4** (dev OpenRouter request shape): no change. Name it in the report as a known dev-only difference; the box request matches.
