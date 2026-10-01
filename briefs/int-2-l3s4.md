# INT-2: integrate L3-S4 onto main (finish the in-progress rebase)

Card **INT-2**. Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l3-s4`, branch `l3-s4`. **A rebase onto `main` is in progress there:** L3-S4's first commit stopped with 10 conflicts. Its second commit (a fixup) follows.
- **Exception to the standing rules:** for this card you **may** finish this one rebase (`git add` + `GIT_EDITOR=true git -c commit.gpgsign=false rebase --continue`). Nothing else: no new rebases, no push, no fetch. **Never edit `.env`.**
- **Ports:** `E2E_PORT=6174`. No compose stack.

`main` gained L3-S3 (the designed chat, cards, `/chat`, panel; it extended the typed data layer, the MSW mock world and handlers, i18n, router and styles) while L3-S4 built Unlock, Home, Rules, Entities, Settings and the states on the same files. Produce one integrated web app that keeps **both sides' behaviour**.

## Read first

- `briefs/common.md`, `docs/decisions.md` (D12: fictional names in mocks).
- **The two reports:** `~/DevFiles/mona-hq/orchestrator/reports/l3-s3-report.md` and `l3-s4-report.md` (each lists the shell and spec files it changed).

## Resolve

- **`apps/web/src/data/dto.ts`, `journal.ts`:** union of types and hooks. Where both changed the same type, keep the C1 §11 / C2 shape. The contracts decide.
- **`apps/web/src/mocks/{world,handlers,browser}.ts`:** one mock world serving both sides' fixtures and handlers. Keep fictional names (D12); no seed counterparty names.
- **`apps/web/src/i18n/{en,fr,ro}.json`:** deep-merge. If a key collides with different text, keep the one C8 names, else L3-S4's, and list it in the report.
- **`apps/web/src/router.tsx`:** both sides' routes, with the real screens replacing placeholders (`/chat` is real now; L3-S4 moved a shell-spec scope test to `/chat` as "the last placeholder", so repoint it to a route that still fits, or drop that assumption).
- **`apps/web/src/styles/app.css`:** union.
- Then the fixup commit; resolve the same way.

## Acceptance (fresh output in the report)

- The rebase finished: `git log --oneline main..HEAD` shows L3-S4's commit or commits.
- `make web-check` exit 0, with test counts.
- `E2E_PORT=6174 npx -w apps/web playwright test --workers=2`: all non-env specs pass (report passed/skipped).
- The report lists each conflict and its resolution.

## Don't

- No new features.
- No backend changes.
- Never edit `.env`.
