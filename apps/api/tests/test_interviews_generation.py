"""C6 §10 tests 1, 4, 6, 7, 10, 11, 13 and the §4.8 budgets, on recorded model output."""

import json
import threading
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import delete, text, update

from mona.interviews import answers, service
from mona.interviews.candidates import candidates
from mona.interviews.compile import Compiler
from mona.interviews.generate import CUT_PREFIX, generate_interview
from mona.interviews.prompt import build_input
from mona.interviews.schema import build, errors, registry_enums, strings_bounded
from mona.rules import store
from mona.rules.grammar import RuleBody
from mona.services.registry import T
from tests.l4_world import RecordedModel, World, fixture, input_of, resolve_tags

pytestmark = pytest.mark.usefixtures("l4_db")


def make_rule(w: World, key: str, conditions: list, action: dict, state: str = "active") -> str:
    with w.engine.begin() as conn:
        row, _ = store.save_rule(
            conn,
            key=key,
            name=key,
            state=state,
            source="interview",
            body=RuleBody.model_validate({"conditions": conditions, "action": action}),
            priority=None,
            names=store.names(conn),
        )
    return row["id"]


def start_batch(w: World, b: str, lang: str = "en") -> str:
    return service.start(w.ctx, {"type": "batch", "batch_id": b}, lang=lang).interview_id


def run(w: World, interview_id: str, model: RecordedModel) -> str:
    return generate_interview(w.ctx, interview_id, model_factory=lambda: model, clock=w.clock)


def analysis_sent(model: RecordedModel) -> str:
    return next(c for c in model.calls if c["pass"] == 2)["user"].split("\n\nAnalysis:\n", 1)[1]


# --- test 1: candidates ---


def test_candidates_exclude_unreadable_asked_and_visitor_documents():
    w = World()
    make_rule(
        w,
        "ask-opco",
        [{"field": "counterparty", "op": "equals", "value": "opco"}],
        {"review": True},
    )
    b, vb = w.batch(), w.batch(visitor=True)
    excluded = {
        w.doc("scan", batch=b, reasons=["unreadable"], status="unreadable"),
        w.doc("asked", batch=b, reasons=["low"], counterparty="opco", rule="ask-opco"),
        w.doc("visitor bill", batch=vb, reasons=["entity"]),
        w.doc("filed", batch=b, status="filed", reasons=[], path="Cabinet Marchand/x.pdf"),
    }
    included = {
        w.doc("conflict", batch=b, reasons=["conflict"]),
        w.doc("entity", batch=b, reasons=["entity"]),
        w.doc("low", batch=b, reasons=["low"], counterparty="unim"),
        w.doc(
            "asked but also entity",
            batch=b,
            reasons=["low", "entity"],
            counterparty="opco",
            rule="ask-opco",
        ),
    }
    with w.engine.connect() as conn:
        ids = {d.id for d in candidates(conn, {"type": "queue"})}
    assert included <= ids
    assert not excluded & ids


def test_a_listed_filed_document_is_a_candidate_of_a_documents_scope():
    w = World()
    b = w.batch()
    filed = w.doc("filed", batch=b, status="filed", reasons=[], path="Cabinet Marchand/y.pdf")
    with w.engine.connect() as conn:
        assert [d.id for d in candidates(conn, {"type": "documents", "document_ids": [filed]})] == [
            filed
        ]


def test_the_40_cap_keeps_the_largest_clusters():
    w = World()
    b = w.batch()
    big = {w.doc(f"agipi {n}", batch=b, counterparty="agipi") for n in range(30)}
    mid = {w.doc(f"hello {n}", batch=b, counterparty="hello-bank") for n in range(10)}
    small = {w.doc(f"single {n}", batch=b, extracted_counterparty=f"Shop {n}") for n in range(5)}
    with w.engine.connect() as conn:
        ids = {d.id for d in candidates(conn, {"type": "queue"})}
    assert ids == big | mid
    assert not small & ids


# --- test 4: time box [M] ---


