"""C5 §1.4, §5, §6.1, §7: extraction, prompt, schema, model request, evidence and findQuery."""

import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from mona.pipeline import cache, extract
from mona.pipeline import prompt as prompts
from mona.pipeline.evidence import check, field_confidence
from mona.pipeline.findquery import find_query
from mona.pipeline.model import D4_PIN, QWEN36, LlmClient, SchemaInvalid, extra_body
from mona.pipeline.schema import Field, build, clean, errors, strings_bounded
from tests.pipeline_world import RECORDED, SYNTHETIC, Tools, mini_pdf


@pytest.fixture
def demo_schema(l1m2_demo_engine):
    from mona.pipeline.classify import request_schema
    from mona.services import registry

    with l1m2_demo_engine.connect() as conn:
        return request_schema(registry.load(conn))


SCHEMA = build(["insurance", "bank", "tax"], ["insurance.per", "bank.releve"], ["cabinet", "lmnp"])


def f(key: str, quote: str, page: int = 1, value: str = "x") -> Field:
    kw: dict = {}
    if key == "amount":
        kw = {"amount": Decimal(value), "currency": "EUR"}
    elif key in ("doc_date", "period_start", "period_end", "due_date"):
        kw = {"day": date.fromisoformat(value)}
    return Field(key, value, quote, page, **kw)


# --- §6.1 evidence verification [M] ---

PAGES = ["AGIPI\nAvis d'échéance\nMontant : 1 284,00 €", "Contrat PER-4411\nDate : 14/04/2025",
         "Contrat PER-4411 rappel"]  # fmt: skip


def test_verbatim_quote_on_the_stated_page():
    c = check(f("doc_type", "Avis d'échéance"), PAGES)
    assert (c.verified, c.page, c.stated_page) == (True, 1, 1)


def test_quote_on_exactly_one_other_page_is_relocated():
    c = check(f("doc_date", "Date : 14/04/2025", page=1, value="2025-04-14"), PAGES)
    assert (c.verified, c.page, c.stated_page) == (True, 2, 1)


def test_quote_on_two_other_pages_is_not_found():
    c = check(f("reference", "Contrat PER-4411", page=1), PAGES)
    assert (c.found, c.verified, c.page) == (False, False, 1)


def test_stated_page_wins_over_other_pages():
    assert check(f("reference", "Contrat PER-4411", page=3), PAGES).page == 3


@pytest.mark.parametrize(
    "quote",
    ["Montant : 1 284,00 €", "Montant : 1 284,00 €", "MONTANT : 1 284,00 €"],
)
def test_spacing_and_case_variants_verify(quote):
    assert check(f("amount", quote, value="1284.00"), PAGES).verified


def test_typographic_punctuation_folds():
    pages = ["L’avis d'échéance n° 2025-12 − solde"]
    assert check(f("doc_type", "L'avis d’échéance n° 2025‐12 - solde"), pages).verified


def test_paraphrase_and_short_quotes_fail():
    assert not check(f("doc_type", "Avis de paiement"), PAGES).verified
    assert not check(f("doc_type", "Av"), PAGES).found


def test_amount_value_check():
    assert check(f("amount", "Montant : 1 284,00 €", value="1284.00"), PAGES).verified
    wrong = check(f("amount", "Montant : 1 284,00 €", value="1248.00"), PAGES)
    assert wrong.found and not wrong.verified


@pytest.mark.parametrize(
    "quote",
    ["le 14/04/2025", "le 14.04.2025", "le 14-04-2025", "2025-04-14", "le 14/04/25",
     "le 14 avril 2025", "14 avr. 2025", "April 14 2025 was 14 April 2025", "14 aprilie 2025",
     "14 apr. 2025"],
)  # fmt: skip
def test_each_date_form(quote):
    c = check(f("doc_date", quote, value="2025-04-14"), [quote])
    assert c.verified, quote


def test_first_of_month_with_er_and_abbreviated_months():
    assert check(
        f("doc_date", "le 1er févr. 2026", value="2026-02-01"), ["le 1er févr. 2026"]
    ).verified
    assert check(f("doc_date", "le 1 sept. 2026", value="2026-09-01"), ["le 1 sept. 2026"]).verified


def test_wrong_date_fails_the_value_check():
    c = check(f("due_date", "le 14/04/2025", value="2025-04-15"), ["le 14/04/2025"])
    assert c.found and not c.verified


