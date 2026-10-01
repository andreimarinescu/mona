"""C5 §1.5 and §5.3–§5.5: the prompt, its context budget, and the exemplars."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import Connection, select, text

from mona.rules.grammar import Condition, RuleAction
from mona.services.dto import destination
from mona.services.registry import Snapshot, T

BUDGET = 20_000
PAGES_SENT = 3
PAGE_CHARS = 4_000
PAGE_CHARS_CUT = 2_500
RULES_MAX = 30
RULES_CUT = 15
EXEMPLARS_MAX = 5
EXEMPLAR_SIMILARITY = 0.2
LANGUAGE_NAMES = {"fr": "French", "en": "English", "ro": "Romanian"}

INTRO = (
    "You read the paperwork of {practice}, a French dental practice, and of the companies and "
    "family of its owners. For each document, decide which entity it belongs to and which "
    "category it is, and extract the fields below with evidence."
)
UNKNOWN = (
    "- unknown: the text is garbled, handwritten or too short to decide. A readable document "
    "always has a real category."
)
HOUSE_RULES = (
    "## House rules\nThe practice files documents by these rules. They are applied after you "
    "answer; use them to understand the practice."
)
FIELDS = """## Fields
Return one JSON object. Each field is {{"value", "quote", "page"}}, or null when the document does not state it.
- entity: the entity above the document concerns or is addressed to; null if none fits
- counterparty: the issuer or other party (supplier, bank, insurer, administration)
- issuer: the issuing office as printed, only if it differs from the counterparty
- reference: the invoice, contract, notice or file number
- doc_type: the document's own title or kind
- doc_date: the issue date, as YYYY-MM-DD
- period_start / period_end: the period covered (statement period, fiscal year, contract term), as YYYY-MM-DD
- amount: the main amount due or paid, as a number, plus "currency" (ISO 4217)
- due_date: the payment or reply deadline, as YYYY-MM-DD
- addressee: the person or company the document is addressed to, as written
- title: a short title in {language}: issuer, kind, period
- confidence: 0 to 1, for category and entity together
- reason: one sentence quoting the decisive evidence"""  # noqa: E501
QUOTES = """## Quotes
- Copy a short span (3 to 12 words) character for character from ONE line of the document text: same spelling, accents, capitals, punctuation and odd spacing, even if the OCR looks wrong.
- Never translate, reformat, abbreviate or join text from different lines. Dates and amounts are quoted as printed, even though "value" is normalised.
- "page" is the number in the nearest "=== PAGE n ===" marker above the quoted line.
- If you cannot find a supporting span, return null for the field."""  # noqa: E501


class PromptBudget(Exception):
    """C5 §5.4: still over the ceiling after every cut."""


@dataclass(frozen=True)
class Sections:
    """The prompt's parts, before the budget cuts."""

    practice_name: str
    language: str
    entities: tuple[str, ...]
    categories: tuple[str, ...]
    rules: tuple[str, ...]
    exemplars: tuple[str, ...]
    filename: str
    pages: tuple[str, ...]


@dataclass(frozen=True)
class Cut:
    exemplars: int = EXEMPLARS_MAX
    rules: int = RULES_MAX
    chars: int = PAGE_CHARS
    pages: int = PAGES_SENT


CUTS = (
    Cut(),
    Cut(exemplars=0),
    Cut(exemplars=0, rules=RULES_CUT),
    Cut(exemplars=0, rules=0),
    Cut(exemplars=0, rules=0, chars=PAGE_CHARS_CUT),
    Cut(exemplars=0, rules=0, chars=PAGE_CHARS_CUT, pages=2),
    Cut(exemplars=0, rules=0, chars=PAGE_CHARS_CUT, pages=1),
)


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str
    pages_sent: tuple[str, ...]
    page_count: int
    cut: Cut

    @property
    def tokens(self) -> int:
        return estimate(self.system + self.user)


def estimate(s: str) -> int:
    return math.ceil(len(s) / 3.2)


def page_block(pages: Sequence[str], page_count: int) -> str:
    """C5 §1.5, variant `p1_markers_layout`."""
    out = [f"Document text, {len(pages)} of {page_count} page(s):"]
    for n, p in enumerate(pages, 1):
        out += [f"=== PAGE {n} ===", p]
    return "\n".join(out)


def render(s: Sections, cut: Cut) -> Prompt:
    system = [INTRO.format(practice=s.practice_name), "", "## Entities", *s.entities, "",
              "## Categories", *s.categories, UNKNOWN, ""]  # fmt: skip
    rules = s.rules[: cut.rules]
    if rules:
        system += [HOUSE_RULES, *rules, ""]
    system += [FIELDS.format(language=LANGUAGE_NAMES[s.language]), "", QUOTES, "",
               "Respond with JSON only."]  # fmt: skip
    pages = tuple(p[: cut.chars] for p in s.pages[: min(cut.pages, PAGES_SENT)])
    user: list[str] = []
    exemplars = s.exemplars[: cut.exemplars]
    if exemplars:
        user += ["Documents already filed here, for reference:", *exemplars, ""]
    user += [f"Filename: {s.filename}", "", page_block(pages, len(s.pages))]
    return Prompt("\n".join(system), "\n".join(user), pages, len(s.pages), cut)


