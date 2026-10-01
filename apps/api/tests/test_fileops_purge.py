"""C9 §5 and §8 test 6: the Visitors purge."""

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import insert, select, update
from typer.testing import CliRunner

from mona import cli, jobs
from mona.fileops import SimulatedCrash, sha256_file
from mona.fileops.purge import purge_visitors
from mona.ids import new_id
from mona.pipeline import runtime
from mona.services import file_document, undo
from mona.services.corrections import resolve_counterparty
from mona.services.registry import T
from tests.services_world import Services

TARGET = "Visitors/Factures reçues/2026"


@pytest.fixture
def s(seeded_engine, tmp_path) -> Services:
    return Services(seeded_engine, tmp_path / "data")


def classify(s: Services, doc: str, path: str) -> None:
    folder, _, name = path.rpartition("/")
    cls = new_id("cls")
    row = s.row(doc)
    with s.engine.begin() as conn:
        conn.execute(
            insert(T["classifications"]).values(
                id=cls, document_id=doc, method="llm", entity_id=row["entity_id"],
                category_id=row["category_id"], confidence=95, band="high", reasons=[],
                proposed_path=folder, proposed_file_name=name,
            )
        )  # fmt: skip
        d = T["documents"]
        conn.execute(d.update().where(d.c.id == doc).values(classification_id=cls))


def caches(s: Services, doc: str) -> list[Path]:
    sha = s.row(doc)["sha256"]
    return sorted((s.ctx.textcache / sha[:2]).glob(f"{sha}.*"))


@dataclass
class VisitorBatch:
    batch: str
    filed: str
    review: str
    practice: str
    deadline: str
    reminder: str
    groups: list[str]
    shas: list[str]


def visitor_batch(s: Services) -> VisitorBatch:
    """§8 test 6's batch: a filed document (hand-added deadline journaled by subject only,
    reminders, a card event, an adopted trash copy), a review document, a duplicate item;
    group-undone, redone, then one entry undone again."""
    practice = s.doc(counterparty="opco", category="payment_calls", entity="cabinet")
    vb = s.new_batch(visitor=True)
    content = b"%PDF-1.4 visitor " + secrets.token_bytes(32)
    filed = s.doc(entity="visitors", category="payment_calls", status="processing", batch=vb,
                  content=content)  # fmt: skip
    review = s.doc(entity="visitors", category="payment_calls", status="processing", batch=vb)
    classify(s, filed, f"{TARGET}/facture-eau.pdf")
    classify(s, review, f"{TARGET}/lettre.pdf")
    archive = s.ctx.ops.roots.archive / TARGET
    archive.mkdir(parents=True)
    (archive / "facture-eau.pdf").write_bytes(content)
    for doc in (filed, review):
        file_document(s.ctx, doc)
    g, f = T["op_groups"], T["file_ops"]
    with s.engine.connect() as conn:
        intake = conn.execute(select(g.c.id).where(g.c.batch_id == vb)).scalar_one()
    u = undo(s.ctx, actor="user", via="ui", group_id=intake).group_id
    r = undo(s.ctx, actor="user", via="ui", group_id=u).group_id
    with s.engine.connect() as conn:
        redo = conn.execute(
            select(f.c.id).where(f.c.group_id == r, f.c.document_id == review)
        ).scalar_one()
    undo(s.ctx, actor="user", via="ui", journal_id=redo)
    ents = s.ids("entities")
    ddl, rem = new_id("ddl"), new_id("rem")
    now = s.clock()
    with s.engine.begin() as conn:
        conn.execute(insert(T["deadlines"]).values(
            id=ddl, document_id=filed, entity_id=ents["visitors"], label="Water bill",
            due_date=date(2026, 11, 2), origin="user"))  # fmt: skip
        conn.execute(insert(T["reminders"]).values(
            id=rem, deadline_id=ddl, remind_on=date(2026, 10, 30), created_by="user"))  # fmt: skip
        conn.execute(insert(T["reminders"]).values(
            id=new_id("rem"), document_id=filed, remind_on=date(2026, 10, 31),
            created_by="user"))  # fmt: skip
        for action, subject in (("deadline.add", ddl), ("reminder.add", rem)):
            conn.execute(insert(f).values(
                at=now, actor="user", via="ui", action=action, subject_id=subject,
                after={"id": subject}, undoable=False))  # fmt: skip
        conn.execute(insert(T["card_events"]).values(
            id=new_id("crd"), tool="get_document", kind="doc",
            subject={"document_id": filed}, channel="web"))  # fmt: skip
        p = s.row(practice)
        conn.execute(insert(T["intake_items"]).values(
            id=new_id("itm"), batch_id=vb, original_name="again.pdf", sha256=p["sha256"],
            size_bytes=p["size_bytes"], outcome="duplicate", document_id=practice))  # fmt: skip
    for doc in (filed, review):
        sha = s.row(doc)["sha256"]
        for ext in ("ocr.pdf", "p1.png", "model.c5-v1.json"):
            (s.ctx.textcache / sha[:2] / f"{sha}.{ext}").write_bytes(b"cache")
    assert s.row(filed)["location"] == "archive" and s.row(review)["status"] == "review"
    assert [p.name for p in (s.ctx.ops.roots.trash / filed).iterdir()] == ["facture-eau.pdf"]
    with s.engine.connect() as conn:
        targets = dict(conn.execute(select(g.c.id, g.c.target_group_id)).all())
    assert (targets[u], targets[r]) == (intake, u)
    shas = [s.row(d)["sha256"] for d in (filed, review)]
    return VisitorBatch(vb, filed, review, practice, ddl, rem, [intake, u, r], shas)


