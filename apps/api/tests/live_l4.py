"""L4 runs on the seeded dev stack, inside the api container (synthetic documents only).

`python -m tests.live_l4 stage`: the 4:00 beat on recorded model output. Stop `worker-llm`
first; this process runs the llm queue itself with the recording bound.
`python -m tests.live_l4 smoke --runs N [--inline]`: live batch debriefs through the workers
(or this process) and the configured model, with the C6 §10 test 12 checks. Both replace
earlier L4 run rows.
"""

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select, text, update

from mona.interviews import answers, hooks
from mona.interviews.cache import cache_dir, fingerprint
from mona.interviews.config import PROMPT_VERSION
from mona.interviews.model import set_model_factory
from mona.services import undo
from mona.services.registry import T
from mona.settings import get_settings
from tests.l4_world import World, fixture, input_of, resolve_tags
from tests.rows import CLEANUP

API = "http://localhost:8765"
PEOPLE = {"Mme Anna Marchand": "christine", "M. Paul Marchand": "claudiu"}
STAGE = [  # demo-script positions 1-18 (19 is the duplicate, which never becomes a document)
    *[("filed", None, ())] * 10,
    ("review", "agipi-vie-anna", ("entity",)),
    ("review", "agipi-vie-paul", ("entity",)),
    ("review", "agipi-per-anna", ("entity",)),
    ("review", "hello-jan", ("entity",)),
    ("review", "hello-feb", ("entity",)),
    ("review", "hello-mar", ("entity",)),
    ("review", "unim", ("low",)),
    ("unreadable", None, ("unreadable",)),
]
STAGE_PEOPLE = {
    "agipi-vie-anna": "claudiu",
    "agipi-vie-paul": "christine",
    "agipi-per-anna": "christine",
}
ENTITIES = {"cabinet": "selarl-simina"}  # the C5 §8.5 fixture seed's practice entity → demo's


def log(step: str, **kw: Any) -> None:
    print(json.dumps({"step": step, **kw}, ensure_ascii=False, default=str), flush=True)


def check(ok: bool, what: str) -> None:
    if not ok:
        log("FAILED", check=what)
        sys.exit(1)


def reset(w: World) -> None:
    d, roots = T["documents"], w.ctx.ops.roots
    with w.engine.begin() as conn:
        for row in conn.execute(select(d.c.location, d.c.current_path)):
            root = {"archive": roots.archive, "inbox": roots.inbox}.get(row.location)
            if root is not None:
                (root / row.current_path).unlink(missing_ok=True)
        conn.execute(text("UPDATE rules SET origin_question_id = NULL WHERE source = 'interview'"))
        for stmt in CLEANUP:
            if stmt.startswith("DELETE FROM batches"):
                conn.execute(text("DELETE FROM rules WHERE source = 'interview'"))
            conn.execute(text(stmt))
        conn.execute(text("DELETE FROM procrastinate_jobs WHERE status IN ('todo', 'doing')"))
        has = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns WHERE table_name = 'settings'"
                " AND column_name = 'debrief_early_min'"
            )
        ).first()
        if not has:
            conn.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN debrief_early_min smallint NOT NULL"
                    " DEFAULT 5 CHECK (debrief_early_min BETWEEN 1 AND 50)"
                )
            )
            log("settings.debrief_early_min added (amendment A9 DDL; migration 0005 is L2's)")
    for p in cache_dir(w.ctx.textcache).glob("*.json"):
        p.unlink()


def world() -> World:
    """The test world on the stack's database and /data, keeping the real clock."""
    w = World()
    w.ctx.clock = w.ctx.ops.clock = lambda: datetime.now(UTC)
    w.clock.now = datetime.now(UTC) - timedelta(minutes=5)
    return w


def person_names(w: World) -> dict[str, str]:
    p = T["people"]
    with w.engine.connect() as conn:
        return dict(conn.execute(select(p.c.key, p.c.display_name)).all())


def spec_with(w: World, addressees: dict[str, str]) -> dict[str, Any]:
    """The S6 cluster, re-keyed to the demo seed when the stack holds it (`tag` or name → key)."""
    names = person_names(w)
    spec = fixture("cluster.json")
    for d in spec["docs"]:
        old = d.get("addressee") or ""
        key = addressees.get(d["tag"]) or addressees.get(old)
        if key:
            d["addressee"] = names[key]
            d["pages"] = [p.replace(old, names[key]) for p in d["pages"]]
        if d.get("entity"):
            d["entity"] = ENTITIES.get(d["entity"], d["entity"])
    for q in spec["pass2"]["questions"]:
        for o in q["options"]:
            for b in o["rule_draft"]["branches"]:
                b["action"]["entity"] = ENTITIES.get(b["action"]["entity"], b["action"]["entity"])
    return spec


