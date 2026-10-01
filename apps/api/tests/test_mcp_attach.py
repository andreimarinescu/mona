"""`ingest_attachment` over MCP (C4 §3.14): copy, the C2 intake path, cards, refusals."""

import hashlib
import logging
import socket
from typing import Literal

import psycopg
import pytest
from pydantic import Field

from mona.api import intake
from mona.mcp import attach
from mona.services import delete_document
from mona.settings import get_settings
from tests import rows
from tests.mcp_http import call
from tests.mcp_results import CardRef, Strict

PDF = b"%PDF-1.4\n%attachment\n%%EOF\n"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00telegram photo\xff\xd9"
NAME = "doc_0123456789ab_facture eau.pdf"
SHA = hashlib.sha256(PDF).hexdigest()


class IngestResult(Strict):
    batch_id: str = Field(pattern=r"^bat_[0-9a-hjkmnp-tv-z]{26}$")
    outcome: Literal["accepted", "duplicate", "rejected"]
    document_id: str | None = Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
    deleted: bool
    reject_reason: Literal["unsupported_type", "too_large", "empty", "unreadable_file"] | None
    card_refs: list[CardRef]


@pytest.fixture
def cache(l2_world, tmp_path, monkeypatch):
    root = tmp_path / "hermes-cache"
    for sub in ("documents", "images"):
        (root / sub).mkdir(parents=True)
    (root / "documents" / NAME).write_bytes(PDF)
    (root / "images" / "img_0123456789ab.jpg").write_bytes(JPEG)
    monkeypatch.setenv("MONA_ATTACH_ROOT", str(root))
    get_settings.cache_clear()
    intake.get_intake_ctx.cache_clear()
    yield root
    intake.get_intake_ctx.cache_clear()


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


def ok(res) -> dict:
    assert not res.is_error, res.text
    assert len(res.text) <= 4000
    IngestResult.model_validate(res.data)
    return res.data


def error(res) -> dict:
    assert res.is_error, res.text
    return res.data["error"]


async def test_an_attachment_is_copied_into_a_telegram_batch_with_a_doc_card(
    l2_world, cache, caplog
):
    caplog.set_level(logging.INFO, logger="mona.mcp.attach")
    src = cache / "documents" / NAME
    body = ok(await call("ingest_attachment", {"path": str(src)}, channel="telegram"))
    doc = body["document_id"]
    assert (body["outcome"], body["deleted"], body["reject_reason"]) == ("accepted", False, None)
    assert src.read_bytes() == PDF
    assert (l2_world.ctx.ops.roots.inbox / f"{doc}.pdf").read_bytes() == PDF
    assert sql(
        "SELECT source, original_name, status, pipeline_stage, sha256 FROM documents"
        " WHERE id = %s", (doc,),
    ) == [("telegram", "facture eau.pdf", "processing", "queued", SHA)]  # fmt: skip
    assert sql("SELECT source, visitor FROM batches WHERE id = %s", (body["batch_id"],)) == [
        ("telegram", False)
    ]
    assert sql(
        "SELECT kind, actor, via FROM op_groups WHERE batch_id = %s", (body["batch_id"],)
    ) == [("intake_batch", "mona", "pipeline")]
    assert sql(
        "SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'extract_text'"
        " AND args->>'document_id' = %s", (doc,),
    ) == [(1,)]  # fmt: skip
    [card] = rows.card_rows()
    assert (card.tool, card.kind, card.subject, card.channel) == (
        "ingest_attachment", "doc", {"document_id": doc}, "telegram",
    )  # fmt: skip
    assert body["card_refs"] == [card.id]
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert f"documents/{NAME}" in logged and str(cache) not in logged


async def test_relative_image_paths_and_the_visitor_flag(l2_world, cache):
    body = ok(
        await call("ingest_attachment", {"path": "images/img_0123456789ab.jpg",
                                         "for_visitor": True})
    )  # fmt: skip
    assert sql("SELECT visitor FROM batches WHERE id = %s", (body["batch_id"],)) == [(True,)]
    assert sql(
        "SELECT original_name, mime_type FROM documents WHERE id = %s", (body["document_id"],)
    ) == [("img_0123456789ab.jpg", "image/jpeg")]


