"""C2 §4 and §6 over HTTP: search, detail, files, folders, review and document actions."""

from datetime import date

import psycopg
import pytest
from sqlalchemy import insert, select, update

from mona.app import create_app
from mona.ids import new_id
from mona.services import correct_document
from mona.services.registry import T
from mona.settings import get_settings
from tests.api_client import api_client

PDF = b"%PDF-1.4\n" + b"x" * 400


@pytest.fixture
def app(l2_world):
    return create_app()


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


def filed(w, **kw) -> str:
    """A document filed by Mona through the correction service."""
    doc = w.doc(content=kw.pop("content", None), **kw)
    correct_document(
        w.ctx, doc, actor="mona", via="chat", entity=kw.get("entity") or "cabinet",
        category=kw.get("category") or "payment_calls",
    )  # fmt: skip
    return doc


def classify(w, doc: str, *, entity: str | None, category: str | None, path: str | None,
             name: str | None, rule: str | None = None) -> str:  # fmt: skip
    ids = w.ids("entities")
    cls = new_id("cls")
    with w.engine.begin() as conn:
        conn.execute(
            insert(T["classifications"]).values(
                id=cls, document_id=doc, method="llm", entity_id=ids.get(entity),
                category_id=category, confidence=55, band="low", reasons=["low"],
                proposed_path=path, proposed_file_name=name,
                rule_id=w.rule_id(rule) if rule else None,
            )
        )  # fmt: skip
        d = T["documents"]
        conn.execute(update(d).where(d.c.id == doc).values(classification_id=cls))
    return cls


# --- §4.1 search ---


async def test_search_filters_sorts_and_facets(l2_world, app):
    w = l2_world
    a = filed(w, counterparty="opco", category="payment_calls", entity="cabinet",
              doc_date=date(2025, 3, 1), amount=100, title="OPCO appel mars")  # fmt: skip
    b = filed(w, counterparty="opco", category="payment_calls", entity="cabinet",
              doc_date=date(2025, 6, 1), amount=300, title="OPCO appel juin")  # fmt: skip
    c = filed(w, counterparty="talenz", category="annual_accounts", entity="studio",
              doc_date=date(2024, 9, 30), amount=900, title="TALENZ bilan")  # fmt: skip
    r = w.doc(counterparty="opco", title="Unknown letter")
    ents = w.ids("entities")
    async with api_client(app) as cl:
        all_ = (await cl.get("/api/documents")).json()
        assert [i["id"] for i in all_["items"]] == [b, a, c, r]
        assert all_["total"] == 4 and all_["offset"] == 0 and all_["limit"] == 50
        cab = (await cl.get("/api/documents", params={"entityId": ents["cabinet"]})).json()
        assert {i["id"] for i in cab["items"]} == {a, b}
        facet = {f["name"]: f["count"] for f in cab["facets"]["entities"]}
        assert facet == {"Cabinet Marchand SELARL": 2, "Studio Numérique SASU": 1}
        assert cab["facets"]["amount"] == {"min": 100.0, "max": 300.0}
        years = (await cl.get("/api/documents", params={"year": 2025})).json()
        assert {i["id"] for i in years["items"]} == {a, b}
        assert {y["year"]: y["count"] for y in years["facets"]["years"]} == {2025: 2, 2024: 1}
        amount = await cl.get("/api/documents", params={"amountMin": 200, "sort": "amount_desc"})
        assert [i["id"] for i in amount.json()["items"]] == [c, b]
        status = (await cl.get("/api/documents", params={"status": "review"})).json()
        assert [i["id"] for i in status["items"]] == [r]
        counts = {s["status"]: s["count"] for s in status["facets"]["statuses"]}
        assert counts == {"filed": 3, "review": 1}
        q = (await cl.get("/api/documents", params={"q": "juin"})).json()
        assert [i["id"] for i in q["items"]] == [b]
        cats = (await cl.get("/api/documents", params={"categoryId": "annual_accounts"})).json()
        assert {x["id"]: x["label"] for x in cats["facets"]["categories"]}["annual_accounts"] == (
            "Annual accounts"
        )
        page = (await cl.get("/api/documents", params={"limit": 1, "offset": 1})).json()
        assert [i["id"] for i in page["items"]] == [a] and page["total"] == 4
        bad = await cl.get("/api/documents", params={"entityId": "doc_" + "0" * 26})
        assert bad.status_code == 400 and bad.json()["error"]["field"] == "entityId"