def wait_jobs(w: World, task: str, timeout: float = 60) -> None:
    sql = text(
        "SELECT count(*) FROM procrastinate_jobs"
        " WHERE task_name = :t AND status IN ('todo', 'doing')"
    )
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with w.engine.connect() as conn:
            if not conn.execute(sql, {"t": task}).scalar_one():
                failed = conn.execute(
                    text(
                        "SELECT count(*) FROM procrastinate_jobs"
                        " WHERE task_name = :t AND status = 'failed'"
                    ),
                    {"t": task},
                ).scalar_one()
                check(failed == 0, f"no {task} job failed")
                return
        time.sleep(0.2)
    check(False, f"{task} jobs finished within {timeout} s")


def joined(path: list[str]) -> str:
    return "/".join(path)


# --- stage ---


class Replay:
    """The recorded S6 cluster passes; questions about documents not in the input are left out."""

    model = "recorded"

    def __init__(self, spec: dict[str, Any], tags: dict[str, str]):
        self.spec = spec
        self.tags = tags

    def stream(self, system: str, user: str, **kw: Any):
        yield "reasoning", "Thinking about the clusters. "
        yield "content", self.spec["pass1"]

    def complete_json(self, system: str, user: str, schema: dict, **kw: Any) -> dict:
        aliases = {d["alias"] for d in input_of(user)["documents"]}
        out = resolve_tags(self.spec["pass2"], user, self.tags)
        questions = []
        for q in out["questions"]:
            if set(q["affected"]) <= aliases:
                q["evidence"] = [e for e in q["evidence"] if e["doc"] in aliases]
                questions.append(q)
        return {"questions": questions}


