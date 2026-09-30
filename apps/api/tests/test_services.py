"""Services over the seeded registry: filing, corrections, alias learning, rules, undo, delete."""

import errno
import threading
from datetime import date

import pytest
from sqlalchemy import insert, select, update

from mona.fileops import Fs
from mona.ids import new_id
from mona.services import (
    ServiceError,
    apply_rule,
    correct_document,
    delete_document,
    file_document,
    preview_rule,
    resolve_counterparty,
    restore_document,
    undo,
)
from mona.services.registry import T
from mona.text import norm
from tests.services_world import IBAN_SPACED, Services

OPCO_PATH = (
    "Cabinet Marchand/Appels de paiement/2025/2026-02-27_OPCO-EP_Contribution-OPCO_2025-A-118.pdf"
)


@pytest.fixture
def s(seeded_engine, tmp_path) -> Services:
    return Services(seeded_engine, tmp_path / "data")


def classify(s: Services, doc: str, path: str, *, rule: str | None = None) -> str:
    """What classify_document (M2) leaves before filing: a classification with its path."""
    folder, _, name = path.rpartition("/")
    cls = new_id("cls")
    row = s.row(doc)
    applied = {k: row[k] for k in ("entity_id", "sub_unit_id", "category_id", "subcategory_key",
                                   "counterparty_id")}  # fmt: skip
    with s.engine.begin() as conn:
        conn.execute(
            insert(T["classifications"]).values(
                id=cls, document_id=doc, method="rule" if rule else "llm", rule_id=rule,
                confidence=95, band="high", reasons=[], proposed_path=folder,
                proposed_file_name=name, **applied,
            )
        )  # fmt: skip
        d = T["documents"]
        conn.execute(update(d).where(d.c.id == doc).values(classification_id=cls))
    return cls


def opco_doc(s: Services, **kw) -> str:
    values = dict(
        counterparty="opco", category="payment_calls", subcategory="contribution_opco",
        entity="cabinet", doc_date=date(2026, 2, 27), period_end=date(2025, 12, 31),
        reference="2025-A-118", status="processing",
    )  # fmt: skip
    return s.doc(**{**values, **kw})


def review_open(s: Services, doc: str) -> int:
    r = T["review_items"]
    with s.engine.connect() as conn:
        return len(
            conn.execute(select(r.c.id).where(r.c.document_id == doc, r.c.status == "open")).all()
        )


# --- file_document (pipeline filing) ---


def test_file_document_files_into_the_intake_group_and_finishes_the_batch(s):
    done = []
    s.ctx.on_batch_done = done.append
    a, b = opco_doc(s), opco_doc(s, reference="2025-A-119")
    classify(s, a, OPCO_PATH)
    classify(s, b, OPCO_PATH.replace("118", "119"))
    first = file_document(s.ctx, a)
    assert first.path == OPCO_PATH.split("/")[:-1] and first.status == "filed"
    assert first.badge_until is not None and first.filed_by == "mona"
    assert done == []
    file_document(s.ctx, b)
    assert done == [s.batch]
    f, g = T["file_ops"], T["op_groups"]
    with s.engine.connect() as conn:
        grp = conn.execute(select(g.c.id).where(g.c.batch_id == s.batch)).scalar()
        rows = conn.execute(select(f).where(f.c.action == "file")).mappings().all()
        batch = conn.execute(select(T["batches"]).where(T["batches"].c.id == s.batch)).one()
    assert {(r["group_id"], r["batch_id"], r["actor"], r["via"]) for r in rows} == {
        (grp, s.batch, "mona", "pipeline")
    }
    assert batch.status == "done" and batch.finished_at is not None
    assert s.row(a)["pipeline_stage"] == "done"
    assert file_document(s.ctx, a).path == first.path


