from datetime import date
from decimal import Decimal

import pytest

from mona.rules.engine import Subject, evaluate, holds, learned_priority, siren_candidates
from mona.rules.grammar import Condition
from mona.templates import render
from tests.rules_world import (
    IBAN,
    IBAN_BAD,
    IBAN_SPACED,
    STUDIO_SIREN,
    WORLD,
    render_values,
    rule,
    siret_of,
)

W = WORLD
_GOOD = siret_of(STUDIO_SIREN)
BAD_SIRET = _GOOD[:-1] + str((int(_GOOD[-1]) + 1) % 10)


def S(**kw) -> Subject:
    return Subject(**kw)


# (condition, a subject where it holds, a subject where it doesn't) — one row per (field, op).
ROWS = [
    ({"field": "counterparty", "op": "equals", "value": "AGIPI"},
     S(counterparty="agipi"), S(counterparty="unim")),
    ({"field": "counterparty", "op": "equals", "value": "agipi assurance"},
     S(counterparty="agipi"), S(counterparty="talenz")),
    ({"field": "counterparty", "op": "equals", "value": "hello-bank"},
     S(counterparty="hello-bank"), S(counterparty="agipi")),
    ({"field": "counterparty", "op": "in", "value": ["UNIM", "Talenz"]},
     S(counterparty="talenz"), S(counterparty="agipi")),
    ({"field": "counterparty", "op": "contains", "value": "hello"},
     S(counterparty="hello-bank"), S(counterparty="opco")),
    ({"field": "text", "op": "contains", "value": "Plan d’Épargne"},
     S(text="votre plan d'épargne retraite"), S(text="assurance vie")),
    ({"field": "text", "op": "contains_any", "value": ["assurance vie", "PER"]},
     S(text="Votre PER."), S(text="PERSONNEL")),
    ({"field": "text", "op": "contains_all", "value": ["bilan", "2025"]},
     S(text="Bilan au 31/12/2025"), S(text="Bilan 2024")),
    ({"field": "doc_type", "op": "equals", "value": "Avis d'échéance"},
     S(doc_type="AVIS D’ECHEANCE"), S(doc_type="avis")),
    ({"field": "doc_type", "op": "in", "value": ["relevé", "Relevé de compte"]},
     S(doc_type="releve de compte"), S(doc_type="relevé de frais")),
    ({"field": "doc_type", "op": "contains", "value": "relevé"},
     S(doc_type="Relevé de frais"), S(doc_type="relevés")),
    ({"field": "category", "op": "equals", "value": "bank"},
     S(category="bank"), S(category="insurance")),
    ({"field": "category", "op": "in", "value": ["bank", "tax"]},
     S(category="tax"), S(category="unknown")),
    ({"field": "entity", "op": "equals", "value": "cabinet"},
     S(entity="cabinet"), S(entity="studio")),
    ({"field": "entity", "op": "in", "value": ["cabinet", "lmnp"]},
     S(entity="lmnp"), S(entity="personal")),
    ({"field": "addressee", "op": "contains", "value": "Marchand"},
     S(addressee="M. PAUL MARCHAND"), S(addressee="M. Paul Marchandise")),
    ({"field": "addressee", "op": "is_person", "value": "paul"},
     S(addressee="à l'attention de M. Paul Marchand"), S(addressee="Mme Anna Marchand")),
    ({"field": "addressee", "op": "is_entity", "value": "cabinet"},
     S(addressee="SELARL CABINET MARCHAND"), S(addressee="Studio Numérique")),
    ({"field": "person", "op": "mentions", "value": "anna"},
     S(text="Assurée : Marchand Anna"), S(text="Assuré : Paul Marchand")),
    ({"field": "iban", "op": "account", "value": "lmnp-hello"},
     S(text=f"IBAN : {IBAN_SPACED}"), S(text=f"IBAN : {IBAN_BAD}")),
    ({"field": "iban", "op": "entity", "value": "lmnp"},
     S(text=f"iban {IBAN.lower()} x {IBAN}"), S(text="no account here")),
    ({"field": "siren", "op": "equals", "value": STUDIO_SIREN},
     S(text="SIREN 888 888 880"), S(text="SIREN 888 888 881")),
    ({"field": "siren", "op": "in", "value": ["123456782", STUDIO_SIREN]},
     S(text="RCS 888.888.880"), S(text="RCS 123456789")),
    ({"field": "siren", "op": "entity", "value": "studio"},
     S(text=f"SIRET {siret_of(STUDIO_SIREN)}"), S(text=f"SIRET {BAD_SIRET}")),
    ({"field": "amount", "op": "gt", "value": 100},
     S(amount=Decimal("100.01")), S(amount=Decimal("100.00"))),
    ({"field": "amount", "op": "gte", "value": 100},
     S(amount=Decimal("100.00")), S(amount=Decimal("99.99"))),
    ({"field": "amount", "op": "lt", "value": 100},
     S(amount=Decimal("99.99")), S(amount=Decimal("100"))),
    ({"field": "amount", "op": "lte", "value": 100},
     S(amount=Decimal("100")), S(amount=Decimal("100.01"))),
    ({"field": "amount", "op": "between", "value": [10, 20.5]},
     S(amount=Decimal("20.50")), S(amount=Decimal("20.51"))),
]  # fmt: skip


