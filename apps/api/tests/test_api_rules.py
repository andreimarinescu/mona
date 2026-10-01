"""C2 §7 rules over HTTP, and the `rule.apply` note (§14)."""

from datetime import date

import psycopg
import pytest

from mona.app import create_app
from mona.services import correct_document
from mona.settings import get_settings
from tests import rows
from tests.api_client import api_client


@pytest.fixture
def app(l2_world):
    return create_app()


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


def draft_rule(w) -> tuple[str, list[str]]:
    """A draft `counterparty equals opco` rule for studio, and two OPCO documents it would move."""
    docs = [w.doc(counterparty="opco", doc_date=date(2025, 1, 1 + i)) for i in range(2)]
    c = correct_document(
        w.ctx, docs[0], actor="user", via="ui", entity="studio", category="payment_calls",
        scope="all",
    )  # fmt: skip
    return c.rule.id, docs


async def test_list_orders_by_state_then_priority_and_filters(l2_world, app):
    w = l2_world
    rule_id, _ = draft_rule(w)
    ents = w.ids("entities")
    async with api_client(app) as cl:
        page = (await cl.get("/api/rules")).json()
        drafts = (await cl.get("/api/rules", params={"state": "draft"})).json()
        studio = (await cl.get("/api/rules", params={"entityId": ents["studio"]})).json()
        named = (await cl.get("/api/rules", params={"q": "opco"})).json()
        one = (await cl.get(f"/api/rules/{rule_id}")).json()
        bad = await cl.get("/api/rules/doc_" + "0" * 26)
    states = [i["rule"]["state"] for i in page["items"]]
    assert states == sorted(states, key=["active", "draft", "disabled"].index)
    active = [i["rule"]["priority"] for i in page["items"] if i["rule"]["state"] == "active"]
    assert active == sorted(active, reverse=True)
    assert page["total"] == 7 and all(i["valid"] for i in page["items"])
    assert [i["rule"]["id"] for i in drafts["items"]] == [rule_id]
    assert rule_id in [i["rule"]["id"] for i in studio["items"]]
    assert {i["rule"]["action"]["entity"] for i in studio["items"]} == {"studio"}
    assert rule_id in [i["rule"]["id"] for i in named["items"]]
    assert one["rule"]["id"] == rule_id and one["problems"] == []
    assert bad.status_code == 404


async def test_patch_enables_without_bumping_the_version_and_journals_once(l2_world, app):
    w = l2_world
    rule_id, _ = draft_rule(w)
    async with api_client(app) as cl:
        res = await cl.patch(
            f"/api/rules/{rule_id}", json={"enabled": True, "name": "OPCO → Studio"}
        )
        body = res.json()
        again = await cl.patch(f"/api/rules/{rule_id}", json={"enabled": True})
        bumped = await cl.patch(f"/api/rules/{rule_id}", json={"priority": 99})
    assert res.status_code == 200 and body["rule"]["state"] == "active"
    assert body["rule"]["enabled"] and body["rule"]["name"] == "OPCO → Studio"
    assert body["rule"]["version"] == 1
    assert again.json()["rule"]["version"] == 1 and bumped.json()["rule"]["version"] == 2
    changes = sql(
        "SELECT actor, via FROM file_ops WHERE action = 'rule.change' AND subject_id = %s",
        (rule_id,),
    )
    assert changes == [("user", "ui"), ("user", "ui")]
    assert (w.ctx.config_dir / "rules.yaml").exists()


async def test_patch_with_an_invalid_rule_is_422_and_writes_nothing(l2_world, app):
    w = l2_world
    rule_id, _ = draft_rule(w)
    before = sql("SELECT version, conditions, name FROM rules WHERE id = %s", (rule_id,))
    entries = sql("SELECT count(*) FROM file_ops")
    async with api_client(app) as cl:
        unknown = await cl.patch(
            f"/api/rules/{rule_id}",
            json={
                "name": "x",
                "conditions": [{"field": "entity", "op": "equals", "value": "nope"}],
            },
        )
        malformed = await cl.patch(
            f"/api/rules/{rule_id}", json={"conditions": [{"field": "colour", "op": "is"}]}
        )
        visitors = await cl.patch(f"/api/rules/{rule_id}", json={"action": {"entity": "visitors"}})
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "invalid_rule"
    assert unknown.json()["error"]["field"] == "conditions.0"
    assert "unknown entity" in unknown.json()["error"]["details"]["message"]
    assert malformed.status_code == 422 and malformed.json()["error"]["field"].startswith(
        "conditions.0"
    )
    assert visitors.status_code == 422 and visitors.json()["error"]["field"] == "action.entity"
    assert sql("SELECT version, conditions, name FROM rules WHERE id = %s", (rule_id,)) == before
    assert sql("SELECT count(*) FROM file_ops") == entries


