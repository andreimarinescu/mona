# L3-shell: app shell, routing, language, toasts (HANDOFF build order step 1)

Card **L3**, the shell. Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l3-shell`, branch `l3-shell`, based on `main` (which has `@mona/ui`).
- **Ports:** Playwright with `E2E_PORT=5374`. No compose stack is needed.

The screens come next, after contract C2 (REST) freezes. This card builds everything around them, so each screen later drops into a finished shell. Data comes through a small data-access layer with **stub providers** returning C1 §11 DTO fixtures. When C2 freezes, the stubs are swapped for the generated API client without touching components.

## Read first

- `briefs/common.md` and `docs/decisions.md`.
- `design/mona-handoff/HANDOFF.md`: "v1 demo scope" (the cut list), §2 (routes and the shell), §3 (Shell components), §4 (toasts, language, formatting, theme), §5 (accessibility), §8 step 1.
- `design/screens/mona-web-app.pdf` p2 (Home, for the sidebar); the `.html` canvas "Parts" (Sidebar, MobileTabBar) and "Mobile" pages.
- `packages/ui` (`@mona/ui`: use its components; never restyle them) and `design/mona-design-system/formatting.md`.
- `docs/contracts/C1-domain.md` §11 (DTOs) and `C3-chat-stream.md` §2 (what the chat panel will send; the panel body itself comes later).

## Build

1. **Routes** (TanStack Router): every v1 route in HANDOFF §2 **except `/reports`**, which is cut.
   - Each non-shell page renders a titled placeholder with `EmptyState` until its screen card lands.
   - Keep the dev routes (`/dev/ds`, `/dev/pdf`, `/dev/chat`).
   - `/unlock` renders outside the shell.
2. **Shell:**
   - `AppShell`: `Sidebar` 248 px + the routed page + the `ChatPanel` slot + `ToastRegion`.
   - **`Sidebar`:** logo (handoff assets), `EntityScopeSwitcher` ("Showing: All entities"; filters every screen through app state), the nav, `AskMonaButton` (shows `/`), `UserMenu` (Profile · lock), and `SystemStatusLine` (from `/api/health` now; queue count later).
   - **`MobileTabBar`** below 1024 px: Home, Review, Chat, Archive, More. Rules, Entities, Activity and Settings live under More.
   - **`ChatPanel` frame:** non-modal, 460 px, over the page, `role="complementary"`. Its open state and conversation id live in app state and survive navigation. Its body can mount the existing `/dev/chat` thread for now.
   - The "Mona can see: …" page-context line is produced from each route; this is the `pageContext.summary` C3 sends.
3. **Keyboard and accessibility** (HANDOFF §2, §5):
   - `/` focuses Ask Mona (the Home entry, or it opens the panel), unless focus is in a text field;
   - `Esc` closes the panel and returns focus to whatever opened it;
   - a "Skip to content" link is the first tab stop;
   - a visible focus ring;
   - real elements only.
4. **Language and formatting:**
   - react-i18next with en/fr/ro. The UI language comes from a settings stub (C2 will serve it) and is set on `<html lang>`.
   - All numbers, dates and amounts go through `format` from `@mona/ui`.
   - `data-theme="light"` stays pinned, with no theme control anywhere.
   - **Extend `scripts/i18n-check.mjs`** so plural suffixes follow each locale's CLDR categories (en `one/other`, fr `one/many/other`, ro `one/few/other`) instead of being rejected as unknown keys. Add tests for it.
5. **Toasts** (HANDOFF §4):
   - past tense, grouped ("Filed 12 documents", not 12 toasts), at most 3;
   - an Undo slot kept for ≥ 8 s;
   - danger toasts use `role="alert"` and stay until dismissed;
   - bottom-right, shifting left of the open chat panel.
6. **Data-access layer** (`apps/web/src/data/`): typed hooks (`useEntities`, `useSettings`, `useHealth`, …) over an interface with stub providers holding fictional C1 DTO fixtures. `useHealth` uses the real endpoint. Document the swap point in one line of its README.

## Acceptance (fresh output in the report)

- `make web-check` green; the i18n check tests cover the plural rule, with mutation: reject `_many` again → a test fails.
- **Playwright** (`E2E_PORT=5374 make e2e`):
  - every route reachable from the nav;
  - `/reports` 404s;
  - the panel stays open across navigation;
  - `/` and `Esc` behave as specified;
  - the skip link is first;
  - at 390 px wide the tab bar shows with More holding the four desk screens;
  - no console errors or warnings on any route;
  - basic axe checks (`@axe-core/playwright`) with 0 serious or critical violations.
- vitest for toast grouping (cap 3, undo window) and the page-context line per route.
- Screenshots of Home (placeholder) in the shell at 1440 and at 390 wide, in the report.

## Don't

- No screens beyond placeholders, and no real data other than health.
- No dark theme or `ThemeToggle`.
- No restyling of `@mona/ui` components. Tailwind is for page layout only, on DS tokens.
- Nothing from the cut list (Reports, recovery key, rule version history, scanner/email copy).
