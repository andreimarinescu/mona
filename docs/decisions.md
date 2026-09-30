# Decisions

Newest first. Lanes re-read this file at every commit boundary; an entry binds even if you never saw the message that announced it.

## D13 · 2026-10-01 · Overnight autonomy (operator ruling)

- While Andrei is away, the orchestrator verifies and merges finished lanes and launches the queued cards (vault resume point) within the lane limits (3 heavy + 1 light). This lifts the kickoff's "operator present for new launches" rule for these unattended stretches.
- **Not without Andrei:**
  - signing and pushing (the next sitting waits for him);
  - contract verdicts;
  - anything the standing rules call important.
  Those are batched as questions for his return, and work that depends on them is held.
- Every launch and merge is logged in the vault resume point, so a compaction loses nothing.

## D12 · 2026-10-01 · Mona is practice-agnostic (operator question)

- **Only in seed data.** Practice-specific content (entity, person and counterparty names such as AGIPI, TALENZ or Hello bank; addresses; example suppliers) lives only in seed data (`demo/seed/`, the private overlay, test fixtures) and in docs and tests as examples. It never appears in application code, prompts, tool descriptions or the committed Hermes profile.
- **Model-facing text is generic.** Tool descriptions and prompts use neutral examples ("a supplier, insurer, bank or public body"). Practice examples reach the model only through registry data (`categories.model_definition`, counterparties, rules).
- **Hermes memory seeds are generated.** `deploy/hermes/memories/` is rendered from the loaded practice registry at seed/reset time, not hand-written. Until then the committed files are the demo practice's and are listed as such.
- **Guard.** A check reads every entity, person and counterparty name and alias from `demo/seed/practice.yaml` and fails if any appears in `apps/*/src`, `packages/`, or `deploy/hermes/` outside `memories/`. It runs in `make check`.
- **Carried by:**
  - L2 fixes the "e.g. AGIPI" hint in `mona/mcp/filters.py`;
  - L5c generates the memory seeds;
  - the guard lands with the next lane that touches `scripts/`.

## D11 · 2026-10-01 · Parallel-lane ownership on the api

- **Migrations:** only L2 adds Alembic migrations (next: `0005`, auth sessions + A9). Every other lane (L1-M2, L4, L1-M3) adds none. A needed index or column goes in the lane's report, and the orchestrator routes it.
- **Routers:** each lane keeps its routes in its own module (`mona/api/<area>.py`, `mona/interviews/api.py`, …) and adds one `include_router` line in the app factory, so merges stay one-line conflicts.
- **Model client:** L1-M2's model client module is the one client (C9 §1.2 "one LLM client"). L2-P2 adds the prod fail-closed guard to it; L4 calls it, never a second client.
- **Shared test fixtures** (`apps/api/tests/conftest.py`): add fixtures with lane-specific names (`<lane>_…`) to avoid clashes like the L1/L2 `seeded_template` collision.

## D10 · 2026-10-01 · Contract set B frozen at v1.0 (Andrei's verdict)