def _id(row) -> str:
    c = row[0]
    return f"{c['field']}-{c['op']}-{c['value']}"


def test_every_field_op_is_covered():
    from mona.rules.grammar import OPS

    covered = {(r[0]["field"], r[0]["op"]) for r in ROWS}
    assert covered == {(f, op) for f, ops in OPS.items() for op in ops}


@pytest.mark.parametrize("row", ROWS, ids=[_id(r) for r in ROWS])
@pytest.mark.parametrize("negate", [False, True])
def test_condition_both_polarities(row, negate):
    cond, yes, no = row
    c = Condition.model_validate({**cond, "negate": negate})
    assert holds(c, yes, W) is not negate
    assert holds(c, no, W) is negate


@pytest.mark.parametrize(
    "cond",
    [
        {"field": "counterparty", "op": "equals", "value": "AGIPI"},
        {"field": "addressee", "op": "contains", "value": "Paul"},
        {"field": "addressee", "op": "is_person", "value": "paul"},
        {"field": "amount", "op": "gt", "value": 0},
        {"field": "doc_type", "op": "equals", "value": "avis"},
        {"field": "category", "op": "equals", "value": "bank"},
        {"field": "entity", "op": "equals", "value": "cabinet"},
    ],
)
def test_missing_subject_is_false_and_negated_true(cond):
    assert holds(Condition.model_validate(cond), S(), W) is False
    assert holds(Condition.model_validate({**cond, "negate": True}), S(), W) is True


def test_unknown_category_is_a_missing_subject():
    c = Condition(field="category", op="equals", value="unknown")
    assert holds(c, S(category="unknown"), W) is False


def test_dangling_reference_is_false_even_negated():
    for negate in (False, True):
        c = Condition(field="person", op="mentions", value="ghost", negate=negate)
        assert holds(c, S(text="ghost"), W) is False


def test_whole_word_match():
    c = Condition(field="text", op="contains", value="OPCO")
    assert holds(c, S(text="Appel OPCO 2025"), W)
    assert not holds(c, S(text="OPCOMMERCE"), W)
    assert holds(
        Condition(field="counterparty", op="contains", value="bank"),
        S(counterparty="hello-bank"),
        W,
    )


def test_iban_with_a_bad_checksum_is_ignored():
    c = Condition(field="iban", op="account", value="lmnp-hello")
    assert not holds(c, S(text=IBAN_BAD), W)
    assert holds(c, S(text=IBAN), W)


def test_siren_via_siret():
    siret = siret_of(STUDIO_SIREN)
    assert STUDIO_SIREN in siren_candidates(f"SIRET : {siret}")
    spaced = f"{siret[:3]} {siret[3:6]} {siret[6:9]} {siret[9:]}"
    assert STUDIO_SIREN in siren_candidates(spaced)
    assert siren_candidates(f"SIRET {BAD_SIRET}") == set()


PER_BY_PERSON = rule(
    "rul_per",
    [{"field": "counterparty", "op": "equals", "value": "AGIPI"}],
    {"entity": "personal", "unit": {"from": "person"}, "category": "insurance",
     "subcategory": "per"},
)  # fmt: skip


