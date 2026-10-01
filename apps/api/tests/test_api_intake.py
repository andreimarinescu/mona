"""C2 §5 over HTTP: the upload's per-file results and limits (§17 item 5), and the batch reads."""

import zlib

import httpx
import psycopg
import pytest

from mona.api import intake
from mona.app import create_app
from mona.settings import get_settings
from tests.api_client import api_client

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
PNG_ROW = zlib.compress(b"\x00\xff\x00\x00")
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    + b"\x90wS\xde"
    + len(PNG_ROW).to_bytes(4, "big") + b"IDAT" + PNG_ROW
    + zlib.crc32(b"IDAT" + PNG_ROW).to_bytes(4, "big")
    + b"\x00\x00\x00\x00IEND\xaeB`\x82"
)  # fmt: skip
EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 48
TRUNCATED = PDF[:30]


@pytest.fixture
def app(l2_world):
    intake.get_intake_ctx.cache_clear()
    yield create_app()
    intake.get_intake_ctx.cache_clear()


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


def unique(tag: str) -> bytes:
    return PDF + f"% {tag}\n".encode()


def files(*parts: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("file", (name, data, "application/octet-stream")) for name, data in parts]


def extract_jobs(doc_ids: list[str]) -> list[str]:
    rows = sql(
        "SELECT args->>'document_id' FROM procrastinate_jobs WHERE task_name = 'extract_text'"
        " AND args->>'document_id' = ANY(%s) ORDER BY id",
        (doc_ids,),
    )
    return [r[0] for r in rows]


def inbox_files(w) -> list[str]:
    return sorted(p.name for p in w.ctx.ops.roots.inbox.iterdir())


async def test_each_part_gets_its_result_in_part_order(l2_world, app):
    w = l2_world
    before = inbox_files(w)
    sent = [("a.pdf", unique("a")), ("photo.jpg", JPEG), ("scan.png", PNG),
            ("invoice.pdf", EXE), ("empty.pdf", b"")]  # fmt: skip
    async with api_client(app) as c:
        res = await c.post("/api/intake", files=files(*sent))
        assert res.status_code == 201, res.text
        body = res.json()
        detail = await c.get(f"/api/batches/{body['batch']['id']}")
    items = body["items"]
    assert [i["originalName"] for i in items] == [n for n, _ in sent]
    assert [(i["outcome"], i["rejectReason"]) for i in items] == [
        ("accepted", None), ("accepted", None), ("accepted", None),
        ("rejected", "unsupported_type"), ("rejected", "empty"),
    ]  # fmt: skip
    assert [i["sizeBytes"] for i in items] == [len(d) for _, d in sent]
    accepted = [i["documentId"] for i in items[:3]]
    assert extract_jobs(accepted) == accepted
    assert inbox_files(w) == sorted([*before, f"{accepted[0]}.pdf", f"{accepted[1]}.jpg",
                                      f"{accepted[2]}.png"])  # fmt: skip
    batch = body["batch"]
    assert (batch["source"], batch["status"], batch["visitor"], batch["finishedAt"]) == (
        "drop", "running", False, None,
    )  # fmt: skip
    assert batch["counts"] == {
        "items": 5, "accepted": 3, "duplicate": 0, "rejected": 2, "processing": 3, "filed": 0,
        "review": 0, "unreadable": 0, "failed": 0,
    }  # fmt: skip
    assert sql("SELECT kind, actor, via FROM op_groups WHERE id = %s", (batch["groupId"],)) == [
        ("intake_batch", "mona", "pipeline")
    ]
    got = detail.json()
    assert [i["id"] for i in got["items"]] == [i["id"] for i in items]
    assert [i["document"]["pipelineStage"] for i in got["items"][:3]] == ["queued"] * 3
    assert [i["document"] for i in got["items"][3:]] == [None, None]


@pytest.mark.xfail(strict=True, reason="ingest_files sniffs magic bytes only (L1 change needed)")
async def test_a_truncated_pdf_is_an_unreadable_file(l2_world, app):
    async with api_client(app) as c:
        res = await c.post("/api/intake", files=files(("cut.pdf", TRUNCATED)))
    item = res.json()["items"][0]
    assert (item["outcome"], item["rejectReason"]) == ("rejected", "unreadable_file")


async def test_the_same_bytes_again_are_a_duplicate_and_the_batch_is_done(l2_world, app):
    data = unique("dup")
    async with api_client(app) as c:
        first = (await c.post("/api/intake", files=files(("x.pdf", data)))).json()
        again = (await c.post("/api/intake", files=files(("y.pdf", data)))).json()
    doc = first["items"][0]["documentId"]
    item = again["items"][0]
    assert (item["outcome"], item["documentId"], item["deleted"], item["restoreJournalId"]) == (
        "duplicate", doc, False, None,
    )  # fmt: skip
    assert again["batch"]["id"] != first["batch"]["id"]
    assert again["batch"]["status"] == "done" and again["batch"]["finishedAt"] is not None
    assert sql("SELECT count(*) FROM documents WHERE sha256 = %s", (item["sha256"],)) == [(1,)]


