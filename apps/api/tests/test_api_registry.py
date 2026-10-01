"""C2 §8 registry over HTTP (C2 §17 item 14)."""

import logging

import psycopg
import pytest
from sqlalchemy import insert

from mona.app import create_app
from mona.ids import new_id
from mona.services.registry import T
from mona.settings import get_settings
from tests.api_client import api_client
from tests.pg import pg_dump
from tests.rows import CLEANUP

IBAN = "FR14 2004 1010 0505 0001 3M02 606"
IBAN_FLAT = IBAN.replace(" ", "")
NEW_ENTITY = {
    "displayName": "Atelier Nord SARL", "folderName": "Atelier Nord", "visibility": "practice",
    "fiscalYearEnd": "06-30", "siren": "123 456 789", "aliases": ["ATELIER NORD"],
}  # fmt: skip


REGISTRY = (
    "entities", "people", "counterparties", "counterparty_aliases", "categories",
    "subcategories", "templates", "sub_units", "entity_people", "accounts",
)  # parents first  # fmt: skip


@pytest.fixture
def app(l2_world):
    """The registry tables are restored after each test (the module shares one database)."""
    with psycopg.connect(get_settings().libpq_url) as conn:
        for t in REGISTRY:
            conn.execute(f"CREATE TABLE l2_snap_{t} AS SELECT * FROM {t}")
    yield create_app()
    with psycopg.connect(get_settings().libpq_url) as conn:
        for stmt in CLEANUP:
            conn.execute(stmt)
        for t in reversed(REGISTRY):
            conn.execute(f"DELETE FROM {t}")
        for t in REGISTRY:
            conn.execute(f"INSERT INTO {t} SELECT * FROM l2_snap_{t}")
            conn.execute(f"DROP TABLE l2_snap_{t}")


def sql(stmt: str, params: tuple = ()) -> list:
    with psycopg.connect(get_settings().libpq_url) as conn:
        cur = conn.execute(stmt, params)
        return cur.fetchall() if cur.description else []


def dbname() -> str:
    return get_settings().database_url.rsplit("/", 1)[1]


async def test_entities_list_with_counts_and_the_visitors_id(l2_world, app):
    w = l2_world
    w.doc(entity="studio")
    ids = w.ids("entities")
    async with api_client(app) as cl:
        body = (await cl.get("/api/entities")).json()
        one = await cl.get(f"/api/entities/{ids['lmnp']}")
    assert body["visitorsEntityId"] == ids["visitors"]
    assert {e["key"] for e in body["items"]} == set(ids)
    assert body["documentCounts"][ids["studio"]] == 1
    lmnp = one.json()
    assert one.status_code == 200 and lmnp["subUnits"][0]["key"] == "angers-strasbourg"
    assert lmnp["accounts"][0]["ibanLast4"] and "iban" not in lmnp["accounts"][0]
    assert {"aliases", "addresses", "purgeAfterHours", "sortOrder"} <= set(lmnp)


async def test_create_and_patch_an_entity(l2_world, app):
    async with api_client(app) as cl:
        res = await cl.post("/api/entities", json=NEW_ENTITY)
        created = res.json()
        patched = await cl.patch(
            f"/api/entities/{created['id']}", json={"displayName": "Atelier Nord", "aliases": []}
        )
        kept = await cl.patch(f"/api/entities/{created['id']}", json={"legalForm": "SARL"})
    assert res.status_code == 201
    assert (created["key"], created["siren"], created["fiscalYearEnd"]) == (
        "atelier-nord", "123456789", "06-30",
    )  # fmt: skip
    assert created["aliases"] == ["ATELIER NORD"] and created["purgeAfterHours"] is None
    assert patched.status_code == 200 and patched.json()["aliases"] == []
    assert kept.json()["displayName"] == "Atelier Nord" and kept.json()["legalForm"] == "SARL"


