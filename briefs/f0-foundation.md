# F0: schema, models, DTOs and seed loader (the base for L1 and L2)

Card **F0**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/f0-foundation`, branch `f0-foundation`, based on `main`.
- **Compose project:** `-p mona-f0`.

L1 (pipeline and filing) and L2 (API, MCP, adapter) launch in parallel as soon as this lands, and both build on it. Keep it exact and small: this card is the shared layer, not features.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D7).
- **`docs/contracts/C1-domain.md` (frozen v1.0), in full.** Its SQL is normative.
- `docs/contracts/C5-classification.md` §2 (`norm()`), §4 (rule grammar), §10 (`rules.yaml` schema).
- `docs/contracts/C7-file-ops.md` §2 (journal fields).
- `docs/contracts/amendments.md`.
- The scaffold: `apps/api/src/mona/` (settings, migrations 0001, jobs) and the S5 spike tables (`spike_*`), which stay until L2 replaces them.

## Build

1. **Migration `0002`**: exactly C1's schema. Every table, constraint, index, the `mona` text-search config and the extensions. Downgrade drops it all.
2. **Schema parity test [M]**:
   - Apply C1's `sql` blocks, extracted from the contract file at test time, to one scratch database.
   - Migrate another to head.
   - Compare the normalised `pg_dump --schema-only` of the two (ignoring `alembic_version`, `procrastinate_*` and `spike_*`). They must be identical.
   - This is the guarantee that the migration is the contract.
3. **SQLAlchemy 2 models** (`mona/db/`) for every C1 table: typed `Mapped[]`, relationships only where L1/L2 obviously need them.
   - An autogenerate-diff test: models vs the migrated DB → no difference.
   - Async session factory, plus a sync one for Procrastinate jobs if needed.
4. **Shared helpers C1 names** (pure functions, fully tested):
   - prefixed ULID ids (C1 §1);
   - `norm()` per C5 §2, with all the C5 §2 test vectors;
   - the IBAN HMAC + last-4 helper (key from settings: add `MONA_IBAN_PEPPER` to settings and `.env.example`; the orchestrator already put a dev value in `.env`);
   - snake ↔ camel DTO aliasing (C1 §1.1).
5. **Pydantic DTOs** (`mona/dto/`) for every C1 §11 type, with camelCase aliases, validators for the enums (DS `Category`, `DocStatus`, `Reason`, `FieldKey`), and the RuleDraft branch shape per C1 §11.5. These become C2's response models.
6. **Seed loader** `mona seed load <dir> [--tier preseeded|all]`:
   - Reads `practice.yaml` + `rules.yaml` (C5 §10 schema) plus an optional private identifiers overlay (path from `MONA_SEED_OVERLAY`).
   - Enforces C1 §9's seed invariants and is idempotent: loading twice leaves the same state.
   - Test it against a **synthetic** seed fixture in `apps/api/tests/fixtures/seed/`, covering every invariant with a failing case.
   - L5b produces the real seed in parallel and runs your loader.

## Acceptance (fresh output in the report)

- `docker compose -p mona-f0 up -d --build` → `migrate` exits 0 at head.
- Schema parity test green; mutation: drop one index from the migration → red.
- Autogenerate diff empty.
- Helper tests green, including every C5 §2 vector; mutation: drop the ș/ş fold from `norm()` → red.
- DTO tests: every DTO round-trips a sample and rejects a bad enum.
- Seed loader: a synthetic seed loads twice with an identical DB (compare dumps), and every C1 §9 invariant's failing fixture is rejected with the invariant named.
- `make check` green. Tear down (`down`, keep volumes).

## Don't

- No REST endpoints, MCP tools, pipeline jobs or file ops: those are L1/L2.
- No contract changes. If C1 is wrong or unbuildable, stop that item and report it; the orchestrator amends.
- No real practice data in fixtures.