def build(s: Sections, max_pages: int = PAGES_SENT) -> Prompt:
    """The first cut level of §5.4 that fits under the ceiling, sending ≤ `max_pages` pages."""
    for cut in CUTS:
        p = render(s, replace(cut, pages=min(cut.pages, max_pages)))
        if p.tokens <= BUDGET:
            return p
    raise PromptBudget("prompt_budget")


# --- sections from the database ---


def entity_lines(conn: Connection, snap: Snapshot) -> list[str]:
    ep, p = T["entity_people"], T["people"]
    people: dict[str, list[str]] = {}
    for row in conn.execute(
        select(ep.c.entity_id, p.c.display_name)
        .join(p, p.c.id == ep.c.person_id)
        .order_by(p.c.display_name)
    ):
        people.setdefault(row.entity_id, []).append(row.display_name)
    lines = []
    rows = sorted(snap.entities.values(), key=lambda e: (e["sort_order"], e["key"]))
    for e in rows:
        if e["key"] == snap.visitors:
            continue
        lines.append(
            f"- {e['key']}: {e['display_name']} ({e['legal_form'] or 'private household'}). "
            f"Names on documents: {'; '.join(e['aliases'])}. "
            f"People: {', '.join(people.get(e['id'], []))}."
        )
    return lines


def category_lines(snap: Snapshot) -> list[str]:
    lines = []
    for c in sorted(snap.categories.values(), key=lambda c: (c["sort_order"], c["id"])):
        subs = sorted(
            (s for (cid, _), s in snap.subcategories.items() if cid == c["id"]),
            key=lambda s: (s["sort_order"], s["key"]),
        )
        listed = "; ".join(f"{s['key']} ({s['labels']['en']})" for s in subs)
        lines.append(f"- {c['id']}: {c['model_definition']} Subcategories: {listed}")
    return lines


def rule_lines(conn: Connection, snap: Snapshot) -> list[str]:
    r = T["rules"]
    rows = conn.execute(
        select(r)
        .where(r.c.state == "active")
        .order_by(r.c.priority.desc(), r.c.created_at, r.c.id)
        .limit(RULES_MAX)
    ).mappings()
    lines = []
    for row in rows:
        conds = [Condition.model_validate(c) for c in row["conditions"]]
        try:
            dest = destination(snap, RuleAction.model_validate(row["action"]), conds)
        except KeyError:
            continue
        lines.append(f"- {row['condition_text']['en']} → {' / '.join(dest)}")
    return lines


EXEMPLARS = text(
    """
    SELECT d.title, cp.name AS counterparty, e.key AS entity, d.category_id, d.subcategory_key,
           d.counterparty_id, similarity(d.head_norm, :head) AS sim
    FROM documents d
    JOIN classifications c ON c.id = d.classification_id
    JOIN entities e ON e.id = d.entity_id
    LEFT JOIN counterparties cp ON cp.id = d.counterparty_id
    WHERE d.status = 'filed' AND d.deleted_at IS NULL AND d.id <> :id
      AND d.head_norm IS NOT NULL AND d.category_id IS NOT NULL
      AND (c.method IN ('user', 'rule') OR c.band = 'high')
      AND e.purge_after_hours IS NULL
      AND NOT EXISTS (SELECT 1 FROM batches b WHERE b.id = d.batch_id AND b.visitor)
      AND similarity(d.head_norm, :head) >= :min
    ORDER BY sim DESC, d.id
    LIMIT 50
    """
)


def exemplar_lines(conn: Connection, doc: Mapping[str, Any]) -> list[str]:
    """C5 §5.5: ≤ 5 similar filed documents, ≤ 2 per counterparty, never a Visitors one (C9 §5.5);
    never their text."""
    if not doc["head_norm"]:
        return []
    per_cp: dict[Any, int] = {}
    lines = []
    for row in conn.execute(
        EXEMPLARS, {"head": doc["head_norm"], "id": doc["id"], "min": EXEMPLAR_SIMILARITY}
    ):
        if per_cp.get(row.counterparty_id, 0) >= 2:
            continue
        per_cp[row.counterparty_id] = per_cp.get(row.counterparty_id, 0) + 1
        cat = row.category_id + (f".{row.subcategory_key}" if row.subcategory_key else "")
        lines.append(
            f'- "{row.title or "untitled"}" from {row.counterparty or "unknown"} → '
            f"{row.entity} / {cat}"
        )
        if len(lines) == EXEMPLARS_MAX:
            break
    return lines


def sections(
    conn: Connection, snap: Snapshot, doc: Mapping[str, Any], pages: Sequence[str]
) -> Sections:
    return Sections(
        practice_name=snap.settings["practice_name"],
        language=snap.language,
        entities=tuple(entity_lines(conn, snap)),
        categories=tuple(category_lines(snap)),
        rules=tuple(rule_lines(conn, snap)),
        exemplars=tuple(exemplar_lines(conn, doc)),
        filename=doc["original_name"],
        pages=tuple(pages),
    )
