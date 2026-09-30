# Decisions

Newest first. Lanes re-read this file at every commit boundary; an entry binds even if you never saw the message that announced it.

## D4 · 2026-09-30 · W0 spike results folded into dev config (S5, S6)

- **OpenRouter pins (dev).** Direct requests (pydantic-ai sub-tasks) send `provider: {order: [akashml, coreweave, siliconflow, parasail, deepinfra], allow_fallbacks: false, require_parameters: true, quantizations: [fp8, fp16, bf16]}`. Hermes has no `allow_fallbacks`/`quantizations` keys, so `deploy/hermes/config.yaml` uses `provider_routing.only` + `order` + `require_parameters`, which keeps the same five fp8+ providers. CoreWeave and SiliconFlow lack tool support, and `require_parameters` skips them on Hermes turns.
- **Thinking off:** `reasoning: {enabled: false}` on OpenRouter; per-request `chat_template_kwargs: {"enable_thinking": false}` on llama-server. Typed outputs support both. Typed outputs never run with thinking on (S6 reproduced P0-3).
- **Hermes session titles must be unique:** the adapter titles a Hermes session with our conversation id (C3 amendment at the set A fold).
- **Profile seeding:** `deploy/hermes/` seeds the `hermes_data` volume on first start only. After editing it, reseed with `docker compose down -v` or a targeted volume reset. `mona demo-reset` (L5b) owns this in the demo.
- **Dev secrets:** `HERMES_API_KEY` was rotated on 2026-09-30 after it appeared in a lane's tool output. Lanes print `docker compose config` only through a filter.

## D3 · 2026-09-30 · Hermes integration facts from S1/S2 (details: `docs/spikes/s1/README.md`)

- **Image.** Hermes 0.21.5 is `nousresearch/hermes-agent:v2026.9.24@sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7`; there is no `0.21.5` tag. The profile is the `/opt/data` volume; start the image with `gateway run` under its own entrypoint.
- **Adapter path.** The HermesEngine adapter uses `POST /v1/chat/completions` with `X-Hermes-Session-Id`. It's the only path that streams reasoning live (`delta.reasoning_content`). Tool lifecycle comes from `event: hermes.tool.progress`.
- **Overlays.** The page-context line and the card-action notes are sent as `system` messages in that request; Hermes applies them as the turn's ephemeral system prompt. The overlay also names the reply language.
- **Cards.** No stream path carries tool results, so cards come only from `card_events` (C1/C3).
- **Networking.** Every service runs on the compose network; the laptop's ufw drops container → host traffic.
- **Egress.** Hermes ingests `OPENROUTER_API_KEY` from its environment into a credential pool regardless of config. The prod assertion (C9) checks that the key is absent from the Hermes container env and from `$HERMES_HOME/.env`.

## D2 · 2026-09-30 · Operator rulings at W0 start

- Signing sittings happen at each gate: Hermes go/no-go, contract set A verdict, set B verdict, then each milestone. The orchestrator announces the batch; Andrei folds, signs and pushes.
- L5 starts now, alongside W0. Seed and fixtures get re-keyed when C1/C5 freeze.
- The five derived logo files in `design/mona-handoff/assets/` are checked and approved.
- Telegram (S4, owner bot) stays deferred to a later testing session; no gateway or bot in W0.

## D1 · 2026-09-30 · W0 toolchain, layout and working conventions

- **Monorepo.** npm workspaces for the web side (`apps/web`, later `packages/ui`). One uv project in `apps/api` (Python package `mona`) holds the API, the MCP server and the Procrastinate jobs. The workers run from the same image with a different command, so the top-level `worker/` directory goes away.
- **Python.** 3.12, FastAPI, pydantic v2, SQLAlchemy 2 (async, psycopg 3) + Alembic, Procrastinate 3.x, pydantic-ai, FastMCP; ruff (lint + format) and pytest. One Python image carries the OCR tooling (ocrmypdf, tesseract fra/eng/ron, poppler-utils, img2pdf).
- **Web.** Vite + React 19 + TypeScript (strict), TanStack Router + Query, react-i18next, Tailwind v4 without preflight, vitest, eslint. assistant-ui + `ai` arrive with S5/L3.
- **Compose.** `compose.yaml`, dev profile: `postgres:17`, `api`, `worker-llm` (queue `llm`, concurrency 1), `worker-cpu` (queue `cpu`, concurrency 3), `web` (Vite dev server, proxies `/api` and `/mcp` to the api), `hermes` (added by S1). Data under `./data` (gitignored), mounted at `/data`. Host ports come from env with defaults: web 5173, api 8765, postgres 55432, hermes 8642. Caddy is L6 (prod).
- **CI.** GitHub Actions on push and PR: `web` (lint, typecheck, test, i18n missing-key check, build) and `py` (ruff check, ruff format --check, pytest against a postgres service). `make check` runs the same locally.
- **Private data.** Everything derived from practice documents lives in `~/DevFiles/mona-hq/demo-data/`, never in the repo or the vault. Repo fixtures are synthetic; repo docs refer to practice documents by `sha256[:12]`. Identifiers used by the seed (IBANs, SIRENs, addresses) sit in a local overlay there, not in the committed seed.
- **Git.** Lanes work in `~/DevFiles/mona-hq/.worktrees/<card>` on a branch named after the card. The orchestrator rebases lane branches onto `main` and fast-forwards, keeping history linear for the fold-and-sign at gates.
- **Reports.** `~/DevFiles/mona-hq/orchestrator/reports/<card>-report.md`, mirrored to vault `mona-hq/audits/` without document names.