async def test_a_deleted_documents_bytes_upload_again_as_a_new_visitor_document(l2_world, app):
    """A24."""
    data = unique("reupload")
    async with api_client(app) as c:
        first = (await c.post("/api/intake", files=files(("x.pdf", data)))).json()
        old = first["items"][0]["documentId"]
        [(path,)] = sql("SELECT current_path FROM documents WHERE id = %s", (old,))
        gone = await c.post(f"/api/documents/{old}/delete", json={"confirm": True,
                                                                  "fileName": path})  # fmt: skip
        assert gone.status_code == 200, gone.text
        entry = gone.json()["undo"]["journalId"]
        again = await c.post("/api/intake", files=files(("x.pdf", data)), data={"visitor": "true"})
        item = again.json()["items"][0]
        twin = item["documentId"]
        refused = await c.post(f"/api/journal/{entry}/undo", json={})
        had = (await c.post("/api/intake", files=files(("y.pdf", data)))).json()["items"][0]
        [(twin_path,)] = sql("SELECT current_path FROM documents WHERE id = %s", (twin,))
        await c.post(f"/api/documents/{twin}/delete", json={"confirm": True, "fileName": twin_path})
        restored = await c.post(f"/api/journal/{entry}/undo", json={})
    assert (item["outcome"], item["deleted"], item["restoreJournalId"]) == ("accepted", False, None)
    assert twin != old and again.json()["batch"]["visitor"] is True
    visitors = "SELECT e.purge_after_hours IS NOT NULL FROM documents d JOIN entities e"
    assert sql(visitors + " ON e.id = d.entity_id WHERE d.id = %s", (twin,)) == [(True,)]
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "conflict"
    assert refused.json()["error"]["details"] == {"reason": "duplicate"}
    assert (had["outcome"], had["documentId"], had["deleted"]) == ("duplicate", twin, False)
    assert restored.status_code == 200, restored.text
    assert sql("SELECT id, deleted_at IS NULL FROM documents WHERE sha256 = %s ORDER BY id",
               (item["sha256"],)) == sorted([(old, True), (twin, False)])  # fmt: skip


async def test_the_visitor_flag_and_title_mark_the_batch(l2_world, app):
    async with api_client(app) as c:
        res = await c.post(
            "/api/intake", files=files(("v.pdf", unique("visitor"))),
            data={"visitor": "true", "title": "  Salon stand  "},
        )  # fmt: skip
    batch = res.json()["batch"]
    assert (batch["visitor"], batch["title"]) == (True, "Salon stand")
    assert sql("SELECT visitor, title, source FROM batches WHERE id = %s", (batch["id"],)) == [
        (True, "Salon stand", "drop")
    ]


async def test_51_files_are_413_and_nothing_is_written(l2_world, app):
    w = l2_world
    before = (sql("SELECT count(*) FROM batches"), inbox_files(w))
    many = [(f"f{i}.pdf", unique(f"many{i}")) for i in range(51)]
    async with api_client(app) as c:
        res = await c.post("/api/intake", files=files(*many))
    assert res.status_code == 413 and res.json()["error"]["code"] == "too_large"
    assert (sql("SELECT count(*) FROM batches"), inbox_files(w)) == before
    assert sql("SELECT count(*) FROM intake_items") == [(0,)]


async def test_a_part_over_25_mb_is_refused_as_it_streams_and_nothing_is_written(
    l2_world, app, monkeypatch
):
    w = l2_world
    monkeypatch.setattr(intake, "MAX_FILE_BYTES", 1000)
    seen = []
    real = intake.UploadForm._part_data

    def spy(self, data, start, end):
        seen.append(end - start)
        return real(self, data, start, end)

    monkeypatch.setattr(intake.UploadForm, "_part_data", spy)
    before = (sql("SELECT count(*) FROM batches"), inbox_files(w))

    async def body():
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="big.pdf"\r\n\r\n'
        for _ in range(100):
            yield b"%PDF-" + b"x" * 495

    async with api_client(app) as c:
        res = await c.post(
            "/api/intake", content=body(),
            headers={"content-type": "multipart/form-data; boundary=b"},
        )  # fmt: skip
    assert res.status_code == 413 and res.json()["error"]["code"] == "too_large"
    assert sum(seen) <= 1500
    assert (sql("SELECT count(*) FROM batches"), inbox_files(w)) == before


