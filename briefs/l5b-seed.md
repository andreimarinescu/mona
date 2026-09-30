# L5b: seed re-keyed to the frozen contracts, demo tiers, acceptance expectations

Card **L5**, part b. Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l5-seed`, branch `l5-seed`, based on `main`.
- **Private outputs:** `~/DevFiles/mona-hq/demo-data/`.

F0 is building the seed loader (`mona seed load`) in parallel. You produce the data it loads. Part c (the confidence histogram and thresholds, `mona demo-reset`, the `findQuery` fixture check) follows once L1's pipeline exists, so this card has no model calls.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D7).
- **The frozen contracts:**
  - `docs/contracts/C1-domain.md`: §2 registry tables, §9 seed invariants, §11 DTOs;
  - `docs/contracts/C5-classification.md`: §4 rule grammar and actions, §4.5 `unit`, §6.2 resolution, §8 templates with the worked examples, §10 `rules.yaml` schema.
- **Your part a:** `demo/` and its README, and `~/DevFiles/mona-hq/orchestrator/reports/l5-data-report.md`.
- **`docs/demo-script.md` v1:** the pre-seeded state, the live batch, and the "learned live" rules.
- Claudiu's input (`~/DevFiles/mona-hq/latest-classification-feedback-claudiu.md`, `…/exemplu-ORGANIZARE-Clasificare Documente.txt`).

## Build

1. **Re-key** `demo/seed/practice.yaml` and `demo/seed/rules.yaml` to C1 §9 / C5 §10 exactly.
   - Categories by slug, including `health` (D7).
   - Labels in fr/en/ro and DS icons.
   - Path and file-name templates in C5 §8 grammar.
   - Entities with sub-units. **Person splits exist only through rules** (C5 §4.5); there are no implicit person folders.
   - Counterparties with aliases (C1 §2.5).
   - Accounts referencing the private overlay keys (identifiers stay in `demo-data/seed/identifiers.yaml`, re-keyed to what the loader expects).
2. **Two tiers.**
   - `rules.yaml` holds the **pre-seeded** rules (OPCO, TALENZ, OXYLEO, UNIM, SELARL annual documents, payroll).
   - `rules.learned.yaml` holds the rules the demo's debrief teaches live (the AGIPI split by insured person with PER vs Assurance Vie; Hello bank → LMNP / Angers-Strasbourg / Banque / {fy}). They're used by tests and rehearsal as the expected outcome; `demo-reset` never loads them.
3. **Acceptance expectations** `demo/expectations.yaml`: for every acceptance case (the six feedback cases, same insurer with two persons, FY-crossing, rotated scan, duplicate) and every live-batch and synthetic document in demo-script v1, list the id (sha12 or `syn-*`), the expected entity / category / sub-unit / counterparty / fiscal year, the rendered path and file name under C5 §8, and the expected band/reason (auto-file / queue with which `ReasonChip`), **both before and after** the learned rules.
   - Keep the private detail (file names, real amounts) in `demo-data/`. The committed file carries ids, generic labels and fictional values only.
4. **Update `demo/synthetic/docs.yaml`** expectations to C5 §8 (paths, names, fiscal years). Regenerate with `--anchor 2026-10-20` and confirm the text-layer tests still pass.
5. **Cross-check renderer:** update `demo/scripts/templates.py` to the C5 §8 grammar. A test renders every expectation from `expectations.yaml` and every C5 §8.5 worked example. This is a second, independent implementation, so L1's renderer can be diffed against it later.

## Acceptance

- `pytest demo/tests` green, including: every C5 §8.5 worked example; every expectation renders; the learned-rules file parses under the same schema; and a guard test that no committed file contains IBAN/SIREN patterns or private surnames.
- If F0's loader has landed on `main` by the time you finish, `mona seed load demo/seed --tier preseeded` loads your seed with the overlay on a scratch stack (`-p mona-l5`, with `WEB_PORT=5373 API_PORT=8965 POSTGRES_PORT=55632 HERMES_PORT=8842` so it can't collide with other lanes' stacks). Otherwise, report that the load is pending.
- The report lists every place where Claudiu's input is still an assumption (FY ends, payroll destination, trip receipts, the PER/AV folder names), with the default you chose.

## Don't

- No application code under `apps/`.
- No contract changes: report conflicts.
- No model calls.
