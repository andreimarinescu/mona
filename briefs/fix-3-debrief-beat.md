# FIX-3: the 4:00 beat ruling (first-seen signal, 90/75, stage cache, R11) and small follow-ups

Card **FIX-3**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-3`, branch `fix-3`, based on `main`.
- **Compose project:** `-p mona-fix3`. Export `WEB_PORT=6873 API_PORT=10165 POSTGRES_PORT=56832 HERMES_PORT=10042` (never edit `.env`).

Andrei ruled on the debrief beat (`docs/decisions.md` D15). Read D15 first, then amendments **A17** (a first-seen counterparty asks) and **A18** (thresholds 90/75) in `docs/contracts/amendments.md`. D15's standing direction applies to every choice here: a deterministic signal or check is better than relying on the model's judgement.

## Read first

- `briefs/common.md`; C5 §4.6, §5.1, §9; C6 §4.7 (the cached debrief); C9 §6 (snapshot, reset, §6.2 checks); C8 §5.4.
- `docs/demo-script.md` (beats 3:15 and 4:00, the fallbacks).
- `~/DevFiles/mona-hq/orchestrator/reports/l4-report.md` ("Quality run", open question 1) and `l5c-report.md` (the histogram, note 6).
- `apps/api/tests/live_l4.py` (the `stage` and `smoke` scenarios).

## Do

1. **A17, the first-seen signal**, in the classification outcome (C5 §9.3/§9.4 as amended), with `review.sentence.first` in the server catalog (EN/FR/RO; native-quality FR, best-effort RO). Tests:
   - first document of a counterparty → `entity`, with the `first` sentence;
   - a second document after one is filed → no signal;
   - a winning rule → no signal;
   - a visitor batch → no signal;
   - no counterparty → no signal;
   - three siblings in one batch all queue.

   **Mutation:** drop the filed-documents check → a test fails.
2. **A18:** migration 0006 alters the threshold defaults to 90/75, and the demo seed sets 90/75 explicitly. Tests that depend on bands set their thresholds explicitly.
3. **R11 (integrated review 1):**
   - Add disabled `source: seed` copies of the AGIPI and Hello bank rules (from `demo/seed/rules.learned.yaml`) to the stage seed. `demo-snapshot` must accept them (C9 §6.2 item 4).
   - Prove the fallback: the Rules screen enables one, and its preview lists the expected moves (e2e or API test).
   - Check what a debrief answer does when a disabled seed rule has the same conditions. The learned rule must win (C5 §4.6.1) and nothing is refused; pin it with a test.
   - Update the 4:00 fallback line in `docs/demo-script.md`.
4. **The stage cache (C6 §4.7, D15):**
   - Prove end to end that `MONA_DEBRIEF_CACHE=prefer` with a cache file in the snapshot shows the cached debrief with no live model call.
   - Write the rehearsal procedure into `demo/README.md` and the runbooks (EN/FR): run the live batch, judge the debrief, then `demo-snapshot --refresh-textcache` only when the debrief is good.
   - If C6 lacks a way to keep a good cache file from being overwritten by a later bad rehearsal run, report it (don't amend).
5. **A reproducible stage build, then the stage proof (D9 quality run, Qwen 3.6 allowed):**
   - **Build first.** No `demo` stage snapshot exists yet, and every migration invalidates one ("the snapshot is from another schema version; rebuild it"). Add `deploy/bin/mona stage-build` that runs C9 §6.3's whole build order on the current compose project:
     - seed load (pre-seeded tier, private overlay);
     - the `prefiled` documents of `demo/expectations.yaml` through `POST /api/intake` (resolve their paths from the private corpus manifest and the synthetic set), then wait until they settle;
     - the §6.7 stage settings, 90/75 included;
     - `demo-snapshot --name demo` with the findQuery cases;
     - steps 2–5: the live batch through intake with the quality model until its debrief is `ready`, `demo-prefiled`, `--refresh-textcache`, the reset, and §8 test 8.

     Document it in `demo/README.md` and the runbooks.
   - **Then the proof:** with the new signal at 90/75, report per live-batch document of `docs/demo-script.md`: queued or filed, the reasons, the band.
   - **Target:** the 3 AGIPI and 3 Hello bank documents queue on `entity` (first-seen), 5–8 queued in total, and the debrief asks about AGIPI and Hello bank.
   - If the snapshot pre-files an AGIPI or Hello bank document (which would defeat the signal), change the stage corpus composition (demo data, not product) and report it.
   - Re-run L5c's histogram at 90/75 with the signal, from cached model outputs where possible. Report the counts against L5c's.
   - **Privacy:** outputs go to `~/DevFiles/mona-hq/demo-data/runs/fix-3/` and are never committed.
   - **Also:** regenerate the shared `~/DevFiles/mona-hq/demo-data/synthetic/` with `uv run demo/synthetic/generate.py --anchor 2026-10-20` (L5c note 6; you're authorised to overwrite it).
6. **Small follow-ups:**
   - **Chat after auto-lock (FIX-1 question 2):** a 401/423 from the chat transport sends the person to `/unlock`, as other requests do, with a test.
   - **Telegram previews (FIX-2 question 1):** `answer_question` previews on the telegram channel leave out documents the channel can't see, as `preview_rule` now does, with a test.
   - **Doctor's privacy scan (FIX-2 question 3):** `mona doctor --privacy`'s memory scan reuses `mona.firstline`'s amount and date patterns (not its name check), with a test for a trailing "€" before punctuation.

## Acceptance (fresh output in the report)

- `make check` green (Python and web counts).
- Each item: the change and the test that pins it, and the A17 mutation.
- The stage-proof table (sha12 ids only, no document names or contents in the report).

## Don't

- No contract changes beyond A17/A18. If something else needs one, stop and report.
- No practice document names, text or amounts in the repo, the report or commit messages (D12).
- Never edit `.env`.