def files(s: Services) -> set[str]:
    roots = s.ctx.ops.roots
    return {
        str(Path(dirpath, n).relative_to(roots.data))
        for root in (roots.inbox, roots.archive, roots.trash)
        for dirpath, _, names in os.walk(root)
        for n in names
    }


def db_state(s: Services) -> dict[str, int]:
    with s.engine.connect() as conn:
        return {t: len(conn.execute(select(T[t])).all()) for t in (
            "documents", "file_ops", "op_groups", "batches", "intake_items", "deadlines",
            "reminders", "card_events")}  # fmt: skip


def invariants(s: Services) -> None:
    """C7 invariants 1–2: every document's file is in place; no file is a stray."""
    roots = s.ctx.ops.roots
    expected = set()
    with s.engine.connect() as conn:
        for d in conn.execute(select(T["documents"])).mappings():
            path = roots.root(d["location"]) / d["current_path"]
            assert sha256_file(path) == d["sha256"], d["id"]
            expected.add(str(path.relative_to(roots.data)))
    assert files(s) == expected


def assert_purged(s: Services, w: VisitorBatch) -> None:
    f, g = T["file_ops"], T["op_groups"]
    with s.engine.connect() as conn:
        assert conn.execute(select(T["documents"].c.id)).scalars().all() == [w.practice]
        assert conn.execute(select(f.c.id).where(
            f.c.document_id.in_([w.filed, w.review]) | f.c.subject_id.in_([w.deadline, w.reminder])
        )).all() == []  # fmt: skip
        assert conn.execute(select(g.c.id).where(g.c.id.in_(w.groups))).all() == []
        assert conn.execute(select(T["batches"].c.id)).scalars().all() == [s.batch]
        for t in ("deadlines", "reminders", "card_events"):
            assert conn.execute(select(T[t])).all() == [], t
        items = conn.execute(select(T["intake_items"])).all()
    assert items == []
    for sha in w.shas:
        assert list((s.ctx.textcache / sha[:2]).glob(f"{sha}.*")) == []
    assert caches(s, w.practice)
    assert not (s.ctx.ops.roots.trash / w.filed).exists()
    assert not (s.ctx.ops.roots.archive / "Visitors").exists()
    invariants(s)


def test_purge_after_24_hours_removes_the_batch_and_everything_derived(s):
    w = visitor_batch(s)
    before, on_disk = db_state(s), files(s)
    s.clock.advance(hours=23, minutes=59)
    out = purge_visitors(s.ctx.ops)
    assert (out.due, out.purged) == ([], [])
    assert db_state(s) == before and files(s) == on_disk
    s.clock.advance(minutes=1)
    out = purge_visitors(s.ctx.ops)
    assert out.purged == [w.filed, w.review] and out.batches == [w.batch] and out.failed == []
    assert_purged(s, w)


def test_purge_removes_extracted_counterparties_only_visitors_used(s):
    w = visitor_batch(s)
    c, d, cl, r, a = (T[t] for t in ("counterparties", "documents", "classifications", "rules",
                                     "accounts"))  # fmt: skip
    with s.engine.begin() as conn:
        made = {k: resolve_counterparty(conn, f"Eaux Fictives {k}")
                for k in ("only", "shared", "ruled", "banked")}  # fmt: skip
        made["seed"] = conn.execute(select(c.c.id).where(c.c.origin == "seed").limit(1)).scalar()
        key = conn.execute(select(c.c.key).where(c.c.id == made["ruled"])).scalar_one()
        conn.execute(update(d).where(d.c.id.in_([w.filed, w.review])).values(
            counterparty_id=made["only"]))  # fmt: skip
        conn.execute(update(d).where(d.c.id == w.practice).values(counterparty_id=made["shared"]))
        for doc, cp in ((w.filed, "shared"), (w.review, "ruled")):
            conn.execute(update(cl).where(cl.c.document_id == doc).values(counterparty_id=made[cp]))
        for doc, cp in ((w.filed, "banked"), (w.review, "seed")):
            conn.execute(insert(cl).values(
                id=new_id("cls"), document_id=doc, method="llm", counterparty_id=made[cp],
                confidence=50, band="low", reasons=[]))  # fmt: skip
        ruled = {"field": "counterparty", "op": "in", "value": ["opco", key]}
        conn.execute(update(r).where(r.c.key == "opco-cabinet").values(conditions=[ruled]))
        account = conn.execute(select(a.c.id).limit(1)).scalar_one()
        conn.execute(update(a).where(a.c.id == account).values(bank_counterparty_id=made["banked"]))
    out = purge_visitors(s.ctx.ops, ignore_age=True)
    assert out.purged == [w.filed, w.review] and out.failed == []
    with s.engine.connect() as conn:
        left = set(conn.execute(select(c.c.id)).scalars())
        aliases = set(conn.execute(select(T["counterparty_aliases"].c.counterparty_id)).scalars())
    assert made["only"] not in left | aliases
    assert {made[k] for k in ("shared", "ruled", "banked", "seed")} <= left