@pytest.mark.parametrize(
    ("patch", "status", "code", "field"),
    [
        ({"siren": "12345"}, 422, "invalid_value", "siren"),
        ({"fiscalYearEnd": "02-30"}, 422, "invalid_value", "fiscalYearEnd"),
        ({"key": "Bad Key"}, 422, "invalid_value", "key"),
        ({"folderName": "a/b"}, 422, "invalid_value", "folderName"),
        ({"folderName": "Cabinet Marchand"}, 409, "conflict", "folderName"),
        ({"purgeAfterHours": 24}, 403, "not_allowed", "purgeAfterHours"),
    ],
)
async def test_entity_write_refusals(l2_world, app, patch, status, code, field):
    async with api_client(app) as cl:
        res = await cl.post("/api/entities", json={**NEW_ENTITY, **patch})
    assert res.status_code == status
    assert (res.json()["error"]["code"], res.json()["error"]["field"]) == (code, field)
    assert sql("SELECT count(*) FROM entities WHERE folder_name = 'Atelier Nord'") == [(0,)]


async def test_visitors_keeps_its_identity_and_a_bounded_purge(l2_world, app):
    w = l2_world
    ids = w.ids("entities")
    visitors, cabinet = ids["visitors"], ids["cabinet"]
    async with api_client(app) as cl:
        renamed = await cl.patch(f"/api/entities/{visitors}", json={"displayName": "Guests"})
        hours = await cl.patch(f"/api/entities/{visitors}", json={"purgeAfterHours": 48})
        too_long = await cl.patch(f"/api/entities/{visitors}", json={"purgeAfterHours": 169})
        cleared = await cl.patch(f"/api/entities/{visitors}", json={"purgeAfterHours": None})
        folder = await cl.patch(f"/api/entities/{visitors}", json={"folderName": "Guests"})
        practice = await cl.patch(f"/api/entities/{cabinet}", json={"purgeAfterHours": 24})
        deleted = await cl.delete(f"/api/entities/{visitors}")
        sub = await cl.post(f"/api/entities/{visitors}/sub-units", json={"label": "X"})
    assert renamed.status_code == 200 and renamed.json()["displayName"] == "Guests"
    assert hours.json()["purgeAfterHours"] == 48
    assert [too_long.status_code, cleared.status_code] == [422, 422]
    assert too_long.json()["error"]["field"] == "purgeAfterHours"
    assert sql("SELECT purge_after_hours FROM entities WHERE id = %s", (visitors,)) == [(48,)]
    assert [folder.status_code, practice.status_code, deleted.status_code] == [403, 403, 403]
    assert sub.status_code == 403
    assert sql("SELECT purge_after_hours FROM entities WHERE id = %s", (cabinet,)) == [(None,)]


async def test_deleting_a_referenced_entity_is_in_use_never_500(l2_world, app):
    w = l2_world
    ids = w.ids("entities")
    async with api_client(app) as cl:
        lmnp = await cl.delete(f"/api/entities/{ids['lmnp']}")
        doc_ent = (await cl.post("/api/entities", json=NEW_ENTITY)).json()["id"]
        sub_ent = (
            await cl.post("/api/entities", json={**NEW_ENTITY, "folderName": "Sud", "siren": None})
        ).json()["id"]
        cls_ent = (
            await cl.post("/api/entities", json={**NEW_ENTITY, "folderName": "Est", "siren": None})
        ).json()["id"]
        free = (await cl.post("/api/entities", json={**NEW_ENTITY, "folderName": "Ouest"})).json()[
            "id"
        ]
        await cl.post(f"/api/entities/{sub_ent}/sub-units", json={"label": "Annexe"})
        doc = w.doc()
        sql("UPDATE documents SET entity_id = %s WHERE id = %s", (doc_ent, doc))
        other = w.doc()
        with w.engine.begin() as conn:
            conn.execute(
                insert(T["classifications"]).values(
                    id=new_id("cls"), document_id=other, method="llm", entity_id=cls_ent,
                    confidence=50, band="low", reasons=["low"],
                )
            )  # fmt: skip
        by_doc = await cl.delete(f"/api/entities/{doc_ent}")
        by_sub = await cl.delete(f"/api/entities/{sub_ent}")
        by_cls = await cl.delete(f"/api/entities/{cls_ent}")
        gone = await cl.delete(f"/api/entities/{free}")
        again = await cl.get(f"/api/entities/{free}")
    refs = {
        name: (r.status_code, r.json()["error"]["code"], r.json()["error"]["details"]["references"])
        for name, r in (("lmnp", lmnp), ("doc", by_doc), ("sub", by_sub), ("cls", by_cls))
    }
    assert refs["lmnp"] == (409, "in_use", ["sub_units", "accounts", "rules"])
    assert refs["doc"] == (409, "in_use", ["documents"])
    assert refs["sub"] == (409, "in_use", ["sub_units"])
    assert refs["cls"] == (409, "in_use", ["classifications"])
    assert gone.status_code == 204 and again.status_code == 404


