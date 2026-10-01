"""C6 §10 test 2 (triggers, concurrency) and test 3 (reuse and scope equality)."""

import threading
import time

import pytest
from sqlalchemy import update

from mona.interviews import hooks, service, triggers
from mona.interviews.candidates import scope_equal
from mona.interviews.generate import generate_interview
from mona.services.registry import T
from tests.l4_world import RecordedModel, World

pytestmark = pytest.mark.usefixtures("l4_db")

# Demo-script order: 10 auto-filed, then AGIPI ×3, Hello bank ×3, UNIM, then the unreadable.
LIVE = [("filed", ())] * 10 + [("review", ("entity",))] * 6 + [("review", ("low",))]
LIVE += [("unreadable", ("unreadable",))]
CPS = [None] * 10 + ["agipi"] * 3 + ["hello-bank"] * 3 + ["unim", None]


def settle(w: World, doc_id: str, status: str, reasons: tuple) -> None:
    d = T["documents"]
    values = {"status": status, "pipeline_stage": "done", "reasons": list(reasons)}
    if status == "filed":
        values |= {"location": "archive", "current_path": f"Cabinet Marchand/{doc_id}.pdf"}
    with w.engine.begin() as conn:
        conn.execute(update(d).where(d.c.id == doc_id).values(**values))


def finish(w: World, batch: str) -> None:
    b = T["batches"]
    with w.engine.begin() as conn:
        conn.execute(update(b).where(b.c.id == batch).values(status="done"))


def demo_drop(w: World) -> tuple[str, list[str], str]:
    """Two uncovered review documents of an earlier batch, then the live drop, unsettled."""
    earlier = w.batch()
    for n in range(2):
        w.doc(f"earlier {n}", batch=earlier, extracted_counterparty=f"Old {n}")
    live = w.batch(status="running")
    docs = [
        w.doc(
            f"live {n + 1}",
            batch=live,
            status="processing",
            stage="classifying",
            reasons=(),
            counterparty=cp,
        )
        for n, cp in enumerate(CPS)
    ]
    return live, docs, earlier


def interviews_by_scope(w: World) -> dict[str, list]:
    out: dict[str, list] = {}
    for iv in w.interviews():
        out.setdefault(iv["scope"]["type"], []).append(iv)
    return out


def test_early_start_at_7_covers_all_seven_candidates():
    w = World()
    w.set_settings(debrief_queue_threshold=5)
    live, docs, _ = demo_drop(w)
    started_at = None
    for n, (doc_id, (status, reasons)) in enumerate(zip(docs, LIVE, strict=True), start=1):
        settle(w, doc_id, status, reasons)
        if triggers.debrief_check(w.ctx, live) and started_at is None:
            started_at = n
    finish(w, live)
    assert triggers.debrief_check(w.ctx, live) == []
    by = interviews_by_scope(w)
    assert started_at == 17
    assert list(by) == ["batch"]
    assert by["batch"][0]["scope"]["candidate_document_ids"] == sorted(docs[10:17])
    agipi = set(docs[10:13])
    assert (
        sum(bool(agipi & set(iv["scope"]["candidate_document_ids"])) for iv in w.interviews()) == 1
    )


def test_early_start_at_5_leaves_two_uncovered_for_the_queue_once_the_batch_is_done():
    w = World()
    w.set_settings(debrief_queue_threshold=4)
    live, docs, _ = demo_drop(w)
    _set_early_min(w, 5)
    started_at = None
    for n, (doc_id, (status, reasons)) in enumerate(zip(docs, LIVE, strict=True), start=1):
        settle(w, doc_id, status, reasons)
        if triggers.debrief_check(w.ctx, live) and started_at is None:
            started_at = n
    assert started_at == 15
    by = interviews_by_scope(w)
    assert list(by) == ["batch"]
    assert by["batch"][0]["scope"]["candidate_document_ids"] == sorted(docs[10:15])
    finish(w, live)
    created = triggers.debrief_check(w.ctx, live)
    by = interviews_by_scope(w)
    assert len(by["batch"]) == 1 and len(created) == 1
    queue = by["queue"][0]["scope"]["candidate_document_ids"]
    assert set(docs[15:17]) <= set(queue) and len(queue) == 4