def test_a_crash_after_the_files_is_completed_by_the_next_run(s):
    w = visitor_batch(s)

    def crash(doc_id):
        raise SimulatedCrash("after_files")

    with pytest.raises(SimulatedCrash):
        purge_visitors(s.ctx.ops, ignore_age=True, crash=crash)
    out = purge_visitors(s.ctx.ops, ignore_age=True)
    invariants(s)
    assert out.purged == [w.filed, w.review] and out.failed == []
    assert_purged(s, w)


def test_a_failed_transaction_rolls_back_and_names_the_constraint(s, caplog):
    w = visitor_batch(s)
    f = T["file_ops"]
    with s.engine.begin() as conn:
        entry = conn.execute(
            select(f.c.id).where(f.c.document_id == w.filed).order_by(f.c.id)
        ).scalars().first()  # fmt: skip
        conn.execute(insert(f).values(
            actor="user", via="ui", action="undo", document_id=w.practice, undo_of=entry,
            fs_state="failed", undoable=True))  # fmt: skip
    with caplog.at_level(logging.INFO, logger="mona.fileops.purge"):
        out = purge_visitors(s.ctx.ops, ignore_age=True)
    assert out.failed == [w.filed] and out.purged == [w.review] and out.batches == []
    assert s.row(w.filed)["deleted_at"] is None
    assert not (s.ctx.ops.roots.archive / TARGET / "facture-eau.pdf").exists()
    assert "ForeignKeyViolation file_ops_undo_of_fkey" in caplog.text
    assert f"purged visitor document {w.review} (batch {w.batch})" in caplog.text


def test_dry_run_and_no_visitor_documents_change_nothing(s):
    w = visitor_batch(s)
    before, on_disk = db_state(s), files(s)
    out = purge_visitors(s.ctx.ops, ignore_age=True, dry_run=True)
    assert out.due == [(w.filed, w.batch), (w.review, w.batch)] and out.purged == []
    assert db_state(s) == before and files(s) == on_disk


def test_a_visitor_batch_of_duplicates_only_goes_too(s):
    p = s.row(s.doc(counterparty="opco", category="payment_calls", entity="cabinet"))
    vb = s.new_batch(visitor=True)
    with s.engine.begin() as conn:
        conn.execute(insert(T["intake_items"]).values(
            id=new_id("itm"), batch_id=vb, original_name="again.pdf", sha256=p["sha256"],
            size_bytes=p["size_bytes"], outcome="duplicate", document_id=p["id"]))  # fmt: skip
    s.clock.advance(hours=24)
    out = purge_visitors(s.ctx.ops)
    assert out.batches == [vb] and out.purged == []
    assert [b["id"] for b in s.engine.connect().execute(select(T["batches"])).mappings()] == [
        s.batch
    ]
    assert s.row(p["id"])["location"] == "inbox"


def test_the_periodic_job_runs_every_15_minutes_on_cpu():
    tasks = {k[0]: v for k, v in jobs.app.periodic_registry.periodic_tasks.items()}
    t = tasks["purge_visitors"]
    assert (t.cron, t.task.queue, t.task.queueing_lock) == ("*/15 * * * *", "cpu", "purge_visitors")


def test_the_command(s, monkeypatch):
    w = visitor_batch(s)
    monkeypatch.setattr(runtime, "get_context", lambda: s.ctx)
    dry = CliRunner().invoke(cli.app, ["purge-visitors", "--dry-run"])
    assert dry.exit_code == 0 and "0 documents due" in dry.output
    dry = CliRunner().invoke(cli.app, ["purge-visitors", "--now", "--dry-run"])
    assert f"would purge visitor document {w.filed} (batch {w.batch})" in dry.output
    run = CliRunner().invoke(cli.app, ["purge-visitors", "--now"])
    assert run.exit_code == 0 and "purged 2 documents, 1 batches" in run.output
    assert_purged(s, w)