async def test_sub_units_and_people_links(l2_world, app):
    w = l2_world
    ids, people = w.ids("entities"), w.ids("people")
    cabinet = ids["cabinet"]
    async with api_client(app) as cl:
        made = await cl.post(
            f"/api/entities/{cabinet}/sub-units",
            json={"label": "Annexe", "personId": people["anna"]},
        )
        sub_id = made.json()["subUnits"][0]["id"]
        clash = await cl.post(f"/api/entities/{cabinet}/sub-units", json={"label": "Annexe"})
        renamed = await cl.patch(f"/api/sub-units/{sub_id}", json={"label": "Annexe Est"})
        linked = await cl.put(
            f"/api/entities/{cabinet}/people/{people['paul']}", json={"role": "gérant"}
        )
        relinked = await cl.put(f"/api/entities/{cabinet}/people/{people['paul']}", json={})
        unlinked = await cl.delete(f"/api/entities/{cabinet}/people/{people['paul']}")
        used = await cl.delete(f"/api/sub-units/{w.ids('sub_units')['angers-strasbourg']}")
        dropped = await cl.delete(f"/api/sub-units/{sub_id}")
    assert made.status_code == 201 and made.json()["subUnits"][0]["key"] == "annexe"
    assert clash.status_code == 409 and clash.json()["error"]["details"]["reason"] == "duplicate"
    assert renamed.json()["subUnits"][0]["label"] == "Annexe Est"
    assert linked.status_code == 200
    assert {"personId": people["paul"], "role": "gérant"} in linked.json()["people"]
    assert {"personId": people["paul"], "role": None} in relinked.json()["people"]
    assert unlinked.status_code == 200
    assert people["paul"] not in [p["personId"] for p in unlinked.json()["people"]]
    assert used.status_code == 409 and used.json()["error"]["details"]["references"] == ["rules"]
    assert dropped.status_code == 204


async def test_an_iban_is_never_stored_logged_or_echoed(l2_world, app, caplog):
    w = l2_world
    cabinet = w.ids("entities")["cabinet"]
    caplog.set_level(logging.DEBUG)
    async with api_client(app) as cl:
        res = await cl.post(
            f"/api/entities/{cabinet}/accounts",
            json={"label": "Atelier · courant", "iban": IBAN, "currency": "EUR"},
        )
        dup = await cl.post(
            f"/api/entities/{cabinet}/accounts",
            json={"label": "Again", "iban": IBAN_FLAT.lower(), "currency": "EUR"},
        )
        bad = await cl.post(
            f"/api/entities/{cabinet}/accounts",
            json={"label": "Bad", "iban": IBAN_FLAT[:-1] + "7", "currency": "EUR"},
        )
    assert res.status_code == 201
    account = next(a for a in res.json()["accounts"] if a["key"] == "atelier-courant")
    assert account["ibanLast4"] == "2606"
    assert (
        dup.status_code == 409 and dup.json()["error"]["details"]["reason"] == "duplicate_account"
    )
    assert bad.status_code == 422 and bad.json()["error"]["field"] == "iban"
    dump = pg_dump(dbname(), "--data-only")
    for text in (dump, caplog.text, res.text, dup.text, bad.text):
        assert IBAN_FLAT not in text and IBAN not in text and IBAN_FLAT.lower() not in text