async def test_preview_caps_moves_and_apply_is_idempotent_with_the_same_counts(l2_world, app):
    w = l2_world
    rule_id, docs = draft_rule(w)
    async with api_client(app) as cl:
        full = (await cl.get(f"/api/rules/{rule_id}/preview")).json()
        capped = (await cl.get(f"/api/rules/{rule_id}/preview", params={"limit": 1})).json()
        first = (await cl.post(f"/api/rules/{rule_id}/apply", json={})).json()
        second = (await cl.post(f"/api/rules/{rule_id}/apply")).json()
        after = (await cl.get(f"/api/rules/{rule_id}/preview")).json()
    assert (full["movesTotal"], full["staysTotal"], full["applied"]) == (1, 1, False)
    assert len(capped["moves"]) == 1 and capped["movesTotal"] == 1
    assert first["moved"] == 1 and first["groupId"] and first["preview"]["applied"]
    assert (second["moved"], second["groupId"]) == (0, None)
    assert (after["movesTotal"], after["staysTotal"]) == (1, 1) and after["applied"]
    [(kind, actor, via)] = sql(
        "SELECT kind, actor, via FROM op_groups WHERE id = %s", (first["groupId"],)
    )
    assert (kind, actor, via) == ("rule_apply", "user", "ui")
    [(state,)] = sql("SELECT state FROM rules WHERE id = %s", (rule_id,))
    assert state == "active" and w.row(docs[1])["status"] == "filed"


async def test_apply_from_a_card_writes_one_note_after_the_moves(l2_world, app):
    w = l2_world
    rule_id, _ = draft_rule(w)
    cnv, _ = rows.turn(status="closed")
    async with api_client(app) as cl:
        await cl.post(f"/api/rules/{rule_id}/apply", json={"conversationId": cnv})
        await cl.post(f"/api/rules/{rule_id}/apply", json={"conversationId": "cnv_" + "0" * 26})
        await cl.post(f"/api/rules/{rule_id}/apply")
        bad = await cl.post(f"/api/rules/{rule_id}/apply", json={"conversationId": "x"})
    notes = sql("SELECT kind, text FROM card_action_notes WHERE conversation_id = %s", (cnv,))
    name = sql("SELECT name FROM rules WHERE id = %s", (rule_id,))[0][0]
    assert notes == [
        ("rule.apply", f'Applied the rule "{name}": 1 documents moved, 1 already in place.')
    ]
    assert sql("SELECT count(*) FROM card_action_notes") == [(1,)]
    assert bad.status_code == 400 and bad.json()["error"]["field"] == "conversationId"


async def test_undoing_an_apply_group_reports_the_rule_states(l2_world, app):
    rule_id, _ = draft_rule(l2_world)
    async with api_client(app) as cl:
        group = (await cl.post(f"/api/rules/{rule_id}/apply")).json()["groupId"]
        undo = (await cl.post(f"/api/journal/groups/{group}/undo")).json()
        redo = (await cl.post(f"/api/journal/groups/{undo['groupId']}/undo")).json()
    assert undo["ruleStates"] == [{"ruleId": rule_id, "state": "draft"}]
    assert redo["ruleStates"] == [{"ruleId": rule_id, "state": "active"}]


async def test_learned_lists_recent_interview_and_correction_rules(l2_world, app):
    w = l2_world
    rule_id, _ = draft_rule(w)
    async with api_client(app) as cl:
        await cl.post(f"/api/rules/{rule_id}/apply")
        learned = (await cl.get("/api/rules/learned")).json()
        none = (await cl.get("/api/rules/learned", params={"since": "2100-01-01T00:00:00Z"})).json()
    assert [(x["rule"]["id"], x["moved"]) for x in learned][:1] == [(rule_id, 1)]
    assert none == []
