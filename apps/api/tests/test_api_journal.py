"""C2 §9 journal over HTTP: activity, group and entry reads, undo and redo, and the §14 notes."""

import psycopg
import pytest

from mona.api import cardnotes
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


def corrected(w, **kw) -> tuple[str, str, int]:
    """A review document the person filed with a correction: (document, group, file entry)."""
    doc = w.doc(counterparty="opco", **kw)
    c = correct_document(
        w.ctx, doc, actor="user", via="ui", entity="cabinet", category="payment_calls"
    )
    [(entry,)] = sql(
        "SELECT id FROM file_ops WHERE group_id = %s AND action = 'file'", (c.group_id,)
    )
    return doc, c.group_id, entry


def notes(cnv: str) -> list:
    return sql("SELECT kind, text FROM card_action_notes WHERE conversation_id = %s", (cnv,))


async def test_activity_lists_groups_and_ungrouped_entries_newest_first(l2_world, app):
    w = l2_world
    doc, group, _ = corrected(w)
    other = w.doc()
    w.ctx.ops.delete(other, actor="user", via="ui")
    async with api_client(app) as cl:
        page = (await cl.get("/api/activity")).json()
        mine = (await cl.get("/api/activity", params={"actor": "user"})).json()
        monas = (await cl.get("/api/activity", params={"actor": "mona"})).json()
        deletes = (await cl.get("/api/activity", params={"kind": "delete"})).json()
        found = (await cl.get("/api/activity", params={"q": doc[-10:]})).json()
    kinds = [(i["kind"], i.get("group", {}).get("id")) for i in page["items"]]
    assert kinds[0] == ("entry", None) and kinds[1] == ("group", group)
    item = page["items"][1]
    assert item["entriesTotal"] == len(item["preview"]) >= 1
    assert item["redoGroupId"] is None and item["group"]["kind"] == "correction"
    assert page["documents"][doc]["deleted"] is False
    assert page["documents"][other]["deleted"] is True
    assert page["nextCursor"] is None
    assert len(mine["items"]) == 2 and monas["items"] == []
    assert [i["entry"]["action"] for i in deletes["items"]] == ["delete"]
    assert [i["group"]["id"] for i in found["items"]] == [group]


async def test_activity_pages_by_cursor_and_refuses_a_foreign_cursor(l2_world, app):
    w = l2_world
    groups = [corrected(w)[1] for _ in range(3)]
    async with api_client(app) as cl:
        first = (await cl.get("/api/activity", params={"limit": 2})).json()
        second = (
            await cl.get("/api/activity", params={"limit": 2, "cursor": first["nextCursor"]})
        ).json()
        foreign = await cl.get(
            "/api/activity", params={"limit": 2, "actor": "user", "cursor": first["nextCursor"]}
        )
    seen = [i["group"]["id"] for i in first["items"] + second["items"]]
    assert seen == groups[::-1] and second["nextCursor"] is None
    assert foreign.status_code == 400 and foreign.json()["error"]["field"] == "cursor"


async def test_group_and_entry_reads(l2_world, app):
    w = l2_world
    doc, group, entry = corrected(w)
    async with api_client(app) as cl:
        g = (await cl.get(f"/api/journal/groups/{group}")).json()
        e = (await cl.get(f"/api/journal/{entry}")).json()
        missing = [
            (await cl.get(p)).status_code
            for p in (
                "/api/journal/999999",
                "/api/journal/x1",
                "/api/journal/groups/doc_" + "0" * 26,
            )
        ]
    assert g["group"]["id"] == group and [x["id"] for x in g["entries"]] == sorted(
        x["id"] for x in g["entries"]
    )
    assert entry in [x["id"] for x in g["entries"]] and doc in g["documents"]
    assert e["entry"]["id"] == entry and e["entry"]["documentIds"] == [doc]
    assert missing == [404, 404, 404]