# --- §4.2 detail ---


async def test_detail_has_fields_suggestion_journal_and_deadlines(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="opco", category="payment_calls", doc_type="appel",
                verified={"amount": True, "doc_date": False}, amount=42.5,
                doc_date=date(2025, 1, 2))  # fmt: skip
    classify(w, doc, entity="cabinet", category="payment_calls", path="Cabinet Marchand/X",
             name="f.pdf")  # fmt: skip
    sql("UPDATE extraction_fields SET currency = 'EUR' WHERE key = 'amount'")
    async with api_client(app) as cl:
        d = (await cl.get(f"/api/documents/{doc}")).json()
        sql("UPDATE profile SET locale = 'fr'")
        fr = (await cl.get(f"/api/documents/{doc}")).json()
    assert [f["key"] for f in d["fields"]] == ["doc_date", "amount"]
    amount = d["fields"][1]
    assert amount["money"] == {"value": 42.5, "currency": "EUR"}
    assert amount["evidence"]["documentTitle"] == d["title"] and amount["evidence"]["verified"]
    s = d["suggestion"]
    assert s["path"] == ["Cabinet Marchand", "X"] and s["fileName"] == "f.pdf"
    assert s["sentence"] == (
        "I think this document from OPCO EP (appel) belongs to Cabinet Marchand SELARL, "
        "but I'm not sure enough to file it."
    )
    assert fr["suggestion"]["sentence"].startswith("Je pense que ce document de OPCO EP (appel)")
    assert d["journal"] == [] and d["deadlines"] == []
    assert d["pdfUrl"] == f"/api/documents/{doc}/pdf" and d["thumbnailUrl"] is None


async def test_unknown_deleted_or_mistyped_ids_are_404(l2_world, app):
    w = l2_world
    doc = filed(w, counterparty="opco")
    sql("UPDATE documents SET deleted_at = now(), location = 'trash' WHERE id = %s", (doc,))
    async with api_client(app) as cl:
        for path in (f"/api/documents/{doc}", "/api/documents/doc_" + "0" * 26,
                     "/api/documents/ent_" + "0" * 26, "/api/documents/nope"):  # fmt: skip
            res = await cl.get(path)
            assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"


# --- §4.3 files (test 8) ---


async def test_pdf_serves_archive_bytes_resolved_per_request_with_ranges(l2_world, app):
    w = l2_world
    doc = filed(w, counterparty="opco", content=PDF)
    async with api_client(app) as cl:
        res = await cl.get(f"/api/documents/{doc}/pdf")
        assert res.status_code == 200 and res.content == PDF
        sha = w.row(doc)["sha256"]
        assert res.headers["etag"] == f'"{sha}"'
        assert res.headers["content-type"] == "application/pdf"
        assert res.headers["content-disposition"].startswith("inline; filename*=UTF-8''")
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["content-security-policy"] == "sandbox"
        assert res.headers["accept-ranges"] == "bytes"
        part = await cl.get(f"/api/documents/{doc}/pdf", headers={"range": "bytes=0-99"})
        assert part.status_code == 206 and part.content == PDF[:100]
        before = w.disk_path(doc)
        correct_document(w.ctx, doc, actor="user", via="ui", category="bank")
        assert w.disk_path(doc) != before and not before.exists()
        moved = await cl.get(f"/api/documents/{doc}/pdf")
        assert moved.status_code == 200 and moved.content == PDF
        original = await cl.get(f"/api/documents/{doc}/original")
        assert original.content == PDF
        assert original.headers["content-disposition"].startswith("attachment; filename*=")


