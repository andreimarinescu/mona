# L6: `mona doctor`, prod deploy, llama-swap prod config, perf and egress scripts, runbook

Card **L6** (plan §6.3 L6). Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l6`, branch `l6`, based on `main`.
- **Compose project:** `-p mona-l6`. Export `WEB_PORT=6473 API_PORT=9765 POSTGRES_PORT=56432 HERMES_PORT=9642` (never edit `.env`).

The mona box (RTX 5060 Ti 16 GB, sm_120) returns around Oct 7, and integration on it runs Oct 8–10. This card prepares everything to run there on day one, and proves what it can on the laptop dev stack. **No SSH to mona and no changes on it**: Andrei opens access when it's back.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D14).
- `docs/contracts/C9-privacy-ops.md`:
  - §1 environments and egress;
  - §2 the prod assertion and the egress test (§2.3);
  - §4 the Hermes lockdown and network exposure (§4.3: `/mcp` never on the proxy);
  - §6 the demo snapshot and reset, already built in `apps/api/src/mona/demo/` and `deploy/bin/mona`;
  - §7 secrets and logs.
- `docs/contracts/C2-rest-api.md` §15.2 (system status reads llama-swap `/v1/models` and the upstream `/props`).
- **The plan** `~/Obsidian/dev-docs/mona-hq/specs/mona-mvp-master-plan.md`:
  - §3 "mona LLM config": one 35B llama-server, `-c 131072 --parallel 2`, `context_length` 65536, no 4B in the agent swap group, no mmproj, retune `--n-cpu-moe`, keep the current two-lane config as the rollback;
  - §6.4 schedule;
  - §10c / `docs/demo-script.md`;
  - §14 perf and privacy verification.
- **Existing LLM stack files** (read-only): `~/DevFiles/mona-hq/llm/llama-swap.yaml`, `~/DevFiles/mona-hq/llm/Dockerfile`, `~/DevFiles/mona-hq/llm/download-pinned.sh`; vault notes `~/Obsidian/dev-docs/mona-hq/llm-stack-handoff.md` and `local-fallback-env.md` (the post-maintenance checklist).
- **Notes:** `~/DevFiles/mona-hq/orchestrator/l6-notes.md`.

## Build

1. **`mona doctor`** (CLI + `deploy/bin/mona doctor`): one line per check, green/amber/red, exit code ≠ 0 on red. Checks:
   - Postgres;
   - migrations at head;
   - the Procrastinate queues (`llm`/`cpu` depth, stalled jobs);
   - Hermes health and its toolsets;
   - the model endpoint (llama-swap `/v1/models`, upstream `/props` slots and context; on dev, OpenRouter reachability);
   - GPU (via the llama-swap metrics or `nvidia-smi` through the wrapper);
   - disk free on `/data`;
   - documents with `missing_file` (L1-M1);
   - purge failures (L1-M3);
   - `MONA_PUBLIC_ORIGIN` set and well-formed;
   - in prod, `mona check-prod` (the C9 §2.1 assertion).

   Telegram shows "not configured" (deferred). Tests run against the dev stack.
2. **Prod deploy:**
   - `deploy/compose.prod.yaml` overlay: Caddy in front with `/api` and the web served, `/mcp` not routed (C9 §4.3), restart policies, `MONA_ENV=prod`, the prod Hermes config, **no `OPENROUTER_API_KEY` anywhere in the Hermes or api env**, the A13 mounts, the non-root users;
   - `deploy/bin/deploy` (build and tag images, keep the last 2 tags, `--rollback`);
   - a `deploy/.env.prod.example` that lists what the box's `.env` needs (no values).
   - Prove on the laptop with `MONA_ENV=prod` where possible (`check-prod` passes, Hermes healthy with no cloud key; the model calls will fail closed without llama-swap, as they should).
3. **llama-swap prod config** `deploy/llm/llama-swap.prod.yaml`: one 35B server per plan §3 (`-c 131072 --parallel 2`, per-request thinking toggle supported, no mmproj, the 4B outside the agent group or removed, an `--n-cpu-moe` placeholder with a note to tune on Oct 8), plus the rollback copy of the current two-lane config. No model downloads.
4. **`mona perf`** (for Oct 8, dry-run on the laptop): the per-document classification time over the rehearsed live batch, cold/warm time to first reasoning and first text for the 4 chat beats, chat during a running batch (criterion 4: ≤ 10 s, no llama-swap reload), and VRAM headroom. It writes a report file and never sends practice text anywhere but the configured model endpoint.
5. **Egress test** (C9 §2.3, plan §0 criterion 5) as `deploy/bin/egress-test`: run a full demo pass while capturing outbound connections (tcpdump or nft counters on the host); pass = only allowed destinations (Telegram's API once it's live; none for now). Document the run steps; it runs on mona on Oct 8.
6. **Runbook** `docs/runbook.md` (EN) + `docs/runbook.fr.md` (FR), one page each, laminated-card style, for Claudiu:
   - start and stop, `mona doctor`, `demo-reset --anchor today`, the warm-up turn;
   - what to do if Mona is offline (the beats' fallbacks from `docs/demo-script.md`);
   - the URL to open (it must equal `MONA_PUBLIC_ORIGIN`);
   - the stage privacy line (C9 §5.4);
   - who to call.

   No practice data. Mirror to vault `mona-hq/reference/mona-runbook.md` only if you can write there; otherwise the orchestrator does it.

## Acceptance (fresh output in the report)

- `make check` green.
- `mona doctor` on the dev stack: all green, then red on purpose (stop Postgres; stop Hermes), with the right exit codes.
- The prod overlay up on the laptop with `MONA_ENV=prod`: `check-prod` green, and `docker compose config` (filtered, no secrets printed) shows no OpenRouter key in api/hermes/worker env and no `/mcp` route in the Caddyfile.
- `mona perf --dry-run` produces a report skeleton.
- The runbooks exist and fit on one page each (word count in the report).

## Don't

- No SSH to mona, no model downloads, no changes outside the repo (the existing `~/DevFiles/mona-hq/llm/` files are read-only).
- No product changes.
- Never edit `.env`.