def test_unit_from_person_via_addressee():
    s = S(counterparty="agipi", addressee_person="paul", text="Anna Marchand et Paul Marchand")
    out = evaluate([PER_BY_PERSON], s, W)
    assert out.destination.unit == "paul" and not out.destination.unit_unresolved


def test_unit_from_person_via_a_single_mention():
    s = S(counterparty="agipi", text="Assurée : Mme Anna Marchand")
    assert evaluate([PER_BY_PERSON], s, W).destination.unit == "anna"


def test_unit_from_person_unresolved_with_two_mentions():
    s = S(counterparty="agipi", text="Anna Marchand, Paul Marchand")
    d = evaluate([PER_BY_PERSON], s, W).destination
    assert d.unit is None and d.unit_unresolved


def test_rule_without_unit_gives_no_sub_unit_even_with_an_addressee():
    oxyleo = rule(
        "rul_ox",
        [{"field": "counterparty", "op": "equals", "value": "OXYLEO"}],
        {"entity": "personal", "category": "tax"},
    )
    s = S(
        counterparty="oxyleo",
        addressee="M. Paul Marchand",
        addressee_person="paul",
        text="M. Paul Marchand",
        subcategory="preparation",
        category="tax",
    )
    d = evaluate([oxyleo], s, W).destination
    assert d.unit is None and not d.unit_unresolved
    out = render(
        d.path_template,
        d.file_template,
        render_values(d, s, counterparty_name="OXYLEO", doc_date=date(2026, 5, 12)),
    )
    assert out.path == "Personnel/Impôts et taxes/2026/2026-05-12_OXYLEO_Elements-preparatoires.pdf"


def test_action_fallbacks_use_the_model_values():
    r = rule(
        "rul_a", [{"field": "counterparty", "op": "equals", "value": "UNIM"}], {"entity": "cabinet"}
    )
    d = evaluate(
        [r],
        S(counterparty="unim", category="insurance", subcategory="prevoyance", entity="personal"),
        W,
    ).destination
    assert (d.entity, d.category, d.subcategory) == ("cabinet", "insurance", "prevoyance")
    r2 = rule(
        "rul_b",
        [{"field": "counterparty", "op": "equals", "value": "UNIM"}],
        {"entity": "cabinet", "category": "bank"},
    )
    d2 = evaluate(
        [r2], S(counterparty="unim", category="insurance", subcategory="prevoyance"), W
    ).destination
    assert (d2.category, d2.subcategory) == ("bank", None)


def test_priority_winner():
    low = rule(
        "rul_low",
        [{"field": "counterparty", "op": "equals", "value": "AGIPI"}],
        {"entity": "cabinet", "category": "insurance"},
        10,
    )
    high = rule(
        "rul_high",
        [{"field": "text", "op": "contains", "value": "PER"}],
        {"entity": "personal", "category": "insurance"},
        30,
        created=5,
    )
    out = evaluate([low, high], S(counterparty="agipi", text="PER"), W)
    assert out.winner.id == "rul_high" and out.destination.entity == "personal"
    assert out.matched == ("rul_low", "rul_high")


def test_equal_destinations_tie_goes_to_the_oldest_rule():
    a = rule(
        "rul_b",
        [{"field": "counterparty", "op": "equals", "value": "UNIM"}],
        {"entity": "cabinet", "category": "insurance"},
        created=3,
    )
    b = rule(
        "rul_a",
        [{"field": "text", "op": "contains", "value": "prévoyance"}],
        {"entity": "cabinet", "category": "insurance"},
        created=1,
    )
    c = rule(
        "rul_c",
        [{"field": "text", "op": "contains", "value": "prévoyance"}],
        {"entity": "cabinet", "category": "insurance"},
        created=1,
    )
    out = evaluate([a, c, b], S(counterparty="unim", text="prevoyance"), W)
    assert out.winner.id == "rul_a" and not out.conflict


def test_conflict_lists_both_ids_and_has_no_winner():
    a = rule(
        "rul_1",
        [{"field": "counterparty", "op": "equals", "value": "AGIPI"}],
        {"entity": "cabinet", "category": "insurance"},
    )
    b = rule(
        "rul_2",
        [{"field": "text", "op": "contains", "value": "PER"}],
        {"entity": "personal", "category": "insurance"},
    )
    low = rule(
        "rul_3",
        [{"field": "text", "op": "contains", "value": "PER"}],
        {"entity": "lmnp", "category": "bank"},
        5,
    )
    out = evaluate([a, b, low], S(counterparty="agipi", text="PER"), W)
    assert out.winner is None and out.destination is None
    assert out.conflict and set(out.conflicting) == {"rul_1", "rul_2"}


