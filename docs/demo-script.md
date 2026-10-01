# Demo script v1 (Sicily, Oct 18–24; Claudiu drives; ≤ 12 min, English-led)

This is v1 of plan Appendix E, with document ids and a fallback for every beat. Ids are `sha256[:12]` of the practice documents, whose map lives in the private `demo-data/corpus/manifest.jsonl`; `syn-*` ids are synthetic documents from `demo/synthetic/docs.yaml`. Labels here are generic on purpose. Real amounts, names and addresses stay out of the repo.

**Key moment:** the pile gets filed, then the evidence viewer shows why. It gets the most rehearsal.

## Stage state before the talk (`mona demo-reset --anchor <today>`)

- **Pre-seeded registry:**
  - the 8 entities, the categories and templates;
  - the tier-1 rules: OPCO, TALENZ, OXYLEO, UNIM, SELARL annual documents, payroll.
- **Learned live (not in the seed):** the AGIPI split (PER vs Assurance Vie by insured person) and Hello bank → LMNP / Angers-Strasbourg / Banque / {fy}. `demo-reset` must restore the state *without* these rules active (the L5b seed tiers). The seed carries them only as disabled copies, the Apply-failure fallback (R11, D15).
- **Never filed before:** no AGIPI or Hello bank document is in the history, so both queue as first-seen counterparties (A17) and reach the debrief.
- **Already filed** ("overnight" history, journaled as earlier batches):
  - 8 DSN payroll documents (2a7f59091e07, 3bb97ca05844, bc1aa08e13ec, 804e66355f40, 18bd5e19bab9, a0315e754e52, b9c89da3fa92, 56d901f94557);
  - syn-sie-earlier and syn-supplier-earlier, so the live SIE letter and the rotated supplier scan have a filed predecessor and file (A17);
  - a personal tax notice (342bb6ec5672);
  - suppliers (4bda4dfe69d6, cfe8de908680, 0ee7c1361fce);
  - **syn-urssaf-call** (payment call due anchor + 3 days), which drives the Home brief and "what's due".
- **Empty Visitors entity.**
- **Pre-flight (T−10 min):**
  1. `mona doctor` all green.
  2. One warm-up chat turn, to fill the prompt cache on the chat slot.
  3. The browser on Home at 1440 wide, EN, light, zoom checked on the projector.
  4. The phone paired for the volunteered-document beat.

## Beats

