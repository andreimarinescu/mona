# W1-B: draft contract set B (C2, C6, C8, C9)

Card **W1**, set B (plan §5). Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/w1-contracts-b`, branch `w1-contracts-b`, based on `main`.
- **Output:** `docs/contracts/C2-rest-api.md`, `C6-interview.md`, `C8-i18n.md`, `C9-privacy-ops.md`.

Next come the same gate as set A (reviewer lenses with skeptics, a fold, verification), then Andrei's verdict and the freeze. After that L3 (web) and L4 (intelligence) build on these, and L2 finishes its REST side. Write for lanes that can't ask you anything.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D7).
- **Set A, frozen v1.0:** `docs/contracts/C1-domain.md`, `C3-chat-stream.md`, `C4-mcp-tools.md`, `C5-classification.md`, `C7-file-ops.md`, and `amendments.md`. Set B must not contradict set A. If set B needs a set A change, write it up as a proposed amendment in your report, not in the set A files.
- **Every forward reference set A makes to C2/C6/C8/C9.** They're listed in `~/DevFiles/mona-hq/orchestrator/reports/w1-contracts-a-report.md` (section "Forward references set B must honour") and in `w1-contracts-a-fold-report.md` (the new set B forward references). Grep the frozen contracts for "C2", "C6", "C8" and "C9" too; each hit is an obligation.
- **The master plan** `~/Obsidian/dev-docs/mona-hq/specs/mona-mvp-master-plan.md`: §1 rulings, §2.2 interview engine, §2.5 i18n, §5 (C2/C6/C8/C9 lines and the delta-review details), §9 (unlock/auto-lock, visibility, draft card), §10c/`docs/demo-script.md`, §12b.
- **Design:** `design/mona-handoff/HANDOFF.md` §2–§6 (routes, behaviours, `InterviewCard`, `CorrectionScopePrompt`, `FirstRunChecklist`, Settings sections, `AccountantExportDialog`).
- **Spikes:**
  - S6 two-pass debrief: `docs/spikes/s6/README.md` and `debrief/`, with the latency numbers and the time-box proposal.
  - S1/S5 for Hermes and ops facts.
- **Existing web i18n:** `apps/web/src/i18n/`, `scripts/i18n-check.mjs`.

## Each contract: same form as set A

Header (version 0.1-draft, status, freeze date, change rule, consumers, depends-on), numbered sections, "Test obligations" (mark mutation-checked ones [M]), and "Open questions" with a proposal each.

- **C2 · REST API and auth.**
  - Every endpoint the web needs for the screens in HANDOFF §2 and the set A forward references: method, path, request and response (C1 §11 DTOs by name), errors (one error envelope), pagination, idempotency.
  - Auth: the single owner profile, argon2, the session cookie, CSRF, auto-lock, and 423 on writes while locked (plan §12b). Pipeline and Hermes use the service key.
  - The deep link `/documents/:id?page=&q=`. The PDF endpoint serves the cached OCR'd copy, else the archive bytes resolved at request time.
  - Card-action endpoints that write C3 notes; polling endpoints; conversations.
  - Corrections with scope ("just this one" / "every document like this"); delete with confirmation; deadline "Done"; visitor-flag upload; restore of a re-uploaded deleted document; settings (thresholds, language, auto-lock); system status (llama-swap `/v1/models` + `/props`).
  - The OpenAPI → TS client flow.
- **C6 · interview protocol.**
  - Seed / per-batch debrief / on-demand; triggers (the batch-end hook, and `debrief_queue_threshold` with demo-script v1's "debrief works on whatever has queued"); clustering.
  - Two-pass generation: pass 1 thinking with a **time box** (S6: cut at about 35–40 s and hand partial reasoning to pass 2; your call, with a proposal); pass 2 no-think json_schema, ≤ 7 questions, the branch RuleDraft (C1 §11.5).
  - Question and option schema; "ask me each time"; "It depends; let me explain" as a composer path.
  - Answer → rule(s) → preview → apply → undo, including whether undoing Apply disables the rule.
  - Matching the cached debrief to the live batch by sha256; notes; the interview states, as the C4 reuse semantics expect.
- **C8 · i18n.**
  - Key namespaces and the source-of-truth flow (en → fr/ro), locale negotiation (UI setting vs conversation language, C3's reply-language line), `detect_language`.
  - Formatting through `Mona.format`; the ș/ț rules (reference C5 `norm()`, don't redefine it).
  - Every string key set A names: tool labels, `review.sentence.*`, errors, the chat-banner key, the RO `condition_text` wording review.
  - The glossary of product terms in EN/FR/RO, and the CI rule (missing keys fail).
- **C9 · privacy and ops.**
  - **Egress per environment:** dev may use OpenRouter; **prod has no cloud AI**. The config assertion covers the D3 trap (`OPENROUTER_API_KEY` absent from the Hermes env and `$HERMES_HOME/.env`), and there is an egress test.
  - Hermes lockdown in prod (the S1 key map; the unsandboxed-terminal warning; `agent.disabled_toolsets` as a backstop); `/mcp` kept off the reverse proxy.
  - Visibility semantics `visible(row, channel)` for web, Telegram and exports: personal entities stay out of Telegram notifications and exports. Memory on Telegram.
  - The Visitors purge (`batches.visitor`, `purge_after_hours`) and the Telegram first-line rule (no names or amounts).
  - **The demo snapshot:** exactly what `mona demo-reset` restores (DB, archive tree, text/OCR/thumbnail/model caches, the Hermes profile dir) and how dates re-anchor (event timestamps shift, printed dates never do). Backup and restore of the demo state.

## Deliverable

- The four documents, committed unsigned.
- The report at `~/DevFiles/mona-hq/orchestrator/reports/w1-contracts-b-report.md`: a summary per contract, every set A forward reference → where it's honoured, proposed set A amendments (if any), and the open questions ranked by how much they block L2/L3/L4.

## Don't

- No code.
- No edits to set A files.
- Don't re-open R1–R59 or D1–D7.
