# L1-M1: rules engine, templates, file ops and the core services

Card **L1**, milestone 1 (plan §6.3 L1). Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l1-m1`, branch `l1-m1`, based on `main` (which includes F0).
- **Compose project:** `-p mona-l1`, with `WEB_PORT=5473 API_PORT=9065 POSTGRES_PORT=55732 HERMES_PORT=8942`.

This is the correctness core of Mona: the rules engine, path and name templates, and the journaled file operations with undo. L2 wraps your services as MCP tools and REST endpoints, L4 builds interviews on them, and milestone 2 (the pipeline jobs and the model step) calls them. Everything here is deterministic and must be mutation-checked.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D7; D5 = the actor is who executed, with `via`).
- The frozen contracts:
  - **C7 in full;**
  - **C5 §2, §4, §6.2 (resolution; alias learning §6.2.5), §8, §9 (bands and reasons, for `correct_document`), §10, §11;**
  - **C1 §2–§5, §9, §11;**
  - C4 §3.5, §3.8, §3.9 and §3.16 (the semantics of the tools your services back), §2.4 errors and §2.7 side effects.
- F0's code on `main`: `mona/db`, `mona/dto`, `norm()`, ids, the IBAN helper, the seed loader.
- L5's data: `demo/seed/`, and `demo/expectations.yaml` if it has landed on `main` (L5b is running in parallel).

## Reuse, don't rewrite

F0 already built the C5 §4 rule **grammar** (parsing and validation), the C5 §8.1 **template parser** and the C5 §4.7 `condition_text` renderer, because the seed loader needed them (see `mona/` on `main` and `~/DevFiles/mona-hq/orchestrator/reports/f0-foundation-report.md`). Build evaluation, rendering and everything else on top of those modules. Extend them if needed; don't duplicate them.

## Integration notes (from F0, 2026-09-30)

- **Run checks with your own project:** `make check COMPOSE="docker compose -p <your project>"`, with your ports exported (`POSTGRES_PORT` etc.). Plain `make check` would start the default project. Run `npm ci` in your worktree before any `compose up`, so compose can't create a root-owned `node_modules`.
- **Migrations:** C1's schema is migration `0003`. The S5 spike tables are `0002`. Only L2 adds a migration in this wave: `0004` drops the `spike_*` tables. L1 adds none. If you need an index, name it in your report.
- **Amendment A1:** the IBAN salt lives in `settings.iban_salt`, created by the seed loader. Read it from settings, never from env.

## Build

1. **Templates** (`mona/templates/`): C5 §8 grammar, token values, the fiscal-year formula, folder segments (accents kept), file names (diacritics dropped, sanitised, capped with room for the collision suffix).
   - All C5 §8.5 worked examples as tests.
   - If `demo/expectations.yaml` is on `main`, diff every expectation against your renderer; the two implementations must agree, and any disagreement goes in the report with who is right per C5.
2. **Rules engine** (`mona/rules/`): C5 §4 in full:
   - conditions, including the identifier candidates;
   - persons and sub-units (sub-units only from a rule's `unit`);
   - actions;
   - priority and conflict detection (learned rules outrank the rules they correct);
   - the rendered `condition_text` in EN/FR/RO (§4.7);
   - statistics (§4.8);
   - `rules.yaml` import and export (§10), round-trip tested.
3. **File ops** (`mona/fileops/`): C7 in full:
   - roots and the move-inside-root guard;
   - the atomic move with its journal entry and crash recovery (the §4.3 table: every row as a test, crashes injected between steps);
   - undo, redo and group undo;
   - live undo state and supersede;
   - the badge;
   - delete to trash;
   - collisions (`-2`, `-3`, …), same document, identical bytes (adopt).
   - **§9 invariants as property tests** (hypothesis): random sequences of file / undo / redo / delete / move leave the archive tree equal to the DB paths, with no strays.
4. **Services** (`mona/services/`), the functions L2's MCP tools and REST endpoints call. Signatures take `actor` and `via` (D5) and return C1 DTOs:
   - `file_document` (used by the pipeline in M2);
   - `correct_document`: C4 §3.5 semantics, including scope "every document like this" → a rule (C5 §4.6.1 priority) and alias learning (§6.2.5);
   - `preview_rule` / `apply_rule` (C4 §3.8/§3.9, with `RulePreview` "Applied" from the group);
   - `undo` (C4 §3.16, including redo);
   - `delete_document` / `restore_document`;
   - deadline creation from a classified document (C1 §6.2: only due dates on or after arrival).

   Keep one module per concern, no web or MCP code here. Write a short `mona/services/README.md` listing each function's signature and the contract section it implements. L2 builds against it.

## Acceptance (fresh output in the report)

- `make check` green; the new tests are in the suite.
- **Mutation checks,** recorded with the failing test's name:
  - the root guard: compare without a trailing `/`;
  - the supersede rule: ignore it;
  - group undo order: forward instead of reverse;
  - collision: the suffix counter off by one;
  - recovery: skip the re-check under the lock;
  - `{fy}`: use the document date instead of `period_end`;
  - file names: keep diacritics;
  - a rule condition: flip `not`;
  - rule priority: tie-break reversed;
  - alias learning: skip the merge;
  - plus every other [M] obligation in C5 §11 and C7 §10 that falls in this milestone.
- The property tests run at least 500 examples in CI mode.
- **Seed:**
  - F0's loader loads `demo/seed` (pre-seeded tier; the overlay from `MONA_SEED_OVERLAY` if present).
  - `apply_rule` over a synthetic set of documents reproduces the C5 §8.5 paths on disk.
  - `undo` restores every file, byte-identical (sha256).

## Don't

- No extraction, OCR, model calls or Procrastinate jobs: that's milestone 2.
- No REST endpoints or MCP tools: that's L2.
- No contract changes. If something is unbuildable or ambiguous, stop that item and report it.
