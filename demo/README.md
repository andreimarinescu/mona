# Demo data tooling

Private outputs go to `~/DevFiles/mona-hq/demo-data/`; nothing derived from practice documents is committed.

- `demo/seed/practice.yaml` (C1 §9) and `demo/seed/rules.yaml` (C5 §10, the pre-seeded tier) are what `mona seed load demo/seed --tier preseeded` loads. `demo/seed/rules.learned.yaml` holds the rules the debrief teaches live; `demo-reset` never loads it.
- Identifiers resolve from `demo-data/seed/identifiers.yaml` (`MONA_SEED_OVERLAY`): `{ref: a.b.c}` is a dotted path into it (`people.<key>`, `entities.<key>`, `accounts.<key>.iban`, `counterparties.<key>.siren`).
- `demo/expectations.yaml` lists, for every live-batch, pre-filed and synthetic document, the expected destination, band and reason before and after the learned rules. Real dates, references and file names are in `demo-data/seed/expectations.private.yaml`.
- `uv run demo/scripts/inventory.py` writes the corpus manifest and summary to `demo-data/corpus/`.
- `uv run demo/synthetic/generate.py --anchor 2026-10-20` renders `demo/synthetic/docs.yaml` to `demo-data/synthetic/` and writes its fictional account IBANs to `generated-identifiers.yaml` (copy them into the overlay).
- `demo/scripts/templates.py` is an independent C5 §8 renderer for diffing against L1's; `rules_schema.py` validates the rules files.
- Tests: `uv run --no-project --with pytest --with pyyaml --with reportlab --with pillow --with numpy pytest demo/tests` (needs poppler-utils). Tests that need the private overlay, expectations or corpus skip when `demo-data/` is absent.
- Demo state (C9 §6): `deploy/bin/mona demo-snapshot --name <n>`, `deploy/bin/mona demo-reset --name <n> --anchor <date>`, `backup` and `restore` run on the host; set `MONA_COMPOSE="docker compose -p <project>"` for a lane stack. Every DB and file step runs as `mona ops <step>` in the compose `ops` one-shot container. `mona hermes-memory` (also run by `seed load` and `demo-reset`) renders the Hermes memory seeds from the registry.

## The stage build (C9 §6.3) and the rehearsal

**Build.** `deploy/bin/mona stage-build [--early N] [--anchor YYYY-MM-DD] [--yes]` rebuilds `demo` and `demo-prefiled` from scratch on the current compose project (`MONA_COMPOSE`). It needs `MONA_SEED_OVERLAY_HOST`, and it reads the corpus, the corpus manifest and the synthetic set from `MONA_CORPUS_DIR`, `MONA_CORPUS_MANIFEST` and `MONA_SYNTHETIC_DIR` (default: the laptop's `demo-data/` layout). Every migration invalidates a snapshot ("the snapshot is from another schema version; rebuild it"), so run it again after one. Steps:
1. Clean slate: the schema at head, empty data trees and debrief cache, no Hermes conversation. Text and model-output caches are content-addressed and kept, so a rebuild with the same model reuses them. Then `seed load /seed --tier preseeded` with the overlay.
2. The `prefiled` documents of `demo/expectations.yaml` through `POST /api/intake`. Any that queue are filed as the person would: confirmed when the suggestion is the expected destination, corrected to it otherwise (no rule).
3. The §6.7 settings through `PATCH /api/settings`: 90/75 (A18), `debriefEarlyMin` (`--early`, default 7), queue threshold 5, auto-lock 120.
4. `demo` with the findQuery cases of the pre-filed documents (`mona pipeline evidence`; the pdf.js check is `MONA_FINDQUERY_CASES=… npm run e2e -w apps/web -- findquery` on the laptop).
5. `demo-reset --name demo`, then the `live` documents in script order, waiting until the batch debrief is `ready` from a live run. Run it with the quality model (D9), and with `MONA_DEBRIEF_CACHE` at `fallback` or `prefer`: the build emptied the debrief cache, so either mode generates live.
6. `demo-prefiled`, then `demo-snapshot --refresh-textcache --name demo`, then `demo-reset --name demo` and the check that a debrief cache file for exactly the live batch's candidates is in `demo` (C9 §8 test 8).

Each step prints the per-document outcome by `sha256[:12]`; `/data/stage-build/` keeps the reports (never part of a snapshot).

**Rehearsal: keeping a good debrief.** On stage the box runs `MONA_DEBRIEF_CACHE=prefer` (D15), so the debrief shown is the one in `demo`'s text cache. To replace it:
1. `mona demo-reset`, drop the live batch, and let the debrief reach `ready`. Don't open chat and don't answer.
2. Judge the debrief in the Intake banner and the chat card: the AGIPI question splits PER and life insurance by insured person, Hello bank goes to LMNP / Angers-Strasbourg / Banque, every quote is highlighted.
3. Only if it is good: `mona demo-snapshot --refresh-textcache --name demo`. After a bad run, just `mona demo-reset` (the snapshot keeps the previous file).

With `prefer`, a rehearsal whose candidates match a cached file shows that file and writes nothing, so to rehearse a fresh live debrief set `MONA_DEBRIEF_CACHE=fallback` for the rehearsal.