def test_pass1_is_cut_at_the_budget_and_pass2_gets_the_working_notes(monkeypatch):
    monkeypatch.setenv("MONA_INTERVIEW_PASS1_BUDGET_S", "35")
    w = World()
    w.cluster(w.batch())
    interview_id = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    events = [("reasoning", f"step {n}. ") for n in range(200)] + [("content", "FINAL")]
    model = RecordedModel(w, pass1=events, step_s=1.0)
    assert run(w, interview_id, model) == "ready"
    notes = analysis_sent(model)
    assert notes.startswith(CUT_PREFIX)
    assert "step 34." in notes and "step 36." not in notes and "FINAL" not in notes
    iv = w.row("interviews", interview_id)
    assert (iv["status"], iv["analysis"]) == ("ready", notes)


def test_pass1_in_time_keeps_its_content_and_empty_content_keeps_the_notes():
    w = World()
    w.cluster(w.batch())
    first = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    model = RecordedModel(w, pass1=[("reasoning", "hmm "), ("content", "- AGIPI: split.")])
    run(w, first, model)
    assert analysis_sent(model) == "- AGIPI: split."
    service.cancel(w.ctx, first)
    second = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    model = RecordedModel(w, pass1=[("reasoning", "only thinking"), ("content", "  ")])
    run(w, second, model)
    assert analysis_sent(model) == CUT_PREFIX + "only thinking  "


def test_the_log_line_carries_the_pass_timings_and_no_document_text(caplog):
    w = World()
    w.cluster(w.batch())
    interview_id = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    with caplog.at_level("INFO", logger="mona.interviews.generate"):
        run(w, interview_id, RecordedModel(w))
    (line,) = [r.getMessage() for r in caplog.records if interview_id in r.getMessage()]
    assert "ready, pass 1 " in line and ", pass 2 " in line and line.endswith(" questions")
    assert "AGIPI" not in line


def test_a_stream_that_breaks_after_some_reasoning_keeps_the_notes():
    w = World()
    w.cluster(w.batch())
    interview_id = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    model = RecordedModel(w, pass1=[("reasoning", "partial thoughts")])
    model.pass1.append(("error", "read timeout"))
    assert run(w, interview_id, model) == "ready"
    assert analysis_sent(model) == CUT_PREFIX + "partial thoughts"


# --- test 6: checks and compile [M] ---

BRANCH = {
    "conditions": [{"field": "counterparty", "op": "equals", "value": "AGIPI"}],
    "action": {"entity": "personal", "unit": None, "category": "insurance", "subcategory": None},
}


def opt(id_: str, kind: str, branches: list, discriminator=None, label: str = "x") -> dict:
    return {
        "id": id_,
        "label": label,
        "rule_draft": {"kind": kind, "discriminator": discriminator, "branches": branches},
    }


def with_action(**action) -> dict:
    return {**BRANCH, "action": {**BRANCH["action"], **action}}


def on_text(words: str, subcategory: str) -> dict:
    branch = with_action(subcategory=subcategory)
    return {
        **branch,
        "conditions": [*BRANCH["conditions"], {"field": "text", "op": "contains", "value": words}],
    }