- C2, C6, C8 and C9 are frozen at 1.0. Amendments A7 and A9–A11 amend set A; changes now go only through `amendments.md`.
- **Stage privacy line:** "the document and everything Mona derived from it are deleted after 24 hours" (C9 §5.4). The stage instance is a throwaway database.
- **Stage fallback networking** (a laptop stack the presenter's phone connects to) is Andrei's call on site. No lane builds or documents it beyond the loopback default.
- **Lanes unblocked:** L2-P2 (REST, write tools, auth), L3 screens, L4 (interviews, deadlines, drafts, export), L1-M3 (the set B hooks, the Visitors purge, apply-group rule revert, A7/A10).

## D9 · 2026-09-30 · Cheap model for tests; Qwen 3.6 only for quality runs (operator request)

- **Test model:** `qwen/qwen3.7-flash` on OpenRouter (Alibaba). It costs $0.03/M prompt and $0.13/M completion, against Qwen 3.6's $0.15/$1.00. It streams `reasoning_content`, calls tools, honours json_schema, and `reasoning.enabled=false` gives 0 reasoning tokens (probed 2026-09-30). **Every dev and test run uses it by default:** unit and integration tests that reach a model, e2e including `MONA_LIVE=1`, and lane smoke runs.
- **Qwen 3.6 (`qwen/qwen3.6-35b-a3b`, D4 pins) only for quality runs,** where the output itself is the evidence:
  - classification or evidence accuracy on real documents (L5c histogram, acceptance cases);
  - debrief quality;
  - timing measurements;
  - rehearsals.

  Lanes name the quality runs in their reports.
- **Free models are out:** `:free` endpoints are rate-limited upstream (429 on the first call) and may retain prompts. Practice documents never go to a `:free` endpoint.
- **Switching:**
  - Hermes: `deploy/hermes/config.yaml` sets `model.default: "${MONA_CHAT_MODEL}"`. Hermes expands `${VAR}` in any string but has no default syntax, so compose passes `MONA_CHAT_MODEL: ${MONA_CHAT_MODEL:-qwen/qwen3.7-flash}` to the Hermes service.
  - The D4 provider pins move under `provider_routing.models."qwen/qwen3.6-35b-a3b"` (per-model overrides), so the flash model routes to its only provider.
  - Direct model calls (pydantic-ai sub-tasks) read `MONA_LLM_MODEL` with the same default.
  - Prod (llama-server) is unaffected (C9).
- **Spend:** reports that ran models include the OpenRouter usage delta (`GET https://openrouter.ai/api/v1/key` → `data.usage`). Total at D9: $0.46.

## D8 · 2026-09-30 · Set A amendments A2–A6 (from the set B draft)

- Set A is amended by A2–A6 in `docs/contracts/amendments.md`:
  - A2: Visitors documents are never rule candidates;
  - A3: the "ask me each time" answer shape;
  - A4: the activating rule change joins the apply group;
  - A5: the `ses` id prefix;
  - A6: Romanian titles use comma-below.
- **Running lanes read the main checkout's copy** (`~/DevFiles/mona-hq/mona/docs/contracts/amendments.md`) at every commit boundary. It wins over the frozen text it amends.
- The Romanian `condition_text` wording (W1-B P2) will be A7, when set B freezes, since its table lives in C8 §8.

## D7 · 2026-09-30 · Contract set A frozen at v1.0 (Andrei's verdict)

- C1, C3 (shape), C4, C5 and C7 are frozen at 1.0 in `docs/contracts/`. Changes now go only through `amendments.md`.
- **Gate trail:** the drafts, the review findings (`~/DevFiles/mona-hq/orchestrator/review/w1a-gate-findings.md`), the fold report and the verification pass. Summary in vault `mona-hq/audits/`.
- **Product behaviour settled by the set:**
  - Delete goes to trash and is undoable.
  - Only due dates on or after arrival become deadlines.
  - Sub-units (person splits) come only from rules.
  - New `health` category.
  - The transcript is served from our `chat_turns`, not from Hermes.
  - Model-output cache: whether it's on during the stage run is decided after the Oct 8 mona timings (demo script v2).
- **Lanes unblocked:** L1 (pipeline and filing), L2 (API, MCP, adapter). L3/L4 wait for set B (C2, C6, C8, C9).

## D6 · 2026-09-30 · Signing sittings run by the orchestrator (operator request)

- **Who runs it.** The orchestrator signs and pushes at each gate (D2 cadence) with `tools/sitting.sh [<branch>]`, the Mona port of the pilot-protocol system:
  - a zenity question first: the commit list and the number of PIN + touch prompts. Declining changes nothing.
  - then one GitHub SSH master (a single PIN + touch for fetch and push);
  - then `tools/resign-branch.sh`: a two-pass fold-then-sign with tree, signature and identity checks. The unsigned tip is kept at `refs/archive/unsigned/<branch>`;
  - then push and verify.
- **Missed PINs.**
  - `~/.local/bin/git-ssh-sign` retries each signature up to 3 times.
  - `sitting.sh` offers up to 3 attempts per step (connect, sign, push). Each retry dialog reminds the operator that 3 wrong PINs in a row lock the key until it's re-plugged.
  - A fixup-fold conflict stops without a retry.
- **Before a sitting,** the orchestrator folds lane commits into one commit per card (tree-identical), to keep the signature count low.
- **After a sitting,** active lane branches move with `git rebase --onto <branch> refs/archive/unsigned/<branch> <lane>`. The archive is then dropped with `tools/resign-branch.sh --drop-archive <branch>`.
- **Republish:** if unsigned commits reach `origin` (for example a manual push), the next sitting runs `tools/sitting.sh --from <last signed commit on origin>`. That re-signs everything above it and force-pushes with a lease; the permission dialog names the rewritten commits.
- **Lanes** never push. The orchestrator uses GitHub freely; SSH calls to the private repo ask for a FIDO touch through zenity, which is expected (operator, 2026-09-30).

## D5 · 2026-09-30 · Operator rulings at the Hermes go/no-go (gate 0)

- **Hermes: go.** Hermes 0.21.5 stays the one Mona brain (R19). The pydantic-ai chat engine stays cut. Evidence: S1, S2, S5 and S6 (`docs/spikes/`).
- **Demo toolsets:** `platform_toolsets.api_server: [memory, mona]`. `skills` and `todo` are off for the demo, saving about 3k prompt tokens per call. Hermes skills (self-improving, trimmed catalog) come back after the demo, since Mona is meant to become a general agent. Roadmap item.
- **Journal actor = who executed** (amends plan §9 / HANDOFF §6 "Telegram owner actions count as user"):
  - Anything done through Mona's tools, whether from chat, Telegram or cron, is `mona`, tagged with the channel.
  - Only direct actions in the web UI (clicks, card buttons, forms) are `user`.
  - The Activity log's "by you" therefore means "done by you in the app".
- **Stub files:** the 12 text-only corpus stubs stay replaced by synthetic fillers. Real PDFs can replace them later without contract changes.

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