async def test_accounts_named_by_a_rule_are_in_use(l2_world, app):
    w = l2_world
    async with api_client(app) as cl:
        used = await cl.delete(f"/api/accounts/{w.ids('accounts')['lmnp-hello']}")
        missing = await cl.delete("/api/accounts/acc_" + "0" * 26)
    assert used.status_code == 409 and used.json()["error"]["details"]["references"] == ["rules"]
    assert missing.status_code == 404


async def test_people_list_create_and_patch(l2_world, app):
    async with api_client(app) as cl:
        made = await cl.post(
            "/api/people", json={"displayName": "Léa Martin", "aliases": ["MME LEA MARTIN"]}
        )
        patched = await cl.patch(f"/api/people/{made.json()['id']}", json={"shortName": "Léa"})
        listed = (await cl.get("/api/people")).json()
        bad = await cl.post("/api/people", json={"displayName": "X", "key": "9x"})
    assert made.status_code == 201 and made.json()["key"] == "lea-martin"
    assert patched.json()["shortName"] == "Léa" and patched.json()["aliases"] == ["MME LEA MARTIN"]
    assert made.json()["id"] in [p["id"] for p in listed["items"]]
    assert bad.status_code == 422 and bad.json()["error"]["field"] == "key"


CATEGORY = {
    "id": "legal_notices",
    "labels": {"en": "Legal notices", "fr": "Annonces légales", "ro": "Anunțuri legale"},
    "icon": "tax",
    "modelDefinition": "Legal notices published about an entity.",
    "template": {
        "pathTemplate": "{entity}/Annonces/{year}",
        "fileTemplate": "{date:YYYY-MM-DD}_{counterparty}",
    },
}


async def test_categories_templates_and_subcategories(l2_world, app):
    w = l2_world
    studio = w.ids("entities")["studio"]
    async with api_client(app) as cl:
        made = await cl.post("/api/categories", json=CATEGORY)
        sub = await cl.post(
            "/api/categories/legal_notices/subcategories",
            json={"labels": {"en": "Notice", "fr": "Avis", "ro": "Aviz"}},
        )
        sub2 = await cl.patch(
            "/api/categories/legal_notices/subcategories/notice",
            json={"labels": {"en": "Notice", "fr": "Avis officiel", "ro": "Aviz"}},
        )
        override = await cl.put(
            f"/api/categories/legal_notices/templates/{studio}",
            json={"pathTemplate": "{entity}/Juridique/{fy}", "fileTemplate": "{date:YYYY}_{sub}"},
        )
        patched = await cl.patch("/api/categories/legal_notices", json={"icon": "invoice"})
        removed = await cl.delete(f"/api/categories/legal_notices/templates/{studio}")
        listed = (await cl.get("/api/categories")).json()
    assert (
        made.status_code == 201
        and made.json()["template"]["pathTemplate"] == "{entity}/Annonces/{year}"
    )
    assert sub.status_code == 201 and sub.json()["subcategories"][0]["key"] == "notice"
    assert sub2.json()["subcategories"][0]["labels"]["fr"] == "Avis officiel"
    assert override.json()["entityTemplates"] == [
        {
            "entityId": studio,
            "pathTemplate": "{entity}/Juridique/{fy}",
            "fileTemplate": "{date:YYYY}_{sub}",
        }
    ]
    assert patched.json()["icon"] == "invoice" and removed.json()["entityTemplates"] == []
    assert "legal_notices" in [c["id"] for c in listed["items"]]
    assert listed["documentCounts"]["legal_notices"] == 0


