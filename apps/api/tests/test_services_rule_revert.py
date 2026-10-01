"""C6 §7.3 / §10 test 9: undoing an Apply returns the rule to draft; redo re-activates it."""

from datetime import date

import pytest
from sqlalchemy import select, update

from mona.rules import store
from mona.services import apply_rule, undo
from mona.services.registry import T
from tests.services_world import Services


@pytest.fixture
def s(seeded_engine, tmp_path) -> Services:
    return Services(seeded_engine, tmp_path / "data")


def draft_opco(s: Services) -> tuple[str, list[str]]:
    rid = s.rule_id("opco-cabinet")
    with s.engine.begin() as conn:
        conn.execute(update(T["rules"]).where(T["rules"].c.id == rid).values(state="draft"))
    docs = [
        s.doc(counterparty="opco", category="payment_calls", subcategory="contribution_opco",
              entity="cabinet", doc_date=date(2026, 2, 27), period_end=date(2025, 12, 31),
              reference=f"R-{i}")
        for i in range(2)
    ]  # fmt: skip
    return rid, docs


def state(s: Services, rid: str) -> str:
    with s.engine.connect() as conn:
        return conn.execute(select(T["rules"].c.state).where(T["rules"].c.id == rid)).scalar_one()


def changes(s: Services, group_id: str) -> list[tuple[str, str, str, str]]:
    f = T["file_ops"]
    with s.engine.connect() as conn:
        rows = conn.execute(
            select(f).where(f.c.group_id == group_id, f.c.action == "rule.change").order_by(f.c.id)
        ).mappings()
        return [(r["before"]["state"], r["after"]["state"], r["actor"], r["via"]) for r in rows]


def locations(s: Services, docs: list[str]) -> list[str]:
    return [s.row(d)["location"] for d in docs]


def test_undo_of_an_apply_drafts_the_rule_and_redo_activates_it(s):
    rid, docs = draft_opco(s)
    g = apply_rule(s.ctx, rid, actor="mona", via="chat").group_id
    assert state(s, rid) == "active" and locations(s, docs) == ["archive"] * 2

    u = undo(s.ctx, actor="user", via="ui", group_id=g)
    assert locations(s, docs) == ["inbox"] * 2
    assert state(s, rid) == "draft"
    assert u.rule_states == [{"rule_id": rid, "state": "draft"}]
    assert changes(s, u.group_id) == [("active", "draft", "user", "ui")]
    assert "draft" in (s.ctx.config_dir / "rules.yaml").read_text()

    r = undo(s.ctx, actor="mona", via="chat", group_id=u.group_id)
    assert locations(s, docs) == ["archive"] * 2
    assert state(s, rid) == "active"
    assert r.rule_states == [{"rule_id": rid, "state": "active"}]
    assert changes(s, r.group_id) == [("draft", "active", "mona", "chat")]

    again = undo(s.ctx, actor="user", via="ui", group_id=g)
    assert locations(s, docs) == ["inbox"] * 2 and state(s, rid) == "draft"
    assert again.rule_states == [{"rule_id": rid, "state": "draft"}]


def test_undo_through_the_redo_group_drafts_it_too(s):
    rid, docs = draft_opco(s)
    g = apply_rule(s.ctx, rid, actor="mona", via="chat").group_id
    u = undo(s.ctx, actor="user", via="ui", group_id=g)
    r = undo(s.ctx, actor="user", via="ui", group_id=u.group_id)
    last = undo(s.ctx, actor="user", via="ui", group_id=r.group_id)
    assert locations(s, docs) == ["inbox"] * 2 and state(s, rid) == "draft"
    assert last.rule_states == [{"rule_id": rid, "state": "draft"}]


def test_a_rule_changed_since_is_left_alone(s):
    rid, docs = draft_opco(s)
    g = apply_rule(s.ctx, rid, actor="mona", via="chat").group_id
    with s.engine.begin() as conn:
        store.set_state(conn, rid, "disabled", actor="user", via="ui", at=s.clock())
    u = undo(s.ctx, actor="user", via="ui", group_id=g)
    assert locations(s, docs) == ["inbox"] * 2
    assert state(s, rid) == "disabled" and u.rule_states == [] and changes(s, u.group_id) == []


def test_a_single_entry_undo_never_changes_the_rule(s):
    rid, docs = draft_opco(s)
    g = apply_rule(s.ctx, rid, actor="mona", via="chat").group_id
    f = T["file_ops"]
    with s.engine.connect() as conn:
        entries = conn.execute(
            select(f.c.id).where(f.c.group_id == g, f.c.action == "file")
        ).scalars()
        entries = list(entries)
    for e in entries:
        undo(s.ctx, actor="user", via="ui", journal_id=e)
    assert locations(s, docs) == ["inbox"] * 2 and state(s, rid) == "active"


def test_an_apply_of_a_disabled_rule_returns_it_to_disabled(s):
    rid = s.rule_id("unim-business")
    s.doc(counterparty="unim", category="insurance", subcategory="prevoyance",
          entity="cabinet", amount=120, doc_date=date(2025, 11, 3))  # fmt: skip
    g = apply_rule(s.ctx, rid, actor="mona", via="chat").group_id
    undo(s.ctx, actor="user", via="ui", group_id=g)
    assert state(s, rid) == "disabled"


def test_an_apply_that_activated_nothing_leaves_the_rule(s):
    rid, docs = draft_opco(s)
    with s.engine.begin() as conn:
        conn.execute(update(T["rules"]).where(T["rules"].c.id == rid).values(state="active"))
    g = apply_rule(s.ctx, rid, actor="mona", via="chat").group_id
    u = undo(s.ctx, actor="user", via="ui", group_id=g)
    assert state(s, rid) == "active" and u.rule_states == []
