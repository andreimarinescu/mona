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
