"""The write tools over MCP (C4 §3.5, §3.8, §3.9, §3.16; §5 items 4, 6–10)."""

import json
import socket
from datetime import date
from typing import Literal

import psycopg
from pydantic import Field

from mona.chat.cards import card_chunk
from mona.db import get_engine
from mona.services import correct_document
from mona.settings import get_settings
from tests import rows
from tests.mcp_http import call
from tests.mcp_results import CardRef, Strict

DOC = Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")


class Move(Strict):
    document_id: str = DOC
    title: str
    from_: str = Field(alias="from")
    to: str


class Preview(Strict):
    rule_id: str
    name: str
    state: Literal["draft", "active", "disabled"]
    condition_text: str
    moves_total: int
    stays_total: int
    moves: list[Move] = Field(max_length=5)


class PreviewResult(Preview):
    card_refs: list[CardRef]


class RuleState(Strict):
    id: str
    state: Literal["draft", "active", "disabled"]


class CorrectResult(Strict):
    document_id: str = DOC
    outcome: Literal["moved", "unchanged"]
    path: str
    journal_ids: list[int]
    group_id: str | None
    rule: RuleState | None
    preview: Preview | None
    card_refs: list[CardRef]


class Failed(Strict):
    document_id: str = DOC
    code: str


class ApplyResult(Strict):
    rule_id: str
    group_id: str | None
    moved: int
    unchanged: int
    failed: list[Failed]
    card_refs: list[CardRef]


class UndoneItem(Strict):
    journal_id: int
    document_id: str = DOC
    title: str
    to: str | None


class SkippedItem(Strict):
    journal_id: int
    state: Literal["superseded", "already_undone", "not_undoable", "not_allowed"]


class UndoResult(Strict):
    group_id: str | None
    undone: list[UndoneItem]
    skipped: list[SkippedItem]


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


def ok(res, model):
    assert not res.is_error, res.text
    assert len(res.text) <= 4000
    model.model_validate(res.data)
    return res.data


def error(res) -> dict:
    assert res.is_error, res.text
    return res.data["error"]


def opco_docs(w, n: int = 2) -> list[str]:
    return [w.doc(counterparty="opco", doc_date=date(2025, 1, 1 + i)) for i in range(n)]


# --- correct_document ---


async def test_correct_one_refiles_as_mona_with_a_doc_card(l2_world):
    w = l2_world
    doc = w.doc(counterparty="opco", doc_date=date(2026, 2, 27))
    res = await call(
        "correct_document", {"document_id": doc, "entity": "Cabinet Marchand",
                             "category": "Appels de paiement"},
    )  # fmt: skip
    body = ok(res, CorrectResult)
    assert body["outcome"] == "moved" and body["rule"] is None and body["preview"] is None
    assert body["path"] == w.row(doc)["current_path"] and body["path"].startswith("Cabinet")
    [(kind, actor, via)] = sql(
        "SELECT kind, actor, via FROM op_groups WHERE id = %s", (body["group_id"],)
    )
    assert (kind, actor, via) == ("correction", "mona", "chat")
    assert {a for (a,) in sql("SELECT DISTINCT actor FROM file_ops")} == {"mona"}
    [card] = rows.card_rows()
    assert (card.tool, card.kind, card.subject, card.channel) == (
        "correct_document", "doc", {"document_id": doc}, "web",
    )  # fmt: skip
    again = ok(
        await call("correct_document", {"document_id": doc, "entity": "cabinet",
                                        "category": "payment_calls"}),
        CorrectResult,
    )  # fmt: skip
    assert again["outcome"] == "unchanged" and again["journal_ids"] == []


async def test_correct_all_drafts_a_rule_with_its_preview_card(l2_world):
    w = l2_world
    docs = opco_docs(w)
    args = {"document_id": docs[0], "entity": "studio", "category": "payment_calls",
            "scope": "all"}  # fmt: skip
    body = ok(await call("correct_document", args), CorrectResult)
    assert body["rule"]["state"] == "draft"
    assert body["preview"]["moves_total"] == 1 and body["preview"]["stays_total"] == 1
    assert body["preview"]["moves"][0]["document_id"] == docs[1]
    [card] = rows.card_rows()
    assert (card.kind, card.subject) == ("rulePreview", {"rule_id": body["rule"]["id"]})
    again = ok(await call("correct_document", args), CorrectResult)
    assert again["rule"]["id"] == body["rule"]["id"]


