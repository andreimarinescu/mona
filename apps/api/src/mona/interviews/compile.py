"""C6 §4.5: checks and compilation of pass-2 output into stored questions."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, select, text

from mona.db.models import Base
from mona.i18n import ro_comma_below, t
from mona.interviews.config import MAX_QUESTIONS
from mona.interviews.prompt import Input, pages
from mona.rules import store
from mona.rules.engine import Subject, holds
from mona.rules.grammar import RuleBody, RuleDraft, unresolved
from mona.services import registry
from mona.services.placement import subject
from mona.services.registry import Snapshot
from mona.text import norm

T = Base.metadata.tables
OPTION_IDS = ("a", "b", "c")
TRIGRAM_MIN = 0.6
FIND_MAX = 120
_TRIM = " \t\n.,;:"


def find_query(quote: str, page_text: str) -> str | None:
    """C5 §7 for a clue with no field value: the whole quote, else its longest in-line run."""
    lines = [norm(line) for line in page_text.split("\n")]
    candidate: str | None = None
    if any(norm(quote) in line for line in lines):
        candidate = quote
    else:
        words = quote.split()
        best: tuple[int, int] | None = None
        for i in range(len(words)):
            for j in range(len(words), i + 1, -1):
                span = norm(" ".join(words[i:j]))
                if len(span) >= 6 and any(span in line for line in lines):
                    if best is None or j - i > best[1] - best[0]:
                        best = (i, j)
                    break
        candidate = " ".join(words[best[0] : best[1]]) if best else None
    if candidate is None:
        return None
    out = re.sub(r"\s+", " ", candidate.strip(_TRIM))
    if len(out) > FIND_MAX:
        cut = out[:FIND_MAX]
        out = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return out.strip(_TRIM) or None


@dataclass
class Compiled:
    text: str
    affected: list[str]
    evidence: list[dict[str, Any]]
    options: list[dict[str, Any]]
    suggestion_confidence: int
    counterparty_id: str | None = None
    model_order: int = 0
    impact: int = 0


@dataclass
class Compiler:
    """One pass over a pass-2 output against the current registry and documents."""

    conn: Connection
    inp: Input
    lang: str
    textcache: Path
    seed: bool = False
    snap: Snapshot = field(init=False)
    _subjects: dict[str, Subject] = field(default_factory=dict)
    _pages: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.snap = registry.load(self.conn)
        self.reg = store.registry(self.conn)

    # --- helpers ---

    def pages_of(self, doc_id: str) -> list[str]:
        if doc_id not in self._pages:
            self._pages[doc_id] = pages(self.textcache, self.inp.docs[doc_id].sha256)
        return self._pages[doc_id]

    def subject_of(self, doc_id: str) -> Subject:
        if doc_id not in self._subjects:
            d = T["documents"]
            row = self.conn.execute(select(d).where(d.c.id == doc_id)).mappings().one()
            self._subjects[doc_id] = subject(self.conn, self.snap, row, self.textcache)
        return self._subjects[doc_id]

    def counterparty_key(self, value: str) -> str | None:
        """C5 §6.2 step 1 without inserting: exact alias, else trigram ≥ 0.6."""
        n = norm(value)
        if not n:
            return None
        for key, cp in self.snap.world.counterparties.items():
            if n == norm(key) or n == cp.name_norm or n in cp.alias_norms:
                return key
        hit = self.conn.execute(
            text(
                "SELECT key FROM counterparties WHERE similarity(name_norm, :n) >= :t"
                " ORDER BY similarity(name_norm, :n) DESC, id LIMIT 1"
            ),
            {"n": n, "t": TRIGRAM_MIN},
        ).scalar()
        return hit

    # --- §4.5 steps ---

    def evidence(self, items: list[dict], affected: list[str]) -> list[dict[str, Any]]:
        out = []
        for item in items:
            doc_id = self.inp.aliases.get(item.get("doc", ""))
            if doc_id is None or doc_id not in affected:
                continue
            q = norm(item.get("quote", ""))
            if len(q) < 3:
                continue
            for n, page in enumerate(self.pages_of(doc_id), start=1):
                if q in norm(page):
                    out.append(
                        {
                            "document_id": doc_id,
                            "field": None,
                            "page": n,
                            "quote": item["quote"],
                            "verified": True,
                            "find_query": find_query(item["quote"], page),
                        }
                    )
                    break
        return out

    def compile_branch(
        self,
        branch: Mapping[str, Any],
        settled: list[str],
        shared_cp: str | None,
        *,
        always: bool = False,
    ) -> dict[str, Any] | None:
        conditions = []
        for c in branch.get("conditions", []):
            c = dict(c)
            if c.get("field") == "counterparty" and c.get("op") in ("equals", "in"):
                values = c["value"] if isinstance(c["value"], list) else [c["value"]]
                keys = [self.counterparty_key(str(v)) or v for v in values]
                c["value"] = keys if isinstance(c["value"], list) else keys[0]
            conditions.append(c)
        a = branch.get("action") or {}
        entity = a.get("entity")
        action: dict[str, Any] = {"entity": entity}
        unit = a.get("unit")
        if unit == "from_person":
            action["unit"] = {"from": "person"}
        elif isinstance(unit, str):
            ent, _, key = unit.partition("/")
            if ent != entity:
                return None
            action["unit"] = key
        if a.get("category"):
            action["category"] = a["category"]
        sub = a.get("subcategory")
        if isinstance(sub, str) and sub.partition(".")[0] == action.get("category"):
            action["subcategory"] = sub.partition(".")[2]
        if shared_cp and not any(c.get("field") == "counterparty" for c in conditions):
            conditions.insert(0, {"field": "counterparty", "op": "equals", "value": shared_cp})
        try:
            body = RuleBody.model_validate({"conditions": conditions, "action": action})
        except ValidationError:
            return None
        if unresolved(body, self.reg):
            return None
        if "subcategory" in action:
            held = [
                d
                for d in settled
                if always
                or all(holds(c, self.subject_of(d), self.snap.world) for c in body.conditions)
            ]
            subs = {self.inp.docs[d].subcategory for d in held} - {None}
            if len(subs) > 1:
                body.action.subcategory = None
        return body.model_dump(mode="json")

    def rule_draft(
        self, draft: Mapping[str, Any], settled: list[str], shared_cp: str | None
    ) -> dict[str, Any] | None:
        kind = draft.get("kind")
        branches: list[dict[str, Any]] = []
        if kind != "ask":
            for b in draft.get("branches") or []:
                compiled = self.compile_branch(b, settled, shared_cp, always=kind == "always")
                if compiled is None:
                    return None
                branches.append(compiled)
        discriminator = draft.get("discriminator") if kind == "depends" else None
        try:
            checked = RuleDraft.model_validate(
                {"kind": kind, "discriminator": discriminator, "branches": branches}
            )
        except ValidationError:
            return None
        return checked.model_dump(mode="json")

    def question(self, q: Mapping[str, Any], order: int) -> Compiled | None:
        affected_aliases = [
            a for a in dict.fromkeys(q.get("affected", [])) if a in self.inp.aliases
        ]
        counterparty_id: str | None = None
        if self.seed:
            cps = [self.inp.aliases[a] for a in affected_aliases]
            affected = list(dict.fromkeys(d for c in cps for d in self.inp.seed_docs.get(c, [])))
            counterparty_id = cps[0] if len(cps) == 1 else None
            evidence: list[dict[str, Any]] = []
        else:
            affected = [self.inp.aliases[a] for a in affected_aliases]
            if not affected:
                return None
            shared = {self.inp.docs[d].counterparty_id for d in affected}
            counterparty_id = next(iter(shared)) if len(shared) == 1 else None
            evidence = self.evidence(q.get("evidence", []), affected)
        shared_key = self.snap.counterparty_keys.get(counterparty_id) if counterparty_id else None
        options = []
        for opt in q.get("options", []):
            draft = self.rule_draft(opt.get("rule_draft") or {}, affected, shared_key)
            if draft is None or opt.get("id") in {o["id"] for o in options}:
                continue
            options.append(
                {
                    "id": opt["id"],
                    "label": opt.get("label", ""),
                    "suggested": False,
                    "rule_draft": draft,
                }
            )
        if not any(o["rule_draft"]["kind"] != "ask" for o in options):
            return None
        ids = [o["id"] for o in options]
        chosen = q.get("suggested") if q.get("suggested") in ids else ids[0]
        if len(options) < 3 and not any(o["rule_draft"]["kind"] == "ask" for o in options):
            free = next(i for i in OPTION_IDS if i not in {o["id"] for o in options})
            options.append(
                {
                    "id": free,
                    "label": t("interview.option.ask", self.lang),
                    "suggested": False,
                    "rule_draft": {"kind": "ask", "discriminator": None, "branches": []},
                }
            )
        for o in options:
            o["suggested"] = o["id"] == chosen
        confidence = Decimal(str(q.get("confidence", 0))) * 100
        text_ = q.get("text", "")
        if self.lang == "ro":
            text_ = ro_comma_below(text_)
            for o in options:
                o["label"] = ro_comma_below(o["label"])
        return Compiled(
            text=text_,
            affected=affected,
            evidence=evidence,
            options=options,
            suggestion_confidence=int(confidence.quantize(Decimal(1), rounding=ROUND_HALF_UP)),
            counterparty_id=counterparty_id,
            model_order=order,
        )

    def run(self, output: Mapping[str, Any]) -> list[Compiled]:
        out = []
        for n, q in enumerate(output.get("questions", [])[:MAX_QUESTIONS]):
            compiled = self.question(q, n)
            if compiled is not None:
                out.append(compiled)
        return out
