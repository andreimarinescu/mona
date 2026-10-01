"""C6 §10 test 8 (answers) and test 9 (undo of an Apply), on the recorded cluster."""

import pytest
from sqlalchemy import select

from mona.interviews import answers, service
from mona.interviews.generate import generate_interview
from mona.interviews.prompt import build_input
from mona.rules import store
from mona.rules.engine import evaluate
from mona.rules.grammar import RuleBody
from mona.services import registry, undo
from mona.services.placement import subject
from mona.services.registry import T
from tests.l4_world import RecordedModel, World

pytestmark = pytest.mark.usefixtures("l4_db")


@pytest.fixture
def debrief():
    w = World()
    b = w.batch()
    w.cluster(b)
    interview_id = service.start(w.ctx, {"type": "batch", "batch_id": b}, lang="en").interview_id
    assert (
        generate_interview(w.ctx, interview_id, model_factory=lambda: RecordedModel(w)) == "ready"
    )
    names = ("AGIPI", "Hello", "UNIM", "Atelier", "Orélia")
    qs = {next(n for n in names if n in q["text"]): q for q in w.questions(interview_id)}
    return w, interview_id, qs


def option(q, kind: str) -> str:
    return next(o["id"] for o in q["options"] if o["rule_draft"]["kind"] == kind)


def rules_of(w: World, question_id: str) -> list:
    r = T["rules"]
    with w.engine.connect() as conn:
        return list(
            conn.execute(
                select(r).where(r.c.origin_question_id == question_id).order_by(r.c.created_at)
            ).mappings()
        )


def entries(w: World, action: str, rule_id: str) -> list:
    f = T["file_ops"]
    with w.engine.connect() as conn:
        return list(
            conn.execute(
                select(f).where(f.c.action == action, f.c.rule_id == rule_id).order_by(f.c.id)
            ).mappings()
        )


# --- test 8 [M] ---


def test_always_drafts_one_rule_above_the_rules_it_corrects(debrief):
    w, _, qs = debrief
    with w.engine.begin() as conn:
        store.save_rule(
            conn,
            key="unim-any",
            name="unim-any",
            state="active",
            source="seed",
            body=RuleBody.model_validate(
                {
                    "conditions": [{"field": "counterparty", "op": "equals", "value": "unim"}],
                    "action": {"entity": "personal", "category": "insurance"},
                }
            ),
            priority=None,
            names=store.names(conn),
        )
    q = qs["UNIM"]
    out = answers.answer(w.ctx, q["id"], option_id="a", actor="user", via="ui")
    [rule] = rules_of(w, q["id"])
    assert out.rule_ids == [rule["id"]]
    assert (rule["state"], rule["source"], rule["priority"]) == ("draft", "interview", 11)
    assert rule["name"] == "UNIM · Yes, the practice"
    [created] = entries(w, "rule.create", rule["id"])
    assert (created["actor"], created["via"]) == ("user", "ui")
    assert [p.rule.id for p in out.previews] == [rule["id"]]
    assert out.previews[0].moves_total == 1
    assert w.row("interview_questions", q["id"])["status"] == "answered"


def test_depends_drafts_one_rule_per_branch_with_both_products(debrief):
    w, _, qs = debrief
    q = qs["AGIPI"]
    out = answers.answer(w.ctx, q["id"], option_id="a", actor="mona", via="chat")
    rules = rules_of(w, q["id"])
    assert [r["id"] for r in rules] == out.rule_ids and len(rules) == 2
    assert [r["name"] for r in rules] == [
        "AGIPI · Split by insured person, PER vs life (“plan d'épargne retraite” or “PER”)",
        "AGIPI · Split by insured person, PER vs life (“assurance vie”)",
    ]
    assert all(r["action"]["unit"] == {"from": "person"} for r in rules)
    paths = {m.document_id: "/".join(m.to) for p in out.previews for m in p.moves}
    assert paths == {
        w.tags["agipi-per-anna"]: "Personnel/Anna/Assurances/AGIPI/PER/2025",
        w.tags["agipi-vie-anna"]: "Personnel/Anna/Assurances/AGIPI/Assurance vie/2025",
        w.tags["agipi-vie-paul"]: "Personnel/Paul/Assurances/AGIPI/Assurance vie/2025",
    }


