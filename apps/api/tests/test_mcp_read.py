from datetime import UTC, date, datetime, timedelta

import pytest

from mona import clock
from tests import rows
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("clean")

TODAY = clock.paris_today()


@pytest.fixture
def archive() -> dict[str, str]:
    """Filed documents across entities, plus review, processing and deleted ones."""
    d = rows.document
    return {
        "agipi_2025a": d(
            "AGIPI PER avis d'échéance",
            entity="personal",
            category="insurance",
            counterparty="agipi",
            doc_date=date(2025, 4, 14),
            amount=520.0,
        ),
        "agipi_2025b": d(
            "AGIPI PER avis d'échéance octobre",
            entity="personal",
            category="insurance",
            counterparty="agipi",
            doc_date=date(2025, 10, 14),
            amount=520.0,
        ),
        "agipi_2024": d(
            "AGIPI PER 2024",
            entity="personal",
            category="insurance",
            counterparty="agipi",
            doc_date=date(2024, 4, 14),
            amount=480.0,
        ),
        "opco": d(
            "OPCO EP contribution",
            entity="cabinet",
            category="payment_calls",
            counterparty="opco",
            doc_date=date(2025, 2, 1),
            amount=300.0,
            text="appel de contribution formation professionnelle",
        ),
        "hello": d(
            "Hello bank relevé juin",
            entity="lmnp",
            category="bank",
            counterparty="hello-bank",
            doc_date=date(2025, 6, 30),
        ),
        "talenz": d(
            "TALENZ bilan",
            entity="studio",
            category="annual_accounts",
            counterparty="talenz",
            doc_date=date(2025, 11, 15),
            amount=1800.0,
            fiscal_year=2026,
        ),
        "ron": d(
            "Factură RON",
            entity="cabinet",
            category="payment_calls",
            doc_date=date(2025, 5, 5),
            amount=250.0,
            currency="RON",
        ),
        "review": d(
            "Unknown letter", entity=None, category=None, status="review", reasons=("entity",)
        ),
        "unreadable": d(
            "scan.pdf", entity=None, category=None, status="unreadable", reasons=("unreadable",)
        ),
        "processing": d("In flight", entity=None, category=None, status="processing"),
        "deleted": d(
            "AGIPI deleted",
            entity="personal",
            category="insurance",
            counterparty="agipi",
            doc_date=date(2025, 1, 1),
            amount=999.0,
            deleted=True,
        ),
    }


def ids(res) -> set[str]:
    return {r["id"] for r in res.data["results"]}


# search_documents and sum_amounts filters (C4 §5.5)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"entity": "personal"}, {"agipi_2025a", "agipi_2025b", "agipi_2024"}),
        ({"entity": "Personnel"}, {"agipi_2025a", "agipi_2025b", "agipi_2024"}),
        ({"entity": "CABINET MARCHAND"}, {"opco", "ron"}),
        ({"entity": "Cabinet Marchand SELARL"}, {"opco", "ron"}),
        ({"entity": "Studio Numerique"}, {"talenz"}),
        ({"entity": "Cabinet Marchant SELARL"}, {"opco", "ron"}),
        ({"category": "insurance"}, {"agipi_2025a", "agipi_2025b", "agipi_2024"}),
        ({"category": "Asigurări"}, {"agipi_2025a", "agipi_2025b", "agipi_2024"}),
        ({"category": "banque"}, {"hello"}),
        ({"counterparty": "AGIPI"}, {"agipi_2025a", "agipi_2025b", "agipi_2024"}),
        ({"counterparty": "A.G.I.P.I."}, {"agipi_2025a", "agipi_2025b", "agipi_2024"}),
        ({"counterparty": "hello bank"}, {"hello"}),
        ({"counterparty": "Nobody"}, set()),
        ({"year": 2024}, {"agipi_2024"}),
        ({"fiscal_year": 2026}, {"talenz"}),
        ({"date_from": "2025-06-01", "date_to": "2025-10-14"}, {"hello", "agipi_2025b"}),
        ({"amount_min": 500, "amount_max": 520}, {"agipi_2025a", "agipi_2025b"}),
        ({"status": "review"}, {"review", "unreadable"}),
        ({"status": "filed", "entity": "lmnp"}, {"hello"}),
        ({"counterparty": "AGIPI", "year": 2025}, {"agipi_2025a", "agipi_2025b"}),
        ({"query": "formation"}, {"opco"}),
        ({"query": "echeance", "counterparty": "agipi"}, {"agipi_2025a", "agipi_2025b"}),
    ],
)
async def test_search_filters(archive, args, expected):
    res = await call("search_documents", args)
    assert not res.is_error, res.text
    assert ids(res) == {archive[k] for k in expected}
    assert res.data["total"] == len(expected)


