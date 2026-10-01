# Data access

Components read through hooks; once the generated client lands, only this folder changes.

- `dto.ts`: the C1 §11 and C2 DTOs, typed by hand.
- `http.ts`: `fetch` with the C2 error envelope (`ApiError`) and the session CSRF header on writes.
- `intake.ts`, `review.ts`, `journal.ts`, `registry.ts`: the C2 §5, §6, §9 and §8 calls and their hooks. Undo and redo run through `useUndoRunner`, which toasts and refreshes.
- `archive.ts`, `exports.ts`, `reminders.ts`, `calendar.ts`: the C2 §4.1 and §4.5 reads (facet filters to the query, the route's search params, folder listings), the §12 export preview and pack (polled), the §10 reminders, and calendar dates as local days (C8 §6.2).
- `polling.ts`: the C2 §1.5 rules, pure, so they can be tested.
- `providers.ts`: the shell's entities, settings, counts and health, all from C2 (`/api/entities`, `/api/settings`, `/api/shell`, `/api/health`).
- `rules.ts`, `home.ts`, `settings.ts`, `auth.ts`, `template.ts`: the §7 rules and learned list, `GET /api/home`, settings (with the §15.1 limits checked on the client too) and system status, the lock (`/api/auth/*`, the heartbeat, `safeNext`), and the C5 §8 template grammar the category editor uses for its chips.
- `http.ts` also tells the app when a call answers 401 `unauthenticated` or 423 (`setAuthLostHandler`); `AuthWatcher` sends the person to `/unlock?next=`.

## Mock API

`src/mocks` serves the C2 endpoints the screens use from an in-memory world (seeded review queue, journal, rules, registry, settings and lock state; uploads advance through the pipeline over time). Vitest mounts it with `msw/node` (`src/test/mockApi.tsx`). In the dev server, set `localStorage['mona.msw'] = '1'` (and optionally `mona.msw.step`, milliseconds per pipeline step; `mona.msw.locked` = '1' starts locked, `mona.msw.autoLock` sets the minutes, `mona.msw.seed` = '0' starts empty, `mona.msw.brain` = 'offline', `mona.msw.locale`) and reload; the world lives in the page and resets on reload.