| t | Beat | On screen | Documents | Fallback |
|---|---|---|---|---|
| 0:00 | **Meet Mona.** "Our back-office colleague. She lives on a box in the practice." | Home: `MonaBrief` ("filed N overnight, 2 need you, URSSAF due in 3 days"), action cards | pre-seeded state | Brief text is computed from the DB, so it can't fail on the model. If Home errors, open the Activity log |
| 0:45 | **The pile.** Drag 19 documents onto Intake. Mona starts; the pipeline animates | Intake: `BatchProgress`, `PipelineRow`s | live batch, **in this order**: 945a8bd4c054 (OPCO call, SELARL), syn-sie-letter, 79e0ba30cd98, 162ae8e85e14, 90f3898a7337, d6759080655c, syn-oxyleo-prep, 83ef9c3e34b2, 437dfdbb789d, syn-supplier-rotated, 110c37b2aaa1, 86c269dd3165, syn-agipi-per, d4e32792cb51, 03f336dd6ee3, 051809a11573, 2fa37b7d01cf, syn-unreadable, **syn-duplicate-urssaf** (a copy of the pre-filed one) | If the pipeline stalls: the same batch pre-filed from the snapshot (`demo-reset --prefiled`), shown in the Activity log |
| 1:30 | **The evidence** (key moment), while the batch keeps running. "Here's one she just filed, and why" | `DocumentViewer`: pdf.js with the highlighted amount and deadline; side panel with fields, the path, "rule that fired" | 945a8bd4c054 (first in the batch, so filed within ~15 s), then syn-urssaf-call (pre-filed, amount + due date) | If find misses: the `EvidenceSnippet` quotes in the side panel carry the story. Backups: 83ef9c3e34b2, syn-sie-letter |
| 3:15 | **Back to the pile.** "9 filed, 8 need you, 1 unreadable, 1 already had." Show the renamed files in the folder tree | Intake summary, `BatchQuestionsBanner` "Mona has N questions" (N from the rehearsed debrief: 5 in the FIX-3 build); Archive folders | — | If the batch isn't finished, narrate the rows still moving, then go on. The debrief works on whatever has queued |
| 4:00 | **Mona asks.** Debrief in chat | `InterviewCard` AGIPI: "split by insured person, PER vs life?" → answer → `RulePreviewCard` (3 move) → Apply. Then Hello bank → LMNP / Angers-Strasbourg / Banque / {fy} → preview (3 move) → Apply. UNIM confirmation if time allows | AGIPI: 110c37b2aaa1, 86c269dd3165, syn-agipi-per. Hello bank: d4e32792cb51, 03f336dd6ee3, 051809a11573. UNIM: 2fa37b7d01cf | The box runs `MONA_DEBRIEF_CACHE=prefer`: the debrief shown is Mona's own from a good rehearsal, kept in `demo` (D15). If Apply fails: Rules › Disabled › enable the seeded copy (AGIPI PER, AGIPI life insurance or Hello bank); its preview lists the same moves → Apply |
| 7:00 | **Ask Mona.** "How much did we pay AGIPI last year?" → total + `DocCard`s. "What's due this month?" → `DeadlineCard`. Switch to French: « Rédigez une réponse au SIE pour demander un échéancier » → `DraftCard` (Copy / Download, never Send) | Chat page, or the slide-over over Archive (shows "Mona can see…") | syn-sie-letter for the draft; the AGIPI trio for the sum | Tested prompts only, at most 2 tool calls each. If the model stalls: the same answers in the pre-recorded Activity/Archive views |
| 9:30 | **Volunteered document.** Claudiu photographs an attendee's paper letter; it goes into **Visitors**, purged after 24 h | Telegram owner bot → reply; the document appears in Intake | the live photo; syn-visitor-photo as the rehearsal stand-in | Telegram is deferred to a later testing session: until it lands, the fallback **is** the beat (upload from the phone browser to Intake) |
| 10:30 | **Trust.** "Everything is journaled and reversible." Undo the Hello bank rule application (one batch undo, the files move back), then Redo. Rules: "what Mona learned today" | Activity log (`ActivityBatch` → Undo whole batch); Rules | — | If undo errors: show the journal entries and their before/after paths |
| 11:30 | **Close.** Runs locally; nothing leaves the building; roadmap; waitlist QR | Settings › Privacy (`DataFlowDiagram`), then the deck | — | The deck slides |

## Timing budget and the latency risk

- S6 measured about **8 s per document** (p95 16 s) for classification with evidence quotes on OpenRouter. On mona, one GPU slot serves the pipeline and the other is kept free for chat, so 19 documents take about 3–4 minutes.
- The script is built for that: the batch runs *behind* the evidence beat and the return to Intake, and the debrief starts from whatever has queued.
- Target for L1/L6: ≤ 8 s per document on mona with pre-extracted text (the `demo-reset` snapshot carries the text and OCR caches for every live-batch document). Measure on Oct 8. If it's over, cut the live batch to 12 documents (drop 162ae8e85e14, d6759080655c, 437dfdbb789d, syn-supplier-rotated and two of the auto-files) rather than faking results.
- Chat turns must stay ≤ 10 s to the first visible thinking while the batch runs (plan §0 criterion 4).

## Never on stage

- 26520a11ac2f, 7ecdd3e1f290, 1c6df1fea1a3 and 30eb3d628163: official debt and recovery notices for a real company. The reply beat uses syn-sie-letter.
- d63283602f1d, d72832f72c86, 8abaaf8a8262 and 11820c325901: third-party documents.
- The personal documents with the family address in the header (AGIPI, OXYLEO): Claudiu's call (R4). Rehearse with and without them.

## Open for v2 (after L5b and the Oct 7 baseline)

- Real confidences from the L5b histogram. Check that the queue mix really lands at 7.
- Timings from the Oct 7 laptop walkthrough and the Oct 8–10 mona runs.
- The cached debrief and `--prefiled` snapshot mechanics: `mona stage-build` builds both, and demo/README.md has the rehearsal procedure (FIX-3).
- The runbook card for Claudiu (L6), EN/FR.
