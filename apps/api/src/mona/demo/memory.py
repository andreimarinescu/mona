"""D12: Hermes' memory seeds (`memories/MEMORY.md`, `USER.md`) rendered from the loaded registry."""

import calendar
import os
from pathlib import Path

from sqlalchemy import Connection, text

# The pinned Hermes store: entries joined by this delimiter, no trailing newline.
ENTRY_DELIMITER = "\n§\n"
MEMORY_LIMIT = 2200
USER_LIMIT = 1375


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _entity_line(e) -> str:
    notes = []
    if e.legal_form and e.legal_form.casefold() != e.display_name.casefold():
        notes.append(e.legal_form)
    if (e.fy_end_month, e.fy_end_day) != (12, 31):
        notes.append(f"fiscal year ends {e.fy_end_day} {calendar.month_name[e.fy_end_month]}")
    if e.sub_units:
        notes.append(("sub-units " if len(e.sub_units) > 1 else "sub-unit ") + _join(e.sub_units))
    return e.display_name + (f" ({', '.join(notes)})" if notes else "")


def render(conn: Connection) -> tuple[str, str]:
    """(MEMORY.md, USER.md) for the registry in `conn`; deterministic for the same rows."""
    entities = conn.execute(
        text(
            "SELECT e.display_name, e.legal_form, e.visibility, e.fy_end_month, e.fy_end_day,"
            " e.purge_after_hours,"
            " (SELECT array_agg(s.label ORDER BY s.key) FROM sub_units s"
            "  WHERE s.entity_id = e.id) AS sub_units,"
            " (SELECT array_agg(coalesce(p.short_name, p.display_name) ORDER BY p.key)"
            "  FROM entity_people ep JOIN people p ON p.id = ep.person_id"
            "  WHERE ep.entity_id = e.id) AS people"
            " FROM entities e ORDER BY e.sort_order, e.key"
        )
    ).all()
    accountants = list(
        conn.execute(
            text("SELECT name FROM counterparties WHERE kind = 'accountant' ORDER BY name")
        ).scalars()
    )
    memory = []
    practice = [e for e in entities if e.visibility == "practice" and e.purge_after_hours is None]
    if practice:
        memory.append("Entities: " + "; ".join(_entity_line(e) for e in practice) + ".")
    for e in entities:
        if e.visibility == "personal":
            whose = f" of {_join(e.people)}" if e.people else ""
            memory.append(
                f"{e.display_name} holds the personal papers{whose}. Its documents never appear"
                " on Telegram or in an accountant pack."
            )
    for e in entities:
        if e.purge_after_hours is not None:
            memory.append(
                f"{e.display_name} holds documents volunteered by visitors; they are kept apart"
                f" and removed after {e.purge_after_hours} hours."
            )
    if accountants:
        who = _join(accountants)
        noun = "accountant is" if len(accountants) == 1 else "accountants are"
        memory.append(
            f"The practice's {noun} {who}. Tax, legal and accounting conclusions are for"
            f" {who} to confirm."
        )

    profile = conn.execute(text("SELECT name, locale FROM profile")).first()
    user = []
    if profile is not None:
        person = conn.execute(
            text(
                "SELECT display_name, short_name FROM people"
                " WHERE :n IN (short_name, display_name) ORDER BY key LIMIT 1"
            ),
            {"n": profile.name},
        ).first()
        call = profile.name
        who = call
        if person is not None and person.display_name != call:
            who = f"{person.display_name} ({call})"
        user.append(f"The owner is {who}. {call} runs the back office.")
        user.append(
            f"Address {call} formally ('vous' in French, 'dumneavoastră' in Romanian) until"
            f" {call} switches to 'tu' or asks to; in English, plain and polite."
        )
        lang = {"en": "English", "fr": "French", "ro": "Romanian"}.get(profile.locale)
        if lang:
            user.append(f"{call}'s interface language is {lang}.")
        user.append(
            f"{call} wants amounts and due dates first: lead with the amount (with currency) and"
            " the due date, then the rest."
        )
    return ENTRY_DELIMITER.join(memory), ENTRY_DELIMITER.join(user)


def _write_atomic(path: Path, content: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def write(conn: Connection, hermes_home: Path) -> tuple[Path, Path]:
    memory, user = render(conn)
    d = hermes_home / "memories"
    d.mkdir(parents=True, exist_ok=True)
    paths = d / "MEMORY.md", d / "USER.md"
    for path, content in zip(paths, (memory, user), strict=True):
        _write_atomic(path, content)
    return paths