def _set_early_min(w: World, n: int) -> None:
    """A9's column lands with L2's migration; until then the check reads the default (5)."""
    from sqlalchemy import text

    with w.engine.begin() as conn:
        has = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns WHERE table_name = 'settings'"
                " AND column_name = 'debrief_early_min'"
            )
        ).first()
        if has is None:
            conn.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN debrief_early_min smallint NOT NULL DEFAULT 5"
                )
            )
        conn.execute(text("UPDATE settings SET debrief_early_min = :n"), {"n": n})


@pytest.fixture(autouse=True)
def early_min_7(l4_db):
    """C9 §6.7: the stage value."""
    _set_early_min(World(), 7)


def test_a_batch_ending_with_3_candidates_gets_its_debrief_at_the_end():
    w = World()
    b = w.batch(status="running")
    for n in range(3):
        w.doc(f"q {n}", batch=b, counterparty="agipi")
    assert triggers.debrief_check(w.ctx, b) == []
    finish(w, b)
    created = triggers.debrief_check(w.ctx, b)
    assert len(created) == 1 and w.row("batches", b)["debrief_interview_id"] == created[0]
    assert triggers.debrief_check(w.ctx, b) == []


def test_telegram_and_visitor_batches_get_no_batch_debrief():
    w = World()
    for kw in ({"source": "telegram"}, {"visitor": True}):
        b = w.batch(**kw)
        w.doc("one", batch=b, counterparty="agipi")
        assert triggers.debrief_check(w.ctx, b) == []


def test_the_queue_trigger_fires_at_the_threshold_and_never_for_asked_documents():
    w = World()
    w.set_settings(debrief_queue_threshold=3)
    b1 = w.batch(source="telegram")
    for n in range(2):
        w.doc(f"t {n}", batch=b1, extracted_counterparty=f"Shop {n}")
    assert triggers.debrief_check(w.ctx, b1) == []
    b2 = w.batch(source="telegram")
    w.doc("t 2", batch=b2, extracted_counterparty="Shop 2")
    [queue] = triggers.debrief_check(w.ctx, b2)
    assert len(w.row("interviews", queue)["scope"]["candidate_document_ids"]) == 3
    generate_interview(w.ctx, queue, model_factory=lambda: RecordedModel(w, pass2=_one_q(w)))
    service.cancel(w.ctx, queue)
    b3 = w.batch(source="telegram")
    w.doc("t 3", batch=b3, extracted_counterparty="Shop 3")
    assert triggers.debrief_check(w.ctx, b3) == []


def _one_q(w: World):
    def out(user: str) -> dict:
        from tests.l4_world import input_of

        aliases = [d["alias"] for d in input_of(user)["documents"]]
        branch = {
            "conditions": [{"field": "text", "op": "contains", "value": "shop"}],
            "action": {"entity": "cabinet", "unit": None, "category": None, "subcategory": None},
        }
        return {
            "questions": [
                {
                    "text": "Shops?",
                    "affected": aliases,
                    "evidence": [],
                    "options": [
                        {
                            "id": "a",
                            "label": "Practice",
                            "rule_draft": {
                                "kind": "always",
                                "discriminator": None,
                                "branches": [branch],
                            },
                        },
                        {
                            "id": "b",
                            "label": "Ask",
                            "rule_draft": {"kind": "ask", "discriminator": None, "branches": []},
                        },
                    ],
                    "suggested": "a",
                    "confidence": 0.5,
                }
            ]
        }

    return out


def _race(w: World, batches: list[str], monkeypatch) -> None:
    real = triggers.uncovered

    def slow(conn, scope):
        out = real(conn, scope)
        time.sleep(0.15)
        return out

    monkeypatch.setattr(triggers, "uncovered", slow)
    barrier = threading.Barrier(len(batches))
    errors: list[BaseException] = []

    def check(b: str) -> None:
        barrier.wait()
        try:
            triggers.debrief_check(w.ctx, b)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=check, args=(b,)) for b in batches]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_concurrent_checks_of_one_batch_create_one_interview(monkeypatch):
    w = World()
    b = w.batch()
    for n in range(3):
        w.doc(f"q {n}", batch=b, counterparty="agipi")
    _race(w, [b, b], monkeypatch)
    assert len(w.interviews()) == 1


