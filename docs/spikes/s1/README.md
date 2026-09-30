# S1 + S2: Hermes 0.21.5 in Docker, API server, MCP tools, overlays

Run 2026-09-30 on the laptop. The model was OpenRouter `qwen/qwen3.6-35b-a3b` with no provider pins (S6 recommends the pins). Everything used synthetic data from `spike_mcp.py`.

## Result

| Spike | Pass condition | Result |
|---|---|---|
| S1 | Official image runs the API server from a profile volume; the stream payloads of both paths are captured; the lockdown knobs are mapped to real keys | **Pass.** Fixtures are in `fixtures/`, the key map is below |
| S2 | 10/10 tool calls through our MCP (HTTP + key header), `tool_search` off, toolsets locked; replies reflect the page-context overlay and a card-action note | **Pass.** Tools 10/10, answers 10/10, overlay and note both honoured |

## Image

- `0.21.5` is not a published tag. Hermes images are tagged by date, so 0.21.5 is `nousresearch/hermes-agent:v2026.9.24`, digest `sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7`. `hermes --version` in the container reports `v0.21.5 (2026.9.24)`, and `/health` reports `version 0.21.5`.
- s6-overlay is PID 1. Start it with `gateway run` and keep the image entrypoint.
- `HERMES_UID`/`HERMES_GID` remap the internal user so files in the profile volume are owned by the host user. Never use `--user`.
- `HERMES_HOME=/opt/data` is the profile, a single volume holding `config.yaml`, `SOUL.md`, `.env`, `memories/`, `skills/`, `sessions/` and `state.db`. `demo-reset` restores this directory.
- First boot seeds the profile and takes about 70 s. Later boots take about 9 s.
- The dashboard stays off unless `HERMES_DASHBOARD` is truthy.

## Key map (plan §3 lockdown → 0.21.5)