def settle(w: World, doc_id: str, status: str, reasons: tuple) -> None:
    d = T["documents"]
    values: dict[str, Any] = {
        "status": status,
        "pipeline_stage": "done",
        "reasons": list(reasons),
    }
    with w.engine.begin() as conn:
        row = conn.execute(select(d).where(d.c.id == doc_id)).mappings().one()
        if status == "filed":
            target = w.ctx.ops.roots.archive / "Stage" / row["current_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            (w.ctx.ops.roots.inbox / row["current_path"]).rename(target)
            values |= {
                "location": "archive",
                "current_path": f"Stage/{row['current_path']}",
                "filed_at": datetime.now(UTC),
                "filed_by": "mona",
            }
        conn.execute(update(d).where(d.c.id == doc_id).values(**values))
        if status in ("review", "unreadable"):
            from mona.ids import new_id

            conn.execute(
                T["review_items"]
                .insert()
                .values(id=new_id("rev"), document_id=doc_id, reasons=list(reasons))
            )


def stage() -> None:
    w = world()
    reset(w)
    with w.engine.begin() as conn:
        conn.execute(text("UPDATE settings SET debrief_early_min = 7, debrief_queue_threshold = 5"))
    spec = spec_with(w, STAGE_PEOPLE)
    by_tag = {d["tag"]: d for d in spec["docs"]}
    batch = w.batch(status="running")
    docs: list[str] = []
    for n, (_, tag, _) in enumerate(STAGE, start=1):
        if tag:
            d = dict(by_tag[tag])
            d.pop("reasons")
            docs.append(
                w.doc(
                    d.pop("title"),
                    batch=batch,
                    status="processing",
                    stage="classifying",
                    reasons=(),
                    **d,
                )  # fmt: skip
            )
        else:
            docs.append(
                w.doc(
                    f"Stage stand-in {n}",
                    batch=batch,
                    status="processing",
                    stage="classifying",
                    reasons=(),
                    entity="selarl-simina",
                    category="bank",
                )  # fmt: skip
            )
    log("live batch", batch=batch, documents=len(docs))

    for n, ((outcome, _, reasons), doc_id) in enumerate(zip(STAGE, docs, strict=True), 1):
        settle(w, doc_id, outcome, reasons)
        last = n == len(STAGE)
        if last:
            b = T["batches"]
            with w.engine.begin() as conn:
                conn.execute(
                    update(b)
                    .where(b.c.id == batch)
                    .values(status="done", finished_at=datetime.now(UTC))
                )
        hooks.on_document_settled(batch)
        if last:
            hooks.on_batch_done(batch)
        wait_jobs(w, "debrief_check")
        ivs = w.interviews()
        if n < 17:
            check(not ivs, f"no interview after position {n}")
        else:
            check(len(ivs) == 1, f"exactly one interview after position {n}")
        if n == 17:
            iv = ivs[0]
            cands = iv["scope"]["candidate_document_ids"]
            check(iv["scope"]["type"] == "batch", "the early start is the batch debrief")
            check(sorted(cands) == sorted(docs[10:17]), "its snapshot is the 7 review documents")
            log("early start", position=n, interview=iv["id"], candidates=len(cands))
    log("batch done", interviews=len(w.interviews()), queue_debriefs=0)

    tags = {tag: doc_id for (_, tag, _), doc_id in zip(STAGE, docs, strict=True) if tag}
    set_model_factory(lambda: Replay(spec, tags))
    from mona.jobs import app as jobs_app

    t0 = time.monotonic()
    jobs_app.run_worker(queues=["llm"], wait=False, install_signal_handlers=False)
    interview_id = w.interviews()[0]["id"]
    with httpx.Client(base_url=API, timeout=30) as api:
        iv = api.get(f"/api/interviews/{interview_id}").json()
        check(iv["status"] == "ready", "the debrief is ready")
        check(iv["openQuestions"] == 3, "the banner data says 3 questions")
        asked = [q["question"] for q in iv["questions"]]
        log("debrief ready", seconds=round(time.monotonic() - t0, 2), source=iv["source"],
            questions=asked, open_questions=iv["openQuestions"])  # fmt: skip

        agipi = {tags["agipi-vie-anna"], tags["agipi-vie-paul"], tags["agipi-per-anna"]}
        q = next(q for q in iv["questions"] if set(q["affects"]) == agipi)
        option = next(o for o in q["options"] if o["suggested"])
        r = api.post(
            f"/api/interviews/{interview_id}/questions/{q['id']}/answer",
            json={"optionId": option["id"]},
        )
        check(r.status_code == 200, f"the AGIPI answer is accepted ({r.status_code})")
        res = r.json()
        check(len(res["rules"]) == 2 and len(res["previews"]) == 2, "2 draft rules, 2 previews")
        moves = {m["documentId"]: m["to"] for p in res["previews"] for m in p["moves"]}
        expect = {
            tags["agipi-vie-anna"]: ("Assurance vie", "Claudiu"),
            tags["agipi-vie-paul"]: ("Assurance vie", "Christine"),
            tags["agipi-per-anna"]: ("PER", "Christine"),
        }
        for doc_id, (product, unit) in expect.items():
            to = moves.get(doc_id, [])
            check(product in to and unit in to, f"{doc_id} previews under {unit}, {product}: {to}")
        log("AGIPI answered", option=option["label"], rules=[x["name"] for x in res["rules"]],
            previews=[joined(m) for m in moves.values()])  # fmt: skip

        r = api.post(f"/api/interviews/{interview_id}/questions/{q['id']}/apply", json={})
        check(r.status_code == 200, f"Apply all ({r.status_code})")
        results = r.json()["results"]
        groups = [x["groupId"] for x in results]
        check(len(groups) == 2 and all(groups), "one group per rule")
        check(sum(x["moved"] for x in results) == 3, "3 documents moved")
    rule_ids = [x["id"] for x in res["rules"]]
    before = placement(w, list(agipi))
    check(all(p[0] == "archive" and p[2] for p in before.values()), "moved and on disk")
    check(states(w, rule_ids) == ["active", "active"], "both rules active after Apply all")
    log("applied", groups=groups, placement={k: v[1] for k, v in before.items()})

    undone = [undo(w.ctx, actor="user", via="ui", group_id=g) for g in groups]
    after_undo = placement(w, list(agipi))
    check(all(p[0] == "inbox" and p[2] for p in after_undo.values()), "files back in the inbox")
    check(states(w, rule_ids) == ["draft", "draft"], "rules back to draft")
    log("group undo", rule_states=[u.rule_states for u in undone])

    redone = [undo(w.ctx, actor="user", via="ui", group_id=u.group_id) for u in undone]
    after_redo = placement(w, list(agipi))
    check(after_redo == before, "redo puts every file back where Apply all put it")
    check(states(w, rule_ids) == ["active", "active"], "rules active again")
    log("redo", rule_states=[r.rule_states for r in redone])
    log("STAGE OK")


def placement(w: World, doc_ids: list[str]) -> dict[str, tuple[str, str, bool]]:
    d = T["documents"]
    out = {}
    with w.engine.connect() as conn:
        for row in conn.execute(select(d).where(d.c.id.in_(doc_ids))).mappings():
            root = (
                w.ctx.ops.roots.archive if row["location"] == "archive" else w.ctx.ops.roots.inbox
            )
            on_disk = (root / row["current_path"]).is_file()
            out[row["id"]] = (row["location"], row["current_path"], on_disk)
    return out


def states(w: World, rule_ids: list[str]) -> list[str]:
    r = T["rules"]
    with w.engine.connect() as conn:
        by_id = dict(conn.execute(select(r.c.id, r.c.state).where(r.c.id.in_(rule_ids))).all())
    return [by_id[i] for i in rule_ids]


# --- smoke ---


def smoke(runs: int, inline: bool) -> None:
    w = world()
    reset(w)
    w.set_settings(debrief_queue_threshold=50)
    demo = "cabinet" not in w.ids("entities")
    log("model", model=get_settings().mona_llm_model, registry="demo" if demo else "C5 §8.5")
    summary = []
    for run in range(1, runs + 1):
        w = world()
        batch = w.batch(status="done")
        tags = w.cluster(batch, spec_with(w, PEOPLE if demo else {}))
        t0 = time.monotonic()
        hooks.on_batch_done(batch)
        iv = None
        while time.monotonic() - t0 < 240:
            if inline:
                from mona.jobs import app as jobs_app

                jobs_app.run_worker(
                    queues=["cpu", "llm"], wait=False, install_signal_handlers=False
                )
            ivs = [x for x in w.interviews() if x["batch_id"] == batch]
            if ivs and ivs[0]["status"] != "generating":
                iv = ivs[0]
                break
            time.sleep(0.5)
        check(iv is not None, "the debrief finished within 240 s")
        wall = time.monotonic() - t0
        out = {"run": run, "status": iv["status"], "error": iv["error"], "wall_s": round(wall, 1)}
        if iv["status"] == "ready":
            out |= judge(w, iv, tags)
        log("smoke run", **out)
        summary.append(out)
    log("smoke summary", runs=summary)


def judge(w: World, iv: Any, tags: dict[str, str]) -> dict[str, Any]:
    """C6 §10 test 12 on one ready debrief."""
    qs = w.questions(iv["id"])
    d = T["documents"]
    cands = iv["scope"]["candidate_document_ids"]
    with w.engine.connect() as conn:
        shas = list(conn.execute(select(d.c.sha256).where(d.c.id.in_(cands))).scalars())
    raw_path = (
        cache_dir(w.ctx.textcache) / f"{fingerprint(shas)}.{PROMPT_VERSION}.{iv['lang']}.json"
    )
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    kept = {q["text"] for q in qs}
    raw_evidence = sum(len(q["evidence"]) for q in raw["questions"] if q["text"] in kept)
    kept_evidence = sum(len(q["evidence"]) for q in qs)
    agipi = {tags["agipi-per-anna"]: "PER", tags["agipi-vie-anna"]: "Assurance vie",
             tags["agipi-vie-paul"]: "Assurance vie"}  # fmt: skip
    q = next((q for q in qs if set(agipi) & set(q["affected_document_ids"])), None)
    out: dict[str, Any] = {
        "ready_s": round((iv["ready_at"] - iv["created_at"]).total_seconds(), 1),
        "questions": len(qs),
        "questions_returned": len(raw["questions"]),
        "evidence_returned": raw_evidence,
        "evidence_verified": kept_evidence,
        "agipi_question": q is not None,
    }
    if q is None:
        return out
    option = next(o for o in q["options"] if o["suggested"])
    draft = option["rule_draft"]
    out |= {
        "agipi_affects_all_three": set(agipi) <= set(q["affected_document_ids"]),
        "agipi_suggested": f"{draft['kind']} on {draft['discriminator']}",
        "agipi_from_person": all(
            b["action"].get("unit") == {"from": "person"} for b in draft["branches"]
        ),
    }
    res = answers.answer(w.ctx, q["id"], option_id=option["id"], actor="user", via="ui")
    moves = {m.document_id: list(m.to) for p in res.previews for m in p.moves}
    out["agipi_products"] = {
        tag: next((p for p in ("PER", "Assurance vie") if p in moves.get(doc_id, [])), None)
        for tag, doc_id in tags.items()
        if doc_id in agipi
    }
    out["agipi_products_ok"] = all(agipi[doc_id] in moves.get(doc_id, []) for doc_id in agipi)
    units = person_units(w, list(agipi))
    out["agipi_people_ok"] = all(units[doc_id] in moves.get(doc_id, []) for doc_id in agipi)
    return out


def person_units(w: World, doc_ids: list[str]) -> dict[str, str | None]:
    """The personal sub-unit label of each document's addressee person."""
    d, s = T["documents"], T["sub_units"]
    with w.engine.connect() as conn:
        rows = conn.execute(
            select(d.c.id, s.c.label).outerjoin(s, s.c.person_id == d.c.addressee_person_id)
            .where(d.c.id.in_(doc_ids))
        ).all()  # fmt: skip
    return dict(rows)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("mona.interviews.generate").setLevel(logging.INFO)
    if get_settings().mona_env != "dev":
        sys.exit("refusing: MONA_ENV is not dev")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stage")
    s = sub.add_parser("smoke")
    s.add_argument("--runs", type=int, default=1)
    s.add_argument("--inline", action="store_true", help="run the jobs in this process")
    args = parser.parse_args()
    stage() if args.cmd == "stage" else smoke(args.runs, args.inline)


if __name__ == "__main__":
    main()