@pytest.fixture
def compiled():
    """One stubbed pass-2 output through §4.5, against the recorded cluster."""
    w = World()
    tags = w.cluster(w.batch())
    agipi = [tags["agipi-per-anna"], tags["agipi-vie-anna"], tags["agipi-vie-paul"]]
    per_only = [tags["agipi-per-anna"]]
    with w.engine.connect() as conn:
        inp = build_input(conn, sorted(tags.values()), "en", w.ctx.textcache, w.clock())
        a = inp.alias_of
        q = lambda ids, options, **kw: {  # noqa: E731
            "text": kw.get("text", "Q?"),
            "affected": [a[i] for i in ids],
            "evidence": kw.get("evidence", []),
            "options": options,
            "suggested": kw.get("suggested", "a"),
            "confidence": kw.get("confidence", 0.8),
        }
        no_cp = {
            "conditions": [{"field": "text", "op": "contains", "value": "AGIPI"}],
            "action": BRANCH["action"],
        }
        by_name = {
            "conditions": [{"field": "counterparty", "op": "equals", "value": "AGIPI Assurance"}],
            "action": BRANCH["action"],
        }
        output = {
            "questions": [
                q(
                    agipi,
                    [
                        opt("a", "depends", [BRANCH, BRANCH]),
                        opt("b", "always", [BRANCH, BRANCH]),
                        opt("c", "always", [BRANCH]),
                    ],
                    suggested="a",
                    confidence=0.724,
                    evidence=[
                        {"doc": a[tags["agipi-per-anna"]], "quote": "not printed anywhere"},
                        {"doc": a[tags["agipi-vie-paul"]], "quote": "Assuré : M. Paul Marchand"},
                        {"doc": a[tags["hello-jan"]], "quote": "LOYER ANGERS STRASBOURG"},
                    ],
                ),
                q(
                    agipi,
                    [
                        opt("a", "always", [with_action(entity=None)]),
                        opt(
                            "b",
                            "always",
                            [with_action(entity="cabinet", unit="lmnp/angers-strasbourg")],
                        ),
                        opt("c", "ask", []),
                    ],
                    text="only ask survives",
                ),
                q(
                    agipi,
                    [opt("a", "always", [no_cp]), opt("b", "always", [by_name])],
                    text="prepend and resolve",
                ),
                q(
                    agipi,
                    [opt("a", "always", [with_action(subcategory="insurance.per")])],
                    text="mixed subcategories",
                ),
                q(
                    per_only,
                    [opt("a", "always", [with_action(subcategory="insurance.per")])],
                    text="one subcategory",
                ),
                q(
                    agipi,
                    [opt("a", "always", [with_action(subcategory="bank.releve")])],
                    text="subcategory of another category",
                ),
                q(
                    agipi,
                    [
                        opt("a", "always", [on_text("épargne retraite", "insurance.per")]),
                        opt(
                            "b",
                            "depends",
                            [
                                on_text("épargne retraite", "insurance.per"),
                                on_text("assurance vie", "insurance.assurance_vie"),
                            ],
                            discriminator="text",
                        ),
                    ],
                    text="always settles every affected document, a branch its own",
                ),
            ]
        }
        out = Compiler(conn, inp, "en", w.ctx.textcache).run(output)
    return {c.text: c for c in out}, tags


def test_evidence_is_verified_on_its_page_and_kept_only_for_affected_documents(compiled):
    by_text, tags = compiled
    ev = by_text["Q?"].evidence
    assert len(ev) == 1
    assert ev[0]["document_id"] == tags["agipi-vie-paul"]
    assert ev[0]["page"] == 2 and ev[0]["verified"] is True
    assert ev[0]["find_query"] == "Assuré : M. Paul Marchand"


def test_evidence_find_query_is_the_pipelines_and_never_crosses_a_column():
    w = World()
    page = (
        "AGIPI Retraite                              M. Paul Marchand\n"
        "Plan d'épargne retraite                     12 rue des Lilas"
    )
    doc = w.doc("AGIPI PER", batch=w.batch(), counterparty="agipi", pages=[page])
    with w.engine.connect() as conn:
        inp = build_input(conn, [doc], "en", w.ctx.textcache, w.clock())
        quotes = ["AGIPI Retraite M. Paul Marchand", "Plan d'épargne retraite"]
        output = {
            "questions": [
                {
                    "text": "Q?",
                    "affected": [inp.alias_of[doc]],
                    "evidence": [{"doc": inp.alias_of[doc], "quote": q} for q in quotes],
                    "options": [opt("a", "always", [BRANCH])],
                    "suggested": "a",
                    "confidence": 0.8,
                }
            ]
        }
        [compiled] = Compiler(conn, inp, "en", w.ctx.textcache).run(output)
    assert [e["verified"] for e in compiled.evidence] == [True, True]
    assert [e["find_query"] for e in compiled.evidence] == [
        "M. Paul Marchand",
        "Plan d'épargne retraite",
    ]


