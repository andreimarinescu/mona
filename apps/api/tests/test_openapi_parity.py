"""C2 §17 item 13: operation ids and DTO component names (C2 §16 items 4–5)."""

import re

from mona.app import create_app

C1_DTOS = {
    "Money", "Evidence", "ExtractedField", "DocumentSummary", "DocumentDetail", "Suggestion",
    "Rule", "RulePreview", "PathState", "JournalEntry", "JournalGroup", "Deadline", "Entity",
    "Person", "Category", "Counterparty",
}  # fmt: skip
C2_DTOS = {
    "ApiError", "AuthState", "ShellState", "BriefFacts", "HomeView", "BatchSummary",
    "DocumentPage", "FolderNode", "FolderListing", "FileOpResult", "CorrectionRequest",
    "RuleListItem", "RulePatch", "ApplyResult", "LearnedItem", "EntityWrite", "EntityDetail",
    "PersonDetail", "TemplatePreview", "ActivityPage", "UndoResult", "SettingsView",
    "SettingsPatch", "SystemStatus", "ConversationSummary",
}  # fmt: skip


def schema() -> dict:
    return create_app().openapi()


def test_every_route_has_a_camel_case_operation_id_and_declares_its_errors():
    ops = [
        (path, method, op)
        for path, item in schema()["paths"].items()
        for method, op in item.items()
    ]
    ids = [op.get("operationId") for _, _, op in ops]
    assert all(i and re.fullmatch(r"[a-z][a-zA-Z0-9]*", i) for i in ids), ids
    assert len(ids) == len(set(ids))
    for path, method, op in ops:
        if path in ("/api/health",):
            continue
        declared = {code for code in op["responses"] if code.startswith(("4", "5"))}
        assert declared, (method, path)
        for code in declared:
            ref = op["responses"][code]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ApiError"), (method, path, code)


def test_dtos_are_components_under_their_contract_names():
    components = set(schema()["components"]["schemas"])
    assert sorted((C1_DTOS | C2_DTOS) - components) == []


def test_mcp_is_not_in_the_schema():
    assert not [p for p in schema()["paths"] if p.startswith("/mcp")]