@pytest.mark.parametrize(
    ("key", "quote", "value", "fy_end", "ok"),
    [("period_end", "exercice 2025", "2025-12-31", None, True),
     ("period_end", "exercice 2025", "2025-09-30", (9, 30), True),
     ("period_start", "exercice 2025", "2024-10-01", (9, 30), True),
     ("period_start", "exercice 2025", "2025-01-01", None, True),
     ("period_end", "exercice 2025", "2025-06-30", None, False),
     ("period_start", "relevé de décembre 2025", "2025-12-01", None, True),
     ("period_end", "relevé de décembre 2025", "2025-12-31", None, True),
     ("period_end", "relevé de février 2024", "2024-02-29", None, True),
     ("doc_date", "exercice 2025", "2025-12-31", None, False)],
)  # fmt: skip
def test_period_forms(key, quote, value, fy_end, ok):
    assert check(f(key, quote, value=value), [quote], fy_end).verified is ok


def test_field_confidence_caps_unverified_at_40():
    got = (field_confidence(92, True), field_confidence(92, False), field_confidence(30, False))
    assert got == (
        92, 40, 30,
    )  # fmt: skip


# --- §7 findQuery ---


def test_single_line_quote_is_the_whole_quote():
    page = "Objet : Appel de cotisations, 3e trimestre 2026.\nsuite"
    c = check(f("doc_type", "Appel de cotisations, 3e trimestre 2026."), [page])
    assert find_query(c, page) == "Appel de cotisations, 3e trimestre 2026"


def test_quote_spanning_two_lines_gives_the_longest_single_line_run():
    page = "Nous vous informons que le prochain versement sur votre plan\nd'épargne retraite est dû"
    quote = "prochain versement sur votre plan d'épargne retraite"
    c = check(f("doc_type", quote), [page])
    assert c.verified and find_query(c, page) == "prochain versement sur votre plan"


def test_amount_falls_back_to_the_number_token():
    page = "Montant\n480,00"
    c = check(f("amount", "Montant 480,00", value="480.00"), [page])
    assert c.verified and find_query(c, page) == "480,00"


def test_date_falls_back_to_the_printed_date():
    page = "Payable\n14/04/2025"
    c = check(f("due_date", "Payable 14/04/2025", value="2025-04-14"), [page])
    assert c.verified and find_query(c, page) == "14/04/2025"


def test_unverified_gives_null():
    page = "Montant : 1 284,00 €"
    assert (
        find_query(check(f("amount", "Montant : 1 248,00 €", value="1248.00"), [page]), page)
        is None
    )


def test_original_accents_kept_and_edges_trimmed():
    page = "Votre référence : « ÉCHÉANCE-2025 » ; merci"
    c = check(f("reference", "référence : « ÉCHÉANCE-2025 » ;"), [page])
    assert find_query(c, page) == "référence : « ÉCHÉANCE-2025 »"


def test_find_query_is_capped_at_a_word_boundary():
    words = " ".join(f"mot{i}" for i in range(40))
    c = check(f("doc_type", words), [words])
    q = find_query(c, words)
    assert q is not None and len(q) <= 120 and words.startswith(q) and not q.endswith(" ")
    assert words[len(q)] == " "


def test_find_query_normalisation_uses_norm():
    # [M] target: without norm() on both sides the curly apostrophe and NBSP miss the line.
    page = "L’avis d’échéance du contrat"
    c = check(f("doc_type", "L'avis d'échéance du contrat"), [page])
    assert find_query(c, page) == "L'avis d'échéance du contrat"


# --- §5.2 schema and §5.1 request ---


def test_every_string_is_bounded():
    assert strings_bounded(SCHEMA)
    loose = json.loads(json.dumps(SCHEMA))
    loose["properties"]["reason"].pop("maxLength")
    assert not strings_bounded(loose)


def test_schema_enums_and_nullable_evidence():
    props = SCHEMA["properties"]
    assert props["category"]["enum"] == ["insurance", "bank", "tax", "unknown"]
    assert props["entity"]["anyOf"][0]["properties"]["value"]["enum"] == ["cabinet", "lmnp"]
    amount = props["amount"]["anyOf"][0]
    assert list(amount["properties"]) == ["value", "currency", "quote", "page"]
    assert SCHEMA["additionalProperties"] is False and set(SCHEMA["required"]) == set(props)


@pytest.mark.parametrize("doc_id", sorted(RECORDED["outputs"]))
def test_recorded_outputs_validate_against_the_demo_schema(doc_id, demo_schema):
    assert errors(RECORDED["outputs"][doc_id], demo_schema) == []


