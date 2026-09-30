# Demo data tooling

Private outputs go to `~/DevFiles/mona-hq/demo-data/`; nothing derived from practice documents is committed.

- `uv run demo/scripts/inventory.py` writes the corpus manifest and summary to `demo-data/corpus/`.
- `uv run demo/synthetic/generate.py --anchor 2026-10-20` renders `demo/synthetic/docs.yaml` to `demo-data/synthetic/`.
- `demo/seed/practice.yaml` and `rules.yaml` are the draft seed; identifiers resolve from `demo-data/seed/identifiers.yaml`.
- Tests: `uv run --no-project --with pytest --with pyyaml --with reportlab --with pillow --with numpy pytest demo/tests` (needs poppler-utils).