def test_ask_records_one_active_review_rule_that_sends_the_next_document_to_review(debrief):
    w, _, qs = debrief
    q = qs["Hello"]
    out = answers.answer(w.ctx, q["id"], option_id=option(q, "ask"), actor="user", via="ui")
    [rule] = rules_of(w, q["id"])
    assert out.rule_ids == [rule["id"]] and out.previews == []
    assert rule["state"] == "active" and rule["action"] == {"review": True}
    assert rule["conditions"] == [{"field": "counterparty", "op": "equals", "value": "hello-bank"}]
    later = w.doc(
        "Hello bank relevé avril 2025",
        batch=w.batch(),
        counterparty="hello-bank",
        category="bank",
        pages=["Hello bank!\nRelevé de compte n° 4"],
    )
    with w.engine.connect() as conn:
        snap = registry.load(conn)
        doc = conn.execute(select(T["documents"]).where(T["documents"].c.id == later)).mappings()
        outcome = evaluate(
            registry.rule_specs(conn), subject(conn, snap, doc.one(), w.ctx.textcache), snap.world
        )
    assert outcome.winner is not None and outcome.winner.id == rule["id"]
    assert outcome.destination is not None and outcome.destination.review is True


def test_free_text_drafts_nothing_and_feeds_later_interviews(debrief):
    w, _, qs = debrief
    q = qs["Hello"]
    out = answers.answer(
        w.ctx, q["id"], free_text="Those are the flat's statements.", actor="user", via="ui"
    )
    assert out.rule_ids == [] and out.previews == []
    assert w.row("interview_questions", q["id"])["status"] == "answered"
    with w.engine.connect() as conn:
        inp = build_input(conn, [w.tags["hello-jan"]], "en", w.ctx.textcache, w.clock())
    assert inp.body["earlier_explanations"] == [
        {
            "counterparty": "Hello bank",
            "question": q["text"],
            "answer": "Those are the flat's statements.",
        }
    ]


def test_the_same_answer_twice_is_one_set_of_rules_and_a_different_one_conflicts(debrief):
    w, _, qs = debrief
    q = qs["AGIPI"]
    first = answers.answer(w.ctx, q["id"], option_id="a", actor="user", via="ui")
    again = answers.answer(w.ctx, q["id"], option_id="a", actor="mona", via="chat")
    assert again.rule_ids == first.rule_ids and len(rules_of(w, q["id"])) == 2
    with pytest.raises(answers.ServiceError) as e:
        answers.answer(w.ctx, q["id"], option_id="b", actor="user", via="ui")
    assert (e.value.code, e.value.hint) == ("conflict", "already_answered")
    with pytest.raises(answers.ServiceError) as e:
        answers.answer(w.ctx, q["id"], free_text="no", actor="user", via="ui")
    assert e.value.hint == "already_answered"


def test_skip_and_the_interview_becomes_done_when_nothing_is_open(debrief):
    w, interview_id, qs = debrief
    ids = [q["id"] for q in qs.values()]
    answers.answer(w.ctx, ids[0], option_id="a", actor="user", via="ui")
    for qid in ids[1:]:
        answers.skip(w.ctx, qid)
    iv = w.row("interviews", interview_id)
    assert iv["status"] == "done" and iv["finished_at"] is not None
    with pytest.raises(answers.ServiceError) as e:
        answers.answer(w.ctx, ids[1], option_id="a", actor="user", via="ui")
    assert e.value.hint == "question_skipped"
    with pytest.raises(answers.ServiceError) as e:
        answers.skip(w.ctx, ids[0])
    assert e.value.hint == "already_answered"
    assert answers.skip(w.ctx, ids[1]) == interview_id


