# deploy/

Prod on mona is `compose.yaml` plus `deploy/compose.prod.yaml`: Caddy is the only published port (loopback, `WEB_PORT`, default 8080; reach it through the SSH tunnel), `/mcp` is not routed, no cloud key is in any service, and `hermes-seed` installs `config.prod.yaml` and runs A4/A5 before Hermes starts.

| Path | What |
|---|---|
| `bin/mona` | Host wrapper: `up`, `stop`, `status`, `doctor`, `perf`, `demo-reset`, `demo-snapshot`, `backup`, `restore`; anything else runs in the api image |
| `bin/doctor-host` | Host half of `mona doctor`: GPU, published ports, cloud-key names in containers |
| `bin/deploy` | Build and tag `mona-api` and `mona-web`, start them, run doctor; keeps the last 2 releases; `--rollback` |
| `bin/egress-test`, `bin/egress-analyze` | C9 §2.3 capture and judge |
| `compose.prod.yaml`, `caddy/` | The prod overlay, the web build with Caddy, its Caddyfile |
| `.env.prod.example` | Names the box's `.env` needs |
| `llm/` | llama-swap prod config, the two-lane rollback copy, the compose file that joins the prod network |
| `hermes/` | Hermes profile seeds (dev and prod `config.yaml`) |

## First deploy on the box
1. Copy `.env.prod.example` to `.env` and fill it in. `MONA_PUBLIC_ORIGIN` is the exact address the browser shows.
2. `deploy/bin/deploy`. It builds, starts, and runs `mona doctor`. The model line stays red until llama-swap is up.
3. `deploy/bin/mona seed load /seed`, then `deploy/bin/mona demo-reset --yes`.
4. llama-swap: in `~/llm` put `llama-swap.prod.yaml` and `compose.prod.yaml` (from `deploy/llm/`), set `MONA_NETWORK` to the prod network (`docker network ls`, `<project>_default`), tune `--n-cpu-moe` in the macro, then `docker compose -f compose.prod.yaml up -d`. It is reached as `http://llama-swap:8080/v1` (the value of `MONA_LLM_BASE_URL`) and is published on `127.0.0.1:9292` only.
5. `deploy/bin/mona doctor` all green.

Rollbacks:
- Release: `deploy/bin/deploy --rollback` restores the previous images. Migrations only move forward.
- llama-swap: put `llama-swap.two-lane.yaml` back as `llama-swap.yaml` with the old `compose.yaml`, then `docker compose up -d --force-recreate`; point `MONA_LLM_MODEL` at a lane it serves.

A Hermes volume used in prod holds `config.prod.yaml`. The dev seed installs a config only when none exists, so reset before using the volume in dev: `mona demo-reset` installs the right one for the environment.

## Perf (Oct 8)
`mona perf --batch <folder of the rehearsed live batch> --order <names, one per line> --beats <json of {id, prompt}>` writes `<data>/perf/perf-<time>.md` and `.json`: classification per document, the chat beats cold (llama-swap unloaded first), warm, and during the running batch, llama-swap reloads (polls `/running`), and VRAM sampled with `nvidia-smi` on the host. `--dry-run` writes the skeleton and touches nothing. Batch and beats live in `demo-data/`, never in the repo; the report names documents by `sha256[:12]`. Afterwards `mona demo-reset`: the run leaves a batch and Hermes sessions behind.

## Egress test (Oct 8, prod stack up)
1. `sudo deploy/bin/egress-test --plan` shows the bridge, the subnets and the steps; nothing is captured.
2. `sudo deploy/bin/egress-test --idle 1800`. It starts `tcpdump` on the compose bridge (headers only), runs `mona demo-reset --yes`, then waits while you drive the full demo: drop batch through filing, the debrief, the chat turns (search, sum, deadlines, draft), an accountant export, a photo sent to the owner bot, the 07:30 brief triggered by hand. Press Enter, and it idles 30 minutes so the purge and housekeeping jobs run.
3. It judges the capture. PASS: every destination is `api.telegram.org` (its DNS answers or Telegram's published ranges) or the DNS resolver, and every DNS query is for `api.telegram.org`. With Telegram not live, a capture with no outbound packet passes. The destination list is in `egress-<time>/destinations.txt`; paste it into the L6 report.
4. Re-judge a capture later: `deploy/bin/egress-test --analyze <dir>/capture.txt --internal <compose subnet>`. `--telegram-cidrs <file>` replaces the built-in ranges with a fresh copy of Telegram's list.
5. Optional hardening (decide after Oct 8): an nftables rule that drops and logs forwarded traffic from the Docker bridges to anything but the compose subnets, llama-swap, the resolver and Telegram's ranges; then also assert zero logged drops.