async def test_search_never_returns_processing_or_deleted(archive):
    res = await call("search_documents", {"limit": 25})
    assert archive["processing"] not in ids(res) and archive["deleted"] not in ids(res)
    assert res.data["total"] == 9


async def test_search_orders_by_date_desc_without_a_query(archive):
    res = await call("search_documents", {"counterparty": "agipi"})
    assert [r["id"] for r in res.data["results"]] == [
        archive["agipi_2025b"],
        archive["agipi_2025a"],
        archive["agipi_2024"],
    ]
    first = res.data["results"][0]
    assert first["entity"] == {"key": "personal", "name": "Personnel"}
    assert first["category"] == {"id": "insurance", "label": "Insurance"}
    assert (first["counterparty"], first["amount"], first["currency"]) == ("AGIPI", 520.0, "EUR")
    assert first["date"] == "2025-10-14"


async def test_unknown_entity_lists_the_visible_entities(archive):
    res = await call("search_documents", {"entity": "Acme Holding"})
    err = res.data["error"]
    assert (err["code"], err["field"]) == ("invalid_argument", "entity")
    assert err["message"] == "Unknown entity 'Acme Holding'."
    assert {v["key"] for v in err["valid"]} == {"cabinet", "studio", "lmnp", "personal"}
    tg = await call("search_documents", {"entity": "Acme Holding"}, channel="telegram")
    assert {v["key"] for v in tg.data["error"]["valid"]} == {"cabinet", "studio", "lmnp"}


async def test_unknown_category_lists_the_categories(archive):
    res = await call("sum_amounts", {"category": "Utilities"})
    err = res.data["error"]
    assert (err["code"], err["field"]) == ("invalid_argument", "category")
    assert {"id": "bank", "label": "Bank"} in err["valid"]


async def test_sum_by_filters(archive):
    res = await call("sum_amounts", {"counterparty": "AGIPI", "year": 2025})
    assert res.data["count"] == 2 and res.data["totals"] == [{"currency": "EUR", "total": 1040.0}]
    assert res.data["document_ids"] == [archive["agipi_2025b"], archive["agipi_2025a"]]
    assert res.data["listed"] == 2 and res.data["excluded"] == []


async def test_sum_keeps_currencies_apart_and_lists_documents_without_amount(archive):
    res = await call("sum_amounts", {"date_from": "2025-01-01", "date_to": "2025-12-31"})
    assert res.data["totals"] == [
        {"currency": "EUR", "total": 3140.0},
        {"currency": "RON", "total": 250.0},
    ]
    assert res.data["excluded"] == [{"id": archive["hello"], "reason": "no_amount"}]
    assert res.data["count"] == 5


async def test_sum_by_ids_reports_unknown_ones(archive):
    missing = "doc_01m3sg44rengv1yevkp7ca1xg5"
    res = await call(
        "sum_amounts",
        {"document_ids": [archive["opco"], missing, archive["deleted"], archive["hello"]]},
    )
    assert res.data["totals"] == [{"currency": "EUR", "total": 300.0}]
    assert res.data["excluded"] == [
        {"id": missing, "reason": "not_found"},
        {"id": archive["deleted"], "reason": "not_found"},
        {"id": archive["hello"], "reason": "no_amount"},
    ]


@pytest.mark.parametrize(
    "args", [{}, {"document_ids": ["doc_01m3sg44rengv1yevkp7ca1xg5"], "year": 2025}]
)
async def test_sum_needs_exactly_ids_or_filters(archive, args):
    res = await call("sum_amounts", args)
    assert res.data["error"]["code"] == "invalid_argument"


async def test_sum_caps_its_lists():
    for i in range(30):
        rows.document(f"Facture {i}", counterparty="opco", amount=1.0)
    for i in range(12):
        rows.document(f"Sans montant {i}", counterparty="opco")
    res = await call("sum_amounts", {"counterparty": "opco"})
    assert res.data["count"] == 30 and res.data["totals"][0]["total"] == 30.0
    assert (len(res.data["document_ids"]), res.data["listed"]) == (25, 25)
    assert len(res.data["excluded"]) == 10


