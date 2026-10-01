import os
import re
import threading
import time

_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"

PREFIXES: dict[str, str] = {
    "entities": "ent",
    "sub_units": "sub",
    "people": "per",
    "accounts": "acc",
    "counterparties": "cpt",
    "templates": "tpl",
    "rules": "rul",
    "documents": "doc",
    "extractions": "ext",
    "classifications": "cls",
    "batches": "bat",
    "intake_items": "itm",
    "exports": "exp",
    "review_items": "rev",
    "op_groups": "grp",
    "interviews": "int",
    "interview_questions": "qst",
    "interview_answers": "ans",
    "deadlines": "ddl",
    "reminders": "rem",
    "conversations": "cnv",
    "chat_turns": "trn",
    "card_events": "crd",
    "card_action_notes": "not",
    "drafts": "drf",
    "auth_sessions": "ses",
}

_lock = threading.Lock()
_last = 0

_ID = re.compile(r"([a-z]{3})_[0-9a-hjkmnp-tv-z]{26}")


def new_ulid() -> str:
    """A lowercase Crockford ULID (48-bit ms, 80 random bits), strictly increasing per process."""
    global _last
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    with _lock:
        value = max(value, _last + 1)
        _last = value
    return "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))


def new_id(prefix: str) -> str:
    return f"{prefix}_{new_ulid()}"


def is_id(value: object, prefix: str | None = None) -> bool:
    """True if `value` is a C1 §1.2 id, and of `prefix` when one is given."""
    if not isinstance(value, str):
        return False
    m = _ID.fullmatch(value)
    return bool(m) and (prefix is None or m.group(1) == prefix)