async def test_the_same_bytes_again_are_a_duplicate_carded_only_where_visible(l2_world, cache):
    first = ok(await call("ingest_attachment", {"path": f"documents/{NAME}"}))
    web = ok(await call("ingest_attachment", {"path": f"documents/{NAME}"}))
    tg = ok(await call("ingest_attachment", {"path": f"documents/{NAME}"}, channel="telegram"))
    assert (web["outcome"], web["document_id"], len(web["card_refs"])) == (
        "duplicate", first["document_id"], 1,
    )  # fmt: skip
    assert (tg["outcome"], tg["document_id"], tg["card_refs"]) == ("duplicate", None, [])
    assert sql("SELECT count(*) FROM documents WHERE sha256 = %s", (SHA,)) == [(1,)]


async def test_a_trashed_duplicate_says_deleted_and_gets_no_card(l2_world, cache):
    w = l2_world
    doc = w.doc(content=PDF)
    delete_document(w.ctx, doc, actor="user", via="ui")
    body = ok(await call("ingest_attachment", {"path": f"documents/{NAME}"}))
    assert (body["outcome"], body["document_id"], body["deleted"], body["card_refs"]) == (
        "duplicate", doc, True, [],
    )  # fmt: skip


async def test_unsupported_bytes_are_rejected_without_a_card(l2_world, cache):
    (cache / "documents" / "doc_aaaaaaaaaaaa_notes.txt").write_bytes(b"just text")
    body = ok(await call("ingest_attachment", {"path": "documents/doc_aaaaaaaaaaaa_notes.txt"}))
    assert (body["outcome"], body["reject_reason"], body["document_id"], body["card_refs"]) == (
        "rejected", "unsupported_type", None, [],
    )  # fmt: skip


async def test_refusals_write_nothing(l2_world, cache, tmp_path, monkeypatch):
    (tmp_path / "secret.pdf").write_bytes(PDF)
    (cache / "documents" / "folder").mkdir()
    before = sql("SELECT count(*) FROM batches")
    outside = error(await call("ingest_attachment", {"path": "../secret.pdf"}))
    absolute = error(await call("ingest_attachment", {"path": str(tmp_path / "secret.pdf")}))
    missing = error(await call("ingest_attachment", {"path": "documents/doc_ffffffffffff_x.pdf"}))
    folder = error(await call("ingest_attachment", {"path": "documents/folder"}))
    long = error(await call("ingest_attachment", {"path": "documents/" + "x" * 1020}))
    extra = error(await call("ingest_attachment", {"path": f"documents/{NAME}", "move": True}))
    monkeypatch.setattr(attach, "MAX_FILE_BYTES", len(PDF) - 1)
    big = error(await call("ingest_attachment", {"path": f"documents/{NAME}"}))
    assert (outside["code"], absolute["code"]) == ("forbidden_path", "forbidden_path")
    assert (missing["code"], folder["code"], big["code"]) == ("invalid_argument",) * 3
    assert outside["field"] == "path" and "secret" not in outside["message"]
    assert (long["code"], extra["code"]) == ("invalid_argument", "invalid_argument")
    assert sql("SELECT count(*) FROM batches") == before
    assert rows.card_rows() == []


async def test_it_opens_no_socket_but_postgres_and_moves_nothing(l2_world, cache, monkeypatch):
    real = socket.socket.connect
    pg_port = int(get_settings().libpq_url.rsplit(":", 1)[1].split("/")[0])

    def only_postgres(self, address):
        if not (isinstance(address, tuple) and address[1] == pg_port):
            raise AssertionError(f"socket connect to {address}")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", only_postgres)
    ok(await call("ingest_attachment", {"path": f"documents/{NAME}"}, channel="telegram"))
    assert sql("SELECT count(*) FROM file_ops") == [(0,)]
    assert (cache / "documents" / NAME).read_bytes() == PDF