# get_document


async def test_get_document_facts(archive):
    ddl = rows.deadline(
        "AGIPI", date(2025, 10, 30), entity="personal", document_id=archive["agipi_2025b"]
    )
    res = await call("get_document", {"document_id": archive["agipi_2025b"]})
    d = res.data
    assert (d["id"], d["title"], d["status"]) == (
        archive["agipi_2025b"],
        "AGIPI PER avis d'échéance octobre",
        "filed",
    )
    assert d["entity"] == {"key": "personal", "name": "Personnel"}
    assert (d["counterparty"], d["amount"], d["currency"], d["fiscal_year"]) == (
        "AGIPI",
        520.0,
        "EUR",
        2025,
    )
    assert d["path"].startswith("Personnel/") and d["filed_by"] == "mona"
    assert d["deadline_ids"] == [ddl]
    assert d["filed_at"].endswith("Z")


async def test_get_document_of_a_deleted_document_is_not_found(archive):
    res = await call("get_document", {"document_id": archive["deleted"]})
    assert res.data["error"]["code"] == "not_found" and rows.card_rows() == []


# Cards (C4 §5.6)


@pytest.mark.parametrize(("n", "cards"), [(0, 0), (1, 1), (3, 3), (4, 0)])
async def test_search_cards_threshold(n, cards):
    docs = [rows.document(f"Facture {i}", counterparty="opco") for i in range(n)]
    res = await call("search_documents", {"counterparty": "opco"})
    written = rows.card_rows()
    assert len(written) == cards and res.data["card_refs"] == [r.id for r in written]
    assert all((r.tool, r.kind, r.channel) == ("search_documents", "doc", "web") for r in written)
    assert {r.subject["document_id"] for r in written} <= set(docs)
    assert [r.subject for r in written] == [{"document_id": r["id"]} for r in res.data["results"]][
        :cards
    ]


@pytest.mark.parametrize(("n", "cards"), [(1, 1), (5, 5), (6, 0)])
async def test_sum_cards_threshold(n, cards):
    for i in range(n):
        rows.document(f"Facture {i}", counterparty="opco", amount=10.0)
    res = await call("sum_amounts", {"counterparty": "opco"})
    written = rows.card_rows()
    assert len(written) == cards and res.data["card_refs"] == [r.id for r in written]
    assert all((r.tool, r.kind) == ("sum_amounts", "doc") for r in written)


@pytest.mark.parametrize(("n", "cards"), [(1, 1), (3, 3), (4, 0)])
async def test_review_queue_cards_threshold(n, cards):
    for i in range(n):
        rows.document(f"Letter {i}", entity=None, category=None, status="review", reasons=("low",))
    res = await call("list_review_queue")
    written = rows.card_rows()
    assert len(written) == cards and res.data["card_refs"] == [r.id for r in written]
    assert all((r.tool, r.kind) == ("list_review_queue", "doc") for r in written)


@pytest.mark.parametrize(("n", "cards"), [(1, 1), (5, 5), (6, 0)])
async def test_deadline_cards_threshold(n, cards):
    made = [rows.deadline(f"Due {i}", TODAY + timedelta(days=i), amount=5.0) for i in range(n)]
    res = await call("list_deadlines")
    written = rows.card_rows()
    assert len(written) == cards and res.data["card_refs"] == [r.id for r in written]
    assert [r.subject for r in written] == [{"deadline_id": d} for d in made][:cards]
    assert all((r.tool, r.kind) == ("list_deadlines", "deadline") for r in written)


async def test_get_document_writes_one_card(archive):
    res = await call("get_document", {"document_id": archive["opco"]})
    (row,) = rows.card_rows()
    assert res.data["card_refs"] == [row.id]
    assert (row.tool, row.kind, row.subject) == (
        "get_document",
        "doc",
        {"document_id": archive["opco"]},
    )


# list_review_queue and list_deadlines


async def test_review_queue_is_oldest_first_with_reasons(archive):
    later = rows.document(
        "Later", entity=None, category=None, status="review", reasons=("low", "conflict")
    )
    res = await call("list_review_queue")
    assert [i["document_id"] for i in res.data["items"]] == [
        archive["review"],
        archive["unreadable"],
        later,
    ]
    assert res.data["items"][2]["reasons"] == ["low", "conflict"]
    only = await call("list_review_queue", {"reason": "unreadable"})
    assert [i["document_id"] for i in only.data["items"]] == [archive["unreadable"]]


