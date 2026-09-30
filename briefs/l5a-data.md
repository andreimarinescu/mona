# L5a: demo corpus inventory, acceptance fixture map, synthetic gap-fillers, seed draft

Card **L5**, part a (plan §6.3 L5). Agent: `coder-light`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l5-data`, branch `l5-data`, based on `main`.
- **Private outputs:** `~/DevFiles/mona-hq/demo-data/`.

Part b (the confidence histogram and the thresholds, `mona demo-reset`, the `findQuery` check) comes after S6 and the contracts.

**Read first:**
- `briefs/common.md`, especially "Private data";
- `docs/decisions.md`;
- plan §0 success criterion 2, §1 (R4, R6, R14–R18, R38), §2.1, §9 (confidence bands, template tokens), §10c (demo script v0), §11 (seed + questions);
- Claudiu's input: `~/DevFiles/mona-hq/latest-classification-feedback-claudiu.md` and `~/DevFiles/mona-hq/exemplu-ORGANIZARE-Clasificare Documente.txt`;
- `~/DevFiles/mona-hq/classify/classify_llm.py`, the v2 taxonomy.

The corpus is `~/DevFiles/mona-hq/100 PDF neclasificate/`, with the text cache at `~/DevFiles/mona-hq/bench/corpus/textcache/`. Both are read-only.

## Build

1. **Corpus manifest** (private): `demo-data/corpus/manifest.jsonl`, one row per PDF.
   - Fields: `id` (sha256[:12]), `sha256`, `filename`, `pages`, `text_chars` (pdftotext, all pages), `needs_ocr` (< 50 chars on pages 1–2), `rotated_pages` (from `pdfinfo`/page boxes where detectable), `lang_guess` (fr/en/ro/es/other, a simple heuristic), `has_textcache`.
   - Also a short `manifest-summary.md` with counts only.
   - Generate it with a committed script, `demo/scripts/inventory.py` (uv inline deps). The script writes only into `demo-data/`.
2. **Acceptance fixture map** (private): `demo-data/corpus/acceptance-map.md`.
   - For each case, list the candidate document IDs, the expected entity / category / path, and the evidence lines:
     - the six feedback cases (AGIPI PER vs Assurance Vie by insured person; Hello bank → LMNP/Angers-Strasbourg/Banque/{fy}; TALENZ per company → Documents annuels/{fy}; OXYLEO → Personnel/Impôts et taxes/{year}; OPCO → SELARL/Appels de paiement/{fy}; UNIM → business);
     - the same insurer with two insured persons;
     - an FY-crossing bilan;
     - a rotated multi-page scan;
     - a duplicate (same sha256, or the same letter twice).
   - List every case the corpus can't cover as a **gap**.
3. **Synthetic gap-fillers** (in the repo, fictional content): `demo/synthetic/`.
   - Each document is defined in `demo/synthetic/docs.yaml`: id, the generator template, fields, and the expected classification (entity, category, subcategory, counterparty, dates as **offsets from an anchor date**, amount, expected path and file name under the plan's templates).
   - A generator script (`uv run`, e.g. reportlab + Pillow) renders them into `demo-data/synthetic/` (not the repo), using `--anchor YYYY-MM-DD`.
   - Cover:
     - every gap from item 2;
     - 2–3 patient-type showcase documents (devis, prescription; R7);
     - a phone photo of a printed letter (JPEG with perspective, shadow and noise);
     - an URSSAF payment demand due within 7 days of the anchor;
     - a SIE letter suitable for the "draft a reply asking for a payment schedule" beat;
     - one near-unreadable scan.
   - Addressees are the seed entities (names allowed); every identifier, amount and reference is fictional.
4. **Seed draft** (in the repo): `demo/seed/practice.yaml` and `demo/seed/rules.yaml`. It's a draft that will be re-keyed when C1/C5 freeze, so keep it simple and readable.
   - **Entities** (plan §11): canonical id, display name, legal form, visibility (practice|personal), fiscal-year end (unknown → `null` plus a `todo:` noting Claudiu's question 7), sub-units, linked people, filing language FR.
   - **Categories:** canonical ids derived from Claudiu's structure with better names (R14), labels in fr/en/ro, the DS `Category` icon (`bank|invoice|tax|insurance|payroll|training|travel|personal`), a path template and a file-name template using the tokens `{entity} {year} {fy} {category} {sub} {counterparty} {issuer} {reference} {date:YYYY-MM-DD}`. The `{fy}` categories are annual documents, bank and payment calls (R18). File names are date-first and diacritics-free; folders keep French accents (R17 as amended in §9).
   - **Rules:** the plan §11 seed rules as `conditions[]` + action, with a readable `condition_text`.
   - Identifiers the rules need (IBAN fragments, SIRENs, addresses) go in the private overlay `demo-data/seed/identifiers.yaml`, harvested from the corpus. The committed YAML references them by key.
5. **Demo candidates** (private): `demo-data/corpus/demo-candidates.md`.
   - A proposed live batch of about 20 documents: a mix that auto-files, 5–7 that queue, 1 unreadable, 1 duplicate.
   - 3 documents for the evidence moment: clean text layer, an amount and a due date on page 1.
   - The debrief clusters (AGIPI, Hello bank).
   - What goes into the pre-seeded (already filed) state.

   Rank them with reasons.

## Acceptance

- The manifest covers all PDFs. The summary counts are in the report (counts only).
- The acceptance map has an entry per case, with gaps named.
- `uv run demo/synthetic/generate.py --anchor 2026-10-20` renders every document in `docs.yaml` into `demo-data/synthetic/` with 0 errors. `pdftotext` on each generated PDF finds the key fields: amount and date, checked by a small test.
- The seed YAML parses. A tiny test renders every category's path and file-name template against a synthetic document without unknown tokens.
- The repo diff contains no practice-document names, quotes or identifiers: `git diff main --stat` plus a grep for IBAN/SIREN patterns, both shown in the report.

## Don't

- No application code (`apps/`), contracts or compose changes.
- No copies of practice documents or their text anywhere except `demo-data/`.
