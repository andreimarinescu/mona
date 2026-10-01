"""C5 §1 and §11 (tests 10–12, 14), C1 §12 (tests 7, 9, 10), C7 §8.4: the pipeline end to end."""

import copy
import errno
import subprocess
import threading
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, text, update

from mona.fileops import Fs, sha256_file
from mona.pipeline import cache, intake, stages
from mona.pipeline import classify as classify_mod
from mona.pipeline.intake import Upload, ingest_file, ingest_files
from mona.pipeline.model import SchemaInvalid, TransportError
from mona.pipeline.queue import JOBS
from mona.pipeline.schema import PROMPT_VERSION
from mona.services import delete_document
from mona.services import pipeline as services_pipeline
from mona.services.errors import ServiceError
from mona.services.registry import T
from tests.pipeline_world import (
    RECORDED,
    SYNTHETIC,
    FakeModel,
    Pipeline,
    Tools,
    content_for,
)

LIVE_ORDER = ["syn-sie-letter", "syn-oxyleo-prep", "syn-supplier-rotated", "syn-agipi-per",
              "syn-unreadable", "syn-urssaf-call", "syn-hello-fy-crossing", "syn-patient-devis",
              "syn-patient-ordonnance", "syn-patient-care-sheet"]  # fmt: skip
HISTORY = ("SIE Mayenne", "AGIPI", "urssaf-pays-de-la-loire", "Hello bank", "Dentalis Fournitures")


def review_invariant(p: Pipeline) -> None:
    """C1 §4.5 / §12 test 7: a live document is in review iff it has one open review item."""
    with p.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT d.id, d.status, count(r.id) FILTER (WHERE r.status = 'open') AS open"
                " FROM documents d LEFT JOIN review_items r ON r.document_id = d.id"
                " WHERE d.deleted_at IS NULL GROUP BY d.id, d.status"
            )
        ).all()
    for r in rows:
        assert (r.status in ("review", "unreadable")) == (r.open == 1) and r.open <= 1, r


def ids(intake_result) -> list[str]:
    return [i.document_id for i in intake_result.items]


def raw_for(doc_id: str, **over) -> dict:
    return copy.deepcopy(RECORDED["outputs"][doc_id]) | over


# --- intake (C1 §4.1, C7 §8.4) ---