async def test_deadlines_window_overdue_entity_and_reminders(archive):
    overdue = rows.deadline("URSSAF late", TODAY - timedelta(days=3), amount=100.0)
    soon = rows.deadline("URSSAF soon", TODAY + timedelta(days=3), amount=1284.0)
    later = rows.deadline("Studio TVA", TODAY + timedelta(days=45), entity="studio")
    rows.deadline("Paid", TODAY + timedelta(days=1), status="done")
    rows.deadline(
        "Of a deleted doc",
        TODAY + timedelta(days=2),
        document_id=archive["deleted"],
        entity="personal",
    )
    rows.reminder(TODAY + timedelta(days=1), deadline_id=soon)
    res = await call("list_deadlines")
    items = res.data["items"]
    assert [i["deadline_id"] for i in items] == [overdue, soon]
    assert (items[0]["days_left"], items[1]["days_left"]) == (-3, 3)
    assert items[1]["reminder_on"] == (TODAY + timedelta(days=1)).isoformat()
    assert items[1]["entity"] == {"key": "cabinet", "name": "Cabinet Marchand SELARL"}
    no_overdue = await call("list_deadlines", {"include_overdue": False, "within_days": 60})
    assert [i["deadline_id"] for i in no_overdue.data["items"]] == [soon, later]
    studio = await call("list_deadlines", {"entity": "studio", "within_days": 60})
    assert [i["deadline_id"] for i in studio.data["items"]] == [later]


# get_brief (C4 §3.15, §5.14)


async def test_brief_facts(archive):
    old = datetime.now(UTC) - timedelta(days=3)
    rows.document("Old filing", filed_at=old)
    rows.deadline("URSSAF", TODAY + timedelta(days=2), amount=1284.0)
    rows.deadline("Far", TODAY + timedelta(days=20))
    reminded = rows.deadline("Assurance", TODAY + timedelta(days=5))
    rows.reminder(TODAY, deadline_id=reminded)
    rows.rule(
        "t-learned",
        [{"field": "counterparty", "op": "equals", "value": "OPCO"}],
        {"entity": "cabinet", "category": "payment_calls"},
    )
    pending = rows.interview(open_questions=3)
    res = await call("get_brief")
    b = res.data
    assert b["filed"]["count"] == 7
    assert {e["key"]: e["count"] for e in b["filed"]["by_entity"]} == {
        "personal": 3,
        "cabinet": 2,
        "lmnp": 1,
        "studio": 1,
    }
    assert b["needs_review"] == {"count": 2, "by_reason": {"entity": 1, "unreadable": 1}}
    assert [d["label"] for d in b["due_soon"]] == ["URSSAF", "Assurance"]
    assert b["reminders_today"][0]["label"] == "Assurance"
    assert [r["name"] for r in b["learned"]] == ["Rule t-learned"]
    assert b["pending_interview"] == {"interview_id": pending, "open_questions": 3}
    since = (datetime.now(UTC) - timedelta(days=4)).isoformat()
    wider = await call("get_brief", {"since": since})
    assert wider.data["filed"]["count"] == 8


