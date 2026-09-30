# Mona repo

- Source of truth: vault `mona-hq/specs/mona-mvp-master-plan.md` (rulings R1–R59) → `docs/contracts/` (once frozen) → `docs/contracts/amendments.md` → `docs/decisions.md`. Precedence: contract > amendments > brief.
- Design tokens: `design/mona-handoff/tokens.css` is the only token source (load order: tokens.css → the design system's bundle.css → app CSS; Tailwind without preflight). Components follow `design/mona-handoff/HANDOFF.md` names and `design/mona-design-system/components/index.d.ts` APIs. Screens: `design/screens/mona-web-app.pdf` (page map in plan §9).
- Commits in this repo are unsigned (`commit.gpgsign=false` repo-local); lanes never trigger a signature, fetch or push. The orchestrator signs and pushes at gates with `tools/sitting.sh`: it asks the operator via zenity, then collects one YubiKey PIN + touch per signature plus one for the GitHub connection. GitHub use is fine at any time; SSH calls to the private repo ask the operator for a FIDO touch through zenity, which is expected.
- Never commit or copy practice documents, OCR text or Hermes state into the repo or the vault.