def test_apply_all_applies_each_rule_in_branch_order_and_repeats_move_nothing(debrief):
    w, _, qs = debrief
    q = qs["AGIPI"]
    out = answers.answer(w.ctx, q["id"], option_id="a", actor="user", via="ui")
    results = answers.apply_all(w.ctx, q["id"], actor="user", via="ui")
    assert [r.rule_id for r in results] == out.rule_ids
    assert [r.moved for r in results] == [1, 2]
    assert all(w.row("rules", r)["state"] == "active" for r in out.rule_ids)
    again = answers.apply_all(w.ctx, q["id"], actor="user", via="ui")
    assert [(r.moved, r.group_id) for r in again] == [(0, None), (0, None)]


def test_apply_all_needs_a_rule_to_apply(debrief):
    w, _, qs = debrief
    q = qs["Hello"]
    answers.answer(w.ctx, q["id"], option_id=option(q, "ask"), actor="user", via="ui")
    with pytest.raises(answers.ServiceError) as e:
        answers.apply_all(w.ctx, q["id"], actor="user", via="ui")
    assert e.value.hint == "nothing_to_apply"


# --- test 9 [M]: undoing an Apply disables the rule again ---


@pytest.fixture
def applied(debrief):
    w, _, qs = debrief
    q = qs["Hello"]
    answers.answer(w.ctx, q["id"], option_id="a", actor="user", via="ui")
    [result] = answers.apply_all(w.ctx, q["id"], actor="user", via="ui")
    assert result.moved == 3 and result.group_id
    return w, result.rule_id, result.group_id


def locations(w: World) -> set[str]:
    return {
        w.row("documents", w.tags[t])["location"] for t in ("hello-jan", "hello-feb", "hello-mar")
    }


def test_group_undo_reverts_the_rule_to_draft_and_redo_reactivates_it(applied):
    w, rule_id, g = applied
    first = undo(w.ctx, actor="user", via="ui", group_id=g)
    assert locations(w) == {"inbox"} and w.row("rules", rule_id)["state"] == "draft"
    assert first.rule_states == [{"rule_id": rule_id, "state": "draft"}]
    [change] = [e for e in entries(w, "rule.change", rule_id) if e["group_id"] == first.group_id]
    assert (change["before"]["state"], change["after"]["state"]) == ("active", "draft")
    redo = undo(w.ctx, actor="user", via="ui", group_id=first.group_id)
    assert locations(w) == {"archive"} and w.row("rules", rule_id)["state"] == "active"
    assert redo.rule_states == [{"rule_id": rule_id, "state": "active"}]
    again = undo(w.ctx, actor="user", via="ui", group_id=g)
    assert locations(w) == {"inbox"} and w.row("rules", rule_id)["state"] == "draft"
    assert again.rule_states == [{"rule_id": rule_id, "state": "draft"}]


def test_undoing_the_redo_group_also_reverts_the_rule(applied):
    w, rule_id, g = applied
    first = undo(w.ctx, actor="user", via="ui", group_id=g)
    redo = undo(w.ctx, actor="user", via="ui", group_id=first.group_id)
    undo(w.ctx, actor="user", via="ui", group_id=redo.group_id)
    assert locations(w) == {"inbox"} and w.row("rules", rule_id)["state"] == "draft"


def test_a_rule_changed_since_is_left_alone(applied):
    w, rule_id, g = applied
    with w.engine.begin() as conn:
        store.set_state(conn, rule_id, "disabled", actor="user", via="ui", at=w.clock())
        store.set_state(conn, rule_id, "active", actor="user", via="ui", at=w.clock())
    out = undo(w.ctx, actor="user", via="ui", group_id=g)
    assert locations(w) == {"inbox"} and out.rule_states == []
    assert w.row("rules", rule_id)["state"] == "active"


def test_a_single_entry_undo_never_changes_the_rule(applied):
    w, rule_id, g = applied
    f = T["file_ops"]
    with w.engine.connect() as conn:
        entry = conn.execute(
            select(f.c.id).where(f.c.group_id == g, f.c.action == "file").limit(1)
        ).scalar_one()
    undo(w.ctx, actor="user", via="ui", journal_id=entry)
    assert w.row("rules", rule_id)["state"] == "active"