@pytest.mark.parametrize(
    ("due", "deadlines"), [(date(2026, 10, 13), 0), (date(2026, 10, 14), 1), (date(2026, 11, 1), 1)]
)
def test_extracted_deadline_only_on_or_after_arrival(s, due, deadlines):
    doc = opco_doc(s, due_date=due, amount=120, verified={"due_date": True})
    classify(s, doc, OPCO_PATH)
    file_document(s.ctx, doc)
    t = T["deadlines"]
    with s.engine.connect() as conn:
        rows = conn.execute(select(t).where(t.c.document_id == doc)).mappings().all()
    assert len(rows) == deadlines
    if rows:
        assert rows[0]["origin"] == "extracted" and rows[0]["due_date"] == due


def test_unverified_due_date_makes_no_deadline(s):
    doc = opco_doc(s, due_date=date(2026, 11, 1), verified={"due_date": False})
    classify(s, doc, OPCO_PATH)
    file_document(s.ctx, doc)
    with s.engine.connect() as conn:
        assert conn.execute(select(T["deadlines"])).all() == []


def test_arrival_is_taken_as_a_paris_date(s):
    from datetime import UTC, datetime

    late = datetime(2026, 10, 13, 22, 30, tzinfo=UTC)  # 00:30 on the 14th in Paris
    doc = opco_doc(s, due_date=date(2026, 10, 13), verified={"due_date": True}, arrived_at=late)
    classify(s, doc, OPCO_PATH)
    file_document(s.ctx, doc)
    with s.engine.connect() as conn:
        assert conn.execute(select(T["deadlines"])).all() == []


@pytest.mark.parametrize("failure", ["EACCES", "ENOENT", "forbidden_path"])
def test_filing_failure_lands_in_review_with_conflict(s, failure):
    done = []
    s.ctx.on_batch_done = done.append
    doc = opco_doc(s)
    path = "../escape.pdf" if failure == "forbidden_path" else OPCO_PATH
    classify(s, doc, path)

    class Broken(Fs):
        def link(self, src, dst):
            raise OSError(getattr(errno, failure), failure)

    if failure != "forbidden_path":
        s.ctx.ops.fs = Broken()
    out = file_document(s.ctx, doc)
    r = s.row(doc)
    assert (out.status, out.reasons, out.pipeline_stage) == ("review", ["conflict"], "failed")
    assert r["pipeline_error"] == failure and r["location"] == "inbox"
    assert review_open(s, doc) == 1
    assert done == [s.batch]


# --- correct_document (C4 §3.5) ---


def test_correction_refiles_and_closes_the_review_item(s):
    doc = s.doc(counterparty="unim", category="insurance", subcategory="prevoyance",
                entity="personal", doc_date=date(2025, 11, 3))  # fmt: skip
    out = correct_document(s.ctx, doc, actor="mona", via="chat", entity="Cabinet Marchand")
    assert out.outcome == "moved"
    assert s.disk_path(doc).relative_to(s.ctx.ops.roots.archive).as_posix() == (
        "Cabinet Marchand/Assurances/UNIM/Prévoyance/2025/2025-11-03_UNIM_Prevoyance.pdf"
    )
    r = T["review_items"]
    with s.engine.connect() as conn:
        item = conn.execute(select(r).where(r.c.document_id == doc)).mappings().one()
        entries = conn.execute(select(T["file_ops"])).mappings().all()
        cls = (
            conn.execute(
                select(T["classifications"]).where(
                    T["classifications"].c.id == s.row(doc)["classification_id"]
                )
            )
            .mappings()
            .one()
        )
    assert (item["status"], item["resolution"], item["resolved_by"]) == (
        "resolved",
        "corrected",
        "mona",
    )
    assert [(e["action"], e["actor"], e["via"]) for e in entries] == [("file", "mona", "chat")]
    assert cls["method"] == "user"
    assert s.row(doc)["fiscal_year"] == 2025
    again = correct_document(s.ctx, doc, actor="mona", via="chat", entity="cabinet")
    assert (again.outcome, again.journal_ids) == ("unchanged", [])