async def test_brief_is_stateless(archive, monkeypatch):
    fixed = datetime.now(UTC)
    monkeypatch.setattr(clock, "now", lambda: fixed)

    def table_counts():
        tables = [
            r.tablename
            for r in rows.all_rows("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ]
        return {t: rows.one(f"SELECT count(*) AS n FROM {t}").n for t in tables}

    before = table_counts()
    first, second = await call("get_brief"), await call("get_brief")
    assert first.data == second.data and first.data["generated_at"] == second.data["generated_at"]
    assert first.data["filed"]["count"] == 7
    assert table_counts() == before


# Visibility on the Telegram channel (C4 §2.6, §5.7)


async def test_personal_documents_are_invisible_on_telegram(archive):
    personal = archive["agipi_2025a"]
    web = await call("get_document", {"document_id": personal}, channel="web")
    assert not web.is_error
    for channel in ("telegram", None):
        tg = await call("get_document", {"document_id": personal}, channel=channel)
        assert tg.data["error"]["code"] == "not_found"

    web = await call("search_documents", {"counterparty": "agipi"}, channel="web")
    tg = await call("search_documents", {"counterparty": "agipi"}, channel="telegram")
    assert (web.data["total"], tg.data["total"]) == (3, 0)
    everything = await call("search_documents", {"limit": 25}, channel="telegram")
    assert everything.data["total"] == 6

    web = await call("sum_amounts", {"year": 2025}, channel="web")
    tg = await call("sum_amounts", {"year": 2025}, channel="telegram")
    assert web.data["totals"][0]["total"] == 3140.0
    assert tg.data["totals"][0]["total"] == 2100.0
    ids_tg = await call("sum_amounts", {"document_ids": [personal]}, channel="telegram")
    assert ids_tg.data["excluded"] == [{"id": personal, "reason": "not_found"}]
    entity = await call("sum_amounts", {"entity": "personal"}, channel="telegram")
    assert entity.data["error"]["code"] == "invalid_argument"


async def test_personal_deadlines_and_brief_facts_are_invisible_on_telegram(archive):
    rows.deadline("AGIPI PER due", TODAY + timedelta(days=2), entity="personal", amount=520.0)
    rows.deadline("URSSAF due", TODAY + timedelta(days=3), entity="cabinet", amount=1284.0)
    rows.rule(
        "t-person",
        [{"field": "person", "op": "mentions", "value": "paul"}],
        {"entity": "cabinet", "category": "payment_calls"},
    )
    rows.rule(
        "t-account",
        [{"field": "iban", "op": "account", "value": "lmnp-hello"}],
        {"entity": "cabinet", "category": "bank"},
    )
    rows.rule(
        "t-entity-cond",
        [{"field": "entity", "op": "in", "value": ["studio", "personal"]}],
        {"entity": "studio", "category": "tax"},
    )
    rows.rule(
        "t-personal-action",
        [{"field": "counterparty", "op": "equals", "value": "OXYLEO"}],
        {"entity": "personal", "category": "tax"},
    )
    rows.rule(
        "t-plain",
        [{"field": "counterparty", "op": "equals", "value": "OPCO"}],
        {"entity": "cabinet", "category": "payment_calls"},
    )

    web_dl = await call("list_deadlines", channel="web")
    tg_dl = await call("list_deadlines", channel="telegram")
    assert [i["label"] for i in web_dl.data["items"]] == ["AGIPI PER due", "URSSAF due"]
    assert [i["label"] for i in tg_dl.data["items"]] == ["URSSAF due"]

    web, tg = await call("get_brief", channel="web"), await call("get_brief", channel="telegram")
    assert web.data["filed"]["count"] == 7 and tg.data["filed"]["count"] == 4
    assert "personal" not in {e["key"] for e in tg.data["filed"]["by_entity"]}
    assert [d["label"] for d in tg.data["due_soon"]] == ["URSSAF due"]
    assert {r["name"] for r in web.data["learned"]} == {
        "Rule t-person",
        "Rule t-account",
        "Rule t-entity-cond",
        "Rule t-personal-action",
        "Rule t-plain",
    }
    assert {r["name"] for r in tg.data["learned"]} == {"Rule t-account", "Rule t-plain"}
    assert "AGIPI" not in tg.text and "Personnel" not in tg.text and "520" not in tg.text


async def test_seeded_personal_rule_names_are_hidden_on_telegram():
    with rows.connect() as conn:
        conn.execute("UPDATE rules SET created_at = now() WHERE key = 'agipi-per-by-person'")
        conn.execute("UPDATE rules SET created_at = now() WHERE key = 'hello-bank-lmnp'")
    web, tg = await call("get_brief", channel="web"), await call("get_brief", channel="telegram")
    assert {r["name"] for r in web.data["learned"]} == {
        "AGIPI PER, filed under the insured person",
        "Hello bank statements for the LMNP account",
    }
    assert {r["name"] for r in tg.data["learned"]} == {"Hello bank statements for the LMNP account"}


async def test_review_suggestions_of_personal_entities_are_hidden_on_telegram():
    doc = rows.document(
        "Letter", entity="personal", category=None, status="review", reasons=("low",)
    )
    web = await call("list_review_queue", channel="web")
    tg = await call("list_review_queue", channel="telegram")
    assert [i["document_id"] for i in web.data["items"]] == [doc]
    assert tg.data["items"] == [] and tg.data["total"] == 0
