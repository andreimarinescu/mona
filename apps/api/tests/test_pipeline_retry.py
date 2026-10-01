"""A14 (C5 §1.2/§5): an empty model answer is retried once with the first page only."""

from mona.pipeline import cache
from mona.pipeline.schema import FIELD_KEYS, PROMPT_VERSION, empty_answer
from tests.pipeline_world import RECORDED, SYNTHETIC, FakeModel, Pipeline

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
    assert cache.read_model(p.ctx.textcache, r["sha256"], PROMPT_VERSION, model.model) == EMPTY


def test_an_answer_with_a_field_is_not_retried(l1m2_demo_engine, tmp_path):
    good = RECORDED["outputs"][DOC]
    _, model, r = run(l1m2_demo_engine, tmp_path, good)
    assert len(model.calls) == 1 and r["status"] == "filed"


def test_empty_answer_shape():
    assert empty_answer(EMPTY)
    assert not empty_answer({**EMPTY, "confidence": 0.4})
    assert not empty_answer({**EMPTY, "reference": {"value": "A-1", "quote": "A-1", "page": 1}})
