# L3-S4: Home, Rules, Entities & taxonomy, Settings, states

Card **L3**, screens part 4 (HANDOFF build order steps 6–8). Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l3-s4`, branch `l3-s4`, based on `main`.
- **Ports:** Playwright with `E2E_PORT=6174`. No compose stack is needed (MSW).

Home opens the demo (0:00); Rules shows "what Mona learned today" (10:30); Entities and Settings are desk screens. Build them on the typed C2 data layer and MSW mock (L3-S1/S2 patterns), against the frozen contracts.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D14).
- **Contracts:**
  - C2 §3 (shell and Home: `GET /api/home`, the brief facts), §7 (rules), §8 (registry), §15 (settings and system status), §2.3/§2.5 (lock and unlock, for `/unlock` and auto-lock);
  - C8 §5.6 (the `MonaBrief` templates), §5.7 (auth strings);
  - C1 §11.5, §11.8;
  - C5 §4.7 (`condition_text`), §9 (thresholds: settings);
  - C9 §3, §5.4 (the Privacy section text).
- **Design:**
  - `design/mona-handoff/HANDOFF.md` §3 (Home: `MonaBrief`, `ActionCard` variants, `DateTile`, `Sparkline`, `ChatEntry`; Rules: `RulesTable`/`RuleRow`, `LearnedPanel`; Entities: `EntityCard`, `CategoryTree`, `CategoryEditor`, `TemplateField`; Settings: `SettingsSection`, `ProfileSection`, `StatusTile`, `DataFlowDiagram`; States: `FirstRunChecklist`, `OfflineState`, `EmptyState`, loading skeletons), §4, §5;
  - `design/screens/mona-web-app.pdf` p1 (Unlock), p2 (Home), p14 (Rules), p15 (Entities), p16 (Category editor), p19 (Settings); the HTML canvas States and Mobile (Home at 390).
- **Code:** `apps/web/src/data/` + MSW, the shell (`registerChatEntry` for Home's `ChatEntry`, toasts), `@mona/ui`.
- **Notes:** `~/DevFiles/mona-hq/orchestrator/l3-screens-notes.md`.

## Build

1. **`/unlock`** (p1): password, errors, `next=`, no recovery-key line (cut; HANDOFF §9 open item: the installer resets it). Auto-lock returns here (C2 §2.3).
2. **Home** (p2):
   - `MonaBrief` from the C2 §3.2 facts with C8 §5.6 templates (inline links to sources, the "written at … from N journal entries" caption);
   - `ActionCard` variants (`ReviewQueueCard`, `DueCard` with `DateTile`, `ActivityCard`, `IngestionCard` → the Activity log);
   - `Sparkline`;
   - `ChatEntry` registered for `/`;
   - Home at 390.
3. **Rules** (`/rules`, `/rules/:ruleId`, p14): `RulesTable`/`RuleRow` (name and destination, source chip, fired, last fired, corrections since, on/off) and `LearnedPanel` ("What Mona learned today"). No version history (cut).
4. **Entities & taxonomy** (`/entities`, `/entities/categories/:id`, p15–p16):
   - `EntityCard` (masked IBANs, FY end, sub-units, people, visibility);
   - the Visitors entity shown as such (C2 §8 `visitorsEntityId`);
   - `CategoryTree`;
   - `CategoryEditor` with per-language labels and a `TemplateField` (token chips `{entity} {year} {fy} {category} {sub} {counterparty} {issuer} {reference} {date:…}`, a live preview, 422 on a bad template).
5. **Settings** (`/settings#…`, p19): Profile & lock (name, password, auto-lock), language, thresholds, System status (`StatusTile`s from C2 §15.2), Privacy (`DataFlowDiagram` + the C9 text), About (version from the build). No theme control, no recovery key.
6. **States:** `FirstRunChecklist` (language, entities, archive folder informational, first documents; Telegram is an info row); `OfflineState` ("Mona's brain is offline"); empty states; loading skeletons.

## Acceptance (fresh output in the report)

- `make web-check` green.
- **vitest:** brief rendering from facts in en/fr/ro; `TemplateField` tokens and preview; rule row states; settings validation.
- **Playwright** (`E2E_PORT=6174`, MSW):
  - unlock → Home → `/` focuses `ChatEntry`;
  - Home cards link through;
  - Rules toggles;
  - a category template edit with preview (and the 422 path);
  - Settings thresholds save;
  - auto-lock → `/unlock?next=`;
  - Home at 390;
  - no console errors; axe with 0 serious or critical violations.
- Screenshots of p1, p2, p14, p15, p16 and p19 equivalents at 1440, compared in the report.

## Don't

- No backend code.
- No chat cards (L3-S3).
- No Reports, theme toggle, recovery key or rule history (cut).
