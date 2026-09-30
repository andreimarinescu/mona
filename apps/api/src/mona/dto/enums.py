from typing import Literal

from mona.rules.grammar import ConditionField as ConditionField

Lang = Literal["en", "fr", "ro"]
Currency = Literal["EUR", "RON"]
DocStatus = Literal["filed", "review", "processing", "unreadable"]
Reason = Literal["low", "entity", "conflict", "unreadable"]
Band = Literal["high", "medium", "low"]
Actor = Literal["mona", "user"]
Via = Literal["ui", "chat", "telegram", "pipeline"]
FieldKey = Literal[
    "entity", "counterparty", "issuer", "reference", "doc_type", "doc_date", "period_start",
    "period_end", "amount", "due_date", "addressee",
]  # fmt: skip
DsCategory = Literal[
    "bank", "invoice", "tax", "insurance", "payroll", "training", "travel", "personal"
]  # fmt: skip
PipelineStage = Literal["queued", "reading", "ocr", "classifying", "filing", "done", "failed"]
DocLocation = Literal["inbox", "archive"]
PathLocation = Literal["inbox", "archive", "trash"]
JournalAction = Literal[
    "file", "move", "rename", "unfile", "delete", "undo", "redo", "doc.update", "rule.create",
    "rule.change", "deadline.add", "reminder.add", "mark.unreadable",
]  # fmt: skip
UndoState = Literal["undoable", "undone", "superseded", "not_undoable"]
GroupUndoState = Literal["undoable", "partial", "undone", "not_undoable"]
GroupKind = Literal["intake_batch", "rule_apply", "correction", "undo", "redo", "refile"]
RuleState = Literal["draft", "active", "disabled"]
RuleSource = Literal["interview", "correction", "seed"]
DeadlineStatus = Literal["open", "done", "dismissed"]
InterviewKind = Literal["seed", "debrief", "on_demand"]
InterviewStatus = Literal["generating", "ready", "done", "failed", "cancelled"]
QuestionStatus = Literal["open", "answered", "skipped"]
DraftStatus = Literal["generating", "ready", "failed"]
ExportStatus = Literal["building", "ready", "failed"]
Visibility = Literal["practice", "personal"]
DocSource = Literal["drop", "telegram"]
