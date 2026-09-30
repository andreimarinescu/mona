# S6 — OpenRouter spike: thinking toggle, no-think json_schema, two-pass debrief, provider pins

Run on 2026-09-30 against `qwen/qwen3.6-35b-a3b` (fallback `qwen/qwen3.5-35b-a3b` surveyed, not needed). Total OpenRouter spend: **$0.41** (key usage), budget $3.

## Verdict

| S6 condition | Result |
|---|---|
| Thinking toggle | **Pass.** `reasoning: {enabled: false}` (or `effort: "none"`) gives 0 reasoning tokens on all 5 fp8 providers: 20/20 toggle requests, and 0 reasoning tokens on every no-think call in T3–T6. Nothing else turns it off. |
| Valid typed outputs (no-think json_schema) | **Pass.** v2 classification: 60/60 schema-valid across 6 routes, and every answered request valid. Extended evidence schema: 120/120 valid in the final run (one runaway-string failure in a first run, before `maxLength`, see T4), and 16/16 through pydantic-ai `NativeOutput`. |
| Debrief ≤ 60 s | **Pass, but only with the fast-provider order.** With the recommended provider order every run finished in 30–50 s (8/8 runs). With the first pin (Parasail first) it took 112 s. When a run fell back to Parasail mid-debrief it took 70 s. A time box on pass 1 bounds the worst case (below). |
| Provider pins hold | **Pass.** Routing trails show only pinned providers were tried. Fallback happens only inside `order`. The `require_parameters` and `quantizations` negative controls return 404. |

The S6 fallback (another provider, or `qwen3.5-35b-a3b`) is not needed.

## Recommended provider pin (dev)

```json
"provider": {
  "order": ["akashml", "coreweave", "siliconflow", "parasail", "deepinfra"],
  "allow_fallbacks": false,
  "require_parameters": true,
  "quantizations": ["fp8", "fp16", "bf16"]
}
```

- **Ordering.** Providers are ordered by measured decode speed: AkashML ≈230 tok/s, CoreWeave ≈140, SiliconFlow ≈115, Parasail ≈80, DeepInfra ≈50 (T7).
- **Parameter coverage.** All five support `response_format`, `structured_outputs` and `reasoning`, and every one of them is fp8.
- **Tool calls.** CoreWeave and SiliconFlow don't support `tools`. `require_parameters` skips them automatically on tool-calling (Hermes) requests: a tools request with CoreWeave and SiliconFlow ordered first was served by AkashML 3/3 times (T1b).
- **`allow_fallbacks: false`.** OpenRouter still walks the whole `order` list, but never leaves it. That is the stance we want:
  - Upstream 429s are common. AkashML returned `queue_timeout` on 4/10 requests in one burst, and Parasail on ~25% of requests in another.
  - A 429 fails over in ~0.2–0.3 s.
- **Excluded providers.**
  - Darkbloom: fp4.
  - Reka, Phala: quantization unknown.
  - Venice: no `response_format`.
  - AtlasCloud: no `structured_outputs`. With `json_schema` + `require_parameters` it 404s.
- **Not tested:** `data_collection: "deny"` / `zdr`. R30 allows anything in dev.

For Hermes, this is the `provider` block in its OpenRouter config. S1/S2 own the exact key.

## Which knob turns thinking off

| Request knob | Reasoning tokens (3 providers × 2 reps) | Reasoning text returned | Median wall |
|---|---|---|---|
| none (default: thinking **on**) | 799–1136 | 6/6 | 19.0 s |
| `reasoning: {enabled: false}` | **0** | 0/6 | 0.75 s |
| `reasoning: {effort: "none"}` | **0** | 0/6 | 0.78 s |
| `reasoning: {effort: "low"}` | 634–3219 (still on; 1 run hit `max_tokens` with empty content) | 5/6 | 20.8 s |
| `reasoning: {max_tokens: 256}` | 695–1197 (budget ignored by every provider) | yes | 15.0 s (Parasail) |
| `reasoning: {exclude: true}` | 756–1028 (hidden, still billed and slow) | 0/6 | 19.9 s |
| `include_reasoning: false` | 706–1603 (same as exclude) | 0/6 | 21.2 s |
| `chat_template_kwargs: {enable_thinking: false}` | 724–1135 (ignored by OpenRouter) | 6/6 | 18.5 s |
| `/no_think` in the prompt | 728–829 (ignored by Qwen 3.6) | 6/6 | 19.9 s |

