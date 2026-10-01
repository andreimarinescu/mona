# Standing rules (every Mona lane)

- **Source of truth.** In order of precedence: the frozen contracts in `docs/contracts/` → `docs/contracts/amendments.md` → your brief. Before the contracts freeze, the master plan decides: `~/Obsidian/dev-docs/mona-hq/specs/mona-mvp-master-plan.md` (rulings R1–R59 are decided; don't re-open them). Design: `design/mona-handoff/HANDOFF.md` (its "v1 demo scope" is the cut list) and `design/mona-design-system/components/index.d.ts`.
- **Decisions.** Re-read `docs/decisions.md` in the main checkout (`~/DevFiles/mona-hq/mona/docs/decisions.md`) at every commit boundary. An entry there binds you even if your brief predates it.
- **Where you work.** Your brief names your worktree and branch. Work only there, with absolute paths or `git -C <worktree>`. Don't touch the main checkout, other worktrees, or the mona box.
- **Host safety.**
  - docker compose runs with the project name your brief gives (`-p <name>`), so stacks from different lanes never share containers, networks or volumes. Never `docker system prune`, and never stop or remove containers, images or volumes you didn't create.
  - Python via `uv` inside the project; Node via the host's node 24 + npm. No global installs, no sudo.
- **Private data.**
  - Practice documents (`~/DevFiles/mona-hq/100 PDF neclasificate/`) and their text cache (`~/DevFiles/mona-hq/bench/corpus/textcache/`) are read-only.
  - Anything derived from them (manifests with file names, OCR text, model outputs with quotes, IBANs, SIRENs, addresses) goes to `~/DevFiles/mona-hq/demo-data/` only. Never into the repo, the vault, commit messages or reports. In the repo and in reports, refer to a practice document by `sha256[:12]` plus a generic label ("AGIPI PER notice").
  - Repo fixtures are synthetic (fictional names, amounts, identifiers).
  - Dev may send practice documents to OpenRouter (R30). Keys come from `~/DevFiles/mona-hq/mona/.env`; never print, log or commit them. Never write to `.env` either: it is shared by every lane. Export ports and project names in your shell instead.
- **Commits.**
  - Commit unsigned in your worktree at each coherent step (the repo sets `commit.gpgsign=false`). Corrections go in as `git commit --fixup=<sha>`, never `amend!`/`squash!`.
  - Never rebase, amend, push, fetch or merge. The orchestrator integrates.
  - No `Co-Authored-By` or any attribution text. Never cite a commit hash in code, docs or commit messages.
  - **Never trigger a YubiKey signature.** Any scratch repo or clone inherits the global `commit.gpgsign=true`: run `git config commit.gpgsign false` and `git config tag.gpgsign false` in it first. If a git command hangs waiting for a signature, kill it and report.
- **Code comments.** Minimal: only a crucial non-obvious invariant, one short line. No narration or history; doc and test comments get one short line. Explanations go in your report.
- **Tests are evidence.** Every acceptance item needs a test or a command that can fail. Mutation-check file ops, the rules engine and the template renderer (break the code, watch the test go red, restore). Fresh command output only; never "should pass".
- **Blocked or unsure.** You can't reach the orchestrator mid-run. If the brief and contracts don't answer something, take the smallest conservative option and list it under "Assumptions" in the report. If the choice would change a contract, a ruling, privacy or a user-visible behaviour, stop that item and report it as blocked instead.
- **Report.** When done or blocked, write `~/DevFiles/mona-hq/orchestrator/reports/<card>-report.md`:
  - what was built (files, commit subjects);
  - acceptance item → test or command → result;
  - mutation checks (if any);
  - CI-parity output (commands and their tail);
  - deviations from the brief, each with its reason;
  - assumptions and open questions.

  Your final message is a short summary plus the report path.