def test_invalid_options_are_dropped_and_ask_is_appended(compiled):
    by_text, _ = compiled
    q1 = by_text["Q?"]
    assert [(o["id"], o["rule_draft"]["kind"]) for o in q1.options] == [
        ("c", "always"),
        ("a", "ask"),
    ]
    assert q1.options[1]["label"] == "Ask me each time"
    assert "only ask survives" not in by_text


def test_exactly_one_option_is_suggested_and_confidence_is_rounded(compiled):
    q1 = compiled[0]["Q?"]
    assert [o["suggested"] for o in q1.options] == [True, False]
    assert q1.suggestion_confidence == 72


def test_counterparty_condition_prepended_and_names_resolved_to_keys(compiled):
    q = compiled[0]["prepend and resolve"]
    a, b = (o["rule_draft"]["branches"][0]["conditions"] for o in q.options[:2])
    assert a[0] == {"field": "counterparty", "op": "equals", "value": "agipi"}
    assert a[1]["field"] == "text"
    assert b == [{"field": "counterparty", "op": "equals", "value": "agipi"}]


def test_a_fixed_subcategory_survives_only_when_the_settled_documents_agree(compiled):
    by_text, _ = compiled
    mixed = by_text["mixed subcategories"].options[0]["rule_draft"]["branches"][0]["action"]
    same = by_text["one subcategory"].options[0]["rule_draft"]["branches"][0]["action"]
    other = by_text["subcategory of another category"].options[0]["rule_draft"]["branches"][0]
    assert "subcategory" not in mixed
    assert same["subcategory"] == "per"
    assert "subcategory" not in other["action"]
    always, depends = (
        o["rule_draft"]
        for o in by_text["always settles every affected document, a branch its own"].options[:2]
    )
    assert "subcategory" not in always["branches"][0]["action"]
    assert [b["action"]["subcategory"] for b in depends["branches"]] == ["per", "assurance_vie"]


# --- test 5: schema; the cap of 7 questions [M] ---


def test_the_schema_bounds_every_string_and_accepts_the_recorded_branch_output():
    w = World()
    w.cluster(w.batch())
    with w.engine.connect() as conn:
        inp = build_input(conn, sorted(w.tags.values()), "en", w.ctx.textcache, w.clock())
        enums = registry_enums(conn)
    schema = build(list(inp.aliases), enums)
    assert strings_bounded(schema)
    assert "visitors" not in enums["entities"] and "personal" in enums["entities"]
    assert not any(u.startswith("visitors/") for u in enums["units"])
    output = resolve_tags(fixture("cluster.json")["pass2"], inp.text(), w.tags)
    assert errors(output, schema) == []
    outside = deepcopy(output)
    outside["questions"][0]["affected"].append(f"d{len(inp.aliases) + 1}")
    assert errors(outside, schema)
    visitors = deepcopy(output)
    visitors["questions"][0]["options"][1]["rule_draft"]["branches"][0]["action"]["entity"] = (
        "visitors"
    )
    assert errors(visitors, schema)


def test_at_most_seven_questions_reach_the_interview():
    w = World()
    w.cluster(w.batch())
    with w.engine.connect() as conn:
        inp = build_input(conn, sorted(w.tags.values()), "en", w.ctx.textcache, w.clock())
        output = resolve_tags(fixture("cluster.json")["pass2"], inp.text(), w.tags)
        first = output["questions"][0]
        eight = {"questions": [{**first, "text": f"Q{n}"} for n in range(8)]}
        schema = build(list(inp.aliases), registry_enums(conn))
        assert schema["properties"]["questions"]["maxItems"] == 7
        assert errors(eight, schema)
        kept = Compiler(conn, inp, "en", w.ctx.textcache).run(eight)
    assert [c.text for c in kept] == [f"Q{n}" for n in range(7)]


# --- test 7: ordering and impact ---


