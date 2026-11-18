# FIX-16 N: custom names: the `MMMM` month unit, `rename_documents`, collision-aware previews (A61, A62)

Card **FIX-16-N**. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/fix-16-n`, branch `fix-16-n`, on top of `bugfixes`.
- **Compose project:** `-p mona-fix16n`. Export `WEB_PORT=7994 API_PORT=11284 POSTGRES_PORT=57954 HERMES_PORT=11164 E2E_PORT=5194`. Never edit `.env`.

**Read first:**
- `briefs/common.md`;
- amendments **A28, A61, A62**;
- C5 §4 (rules), §6.2, §8;
- C4 §2 (conventions, errors, cards, visibility), §3.5, §3.8, §3.9, §3.16;
- C1 §11.5;
- C7 §2, §5.4, §8.1;
- C3 §4.5, §5.5;
- `docs/decisions.md` **D12, D15, D18, D23**.
- Code:
  - `apps/api/src/mona/templates/` (`grammar.py`, `render.py`);
  - `rules/engine.py` (~302: `action.filename` wins), `rules/grammar.py`;
  - `services/rules.py` (`draft`/`learned_priority`, `rule_candidates`, preview ~143-147, `apply_rule` ~225-280), `services/placement.py`, `services/undo.py`;
  - `fileops/ops.py` (collision suffix ~81-88, ~297-312; group undo ~724-752);
  - `mcp/write.py` (`correct_document`, `preview_rule`, `apply_rule`, `undo`);
  - `i18n/__init__.py` (`MONTHS`);
  - web: `routes/rules/RuleDetail.tsx`, `data/template.ts`, `mocks/template.ts`, `chat/cards/` (the `rulePreview` card, `PathDiff.tsx`), `apps/web/e2e/chat.mock.spec.ts`.

## Do (in this order; commit after each step)

1. **A61: grammar and render.**
   - Add `MMMM` to `DATE_UNITS` before `MM`.
   - `format_date` takes the filing language and renders the capitalised month name.
   - Literals are NFKD-folded before the `_LITERAL_CHAR` pass (C5 §8.4 step 2).
   - §8.5 case 10 becomes a renderer fixture.
   - A test over `tests/fixtures/seed/practice.yaml` (and any other seed or demo rule and template file) asserts that none uses `MMMM` or an accented literal whose name would change.
   - Tests: MMMM in fr/ro/en; `MMMM` before `MM` (`{date:MMMM}` must not render `1010`); accents in values and literals; folder segments keep accents.
   - **Mutation:** MMMM after MM → a test fails.
2. **A62 item 2: preview suffixes.** The unapplied rule preview simulates the apply in (`arrived_at`, `id`) order, as A62 item 2 defines, and predicts the C7 §8.1 suffixes. Apply must produce exactly the predicted `to_path`s. Test both together, including the case where candidate B currently holds A's target name.
3. **A62 item 1: the service.**
   - `templates/infer.py` holds the pure example → pattern function, with longest-match, left to right, and a round-trip check.
   - `templates/infer.py` follows A62 item 1.1 exactly: normalise first, boundaries, the units inferred after the leading date, the ≥4-character `{reference}`, the tie order, whole-segment month and year checks.
   - `services/rename.py` builds the draft rule per A62 item 1.2.
     - When a rule filed the document (classification method `rule`), copy its conditions and action and add `filename`. Otherwise use the Subject-value conditions, with `would_refile` when the values differ from where it's filed.
     - The rule takes `source='correction'` and `origin_document_id`, with a `rule.create` entry as C4 §3.5 step 4 does. **No migration:** FIX-16-S owns `0011`.
     - The checks from A62 item 1.3: `would_refile` (including template drift), `in_review`, `not_covered`, `date_fallbacks`, collisions.
     - The rename-only check runs before any write, with an unsaved rule through `services/placement.py` `rule_candidates`.
     - The same input returns the same draft.
   - `rule_candidates` lives in `services/placement.py`, not `services/rules.py`. `entity`/`category equals` compare the model's Subject values (C5 §4.2), which is why the filing rule is copied.
   - Tests, with fictional names only:
     - a set of six monthly statements of one counterparty and entity, two of them in the same month, **filed by an IBAN-routed rule** (as the seed's Hello bank rule is);
     - a document with the same counterparty under another entity;
     - one corrected to another entity (→ `would_refile`);
     - one waiting in Review (→ `in_review`);
     - one filed under an older template version (→ `would_refile`);
     - a document filed by the model, not a rule (the Subject-value path);
     - every A62 error;
     - the inference traps: an example with accents and spaces; a literal containing "10" or a 2-character reference; a trailing separator after the date; a literal "Marchand" (no false month hit);
     - apply renames them; group undo restores the names and sets the rule back to draft; redo.
4. **A62: the tool.**
   - `rename_documents` in `mcp/write.py` with C4 §2 conventions: errors, the 4000-character result cap, visibility, cards (`rulePreview`).
   - Add it to `WRITE_TOOLS` in `tests/test_mcp_server.py`.
   - Add `mcp__mona__rename_documents` and `mcp__mona_tg__rename_documents` to `tests/fixtures/hermes/surface.json` for api_server, telegram and cron (`test_hermes_surface.py` asserts the exact tool set).
   - Tool chip strings in the web catalogs:
     - EN "Preparing the new names…" / "Prepared the new names";
     - FR « Préparation des nouveaux noms… » / « Nouveaux noms prêts »;
     - RO „Pregătesc noile nume…" / „Noile nume sunt pregătite".
5. **Web.**
   - RuleDetail shows a "File name" row when `rule.action.filename` is set (EN "File name", FR « Nom du fichier », RO „Numele fișierului").
   - A `{date:MMMM}` chip in `data/template.ts`, the mock renderer, and the `bad_format` text.
   - An e2e in `chat.mock.spec.ts`: a rename ask → the `rulePreview` card with old → new names → Apply → Undo restores the old names.

## Acceptance (fresh output in the report)

- `make check` and `make ci-py` green; `make e2e` no worse than 129 passed / 19 skipped (plus your new test).
- Every test and mutation above. Mutation-check the renderer and the infer round-trip (common rules).
- **Live check** (D9, cheap model, your dev stack with the demo seed).
  - SOUL's `rename_documents` line comes from FIX-16-S in parallel, so it isn't in your tree. For this check only, append A59's line ("To rename documents, call `rename_documents` with the name the person gave, copied exactly; never type a rename table.") to the SOUL installed in your stack's Hermes volume. Don't commit it, and say so in the report.
  - In a fresh conversation, ask in Romanian, with a fictional document from the seed: "poți să redenumești toate extrasele de la <bank> în formatul <example>?" Then check:
  - the tool is called with the example copied exactly;
  - the card shows the right names;
  - Apply, then Undo.
  - Run it 3 times and report the tool-call arguments (no document text) and the spend.

## Don't

- Don't touch `deploy/hermes/SOUL.md` in the repo (FIX-16-S owns it), the chat adapter (FIX-16-W), or the Hermes configs (FIX-16-H).
- No new journal kinds. No template-editing tool.
- No contract changes beyond A61–A62, and no showcase-only code (D16).
- Never edit `.env`. Don't touch the mona box.

Report: `~/DevFiles/mona-hq/orchestrator/reports/fix-16-n-report.md`.