CoreWeave and SiliconFlow behave the same (`results/t2_thinking_extra.json`).

- **Thinking is binary on OpenRouter.** Effort levels and reasoning budgets are not honoured for this model. The only way to bound a thinking pass is to stop reading the stream.
- **`usage.completion_tokens_details.reasoning_tokens` under-counts.** It runs about 60–80% of the non-content completion tokens. Cost and latency follow `completion_tokens`.
- **llama-server equivalent** (plan §3): per request, `chat_template_kwargs: {"enable_thinking": false}`. The adapter maps one internal flag `thinking: bool` to:
  - OpenRouter: `reasoning: {enabled: <bool>}`;
  - llama-server: `chat_template_kwargs: {enable_thinking: <bool>}`.

  Each backend ignores the other's knob. OpenRouter ignores `chat_template_kwargs`, as shown above.

## Recommended request shapes

**Typed output (classification, extraction, debrief pass 2): thinking off + strict json_schema**
```json
{"model": "qwen/qwen3.6-35b-a3b", "temperature": 0, "max_tokens": 2000,
 "reasoning": {"enabled": false},
 "response_format": {"type": "json_schema", "json_schema": {"name": "extraction", "strict": true, "schema": {…}}},
 "provider": {…pin…}}
```
- On llama-server, swap `reasoning` for `"chat_template_kwargs": {"enable_thinking": false}`.
- Put `maxLength` on every free-text string (T4, below).

**Thinking pass (debrief pass 1, Hermes turns):** `"reasoning": {"enabled": true}`, `temperature: 0.6`, streamed.
- The reasoning arrives in `delta.reasoning` (plus `reasoning_details`), and the answer in `delta.content`.
- Hermes re-emits reasoning as `delta.reasoning_content` (D3).
- Set `max_tokens` well above the reasoning (≥ 8k). Otherwise the model can spend the whole budget thinking and return empty content (seen in T2).

**pydantic-ai** (2.52.0), from `t5_pydantic_ai.py`:
```python
model = OpenRouterModel("qwen/qwen3.6-35b-a3b", provider=OpenRouterProvider(api_key=...),
                        profile={**provider.model_profile(MODEL), "supports_json_schema_output": True})
agent = Agent(model, output_type=NativeOutput(Extraction, strict=True), instructions=...)
await agent.run(prompt, model_settings={
    "temperature": 0, "max_tokens": 2000,
    "openrouter_reasoning": {"enabled": False},     # or the unified "thinking": False → effort "none"
    "openrouter_provider": {…pin…},
    "openrouter_usage": {"include": True},          # cost in result.response.provider_details["cost"]
})
```
- **Profile flag.** The OpenRouter profile for Qwen doesn't set `supports_json_schema_output`, so it has to be set to get `NativeOutput`. The llama-server profile needs it too (plan §2.1).
- **OpenAI-compatible path.** With a plain `OpenAIChatModel` (the llama-server path), everything goes in `model_settings["extra_body"]`:
  - OpenRouter: `{"reasoning": {...}, "provider": {...}}`;
  - llama-server: `{"chat_template_kwargs": {"enable_thinking": False}}`.
- **Verified request bodies.** All three styles were captured on the wire. Each carries `reasoning` and `provider` and a strict `json_schema` (`results/t5_pydantic_ai.json`, field `request`).
- **Deprecation.** pydantic-ai 2.52 deprecates passing an `httpx.AsyncClient` to providers. The request-capture hook uses one; the app shouldn't.

## Results

The practice documents are referred to by `sha256[:12]`. The sample has 10 documents with ground-truth categories from `classified/review.md`:
- `d946beb4fc08` personal questionnaire;
- `90f3898a7337` accountant approval-of-accounts letter;
- `110c37b2aaa1` insurer/pension notice (21 pp);
- `945a8bd4c054` training-fund payment call;
- `aaf7383d5692` bank letter;
- `2fa37b7d01cf` insurance notice;
- `8701e7c358dc` supplier invoice;
- `c8bea28024ed` car-rental receipt;
- `0ee7c1361fce` local purchase invoice;
- `437dfdbb789d` payroll declaration (DSN).

Raw responses, page texts and quotes live in `~/DevFiles/mona-hq/demo-data/spikes/s6/`.

### T1 — models and endpoints (`t1_models.py`, `results/t1_models.json`)