async def test_pdf_prefers_the_ocr_copy_and_images_wait_for_it(l2_world, app):
    w = l2_world
    doc = filed(w, counterparty="opco")
    sha = w.row(doc)["sha256"]
    ocr = w.ctx.textcache / sha[:2] / f"{sha}.ocr.pdf"
    ocr.write_bytes(b"%PDF-ocr")
    img = w.doc(counterparty="opco")
    sql("UPDATE documents SET mime_type = 'image/jpeg' WHERE id = %s", (img,))
    async with api_client(app) as cl:
        res = await cl.get(f"/api/documents/{doc}/pdf")
        assert res.content == b"%PDF-ocr" and res.headers["etag"] == f'"{sha}.ocr"'
        wait = await cl.get(f"/api/documents/{img}/pdf")
        assert wait.status_code == 404 and wait.json()["error"]["code"] == "not_ready"
        thumb = await cl.get(f"/api/documents/{doc}/thumbnail")
        assert thumb.status_code == 404 and thumb.json()["error"]["code"] == "not_ready"
        (w.ctx.textcache / sha[:2] / f"{sha}.p1.png").write_bytes(b"\x89PNG")
        thumb = await cl.get(f"/api/documents/{doc}/thumbnail")
        assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/png"
        assert thumb.headers["cache-control"] == "private, max-age=86400"
        summary = (await cl.get(f"/api/documents/{doc}")).json()
        assert summary["thumbnailUrl"] == f"/api/documents/{doc}/thumbnail"
        sql("UPDATE documents SET deleted_at = now(), location = 'trash' WHERE id = %s", (doc,))
        assert (await cl.get(f"/api/documents/{doc}/pdf")).status_code == 404


async def test_pdf_path_outside_its_root_is_refused_by_the_guard(l2_world, app, tmp_path):
    w = l2_world
    doc = filed(w, counterparty="opco", content=PDF)
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"%PDF-secret")
    target = w.disk_path(doc)
    link_dir = target.parent / "evil"
    link_dir.symlink_to(tmp_path, target_is_directory=True)
    rel = w.row(doc)["current_path"].rpartition("/")[0] + "/evil/secret.pdf"
    sql("UPDATE documents SET current_path = %s WHERE id = %s", (rel, doc))
    async with api_client(app) as cl:
        res = await cl.get(f"/api/documents/{doc}/pdf")
    assert res.status_code == 404 and b"secret" not in res.content


# --- §4.5 folders ---


async def test_folders_list_children_with_recursive_counts(l2_world, app):
    w = l2_world
    a = filed(w, counterparty="opco", doc_date=date(2025, 3, 1))
    filed(w, counterparty="opco", doc_date=date(2024, 3, 1))
    filed(w, counterparty="talenz", category="annual_accounts", entity="studio",
          doc_date=date(2025, 5, 1))  # fmt: skip
    async with api_client(app) as cl:
        root = (await cl.get("/api/folders")).json()
        cab = (await cl.get("/api/folders", params={"path": "Cabinet Marchand"})).json()
        leaf_path = w.row(a)["current_path"].rpartition("/")[0]
        leaf = (await cl.get("/api/folders", params={"path": leaf_path})).json()
    assert [(f["name"], f["documentCount"], f["hasChildren"]) for f in root["folders"]] == [
        ("Cabinet Marchand", 2, True),
        ("Studio Numérique", 1, True),
    ]
    assert root["documents"] == [] and root["path"] == []
    assert [f["name"] for f in cab["folders"]] == ["Appels de paiement"]
    assert [d["id"] for d in leaf["documents"]] == [a]
    assert leaf["path"] == leaf_path.split("/")


# --- §6.1 review ---


async def test_review_lists_review_and_unreadable_oldest_first(l2_world, app):
    w = l2_world
    first = w.doc(counterparty="opco")
    second = w.doc(counterparty="opco")
    sql("UPDATE documents SET arrived_at = arrived_at - interval '1 hour' WHERE id = %s", (first,))
    filed(w, counterparty="talenz")
    async with api_client(app) as cl:
        page = (await cl.get("/api/review")).json()
        low = (await cl.get("/api/review", params={"reason": "conflict"})).json()
    assert [i["id"] for i in page["items"]] == [first, second] and page["total"] == 2
    assert low["items"] == []