async def test_exactly_the_limits_are_accepted(l2_world, app, monkeypatch):
    monkeypatch.setattr(intake, "MAX_FILE_BYTES", 1000)
    monkeypatch.setattr(intake, "MAX_FILES", 3)
    data = unique("limit")
    data += b"x" * (1000 - len(data))
    async with api_client(app) as c:
        res = await c.post("/api/intake", files=files(("a.pdf", data), ("b.pdf", JPEG),
                                                      ("c.png", PNG)))  # fmt: skip
    assert res.status_code == 201, res.text
    assert [i["outcome"] for i in res.json()["items"]] == ["accepted"] * 3


@pytest.mark.parametrize(
    ("kwargs", "status", "field"),
    [
        ({"json": {"file": "x"}}, 415, None),
        ({"files": [("visitor", (None, b"true"))]}, 400, "file"),
        ({"data": {"visitor": "yes"}, "files": [("file", ("a.pdf", PDF))]}, 400, "visitor"),
        ({"data": {"title": "t" * 121}, "files": [("file", ("a.pdf", PDF))]}, 400, "title"),
        ({"data": {"note": "x"}, "files": [("file", ("a.pdf", PDF))]}, 400, "note"),
        ({"files": [("upload", ("a.pdf", PDF))]}, 400, "upload"),
    ],
)
async def test_malformed_uploads_are_refused_and_write_nothing(
    l2_world, app, kwargs, status, field
):
    async with api_client(app) as c:
        res = await c.post("/api/intake", **kwargs)
    assert res.status_code == status, res.text
    assert res.json()["error"].get("field") == field
    assert sql("SELECT count(*) FROM intake_items") == [(0,)]


async def test_an_unterminated_body_is_400(l2_world, app):
    before = sql("SELECT count(*) FROM batches")
    async with api_client(app) as c:
        res = await c.post(
            "/api/intake",
            content=b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'
            + PDF,
            headers={"content-type": "multipart/form-data; boundary=b"},
        )
    assert res.status_code == 400 and res.json()["error"]["code"] == "invalid_request"
    assert sql("SELECT count(*) FROM batches") == before


async def test_batches_list_newest_first_detail_polls_and_title_patch(l2_world, app):
    async with api_client(app) as c:
        a = (await c.post("/api/intake", files=files(("a.pdf", unique("l1"))))).json()["batch"]
        b = (await c.post("/api/intake", files=files(("b.pdf", unique("l2"))))).json()["batch"]
        page = (await c.get("/api/batches")).json()
        two = (await c.get("/api/batches", params={"limit": 2, "offset": 1})).json()
        first = await c.get(f"/api/batches/{b['id']}")
        cached = await c.get(
            f"/api/batches/{b['id']}", headers={"If-None-Match": first.headers["etag"]}
        )
        renamed = await c.patch(f"/api/batches/{a['id']}", json={"title": "Tuesday's post"})
        cleared = await c.patch(f"/api/batches/{a['id']}", json={"title": None})
        too_long = await c.patch(f"/api/batches/{a['id']}", json={"title": "x" * 121})
        unknown = await c.get("/api/batches/bat_00000000000000000000000000")
        wrong = await c.get("/api/batches/doc_00000000000000000000000000")
    ids = [i["id"] for i in page["items"]]
    starts = [i["startedAt"] for i in page["items"]]
    assert starts == sorted(starts, reverse=True) and ids.index(b["id"]) < ids.index(a["id"])
    assert page["total"] == len(ids) >= 3 and [i["id"] for i in two["items"]] == ids[1:3]
    assert (two["offset"], two["limit"], two["total"]) == (1, 2, len(ids))
    assert first.status_code == 200 and first.headers["etag"].startswith('W/"')
    assert cached.status_code == 304
    assert renamed.status_code == 200 and renamed.json()["title"] == "Tuesday's post"
    assert cleared.json()["title"] is None
    assert too_long.status_code == 400 and too_long.json()["error"]["field"] == "title"
    assert unknown.status_code == 404 == wrong.status_code


async def test_upload_needs_a_session_and_a_csrf_token(l2_world, app):
    async with api_client(app) as c:
        no_csrf = await c.post(
            "/api/intake", files=files(("a.pdf", PDF)), headers={"x-csrf-token": "nope"}
        )
    assert no_csrf.status_code == 403
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as c:
        anon = await c.post("/api/intake", files=files(("a.pdf", PDF)))
    assert anon.status_code == 401
    assert sql("SELECT count(*) FROM intake_items") == [(0,)]


async def test_the_batch_detail_keeps_upload_order_within_a_millisecond(l2_world, app):
    sent = [(f"note-{i:02}.txt", b"plain text %d" % i) for i in range(40)]
    async with api_client(app) as c:
        body = (await c.post("/api/intake", files=files(*sent))).json()
        got = (await c.get(f"/api/batches/{body['batch']['id']}")).json()
    assert [i["originalName"] for i in got["items"]] == [n for n, _ in sent]
