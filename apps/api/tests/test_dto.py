import copy
import re
from typing import get_args

import psycopg
import pytest
from pydantic import ValidationError

from mona import dto
from mona.dto import enums
from mona.settings import get_settings


def ID(prefix: str, n: int = 1) -> str:
    return f"{prefix}_01j9zq3k8e6y4v2m7c5r1t0b{n:02d}"


TS = "2026-10-14T07:02:00Z"
EVIDENCE = {
    "documentId": ID("doc"),
    "documentTitle": "URSSAF appel T3",
    "field": "due_date",
    "page": 1,
    "quote": "à payer avant le 14/10/2026",
    "verified": True,
    "findQuery": "à payer avant le 14/10/2026",
}
CONDITIONS = [
    {"field": "counterparty", "op": "equals", "value": "OPCO"},
    {"field": "text", "op": "contains_any", "value": ["contribution", "OPCO"], "negate": True},
]
ACTION = {"entity": "cabinet", "unit": {"from": "person"}, "category": "payment_calls",
          "subcategory": "contribution_opco", "path": "{entity}/Appels/{fy}"}  # fmt: skip
RULE = {
    "id": ID("rul"),
    "name": "OPCO contributions",
    "condition": "When the counterparty is OPCO.",
    "conditionText": "When the counterparty is OPCO.",
    "conditions": CONDITIONS,
    "action": ACTION,
    "destination": ["Cabinet Marchand", "Appels de paiement", "{fy}"],
    "enabled": True,
    "state": "active",
    "source": "seed",
    "version": 2,
    "priority": 30,
    "firedCount": 4,
    "lastFiredAt": TS,
    "correctionsSince": 0,
}
RULE_DRAFT = {
    "kind": "depends",
    "discriminator": "addressee",
    "branches": [
        {"conditions": [CONDITIONS[0], {"field": "addressee", "op": "is_person", "value": "paul"}],
         "action": {"entity": "personal", "unit": {"from": "person"}}},
        {"conditions": [CONDITIONS[0], {"field": "addressee", "op": "is_entity", "value": "cab"}],
         "action": {"entity": "cabinet"}},
    ],
}  # fmt: skip
PATH_STATE = {"location": "archive", "path": ["Cabinet Marchand", "2025"],
              "fileName": "2026-02-27_OPCO.pdf", "status": "filed"}  # fmt: skip