# --- §6.2 actions ---


async def test_confirm_files_the_suggestion_and_closes_the_item_confirmed(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="opco")
    classify(w, doc, entity="cabinet", category="payment_calls",
             path="Cabinet Marchand/Appels de paiement/2025", name="x.pdf")  # fmt: skip
    async with api_client(app) as cl:
        res = await cl.post(f"/api/documents/{doc}/confirm")
        again = await cl.post(f"/api/documents/{doc}/confirm")
    body = res.json()
    assert res.status_code == 200 and body["outcome"] == "moved"
    assert body["document"]["status"] == "filed"
    assert body["undo"] == {"journalId": body["journalIds"][0]} and body["groupId"] is None
    assert again.json()["outcome"] == "unchanged" and again.json()["journalIds"] == []
    [(resolution, by)] = sql(
        "SELECT resolution, resolved_by FROM review_items WHERE document_id = %s", (doc,)
    )
    assert (resolution, by) == ("confirmed", "user")
    [(actor, via)] = sql("SELECT actor, via FROM file_ops WHERE document_id = %s", (doc,))
    assert (actor, via) == ("user", "ui")


async def test_confirm_without_an_entity_or_path_is_not_renderable(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="opco")
    classify(w, doc, entity=None, category="payment_calls", path=None, name=None)
    async with api_client(app) as cl:
        res = await cl.post(f"/api/documents/{doc}/confirm")
    assert res.status_code == 422 and res.json()["error"]["code"] == "not_renderable"


async def test_correct_writes_a_user_classification_and_a_correction_group(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="opco", extracted_counterparty="OPCO Atlas")
    ents = w.ids("entities")
    body = {"entityId": ents["cabinet"], "categoryId": "payment_calls",
            "counterparty": {"name": "OPCO EP"}, "docDate": "2025-02-03"}  # fmt: skip
    async with api_client(app) as cl:
        res = await cl.post(f"/api/documents/{doc}/correct", json=body)
        again = await cl.post(f"/api/documents/{doc}/correct", json=body)
    r = res.json()
    assert res.status_code == 200 and r["outcome"] == "moved"
    assert r["undo"] == {"groupId": r["groupId"]} and r["document"]["status"] == "filed"
    assert again.json()["outcome"] == "unchanged"
    [(method,)] = sql(
        "SELECT method FROM classifications WHERE document_id = %s ORDER BY created_at DESC"
        " LIMIT 1",
        (doc,),
    )
    [(kind, actor, via)] = sql("SELECT kind, actor, via FROM op_groups WHERE id = %s",
                               (r["groupId"],))  # fmt: skip
    [(resolution, scope)] = sql(
        "SELECT resolution, scope FROM review_items WHERE document_id = %s", (doc,)
    )
    assert method == "user" and (kind, actor, via) == ("correction", "user", "ui")
    assert (resolution, scope) == ("corrected", "one")
    assert sql("SELECT 1 FROM counterparty_aliases WHERE alias_norm = 'opco atlas'")


async def test_correcting_into_visitors_is_403_and_bad_input_is_400(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="opco")
    ents = w.ids("entities")
    async with api_client(app) as cl:
        visitors = await cl.post(
            f"/api/documents/{doc}/correct",
            json={"entityId": ents["visitors"], "categoryId": "payment_calls"},
        )
        empty = await cl.post(f"/api/documents/{doc}/correct", json={})
        unknown = await cl.post(f"/api/documents/{doc}/correct", json={"colour": "red"})
    assert visitors.status_code == 403 and visitors.json()["error"]["code"] == "not_allowed"
    assert empty.status_code == 400
    assert unknown.status_code == 400 and unknown.json()["error"]["field"] == "colour"