def test_questions_are_stored_by_impact_with_ordinals():
    w = World()
    b = w.batch()
    w.cluster(b)
    for n in range(3):
        w.doc(
            f"UNIM archive {n}",
            batch=b,
            status="filed",
            reasons=[],
            counterparty="unim",
            path=f"Cabinet Marchand/unim-{n}.pdf",
        )
    interview_id = start_batch(w, b)
    assert run(w, interview_id, RecordedModel(w)) == "ready"
    qs = w.questions(interview_id)
    assert [q["ordinal"] for q in qs] == list(range(1, len(qs) + 1))
    assert [q["impact"] for q in qs] == [4, 3, 3, 2, 1]
    assert qs[0]["text"].startswith("Is UNIM")
    assert qs[1]["text"].startswith("How should AGIPI")


# --- test 10: the cached debrief [M] ---


def _reload(w: World, spec: dict, contents: dict[str, bytes], skip_review: set[str]) -> str:
    """demo-reset stand-in: the same bytes as fresh documents with new ids."""
    with w.engine.begin() as conn:
        conn.execute(text("UPDATE batches SET debrief_interview_id = NULL"))
        conn.execute(text("DELETE FROM interviews"))
        conn.execute(text("UPDATE documents SET filed_op_id = NULL"))
        conn.execute(text("DELETE FROM file_ops"))
        conn.execute(text("DELETE FROM op_groups"))
        conn.execute(text("DELETE FROM documents"))
        conn.execute(text("DELETE FROM batches"))
    w.tags.clear()
    b = w.batch(status="running")
    for d in spec["docs"]:
        d = dict(d)
        tag = d["tag"]
        status = "filed" if tag in skip_review else "review"
        extra = {"path": f"LMNP/{tag}.pdf", "reasons": []} if status == "filed" else {}
        w.doc(d.pop("title"), batch=b, content=contents[tag], status=status, **{**d, **extra})
    return b


@pytest.fixture
def cached(monkeypatch):
    """A live (recorded) batch debrief that wrote its cache file."""
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "fallback")
    w = World()
    spec = fixture("cluster.json")
    b = w.batch()
    w.cluster(b, spec)
    contents = {}
    for tag, doc_id in w.tags.items():
        row = w.row("documents", doc_id)
        contents[tag] = (w.ctx.ops.roots.inbox / row["current_path"]).read_bytes()
    interview_id = start_batch(w, b)
    assert run(w, interview_id, RecordedModel(w)) == "ready"
    files = list((w.ctx.textcache / "debrief").glob("*.c6-v1.en.json"))
    assert len(files) == 1
    return w, spec, contents, files[0]


def test_the_cache_file_holds_raw_forms_and_sha256s_only(cached):
    w, _, _, path = cached
    raw = path.read_text(encoding="utf-8")
    body = json.loads(raw)
    assert body["prompt_version"] == "c6-v1" and body["lang"] == "en"
    assert '"from_person"' in raw and '"insurance.per"' in raw and '"lmnp/angers-strasbourg"' in raw
    assert "doc_" not in raw
    shas = {q for question in body["questions"] for q in question["affected_sha256s"]}
    assert shas <= set(body["candidate_sha256s"])


def test_prefer_binds_the_cache_to_fresh_ids_by_sha256(cached, monkeypatch):
    w, spec, contents, _ = cached
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "prefer")
    b = _reload(w, spec, contents, skip_review={"hello-mar"})
    interview_id = start_batch(w, b)
    model = RecordedModel(w)
    assert run(w, interview_id, model) == "cache"
    assert model.calls == []
    iv = w.row("interviews", interview_id)
    assert iv["status"] == "ready" and iv["analysis"] is None
    qs = w.questions(interview_id)
    assert len(qs) == 5
    hello = next(q for q in qs if q["text"].startswith("Are the Hello"))
    assert set(hello["affected_document_ids"]) == {w.tags["hello-jan"], w.tags["hello-feb"]}
    agipi = next(q for q in qs if q["text"].startswith("How should AGIPI"))
    assert {e["document_id"] for e in agipi["evidence"]} <= set(w.tags.values())