def test_correction_of_a_date_writes_doc_update_and_a_rename(s):
    doc = opco_doc(s, status="review")
    correct_document(s.ctx, doc, actor="user", via="ui", entity="cabinet")
    out = correct_document(s.ctx, doc, actor="user", via="ui", doc_date=date(2026, 3, 1))
    f = T["file_ops"]
    with s.engine.connect() as conn:
        actions = [e.action for e in conn.execute(select(f).where(f.c.id.in_(out.journal_ids)))]
    assert sorted(actions) == ["doc.update", "rename"]
    assert s.row(doc)["current_path"].rpartition("/")[2].startswith("2026-03-01_")
    undo(s.ctx, actor="user", via="ui", journal_id=max(out.journal_ids))
    assert s.row(doc)["current_path"].rpartition("/")[2].startswith("2026-02-27_")
    assert s.row(doc)["doc_date"] == date(2026, 3, 1)


def test_correction_counts_against_the_rule_that_filed_it(s):
    doc = opco_doc(s)
    rid = s.rule_id("opco-cabinet")
    classify(s, doc, OPCO_PATH, rule=rid)
    file_document(s.ctx, doc)
    correct_document(s.ctx, doc, actor="mona", via="chat", entity="studio")
    with s.engine.connect() as conn:
        r = conn.execute(select(T["rules"]).where(T["rules"].c.id == rid)).mappings().one()
    assert r["corrections_since"] == 1
    assert s.row(doc)["rule_id"] is None


def test_scope_all_drafts_a_rule_above_the_seed_rule(s):
    doc = opco_doc(s, status="review")
    out = correct_document(s.ctx, doc, actor="mona", via="chat", entity="studio", scope="all")
    assert out.rule is not None and out.rule.state == "draft" and out.rule.source == "correction"
    assert out.rule.priority == 11
    assert [c.model_dump() for c in out.rule.conditions] == [
        {"field": "counterparty", "op": "equals", "value": "opco"}
    ]
    assert out.rule.action.entity == "studio" and out.rule.action.category == "payment_calls"
    assert out.preview is not None and out.preview.stays == [doc]
    other = opco_doc(s, status="review", reference="2025-A-200")
    assert [m.document_id for m in preview_rule(s.ctx, out.rule.id).moves] == [other]
    again = correct_document(s.ctx, doc, actor="mona", via="chat", entity="studio", scope="all")
    assert again.rule.id == out.rule.id and again.outcome == "unchanged"
    exported = (s.ctx.config_dir / "rules.yaml").read_text()
    assert out.rule.id not in exported and "source: correction" in exported


def test_correction_rejects_visitors_and_unknown_values(s):
    doc = opco_doc(s, status="review")
    with pytest.raises(ServiceError) as err:
        correct_document(s.ctx, doc, actor="mona", via="chat", entity="visitors")
    assert err.value.code == "not_allowed"
    with pytest.raises(ServiceError) as err:
        correct_document(s.ctx, doc, actor="mona", via="chat", entity="Garage Dupont")
    assert err.value.code == "invalid_argument" and err.value.field == "entity"
    assert {"key": "cabinet", "name": "Cabinet Marchand SELARL"} in err.value.valid
    assert all(v["key"] != "visitors" for v in err.value.valid)
    with pytest.raises(ServiceError) as err:
        correct_document(s.ctx, doc, actor="mona", via="chat")
    assert err.value.code == "invalid_argument"
    vis = s.doc(counterparty="opco", category="payment_calls", entity="visitors",
                batch=s.new_batch(visitor=True))  # fmt: skip
    with pytest.raises(ServiceError) as err:
        correct_document(s.ctx, vis, actor="mona", via="chat", entity="cabinet")
    assert err.value.code == "not_allowed"


def test_labels_resolve_in_any_language(s):
    doc = opco_doc(s, status="review")
    correct_document(s.ctx, doc, actor="user", via="ui", entity="studio",
                     category="Cereri de plată", subcategory="Contribution OPCO")  # fmt: skip
    r = s.row(doc)
    assert (r["category_id"], r["subcategory_key"]) == ("payment_calls", "contribution_opco")


# --- alias learning (C5 §6.2.5, §11 test 13) ---