async def test_a_visitor_document_corrects_its_category_but_never_its_entity(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="opco", category="payment_calls", entity="visitors",
                doc_date=date(2026, 2, 27), batch=w.new_batch(visitor=True))  # fmt: skip
    ents = w.ids("entities")
    async with api_client(app) as cl:
        moved = await cl.post(f"/api/documents/{doc}/correct", json={"entityId": ents["cabinet"]})
        kept = await cl.post(f"/api/documents/{doc}/correct", json={"entityId": ents["visitors"]})
        category = await cl.post(
            f"/api/documents/{doc}/correct", json={"categoryId": "tax", "subcategoryKey": None}
        )
    assert moved.status_code == kept.status_code == 403
    assert moved.json()["error"]["code"] == "not_allowed"
    assert category.status_code == 200, category.text
    r = w.row(doc)
    assert (r["entity_id"], r["category_id"], r["status"]) == (ents["visitors"], "tax", "filed")
    assert r["current_path"].startswith("Visitors/")


async def test_the_review_page_body_with_a_null_subcategory_files_the_document(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="agipi", category="insurance", subcategory="per", entity="personal",
                doc_date=date(2025, 4, 14))  # fmt: skip
    ents = w.ids("entities")
    body = {"entityId": ents["cabinet"], "categoryId": "payment_calls", "subcategoryKey": None}
    async with api_client(app) as cl:
        res = await cl.post(f"/api/documents/{doc}/correct", json=body)
    assert res.status_code == 200, res.text
    r = res.json()
    assert r["outcome"] == "moved" and r["document"]["status"] == "filed"
    row = w.row(doc)
    assert (row["category_id"], row["subcategory_key"]) == ("payment_calls", None)
    assert row["current_path"].startswith("Cabinet Marchand/Appels de paiement/")


async def test_a_null_clears_the_subcategory_sub_unit_due_date_and_amount(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="hello-bank", category="bank", subcategory="releve", entity="lmnp",
                doc_date=date(2025, 6, 30), due_date=date(2025, 7, 15), amount=42)  # fmt: skip
    unit = w.ids("sub_units")["angers-strasbourg"]
    async with api_client(app) as cl:
        first = await cl.post(f"/api/documents/{doc}/correct", json={"subUnitId": unit})
        assert first.status_code == 200, first.text
        assert w.row(doc)["sub_unit_id"] == unit
        res = await cl.post(
            f"/api/documents/{doc}/correct",
            json={"subUnitId": None, "subcategoryKey": None, "dueDate": None, "amount": None},
        )
        again = await cl.post(f"/api/documents/{doc}/correct", json={"dueDate": None})
    assert res.status_code == 200, res.text
    row = w.row(doc)
    assert (row["sub_unit_id"], row["subcategory_key"]) == (None, None)
    assert (row["due_date"], row["amount"], row["currency"]) == (None, None, None)
    assert row["category_id"] == "bank" and row["status"] == "filed"
    assert again.status_code == 200 and again.json()["outcome"] == "unchanged"


async def test_correcting_a_processing_document_is_a_conflict(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="opco", status="processing")
    ents = w.ids("entities")
    async with api_client(app) as cl:
        res = await cl.post(
            f"/api/documents/{doc}/correct",
            json={"entityId": ents["cabinet"], "categoryId": "payment_calls"},
        )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "conflict"
    assert res.json()["error"]["details"] == {"reason": "processing"}
    row = w.row(doc)
    assert (row["status"], row["location"]) == ("processing", "inbox")


async def test_like_this_drafts_a_rule_whose_preview_matches_the_rules_endpoint(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="opco")
    w.doc(counterparty="opco")
    ents = w.ids("entities")
    async with api_client(app) as cl:
        await cl.post(
            f"/api/documents/{doc}/correct",
            json={"entityId": ents["studio"], "categoryId": "payment_calls"},
        )
        res = await cl.post(f"/api/documents/{doc}/like-this", json={})
        again = await cl.post(f"/api/documents/{doc}/like-this")
        rule_id = res.json()["rule"]["id"]
        preview = (await cl.get(f"/api/rules/{rule_id}/preview")).json()
    body = res.json()
    assert res.status_code == 200 and body["rule"]["state"] == "draft"
    assert body["rule"]["source"] == "correction"
    assert again.json()["rule"]["id"] == rule_id
    assert body["preview"]["movesTotal"] == preview["movesTotal"] == 1
    assert body["preview"]["moves"] == preview["moves"]
    [(scope, rid)] = sql("SELECT scope, rule_id FROM review_items WHERE document_id = %s", (doc,))
    assert (scope, rid) == ("all", rule_id)