def test_a_registry_change_drops_only_the_option_it_invalidates(cached, monkeypatch):
    w, spec, contents, _ = cached
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "prefer")
    b = _reload(w, spec, contents, skip_review=set())
    with w.engine.begin() as conn:
        conn.execute(update(T["accounts"]).values(sub_unit_id=None))
        conn.execute(delete(T["sub_units"]).where(T["sub_units"].c.key == "angers-strasbourg"))
    interview_id = start_batch(w, b)
    assert run(w, interview_id, RecordedModel(w)) == "cache"
    hello = next(q for q in w.questions(interview_id) if q["text"].startswith("Are the Hello"))
    assert [o["label"] for o in hello["options"]] == ["Personal", "Ask me each time"]


def test_fallback_uses_the_cache_when_pass2_stalls_past_60s(cached, monkeypatch):
    w, spec, contents, _ = cached
    b = _reload(w, spec, contents, skip_review=set())
    interview_id = start_batch(w, b)
    release = threading.Event()

    def stall() -> None:
        w.clock.advance(seconds=61)
        release.wait(10)

    model = RecordedModel(w, on_pass2=stall)
    try:
        assert run(w, interview_id, model) == "cache"
    finally:
        release.set()
    iv = w.row("interviews", interview_id)
    assert iv["status"] == "ready" and iv["analysis"] is None
    assert len(w.questions(interview_id)) == 5


def test_a_cache_file_in_another_language_does_not_match(cached, monkeypatch):
    w, spec, contents, _ = cached
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "prefer")
    b = _reload(w, spec, contents, skip_review=set())
    interview_id = start_batch(w, b, lang="fr")
    model = RecordedModel(w)
    assert run(w, interview_id, model) == "ready"
    assert len(model.calls) == 2
    assert w.row("interviews", interview_id)["analysis"] is not None


# --- test 11: states; §4.8 budgets and failure ---


def test_pass2_is_retried_once_then_the_interview_fails():
    w = World()
    w.cluster(w.batch())
    first = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    assert run(w, first, RecordedModel(w, pass2_errors=1)) == "ready"
    service.cancel(w.ctx, first)
    second = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    assert run(w, second, RecordedModel(w, pass2_errors=2)) == "generation_failed"
    row = w.row("interviews", second)
    assert (row["status"], row["error"]) == ("failed", "generation_failed")


def test_no_surviving_question_fails_with_no_questions():
    w = World()
    w.cluster(w.batch())
    interview_id = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    bad = deepcopy(fixture("cluster.json")["pass2"])
    for q in bad["questions"]:
        for o in q["options"]:
            o["rule_draft"] = {"kind": "ask", "discriminator": None, "branches": []}
    assert run(w, interview_id, RecordedModel(w, pass2=bad)) == "failed"
    row = w.row("interviews", interview_id)
    assert (row["status"], row["error"]) == ("failed", "no_questions")


def test_the_job_cap_fails_a_stalled_run_with_timeout(monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    b = w.batch()
    w.cluster(b)
    interview_id = start_batch(w, b)
    release = threading.Event()

    def stall() -> None:
        w.clock.advance(seconds=151)
        release.wait(10)

    try:
        assert run(w, interview_id, RecordedModel(w, on_pass2=stall)) == "timeout"
    finally:
        release.set()
    row = w.row("interviews", interview_id)
    assert (row["status"], row["error"]) == ("failed", "timeout")


def test_a_cancelled_generating_interview_discards_the_job_result():
    w = World()
    w.cluster(w.batch())
    interview_id = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    model = RecordedModel(w, on_pass2=lambda: service.cancel(w.ctx, interview_id))
    assert run(w, interview_id, model) == "discarded"
    assert w.row("interviews", interview_id)["status"] == "cancelled"
    assert w.questions(interview_id) == []


def test_final_states_refuse_further_transitions():
    w = World()
    w.cluster(w.batch())
    interview_id = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    run(w, interview_id, RecordedModel(w))
    qs = w.questions(interview_id)
    assert service.cancel(w.ctx, interview_id) == "cancelled"
    assert service.cancel(w.ctx, interview_id) == "cancelled"
    with pytest.raises(answers.ServiceError) as e:
        answers.answer(w.ctx, qs[0]["id"], option_id="a", actor="user", via="ui")
    assert e.value.hint == "interview_not_ready"
    failed = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    run(w, failed, RecordedModel(w, pass2_errors=2))
    with pytest.raises(answers.ServiceError) as e:
        service.cancel(w.ctx, failed)
    assert e.value.code == "conflict"


def test_the_sweep_fails_generating_interviews_without_a_live_job():
    w = World()
    w.cluster(w.batch())
    stale = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    with w.engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))
        conn.execute(
            update(T["interviews"])
            .where(T["interviews"].c.id == stale)
            .values(created_at=w.clock() - timedelta(minutes=11))
        )
    assert service.sweep_stale(w.ctx) == [stale]
    assert w.row("interviews", stale)["error"] == "timeout"