def test_correction_rule_outranks_the_seed_rule_it_corrects():
    seed = rule(
        "rul_seed",
        [{"field": "counterparty", "op": "equals", "value": "UNIM"}],
        {"entity": "personal", "category": "insurance"},
        10,
    )
    s = S(counterparty="unim")
    p = learned_priority(1, [r.priority for r in [seed] if r.matches(s, W)])
    assert p == 11
    learned = rule(
        "rul_learned",
        [{"field": "counterparty", "op": "equals", "value": "UNIM"}],
        {"entity": "cabinet", "category": "insurance"},
        p,
        created=9,
    )
    out = evaluate([seed, learned], s, W)
    assert out.winner.id == "rul_learned" and out.destination.entity == "cabinet"
    assert learned_priority(3, [11]) == 30 and learned_priority(2, []) == 20


def test_as_active_treats_a_draft_as_active():
    draft = rule(
        "rul_d",
        [{"field": "counterparty", "op": "equals", "value": "UNIM"}],
        {"entity": "cabinet", "category": "insurance"},
        state="draft",
    )
    assert evaluate([draft], S(counterparty="unim"), W).winner is None
    assert evaluate([draft], S(counterparty="unim"), W, as_active="rul_d").winner.id == "rul_d"


# C5 §8.5 cases 1a, 1b, 2, 3 and 5 through the engine and the renderer.
AGIPI_PER = rule(
    "rul_agipi_per",
    [{"field": "counterparty", "op": "equals", "value": "AGIPI"},
     {"field": "text", "op": "contains_any", "value": ["plan d'épargne retraite", "PER"]}],
    {"entity": "personal", "unit": {"from": "person"}, "category": "insurance",
     "subcategory": "per"},
)  # fmt: skip
AGIPI_AV = rule(
    "rul_agipi_av",
    [{"field": "counterparty", "op": "equals", "value": "AGIPI"},
     {"field": "text", "op": "contains_any", "value": ["assurance vie", "situation annuelle"]}],
    {"entity": "personal", "unit": {"from": "person"}, "category": "insurance",
     "subcategory": "assurance_vie"},
)  # fmt: skip
HELLO = rule(
    "rul_hello",
    [{"field": "counterparty", "op": "equals", "value": "Hello bank"},
     {"field": "iban", "op": "account", "value": "lmnp-hello"}],
    {"entity": "lmnp", "unit": "angers-strasbourg", "category": "bank"},
)  # fmt: skip
TALENZ = rule(
    "rul_talenz",
    [{"field": "counterparty", "op": "equals", "value": "TALENZ"},
     {"field": "siren", "op": "entity", "value": "studio"}],
    {"entity": "studio", "category": "annual_accounts"},
)  # fmt: skip
OPCO = rule(
    "rul_opco",
    [{"field": "counterparty", "op": "equals", "value": "OPCO"}],
    {"entity": "cabinet", "category": "payment_calls"},
)
ALL = [AGIPI_PER, AGIPI_AV, HELLO, TALENZ, OPCO]