async def test_like_this_needs_a_correction_and_a_counterparty(l2_world, app):
    w = l2_world
    plain = w.doc(counterparty="opco")
    anonymous = w.doc()
    ents = w.ids("entities")
    async with api_client(app) as cl:
        none = await cl.post(f"/api/documents/{plain}/like-this")
        await cl.post(
            f"/api/documents/{anonymous}/correct",
            json={"entityId": ents["cabinet"], "categoryId": "payment_calls"},
        )
        no_cp = await cl.post(f"/api/documents/{anonymous}/like-this")
    assert none.status_code == 404
    assert no_cp.status_code == 422 and no_cp.json()["error"]["field"] == "counterparty"


async def test_unfile_sends_a_filed_document_back_to_review(l2_world, app):
    w = l2_world
    doc = filed(w, counterparty="opco")
    async with api_client(app) as cl:
        res = await cl.post(f"/api/documents/{doc}/unfile")
        again = await cl.post(f"/api/documents/{doc}/unfile")
    body = res.json()
    assert body["outcome"] == "moved" and body["document"]["status"] == "review"
    assert body["document"]["location"] == "inbox" and body["document"]["reasons"] == ["low"]
    assert again.json()["outcome"] == "unchanged"
    assert sql("SELECT count(*) FROM review_items WHERE document_id = %s AND status = 'open'",
               (doc,)) == [(1,)]  # fmt: skip


async def test_delete_needs_confirm_and_the_current_file_name(l2_world, app):
    w = l2_world
    doc = filed(w, counterparty="opco")
    name = w.row(doc)["current_path"].rpartition("/")[2]
    async with api_client(app) as cl:
        no_confirm = await cl.post(
            f"/api/documents/{doc}/delete", json={"confirm": False, "fileName": name}
        )
        mismatch = await cl.post(
            f"/api/documents/{doc}/delete", json={"confirm": True, "fileName": "other.pdf"}
        )
        assert w.row(doc)["deleted_at"] is None
        res = await cl.post(
            f"/api/documents/{doc}/delete", json={"confirm": True, "fileName": name}
        )
        gone = await cl.post(
            f"/api/documents/{doc}/delete", json={"confirm": True, "fileName": name}
        )
    assert no_confirm.status_code == 400
    assert mismatch.status_code == 422
    assert mismatch.json()["error"] == {
        "code": "invalid_value", "field": "fileName", "details": {"field": "fileName"},
        "message": "The typed name isn't the document's current file name.",
    }  # fmt: skip
    body = res.json()
    assert res.status_code == 200 and body["document"] is None and body["outcome"] == "moved"
    assert w.row(doc)["location"] == "trash"
    [(action, actor, via, undoable)] = sql(
        "SELECT action, actor, via, undoable FROM file_ops WHERE id = %s", (body["journalIds"][0],)
    )
    assert (action, actor, via, undoable) == ("delete", "user", "ui", True)
    assert gone.status_code == 404


async def test_actions_and_reads_are_journaled_as_the_person_in_the_ui(l2_world, app):
    w = l2_world
    doc = filed(w, counterparty="opco")
    async with api_client(app) as cl:
        await cl.post(f"/api/documents/{doc}/unfile")
        d = (await cl.get(f"/api/documents/{doc}")).json()
    assert [(e["action"], e["actor"], e["via"]) for e in d["journal"]][:1] == [
        ("unfile", "user", "ui")
    ]
    assert d["journal"][0]["undoState"] == "undoable"
    rows = w.engine.connect().execute(select(T["file_ops"].c.id)).all()
    assert len(rows) >= 2
