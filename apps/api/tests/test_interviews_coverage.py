"""Amendment A25: every candidate cluster gets a question (targeted pass 2, then deterministic)."""

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest

from mona.i18n import t
from mona.interviews import service
from mona.interviews.generate import generate_interview
from mona.interviews.model import ModelError
from mona.interviews.prompt import pass2_system
from tests.l4_world import RecordedModel, World, fixture, input_of

pytestmark = pytest.mark.usefixtures("l4_db")

AGIPI, HELLO, UNIM, BOIS, ORELIA = range(5)
FIRST_WORD = {AGIPI: "AGIPI", HELLO: "Hello", UNIM: "UNIM", BOIS: "Atelier", ORELIA: "Orélia"}
PROPOSED = {"entity": "personal", "category": "insurance"}


def spec_with(**agipi: Any) -> dict[str, Any]:
    spec = fixture("cluster.json")
    for d in spec["docs"]:
        if d["tag"].startswith("agipi"):
            d.update(agipi)
    return spec


def questions(spec: dict[str, Any], *keep: int) -> list[dict[str, Any]]:
    return [deepcopy(spec["pass2"]["questions"][n]) for n in keep]


def by_input(
    main: list[dict[str, Any]], targeted: dict[int, dict[str, Any] | Exception]
) -> Callable[[str], dict[str, Any]]:
    """Pass 2 answers `main` over the whole input; a targeted call answers by its cluster."""

    def answer(user: str) -> dict[str, Any]:
        titles = [d["title"] for d in input_of(user)["documents"]]
        if len(titles) == 10:
            return {"questions": main}
        for n, out in targeted.items():
            if all(x.startswith(FIRST_WORD[n]) for x in titles):
                if isinstance(out, Exception):
                    raise out
                return {"questions": [out]}
        raise AssertionError(f"unexpected targeted call over {titles}")

    return answer


def start(w: World, spec: dict[str, Any], lang: str = "en") -> tuple[str, str]:
    b = w.batch()
    w.cluster(b, spec)
    return b, service.start(w.ctx, {"type": "batch", "batch_id": b}, lang=lang).interview_id


def run(w: World, interview_id: str, model: RecordedModel) -> str:
    return generate_interview(w.ctx, interview_id, model_factory=lambda: model, clock=w.clock)


def targeted_calls(model: RecordedModel) -> list[dict[str, Any]]:
    return [c for c in model.calls if c["pass"] == 2][1:]


def tagged(w: World, prefix: str) -> set[str]:
    return {doc for tag, doc in w.tags.items() if tag.startswith(prefix)}


def made(caplog: pytest.LogCaptureFixture, interview_id: str) -> list[str]:
    (line,) = [r.getMessage() for r in caplog.records if interview_id in r.getMessage()]
    return line.split(" questions: ", 1)[1].split(", ")