async def test_correct_refusals(l2_world):
    w = l2_world
    doc = w.doc(counterparty="opco")
    personal = w.doc(counterparty="oxyleo", entity="personal")
    visitors = error(await call("correct_document", {"document_id": doc, "entity": "visitors"}))
    unknown = error(await call("correct_document", {"document_id": doc, "entity": "Nowhere SA"}))
    nothing = error(await call("correct_document", {"document_id": doc}))
    no_currency = error(await call("correct_document", {"document_id": doc, "amount": 12.5}))
    reading = w.doc(counterparty="opco", status="processing")
    processing = error(await call("correct_document", {"document_id": reading, "entity": "cabinet",
                                                       "category": "payment_calls"}))  # fmt: skip
    hidden = error(
        await call("correct_document", {"document_id": personal, "category": "tax"},
                   channel="telegram")
    )  # fmt: skip
    no_scope = error(
        await call("correct_document", {"document_id": w.doc(), "entity": "cabinet",
                                        "category": "payment_calls", "scope": "all"})
    )  # fmt: skip
    assert visitors["code"] == "not_allowed"
    assert unknown["code"] == "invalid_argument" and unknown["field"] == "entity"
    assert "visitors" not in [v["key"] for v in unknown["valid"]]
    assert nothing["code"] == "invalid_argument"
    assert no_currency["code"] == "invalid_argument" and no_currency["field"] == "currency"
    assert (processing["code"], processing["hint"]) == ("conflict", "processing")
    assert hidden["code"] == "not_found"
    assert no_scope["code"] == "invalid_argument" and no_scope["field"] == "scope"
    assert sql("SELECT count(*) FROM file_ops WHERE action <> 'doc.update'") == [(0,)]


async def test_correct_on_telegram_journals_via_telegram(l2_world):
    w = l2_world
    doc = w.doc(counterparty="opco", entity="cabinet")
    body = ok(
        await call("correct_document", {"document_id": doc, "entity": "cabinet",
                                        "category": "payment_calls"}, channel="telegram"),
        CorrectResult,
    )  # fmt: skip
    assert sql("SELECT via FROM op_groups WHERE id = %s", (body["group_id"],)) == [("telegram",)]
    assert rows.card_rows()[0].channel == "telegram"


# --- preview_rule and apply_rule ---


def draft(w) -> tuple[str, list[str]]:
    docs = opco_docs(w)
    c = correct_document(
        w.ctx, docs[0], actor="user", via="ui", entity="studio", category="payment_calls",
        scope="all",
    )  # fmt: skip
    return c.rule.id, docs


async def rule_card(rule_id: str) -> dict:
    async with get_engine().connect() as conn:
        chunk = await card_chunk(conn, "rulePreview", {"rule_id": rule_id})
    assert chunk["type"] == "data-rulePreview" and chunk["id"] == rule_id
    return chunk["data"]


async def test_preview_then_apply_keep_the_counts_on_the_card(l2_world):
    w = l2_world
    rule_id, docs = draft(w)
    preview = ok(await call("preview_rule", {"rule_id": rule_id}), PreviewResult)
    before = await rule_card(rule_id)
    applied = ok(await call("apply_rule", {"rule_id": rule_id}), ApplyResult)
    after = await rule_card(rule_id)
    second = ok(await call("apply_rule", {"rule_id": rule_id}), ApplyResult)
    assert (preview["moves_total"], preview["stays_total"], preview["state"]) == (1, 1, "draft")
    assert (applied["moved"], applied["unchanged"], applied["failed"]) == (1, 1, [])
    assert (second["moved"], second["group_id"]) == (0, None)
    assert (before["movesTotal"], before["staysTotal"]) == (
        after["movesTotal"],
        after["staysTotal"],
    )
    assert after["applied"] is True and before["applied"] is False
    [(kind, actor, via)] = sql(
        "SELECT kind, actor, via FROM op_groups WHERE id = %s", (applied["group_id"],)
    )
    assert (kind, actor, via) == ("rule_apply", "mona", "chat")
    cards = rows.card_rows()
    assert [(c.tool, c.kind) for c in cards] == [
        ("preview_rule", "rulePreview"), ("apply_rule", "rulePreview"),
        ("apply_rule", "rulePreview"),
    ]  # fmt: skip
    assert {json.dumps(c.subject) for c in cards} == {json.dumps({"rule_id": rule_id})}


async def test_a_personal_rule_is_not_found_on_telegram(l2_world):
    w = l2_world
    oxyleo = w.rule_id("oxyleo-personal-tax")
    hidden = error(await call("preview_rule", {"rule_id": oxyleo}, channel="telegram"))
    applied = error(await call("apply_rule", {"rule_id": oxyleo}, channel="telegram"))
    shown = await call("preview_rule", {"rule_id": oxyleo})
    missing = error(await call("preview_rule", {"rule_id": "rul_" + "0" * 26}))
    assert hidden["code"] == applied["code"] == missing["code"] == "not_found"
    assert not shown.is_error


# --- undo ---