| | qwen3.6-35b-a3b | qwen3.5-35b-a3b |
|---|---|---|
| Context | 262,144 | 262,144 |
| List price $/M in / out | 0.15 / 1.00 | 0.1625 / 1.30 |
| Reasoning | optional, **default on** | optional |
| Endpoints | 10 | 7 |
| fp8+ with rf + so + reasoning (+ tools) | AkashML, Parasail, DeepInfra (+ tools); CoreWeave, SiliconFlow (no tools) | Parasail, AtlasCloud (+ tools); DeepInfra, SiliconFlow (no tools) |

qwen3.6 endpoint max output tokens:
- AkashML, Parasail, CoreWeave, SiliconFlow: 235,929.
- DeepInfra: 16,384.

### T1b — do pins hold? (`t1b_pins.py`, `results/t1b_pins.json`)

- The "first pin" used for T1b and T3–T5 is `order: [parasail, deepinfra, akashml]` (`_or.PROVIDER_PIN`), with the same other keys as the recommended pin.
- 12/12 requests per run were served by pinned providers, in 2 runs. In the first run, 4/12 fell over from Parasail (429) to DeepInfra, per the routing trail from `/api/v1/generation`. The second run is in the results file (12/12 Parasail).
- Negative controls:
  - `only: [venice]` + `json_schema`, `only: [atlas-cloud]` + `json_schema`, `only: [reka]` + fp8+ and `only: [darkbloom]` + fp8+ all return 404 ("no endpoints").
  - Nothing leaks outside the pin.

### T3 — v2 prompt, strict json_schema, thinking off (`t3_classify.py`)

The v2 SYSTEM, SCHEMA and request shape are loaded at runtime from `classify/classify_llm.py`. The prompt names real people, so it stays out of the repo. Text is the cached first-2-pages text, truncated to 3000 chars as in v2.

| Route | Served by | Schema-valid | Category = ground truth | p50 | p95 | Cost (10 docs) |
|---|---|---|---|---|---|---|
| pin | Parasail (9), DeepInfra (1, 429 fallover) | 10/10 | 10/10 | 2.5 s | 4.4 s | $0.0020 |
| parasail | Parasail | 10/10 | 10/10 | 2.2 s | 3.8 s | $0.0022 |
| deepinfra | DeepInfra | 10/10 | 9/10 | 5.5 s | 6.1 s | $0.0023 |
| akashml | AkashML | 10/10 | 10/10 | 1.1 s | 1.7 s | $0.0020 |
| coreweave | CoreWeave | 10/10 | 10/10 | 1.3 s | 2.9 s | $0.0045 |
| siliconflow | SiliconFlow | 10/10 | 10/10 | 2.9 s | 4.5 s | $0.0050 |

- Reasoning tokens were 0 on every request.
- A first run had AkashML answer only 6/10: four HTTP 429 `queue_timeout` responses from its shared pool. All 6 answers were valid.
- Every *answered* request has been schema-valid.

### T4 — evidence variant, C5 preview (`t4_evidence.py`, `_evidence.py`)

**Setup.**
- Pages 1–3 (`pdftotext -f N -l N`) go to the model with page markers, 4000 chars per page.
- The extended schema has `entity_hint`, `category`, `counterparty`, `doc_type`, `doc_date`, `period_start`, `period_end`, `amount` (+ `currency`), `due_date` and `addressee`. Each is `{value, quote, page}` or null. Plus `confidence`.
- Nullable fields use `anyOf [object, null]`. Strict mode accepted it on all three pinned providers.
- 10 docs × 2 reps per variant, thinking off, pin order.

**Verification** (`_evidence.verify`, unit-tested in `test_evidence.py`):
- Whitespace (incl. U+00A0 and U+202F), case and diacritics are normalised, then the quote is substring-matched on the stated page.
- A failed quote is classified as: found on another page (`wrong_page`), matches after unifying typographic punctuation, matches after removing all whitespace (`ocr_spacing`), ≥ 0.85 similar (`near_miss`), or `paraphrase`.

