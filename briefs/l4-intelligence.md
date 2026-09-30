# L4: the intelligence vertical (interviews, deadlines, drafts, export)

Card **L4** (plan §6.3 L4). Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l4`, branch `l4`, based on `main`.
- **Compose project:** `-p mona-l4`, with `WEB_PORT=5673 API_PORT=9265 POSTGRES_PORT=55932 HERMES_PORT=9142`. `make check COMPOSE="docker compose -p mona-l4"`.

You own the vertical end to end: services, jobs, **REST endpoints** (C2 §10–§12) and **MCP tools** (C4 §3.6, §3.7, §3.10–§3.13). L2-P2 builds auth and the rest of the REST surface in parallel. Use its middleware once it lands on `main`, and until then mount your routers on the existing app the same way the chat routes are mounted. The debrief is the demo's 4:00 beat.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D10; **D9: tests use the cheap model or recorded outputs**).
- `docs/contracts/amendments.md` A1–A13 (A3 the `ask` answer, A4 the apply group, A9 `debrief_early_min`, A10 no visitor deadlines).
- **Contracts:**
  - **C6 in full;**
  - C2 §1 (conventions), §10–§12, §14 (notes your actions write);
  - C4 §2 (conventions), §3.6, §3.7, §3.10–§3.13, §3.15 (`get_brief` exists; keep it consistent);
  - C1 §6 (workflow tables), §11.5/§11.7 (RuleDraft branches, Interview, Draft, Export DTOs);
  - C3 §5–§6 (cards, notes);
  - C8 §3, §5.5, §7 (languages, interview keys, comma-below);
  - C9 §3.3 (visibility in the accountant pack) and §5.5 (Visitors are left out of figures).
- **Spikes:** `docs/spikes/s6/` (the two-pass debrief: prompts, the branch shape, timings, the P0-3 failure mode).
- **Code on `main`:** `mona/services/README.md` (L1-M1: `preview_rule`, `apply_rule`, `undo`, rules store), `mona/mcp`, `mona/chat`, `mona/dto`.
- **Demo:** `docs/demo-script.md`, `demo/seed/rules.learned.yaml` (the expected AGIPI and Hello bank outcomes), `demo/expectations.yaml`.

## Build

1. **Interview engine** (C6):
   - scopes and candidates;
   - **the hooks** `mona.interviews.hooks.on_document_settled(batch_id)` and `on_batch_done(batch_id)`, which L1-M3 will call (expose them now, with tests that call them directly);
   - the batch, queue, on-demand and seed triggers, including `debrief_early_min` (A9) and the advisory lock;
   - clustering;
   - **pass 1** (thinking, time-boxed at the settings value) and **pass 2** (no thinking, strict schema, ≤ 7 questions);
   - checks and compilation to the **branch RuleDraft** (AGIPI → two branches; drop a fixed subcategory when the documents differ);
   - persisting;
   - the **cached debrief bound by sha256** (§4.7) with the fallback mode;
   - budgets and failure.
2. **Answers** (C6 §6): options, `ask` (A3), free text, idempotency, skip, results. Preview/apply through L1's services; the activating `rule.change` joins the apply group (A4). **Undo of a whole apply group reverts the rule to draft, and redo re-activates it** (C6 §7.3): implement it as a hook in L1's undo service if there is a clean extension point, otherwise report exactly what L1-M3 must add.
3. **Deadlines and reminders** (C2 §10, C4 §3.10–§3.11): list, "Done", reminders. `list_deadlines` exists as a read tool; keep one implementation.
4. **Drafts** (C2 §12, C4 §3.12): async `draft_reply` in the conversation language, `[BRACKETS]` for unknowns, `.docx` via python-docx, never sent.
5. **Accountant export** (C2 §12, C4 §3.13): entity + fiscal year → zip + CSV under C9 §3.3 visibility, CSV-injection safe, reuse while building.
6. **REST and MCP:** C2 §10–§12 endpoints and the C4 tools, writing C3 cards and C6 §9 notes.

## Tests and evidence

- **Deterministic tests use recorded model outputs** (no network in CI), for both passes and drafts. Include the S6 cluster.
- **The C6 §10 obligations,** every [M] mutation-checked. At least:
  - the time box;
  - the ≤ 7 cap;
  - the AGIPI two-branch compile (test 12: both PER and Assurance vie paths in the preview);
  - early start at `debrief_early_min`;
  - the queue trigger ignoring running batches;
  - apply-group undo → draft;
  - cached-debrief binding by sha256.
- **Stage scenario,** end to end on the seeded dev stack with recorded outputs: the live batch's 7 review documents settle in order, the early start fires at 7, the banner data says 3 questions, AGIPI answers → 2 preview cards → Apply all moves them → the group undo reverts files and rules, and redo restores both.
- **Live smoke** (cheap model): one real two-pass debrief on the synthetic cluster, with timings and spend delta. **One quality run** (Qwen 3.6, D9) of the same, with timings for the demo-script v2 budget.

## Don't

- No auth or middleware, and no REST outside C2 §10–§12 (L2-P2).
- No web UI (L3).
- No pipeline changes except calling the documented services.
- No contract changes: stop and report.
