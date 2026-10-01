"""Amendment A17 (C5 §9.3/§9.4, C8 §5.4): a first-seen counterparty asks."""

import hashlib

from mona.api import views
from mona.pipeline import cache
from mona.pipeline.intake import Upload, ingest_files
from mona.services import registry
from tests.pipeline_world import RECORDED, SYNTHETIC, Pipeline, mini_pdf


def outcome(p: Pipeline, doc_id: str) -> tuple[str, list[str]]:
    r = p.row(doc_id)
    return r["status"], list(r["reasons"])


def sentence(p: Pipeline, doc_id: str, lang: str = "en") -> str:
    with p.engine.connect() as conn:
        s = views.suggestion(conn, registry.load(conn), p.row(doc_id), lang)
    assert s is not None
    return s.sentence


def stage(engine, tmp_path) -> Pipeline:
    p = Pipeline(engine, tmp_path / "data")
    p.set_thresholds(85, 60)
    return p


def drop_one(p: Pipeline, name: str, *, visitor: bool = False) -> str:
    doc = p.drop_synthetic([name], visitor=visitor).items[0].document_id
    p.drain()
    assert doc is not None
    return doc


def test_the_first_document_of_a_counterparty_asks_with_the_first_sentence(
    l1m2_demo_engine, tmp_path
):
    p = stage(l1m2_demo_engine, tmp_path)
    doc = drop_one(p, "syn-sie-letter")
    assert outcome(p, doc) == ("review", ["entity"])
    assert p.row(doc)["entity_id"] is not None and p.row(doc)["confidence"] == 95
    assert sentence(p, doc) == "First document from SIE Mayenne: where should it go?"
    assert sentence(p, doc, "fr") == "Premier document de SIE Mayenne : où dois-je le classer ?"
    assert sentence(p, doc, "ro") == "Primul document de la SIE Mayenne: unde să-l arhivez?"


def test_a_missing_entity_keeps_the_entity_sentence(l1m2_demo_engine, tmp_path):
    p = stage(l1m2_demo_engine, tmp_path)
    doc = p.drop_synthetic(["syn-sie-letter"], outputs=False).items[0].document_id
    p.cache_model(p.row(doc)["sha256"], {**RECORDED["outputs"]["syn-sie-letter"], "entity": None})
    p.drain()
    assert outcome(p, doc) == ("review", ["entity"])
    assert sentence(p, doc).startswith("This document from SIE Mayenne")


def test_once_a_document_of_the_counterparty_is_filed_the_next_one_files(
    l1m2_demo_engine, tmp_path
):
    p = stage(l1m2_demo_engine, tmp_path)
    p.filed_history("SIE Mayenne")
    doc = drop_one(p, "syn-sie-letter")
    assert outcome(p, doc) == ("filed", [])


def test_a_winning_rule_files_a_first_seen_counterparty(l1m2_demo_engine, tmp_path):
    p = stage(l1m2_demo_engine, tmp_path)
    doc = drop_one(p, "syn-oxyleo-prep")
    assert outcome(p, doc) == ("filed", [])
    assert p.rows("classifications", document_id=doc)[0]["method"] == "rule"


def test_a_visitor_batch_has_no_first_seen_signal(l1m2_demo_engine, tmp_path):
    p = stage(l1m2_demo_engine, tmp_path)
    doc = drop_one(p, "syn-visitor-photo", visitor=True)
    assert outcome(p, doc) == ("filed", [])
    assert p.row(doc)["counterparty_id"] is not None


def test_a_document_without_a_counterparty_has_no_first_seen_signal(l1m2_demo_engine, tmp_path):
    p = stage(l1m2_demo_engine, tmp_path)
    doc = drop_one(p, "syn-patient-devis")
    assert p.row(doc)["counterparty_id"] is None
    assert outcome(p, doc) == ("filed", [])


def test_three_siblings_of_a_new_counterparty_in_one_batch_all_queue(l1m2_demo_engine, tmp_path):
    p = stage(l1m2_demo_engine, tmp_path)
    s = SYNTHETIC["syn-sie-letter"]
    uploads = []
    for i in range(3):
        content = mini_pdf([*s["pages"], f"Copie {i}"])
        sha = hashlib.sha256(content).hexdigest()
        cache.write_pages(p.ctx.textcache, cache.Pages(sha, s["method"], tuple(s["pages"])))
        p.cache_model(sha, RECORDED["outputs"]["syn-sie-letter"])
        uploads.append(Upload(content, f"sie-{i}.pdf"))
    batch = ingest_files(p.ctx, uploads)
    p.drain()
    docs = [i.document_id for i in batch.items]
    assert [outcome(p, d) for d in docs] == [("review", ["entity"])] * 3
    assert len({p.row(d)["counterparty_id"] for d in docs}) == 1
    assert p.rows("batches", id=batch.batch_id)[0]["status"] == "done"