JOURNAL_ENTRY = {
    "id": 42,
    "at": TS,
    "actor": "mona",
    "via": "pipeline",
    "action": "file",
    "documentIds": [ID("doc")],
    "subjectId": None,
    "before": {**PATH_STATE, "location": "inbox", "path": [], "status": "processing"},
    "after": PATH_STATE,
    "batchId": ID("bat"),
    "groupId": ID("grp"),
    "ruleId": ID("rul"),
    "confidence": 91,
    "band": "high",
    "undoable": True,
    "undoState": "undoable",
    "undoneBy": 43,
    "undoOf": None,
}
MONEY = {"value": 1284.0, "currency": "EUR"}
DEADLINE = {
    "id": ID("ddl"),
    "documentId": ID("doc"),
    "label": "URSSAF T3",
    "entityId": ID("ent"),
    "entityName": "Cabinet Marchand",
    "dueDate": "2026-10-14",
    "amount": MONEY,
    "paidBy": "Hello bank · LMNP •• 4821",
    "status": "open",
    "daysLeft": -2,
    "reminder": {"id": ID("rem"), "remindOn": "2026-10-10"},
}
SUMMARY = {
    "id": ID("doc"),
    "title": "URSSAF appel T3",
    "originalName": "scan_0001.pdf",
    "fileName": "2026-09-22_URSSAF_Appel.pdf",
    "path": ["Cabinet Marchand", "Appels de paiement", "2026"],
    "location": "archive",
    "entityId": ID("ent"),
    "entityName": "Cabinet Marchand",
    "subUnitId": ID("sub"),
    "categoryId": "payment_calls",
    "subcategoryKey": "appel_cotisations",
    "counterpartyId": ID("cpt"),
    "counterparty": "URSSAF",
    "docType": "appel de cotisations",
    "reference": "2026-T3",
    "date": "2026-09-22",
    "periodStart": "2026-07-01",
    "periodEnd": "2026-09-30",
    "fiscalYear": 2026,
    "amount": MONEY,
    "dueDate": "2026-10-14",
    "status": "filed",
    "reasons": [],
    "confidence": 93,
    "band": "high",
    "pipelineStage": "done",
    "arrivedAt": TS,
    "source": "drop",
    "filedAt": TS,
    "filedBy": "mona",
    "badgeUntil": TS,
    "rule": {"id": ID("rul"), "name": "URSSAF"},
    "batchId": ID("bat"),
    "pageCount": 2,
    "thumbnailUrl": "/api/documents/x/thumbnail",
    "pdfUrl": "/api/documents/x/pdf",
}
SUGGESTION = {
    "entityId": ID("ent"),
    "subUnitId": None,
    "categoryId": "insurance",
    "subcategoryKey": "per",
    "fileName": None,
    "path": ["Personnel", "Assurances"],
    "confidence": 58,
    "band": "low",
    "reasons": ["low", "conflict"],
    "sentence": "I think this is …",
    "evidence": [EVIDENCE],
    "ruleId": None,
    "conflictingRuleIds": [ID("rul", 1), ID("rul", 2)],
}
QUESTION = {
    "id": ID("qst"),
    "ordinal": 1,
    "question": "Who holds the AGIPI contracts?",
    "lang": "en",
    "affects": [ID("doc", 1), ID("doc", 2)],
    "affectsCount": 2,
    "evidence": [{**EVIDENCE, "field": None, "findQuery": None}],
    "options": [
        {"id": "a", "label": "Split by insured person", "suggested": True, "ruleDraft": RULE_DRAFT},
        {"id": "b", "label": "Ask me each time",
         "ruleDraft": {"kind": "ask", "discriminator": None, "branches": []}},
        {"id": "c", "label": "Something else", "ruleDraft": None},
    ],
    "suggestionConfidence": 72,
    "status": "answered",
    "answer": {"optionId": "a", "freeText": None, "ruleIds": [ID("rul", 3), ID("rul", 4)]},
}  # fmt: skip

SAMPLES = {
    dto.Money: MONEY,
    dto.Evidence: EVIDENCE,
    dto.ExtractedField: {"key": "amount", "value": "1284.00", "money": MONEY,
                         "evidence": EVIDENCE, "confidence": 88},
    dto.DocumentSummary: SUMMARY,
    dto.DocumentDetail: {
        **SUMMARY,
        "fields": [{"key": "doc_date", "value": "2026-09-22", "evidence": EVIDENCE,
                    "confidence": 95}],
        "suggestion": SUGGESTION,
        "journal": [JOURNAL_ENTRY],
        "deadlines": [DEADLINE],
    },
    dto.Suggestion: SUGGESTION,
    dto.Rule: RULE,
    dto.RuleDraft: RULE_DRAFT,
    dto.RulePreview: {
        "rule": RULE,
        "moves": [{"documentId": ID("doc"), "title": "OPCO", "from": ["Inbox"],
                   "fromFileName": "a.pdf", "to": ["Cabinet Marchand"], "toFileName": "b.pdf"}],
        "movesTotal": 4,
        "stays": [ID("doc", 2)],
        "staysTotal": 2,
        "applied": True,
        "groupId": ID("grp"),
    },
    dto.PathState: PATH_STATE,
    dto.JournalEntry: JOURNAL_ENTRY,
    dto.JournalGroup: {
        "id": ID("grp"), "kind": "rule_apply", "at": TS, "actor": "user", "via": "ui",
        "batchId": None, "ruleId": ID("rul"),
        "counts": {"entries": 4, "undoable": 3, "superseded": 1, "undone": 0},
        "undoState": "partial", "targetGroupId": None,
    },
    dto.Deadline: DEADLINE,
    dto.InterviewQuestion: QUESTION,
    dto.Interview: {"id": ID("int"), "kind": "debrief", "status": "ready",
                    "questions": [QUESTION], "batchId": ID("bat"), "createdAt": TS,
                    "lang": "en", "scope": {"type": "batch", "batchId": ID("bat")},
                    "openQuestions": 0, "readyAt": TS, "finishedAt": None, "error": None,
                    "source": "live"},
    dto.Draft: {"id": ID("drf"), "documentId": ID("doc"), "lang": "fr", "status": "ready",
                "title": "Réponse", "body": "Madame, Monsieur", "docxUrl": None},
    dto.ExportPack: {"id": ID("exp"), "entityId": ID("ent"), "entityName": "Cabinet Marchand",
                     "fiscalYear": 2025, "status": "ready", "documentCount": 12,
                     "zipUrl": "/api/exports/x.zip", "csvUrl": "/api/exports/x.csv"},
    dto.Entity: {
        "id": ID("ent"), "key": "cabinet", "displayName": "Cabinet Marchand SELARL",
        "folderName": "Cabinet Marchand", "legalForm": "SELARL", "siren": "123456782",
        "visibility": "practice", "fiscalYearEnd": "12-31", "filingLanguage": None,
        "subUnits": [{"id": ID("sub"), "key": "paul", "label": "Paul", "personId": ID("per")}],
        "people": [{"personId": ID("per"), "role": "gérant"}],
        "accounts": [{"id": ID("acc"), "key": "cab-main", "label": "Banque · Cabinet",
                      "ibanLast4": "4821", "subUnitId": None}],
    },
    dto.Person: {"id": ID("per"), "key": "paul", "displayName": "Paul Marchand",
                 "shortName": "Paul"},
    dto.Category: {
        "id": "insurance", "labels": {"en": "Insurance", "fr": "Assurances", "ro": "Asigurări"},
        "icon": "insurance",
        "subcategories": [{"key": "per", "labels": {"en": "PER", "fr": "PER", "ro": "PER"}}],
        "template": {"pathTemplate": "{entity}/Assurances/{year}",
                     "fileTemplate": "{date:YYYY-MM-DD}_{counterparty}"},
        "entityTemplates": [{"entityId": ID("ent"), "pathTemplate": "{entity}/A/{year}",
                             "fileTemplate": "{date:YYYY-MM-DD}_{sub}"}],
    },
    dto.Counterparty: {"id": ID("cpt"), "key": "agipi", "name": "AGIPI", "kind": "insurer"},
    dto.Condition: CONDITIONS[1],
    dto.RuleAction: ACTION,
}  # fmt: skip

