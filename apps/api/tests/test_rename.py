"""`rename_documents` (C4 §3.18, A62 item 1) over the seeded registry, fictional documents only."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select, update

from mona.rules import store
from mona.services import ServiceError, apply_rule, correct_document, file_document, preview_rule
from mona.services import undo as undo_service
from mona.services.registry import T
from mona.services.rename import rename_documents
from tests.services_world import ARRIVED, IBAN_SPACED, Services
from tests.test_services import classify

FOLDER = "LMNP/Angers-Strasbourg/Banque/2026"
MONTHS = [(1, 16), (2, 16), (3, 5), (3, 20), (4, 16), (5, 16)]
NAMES = ["2026-01-HB-LMNP-Janvier", "2026-02-HB-LMNP-Fevrier", "2026-03-HB-LMNP-Mars",
         "2026-03-HB-LMNP-Mars-2", "2026-04-HB-LMNP-Avril", "2026-05-HB-LMNP-Mai"]  # fmt: skip
EXAMPLE = "2026-01 HB LMNP Janvier.pdf"


@pytest.fixture
def s(seeded_engine, tmp_path) -> Services:
    return Services(seeded_engine, tmp_path / "data")


def statement(s: Services, m: int, day: int, n: int, **kw) -> str:
    values = dict(
        counterparty="hello-bank", category="bank", subcategory="releve", entity="lmnp",
        text=f"Relevé de compte {IBAN_SPACED}", doc_date=date(2026, m, day),
        arrived_at=ARRIVED + timedelta(minutes=n),
    )  # fmt: skip
    return s.doc(**{**values, **kw})


def six_statements(s: Services) -> list[str]:
    """Filed by the IBAN-routed Hello bank rule, as the seed files them."""
    docs = [statement(s, m, day, i) for i, (m, day) in enumerate(MONTHS)]
    out = apply_rule(s.ctx, s.rule_id("hello-bank-lmnp"), actor="mona", via="chat")
    assert out.moved == 6
    return docs


def model_filed(s: Services, path: str, **kw) -> str:
    doc = s.doc(status="processing", **kw)
    classify(s, doc, path)
    file_document(s.ctx, doc)
    return doc


def other_entity(s: Services) -> str:
    return model_filed(
        s, "Cabinet Marchand/Banque/2026/2026-02-10_Hello-bank_Releve-de-compte.pdf",
        counterparty="hello-bank", category="bank", subcategory="releve", entity="cabinet",
        doc_date=date(2026, 2, 10), arrived_at=ARRIVED + timedelta(minutes=30),
    )  # fmt: skip


def names(s: Services, docs: list[str]) -> list[str]:
    return [s.row(d)["current_path"] for d in docs]


def rules_count(s: Services) -> tuple[int, int]:
    f = T["file_ops"]
    with s.engine.connect() as conn:
        n = conn.execute(select(func.count()).select_from(T["rules"])).scalar()
        created = conn.execute(
            select(func.count()).select_from(f).where(f.c.action == "rule.create")
        ).scalar()
    return n, created


def rename(s: Services, doc: str, **kw):
    return rename_documents(s.ctx, doc, actor="mona", via="chat", **kw)


def test_six_statements_filed_by_the_iban_rule_are_renamed_applied_undone_and_redone(s):
    docs = six_statements(s)
    other_entity(s)
    before = names(s, docs)
    hello = store.rule_row(s.engine.connect(), s.rule_id("hello-bank-lmnp"))
    out = rename(s, docs[0], example=EXAMPLE)
    assert out.pattern == "{date:YYYY-MM}-HB-{entity}-{date:MMMM}"
    assert out.renames_total == 6 and out.renames[0]["document_id"] == docs[0]
    expected = {d: f"{n}.pdf" for d, n in zip(docs, NAMES, strict=True)}
    assert {r["document_id"]: r["to_name"] for r in out.renames} == expected
    assert out.renames[0]["from_name"] == "2026-01-16_Hello-bank_Releve-de-compte.pdf"
    assert out.collisions == [{"to_name": "2026-03-HB-LMNP-Mars.pdf", "count": 2}]
    assert (out.not_covered, out.date_fallbacks) == (1, 0)

    with s.engine.connect() as conn:
        rule = store.rule_row(conn, out.rule_id)
    assert (rule["state"], rule["source"], rule["origin_document_id"]) == (
        "draft", "correction", docs[0]
    )  # fmt: skip
    assert rule["conditions"] == hello["conditions"]
    assert rule["action"] == {**hello["action"], "filename": out.pattern}
    assert rule["priority"] == hello["priority"] + 1
    assert rule["name"] == "Rename Hello bank Bank"
    counted = rules_count(s)
    assert rename(s, docs[0], example=EXAMPLE).rule_id == out.rule_id
    assert rules_count(s) == counted

    p = preview_rule(s.ctx, out.rule_id)
    assert {m.document_id: m.to_file_name for m in p.moves} == expected
    assert all("/".join(m.to) == FOLDER for m in p.moves)

    applied = apply_rule(s.ctx, out.rule_id, actor="mona", via="chat")
    assert (applied.moved, applied.failed) == (6, [])
    assert names(s, docs) == [f"{FOLDER}/{n}.pdf" for n in NAMES]
    f = T["file_ops"]
    with s.engine.connect() as conn:
        actions = conn.execute(
            select(f.c.action).where(f.c.group_id == applied.group_id, f.c.document_id.isnot(None))
        ).scalars()
        assert set(actions) == {"rename"}

    undone = undo_service(s.ctx, actor="mona", via="chat", group_id=applied.group_id)
    assert names(s, docs) == before
    assert undone.rule_states == [{"rule_id": out.rule_id, "state": "draft"}]
    redone = undo_service(s.ctx, actor="mona", via="chat", group_id=undone.group_id)
    assert names(s, docs) == [f"{FOLDER}/{n}.pdf" for n in NAMES]
    assert redone.rule_states == [{"rule_id": out.rule_id, "state": "active"}]


def test_a_statement_corrected_to_another_entity_would_refile(s):
    docs = six_statements(s)
    correct_document(s.ctx, docs[2], actor="mona", via="chat", entity="cabinet")
    counted = rules_count(s)
    with pytest.raises(ServiceError) as e:
        rename(s, docs[0], example=EXAMPLE)
    assert (e.value.code, e.value.hint) == ("conflict", "would_refile")
    assert rules_count(s) == counted


def test_a_statement_waiting_in_review_refuses(s):
    docs = six_statements(s)
    statement(s, 6, 16, 10)
    with pytest.raises(ServiceError) as e:
        rename(s, docs[0], example=EXAMPLE)
    assert (e.value.code, e.value.hint) == ("conflict", "in_review")
    with pytest.raises(ServiceError) as e:
        rename(s, statement(s, 7, 16, 11), example="2026-07-HB")
    assert (e.value.code, e.value.hint) == ("conflict", "in_review")


def test_refusal_counts_only_documents_the_channel_may_see(s):
    docs = six_statements(s)
    for d in docs[2:4]:
        correct_document(s.ctx, d, actor="mona", via="chat", entity="cabinet")
    hidden: set[str] = {docs[2]}
    with pytest.raises(ServiceError) as e:
        rename(s, docs[0], example=EXAMPLE, visible=lambda r: r["id"] not in hidden)
    assert "move 1 document(s)" in e.value.message
    hidden.add(docs[3])
    with pytest.raises(ServiceError) as e:
        rename(s, docs[0], example=EXAMPLE, visible=lambda r: r["id"] not in hidden)
    assert e.value.hint == "would_refile" and "move some documents" in e.value.message
    assert not any(ch.isdigit() for ch in e.value.message)


def test_an_in_review_refusal_counts_only_visible_documents(s):
    docs = six_statements(s)
    waiting = statement(s, 6, 16, 10)
    with pytest.raises(ServiceError) as e:
        rename(s, docs[0], example=EXAMPLE)
    assert e.value.message.startswith("1 of these document(s) are waiting")
    with pytest.raises(ServiceError) as e:
        rename(s, docs[0], example=EXAMPLE, visible=lambda r: r["id"] != waiting)
    assert e.value.hint == "in_review"
    assert e.value.message.startswith("Some of these documents are waiting")
    assert not any(ch.isdigit() for ch in e.value.message)


def test_a_statement_filed_under_an_older_template_would_refile(s):
    t = T["templates"]
    with s.engine.begin() as conn:
        conn.execute(
            update(t)
            .where(t.c.category_id == "bank", t.c.entity_id.is_(None))
            .values(path_template="{entity}/Banque/Relevés/{fy}")
        )
    old = statement(s, 1, 2, 0)
    apply_rule(s.ctx, s.rule_id("hello-bank-lmnp"), actor="mona", via="chat")
    assert s.row(old)["current_path"].startswith("LMNP/Angers-Strasbourg/Banque/Relevés/2026/")
    with s.engine.begin() as conn:
        conn.execute(
            update(t)
            .where(t.c.category_id == "bank", t.c.entity_id.is_(None))
            .values(path_template="{entity}/Banque/{fy}")
        )
    unit = s.ids("sub_units")["angers-strasbourg"]
    for i, (m, day) in enumerate(MONTHS):
        d = statement(s, m, day, i + 1, status="processing", sub_unit_id=unit)
        classify(s, d, f"{FOLDER}/{d}.pdf", rule=s.rule_id("hello-bank-lmnp"))
        file_document(s.ctx, d)
    with pytest.raises(ServiceError) as e:
        rename(s, d, example="2026-05-16_HB-LMNP")
    assert (e.value.code, e.value.hint) == ("conflict", "would_refile")
    assert "move 1 document(s)" in e.value.message


UNIM = "Cabinet Marchand/Assurances/UNIM/Prévoyance/2025"


def unim(s: Services, d: date, n: int, **kw) -> str:
    values = dict(
        counterparty="unim", category="insurance", subcategory="prevoyance", entity="cabinet",
        doc_date=d, arrived_at=ARRIVED + timedelta(minutes=n),
    )  # fmt: skip
    return model_filed(s, f"{UNIM}/{d.isoformat()}_UNIM_Prevoyance.pdf", **{**values, **kw})


def test_a_model_filed_document_gets_subject_value_conditions(s):
    docs = [unim(s, date(2025, m, 3), m) for m in (3, 6, 11)]
    out = rename(s, docs[2], example="2025-11_UNIM_Contrat")
    assert out.pattern == "{date:YYYY-MM}_{counterparty}_Contrat"
    assert [r["to_name"] for r in out.renames] == [
        "2025-11_UNIM_Contrat.pdf", "2025-03_UNIM_Contrat.pdf", "2025-06_UNIM_Contrat.pdf"
    ]  # fmt: skip
    with s.engine.connect() as conn:
        rule = store.rule_row(conn, out.rule_id)
    assert rule["conditions"] == [
        {"field": "counterparty", "op": "equals", "value": "unim"},
        {"field": "entity", "op": "equals", "value": "cabinet"},
        {"field": "category", "op": "equals", "value": "insurance"},
    ]
    assert rule["action"] == {
        "entity": "cabinet", "category": "insurance", "subcategory": "prevoyance",
        "filename": "{date:YYYY-MM}_{counterparty}_Contrat",
    }  # fmt: skip
    assert rule["priority"] == 30 and rule["name"] == "Rename UNIM Insurance"
    applied = apply_rule(s.ctx, out.rule_id, actor="mona", via="chat")
    assert (
        applied.moved == 3 and s.row(docs[0])["current_path"] == f"{UNIM}/2025-03_UNIM_Contrat.pdf"
    )


def test_a_model_filed_document_filed_elsewhere_than_read_would_refile(s):
    doc = unim(s, date(2025, 3, 3), 1)
    correct_document(s.ctx, doc, actor="mona", via="chat", subcategory=None, entity="studio")
    with pytest.raises(ServiceError) as e:
        rename(s, doc, example="2025-03_UNIM")
    assert (e.value.code, e.value.hint) == ("conflict", "would_refile")


@pytest.mark.parametrize(
    ("kw", "field", "hint"),
    [
        ({"example": "UNIM 2025-03"}, "example", None),
        ({"example": "2025-03_UNIM_Avril"}, "example", "{date:MMMM}"),
        ({"pattern": "{date:MM}_UNIM_2025"}, "pattern", "{date:YYYY}"),
        ({"pattern": "{date:YYYY}_Juin"}, "pattern", "{date:MMMM}"),
        ({"example": "2025-03_" + "-".join(["Contrat"] * 20)}, "example", "2025-03_Contrat"),
        ({"pattern": "{date:YYYY}_{nope}"}, "pattern", "offset 12"),
        ({}, "example", None),
        ({"example": "2025-03", "pattern": "{date:YYYY}"}, "example", None),
    ],
)
def test_invalid_arguments_write_nothing(s, kw, field, hint):
    doc = unim(s, date(2025, 3, 3), 1)
    counted = rules_count(s)
    with pytest.raises(ServiceError) as e:
        rename(s, doc, **kw)
    assert (e.value.code, e.value.field) == ("invalid_argument", field)
    if hint is not None:
        assert e.value.hint is not None and e.value.hint.startswith(hint)
    if field == "pattern" and "nope" in kw.get("pattern", ""):
        assert "{date:MMMM}" in e.value.valid
    assert rules_count(s) == counted


def test_a_pattern_is_taken_as_given(s):
    doc = unim(s, date(2025, 3, 3), 1)
    out = rename(s, doc, pattern="{date:YYYY}-{date:MMMM}_{counterparty}")
    assert out.renames[0]["to_name"] == "2025-Mars_UNIM.pdf"


def test_no_counterparty_visitors_and_unknown_documents(s):
    bare = model_filed(
        s, "Cabinet Marchand/Assurances/2025/2025-01-02.pdf", category="insurance",
        entity="cabinet", doc_date=date(2025, 1, 2),
    )  # fmt: skip
    with pytest.raises(ServiceError) as e:
        rename(s, bare, example="2025-01-02_x")
    assert (e.value.code, e.value.field) == ("invalid_argument", "document_id")
    visitor = s.doc(counterparty="unim", batch=s.new_batch(visitor=True), doc_date=date(2025, 1, 2))
    with pytest.raises(ServiceError) as e:
        rename(s, visitor, example="2025-01-02_x")
    assert e.value.code == "not_allowed"
    with pytest.raises(ServiceError) as e:
        rename(s, "doc_01m3sg44rengv1yevkp7ca1xg5", example="2025-01-02_x")
    assert e.value.code == "not_found"


def test_names_that_used_the_arrival_date_are_counted(s):
    doc = unim(s, date(2025, 3, 3), 1)
    unim(s, date(2025, 6, 3), 2, doc_date=None, arrived_at=ARRIVED.replace(year=2025, month=6))
    out = rename(s, doc, example="2025-03_UNIM")
    assert out.date_fallbacks == 1
    assert sorted(r["to_name"] for r in out.renames) == ["2025-03_UNIM.pdf", "2025-06_UNIM.pdf"]