def test_intake_places_files_and_queues_extraction_in_drop_order(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    names = ["syn-sie-letter", "syn-oxyleo-prep", "syn-agipi-per"]
    out = p.drop_synthetic(names, outputs=False)
    assert [i.outcome for i in out.items] == ["accepted"] * 3 and not out.batch_done
    for doc_id, name in zip(ids(out), names, strict=True):
        r = p.row(doc_id)
        assert (r["location"], r["current_path"]) == ("inbox", f"{doc_id}.pdf")
        assert (r["status"], r["pipeline_stage"], r["source"]) == ("processing", "queued", "drop")
        assert sha256_file(p.ctx.ops.roots.inbox / r["current_path"]) == r["sha256"]
        assert r["original_name"] == SYNTHETIC[name]["file"] and r["entity_id"] is None
    jobs = p.jobs()
    assert [(j.task_name, j.doc, j.priority, j.queue_name, j.queueing_lock) for j in jobs] == [
        ("extract_text", d, 0, "cpu", f"extract_text:{d}") for d in ids(out)
    ]
    assert [j.id for j in jobs] == sorted(j.id for j in jobs)
    groups = p.rows("op_groups", batch_id=out.batch_id)
    assert [(g["kind"], g["actor"], g["via"]) for g in groups] == [
        ("intake_batch", "mona", "pipeline")
    ]
    items = p.rows("intake_items", batch_id=out.batch_id)
    assert sorted(i["document_id"] for i in items) == sorted(ids(out))


def test_duplicates_create_no_document_and_a_batch_of_them_is_done(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    first = p.drop_synthetic(["syn-urssaf-call", "syn-urssaf-call"], outputs=False)
    assert [i.outcome for i in first.items] == ["accepted", "duplicate"]
    assert first.items[1].document_id == first.items[0].document_id
    again = ingest_file(p.ctx, content_for("syn-urssaf-call"), "scan-2026-10-19.pdf")
    assert (again.items[0].outcome, again.items[0].document_id) == (
        "duplicate", first.items[0].document_id,
    )  # fmt: skip
    assert again.batch_done and p.done_batches == [again.batch_id]
    assert len(list(p.ctx.ops.roots.inbox.iterdir())) == 1
    with p.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(T["documents"])).scalar() == 1


def test_a_duplicate_of_a_trashed_document_says_so(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    doc = ids(p.drop_synthetic(["syn-sie-letter"], outputs=False))[0]
    delete_document(p.ctx, doc, actor="user", via="ui")
    again = ingest_file(p.ctx, content_for("syn-sie-letter"), "again.pdf")
    assert (again.items[0].outcome, again.items[0].deleted) == ("duplicate", True)


def test_rejects(l1m2_demo_engine, tmp_path, monkeypatch):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    monkeypatch.setattr(intake, "MAX_BYTES", 100)
    out = ingest_files(p.ctx, [
        Upload(b"", "empty.pdf"), Upload(b"hello world", "notes.txt"),
        Upload(b"%PDF-" + b"x" * 200, "big.pdf"), Upload(tmp_path / "missing.pdf", "missing.pdf"),
    ])  # fmt: skip
    assert [(i.outcome, i.reject_reason) for i in out.items] == [
        ("rejected", "empty"), ("rejected", "unsupported_type"), ("rejected", "too_large"),
        ("rejected", "unreadable_file"),
    ]  # fmt: skip
    assert out.batch_done and list(p.ctx.ops.roots.inbox.iterdir()) == []
    assert len(p.rows("intake_items", batch_id=out.batch_id)) == 4


def test_images_keep_their_type_and_a_path_can_be_ingested(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    src = tmp_path / "photo.jpg"
    src.write_bytes(content_for("syn-visitor-photo"))
    out = ingest_file(p.ctx, src, "photo.jpg", source="telegram")
    r = p.row(out.items[0].document_id)
    assert (r["mime_type"], r["source"], r["current_path"]) == (
        "image/jpeg", "telegram", f"{r['id']}.jpg",
    )  # fmt: skip


def test_adding_to_a_batch_needs_it_running(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    first = p.drop_synthetic(["syn-sie-letter"], outputs=False)
    more = ingest_file(p.ctx, content_for("syn-oxyleo-prep"), "b.pdf", batch_id=first.batch_id)
    assert more.batch_id == first.batch_id and more.items[0].outcome == "accepted"
    empty = ingest_files(p.ctx, [])
    assert empty.batch_done
    with pytest.raises(ServiceError) as err:
        ingest_file(p.ctx, content_for("syn-agipi-per"), "c.pdf", batch_id=empty.batch_id)
    assert err.value.code == "conflict"


# --- the synthetic set end to end (recorded outputs through the model-output cache) ---


@pytest.fixture
def ran(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    p.set_thresholds(85, 60)
    p.filed_history(*HISTORY)
    live = p.drop_synthetic([*LIVE_ORDER, "syn-urssaf-call"])
    visitors = p.drop_synthetic(["syn-visitor-photo"], visitor=True)
    p.drain()
    return p, dict(zip(LIVE_ORDER, ids(live), strict=False)), live, visitors


def test_every_document_settles_and_each_batch_finishes_once(ran):
    p, docs, live, visitors = ran
    assert p.model.calls == 0
    assert live.items[-1].outcome == "duplicate"
    for name, doc in docs.items():
        assert p.row(doc)["pipeline_stage"] == "done", name
    assert sorted(p.done_batches) == sorted([live.batch_id, visitors.batch_id])
    for b in (live.batch_id, visitors.batch_id):
        assert p.rows("batches", id=b)[0]["status"] == "done"
    review_invariant(p)


def test_recorded_outcomes(ran):
    p, docs, _, visitors = ran
    assert p.path(docs["syn-oxyleo-prep"]) == (
        "Personnel/Impôts et taxes/2026/2026-10-11_OXYLEO_Elements-preparatoires.pdf"
    )
    assert p.path(docs["syn-supplier-rotated"]) == (
        "Cabinet Orthodontie/Factures reçues/Dentalis Fournitures/2026/"
        "2026-10-12_Dentalis-Fournitures_Facture_FA-DEMO-5580.pdf"
    )
    assert p.path(docs["syn-patient-devis"]) == (
        "Cabinet Orthodontie/Documents patients/2026/2026-10-08_Devis_DEV-DEMO-0231.pdf"
    )
    photo = p.row(visitors.items[0].document_id)
    assert photo["current_path"] == (
        "Visitors/Factures reçues/Eaux du Bocage/2026/2026-10-05_Eaux-du-Bocage_Facture_"
        "EB-DEMO-1206.jpg"
    )
    unreadable = p.row(docs["syn-unreadable"])
    assert (unreadable["status"], list(unreadable["reasons"]), unreadable["location"]) == (
        "unreadable", ["unreadable"], "inbox",
    )  # fmt: skip
    oxy = p.rows("classifications", document_id=docs["syn-oxyleo-prep"])[0]
    assert oxy["method"] == "rule" and oxy["rule_id"] is not None
    x = p.rows("extractions", document_id=docs["syn-oxyleo-prep"])[0]
    assert (x["from_cache"], x["model"], x["prompt_version"]) == (True, RECORDED["model"],
                                                                  PROMPT_VERSION)  # fmt: skip


def test_non_visitor_documents_never_get_the_visitors_entity(ran):
    p, docs, _, visitors = ran
    ents = {e["key"]: e["id"] for e in p.rows("entities")}
    for doc in docs.values():
        assert p.row(doc)["entity_id"] != ents["visitors"]
    assert p.row(visitors.items[0].document_id)["entity_id"] == ents["visitors"]


def test_journal_entries_carry_the_intake_group(ran):
    p, docs, live, _ = ran
    group = p.rows("op_groups", batch_id=live.batch_id)[0]["id"]
    entries = [e for e in p.rows("file_ops") if e["batch_id"] == live.batch_id]
    assert entries and all(e["group_id"] == group for e in entries)
    actions = {(e["action"], e["document_id"]) for e in entries}
    assert ("mark.unreadable", docs["syn-unreadable"]) in actions
    assert ("file", docs["syn-oxyleo-prep"]) in actions
    unread = next(e for e in entries if e["action"] == "mark.unreadable")
    assert (unread["actor"], unread["via"], unread["undoable"]) == ("mona", "pipeline", False)


def test_filing_writes_the_extracted_deadline(ran):
    p, docs, _, _ = ran
    urssaf = p.row(docs["syn-urssaf-call"])
    dls = p.rows("deadlines", document_id=docs["syn-urssaf-call"])
    if urssaf["status"] == "filed":
        assert [(str(d["due_date"]), d["origin"]) for d in dls] == [("2026-10-23", "extracted")]
    agipi = p.rows("deadlines", document_id=docs["syn-agipi-per"])
    assert [str(d["due_date"]) for d in agipi] == ["2026-11-01"]


def test_evidence_rows_and_find_queries(ran):
    p, docs, _, _ = ran
    doc = p.row(docs["syn-agipi-per"])
    fields = {f["key"]: f for f in p.rows("extraction_fields", extraction_id=doc["extraction_id"])}
    assert set(fields) >= {"counterparty", "reference", "doc_date", "amount", "due_date"}
    assert fields["amount"]["verified"] and fields["amount"]["currency"] == "EUR"
    assert (
        fields["amount"]["value"] == "480.00"
        and fields["amount"]["find_query"] == "est de 480,00 €"
    )
    for f in fields.values():
        assert (f["find_query"] is not None) == f["verified"], f["key"]
        assert f["confidence"] == (95 if f["verified"] else 40)
    assert doc["page_count"] == 1 and doc["head_norm"].startswith("agipi")
    assert (str(doc["amount"]), doc["currency"], str(doc["due_date"])) == (
        "480.00", "EUR", "2026-11-01",
    )  # fmt: skip


def test_no_extraction_tool_runs_on_a_cache_hit(ran):
    p, *_ = ran
    assert p.tools.calls and {c[0] for c in p.tools.calls} == {"pdftoppm"}
    for c in p.tools.calls:
        assert Path(c[-2]).exists()


def test_search_index_covers_the_page_text(ran):
    p, docs, _, _ = ran
    with p.engine.connect() as conn:
        hit = conn.execute(
            text("SELECT id FROM documents WHERE fts @@ websearch_to_tsquery('mona', :q)"),
            {"q": "fournitures"},
        ).scalars().all()  # fmt: skip
    assert docs["syn-supplier-rotated"] in hit


# --- C5 §11 test 10: failure paths ---


def test_classification_failure_after_retries_lands_in_review(l1m2_demo_engine, tmp_path):
    name = SYNTHETIC["syn-sie-letter"]["file"]
    model = FakeModel({name: TransportError("ModelHTTPError")})
    p = Pipeline(l1m2_demo_engine, tmp_path / "data", model=model)
    doc = ids(p.drop_synthetic(["syn-sie-letter"], outputs=False))[0]
    p.drain()
    r = p.row(doc)
    assert len(model.calls) == 3
    assert [x[2] for x in p.ran if x[0] == "classify_document"] == ["retry", "retry", "failed"]
    assert (r["status"], list(r["reasons"]), r["pipeline_stage"], r["pipeline_error"]) == (
        "review", ["low"], "failed", "TransportError",
    )  # fmt: skip
    assert p.done_batches == [r["batch_id"]]
    review_invariant(p)


def test_schema_invalid_output_is_retried(l1m2_demo_engine, tmp_path):
    name = SYNTHETIC["syn-sie-letter"]["file"]
    good = RECORDED["outputs"]["syn-sie-letter"]
    answers = iter([SchemaInvalid("schema"), good])

    class Flaky(FakeModel):
        def complete(self, system, user, schema):
            self.answers[name] = next(answers)
            return super().complete(system, user, schema)

    p = Pipeline(l1m2_demo_engine, tmp_path / "data", model=Flaky({}))
    p.filed_history("SIE Mayenne")
    doc = ids(p.drop_synthetic(["syn-sie-letter"], outputs=False))[0]
    p.drain()
    assert p.row(doc)["status"] == "filed" and len(p.model.calls) == 2
    cached = cache.read_model(p.ctx.textcache, p.row(doc)["sha256"], PROMPT_VERSION, p.model.model)
    assert cached == good


def test_prompt_over_budget_fails_without_a_retry(l1m2_demo_engine, tmp_path, monkeypatch):
    monkeypatch.setattr("mona.pipeline.prompt.BUDGET", 10)
    model = FakeModel({})
    p = Pipeline(l1m2_demo_engine, tmp_path / "data", model=model)
    doc = ids(p.drop_synthetic(["syn-sie-letter"], outputs=False))[0]
    p.drain()
    r = p.row(doc)
    assert (r["status"], r["pipeline_stage"], r["pipeline_error"]) == (
        "review", "failed", "prompt_budget",
    )  # fmt: skip
    assert model.calls == []


def test_extraction_failure_after_retries_is_unreadable(l1m2_demo_engine, tmp_path):
    def broken(args):
        raise subprocess.CalledProcessError(1, args[0])

    p = Pipeline(l1m2_demo_engine, tmp_path / "data", tools=Tools(handler=broken))
    out = ingest_file(p.ctx, content_for("syn-sie-letter"), "x.pdf", visitor=True)
    doc = out.items[0].document_id
    p.drain()
    r = p.row(doc)
    assert [x[2] for x in p.ran] == ["retry", "retry", "failed"]
    assert (r["status"], list(r["reasons"]), r["pipeline_stage"], r["pipeline_error"]) == (
        "unreadable", ["unreadable"], "failed", "CalledProcessError",
    )  # fmt: skip
    ents = {e["key"]: e["id"] for e in p.rows("entities")}
    assert r["entity_id"] == ents["visitors"]
    assert p.done_batches == [out.batch_id]
    review_invariant(p)


def test_unreadable_in_a_visitor_batch_keeps_the_visitors_entity(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    doc = ids(p.drop_synthetic(["syn-unreadable"], visitor=True))[0]
    p.drain()
    r = p.row(doc)
    ents = {e["key"]: e["id"] for e in p.rows("entities")}
    assert (r["status"], r["pipeline_stage"], r["entity_id"]) == (
        "unreadable", "done", ents["visitors"],
    )  # fmt: skip
    assert p.rows("extractions", document_id=doc) == []


class _Broken(Fs):
    def __init__(self, code: int):
        self.code = code

    def link(self, src, dst):
        raise OSError(self.code, errno.errorcode[self.code])


@pytest.mark.parametrize("failure", ["ENOENT", "EACCES", "forbidden_path"])
def test_filing_failures_land_in_review_and_the_batch_finishes(l1m2_demo_engine, tmp_path, failure):
    fs = None if failure == "forbidden_path" else _Broken(getattr(errno, failure))
    p = Pipeline(l1m2_demo_engine, tmp_path / "data", fs=fs)
    if failure == "forbidden_path":
        outside = tmp_path / "outside"
        outside.mkdir()
        (p.ctx.ops.roots.archive / "Personnel").symlink_to(outside)
    out = p.drop_synthetic(["syn-oxyleo-prep"])
    doc = ids(out)[0]
    p.drain()
    r = p.row(doc)
    assert (r["status"], list(r["reasons"]), r["pipeline_stage"], r["pipeline_error"]) == (
        "review", ["conflict"], "failed", failure,
    )  # fmt: skip
    assert r["location"] == "inbox" and p.done_batches == [out.batch_id]
    if failure == "forbidden_path":
        assert list((tmp_path / "outside").iterdir()) == []
    review_invariant(p)


def test_a_review_outcome_ends_at_done_and_counts_toward_the_batch(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    out = p.drop_synthetic(["syn-hello-fy-crossing"])
    with p.engine.begin() as conn:
        conn.execute(update(T["settings"]).values(confidence_low=99, confidence_high=100))
    p.drain()
    r = p.row(ids(out)[0])
    assert (r["status"], r["pipeline_stage"], r["location"]) == ("review", "done", "inbox")
    assert "low" in r["reasons"] and p.done_batches == [out.batch_id]
    assert p.rows("batches", id=out.batch_id)[0]["finished_at"] is not None
    assert [x[0] for x in p.ran if x[1] == ids(out)[0]].count("file_document") == 0
    review_invariant(p)


@pytest.mark.parametrize(
    ("low", "high", "status", "band"),
    [(60, 85, "filed", "high"), (60, 86, "filed", "medium"), (85, 90, "filed", "medium"),
     (86, 90, "review", "low")],
)  # fmt: skip
def test_band_thresholds_are_inclusive(l1m2_demo_engine, tmp_path, low, high, status, band):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    with p.engine.begin() as conn:
        conn.execute(update(T["settings"]).values(confidence_low=low, confidence_high=high))
    doc = ids(p.drop_synthetic(["syn-test-opco"]))[0]
    p.drain()
    r = p.row(doc)
    assert (r["confidence"], r["status"], r["band"]) == (85, status, band)
    if status == "filed":
        entry = next(e for e in p.rows("file_ops", document_id=doc) if e["action"] == "file")
        assert (entry["band"], entry["confidence"]) == (band, 85)


def test_a_document_deleted_mid_pipeline_stops_and_its_batch_finishes(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    out = p.drop_synthetic(["syn-sie-letter"])
    delete_document(p.ctx, ids(out)[0], actor="user", via="ui")
    p.drain()
    r = p.row(ids(out)[0])
    assert (r["location"], r["pipeline_stage"]) == ("trash", "done")
    assert p.done_batches == [out.batch_id] and p.rows("extractions") == []


# --- C1 §12 test 9: batch lifecycle under concurrency [M] ---


def test_batch_done_exactly_once_when_three_outcomes_race(
    l1m2_demo_template, tmp_path, monkeypatch
):
    from sqlalchemy import create_engine

    from tests.pg import scratch_db, sqlalchemy_url_for

    for n in range(3):
        with scratch_db(template=l1m2_demo_template) as db:
            engine = create_engine(sqlalchemy_url_for(db), pool_size=8)
            try:
                _race_once(engine, tmp_path / f"data{n}", monkeypatch)
            finally:
                engine.dispose()


def _race_once(engine, data, monkeypatch):
    p = Pipeline(engine, data)
    names = ["syn-oxyleo-prep", "syn-patient-ordonnance", "syn-unreadable"]
    out = p.drop_synthetic(names)
    filed, review, unread = ids(out)
    p.cache_model(p.row(review)["sha256"], raw_for("syn-patient-ordonnance", category="unknown"))
    stages.run(p.ctx, "extract_text", filed)
    stages.run(p.ctx, "extract_text", review)
    stages.run(p.ctx, "classify_document", filed, model=lambda: p.model)
    barrier = threading.Barrier(3, timeout=10)
    original = services_pipeline.finish_batch_if_done

    def gated(conn, batch_id, now):
        barrier.wait()
        return original(conn, batch_id, now)

    for mod in (services_pipeline, stages, classify_mod):
        monkeypatch.setattr(mod, "finish_batch_if_done", gated)
    jobs = [("file_document", filed), ("classify_document", review), ("extract_text", unread)]
    errors: list[BaseException] = []

    def work(job, doc):
        try:
            stages.run(p.ctx, job, doc, model=lambda: p.model, runner=p.tools)
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=work, args=j) for j in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    monkeypatch.undo()
    assert errors == []
    outcome = [(p.row(d)["status"], p.row(d)["pipeline_stage"]) for d in (filed, review, unread)]
    assert outcome == [("filed", "done"), ("review", "done"), ("unreadable", "done")]
    batch = p.rows("batches", id=out.batch_id)[0]
    assert batch["status"] == "done" and batch["finished_at"] is not None
    assert p.done_batches == [out.batch_id]
    groups = p.rows("op_groups", batch_id=out.batch_id)
    assert len(groups) == 1
    entries = [e for e in p.rows("file_ops") if e["document_id"] in (filed, unread)]
    assert entries and {e["group_id"] for e in entries if e["action"] != "deadline.add"} == {
        groups[0]["id"]
    }


# --- C5 §11 test 11: the model-output cache [M] ---


def test_second_classification_of_the_same_bytes_uses_the_cache_and_todays_rules(
    l1m2_demo_engine, l1m2_learned_engine, tmp_path
):
    name = SYNTHETIC["syn-agipi-per"]["file"]
    model = FakeModel({name: RECORDED["outputs"]["syn-agipi-per"]})
    first = Pipeline(l1m2_demo_engine, tmp_path / "data", model=model)
    first.filed_history("AGIPI")
    doc1 = ids(first.drop_synthetic(["syn-agipi-per"], outputs=False))[0]
    first.drain()
    assert len(model.calls) == 1
    assert first.path(doc1) == "Personnel/Assurances/AGIPI/2026/2026-10-14_AGIPI_PER-DEMO-0417.pdf"
    assert first.rows("extractions", document_id=doc1)[0]["from_cache"] is False
    second = Pipeline(l1m2_learned_engine, tmp_path / "data", model=model)
    doc2 = ids(second.drop_synthetic(["syn-agipi-per"], outputs=False))[0]
    second.drain()
    assert len(model.calls) == 1
    assert second.rows("extractions", document_id=doc2)[0]["from_cache"] is True
    assert second.path(doc2) == (
        "Personnel/Christine/Assurances/AGIPI/PER/2026/2026-10-14_AGIPI_PER_PER-DEMO-0417.pdf"
    )


def test_another_model_or_todays_schema_is_a_miss(l1m2_demo_engine, tmp_path):
    name = SYNTHETIC["syn-oxyleo-prep"]["file"]
    other = FakeModel({name: RECORDED["outputs"]["syn-oxyleo-prep"]}, model="qwen/qwen3.6-35b-a3b")
    p = Pipeline(l1m2_demo_engine, tmp_path / "data", model=other)
    doc = ids(p.drop_synthetic(["syn-oxyleo-prep"]))[0]
    p.drain()
    assert (
        len(other.calls) == 1 and p.rows("extractions", document_id=doc)[0]["from_cache"] is False
    )

    stale = raw_for("syn-sie-letter", category="retired_category")
    model = FakeModel({SYNTHETIC["syn-sie-letter"]["file"]: RECORDED["outputs"]["syn-sie-letter"]})
    p2 = Pipeline(l1m2_demo_engine, tmp_path / "data2", model=model)
    sha = p2.cache_text(content_for("syn-sie-letter"), "syn-sie-letter")
    p2.cache_model(sha, stale)
    p2.drop_synthetic(["syn-sie-letter"], outputs=False)
    p2.drain()
    assert len(model.calls) == 1
    fresh = cache.read_model(p2.ctx.textcache, sha, PROMPT_VERSION, model.model)
    assert fresh == RECORDED["outputs"]["syn-sie-letter"]


def test_a_user_reextraction_bypasses_and_overwrites_the_cache(l1m2_demo_engine, tmp_path):
    name = SYNTHETIC["syn-oxyleo-prep"]["file"]
    newer = raw_for("syn-oxyleo-prep", title="Nouveau titre")
    model = FakeModel({name: newer})
    p = Pipeline(l1m2_demo_engine, tmp_path / "data", model=model)
    doc = ids(p.drop_synthetic(["syn-oxyleo-prep"]))[0]
    stages.run(p.ctx, "extract_text", doc, runner=p.tools)
    classify_mod.classify(p.ctx, doc, model, bypass_cache=True)
    sha = p.row(doc)["sha256"]
    assert len(model.calls) == 1
    assert cache.read_model(p.ctx.textcache, sha, PROMPT_VERSION, model.model)["title"] == (
        "Nouveau titre"
    )


# --- C5 §11 test 12 and C1 §12 test 10: Visitors ---


def test_visitor_document_without_a_model_entity_files_to_visitors(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    out = p.drop_synthetic(["syn-agipi-per"], visitor=True)
    doc = ids(out)[0]
    p.cache_model(p.row(doc)["sha256"], raw_for("syn-agipi-per", entity=None))
    p.drain()
    r = p.row(doc)
    assert r["current_path"].startswith("Visitors/Assurances/AGIPI/2026/")
    assert (r["status"], list(r["reasons"])) == ("filed", [])
    cls = p.rows("classifications", document_id=doc)[0]
    assert cls["method"] == "llm" and cls["rule_id"] is None
    assert r["confidence"] == 95


def test_the_same_document_outside_a_visitor_batch_queues_for_its_entity(
    l1m2_demo_engine, tmp_path
):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    doc = ids(p.drop_synthetic(["syn-agipi-per"]))[0]
    p.cache_model(p.row(doc)["sha256"], raw_for("syn-agipi-per", entity=None))
    p.drain()
    r = p.row(doc)
    assert (r["status"], list(r["reasons"]), r["entity_id"]) == ("review", ["entity"], None)


def test_rules_never_run_on_a_visitor_batch(l1m2_learned_engine, tmp_path):
    p = Pipeline(l1m2_learned_engine, tmp_path / "data")
    doc = ids(p.drop_synthetic(["syn-oxyleo-prep"], visitor=True))[0]
    p.drain()
    assert p.path(doc).startswith("Visitors/Impôts et taxes/2026/")
    assert p.row(doc)["rule_id"] is None


# --- C5 §11 test 14: the six feedback cases end to end ---

FEEDBACK = {
    "syn-agipi-per": "Personnel/Christine/Assurances/AGIPI/PER/2026/"
    "2026-10-14_AGIPI_PER_PER-DEMO-0417.pdf",
    "syn-hello-fy-crossing": "LMNP/Angers-Strasbourg/Banque/2026/"
    "2026-01-15_Hello-bank_Releve-de-compte.pdf",
    "syn-oxyleo-prep": "Personnel/Impôts et taxes/2026/"
    "2026-10-11_OXYLEO_Elements-preparatoires.pdf",
    "syn-test-opco": "Cabinet Orthodontie/Appels de paiement/2026/"
    "2026-10-12_OPCO-EP_Contribution-OPCO_OPCO-DEMO-0042.pdf",
    "syn-test-talenz": "Medical Digital Design/Documents annuels/2025/2026-10-13_TALENZ.pdf",
    "syn-test-unim": "Cabinet Orthodontie/Assurances/UNIM/2026/2026-10-15_UNIM_UNIM-DEMO-0771.pdf",
}
FEEDBACK_RULES = {
    "syn-agipi-per": "agipi-per-by-person", "syn-hello-fy-crossing": "hello-bank-lmnp",
    "syn-oxyleo-prep": "oxyleo-personal-tax", "syn-test-opco": "opco-selarl",
    "syn-test-talenz": "talenz-mdd", "syn-test-unim": "unim-business",
}  # fmt: skip


def test_six_feedback_cases_file_to_their_paths(l1m2_learned_engine, tmp_path):
    p = Pipeline(l1m2_learned_engine, tmp_path / "data")
    out = p.drop_synthetic(list(FEEDBACK))
    p.drain()
    rules = {r["id"]: r["key"] for r in p.rows("rules")}
    for name, doc in zip(FEEDBACK, ids(out), strict=True):
        r = p.row(doc)
        assert (r["status"], p.path(doc)) == ("filed", FEEDBACK[name]), name
        assert rules[r["rule_id"]] == FEEDBACK_RULES[name], name
        assert r["band"] == "high" or r["band"] == "medium", name
    oxy = p.row(ids(out)[2])
    people = {x["id"]: x["key"] for x in p.rows("people")}
    assert people[oxy["addressee_person_id"]] == "claudiu" and oxy["sub_unit_id"] is None
    fired = {r["key"]: r["fired_count"] for r in p.rows("rules")}
    assert all(fired[k] == 1 for k in FEEDBACK_RULES.values())


# --- conflicts, `review: true` and titles through the pipeline ---


def test_conflicting_rules_queue_with_both_ids(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    _add_rule(p, "t-oxyleo-cabinet", "oxyleo", {"entity": "selarl-simina", "category": "tax"})
    p.set_thresholds(85, 60)
    p.filed_history("oxyleo")
    doc = ids(p.drop_synthetic(["syn-oxyleo-prep"]))[0]
    p.drain()
    r = p.row(doc)
    cls = p.rows("classifications", document_id=doc)[0]
    assert (r["status"], list(r["reasons"])) == ("review", ["conflict"])
    assert len(cls["conflicting_rule_ids"]) == 2 and cls["rule_id"] is None


def test_a_review_rule_queues_even_at_high_confidence(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    _add_rule(p, "t-oxyleo-ask", "oxyleo", {"review": True}, priority=50)
    doc = ids(p.drop_synthetic(["syn-oxyleo-prep"]))[0]
    p.drain()
    r = p.row(doc)
    assert (r["status"], list(r["reasons"])) == ("review", ["low"]) and r["confidence"] >= 60
    assert p.rows("classifications", document_id=doc)[0]["method"] == "rule"


def test_romanian_titles_use_comma_below(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    with p.engine.begin() as conn:
        e = T["entities"]
        conn.execute(update(e).where(e.c.key == "mdd").values(filing_language="ro"))
    doc = ids(p.drop_synthetic(["syn-sie-letter"], outputs=False))[0]
    p.cache_model(p.row(doc)["sha256"], raw_for("syn-sie-letter", title="Înştiinţare SIE"))
    p.drain()
    assert p.row(doc)["title"] == "Înștiințare SIE"


def _add_rule(p: Pipeline, key: str, cp: str, action: dict, priority: int | None = None) -> None:
    from mona.rules import store
    from mona.rules.grammar import RuleBody

    body = RuleBody.model_validate(
        {"conditions": [{"field": "counterparty", "op": "equals", "value": cp}], "action": action}
    )
    with p.engine.begin() as conn:
        store.save_rule(
            conn, key=key, name=key, state="active", source="correction", body=body,
            priority=priority or 10, names=store.names(conn),
        )  # fmt: skip


# --- C5 §5.3/§5.5 prompt from the database ---


def test_prompt_for_the_c5_registry(seeded_engine, tmp_path):
    from mona.pipeline import prompt as prompts
    from mona.pipeline.classify import request_schema
    from mona.services import registry

    with seeded_engine.connect() as conn:
        snap = registry.load(conn)
        doc = {"id": "doc_x", "head_norm": None, "original_name": "a.pdf"}
        prompt = prompts.build(prompts.sections(conn, snap, doc, ["page"]))
    schema = request_schema(snap)
    for key in snap.entities:
        assert (f"- {key}: " in prompt.system) is (key != snap.visitors)
    for cid in snap.categories:
        assert f"- {cid}: " in prompt.system
    ent_enum = schema["properties"]["entity"]["anyOf"][0]["properties"]["value"]["enum"]
    assert sorted(ent_enum) == sorted(k for k in snap.entities if k != snap.visitors)
    assert schema["properties"]["category"]["enum"][:-1] == [
        c["id"] for c in sorted(snap.categories.values(), key=lambda c: (c["sort_order"], c["id"]))
    ]
    rule_lines = [line for line in prompt.system.split("\n") if line.startswith("- When")]
    with seeded_engine.connect() as conn:
        active = conn.execute(
            select(func.count()).select_from(T["rules"]).where(T["rules"].c.state == "active")
        ).scalar()
    assert 0 < len(rule_lines) == min(active, 30)


def test_house_rules_are_active_rules_by_priority(l1m2_demo_engine):
    from mona.pipeline import prompt as prompts
    from mona.services import registry

    with l1m2_demo_engine.begin() as conn:
        r = T["rules"]
        conn.execute(update(r).where(r.c.key == "payroll-selarl").values(state="disabled"))
        conn.execute(update(r).where(r.c.key == "unim-business").values(priority=99))
        snap = registry.load(conn)
        lines = prompts.rule_lines(conn, snap)
    assert len(lines) == 5 and lines[0].startswith("- When the counterparty is unim.")
    assert not any("déclaration sociale" in line for line in lines)
    assert lines[0].endswith("→ Cabinet Orthodontie / Assurances / UNIM / {sub} / {year}")


def test_exemplars_come_from_similar_trusted_filings(l1m2_demo_engine, tmp_path):
    name = SYNTHETIC["syn-test-unim"]["file"]
    model = FakeModel({name: RECORDED["outputs"]["syn-test-unim"]})
    p = Pipeline(l1m2_demo_engine, tmp_path / "data", model=model)
    p.drop_synthetic(["syn-test-opco", "syn-urssaf-call", "syn-sie-letter"])
    p.drain()
    p.drop_synthetic(["syn-test-unim"], outputs=False)
    p.drain()
    user = model.calls[0][1]
    block = user.split("\n\nFilename:")[0]
    assert block.startswith("Documents already filed here, for reference:")
    lines = block.split("\n")[1:]
    assert 1 <= len(lines) <= 5 and all(line.startswith('- "') for line in lines)
    assert "OPCO EP → selarl-simina / payment_calls.contribution_opco" in block
    assert "Montant" not in block and "prélev" not in block


def test_visitor_documents_are_never_exemplars(l1m2_demo_engine, tmp_path):
    from mona.pipeline.prompt import exemplar_lines

    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    doc = ids(p.drop_synthetic(["syn-test-opco"]))[0]
    p.drain()
    row = p.row(doc)
    probe = {"id": "doc_probe", "head_norm": row["head_norm"]}
    d, b, e = T["documents"], T["batches"], T["entities"]
    with p.engine.begin() as conn:
        trusted = exemplar_lines(conn, probe)
        conn.execute(update(b).where(b.c.id == row["batch_id"]).values(visitor=True))
        visitor_batch = exemplar_lines(conn, probe)
        conn.execute(update(b).where(b.c.id == row["batch_id"]).values(visitor=False))
        visitors = conn.execute(select(e.c.id).where(e.c.purge_after_hours.is_not(None))).scalar()
        conn.execute(update(d).where(d.c.id == doc).values(entity_id=visitors))
        visitors_entity = exemplar_lines(conn, probe)
    assert len(trusted) == 1 and "OPCO" in trusted[0]
    assert visitor_batch == visitors_entity == []


def test_thumbnail_uses_the_ocr_copy_when_there_is_one(l1m2_demo_engine, tmp_path):
    p = Pipeline(l1m2_demo_engine, tmp_path / "data")
    doc = ids(p.drop_synthetic(["syn-supplier-rotated"]))[0]
    sha = p.row(doc)["sha256"]
    cache.ocr_path(p.ctx.textcache, sha).write_bytes(b"%PDF-ocr")
    stages.run(p.ctx, "render_thumbnail", doc, runner=p.tools)
    call = p.tools.calls[-1]
    assert call[:9] == ["pdftoppm", "-r", "60", "-f", "1", "-l", "1", "-png", "-singlefile"]
    assert call[-2].endswith(f"{sha}.ocr.pdf")
    assert cache.thumbnail_path(p.ctx.textcache, sha).exists()


def test_jobs_have_the_c5_queues_and_priorities():
    from mona import jobs

    assert {n: (j.queue, j.priority) for n, j in JOBS.items()} == {
        "extract_text": ("cpu", 0), "render_thumbnail": ("cpu", -10),
        "classify_document": ("llm", 0), "file_document": ("cpu", 0),
    }  # fmt: skip
    for n, j in JOBS.items():
        assert jobs.app.tasks[n].queue == j.queue
    assert stages.RETRY["classify_document"].waits == (5, 20)
    assert stages.RETRY["extract_text"].waits == (10, 10)
    assert stages.RETRY["file_document"].waits == ()
    assert not stages.RETRY["classify_document"].will_retry(ValueError(), 0)
    periodic = jobs.app.periodic_registry.periodic_tasks[("recover_pending", "")]
    assert periodic.cron == "* * * * *" and stages.RECOVER_AFTER == timedelta(seconds=30)


def test_evidence_cases_list_every_verified_quote_with_its_viewer_pdf(ran):
    from mona.pipeline.report import evidence_cases

    p, docs, live, _ = ran
    cases = evidence_cases(p.ctx, live.batch_id)
    with p.engine.connect() as conn:
        verified = conn.execute(
            text(
                "SELECT count(*) FROM extraction_fields f JOIN documents d"
                " ON d.extraction_id = f.extraction_id WHERE d.batch_id = :b AND f.verified"
            ),
            {"b": live.batch_id},
        ).scalar()
    assert len(cases) == verified > 0
    for c in cases:
        assert c["find_query"] and c["page"] >= 1 and Path(c["pdf"]).exists()
    rotated = [c for c in cases if c["document_id"] == docs["syn-supplier-rotated"]]
    assert rotated and all(c["method"] == "ocr" for c in rotated)