| Variant | Valid | Category ok | Quotes verified | + page repair¹ | Failure causes | p50 / p95 |
|---|---|---|---|---|---|---|
| p0: markers, layout, "verbatim quote + page" | 20/20 | 20/20 | 89/145 (61%) | 65% | paraphrase 36, near-miss 14, wrong page 6 | 11.2 / 18.7 s |
| **p1: markers, layout, strict quote rules²** | 20/20 | 18/20 | **135/148 (91%)** | **95%** | wrong page 5, near-miss 5, paraphrase 3 | 8.0 / 16.0 s |
| p1, `<page number="n">` tags | 20/20 | 19/20 | 128/146 (88%) | 92% | wrong page 7, near-miss 7, paraphrase 4 | 8.2 / 21.8 s |
| p1, markers, raw (non-layout) text | 20/20 | 16/20 | 131/148 (89%) | 93% | paraphrase 8, wrong page 7, near-miss 2 | 8.4 / 17.1 s |
| p1, tags, `maxLength` 160 | 20/20 | 19/20 | 132/147 (90%) | 94% | wrong page 6, near-miss 6, paraphrase 3 | 7.2 / 18.5 s |
| p1, tags, maxLength, evidence-first key order | 20/20 | 18/20 | 129/143 (90%) | 93% | near-miss 6, wrong page 4, paraphrase 2, OCR spacing 2 | 8.2 / 18.5 s |

¹ The server relocates `page` when the normalised quote occurs on exactly one other page.

² p1 rules:
- a 3–12-word span from ONE line, copied character for character, including OCR errors;
- never reformat dates or amounts in the quote (`value` is normalised);
- `page` = the nearest marker above;
- null when there is no supporting span.

Cost: ≈ $0.013 per 20 extractions.

Per field, best variant (p1 markers):

| Field | Verified |
|---|---|
| entity_hint | 16/18 |
| category | 19/20 |
| counterparty | 17/18 |
| doc_type | 18/20 |
| doc_date | 14/14 |
| period_start | 11/12 |
| period_end | 9/12 |
| amount | 14/14 |
| due_date | 3/4 |
| addressee | 14/16 |

**What moved the rate.** The quote rules took verification from 61% to 91%. Without them, the model quotes the *normalised* value ("2025-04-14" for "14/04/2025", "520.00" for "520,00 €") and writes descriptive "quotes" for category and entity. Page tags vs markers, raw vs layout text, and evidence-first key order are all within noise (88–91%). Raw text cost category accuracy (16/20).

**Main residual causes (p1 variants):**
- **Wrong page (~5%).**
  - `437dfdbb789d`: the addressee/entity on page 2 is attributed to page 1 in 10/10 runs.
  - `110c37b2aaa1`: the period end sits on a later page.
  - Page repair recovers these deterministically.
- **Near miss: the model "corrects" OCR noise.** For example, it restores letters in a garbled supplier name, or normalises the "N°"/":" spacing in a reference. Common on `c8bea28024ed` (a scanned multi-column receipt) and `8701e7c358dc`.
- **Layout stitching.** In `-layout` output, table headers and their values sit in different columns. The model joins a header with a value from another column into one "quote" (`c8bea28024ed` period end).
- **Runaway free text.** Once, in a p0 run before `maxLength` was added, DeepInfra wrote its reasoning into a `quote` string until `max_tokens` (thinking was off). The output was truncated JSON. `maxLength` on strings prevents this class of failure. No recurrence in 120 later extractions.

### T5 — pydantic-ai `NativeOutput` (`t5_pydantic_ai.py`, pydantic-ai **2.52.0**)

Same extended schema as pydantic models (`extra="forbid"`, `max_length`, date `pattern`, `Literal` category), p1 rules, page tags.

| Style | Docs | Valid (pydantic-validated) | Category ok | Quotes verified | Reasoning tok | Median wall |
|---|---|---|---|---|---|---|
| `OpenRouterModel` + `openrouter_reasoning` / `openrouter_provider` | 10 | 10 | 9 | 66/74 | 0 | 7.6 s |
| `OpenRouterModel` + unified `thinking: False` | 3 | 3 | 3 | 19/20 | 0 | 7.5 s |
| `OpenAIChatModel` + `extra_body` | 3 | 3 | 3 | 16/19 | 0 | 5.5 s |

### T6 — two-pass debrief, synthetic (`t6_debrief.py`, `debrief/cluster.json`, `debrief/outputs/`)

**Cluster.** 7 fictional documents with a registry of 2 business entities (SELARL, LMNP) and 2 people:
- one insurer covering the owner (paid by the SELARL, or personally) and her spouse;
- a joint bank account not in the registry that receives LMNP rent;
- a carpenter serving both the practice and the flat;
- an internet line at the flat billed to the spouse.

**Pass 1** (thinking on, streamed): free-form analysis. The concise variant asks for ≤ 250 words of bullets.

