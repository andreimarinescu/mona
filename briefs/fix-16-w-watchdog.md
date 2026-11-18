# FIX-16 W: the adapter cuts a runaway reasoning; a stopped turn ends cleanly in the web (A58)

Card **FIX-16-W**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-16-w`, branch `fix-16-w`, on top of `bugfixes`.
- **Compose project:** `-p mona-fix16w`. Export `WEB_PORT=7992 API_PORT=11282 POSTGRES_PORT=57952 HERMES_PORT=11162 E2E_PORT=5192`. Never edit `.env`.

**Read first:**
- `briefs/common.md`;
- amendments **A28, A29, A40, A58**;
- C3 §3–§4 and §7.2; C8 §5.2;
- `docs/decisions.md` **D15, D23**.
- Code:
  - `apps/api/src/mona/chat/stream.py` (`run_turn`, `upstream_events`, the `finally` block);
  - `chat/translate.py` (`Translator`);
  - `chat/guard.py` (the A40 filter, as a pattern);
  - `settings.py`;
  - `apps/web/src/chat/` (`ThinkingBlock.tsx`, `Messages.tsx`, `ChatThread.tsx`, `ChatComposer.tsx`, `reasoningClock.ts`, the outbox at `ChatThread.tsx` ~77-88);
  - `apps/api/tests/test_chat_adapter.py`, `test_chat_fallback.py`.

## Do

1. **Watchdog (A58 items 1–2).** A small class in `chat/watchdog.py`, fed from `run_turn` after `tr.feed`.
   - Expose a public accessor on `Translator` for the open reasoning part. Don't reach into private fields.
   - Add the settings `MONA_CHAT_REASONING_MAX_CHARS` (12000) and `MONA_CHAT_REASONING_MAX_S` (120) to `settings.py`.
   - Add both to `deploy/compose.prod.yaml`'s `x-prod-env` with their defaults (`${MONA_CHAT_REASONING_MAX_CHARS:-12000}`), as `MONA_INTERVIEW_PASS1_BUDGET_S` is, so they can be tuned on the box.
   - Rule (b) counts only lines of at least 40 characters (A58).
   - On a trip, take the clean-finish branch with `chat.fallback.stuck` (only when the turn has no text yet), `error_code='reasoning_cap'` and status `closed`. Log one line: trip reason and character count only (C9 §7).
   - If a check constraint or enum rejects `closed` plus an `error_code`, report it as blocked. Don't change the schema.
2. **Bookkeeping (A58 item 3).**
   - The `finally` block closes the translator before `close_turn`, so an aborted turn stores `reasoning_ms`.
   - `delta.reasoning` counts as reasoning text only when `reasoning_content` is absent from that delta.
3. **Web (A58 item 4).**
   - A reasoning part is live only when its message is the streaming one and the chat status is `submitted`/`streaming`.
   - The live label uses `chat.thinking.live_seconds`, ticking once a second.
   - A turn the person stopped (the status went from streaming to ready through `stop()`) shows `chat.stopped` and a Retry that calls `regenerate()`.
   - `useChat` gets `experimental_throttle` (or the current API's equivalent) of 50 ms.
   - The outbox sends when the status is neither `submitted` nor `streaming`, so it still sends after a failed turn.
4. **Strings (A58 item 5).** The api catalog gets `chat.fallback.stuck`; the web catalogs get `chat.stopped` and `chat.thinking.live_seconds`. If the catalog test wants plural forms for `{{count}}`, use them with the same text.

| Key | en | fr | ro |
|---|---|---|---|
| `chat.fallback.stuck` | I went round in circles on this one and stopped. Could you ask it another way, or one step at a time? | Je tournais en rond sur cette demande et je me suis arrêtée. Pouvez-vous la formuler autrement, ou étape par étape ? | M-am învârtit în cerc cu această cerere și m-am oprit. Puteți să o formulați altfel sau pas cu pas? |
| `chat.stopped` | Stopped. | Interrompu. | Oprit. |
| `chat.thinking.live_seconds` | Mona is thinking… {{count}} s | Mona réfléchit… {{count}} s | Mona se gândește… {{count}} s |

5. **Tests.**
   - Adapter tests for each trip reason (chars, repeat, time with an injected clock), using recorded-style SSE fixtures. They check that a tripped turn emits `reasoning-end`, the fallback text, `finish-step` and `finish`, is stored `closed`/`reasoning_cap`, and that its parts reload (C3 §7.2).
   - No trip when text is flowing.
   - No trip on an 8-item enumeration whose reasoning repeats short field lines ("- status: open", "currency: EUR").
   - An aborted turn keeps `reasoning_ms`.
   - Web unit tests: the live state after stop, the seconds counter, Stopped plus Retry, the outbox gating.
   - **Mutations:** the watchdog never trips → a test fails; the `finally` close removed → a test fails.

## Acceptance (fresh output in the report)

- `make check` and `make ci-py` green; `make e2e` no worse than 129 passed / 19 skipped.
- The tests and mutations above.
- One live D9 run on your dev stack (OpenRouter, the cheap model): 5 ordinary chat turns are unaffected (no trip, normal replies). Report the spend.

## Don't

- Don't touch SOUL, the Hermes configs or plugin (FIX-16-H), `detect_language` (FIX-16-S), or the tools.
- No contract changes beyond A58, and no showcase-only code (D16).
- Never edit `.env`. Don't touch the mona box.

Report: `~/DevFiles/mona-hq/orchestrator/reports/fix-16-w-report.md`.
