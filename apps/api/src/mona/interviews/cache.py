"""C6 §4.7: the cached debrief, bound to live documents by sha256."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection

from mona.interviews.candidates import clusters, load_docs
from mona.interviews.compile import Compiled, Compiler
from mona.interviews.config import MAX_QUESTIONS
from mona.interviews.coverage import about, cover, deterministic
from mona.interviews.prompt import Input

V = 1


def fingerprint(shas: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(shas)).encode()).hexdigest()[:32]


def cache_dir(textcache: Path) -> Path:
    return textcache / "debrief"


def write(
    textcache: Path,
    *,
    prompt_version: str,
    lang: str,
    candidate_shas: list[str],
    output: dict[str, Any],
    sha_of: dict[str, str],
    now: datetime,
    targeted: list[dict[str, Any]] | None = None,
) -> Path:
    """Pass 2's raw output, then the kept targeted questions (A25), with every alias replaced
    by its document's sha256."""

    def shas(aliases: list[str]) -> list[str]:
        return [sha_of[a] for a in aliases if a in sha_of]

    def question(q: dict[str, Any], made: str) -> dict[str, Any]:
        return {
            "text": q["text"],
            "affected_sha256s": shas(q["affected"]),
            "evidence": [
                {"sha256": sha_of[e["doc"]], "quote": e["quote"]}
                for e in q.get("evidence", [])
                if e.get("doc") in sha_of
            ],
            "options": [
                {"id": o["id"], "label": o["label"], "rule_draft": o["rule_draft"]}
                for o in q["options"]
            ],
            "suggested": q["suggested"],
            "confidence": q["confidence"],
            "made": made,
        }

    doc = {
        "v": V,
        "prompt_version": prompt_version,
        "lang": lang,
        "created_at": now.isoformat(),
        "candidate_sha256s": sorted(candidate_shas),
        "questions": [question(q, "pass2") for q in output.get("questions", [])]
        + [question(q, "targeted") for q in targeted or []],
    }
    d = cache_dir(textcache)
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{fingerprint(candidate_shas)}.{prompt_version}.{lang}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, target)
    return target


@dataclass
class Match:
    path: Path
    questions: list[Compiled]
    created_at: str


def _as_output(cached: dict[str, Any], alias_of_sha: dict[str, str]) -> dict[str, Any]:
    """§4.7 step 1: keep live candidates only, then the pass-2 shape in live aliases."""
    questions = []
    for q in cached.get("questions", []):
        affected = [alias_of_sha[s] for s in q.get("affected_sha256s", []) if s in alias_of_sha]
        if not affected:
            continue
        questions.append(
            {
                "text": q["text"],
                "affected": affected,
                "evidence": [
                    {"doc": alias_of_sha[e["sha256"]], "quote": e["quote"]}
                    for e in q.get("evidence", [])
                    if e.get("sha256") in alias_of_sha
                ],
                "options": q["options"],
                "suggested": q.get("suggested"),
                "confidence": q.get("confidence", 0),
                "made": q.get("made", "pass2"),
            }
        )
    return {"questions": questions}


def _compile(compiler: Compiler, questions: list[dict[str, Any]]) -> list[Compiled]:
    """§4.5 on pass 2's questions, then each targeted one about its cluster while there is room."""
    out = compiler.run({"questions": [q for q in questions if q["made"] != "targeted"]})
    for q in questions:
        if q["made"] != "targeted" or len(out) >= MAX_QUESTIONS:
            continue
        for c in compiler.run({"questions": [q]}):
            if not about(compiler, c.affected, c.text):
                continue
            c.made = "targeted"
            c.model_order = max((x.model_order for x in out), default=-1) + 1
            out.append(c)
    return out


def match(
    conn: Connection,
    textcache: Path,
    *,
    prompt_version: str,
    lang: str,
    candidate_ids: list[str],
) -> Match | None:
    """The cache file with the most questions surviving §4.5 against the live documents."""
    d = cache_dir(textcache)
    if not d.is_dir():
        return None
    docs = load_docs(conn, candidate_ids)
    inp = Input(body={})
    alias_of_sha: dict[str, str] = {}
    for n, doc in enumerate(docs, start=1):
        alias = f"d{n}"
        inp.aliases[alias] = doc.id
        inp.docs[doc.id] = doc
        alias_of_sha[doc.sha256] = alias
    best: Match | None = None
    for path in sorted(d.glob(f"*.{prompt_version}.{lang}.json")):
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if cached.get("v") != V or cached.get("prompt_version") != prompt_version:
            continue
        if cached.get("lang") != lang:
            continue
        output = _as_output(cached, alias_of_sha)
        compiled = _compile(Compiler(conn, inp, lang, textcache), output["questions"])
        if not compiled:
            continue
        created = str(cached.get("created_at", ""))
        if best is None or (len(compiled), created) > (len(best.questions), best.created_at):
            best = Match(path, compiled, created)
    if best is not None:
        compiler = Compiler(conn, inp, lang, textcache)
        cover(
            best.questions,
            [[d.id for d in c.docs] for c in clusters(docs)],
            targeted=None,
            fixed=lambda cluster: deterministic(compiler, cluster),
        )
    return best