E2E = [
    ("1a", S(counterparty="agipi", addressee="M. Paul Marchand", addressee_person="paul",
             text="Votre plan d'épargne retraite", category="insurance"),
     "AGIPI", {"doc_date": date(2025, 4, 14), "reference": "C-48213"},
     "Personnel/Paul/Assurances/AGIPI/PER/2025/2025-04-14_AGIPI_PER_C-48213.pdf"),
    ("1b", S(counterparty="agipi", addressee="Mme Anna Marchand", addressee_person="anna",
             text="Situation annuelle de votre assurance vie"),
     "AGIPI", {"doc_date": date(2025, 3, 2)},
     "Personnel/Anna/Assurances/AGIPI/Assurance vie/2025/2025-03-02_AGIPI_Assurance-vie.pdf"),
    ("2", S(counterparty="hello-bank", text=f"Relevé IBAN {IBAN_SPACED}", subcategory="releve"),
     "Hello bank", {"doc_date": date(2025, 1, 16), "period_end": date(2025, 1, 15)},
     "LMNP/Angers-Strasbourg/Banque/2025/2025-01-16_Hello-bank_Releve-de-compte.pdf"),
    ("3", S(counterparty="talenz", text="Studio Numérique SIREN 888 888 880",
            subcategory="approbation"),
     "TALENZ", {"doc_date": date(2026, 1, 20), "period_end": date(2025, 9, 30)},
     "Studio Numérique/Documents annuels/2025/2026-01-20_TALENZ_Approbation-des-comptes.pdf"),
    ("5", S(counterparty="opco", subcategory="contribution_opco", entity="studio"),
     "OPCO", {"doc_date": date(2026, 2, 27), "period_end": date(2025, 12, 31),
              "reference": "2025-A-118"},
     "Cabinet Marchand/Appels de paiement/2025/2026-02-27_OPCO_Contribution-OPCO_2025-A-118.pdf"),
]  # fmt: skip


@pytest.mark.parametrize(("case", "s", "cp", "kw", "path"), E2E, ids=[c[0] for c in E2E])
def test_c5_cases_through_the_engine(case, s, cp, kw, path):
    out = evaluate(ALL, s, W)
    assert out.winner is not None and not out.conflict
    d = out.destination
    got = render(d.path_template, d.file_template, render_values(d, s, counterparty_name=cp, **kw))
    assert got.path == path


# C5 §9 scoring (thresholds 85/60).
def _score(**kw):
    from mona.rules.scoring import score

    base = {
        "rule_won": True,
        "entity_set": True,
        "model_confidence": 0.7,
        "category_unknown": False,
        "fields": {},
        "tokens": {"year", "date", "counterparty", "sub", "reference"},
        "fallbacks": {},
        "low": 60,
        "high": 85,
    }
    return score(**{**base, **kw})


@pytest.mark.parametrize(
    ("rule_won", "unverified_critical", "fallback", "confidence", "band"),
    [
        (True, False, False, 95, "high"),
        (True, True, False, 75, "medium"),
        (True, False, True, 85, "high"),
        (True, True, True, 65, "medium"),
        (False, False, False, 90, "high"),
        (False, True, False, 70, "medium"),
        (False, False, True, 80, "medium"),
        (False, True, True, 60, "medium"),
    ],
)
def test_confidence_matrix(rule_won, unverified_critical, fallback, confidence, band):
    s = _score(
        rule_won=rule_won,
        model_confidence=0.9,
        fields={"doc_date": not unverified_critical, "amount": True},
        fallbacks={"fy": 10} if fallback else {},
    )
    assert (s.confidence, s.band) == (confidence, band)
    assert s.reasons == (() if confidence >= 60 else ("low",))


def test_high_band_threshold_is_inclusive():
    assert _score(rule_won=False, model_confidence=0.85).band == "high"
    assert _score(rule_won=False, model_confidence=0.84).band == "medium"
    assert _score(rule_won=False, model_confidence=0.595).band == "medium"


def test_penalties():
    assert _score(fields={"reference": False, "counterparty": False}).confidence == 55
    assert (
        _score(
            fields={k: False for k in ("amount", "due_date", "addressee", "doc_type")},
        ).confidence
        == 80
    )
    assert _score(entity_set=False, fields={"entity": False}).confidence == 75
    assert _score(entity_set=True, fields={"entity": False}).confidence == 90
    assert _score(tokens={"sub"}, fields={"doc_date": False}).confidence == 90
    assert _score(fallbacks={"year": 20, "date": 20}).confidence == 55
    assert _score(rule_won=False, model_confidence=0.1, fallbacks={"fy": 20}).confidence == 0


@pytest.mark.parametrize(
    ("kw", "reasons"),
    [
        ({"no_entity": True}, ("entity",)),
        ({"conflict": True}, ("conflict",)),
        ({"review": True}, ("low",)),
        ({"category_unknown": True}, ("low",)),
    ],
)
def test_each_reason_queues_even_at_full_confidence(kw, reasons):
    s = _score(rule_won=False, model_confidence=1.0, **kw)
    assert s.reasons == reasons
