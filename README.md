# Mona

Local-first back-office agent for dental practices: reads the practice's paperwork, files it with a clean name, keeps an undoable journal, asks when unsure, and answers with sources. Nothing leaves the building.

- Plan (canonical): Obsidian vault `mona-hq/specs/mona-mvp-master-plan.md`
- Build kickoff: vault `mona-hq/specs/mona-mvp-kickoff.md`
- Design: `design/` (design system, UI handoff, screen exports)

## Develop

Needs Docker, Node 24 and uv.

- Secrets live in `.env` at the repo root (gitignored; copy `.env.example` and fill it in). Compose reads it; never commit it.
- `npm install` once, then `make up` starts postgres, migrate, api (:8765), the two workers, the Vite dev server (:5173) and Hermes (:8642, API server only). `make down` stops it and keeps the volumes. Set `COMPOSE_PROJECT_NAME` to run a separate stack, and `WEB_PORT`, `API_PORT`, `POSTGRES_PORT`, `HERMES_PORT` to move the host ports.
- Hermes gets only the variables it needs, by name. Its profile lives in the `hermes_data` volume, seeded from `deploy/hermes/` (`config.yaml`, `SOUL.md`, the `mona_prompt` plugin) on every start; memories and sessions stay. The api serves the MCP tools at `/mcp` behind `MONA_SERVICE_KEY`.
- `make check` runs the web checks (lint, typecheck, vitest, i18n check, API client freshness, build) and the Python checks (ruff, pytest against the compose postgres, database `mona_test`), as CI does.
- `make ci-py` runs the Python checks the way the CI job does: against a throwaway postgres:17, with `CI` and `GITHUB_ACTIONS` set (so the Hypothesis CI profile runs) and the private seed overlay hidden. Run it before a sitting when Python tests or CI changed.
- `make e2e` runs the Playwright specs against a Vite dev server on :5174 (`PLAYWRIGHT_SKIP_BROWSER_GC=1 npx -w apps/web playwright install chromium` once; the flag keeps browsers other projects use). The live chat spec needs the stack with Hermes: `E2E_BASE_URL=http://127.0.0.1:5173 MONA_LIVE=1 make e2e`.
- After an API change: `cd apps/api && uv run mona openapi`, then `npm run gen:api -w apps/web`, and commit both files.
- pdf.js is vendored with `scripts/vendor-pdfjs.sh <version>`; the sample PDF under `apps/web/public/dev/` is synthetic (`uv run scripts/make-sample-pdf.py`).
