# L1-M2: the pipeline core (intake → extract → classify → file)

Card **L1**, milestone 2. Agent: `coder`.

- **Worktree:** `~/DevFiles/mona-hq/.worktrees/l1-m2`, branch `l1-m2`, based on `main`.
- **Compose project:** `-p mona-l1b`, with `WEB_PORT=5573 API_PORT=9165 POSTGRES_PORT=55832 HERMES_PORT=9042`. Run `make check COMPOSE="docker compose -p mona-l1b"`.

Milestone 1 (on `main`) built the rules engine, templates, file ops and services. This card turns a dropped file into a filed or queued document, with evidence. The set B hooks (early debrief, the Visitors purge, reverting a rule when its apply group is undone) come in L1-M3 after set B freezes. Leave clean call sites for them.

## Read first

- `briefs/common.md` and `docs/decisions.md` (D1–D9; **D9: model calls default to the cheap `MONA_LLM_MODEL`**).
- `docs/contracts/amendments.md` A1–A8.
- **The frozen contracts:**
  - **C5 in full** (§1 pipeline, jobs, queues, caches, text extraction, page format; §5 model step; §6 verification and resolution; §7 `findQuery`; §9 confidence and bands; §11 tests);
  - C1 §4 (batches, intake items, documents, extractions, classifications, review items) and §6.2 (deadlines);
  - C7 §8.4 (intake dedupe).
- **M1's code on `main`:** `mona/services/README.md`, `mona/rules`, `mona/templates`, `mona/fileops`.
- **Notes from M1:** `~/DevFiles/mona-hq/orchestrator/l1-m2-notes.md` (wiring).
- **Spikes:** `docs/spikes/s6/` (request shapes, quote rules, the verifier, pydantic-ai `NativeOutput`); `apps/web/public/pdfjs/` (pdf.js 6.3.289, for `findQuery`).
- **Demo data:** `demo/expectations.yaml`, `demo/synthetic/` (generator + `docs.yaml`), `docs/demo-script.md`.

## Build

1. **Intake** `mona.pipeline.intake.ingest_file(...)`: bytes or path, source (`drop` | `telegram`), batch, visitor flag.
   - sha256 dedupe (C7 §8.4) and inbox placement.
   - Writes `documents`, `batches` and `intake_items`, then enqueues `extract_text`.
   - L2-P2 calls it from the upload endpoint and from `ingest_attachment`.
2. **Jobs** (C5 §1.2): `extract_text` (`cpu`), `render_thumbnail` (`cpu`), `classify_document` (`llm`, concurrency 1), `file_document` (`cpu`), with the stated priorities, retries and `pipeline_stage` transitions.
   - The review outcome ends at `done`.
   - Failure paths go to review.
   - The batch-done check uses the A8 lock.
   - Drop order is preserved.
3. **Caches** (C5 §1.3), keyed by sha256 under `/data/cache`:
   - page-delimited text (`pdftotext -layout` per page);
   - the OCR'd PDF (`ocrmypdf` with `fra+eng+ron`, rotate and deskew; images through `img2pdf`), with the archive keeping the original bytes;
   - the thumbnail (`pdftoppm -r 60`);
   - **the model-output cache**.
4. **Model step** (C5 §5), in one model client module:
   - the OpenRouter shape (`reasoning.enabled=false`; the D4 pins only when the model is Qwen 3.6) and the llama-server shape (`chat_template_kwargs.enable_thinking=false`), selected by settings;
   - pydantic-ai `NativeOutput` with `supports_json_schema_output=True`;
   - the per-request schema with registry enums;
   - the prompt skeleton, the context budget and cut order, exemplars, the re-keyed category definitions.
5. **After the model** (C5 §6–§9):
   - evidence verification: `norm()`, page correction to the one other page, typographic punctuation, `verified`;
   - resolution;
   - rules (M1);
   - fiscal year and templates (M1);
   - confidence, reasons, band;
   - **`findQuery`** per C5 §7;
   - then persist and hand off to filing or review.
   - Deadlines are created through M1's service.
6. **Wiring:**
   - `recover_pending()` at api and worker startup and as a 60 s periodic task;
   - `make_context()` at startup;
   - `mona pipeline run <files…>` for local runs.

## Tests and evidence

- **Deterministic tests use no network:** synthetic documents from `demo/synthetic/`, with **recorded model outputs** as fixtures, fed through the model-output cache path. CI never calls a model.
- **C5 §11 obligations** for this milestone, including test 14 (the six feedback cases end to end) on the synthetic stand-ins, and the [M] mutation checks (at least: the page-correction rule, `findQuery` normalisation, the band thresholds, the review-outcome stage, cache key and version checks).
- **`findQuery` against real pdf.js:** a Playwright check on `/dev/pdf` (extend it to load a given PDF) that every verified quote's `findQuery` highlights on its page, for every text-layer synthetic document. This is the harness L5c reuses on the rehearsed documents.
- **Live smoke** (cheap model, D9): run the 12 synthetic documents through the dev stack end to end. Report per-document timings and the OpenRouter spend delta.
- **One quality run** (Qwen 3.6, D9): the 19 live-batch documents from `docs/demo-script.md`, with practice documents read from `~/DevFiles/mona-hq/100 PDF neclasificate/` and synthetic ones rendered to `demo-data/`.
  - Record per-document latency (p50/p95), the band and reason outcomes against `demo/expectations.yaml`, and the verified-quote rate.
  - Outputs that contain practice text go to `~/DevFiles/mona-hq/demo-data/runs/`. The report gets counts and ids only.

## Don't

- No REST endpoints or MCP tools: that's L2-P2.
- No interview hooks, Visitors purge or apply-group rule revert: that's L1-M3.
- No contract changes: stop and report.
- Never send practice documents to a `:free` model.