def _raw(**over):
    raw = {k: None for k in SCHEMA["properties"]}
    raw |= {"title": " AGIPI  avis ", "category": "insurance", "subcategory": "insurance.per",
            "confidence": 0.9, "reason": "r"}  # fmt: skip
    return raw | over


def test_schema_rejects_unknown_keys_bad_enums_and_long_strings():
    assert errors(_raw(), SCHEMA) == []
    assert errors(_raw(extra=1), SCHEMA)
    assert errors(_raw(category="travel"), SCHEMA)
    assert errors(_raw(title="x" * 121), SCHEMA)
    ev = {"value": "2025-02-30", "quote": "q", "page": 0}
    assert errors(_raw(doc_date=ev), SCHEMA)


def test_clean_drops_foreign_subcategory_and_impossible_dates():
    out = clean(_raw(subcategory="bank.releve",
                     doc_date={"value": "2025-02-30", "quote": "30/02/2025", "page": 1},
                     due_date={"value": "2025-03-01", "quote": "01/03/2025", "page": 1},
                     amount={"value": 1284, "currency": "EUR", "quote": "1 284 €", "page": 1},
                     counterparty={"value": "  AGIPI \n Vie ", "quote": "AGIPI",
                                   "page": 1}))  # fmt: skip
    assert out.subcategory is None
    assert "doc_date" not in out.fields and out.fields["due_date"].value == "2025-03-01"
    assert out.fields["amount"].value == "1284.00"
    assert out.fields["counterparty"].value == "AGIPI Vie"
    assert out.title == "AGIPI avis"
    assert clean(_raw()).subcategory == "per"


