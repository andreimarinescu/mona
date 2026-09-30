# L3-DS: port the Mona design system to TSX (`packages/ui`)

Card **L3**, the design-system port (plan §9, §12b P1-7). Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l3-ds-port`, branch `l3-ds-port`, based on `main`.
- **Ports:** Playwright runs with `E2E_PORT=5274`. Don't start the compose stack; this card needs none.

The screens (the rest of L3, launching after contract set B freezes) import components from here. Until this lands they use the bundle shim (`apps/web/src/ds/`). The goal is **identical output**: same DOM, same class names, same behaviour. `bundle.css` keeps styling everything.

## Read first

- `briefs/common.md` and `docs/decisions.md`.
- The design system:
  - `design/mona-design-system/README.md`, `formatting.md`, `voice-and-tone.md`;
  - `components/bundle.js` (the source you port), `components/index.d.ts` (**the API contract**), `components/bundle.css`.
- `design/mona-handoff/HANDOFF.md` §3 (component names; `ReasonChip`), §5 (accessibility), §9 (the 16 icons in `assets/icons/`, `ReasonChip`). The component sheet is on the "Parts" page of `design/screens/mona-web-app.html`: open it in a headless browser to see `ReasonChip`.
- The scaffold: `apps/web/src/ds/` (the shim), `/dev/ds`, `e2e/ds.spec.ts`, `vitest` setup.

## Build

1. **`packages/ui`**, npm workspace `@mona/ui`, TSX, React 19, strict TS.
   - One module per component family; `index.ts` exports every component in `index.d.ts`, plus `format` and `i18n`.
   - Import `bundle.css` from the package entry, so the load order stays: tokens → `bundle.css` → app.
2. **Type conformance:** a type-level test asserts each export is assignable to its `index.d.ts` declaration (e.g. `const _b: typeof Contract.Button = Button`). `tsc` fails on any drift.
3. **Behaviour and markup parity [M]**, the acceptance core. A vitest suite renders a matrix of props for every component through **both** the shim (`window.Mona.X`) and the port, then compares the normalised HTML.
   - Normalisation strips generated ids; compare with `useId` values mapped.
   - Interactive components (Dialog, Menu, Popover, Tabs, Combobox, Toast, Drawer, Tooltip, Accordion, RadioGroup, SegmentedControl, Switch) get interaction steps in both versions, with the resulting markup compared.
   - Mutation: change one class name in the port → a parity test fails.
4. **`Mona.format`:** a typed port with tests from `formatting.md` (EN/FR/RO money, percent, dates, relative time; U+00A0 in French).
5. **Extensions** (plan §9, §12b):
   - `ConfidenceMeter` gets an optional `thresholds` prop. Defaults equal the bundle's behaviour; a test shows custom thresholds change the band.
   - `Icon` gains the 16 icons in `design/mona-handoff/assets/icons/`.
   - New **`ReasonChip`** (`low` · `entity` · `conflict` · `unreadable`): icon, word, outline pattern (solid, dashed, double, hatched) and tint, per HANDOFF §3 and the Parts sheet. Add its CSS in `packages/ui/src/reason-chip.css`, using tokens only. Words come from `i18n` in EN/FR/RO.
6. **Swap:** `apps/web` imports from `@mona/ui`. The shim stays only for the parity tests. `/dev/ds` renders from the port, and `e2e/ds.spec.ts` (no console errors or warnings) passes on it. Add `ReasonChip` and the new icons to `/dev/ds`.

## Acceptance (fresh output in the report)

- `make web-check` green (`tsc` includes the type-conformance test).
- The parity suite is green across the whole component set; list the matrix size.
- `E2E_PORT=5274 make e2e` green.
- Mutation checks: a class-name change → parity red; a prop type change → `tsc` red.
- A screenshot of `/dev/ds` from the port, in the report.

## Don't

- No screens.
- No restyling: identical output is the point. If the bundle has a bug, keep it and list it in the report.
- No dark theme: `data-theme="light"` stays pinned.