| Plan knob | Key | Value for Mona |
|---|---|---|
| API server on, keyed | env `API_SERVER_KEY` (≥16 chars; the adapter won't start without it), `API_SERVER_HOST`, `API_SERVER_PORT`, `API_SERVER_MODEL_NAME` | `$HERMES_API_KEY`, `0.0.0.0` on the compose network only (no host port in prod), `8642`, `mona` |
| CORS | env `API_SERVER_CORS_ORIGINS` | unset (only our api calls it) |
| Toolsets locked | `platform_toolsets.api_server` | `[memory, skills, todo, mona]` resolves to exactly those four. `mona` is the MCP server name. The owner bot gets `platform_toolsets.telegram` later (S4) |
| `tool_search` off | `tools.tool_search.enabled` | `false` |
| Auxiliary pinned to main | `auxiliary.<task>.provider` for all 18 tasks | `main` |
| Title generation off | `auxiliary.title_generation.enabled` | `false` |
| Background review off | `auxiliary.background_review.enabled` | `false` |
| `session_search` off | not in any enabled toolset | verified by toolset resolution |
| `context_length` = slot | `model.context_length` | `65536` |
| Skill self-authoring gated | `skills.write_approval` | `true`; also `skills.project_discovery: false` |
| Memory writes | `memory.write_approval` | `false` (Mona keeps preferences; memory is capped at 2,200 chars) |
| Auto-update off | `updates.check` | `false`; the image is pinned by digest |
| Curator off | `curator.enabled` | `false` (it makes auxiliary LLM calls on a timer) |
| OpenRouter response cache | `openrouter.response_cache` | `false` |
| Telemetry | `telemetry.shared_metrics.enabled` | `false` (the default) |
| MCP client | `mcp_servers.mona` | `url: http://api:8765/mcp`, `headers.Authorization: "Bearer ${MONA_SERVICE_KEY}"` (env interpolation works), `sampling.enabled: false`, `tools: {resources: false, prompts: false}` (read from source, `tools/mcp_tool_registration.py`; not exercised here, so L2 verifies it) |
| Model (dev) | `model.provider` / `default` / `base_url` | `openrouter` / `qwen/qwen3.6-35b-a3b` / `https://openrouter.ai/api/v1`, plus the S6 provider pins |
| Model (prod) | same keys | `custom` (alias `llamacpp`), `base_url: http://<llama-swap>/v1` |
| Reasoning for agent turns | `agent.reasoning_effort` | `medium` (thinking on) |

**Egress trap (C9).** If `OPENROUTER_API_KEY` is set, Hermes ingests it from the environment into its credential pool ("this enables OpenRouter spend"), whatever the configured provider. The prod assertion must check that the key is absent from the container env and from `$HERMES_HOME/.env`, not just that the config names no cloud provider.

**Host firewall.** ufw on the laptop drops container → host traffic, so Hermes can't reach services on the host. All services, including the spike MCP server, run on the compose network.

## Stream paths

Both need `Authorization: Bearer $HERMES_API_KEY`. Create sessions with `POST /api/sessions` → `{session: {id}}`.

**`POST /v1/chat/completions` + `X-Hermes-Session-Id`** (`fixtures/completions-stream-overlay.sse`). Recommended for the adapter.
- History comes from `state.db`; only the last user message in the body counts.
- `system` messages in the body become the turn's ephemeral system prompt, which carries the page-context overlay and the card-action notes.
- OpenAI chunks carry `delta.reasoning_content`, **streamed live**, and `delta.content`.
- `event: hermes.tool.progress` carries `{tool, emoji, label, toolCallId, status: running|completed}`.
- `event: hermes.status` frames and `: keepalive` comments appear; skip them.
- The final chunk has `finish_reason` + `usage`, then `data: [DONE]`.

**`POST /api/sessions/{id}/chat/stream`** (`fixtures/session-stream-tools.sse`).
- Body `{message, instructions?}`; `instructions`/`system_message` is the ephemeral system prompt.
- Events: `run.started`, `message.started`, `assistant.delta {delta}`, `tool.started {tool_name, args}`, `tool.completed` (no result), `tool.progress` with `tool_name: "_thinking"` (only once, at the end, not live), `assistant.completed {content}`, `run.completed {messages[] with reasoning, usage}`, `done`.
- Reasoning is not streamed live here, which fails the "thinking visible" part of S5. That's why the completions path is recommended.

**On both paths, tool results never appear in the stream.** Cards have to come from `card_events`, written by our MCP tools and read by the adapter during the turn, as plan v4 (C1/C3) already says.

## S2 numbers (`s2_probe.py`, `fixtures/s2-results.json`)

- 10 prompts in EN/FR/RO, each in a fresh session: the right tools were called 10/10 times and the answers were correct 10/10.
- First reasoning token: median 0.73 s, max 1.39 s. First answer token: median 3.45 s. Whole turn: median 4.0 s, max 13.2 s.
- Tool calls per turn: median 2.5. The outlier made 12 calls, one of them the Hermes-added MCP utility `list_resources`; its prompt ("filed under Personnel") didn't match the toy search. C4 disables `resources`/`prompts` utilities and gives `search_documents` a real entity filter.
- **Page-context overlay** (a system message naming the open document): Mona fetched that document and answered correctly. But she answered in **French** to an English question. The adapter overlay must name the reply language ("the person wrote in English; reply in English").
- **Card-action note:**
  - As a system message ("Card actions since your last reply…"), the next answer builds on the rule without contradicting it and without extra tool calls. **Adopt this.**
  - As a prefixed user message it also works, but costs extra tool calls and drifted to French.

## Prompt size

`usage.prompt_tokens` for a one-word reply:

| Toolsets | Prompt tokens |
|---|---|
| `[memory, skills, todo, mona]` | 8,016 |
| without `skills` | 5,078 |
| `[mona]` only | 3,696 |

Each tool round trip resends the prompt, so the overlay turn above (one tool call, two LLM calls) cost 15,830 prompt tokens. On mona that's local prefill. llama.cpp's prompt cache makes warm turns cheap, but the first turn per slot pays in full; measure it on Oct 8.

## Files

- `spike_mcp.py`: synthetic FastMCP server shaped like C4, with bearer-key auth.
- `config.spike.yaml`: the profile config used here; the source for `deploy/hermes/config.yaml`.
- `s2_probe.py`: reliability, overlay and note probe.
- `fixtures/`: raw SSE captures of both paths, and the S2 results.