@pytest.mark.parametrize("attempt", range(3))
def test_two_batches_settling_together_create_one_queue_debrief(monkeypatch, attempt):
    w = World()
    w.set_settings(debrief_queue_threshold=2)
    batches = []
    for n in range(2):
        b = w.batch(source="telegram")
        w.doc(f"t {n}a", batch=b, extracted_counterparty=f"A{n}")
        w.doc(f"t {n}b", batch=b, extracted_counterparty=f"B{n}")
        batches.append(b)
    _race(w, batches, monkeypatch)
    assert [iv["scope"]["type"] for iv in w.interviews()] == ["queue"]


def test_a_hook_whose_defer_hits_already_enqueued_returns_normally():
    w = World()
    b = w.batch(status="running")
    hooks.on_document_settled(b)
    hooks.on_document_settled(b)
    hooks.on_batch_done(b)
    jobs = w.job_rows("debrief_check")
    assert [(j["queue_name"], j["queueing_lock"], j["args"]) for j in jobs] == [
        ("cpu", f"debrief_check:{b}", {"batch_id": b})
    ]


def test_creating_an_interview_enqueues_generation_at_priority_10():
    w = World()
    b = w.batch()
    w.doc("q", batch=b, counterparty="agipi")
    [iv] = triggers.debrief_check(w.ctx, b)
    [job] = w.job_rows("generate_interview")
    assert (job["queue_name"], job["priority"], job["queueing_lock"]) == (
        "llm",
        10,
        f"generate_interview:{iv}",
    )
    assert job["args"] == {"interview_id": iv}


# --- test 3: reuse ---


def test_start_reuses_a_generating_or_ready_interview_and_starts_after_answers():
    w = World()
    b = w.batch()
    w.cluster(b)
    first = service.start(w.ctx, {"type": "batch", "batch_id": b}, lang="en")
    again = service.start(w.ctx, {"type": "batch", "batch_id": b})
    assert (again.interview_id, again.reused, again.status) == (
        first.interview_id,
        True,
        "generating",
    )
    assert len(w.job_rows("generate_interview")) == 1
    generate_interview(w.ctx, first.interview_id, model_factory=lambda: RecordedModel(w))
    ready = service.start(w.ctx, {"type": "batch", "batch_id": b})
    assert (ready.interview_id, ready.status, ready.open_questions) == (
        first.interview_id,
        "ready",
        5,
    )
    from mona.interviews import answers

    for q in w.questions(first.interview_id):
        answers.skip(w.ctx, q["id"])
    fresh = service.start(w.ctx, {"type": "batch", "batch_id": b})
    assert not fresh.reused and fresh.interview_id != first.interview_id
    assert w.row("batches", b)["debrief_interview_id"] == fresh.interview_id


def test_an_empty_scope_is_refused():
    w = World()
    with pytest.raises(service.ServiceError) as e:
        service.start(w.ctx, {"type": "queue"})
    assert (e.value.code, e.value.field) == ("invalid_argument", "scope")


@pytest.mark.parametrize(
    ("a", "b", "equal"),
    [
        ({"type": "queue"}, {"type": "queue", "candidate_document_ids": ["x"]}, True),
        ({"type": "seed"}, {"type": "seed"}, True),
        ({"type": "batch", "batch_id": "b1"}, {"type": "batch", "batch_id": "b1"}, True),
        ({"type": "batch", "batch_id": "b1"}, {"type": "batch", "batch_id": "b2"}, False),
        (
            {"type": "counterparty", "counterparty_id": "c"},
            {"type": "counterparty", "counterparty_id": "c"},
            True,
        ),
        (
            {"type": "documents", "document_ids": ["d2", "d1"]},
            {"type": "documents", "document_ids": ["d1", "d2"]},
            True,
        ),
        (
            {"type": "documents", "document_ids": ["d1"]},
            {"type": "documents", "document_ids": ["d1", "d2"]},
            False,
        ),
        ({"type": "queue"}, {"type": "seed"}, False),
    ],
)
def test_scope_equality(a, b, equal):
    assert scope_equal(a, b) is equal


def test_documents_scope_reuse_is_order_insensitive():
    w = World()
    b = w.batch()
    ids = [w.doc(f"d {n}", batch=b, counterparty="agipi") for n in range(2)]
    one = service.start(w.ctx, {"type": "documents", "document_ids": ids})
    two = service.start(w.ctx, {"type": "documents", "document_ids": list(reversed(ids))})
    assert two.reused and two.interview_id == one.interview_id