# One enum-typed location per DTO: (path to the value, bad value).
BAD_ENUMS = {
    dto.Money: (["currency"], "USD"),
    dto.Evidence: (["field"], "dueDate"),
    dto.ExtractedField: (["key"], "dueDate"),
    dto.DocumentSummary: (["status"], "archived"),
    dto.DocumentDetail: (["fields", 0, "key"], "docDate"),
    dto.Suggestion: (["band"], "mid"),
    dto.Rule: (["state"], "paused"),
    dto.RuleDraft: (["discriminator"], "colour"),
    dto.RulePreview: (["rule", "source"], "import"),
    dto.PathState: (["location"], "attic"),
    dto.JournalEntry: (["undoState"], "gone"),
    dto.JournalGroup: (["kind"], "batch"),
    dto.Deadline: (["status"], "paid"),
    dto.InterviewQuestion: (["lang"], "de"),
    dto.Interview: (["kind"], "weekly"),
    dto.Draft: (["status"], "sent"),
    dto.ExportPack: (["status"], "zipped"),
    dto.Entity: (["visibility"], "public"),
    dto.Person: (["id"], ID("ent")),
    dto.Category: (["icon"], "rocket"),
    dto.Counterparty: (["id"], "cpt_nope"),
    dto.Condition: (["op"], "startswith"),
    dto.RuleAction: (["unit", "from"], "addressee"),
}
EXPORTED = {getattr(dto, name) for name in dto.__all__}
GRAMMAR_KEYS = {"conditions", "action", "ruleDraft"}


def test_every_exported_dto_has_a_sample_and_a_bad_enum():
    assert set(SAMPLES) == EXPORTED == set(BAD_ENUMS)


@pytest.mark.parametrize("model", list(SAMPLES), ids=lambda m: m.__name__)
def test_round_trip(model):
    sample = SAMPLES[model]
    dumped = model.model_validate(sample).model_dump(mode="json")
    assert dumped == sample
    assert model.model_validate_json(model.model_validate(sample).model_dump_json()) == (
        model.model_validate(sample)
    )


def _keys(value, in_grammar=False):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k, in_grammar
            yield from _keys(v, in_grammar or k in GRAMMAR_KEYS)
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v, in_grammar)


