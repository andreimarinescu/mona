"""A14 (C5 §1.2/§5): an empty model answer is retried once with the first page only."""

import json

from sqlalchemy import create_engine

from mona.pipeline import cache
from mona.pipeline.schema import FIELD_KEYS, PROMPT_VERSION, empty_answer
from tests.pg import scratch_db, sqlalchemy_url_for
from tests.pipeline_world import RECORDED, SYNTHETIC, FakeModel, NoModel, Pipeline

DOC = "syn-supplier-rotated"
EMPTY = {"title": "", "category": "unknown", "subcategory": None, **dict.fromkeys(FIELD_KEYS),
         "confidence": 0, "reason": "null"}  # fmt: skip


class Sequenced(FakeModel):
    def __init__(self, *answers):
        super().__init__({})
        self.queue = list(answers)

    def complete(self, system, user, schema):
        self.answers[SYNTHETIC[DOC]["file"]] = self.queue.pop(0)
        return super().complete(system, user, schema)


def run(engine, tmp_path, *answers):
    model = Sequenced(*answers)
    p = Pipeline(engine, tmp_path / "data", model=model)
    p.filed_history("Dentalis Fournitures")
    doc = p.drop_synthetic([DOC], outputs=False).items[0].document_id
    p.drain()
    return p, model, p.row(doc)


def test_an_empty_answer_is_asked_again_with_the_first_page(l1m2_demo_engine, tmp_path):
    good = RECORDED["outputs"][DOC]
    p, model, r = run(l1m2_demo_engine, tmp_path, EMPTY, good)
    first, second = (user for _, user in model.calls)
    assert "Document text, 2 of 2 page(s):" in first and "=== PAGE 2 ===" in first
    assert "Document text, 1 of 2 page(s):" in second and "=== PAGE 2 ===" not in second
    assert r["status"] == "filed" and r["counterparty_id"] is not None
    assert cache.read_model(p.ctx.textcache, r["sha256"], PROMPT_VERSION, model.model) == good
    assert p.rows("extractions", document_id=r["id"])[0]["raw_output"] == good


def test_two_empty_answers_queue_with_low(l1m2_demo_engine, tmp_path):
    p, model, r = run(l1m2_demo_engine, tmp_path, EMPTY, EMPTY)
    assert len(model.calls) == 2
    assert (r["status"], "low" in r["reasons"]) == ("review", True)
    assert cache.read_model(p.ctx.textcache, r["sha256"], PROMPT_VERSION, model.model) is None


def test_a_cached_empty_answer_is_asked_again(l1m2_demo_engine, tmp_path):
    good = RECORDED["outputs"][DOC]
    model = Sequenced(good)
    p = Pipeline(l1m2_demo_engine, tmp_path / "data", model=model)
    p.filed_history("Dentalis Fournitures")
    doc = p.drop_synthetic([DOC], outputs=False).items[0].document_id
    p.cache_model(p.row(doc)["sha256"], EMPTY)
    p.drain()
    r = p.row(doc)
    assert len(model.calls) == 1 and r["status"] == "filed"
    assert cache.read_model(p.ctx.textcache, r["sha256"], PROMPT_VERSION, model.model) == good


def outcome(p, doc):
    r = p.row(doc)
    fields = p.rows("extraction_fields", extraction_id=r["extraction_id"])
    return r["confidence"], r["band"], {f["key"]: (f["verified"], f["page"]) for f in fields}


def test_a_cache_hit_verifies_against_the_retry_page_budget(
    l1m2_demo_engine, l1m2_demo_template, tmp_path
):
    """A22: the quote is on both pages, so only the one-page retry prompt verifies it."""
    ref = {"value": "FA-DEMO-5580", "quote": "Facture FA-DEMO-5580", "page": 3}
    retried = {**RECORDED["outputs"][DOC], "due_date": None, "reference": ref}
    live, _, r = run(l1m2_demo_engine, tmp_path, EMPTY, retried)
    stored = cache.model_path(live.ctx.textcache, r["sha256"], PROMPT_VERSION)
    assert json.loads(stored.read_text())["pages_sent"] == 1
    with scratch_db(template=l1m2_demo_template) as db:
        engine = create_engine(sqlalchemy_url_for(db))
        try:
            hit = Pipeline(engine, tmp_path / "data", model=NoModel())
            hit.filed_history("Dentalis Fournitures")
            doc = hit.drop_synthetic([DOC], outputs=False).items[0].document_id
            hit.drain()
            assert hit.rows("extractions", document_id=doc)[0]["from_cache"] is True
            assert outcome(hit, doc) == outcome(live, r["id"])
        finally:
            engine.dispose()
    assert outcome(live, r["id"])[2]["reference"] == (True, 1)


def test_an_answer_with_a_field_is_not_retried(l1m2_demo_engine, tmp_path):
    good = RECORDED["outputs"][DOC]
    _, model, r = run(l1m2_demo_engine, tmp_path, good)
    assert len(model.calls) == 1 and r["status"] == "filed"


def test_empty_answer_shape():
    assert empty_answer(EMPTY)
    assert not empty_answer({**EMPTY, "confidence": 0.4})
    assert not empty_answer({**EMPTY, "reference": {"value": "A-1", "quote": "A-1", "page": 1}})