def _mock_client(model: str, backend: str, reply: dict | str):
    sent: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(json.loads(req.content))
        content = reply if isinstance(reply, str) else json.dumps(reply)
        body = {"id": "x", "object": "chat.completion", "created": 0, "model": model,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7,
                          "total_tokens": 18}}  # fmt: skip
        return httpx.Response(200, json=body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    url = "http://llama:8080/v1" if backend == "llama-server" else None
    return LlmClient(
        model=model, backend=backend, base_url=url, api_key="k", http_client=http
    ), sent


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.parametrize(
    ("model", "backend", "knobs"),
    [("qwen/qwen3.7-flash", "openrouter", {"reasoning": {"enabled": False}}),
     (QWEN36, "openrouter", {"reasoning": {"enabled": False}, "provider": D4_PIN}),
     (QWEN36, "llama-server", {"chat_template_kwargs": {"enable_thinking": False}})],
)  # fmt: skip
def test_request_shape_per_backend(model, backend, knobs):
    client, sent = _mock_client(model, backend, _raw())
    result = client.complete("SYSTEM", "USER", SCHEMA)
    body = sent[0]
    assert result.raw["category"] == "insurance" and result.prompt_tokens == 11
    assert body["temperature"] == 0 and body["max_tokens"] == 2000
    rf = body["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "mona_extraction"
    sent_props = rf["json_schema"]["schema"]["properties"]
    assert sent_props["reason"]["maxLength"] == 250 and strings_bounded(rf["json_schema"]["schema"])
    assert {k: body[k] for k in knobs} == knobs
    other = {"reasoning", "provider", "chat_template_kwargs"} - set(knobs)
    assert not other & set(body)
    assert body["messages"][0] == {"role": "system", "content": "SYSTEM"}


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_invalid_output_is_schema_invalid():
    client, _ = _mock_client("qwen/qwen3.7-flash", "openrouter", _raw(category="travel"))
    with pytest.raises(SchemaInvalid):
        client.complete("S", "U", SCHEMA)
    client, _ = _mock_client("qwen/qwen3.7-flash", "openrouter", "{not json")
    with pytest.raises(SchemaInvalid):
        client.complete("S", "U", SCHEMA)


def test_free_models_are_refused():
    with pytest.raises(ValueError, match="free"):
        LlmClient(model="qwen/qwen3.7-flash:free")


def test_extra_body_pins_only_qwen36():
    assert "provider" not in extra_body("openrouter", "qwen/qwen3.7-flash")
    assert extra_body("openrouter", QWEN36)["provider"] == D4_PIN


# --- §5.3–§5.4 prompt (pure) ---


def _sections(pages, exemplars=5, rules=30):
    return prompts.Sections(
        practice_name="Cabinet Marchand", language="fr",
        entities=("- cabinet: Cabinet Marchand SELARL (SELARL). Names on documents: . People: .",),
        categories=("- insurance: Insurance. Subcategories: per (PER)",),
        rules=tuple(f"- When rule {i} holds. → X / Y" for i in range(rules)),
        exemplars=tuple(f'- "doc {i}" from AGIPI → cabinet / insurance' for i in range(exemplars)),
        filename="scan.pdf", pages=tuple(pages),
    )  # fmt: skip


def test_page_block_format():
    p = prompts.render(_sections(["one", "two"], 0, 0), prompts.Cut())
    want = "Filename: scan.pdf\n\nDocument text, 2 of 2 page(s):\n=== PAGE 1 ===\none\n"
    assert p.user == want + "=== PAGE 2 ===\ntwo"
    assert "## House rules" not in p.system and "Respond with JSON only." in p.system


def test_first_three_pages_cut_to_4000():
    p = prompts.build(_sections(["a" * 5000, "b", "c", "d"]))
    assert p.pages_sent == ("a" * 4000, "b", "c") and "Document text, 3 of 4 page(s):" in p.user


def _padded(padding: int) -> prompts.Sections:
    s = _sections(["x" * 4_000] * 3)
    return prompts.Sections(**{**s.__dict__, "entities": ("e" * padding,)})


def test_budget_cutter_takes_the_first_cut_under_the_ceiling():
    reached = set()
    for padding in [0, *range(46_000, 62_000, 25)]:
        s = _padded(padding)
        fits = [c for c in prompts.CUTS if prompts.render(s, c).tokens <= prompts.BUDGET]
        if not fits:
            with pytest.raises(prompts.PromptBudget):
                prompts.build(s)
            continue
        p = prompts.build(s)
        assert p.tokens <= prompts.BUDGET and p.cut == fits[0]
        reached.add(prompts.CUTS.index(p.cut))
    assert reached == set(range(len(prompts.CUTS)))


def test_budget_cuts_in_the_stated_order():
    s = _sections(["x" * 4_000] * 3)
    seen = []
    for cut in prompts.CUTS:
        p = prompts.render(s, cut)
        seen.append((p.system.count("When rule"), p.user.count(" from AGIPI"),
                     max(len(x) for x in p.pages_sent), len(p.pages_sent)))  # fmt: skip
    assert seen == [(30, 5, 4000, 3), (30, 0, 4000, 3), (15, 0, 4000, 3), (0, 0, 4000, 3),
                    (0, 0, 2500, 3), (0, 0, 2500, 2), (0, 0, 2500, 1)]  # fmt: skip
    for a, b in zip(prompts.CUTS, prompts.CUTS[1:], strict=False):
        assert prompts.render(s, b).tokens < prompts.render(s, a).tokens


def test_prompt_over_budget_after_every_cut_fails():
    s = _sections(["x"])
    s = prompts.Sections(**{**s.__dict__, "categories": ("c" * 70_000,)})
    with pytest.raises(prompts.PromptBudget):
        prompts.build(s)


# --- §1.4 extraction ---


def _pdfinfo(pages: int):
    return f"Title: x\nPages:          {pages}\n".encode()


def test_text_pdf_is_read_page_by_page(tmp_path):
    pages = {
        1: b"Page one\x00 text with enough characters   \n\x0c",
        2: b"Second page, also long enough\n",
    }
    tools = Tools(handler=lambda a: _pdfinfo(2) if a[0] == "pdfinfo" else pages[int(a[5])])
    got = extract.extract(tmp_path / "in.pdf", "application/pdf", "a" * 64, tmp_path / "tc", tools)
    assert got.method == "pdftotext"
    assert got.pages == (
        "Page one text with enough characters\n",
        "Second page, also long enough\n",
    )
    assert [c[:7] for c in tools.calls[1:]] == [
        ["pdftotext", "-layout", "-enc", "UTF-8", "-f", "1", "-l"],
        ["pdftotext", "-layout", "-enc", "UTF-8", "-f", "2", "-l"],
    ]
    stored = json.loads(cache.pages_path(tmp_path / "tc", "a" * 64).read_text())
    assert stored == {"v": 1, "sha256": "a" * 64, "method": "pdftotext", "page_count": 2,
                      "pages": list(got.pages)}  # fmt: skip
    assert not list((tmp_path / "tc").rglob("*.tmp"))


def _ocr_tools(text_after: bytes, scanned: bytes = b"   \n"):
    def handler(a):
        if a[0] == "pdfinfo":
            return _pdfinfo(2)
        if a[0] == "ocrmypdf" or a[0] == "img2pdf":
            Path(a[-1]).write_bytes(b"%PDF-ocr")
            return b""
        return text_after if a[-2].endswith(".ocr.pdf") else scanned

    return Tools(handler=handler)


def test_a_page_under_20_characters_runs_ocr_once_on_the_whole_file(tmp_path):
    tools = _ocr_tools(b"Texte reconnu par la reconnaissance optique\n")
    got = extract.extract(tmp_path / "in.pdf", "application/pdf", "b" * 64, tmp_path / "tc", tools)
    ocr = [c for c in tools.calls if c[0] == "ocrmypdf"]
    assert len(ocr) == 1 and got.method == "ocr" and got.page_count == 2
    assert ocr[0][1:-2] == list(extract.OCR_ARGS)
    assert ocr[0][-1].endswith(".ocr.pdf.tmp")
    assert cache.ocr_path(tmp_path / "tc", "b" * 64).read_bytes() == b"%PDF-ocr"


def test_images_go_through_img2pdf_then_ocr(tmp_path):
    tools = _ocr_tools(b"Facture d'eau, montant a payer 74,25 EUR\n")
    got = extract.extract(tmp_path / "in.jpg", "image/jpeg", "c" * 64, tmp_path / "tc", tools)
    assert [c[0] for c in tools.calls][:2] == ["img2pdf", "ocrmypdf"] and got.method == "ocr"
    assert not list((tmp_path / "tc").rglob("*.img.pdf.tmp"))


def test_cache_hit_runs_no_tool(tmp_path):
    cache.write_pages(tmp_path / "tc", cache.Pages("d" * 64, "ocr", ("cached",)))
    tools = Tools()
    got = extract.extract(tmp_path / "in.pdf", "application/pdf", "d" * 64, tmp_path / "tc", tools)
    assert got.pages == ("cached",) and tools.calls == []


def test_a_bumped_cache_version_is_a_miss(tmp_path, monkeypatch):
    cache.write_pages(tmp_path / "tc", cache.Pages("e" * 64, "ocr", ("cached",)))
    monkeypatch.setattr(cache, "VERSION", 2)
    assert cache.read_pages(tmp_path / "tc", "e" * 64) is None


def test_model_cache_key_includes_the_prompt_version(tmp_path):
    raw = {"category": "tax"}
    cache.write_model(tmp_path, "a" * 64, "c5-v1", "m/one", raw)
    stored = json.loads(cache.model_path(tmp_path, "a" * 64, "c5-v1").read_text())
    assert stored == {"v": 1, "sha256": "a" * 64, "prompt_version": "c5-v1", "model": "m/one",
                      "raw_output": raw}  # fmt: skip
    assert cache.read_model(tmp_path, "a" * 64, "c5-v1", "m/one") == raw
    assert cache.read_model(tmp_path, "a" * 64, "c5-v1", "m/two") is None
    cache.model_path(tmp_path, "a" * 64, "c5-v1").rename(
        cache.model_path(tmp_path, "a" * 64, "c5-v2")
    )
    assert cache.read_model(tmp_path, "a" * 64, "c5-v2", "m/one") is None


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler-utils not installed")
def test_real_pdftotext_on_a_synthetic_letter(tmp_path):
    src = tmp_path / "letter.pdf"
    text = SYNTHETIC["syn-urssaf-call"]["pages"][0]
    src.write_bytes(mini_pdf([text, "Page deux : référence URS-DEMO-3391"]))
    got = extract.extract(src, "application/pdf", "f" * 64, tmp_path / "tc")
    assert got.method == "pdftotext" and got.page_count == 2
    assert "URS-DEMO-3391" in got.pages[0] and "842,00 €" in got.pages[0]
    assert got.pages[1].strip() == "Page deux : référence URS-DEMO-3391"


@pytest.mark.skipif(
    shutil.which("ocrmypdf") is None, reason="ocrmypdf not installed (runs in the image)"
)
def test_real_ocr_on_an_image_only_pdf(tmp_path):
    src = tmp_path / "text.pdf"
    src.write_bytes(mini_pdf(["Facture FA-DEMO-5580", "Total TTC : 386,40 EUR"]))
    import subprocess

    subprocess.run(["pdftoppm", "-r", "150", "-png", str(src), str(tmp_path / "p")], check=True)
    img = tmp_path / "scan.pdf"
    subprocess.run(["img2pdf", *sorted(str(p) for p in tmp_path.glob("p-*.png")), "-o", str(img)],
                   check=True)  # fmt: skip
    got = extract.extract(img, "application/pdf", "0" * 64, tmp_path / "tc")
    assert got.method == "ocr" and "FA-DEMO-5580" in got.pages[0]
    assert cache.ocr_path(tmp_path / "tc", "0" * 64).exists()