@pytest.mark.parametrize("model", list(SAMPLES), ids=lambda m: m.__name__)
def test_keys_are_camel_case_and_grammar_keys_single_words(model):
    top_is_grammar = model in (dto.RuleDraft, dto.Condition, dto.RuleAction)
    for key, in_grammar in _keys(model.model_validate(SAMPLES[model]).model_dump(mode="json")):
        if in_grammar or top_is_grammar:
            assert re.fullmatch(r"[a-z]+", key), key
        else:
            assert re.fullmatch(r"[a-z][a-zA-Z0-9]*", key), key


@pytest.mark.parametrize("model", list(BAD_ENUMS), ids=lambda m: m.__name__)
def test_rejects_bad_enum(model):
    path, bad = BAD_ENUMS[model]
    sample = copy.deepcopy(SAMPLES[model])
    target = sample
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = bad
    with pytest.raises(ValidationError):
        model.model_validate(sample)


def test_optional_fields_are_omitted_and_nullable_fields_kept():
    doc = dto.DocumentSummary.model_validate({**SUMMARY, "amount": None, "dueDate": None})
    out = doc.model_dump(mode="json")
    assert "amount" not in out and out["dueDate"] is None
    entry = dto.JournalEntry.model_validate({**JOURNAL_ENTRY, "undoneBy": None, "batchId": None})
    assert "undoneBy" not in entry.model_dump() and "batchId" not in entry.model_dump()


def test_timestamps_serialise_in_utc_with_z():
    doc = dto.DocumentSummary.model_validate({**SUMMARY, "arrivedAt": "2026-10-14T09:02:00+02:00"})
    assert doc.model_dump(mode="json")["arrivedAt"] == TS
    with pytest.raises(ValidationError):
        dto.DocumentSummary.model_validate({**SUMMARY, "arrivedAt": "2026-10-14T09:02:00"})


def test_snake_case_input_is_accepted():
    ev = dto.Evidence.model_validate(
        {"document_id": ID("doc"), "document_title": "t", "field": None, "page": 1,
         "quote": "q", "verified": False, "find_query": None}
    )  # fmt: skip
    assert ev.model_dump()["documentId"] == ID("doc")


def test_money_rounds_to_two_decimals():
    assert dto.Money(value="1284.005", currency="RON").value == 1284.01
    assert dto.Money(value=12.345, currency="EUR").model_dump()["value"] == 12.35


def _check_values(conn, table: str, column: str) -> set[str]:
    rows = conn.execute(
        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
        " JOIN pg_class t ON t.oid = c.conrelid"
        " WHERE t.relname = %s AND c.contype = 'c' AND c.conname = %s",
        (table, f"{table}_{column}_check"),
    ).fetchall()
    assert rows, f"{table}.{column}"
    return set(re.findall(r"'([^']+)'", rows[0][0]))


ENUM_COLUMNS = [
    (enums.FieldKey, "extraction_fields", "key"),
    (enums.DocStatus, "documents", "status"),
    (enums.Reason, "documents", "reasons"),
    (enums.Band, "documents", "band"),
    (enums.Actor, "file_ops", "actor"),
    (enums.Via, "file_ops", "via"),
    (enums.JournalAction, "file_ops", "action"),
    (enums.GroupKind, "op_groups", "kind"),
    (enums.DsCategory, "categories", "icon"),
    (enums.PipelineStage, "documents", "pipeline_stage"),
    (enums.PathLocation, "documents", "location"),
    (enums.DocSource, "documents", "source"),
    (enums.Currency, "documents", "currency"),
    (enums.RuleState, "rules", "state"),
    (enums.RuleSource, "rules", "source"),
    (enums.DeadlineStatus, "deadlines", "status"),
    (enums.InterviewKind, "interviews", "kind"),
    (enums.InterviewStatus, "interviews", "status"),
    (enums.QuestionStatus, "interview_questions", "status"),
    (enums.DraftStatus, "drafts", "status"),
    (enums.ExportStatus, "exports", "status"),
    (enums.Visibility, "entities", "visibility"),
    (enums.Lang, "interviews", "lang"),
]


@pytest.mark.parametrize(("literal", "table", "column"), ENUM_COLUMNS, ids=lambda x: str(x))
def test_enum_values_equal_db_values(literal, table, column):
    with psycopg.connect(get_settings().libpq_url) as conn:
        assert set(get_args(literal)) == _check_values(conn, table, column)