async def test_undo_an_entry_then_its_undo_is_skipped(l2_world):
    w = l2_world
    doc = w.doc(counterparty="opco")
    fixed = ok(
        await call("correct_document", {"document_id": doc, "entity": "cabinet",
                                        "category": "payment_calls"}),
        CorrectResult,
    )  # fmt: skip
    [entry] = [
        i for (i,) in sql(
            "SELECT id FROM file_ops WHERE group_id = %s AND action = 'file'", (fixed["group_id"],)
        )
    ]  # fmt: skip
    body = ok(await call("undo", {"journal_id": entry}), UndoResult)
    assert [u["journal_id"] for u in body["undone"]] == [entry] and body["group_id"] is None
    assert body["undone"][0]["to"] == w.row(doc)["current_path"]
    assert sql("SELECT actor, via FROM file_ops WHERE undo_of = %s", (entry,)) == [("mona", "chat")]
    again = ok(await call("undo", {"journal_id": entry}), UndoResult)
    assert again["undone"] == [] and again["skipped"] == [
        {"journal_id": entry, "state": "already_undone"}
    ]


async def test_undo_a_group_and_redo_it(l2_world):
    w = l2_world
    rule_id, docs = draft(w)
    applied = ok(await call("apply_rule", {"rule_id": rule_id}), ApplyResult)
    undone = ok(await call("undo", {"group_id": applied["group_id"]}), UndoResult)
    redone = ok(await call("undo", {"group_id": undone["group_id"]}), UndoResult)
    assert len(undone["undone"]) == 1 and len(redone["undone"]) == 1
    assert sql("SELECT kind FROM op_groups WHERE id = %s", (redone["group_id"],)) == [("redo",)]
    assert w.row(docs[1])["status"] == "filed"


async def test_undo_arguments_and_visibility(l2_world):
    w = l2_world
    personal = w.doc(counterparty="oxyleo")
    c = correct_document(w.ctx, personal, actor="user", via="ui", entity="personal", category="tax")
    [(entry,)] = sql("SELECT id FROM file_ops WHERE group_id = %s AND action = 'file'",
                     (c.group_id,))  # fmt: skip
    neither = error(await call("undo", {}))
    both = error(await call("undo", {"journal_id": entry, "group_id": c.group_id}))
    entry_tg = error(await call("undo", {"journal_id": entry}, channel="telegram"))
    group_tg = error(await call("undo", {"group_id": c.group_id}, channel="telegram"))
    unknown = error(await call("undo", {"journal_id": 999999}))
    assert neither["code"] == both["code"] == "invalid_argument"
    assert entry_tg["code"] == group_tg["code"] == unknown["code"] == "not_found"
    assert w.row(personal)["location"] == "archive"
    assert not (await call("undo", {"journal_id": entry})).is_error


async def test_mona_never_moves_a_document_to_the_trash(l2_world):
    """C4 §5.10: undoing the person's restore would trash the document; Mona is refused."""
    w = l2_world
    doc = w.doc()
    deleted = w.ctx.ops.delete(doc, actor="user", via="ui").entry_id
    restore = w.ctx.ops.undo(deleted, actor="user", via="ui").entry_id
    res = error(await call("undo", {"journal_id": restore}))
    assert res["code"] == "not_allowed"
    assert sql("SELECT count(*) FROM file_ops WHERE actor = 'mona'") == [(0,)]
    assert w.row(doc)["location"] == "inbox"


# --- schemas, egress, delete ---


async def test_write_schemas_reject_unknown_keys_and_wrong_prefixes(l2_world):
    for name, args in [
        ("correct_document", {"document_id": "rul_" + "0" * 26, "entity": "x"}),
        ("correct_document", {"document_id": "doc_" + "0" * 26, "colour": "red"}),
        ("correct_document", {"document_id": "doc_" + "0" * 26, "scope": "some"}),
        ("preview_rule", {"rule_id": "doc_" + "0" * 26}),
        ("apply_rule", {"rule_id": "rul_x"}),
        ("undo", {"journal_id": 0}),
        ("undo", {"group_id": "bat_" + "0" * 26}),
    ]:
        assert error(await call(name, args))["code"] == "invalid_argument", (name, args)


async def test_write_tools_open_no_socket_and_delete_nothing(l2_world, monkeypatch):
    w = l2_world
    rule_id, docs = draft(w)
    other = w.doc(counterparty="unim")
    real = socket.socket.connect
    pg_port = int(get_settings().libpq_url.rsplit(":", 1)[1].split("/")[0])

    def only_postgres(self, address):
        if not (isinstance(address, tuple) and address[1] == pg_port):
            raise AssertionError(f"socket connect to {address}")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", only_postgres)
    calls = [
        ("correct_document", {"document_id": other, "entity": "cabinet", "category": "insurance"}),
        ("preview_rule", {"rule_id": rule_id}),
        ("apply_rule", {"rule_id": rule_id}),
    ]
    for name, args in calls:
        res = await call(name, args)
        assert not res.is_error, (name, res.text)
    [(group,)] = sql("SELECT id FROM op_groups WHERE kind = 'rule_apply'")
    assert not (await call("undo", {"group_id": group})).is_error
    assert sql(
        "SELECT count(*) FROM file_ops WHERE action = 'delete'"
        " OR after->>'location' = 'trash'"
    ) == [(0,)]  # fmt: skip
