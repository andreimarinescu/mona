# L5c: demo snapshot and reset, generated Hermes memory, the D12 guard, the histogram

Card **L5**, part c. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l5c`, branch `l5c`, based on `main`.
- **Compose project:** `-p mona-l5`, with `WEB_PORT=5373 API_PORT=8965 POSTGRES_PORT=55632 HERMES_PORT=8842`. Run `make check COMPOSE="docker compose -p mona-l5"`.

The stage depends on `mona demo-reset` putting the practice back into exactly the rehearsed state, every time, in minutes. Build the machinery and prove it on a scratch stage built from synthetic documents. The real stage snapshot is built later, after Andrei rules on which documents the debrief asks about (an open product question; don't decide it).

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D14; **D9 quality runs, D12 practice-agnostic, D13 overnight**).
- `docs/contracts/amendments.md`.
- **Contracts:**
  - **C9 §6 in full** (what a snapshot holds and what reset restores, what a snapshot must be, commands and the host wrapper, re-anchoring, the Hermes profile across environments, backup and restore, stage settings), §7 (secrets and logs), §8 tests 7–9;
  - C1 §9 (seed invariants, the pointer on re-anchoring);
  - C6 §4.7 (the cached debrief bound by sha256);
  - C5 §1.3 (caches).
- **Code on `main`:** `mona/seed`, `mona/pipeline` (`mona pipeline run`, `mona pipeline evidence`, the `/dev/pdf` `findQuery` check), `mona/fileops` (recovery: run it before snapshots), `deploy/hermes/`, `demo/` (seed tiers, expectations, synthetic generator), `docs/demo-script.md`.
- **Notes:** `~/DevFiles/mona-hq/orchestrator/l5c-notes.md`.

## Build

1. **The host wrapper and commands** (C9 §6.3): `deploy/bin/mona` (no Docker socket in any service) with `demo-snapshot --name <n>`, `demo-reset [--name <n>] [--anchor <date>] [--prefiled]` and `backup` / `restore`. The pieces:
   - the whole-database dump and restore;
   - archive + inbox + trash mirrored with `rsync --delete`;
   - the text, OCR, thumbnail and model-output caches;
   - the Hermes profile directory per §6.1/§6.5: SOUL, memories, the empty attachment folders, and the installed 07:30 brief job kept across resets; never `state.db`, sessions or `.env`;
   - the §6.2 refusal checks, with the `auth_sessions` tolerance;
   - re-anchoring (§6.4: event timestamps shift, printed dates never do);
   - stage settings (§6.7: `debrief_early_min`, auto-lock, …);
   - recovery run first.

   Reset ends with Hermes restarted and `mona` health green.
2. **Generated Hermes memory** (D12): `mona hermes-memory` renders `memories/MEMORY.md` and `USER.md` from the loaded practice registry (owner name and register, the entities and their purpose, the accountant, preferences) in the format the pinned Hermes reads. `demo-reset` and `seed load` call it. Replace the hand-written files in `deploy/hermes/memories/` with a note saying they're generated.
3. **The D12 guard** `scripts/no-practice-names.py`, in `make check`: every entity, person and counterparty name and alias in `demo/seed/practice.yaml` must not appear in `apps/*/src`, `packages/` or `deploy/hermes/` (outside the generated `memories/`). Case-insensitive, word-bounded.
   - If it finds the L2-P1 "e.g. AGIPI" hint in `mona/mcp/filters.py` (L2-P2 may have fixed it already), fix it with a neutral example.
   - Mutation: plant a name in a source file → the guard fails.
4. **Synthetic fix:** regenerate `syn-urssaf-call` so its amount doesn't wrap across lines (its quote can't verify today), and keep the text-layer tests green.
5. **Confidence histogram** (D9 quality run, Qwen 3.6): run the pipeline (`mona pipeline evidence` or the stack) over the 88 valid PDFs + the synthetic set. Write the per-document confidence, band and reason to `~/DevFiles/mona-hq/demo-data/runs/l5c-histogram/` (private), and the histogram as counts only, plus a proposed threshold pair (C5 §9; defaults 85/60), to the report. **Don't change the thresholds:** that's Andrei's call with the debrief question. Report the spend delta.
6. **`findQuery` on the rehearsed documents:** run the `/dev/pdf` check (L1-M2/M3) over every verified field of the 3 evidence-moment documents in `docs/demo-script.md` and the synthetic set. The practice documents' results go to private outputs, with counts in the report.
7. **The scratch stage proof:** seed (pre-seeded tier) → drop the synthetic batch through the pipeline (cheap model) → `demo-snapshot --name scratch` → change things (file, correct, apply a rule, chat) → `demo-reset --name scratch --anchor <date>` → the state equals the snapshot.
   - **Run it twice in a row:** identical DB dump (modulo the `\restrict` token), identical tree checksums, identical Hermes profile files. This is C9 §8 and plan §14.

## Acceptance (fresh output in the report)

- `make check` green, including the guard and its mutation.
- **C9 §8 tests 7–9,** with the [M] mutations: skip the archive mirror, shift printed dates, keep `sessions/` → each fails.
- The twice-in-a-row reset proof (the checksums).
- Reset wall time on the laptop.
- The histogram counts and proposed thresholds.
- The `findQuery` result counts.

## Don't

- No pipeline, REST or interview logic changes. If something is missing for reset (a hook, a CLI), stop and report.
- Don't build the real stage snapshot, and don't change thresholds or seed tiers: those wait for Andrei's ruling.
- No practice text in the repo or the report.