def aliases(s: Services) -> dict[str, str]:
    a = T["counterparty_aliases"]
    with s.engine.connect() as conn:
        return dict(conn.execute(select(a.c.alias_norm, a.c.counterparty_id)).all())


def test_alias_learning_merges_an_extracted_counterparty(s):
    with s.engine.begin() as conn:
        x = resolve_counterparty(conn, "AGIPI Retraite Madelin")
    xkey = {v: k for k, v in s.ids("counterparties").items()}[x]
    doc = s.doc(counterparty=xkey, extracted_counterparty="AGIPI Retraite Madelin",
                category="insurance", entity="personal", doc_date=date(2025, 4, 14))  # fmt: skip
    other = s.doc(counterparty=xkey, category="insurance", entity="personal")
    with s.engine.begin() as conn:
        conn.execute(
            insert(T["rules"]).values(
                id=new_id("rul"), key="x-rule", name="x", state="draft", source="correction",
                priority=10, conditions=[{"field": "counterparty", "op": "equals", "value": xkey}],
                action={"entity": "personal", "counterparty": xkey},
                condition_text={"en": "-", "fr": "-", "ro": "-"},
            )
        )  # fmt: skip
    correct_document(s.ctx, doc, actor="mona", via="chat", counterparty="AGIPI")
    agipi = s.ids("counterparties")["agipi"]
    assert x not in s.ids("counterparties").values()
    assert aliases(s)[norm("AGIPI Retraite Madelin")] == agipi
    assert s.row(other)["counterparty_id"] == agipi
    with s.engine.connect() as conn:
        rule = conn.execute(select(T["rules"]).where(T["rules"].c.key == "x-rule")).mappings().one()
        cps = conn.execute(select(T["counterparties"])).mappings().all()
        assert resolve_counterparty(conn, "agipi retraite madelin") == agipi
    assert rule["conditions"][0]["value"] == "agipi" and rule["action"]["counterparty"] == "agipi"
    assert rule["version"] == 2
    al = aliases(s)
    assert all(al[c["name_norm"]] == c["id"] for c in cps)


def test_alias_learning_never_takes_a_curated_name(s):
    doc = s.doc(counterparty="unim", extracted_counterparty="UNIM", category="insurance",
                entity="cabinet", doc_date=date(2025, 11, 3))  # fmt: skip
    unim = s.ids("counterparties")["unim"]
    correct_document(s.ctx, doc, actor="mona", via="chat", counterparty="AGIPI")
    assert aliases(s)["unim"] == unim
    assert s.row(doc)["counterparty_id"] == s.ids("counterparties")["agipi"]


def test_new_spelling_becomes_an_alias(s):
    doc = s.doc(counterparty="agipi", extracted_counterparty="A G I P I", category="insurance",
                entity="personal")  # fmt: skip
    correct_document(s.ctx, doc, actor="mona", via="chat", counterparty="AGIPI",
                     entity="cabinet")  # fmt: skip
    assert aliases(s)[norm("A G I P I")] == s.ids("counterparties")["agipi"]


# --- preview_rule / apply_rule (C4 §3.8, §3.9) ---


def test_apply_rule_moves_candidates_in_one_group_and_keeps_its_counts(s):
    rid = s.rule_id("opco-cabinet")
    docs = [opco_doc(s, status="review", reference=f"R-{i}") for i in range(3)]
    vis = s.doc(counterparty="opco", category="payment_calls", entity="cabinet",
                doc_date=date(2026, 2, 27), batch=s.new_batch(visitor=True))  # fmt: skip
    before = preview_rule(s.ctx, rid)
    assert (before.moves_total, before.stays_total, before.applied) == (3, 0, False)
    assert vis not in [m.document_id for m in before.moves]
    out = apply_rule(s.ctx, rid, actor="mona", via="chat")
    assert (out.moved, out.unchanged, out.failed) == (3, 0, [])
    after = out.preview
    assert (after.moves_total, after.stays_total, after.applied, after.group_id) == (
        3, 0, True, out.group_id
    )  # fmt: skip
    f = T["file_ops"]
    with s.engine.connect() as conn:
        rows = conn.execute(select(f).where(f.c.group_id == out.group_id)).mappings().all()
        rule = conn.execute(select(T["rules"]).where(T["rules"].c.id == rid)).mappings().one()
    assert sorted(r["action"] for r in rows) == ["file", "file", "file"]
    assert rule["fired_count"] == 3 and rule["state"] == "active"
    for d in docs:
        assert s.row(d)["rule_id"] == rid and review_open(s, d) == 0
    second = apply_rule(s.ctx, rid, actor="mona", via="chat")
    assert (second.moved, second.group_id) == (0, None)
    assert preview_rule(s.ctx, rid).moves_total == 3


