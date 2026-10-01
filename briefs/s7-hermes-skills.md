# S7 spike: curated Hermes skills as recipes for Qwen 3.6

Card **S7**. Agent: `coder`. **A spike: measure and report, merge nothing but the report.**

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/s7`, branch `s7`, based on `main`.
- **Compose project:** `-p mona-s7`. Export `WEB_PORT=7873 API_PORT=11165 POSTGRES_PORT=57832 HERMES_PORT=11042` (never edit `.env`; the worktree has the `.env` symlink).

Read `docs/decisions.md` **D18** (and D15/D16), `docs/spikes/s1/README.md` (the Hermes key map) and `deploy/hermes/config.yaml`.

**Question:** do curated Hermes skills, recipes we write and version (not self-authored), help Qwen 3.6 answer common asks in ≤ 2 tool calls? Are they better than the same recipes as SOUL lines, and at what prompt cost and latency?

## Do

1. **Re-enable skills** in the spike stack only:
   - the `skills` toolset on `api_server`;
   - `skills.write_approval: true`, with self-authoring and the hub off (check the 0.21.5 keys);
   - 4 curated recipes in the profile: "what's due this month", "how much did we pay / do we owe X", "draft a reply to a letter", "prepare the accountant pack". Each is a short procedure naming the Mona tools to call, with parameters.
2. **Measure on Qwen 3.6** (D9 quality run; ≤ $1 total). 10 asks (the 4 recipes' asks plus paraphrases and 2 asks that match no recipe), each 3 times, in 3 configurations:
   - (A) today's config;
   - (B) skills on with the recipes;
   - (C) skills off with the same recipes as SOUL lines.

   Record:
   - whether the right recipe or skill was used;
   - tool calls per turn;
   - the time to first text and to close;
   - the prompt tokens per call (Hermes usage);
   - correctness of the answer, checked against the stage data.
3. **Write `docs/spikes/s7/README.md`:** the tables, what the skills cost per call, failure modes, and a recommendation (adopt B, adopt C, or neither) with the evidence. Use document ids only: no document text, names or amounts.

## Acceptance

- The README with the three-way tables and raw numbers.
- The spike's config changes are listed but not merged. The only commit is the README (and any harness script under `docs/spikes/s7/`).

## Don't

- No product code changes, no contract changes.
- Never edit `.env`.