async def test_entry_undo_returns_the_undo_result_and_a_second_undo_is_409(l2_world, app):
    w = l2_world
    doc, _, entry = corrected(w)
    async with api_client(app) as cl:
        res = await cl.post(f"/api/journal/{entry}/undo")
        before = sql("SELECT count(*) FROM file_ops")
        again = await cl.post(f"/api/journal/{entry}/undo")
    body = res.json()
    assert res.status_code == 200 and body["groupId"] is None and body["skipped"] == []
    [undone] = body["undone"]
    assert undone["journalId"] == entry and undone["documentId"] == doc
    assert undone["to"]["location"] == "inbox" and undone["to"]["status"] == "review"
    [new] = body["entries"]
    assert (new["action"], new["actor"], new["via"], new["undoOf"]) == ("undo", "user", "ui", entry)
    assert w.row(doc)["location"] == "inbox"
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_undone"
    assert sql("SELECT count(*) FROM file_ops") == before


async def test_a_superseded_entry_is_409_with_nothing_changed(l2_world, app):
    w = l2_world
    doc, _, entry = corrected(w)
    correct_document(w.ctx, doc, actor="user", via="ui", category="insurance")
    path = w.row(doc)["current_path"]
    before = sql("SELECT count(*) FROM file_ops")
    async with api_client(app) as cl:
        res = await cl.post(f"/api/journal/{entry}/undo")
    assert res.status_code == 409 and res.json()["error"]["code"] == "superseded"
    assert sql("SELECT count(*) FROM file_ops") == before and w.row(doc)["current_path"] == path


async def test_group_undo_then_redo_through_redo_group_id(l2_world, app):
    w = l2_world
    doc, group, _ = corrected(w)
    filed_path = w.row(doc)["current_path"]
    async with api_client(app) as cl:
        undo = (await cl.post(f"/api/journal/groups/{group}/undo", json={})).json()
        listed = (await cl.get("/api/activity")).json()
        redo_id = next(i for i in listed["items"] if i.get("group", {}).get("id") == group)[
            "redoGroupId"
        ]
        redo = await cl.post(f"/api/journal/groups/{redo_id}/undo")
        nothing = await cl.post(f"/api/journal/groups/{redo_id}/undo")
    assert undo["groupId"] == redo_id and len(undo["undone"]) >= 1
    assert all(e["action"] == "undo" for e in undo["entries"])
    assert w.row(doc)["current_path"] == filed_path and redo.status_code == 200
    assert {e["action"] for e in redo.json()["entries"]} == {"redo"}
    [(kind, actor, via)] = sql(
        "SELECT kind, actor, via FROM op_groups WHERE id = %s", (redo.json()["groupId"],)
    )
    assert (kind, actor, via) == ("redo", "user", "ui")
    assert nothing.status_code == 409 and nothing.json()["error"]["code"] == "already_undone"


async def test_undo_from_a_card_writes_one_undo_note(l2_world, app):
    w = l2_world
    cnv, _ = rows.turn(status="closed")
    doc, _, entry = corrected(w)
    _, group, _ = corrected(w)
    _, quiet, _ = corrected(w)
    async with api_client(app) as cl:
        await cl.post(f"/api/journal/{entry}/undo", json={"conversationId": cnv})
        await cl.post(f"/api/journal/groups/{group}/undo", json={"conversationId": cnv})
        await cl.post(f"/api/journal/groups/{quiet}/undo")
        unknown = await cl.post(
            f"/api/journal/{entry}/undo", json={"conversationId": "cnv_" + "0" * 26}
        )
    title = w.row(doc)["original_name"]
    assert notes(cnv) == [
        ("undo", f"Undid 1 change(s): {title} back to the Inbox."),
        ("undo", "Undid 1 change(s): a correction."),
    ]
    assert unknown.status_code == 409
    assert sql("SELECT count(*) FROM card_action_notes") == [(2,)]


async def test_a_failure_after_the_undo_note_rolls_back_the_note_and_the_undo(
    l2_world, app, monkeypatch
):
    """C2 §17 item 11 [M]: the single-entry undo writes its note in the effect's transaction."""
    w = l2_world
    cnv, _ = rows.turn(status="closed")
    doc, _, entry = corrected(w)
    real = cardnotes.write

    def write_then_fail(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("after the note")

    monkeypatch.setattr(cardnotes, "write", write_then_fail)
    async with api_client(app) as cl:
        res = await cl.post(f"/api/journal/{entry}/undo", json={"conversationId": cnv})
    assert res.status_code == 500 and res.json()["error"]["code"] == "internal"
    assert notes(cnv) == []
    assert w.row(doc)["location"] == "archive"
    assert sql("SELECT undone_by FROM file_ops WHERE id = %s", (entry,)) == [(None,)]