@pytest.mark.parametrize(
    ("body", "status", "code", "field"),
    [
        ({**CATEGORY, "labels": {"en": "x", "fr": "y"}}, 422, "invalid_value", "labels.ro"),
        ({**CATEGORY, "icon": "rocket"}, 422, "invalid_value", "icon"),
        ({**CATEGORY, "id": "Legal"}, 422, "invalid_value", "id"),
        ({**CATEGORY, "id": "insurance"}, 409, "conflict", "id"),
    ],
)
async def test_category_refusals(l2_world, app, body, status, code, field):
    async with api_client(app) as cl:
        res = await cl.post("/api/categories", json=body)
    assert res.status_code == status
    assert (res.json()["error"]["code"], res.json()["error"]["field"]) == (code, field)


async def test_a_template_with_a_stray_brace_is_422_with_the_offset(l2_world, app):
    before = sql("SELECT path_template FROM templates WHERE category_id = 'insurance'")
    async with api_client(app) as cl:
        patch = await cl.patch(
            "/api/categories/insurance",
            json={"template": {"pathTemplate": "{entity}/Assur}ances", "fileTemplate": "{date}"}},
        )
        post = await cl.post(
            "/api/categories",
            json={**CATEGORY, "template": {"pathTemplate": "{entity}", "fileTemplate": "{date"}},
        )
    err = patch.json()["error"]
    assert patch.status_code == 422 and err["code"] == "invalid_template"
    assert err["details"]["template"] == "path" and err["details"]["offset"] == 14
    assert post.json()["error"]["details"]["template"] == "file"
    assert sql("SELECT path_template FROM templates WHERE category_id = 'insurance'") == before


async def test_template_preview_renders_a_document_or_the_sample(l2_world, app):
    w = l2_world
    doc = w.doc(counterparty="unim", entity="cabinet", category="insurance")
    sql("UPDATE documents SET doc_date = '2025-11-03' WHERE id = %s", (doc,))
    pair = {"pathTemplate": "{entity}/Assurances/{counterparty}/{year}",
            "fileTemplate": "{date:YYYY-MM-DD}_{counterparty}"}  # fmt: skip
    async with api_client(app) as cl:
        on_doc = (await cl.post("/api/templates/preview", json={**pair, "documentId": doc})).json()
        sample = (await cl.post("/api/templates/preview", json=pair)).json()
        studio = (
            await cl.post(
                "/api/templates/preview", json={**pair, "entityId": w.ids("entities")["studio"]}
            )
        ).json()
        broken = await cl.post(
            "/api/templates/preview", json={**pair, "fileTemplate": "{date:YYYY-MM-DD"}
        )
    assert on_doc == {
        "path": ["Cabinet Marchand", "Assurances", "UNIM", "2025"],
        "fileName": "2025-11-03_UNIM.pdf", "error": None,
    }  # fmt: skip
    assert sample["path"] == ["Cabinet Marchand", "Assurances", "ACME", "2026"]
    assert sample["fileName"] == "2026-02-27_ACME.pdf"
    assert studio["path"][0] == "Studio Numérique"
    assert broken.status_code == 200 and broken.json()["error"]["template"] == "file"
    assert broken.json()["path"] == [] and broken.json()["fileName"] is None


async def test_counterparties_match_names_and_aliases_best_first(l2_world, app):
    async with api_client(app) as cl:
        agipi = (await cl.get("/api/counterparties", params={"q": "a.g.i.p.i"})).json()
        hello = (await cl.get("/api/counterparties", params={"q": "hello"})).json()
        everyone = (await cl.get("/api/counterparties", params={"limit": 3})).json()
    assert agipi[0]["key"] == "agipi" and set(agipi[0]) == {"id", "key", "name", "kind"}
    assert hello[0]["key"] == "hello-bank"
    assert len(everyone) == 3
