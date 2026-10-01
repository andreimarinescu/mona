"""Amendment A25 (C6 §4.5–§4.6): every candidate cluster gets a question, through a targeted
pass 2 and then a deterministic question from Mona's own proposal."""

from collections import Counter
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from mona.db.models import Base
from mona.i18n import t
from mona.interviews.compile import Compiled, Compiler
from mona.interviews.config import MAX_QUESTIONS, MAX_TARGETED
from mona.interviews.prompt import Input
from mona.text import norm

T = Base.metadata.tables
EVIDENCE_MAX = 3
LABEL_MAX = 90

Cluster = list[str]


def input_clusters(inp: Input) -> list[Cluster]:
    """The §4.2 clusters the input holds, in its order, as document ids."""
    out: dict[int, Cluster] = {}
    for d in inp.body.get("documents", []):
        out.setdefault(d["cluster"], []).append(inp.aliases[d["alias"]])
    return list(out.values())


def reduced(inp: Input, cluster: Cluster) -> Input:
    """The input with only the cluster's documents; aliases and the registry unchanged."""
    keep = set(cluster)
    alias_of = inp.alias_of
    docs = [d for d in inp.body["documents"] if inp.aliases[d["alias"]] in keep]
    return Input(
        body={**inp.body, "documents": docs},
        aliases={alias_of[d]: d for d in cluster},
        docs={d: inp.docs[d] for d in cluster},
    )


def uncovered(cluster: Cluster, questions: list[Compiled]) -> bool:
    return not set(cluster) & {d for q in questions for d in q.affected}


def about(compiler: Compiler, cluster: Cluster, text: str) -> bool:
    """A26: the text names the cluster's counterparty, an alias, or its extracted string."""
    docs = [compiler.inp.docs[d] for d in cluster]
    ids = {d.counterparty_id for d in docs if d.counterparty_id}
    names = {norm(d.extracted_counterparty or "") for d in docs if not d.counterparty_id}
    if ids:
        cp, a = T["counterparties"], T["counterparty_aliases"]
        names |= set(
            compiler.conn.execute(select(cp.c.name_norm).where(cp.c.id.in_(ids))).scalars()
        )
        names |= set(
            compiler.conn.execute(
                select(a.c.alias_norm).where(a.c.counterparty_id.in_(ids))
            ).scalars()
        )
    n = norm(text)
    return any(x and x in n for x in names)


def _evidence(compiler: Compiler, cluster: Cluster) -> list[dict[str, Any]]:
    """The cluster's verified counterparty quotes, one per document."""
    ef = T["extraction_fields"]
    by_ext = {compiler.inp.docs[d].extraction_id: d for d in cluster}
    rows = {
        by_ext[r.extraction_id]: r
        for r in compiler.conn.execute(
            select(ef.c.extraction_id, ef.c.quote, ef.c.page, ef.c.find_query).where(
                ef.c.extraction_id.in_([e for e in by_ext if e]),
                ef.c.key == "counterparty",
                ef.c.verified,
            )
        )
    }
    out = []
    for d in cluster:
        r = rows.get(d)
        if r is not None:
            out.append(
                {
                    "document_id": d,
                    "field": "counterparty",
                    "page": r.page,
                    "quote": r.quote,
                    "verified": True,
                    "find_query": r.find_query,
                }
            )
    return out[:EVIDENCE_MAX]


def deterministic(compiler: Compiler, cluster: Cluster) -> Compiled | None:
    """A25 step 2: "always" to Mona's own proposal or "Ask me each time"; no model call."""
    docs = [compiler.inp.docs[d] for d in cluster]
    proposals = [(d.entity, d.category) for d in docs if d.entity and d.category]
    cps = {d.counterparty_id for d in docs}
    if not proposals or len(cps) != 1 or None in cps:
        return None
    entity, category = Counter(proposals).most_common(1)[0][0]
    confidence = next(d.confidence for d in docs if (d.entity, d.category) == (entity, category))
    snap = compiler.snap
    if entity not in snap.entities or category not in snap.categories:
        return None
    label = " / ".join(
        (
            snap.entities[entity]["display_name"],
            snap.categories[category]["labels"].get(compiler.lang)
            or snap.categories[category]["labels"]["en"],
        )
    )[:LABEL_MAX]
    alias_of = compiler.inp.alias_of
    draft = {
        "kind": "always",
        "discriminator": None,
        "branches": [
            {
                "conditions": [],
                "action": {
                    "entity": entity,
                    "unit": None,
                    "category": category,
                    "subcategory": None,
                },
            }
        ],
    }
    raw = {
        "text": t("interview.question.where", compiler.lang, counterparty=docs[0].counterparty),
        "affected": [alias_of[d] for d in cluster],
        "evidence": [],
        "options": [{"id": "a", "label": label, "rule_draft": draft}],
        "suggested": "a",
        "confidence": (confidence or 0) / 100,
    }
    q = compiler.question(raw, 0)
    if q is None:
        return None
    q.evidence = _evidence(compiler, cluster)
    q.made = "deterministic"
    return q


def cover(
    questions: list[Compiled],
    clusters: list[Cluster],
    *,
    targeted: Callable[[Cluster], Compiled | None] | None,
    fixed: Callable[[Cluster], Compiled | None],
) -> list[Compiled]:
    """While fewer than 7 questions, each uncovered cluster, largest first, gets one."""
    calls = 0
    for cluster in clusters:
        if len(questions) >= MAX_QUESTIONS:
            break
        if not uncovered(cluster, questions):
            continue
        q = None
        if targeted is not None and calls < MAX_TARGETED:
            calls += 1
            q = targeted(cluster)
        if q is None:
            q = fixed(cluster)
        if q is not None:
            q.model_order = max((x.model_order for x in questions), default=-1) + 1
            questions.append(q)
    return questions