def test_activating_rule_change_joins_the_apply_group(s):
    rid = s.rule_id("unim-business")
    doc = s.doc(counterparty="unim", category="insurance", subcategory="prevoyance",
                entity="cabinet", amount=120, doc_date=date(2025, 11, 3))  # fmt: skip
    out = apply_rule(s.ctx, rid, actor="mona", via="chat")
    f = T["file_ops"]
    with s.engine.connect() as conn:
        rows = conn.execute(select(f).where(f.c.group_id == out.group_id)).mappings().all()
    assert sorted(r["action"] for r in rows) == ["file", "rule.change"]
    change = next(r for r in rows if r["action"] == "rule.change")
    assert (change["before"]["state"], change["after"]["state"]) == ("disabled", "active")
    assert s.row(doc)["location"] == "archive"


def test_undoing_an_apply_restores_the_preview(s):
    rid = s.rule_id("opco-cabinet")
    docs = [opco_doc(s, status="review", reference=f"R-{i}") for i in range(2)]
    out = apply_rule(s.ctx, rid, actor="mona", via="chat")
    u = undo(s.ctx, actor="mona", via="chat", group_id=out.group_id)
    assert len(u.undone) == 2 and not u.skipped
    assert all(s.row(d)["status"] == "review" and review_open(s, d) == 1 for d in docs)
    p = preview_rule(s.ctx, rid)
    assert (p.applied, p.moves_total) == (False, 2)


def test_conflicting_rules_are_not_candidates(s):
    doc = opco_doc(s, status="review")
    with s.engine.begin() as conn:
        conn.execute(
            insert(T["rules"]).values(
                id=new_id("rul"), key="opco-studio", name="rival", state="active", source="seed",
                priority=10,
                conditions=[{"field": "counterparty", "op": "equals", "value": "OPCO"}],
                action={"entity": "studio", "category": "payment_calls"},
                condition_text={"en": "-", "fr": "-", "ro": "-"},
            )
        )  # fmt: skip
    p = preview_rule(s.ctx, s.rule_id("opco-cabinet"))
    assert (p.moves_total, p.stays_total) == (0, 0)
    assert s.row(doc)["location"] == "inbox"


def test_rule_dto_destination(s):
    p = preview_rule(s.ctx, s.rule_id("agipi-per-by-person"))
    assert p.rule.destination == ["Personnel", "{person}", "Assurances", "AGIPI", "PER", "{year}"]
    p = preview_rule(s.ctx, s.rule_id("hello-bank-lmnp"))
    assert p.rule.destination == ["LMNP", "Angers-Strasbourg", "Banque", "{fy}"]
    fr = preview_rule(s.ctx, s.rule_id("opco-cabinet"), lang="fr").rule
    assert fr.condition.startswith("Quand l'émetteur est OPCO")


# --- undo, delete, restore ---


def test_undo_takes_one_id(s):
    with pytest.raises(ServiceError) as err:
        undo(s.ctx, actor="mona", via="chat")
    assert err.value.code == "invalid_argument"
    with pytest.raises(ServiceError) as err:
        undo(s.ctx, actor="mona", via="chat", journal_id=1, group_id="grp_x")
    assert err.value.code == "invalid_argument"
    with pytest.raises(ServiceError) as err:
        undo(s.ctx, actor="mona", via="chat", journal_id=999_999)
    assert err.value.code == "not_found"