**Pass 2** (thinking off, strict json_schema): `{questions: InterviewQuestion[≤7]}`. Each question has:
- `text` in the locale;
- `evidence[{doc_id, quote}]`;
- `affected_doc_ids`;
- `impact`;
- 2–3 `options`, each with a `rule_draft`;
- `suggested_option_id`.

The enums (doc ids, entity ids, categories, condition fields) come from the registry. `test_debrief.py` checks the schema and the semantic checks.

**Runs with the recommended order** (`akashml, coreweave, siliconflow`), concise pass 1:

| Run | Pass 1 (provider, completion / reasoning tok) | Pass 2 | Total | Valid | Questions | Evidence quotes verified |
|---|---|---|---|---|---|---|
| en #1 | 20.8 s (AkashML, 4306 / 3334) | 9.3 s | **30.0 s** | yes | 3 | 7/7 |
| en #2 | 40.5 s (AkashML, 6158 / 4842) | 8.9 s | **49.4 s** | yes | 4 | 7/7 |
| en #3 | 32.2 s (AkashML, 4718 / 3722) | 8.8 s | **41.0 s** | yes | 3 | 7/7 |
| fr | 27.3 s (AkashML, 4366 / 3313) | 11.4 s | **38.6 s** | yes | 3 | 6/6 |
| en, AkashML removed (#1) | 23.7 s (CoreWeave, 4613 / 4196) | 9.0 s | **32.7 s** | yes | 3 | 6/6 |
| en, AkashML removed (#2) | 38.8 s (CoreWeave, 7012 / 6526) | 10.1 s | **48.9 s** | yes | 3 | 7/7 |
| en, branch rule shape | 23.7 s (AkashML) | 9.0 s | **32.7 s** | yes | 4 | 9/9 |
| fr, branch rule shape | 31.4 s (AkashML) | 18.2 s | **49.6 s** | yes | 3 | 7/7 |

Each run costs ≈ $0.006–0.012.

**Other configurations:**
- **First pin, Parasail first:** 86.2 s + 25.4 s = **111.7 s** (valid, 4 questions).
- **AkashML-first with Parasail as the fallback**, 5 runs: four took 26.4–46.6 s and one took **70.4 s**. In that run pass 1 took 50 s (6604 tokens) and pass 2 fell over to Parasail.
- **Time box `--pass1-budget 35`:** pass 1 stops reading the stream at 35 s, and pass 2 gets the partial reasoning as "working notes". 3 runs: 38.2 s, 37.1 s and 33.7 s.
  - In the 38.2 s run pass 1 had fallen over to Parasail and was cut. Pass 2 still returned a valid card, but only 1 question.
  - The time box guarantees the budget and degrades quality instead of time.

**Are the questions sensible?** Yes, on every run:
- All three real ambiguities were found and all 7 documents covered, in ≤ 5 questions, with the higher-impact groups first:
  - insurer by insured person;
  - carpenter by site;
  - the bank account and telecom line at the flat (LMNP vs personal).
- Every evidence quote matched the document snippets exactly.
- FR runs are idiomatic.

**Rule-draft weaknesses** of the brief's single-action shape `{kind, discriminator?, conditions[], action}`:
- It can't express a split such as "d1/d3 → SELARL, d2 → Paul". Options like that were emitted as `always` with one action.
- The conditions were loose (`doc_type = facture` for a counterparty-specific rule).
- "Personal" came out as `entity: null` instead of the person's id.

The **branch shape** (below) fixed all three in both runs.

**P0-3: pass 2 with thinking on + json_schema** (1 run, `debrief/outputs/dbr-pass2-thinking-on.json`):
- The model spent 4556 reasoning tokens, then hit `max_tokens` (6000) partway through the JSON.
- `finish_reason: length`, unterminated JSON, invalid.
- Grammar-constrained content still started correctly, but the reasoning ate the budget. With a smaller `max_tokens` the content is empty.
- **The two-pass split with pass 2 no-think is required.**

### T7 — streaming latency (`t7_streaming.py`, short chat prompt, 3 reps; `results/t7_streaming_extra.json` for CoreWeave/SiliconFlow, 2 reps)

| Route | Mode | First reasoning token | First content token | Total | Decode tok/s |
|---|---|---|---|---|---|
| akashml | think | 0.61 s | 8.9 s | 9.2 s | 232 |
| akashml | no-think | – | 0.38 s | 0.64 s | 233 |
| coreweave | think | 0.54 s | 6.2 s | 6.5 s | 139 |
| coreweave | no-think | – | 0.45 s | 0.88 s | 99 |
| siliconflow | think | 0.89 s | 10.6 s | 11.0 s | 115 |
| siliconflow | no-think | – | 1.08 s | 1.56 s | 115 |
| parasail | think | 0.49 s | 10.6 s | 11.4 s | 81 |
| parasail | no-think | – | 0.46 s | 0.77 s | 156 |
| deepinfra | think | 0.85 s | 16.7 s | 17.8 s | 50 |
| deepinfra | no-think | – | 0.63 s | 1.58 s | 50 |
| first pin | think | 0.67 s | 12.0 s | 12.8 s | 82 |
| first pin | no-think | – | 0.49 s | 1.22 s | 53 |

- **Thinking-mode timings.** The first reasoning token arrives in < 1 s everywhere, which is well inside the S5 "thinking visible ≤ 10 s" budget. Visible content waits for the whole thinking pass: 6–17 s here for ~700–1200 tokens.
- **Stream fields.** Reasoning streams as `delta.reasoning` + `delta.reasoning_details`.
- **Decode speeds** for thinking-mode runs include the reasoning tokens.

## Implications for C5 (extraction/classification)

- **No-think.** Every typed call sends `reasoning: {enabled: false}` (llama-server: `chat_template_kwargs.enable_thinking=false`) with strict json_schema. Every answered request was schema-valid except the single runaway string described in T4, which came before `maxLength` was added.
- **Evidence shape.** `{value, quote, page}` per field, with nullable fields as `anyOf [object, null]`, works in strict mode.
- **String bounds.** Put `maxLength` on every string (quote 160) so a no-think model can't run away inside a string.
- **Page-delimited text.** Send pages 1..N with markers. Page tags performed no better than markers.
- **Adopt the p1 quote rules in the C5 prompt:** a verbatim span from one line, no reformatting, `page` = the nearest marker, null if unsupported.
- **Verification** (the `_evidence.verify` normaliser: whitespace incl. U+00A0/U+202F, case, diacritics):
  - Relocate `page` when the quote occurs on exactly one other page; record it as verified with the page corrected.
  - Treat near-misses (≥ 0.85 similarity) as `verified=false` but highlightable via `findQuery` fuzzy search. Expect ~91% exact and ~95% with page repair on real documents.
  - Normalise typographic punctuation (’ vs ') in the verifier as well.
- **Keep `-layout` text for the model.** Raw text reads worse for category (16/20 vs 18–20/20). The page text used for verification must be the same extraction that was sent.

## Implications for C6 (interview protocol)

- **Two passes are mandatory.**
  - Pass 1: thinking on, streamed.
  - Pass 2: thinking off, strict json_schema.
  - Thinking + json_schema fails (P0-3 reproduced).
- **Latency.** With the recommended pin, generation takes 30–50 s. `start_interview` must enqueue and poll, as already planned. The llama-server slot on mona will be slower than AkashML: re-measure at the Oct 8 perf check.
- **Time box.** Stream pass 1 with a time box of ~35–40 s. If the stream is cut, feed pass 2 the reasoning text as notes. Quality degrades, time doesn't.
- **Rule drafts.** Replace the single-action `rule_draft` with branches: `{kind: always|depends|ask, discriminator, branches: [{conditions[], action}]}`.
  - `always` has one branch, `depends` one branch per discriminator value, and `ask` none.
  - Each branch is scoped by a counterparty condition.
- **Discriminator.** Make `discriminator` an enum of the condition fields. The model used free-text names such as `souscripteur` and `adresse_chantier`.
- **Registry enums.** Build the schema's enums from the registry at request time (entity ids, category ids, condition fields, doc ids).
- **Person entities.** "Personal" maps to a person entity, never null.
- **Semantic checks after schema validation:**
  - evidence quotes ⊂ snippets;
  - `suggested_option_id` ∈ options;
  - `depends` ⇒ discriminator present;
  - every uncertain doc is covered.

## Running

- All scripts are uv scripts (inline deps). Run them from this directory, e.g. `uv run t3_classify.py`.
- They read `OPENROUTER_API_KEY` from `~/DevFiles/mona-hq/mona/.env`.
- Spend is logged to `demo-data/spikes/s6/spend.jsonl`, and calls stop at $2.50.
- Tests: `uv run test_evidence.py`, `uv run test_debrief.py`.
- Results: `results/*.json` hold statistics only (no document text). `debrief/outputs/` holds the synthetic debrief outputs.
