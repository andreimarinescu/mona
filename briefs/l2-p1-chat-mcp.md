# L2-P1: chat adapter, MCP server, read tools, Hermes profile

Card **L2**, phase 1 (plan §6.3 L2). Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l2-p1`, branch `l2-p1`, based on `main` (which includes F0).
- **Compose project:** `-p mona-l2`, with default ports (5173 / 8765 / 55432 / 8642).

Phase 1 turns the S5 spike into the real chat path and stands up the MCP server with the tools that only read the database. Phase 2 comes after C2 freezes and L1's services land: the REST API, the write tools, `ingest_attachment` and auth.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D7; D3 Hermes facts, D4 pins, D5 toolsets and actor).
- The frozen contracts:
  - **C3 in full;**
  - **C4 §1, §2, §3.1–§3.4, §3.10, §3.15, §4.1, §4.3, §5;**
  - C1 §7 (chat tables), §11 (DTOs), §6.2 (deadlines, for `list_deadlines`), §8 (settings).
- The S5 spike on `main`: `apps/api/src/mona/chat/`, the spike MCP, `/dev/chat`, `docs/spikes/s5/`. Replace its `spike_*` tables and in-process stores with the C1 tables, and drop the spike migration.
- `deploy/hermes/` (dev config, SOUL.md), `docs/spikes/s1/README.md` (the key map), `docs/demo-script.md` (the chat beats).


## Integration notes (from F0, 2026-09-30)

- **Run checks with your own project:** `make check COMPOSE="docker compose -p <your project>"`, with your ports exported (`POSTGRES_PORT` etc.). Plain `make check` would start the default project. Run `npm ci` in your worktree before any `compose up`, so compose can't create a root-owned `node_modules`.
- **Migrations:** C1's schema is migration `0003`. The S5 spike tables are `0002`. Only L2 adds a migration in this wave: `0004` drops the `spike_*` tables. L1 adds none. If you need an index, name it in your report.
- **Amendment A1:** the IBAN salt lives in `settings.iban_salt`, created by the seed loader. Read it from settings, never from env.

## Build

1. **Chat adapter** (C3):
   - `POST /api/chat` with the turn lease (§5.1);
   - the Hermes session = conversation id (§4.1);
   - the overlay (§4.2): page context, reply language, pending notes;
   - event mapping (§4.3) and errors, including the in-band `agent_error` (§4.4);
   - tool labels (§4.5; EN strings now, FR/RO keys follow C8);
   - card emission (§5.3) and reconciliation at finish (§5.4);
   - card payloads (§5.5) from C1 DTOs;
   - note lifecycle (§6);
   - conversations list and transcript reload from `chat_turns` (§7).
   - Timeouts per C3.
2. **MCP server** (C4 §1–§2):
   - FastMCP at `/mcp` behind `MONA_SERVICE_KEY`, with the channel from `X-Mona-Channel` (§1.2);
   - naming, results as ids plus facts (§2.2), size caps and pagination (§2.3), the error envelope (§2.4);
   - `card_events` writing with `card_ref`s (§2.5);
   - the visibility filter point (§2.6): on the Telegram channel, personal entities are hidden until C9 says more;
   - the time budget (§2.8).
3. **Read tools:** `search_documents`, `get_document`, `sum_amounts`, `list_review_queue`, `list_deadlines`, `get_brief` (stateless, 24 h default). DB only, exactly per C4 §3.
4. **Hermes profile** (C4 §1.3, §4.2):
   - `deploy/hermes/config.yaml`: `api_server: [memory, mona]`, `telegram: [memory, mona_tg]`, `cron: [mona_tg]`, and the two MCP server entries with their `X-Mona-Channel` headers; resources, prompts and sampling off; the D4 provider routing in dev.
   - The seeded profile ships empty `cache/documents/` and `cache/images/`.
   - The api mounts `/opt/data/cache` read-only through a volume subpath. Prove it starts on a **fresh** `hermes_data` volume.
   - SOUL.md (approved) and memory seeds (plan §10: owner name and register, the entities, the accountant, "amounts and due dates first") in the format Hermes 0.21.5 reads. Check its memory file layout in the pinned image.
5. **Web `/dev/chat`**, kept as the dev harness: it now talks to the real adapter and renders `data-doc` / `data-deadline` cards from the real tools. The final chat UI is L3's.

## Acceptance (fresh output in the report)

- `make check` green.
- **C3 §8 tests** that fall in this phase:
  - the golden mapping [M];
  - protocol validity;
  - errors, including the in-band failure fixture;
  - the lease and attribution;
  - reconciliation;
  - notes;
  - transcript reload.
- **C4 §5 tests** for the server, conventions, caps and the six read tools; the visibility filter on the Telegram channel [M].
- **Live e2e** (`MONA_LIVE=1`), on the dev stack with F0's loader loading the synthetic fixture seed plus a few fictional documents inserted as filed:
  - "How much did we pay AGIPI last year?" → one `sum_amounts` call, a correct total, `DocCard`s;
  - "What's due this month?" → a `DeadlineCard`;
  - page context from `/documents/:id` is honoured;
  - a French prompt gets a French reply, and an English prompt about a French document gets an English reply.

  Record the first reasoning and first text timings.
- The fresh-volume start with the cache subpath mount works. `docker compose config` output is only ever shown through a filter that hides secrets.

## Don't

- No REST resources beyond `/api/chat`, the conversations endpoints C3 §7 needs, and health.
- No write tools, `ingest_attachment`, interviews or drafts.
- No Telegram bot token (S4 is deferred).
- No contract changes. If something doesn't fit, stop that item and report it.