def test_undo_reports_skips(s):
    doc = opco_doc(s, status="review")
    out = correct_document(s.ctx, doc, actor="mona", via="chat", entity="cabinet")
    (eid,) = out.journal_ids
    first = undo(s.ctx, actor="mona", via="chat", journal_id=eid)
    assert first.undone[0]["journal_id"] == eid and first.undone[0]["location"] == "inbox"
    again = undo(s.ctx, actor="mona", via="chat", journal_id=eid)
    assert again.skipped == [{"journal_id": eid, "state": "undone"}]
    redo = undo(s.ctx, actor="mona", via="chat", journal_id=first.undone[0]["entry_id"])
    assert redo.undone and s.row(doc)["location"] == "archive"


def test_delete_and_restore(s):
    doc = opco_doc(s, status="review")
    with pytest.raises(ServiceError) as err:
        delete_document(s.ctx, doc, actor="mona", via="chat")
    assert err.value.code == "not_allowed"
    e = delete_document(s.ctx, doc, actor="user", via="ui")
    assert (e.action, e.after.location, e.undo_state) == ("delete", "trash", "undoable")
    assert review_open(s, doc) == 0
    r = restore_document(s.ctx, doc, actor="user", via="ui")
    assert r.action == "undo" and s.row(doc)["location"] == "inbox" and review_open(s, doc) == 1
    out = undo(s.ctx, actor="mona", via="chat", journal_id=r.id)
    assert out.skipped == [{"journal_id": r.id, "state": "not_allowed"}]
    assert s.row(doc)["location"] == "inbox"


# --- batch lifecycle (C1 §12 test 9, filing side) ---


def test_batch_done_exactly_once_under_concurrent_filing(s, monkeypatch):
    from mona.services import pipeline

    real = pipeline.finish_batch_if_done
    together = threading.Barrier(3, timeout=10)

    def overlapping(conn, batch_id, now):
        together.wait()
        return real(conn, batch_id, now)

    monkeypatch.setattr(pipeline, "finish_batch_if_done", overlapping)
    calls = []
    lock = threading.Lock()

    def hook(b):
        with lock:
            calls.append(b)

    s.ctx.on_batch_done = hook
    docs = [opco_doc(s, reference=f"C-{i}") for i in range(3)]
    for i, d in enumerate(docs):
        classify(s, d, OPCO_PATH.replace("118", f"C-{i}"))
    barrier = threading.Barrier(3)

    def run(d):
        barrier.wait()
        file_document(s.ctx, d)

    threads = [threading.Thread(target=run, args=(d,)) for d in docs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls == [s.batch]
    with s.engine.connect() as conn:
        b = conn.execute(select(T["batches"]).where(T["batches"].c.id == s.batch)).one()
    assert b.status == "done"


def test_iban_condition_uses_the_settings_salt(s):
    doc = s.doc(counterparty="hello-bank", category="bank", subcategory="releve", entity="lmnp",
                text=f"Relevé de compte IBAN {IBAN_SPACED}", doc_date=date(2025, 1, 16),
                period_end=date(2025, 1, 15))  # fmt: skip
    p = preview_rule(s.ctx, s.rule_id("hello-bank-lmnp"))
    assert [m.document_id for m in p.moves] == [doc]


def test_search_index_follows_a_correction(s):
    from sqlalchemy import text

    doc = opco_doc(s, status="review")
    q = text("SELECT id FROM documents WHERE fts @@ websearch_to_tsquery('mona', :q)")
    correct_document(s.ctx, doc, actor="user", via="ui", entity="studio")
    with s.engine.connect() as conn:
        assert conn.execute(q, {"q": "numérique"}).scalars().all() == [doc]
        assert conn.execute(q, {"q": "selarl"}).scalars().all() == []
    correct_document(s.ctx, doc, actor="user", via="ui", entity="cabinet")
    with s.engine.connect() as conn:
        assert conn.execute(q, {"q": "selarl"}).scalars().all() == [doc]