def test_a_cluster_pass2_skips_gets_a_targeted_question(caplog, monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = spec_with()
    _, interview_id = start(w, spec)
    agipi = questions(spec, AGIPI)[0]
    pass2 = by_input(questions(spec, HELLO, UNIM, BOIS, ORELIA), {AGIPI: agipi})
    model = RecordedModel(w, pass2=pass2)
    with caplog.at_level("INFO", logger="mona.interviews.generate"):
        assert run(w, interview_id, model) == "ready"
    main, (call,) = next(c for c in model.calls if c["pass"] == 2), targeted_calls(model)
    full, small = input_of(main["user"]), input_of(call["user"])
    assert call["system"] == main["system"] == pass2_system("en")
    assert (call["timeout_s"], call["temperature"]) == (30.0, 0)
    assert call["schema"]["properties"]["questions"]["maxItems"] == 1
    assert small["registry"] == full["registry"] and small["rules"] == full["rules"]
    assert small["documents"] == [d for d in full["documents"] if d["title"].startswith("AGIPI")]
    assert call["user"].split("\n\nAnalysis:\n")[1] == main["user"].split("\n\nAnalysis:\n")[1]
    qs = w.questions(interview_id)
    q = next(q for q in qs if set(q["affected_document_ids"]) == tagged(w, "agipi"))
    assert q["text"] == "How should AGIPI documents be filed?"
    assert q["options"][0]["rule_draft"]["kind"] == "depends"
    assert all(
        b["action"]["unit"] == {"from": "person"} for b in q["options"][0]["rule_draft"]["branches"]
    )
    assert sorted(made(caplog, interview_id)) == ["pass2"] * 4 + ["targeted"]


@pytest.mark.parametrize(
    "failure",
    [ModelError("timeout"), {"text": "x"}, "only ask"],
    ids=["transport", "schema", "nothing-survives"],
)
def test_a_failed_targeted_call_gives_the_deterministic_question(failure, caplog, monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = spec_with(entity="personal")
    _, interview_id = start(w, spec)
    if failure == "only ask":
        failure = questions(spec, AGIPI)[0]
        for o in failure["options"]:
            o["rule_draft"] = {"kind": "ask", "discriminator": None, "branches": []}
    model = RecordedModel(
        w, pass2=by_input(questions(spec, HELLO, UNIM, BOIS, ORELIA), {AGIPI: failure})
    )
    with caplog.at_level("INFO", logger="mona.interviews.generate"):
        assert run(w, interview_id, model) == "ready"
    assert len(targeted_calls(model)) == 1
    q = next(q for q in w.questions(interview_id) if q["text"].startswith("Where should"))
    assert q["text"] == "Where should the documents from AGIPI go?"
    assert set(q["affected_document_ids"]) == tagged(w, "agipi")
    assert q["suggestion_confidence"] == 50
    a, b = q["options"]
    assert (a["id"], a["suggested"], b["id"], b["suggested"]) == ("a", True, "b", False)
    assert a["label"] == "Personnel / Insurance"
    assert a["rule_draft"] == {
        "kind": "always",
        "discriminator": None,
        "branches": [
            {
                "conditions": [{"field": "counterparty", "op": "equals", "value": "agipi"}],
                "action": {"entity": "personal", "category": "insurance"},
            }
        ],
    }
    assert b["label"] == "Ask me each time" and b["rule_draft"]["kind"] == "ask"
    assert [(e["field"], e["quote"], e["page"], e["verified"]) for e in q["evidence"]] == [
        ("counterparty", "agipi", 1, True)
    ] * 3
    assert sorted(made(caplog, interview_id)) == ["deterministic"] + ["pass2"] * 4


@pytest.mark.parametrize(
    ("lang", "text", "ask"),
    [
        ("fr", "Où dois-je classer les documents envoyés par AGIPI ?", "Me demander à chaque fois"),
        ("ro", "Unde trebuie arhivate documentele de la AGIPI?", "Întrebați-mă de fiecare dată"),
    ],
)
def test_the_deterministic_question_speaks_the_interview_language(lang, text, ask, monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = spec_with(entity="personal")
    _, interview_id = start(w, spec, lang=lang)
    pass2 = by_input(questions(spec, HELLO, UNIM, BOIS, ORELIA), {AGIPI: ModelError("x")})
    assert run(w, interview_id, RecordedModel(w, pass2=pass2)) == "ready"
    q = next(q for q in w.questions(interview_id) if "AGIPI" in q["text"])
    assert q["text"] == text == t("interview.question.where", lang, counterparty="AGIPI")
    assert q["options"][1]["label"] == ask


def test_a_cluster_with_no_proposed_entity_stays_uncovered(monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = spec_with()
    _, interview_id = start(w, spec)
    pass2 = by_input(questions(spec, HELLO, UNIM, BOIS, ORELIA), {AGIPI: ModelError("x")})
    assert run(w, interview_id, RecordedModel(w, pass2=pass2)) == "ready"
    qs = w.questions(interview_id)
    assert len(qs) == 4
    assert not tagged(w, "agipi") & {d for q in qs for d in q["affected_document_ids"]}


def test_a_cluster_without_one_counterparty_gets_no_deterministic_question(monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = fixture("cluster.json")
    for d in spec["docs"]:
        if d["tag"].startswith("bois"):
            d |= PROPOSED
    _, interview_id = start(w, spec)
    pass2 = by_input(questions(spec, AGIPI, HELLO, UNIM, ORELIA), {BOIS: ModelError("x")})
    assert run(w, interview_id, RecordedModel(w, pass2=pass2)) == "ready"
    assert len(w.questions(interview_id)) == 4


def test_at_most_three_targeted_calls_then_deterministic(monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = spec_with(entity="personal")
    _, interview_id = start(w, spec)
    unim = questions(spec, UNIM)[0]
    for o in unim["options"]:
        o["rule_draft"] = {"kind": "ask", "discriminator": None, "branches": []}
    bad = {n: ModelError("x") for n in (AGIPI, HELLO, BOIS, ORELIA)}
    model = RecordedModel(w, pass2=by_input([unim], bad))
    assert run(w, interview_id, model) == "ready"
    assert len(targeted_calls(model)) == 3
    qs = w.questions(interview_id)
    assert [q["text"] for q in qs] == [
        "Where should the documents from AGIPI go?",
        "Where should the documents from UNIM go?",
    ]


def test_the_seven_question_cap_holds(monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = spec_with()
    _, first = start(w, spec)
    extra = [{**questions(spec, AGIPI)[0], "text": f"AGIPI again {n}"} for n in range(3)]
    main = questions(spec, AGIPI, HELLO, BOIS) + extra
    model = RecordedModel(w, pass2=by_input(main, {ORELIA: questions(spec, ORELIA)[0]}))
    assert run(w, first, model) == "ready"
    assert len(targeted_calls(model)) == 1
    qs = w.questions(first)
    assert len(qs) == 7
    assert not tagged(w, "unim") & {d for q in qs for d in q["affected_document_ids"]}
    service.cancel(w.ctx, first)
    second = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    seven = main + [{**questions(spec, AGIPI)[0], "text": "AGIPI once more"}]
    model = RecordedModel(w, pass2=by_input(seven, {}))
    assert run(w, second, model) == "ready"
    assert targeted_calls(model) == [] and len(w.questions(second)) == 7


def test_added_questions_are_stored_in_impact_order(caplog, monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = spec_with(entity="personal")
    b = w.batch()
    w.cluster(b, spec)
    for n in range(3):
        w.doc(
            f"AGIPI archive {n}",
            batch=b,
            status="filed",
            reasons=[],
            counterparty="agipi",
            path=f"Personnel/agipi-{n}.pdf",
        )
    interview_id = service.start(w.ctx, {"type": "queue"}, lang="en").interview_id
    model = RecordedModel(
        w,
        pass2=by_input(
            questions(spec, BOIS, ORELIA),
            {
                AGIPI: ModelError("x"),
                HELLO: questions(spec, HELLO)[0],
                UNIM: questions(spec, UNIM)[0],
            },
        ),
    )
    with caplog.at_level("INFO", logger="mona.interviews.generate"):
        assert run(w, interview_id, model) == "ready"
    qs = w.questions(interview_id)
    assert [q["ordinal"] for q in qs] == list(range(1, len(qs) + 1))
    assert [(q["text"][:24], q["impact"]) for q in qs] == [
        ("Where should the documen", 6),
        ("Are the Hello bank state", 3),
        ("Which site are the Ateli", 2),
        ("Is the Orélia fibre line", 1),
        ("Is UNIM the practice's p", 1),
    ]
    assert made(caplog, interview_id) == ["deterministic", "targeted", "pass2", "pass2", "targeted"]


def test_no_targeted_call_when_it_could_pass_the_job_cap(monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "off")
    w = World()
    spec = spec_with(entity="personal")
    _, interview_id = start(w, spec)
    pass2 = by_input(questions(spec, HELLO, UNIM, BOIS, ORELIA), {AGIPI: questions(spec, AGIPI)[0]})
    model = RecordedModel(w, pass2=pass2, on_pass2=lambda: w.clock.advance(seconds=121))
    assert run(w, interview_id, model) == "ready"
    assert targeted_calls(model) == []
    assert any(q["text"].startswith("Where should") for q in w.questions(interview_id))


def test_the_cache_replays_targeted_questions_and_rebuilds_deterministic_ones(monkeypatch):
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "fallback")
    w = World()
    spec = spec_with()
    b, interview_id = start(w, spec)
    pass2 = by_input(
        questions(spec, HELLO, BOIS, ORELIA),
        {AGIPI: questions(spec, AGIPI)[0], UNIM: ModelError("x")},
    )
    assert run(w, interview_id, RecordedModel(w, pass2=pass2)) == "ready"
    live = sorted(q["text"] for q in w.questions(interview_id))
    assert "Where should the documents from UNIM go?" in live
    (path,) = (w.ctx.textcache / "debrief").glob("*.json")
    cached = json.loads(path.read_text(encoding="utf-8"))
    assert [q["made"] for q in cached["questions"]] == ["pass2"] * 3 + ["targeted"]
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "prefer")
    service.cancel(w.ctx, interview_id)
    replay = service.start(w.ctx, {"type": "batch", "batch_id": b}, lang="en").interview_id
    model = RecordedModel(w)
    assert run(w, replay, model) == "cache"
    assert model.calls == []
    assert sorted(q["text"] for q in w.questions(replay)) == live