def test_the_sweep_leaves_an_interview_whose_job_is_queued():
    w = World()
    w.cluster(w.batch())
    queued = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    with w.engine.begin() as conn:
        conn.execute(
            update(T["interviews"])
            .where(T["interviews"].c.id == queued)
            .values(created_at=w.clock() - timedelta(minutes=11))
        )
    assert service.sweep_stale(w.ctx) == []


# --- test 13: seed ---


def test_seed_interview_affects_input_documents_and_the_ask_rule_is_scoped():
    w = World()
    b = w.batch()
    agipi = {
        w.doc(
            f"AGIPI {n}",
            batch=b,
            status="filed",
            reasons=[],
            counterparty="agipi",
            path=f"Personnel/agipi-{n}.pdf",
        )
        for n in range(2)
    }
    started = service.start(w.ctx, {"type": "seed"}, lang="en")
    scope = w.row("interviews", started.interview_id)["scope"]
    keys = {v: k for k, v in w.ids("counterparties").items()}
    assert [keys[c] for c in scope["candidate_counterparty_ids"]] == ["agipi", "hello-bank", "unim"]

    def pass2(user: str) -> dict:
        alias = {c["name"]: c["alias"] for c in input_of(user)["counterparties"]}
        always = {
            "conditions": [{"field": "category", "op": "equals", "value": "insurance"}],
            "action": {
                "entity": "personal",
                "unit": None,
                "category": "insurance",
                "subcategory": None,
            },
        }
        cabinet = {**always, "action": {**always["action"], "entity": "cabinet"}}
        cabinet = {**always, "action": {**always["action"], "entity": "cabinet"}}
        lmnp = {**always, "action": {**always["action"], "entity": "lmnp", "category": "bank"}}
        return {
            "questions": [
                {
                    "text": "Is AGIPI personal?",
                    "affected": [alias["AGIPI"]],
                    "evidence": [],
                    "options": [opt("a", "always", [always]), opt("b", "always", [cabinet])],
                    "suggested": "a",
                    "confidence": 0.9,
                },
                {
                    "text": "Is Hello bank the LMNP bank?",
                    "affected": [alias["Hello bank"]],
                    "evidence": [],
                    "options": [opt("a", "always", [lmnp]), opt("b", "always", [cabinet])],
                    "suggested": "a",
                    "confidence": 0.9,
                },
            ]
        }

    assert run(w, started.interview_id, RecordedModel(w, pass2=pass2)) == "ready"
    qs = {q["text"]: q for q in w.questions(started.interview_id)}
    ag, hb = qs["Is AGIPI personal?"], qs["Is Hello bank the LMNP bank?"]
    assert set(ag["affected_document_ids"]) == agipi and ag["impact"] == 2
    assert hb["affected_document_ids"] == [] and hb["impact"] == 0
    cond = ag["options"][0]["rule_draft"]["branches"][0]["conditions"]
    assert cond[0] == {"field": "counterparty", "op": "equals", "value": "agipi"}
    ask = next(o["id"] for o in hb["options"] if o["rule_draft"]["kind"] == "ask")
    out = answers.answer(w.ctx, hb["id"], option_id=ask, actor="user", via="ui")
    rule = w.row("rules", out.rule_ids[0])
    assert rule["state"] == "active" and rule["action"] == {"review": True}
    assert rule["conditions"] == [{"field": "counterparty", "op": "equals", "value": "hello-bank"}]
