"""C6 §4.7 with C9 §6.3 (D15): a debrief cached from a live run, refreshed into the snapshot,
is shown after a reset under MONA_DEBRIEF_CACHE=prefer with no model call."""

import hashlib
import json
from typing import Any

import pytest
from sqlalchemy import create_engine

from mona.demo.snapshot import refresh_textcache, restore, take
from mona.interviews import service
from mona.interviews.generate import generate_interview
from mona.pipeline import cache
from mona.pipeline.intake import Upload, ingest_files
from tests.demo_world import DAY, NOW, build, snapshot_reference
from tests.pg import scratch_db, sqlalchemy_url_for
from tests.pipeline_world import RECORDED, SYNTHETIC, mini_pdf

SIE = SYNTHETIC["syn-sie-letter"]
QUOTE = "Avis de mise en recouvrement"
SIE_CP = {"field": "counterparty", "op": "equals", "value": "SIE Mayenne"}


class LiveDebrief:
    """A live model: one question over every candidate; counts its calls."""

    model = "test/live"

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, system: str, user: str, **kw: Any):
        self.calls += 1
        yield "content", "One counterparty, one entity question."

    def complete_json(self, system: str, user: str, schema: dict, **kw: Any) -> dict:
        self.calls += 1
        docs = json.JSONDecoder().raw_decode(user)[0]["documents"]
        aliases = [d["alias"] for d in docs]
        always = {
            "kind": "always",
            "discriminator": None,
            "branches": [
                {
                    "conditions": [SIE_CP],
                    "action": {"entity": "mdd", "unit": None, "category": "payment_calls",
                               "subcategory": None},
                }
            ],
        }  # fmt: skip
        ask = {"kind": "ask", "discriminator": None, "branches": []}
        return {
            "questions": [
                {
                    "text": "Do the SIE Mayenne letters belong to Medical Digital Design?",
                    "affected": aliases,
                    "evidence": [{"doc": aliases[0], "quote": QUOTE}],
                    "options": [
                        {"id": "a", "label": "Yes, Medical Digital Design", "rule_draft": always},
                        {"id": "b", "label": "Ask me each time", "rule_draft": ask},
                    ],
                    "suggested": "a",
                    "confidence": 0.9,
                }
            ]
        }


class NoCall(LiveDebrief):
    def stream(self, system: str, user: str, **kw: Any):
        raise AssertionError("unexpected model call")

    def complete_json(self, system: str, user: str, schema: dict, **kw: Any) -> dict:
        raise AssertionError("unexpected model call")


@pytest.fixture
def stage(l1m2_demo_template, tmp_path):
    with scratch_db(template=l1m2_demo_template) as db:
        url = sqlalchemy_url_for(db)
        engine = create_engine(url)
        try:
            yield build(engine, url, tmp_path)
        finally:
            engine.dispose()


def drop_live_batch(stage) -> tuple[str, list[str]]:
    """Two letters of a first-seen counterparty with no entity: both queue."""
    p = stage.p
    uploads = []
    for i in range(2):
        content = mini_pdf([*SIE["pages"], f"Copie {i}"])
        sha = hashlib.sha256(content).hexdigest()
        cache.write_pages(p.ctx.textcache, cache.Pages(sha, SIE["method"], tuple(SIE["pages"])))
        p.cache_model(sha, {**RECORDED["outputs"]["syn-sie-letter"], "entity": None})
        uploads.append(Upload(content, f"sie-{i}.pdf"))
    batch = ingest_files(p.ctx, uploads)
    p.drain()
    docs = [i.document_id for i in batch.items]
    assert [p.row(d)["status"] for d in docs] == ["review", "review"]
    return batch.batch_id, docs  # type: ignore[return-value]


def debrief(stage, batch_id: str, model: LiveDebrief) -> str:
    ctx = stage.p.ctx
    interview_id = service.start(ctx, {"type": "batch", "batch_id": batch_id}, lang="en")
    generate_interview(ctx, interview_id.interview_id, model_factory=lambda: model)
    return interview_id.interview_id


def test_a_refreshed_debrief_is_shown_after_reset_with_no_model_call(stage, monkeypatch):
    rep = take(stage.env, "scratch", snapshot_reference(), None, NOW)
    assert rep.problems == []
    monkeypatch.setenv("MONA_DEBRIEF_CACHE", "prefer")
    batch, docs = drop_live_batch(stage)
    live = LiveDebrief()
    first = debrief(stage, batch, live)
    assert live.calls == 2 and stage.p.rows("interviews", id=first)[0]["analysis"] is not None
    assert len(list((stage.env.data / "textcache" / "debrief").glob("*.json"))) == 1

    refresh_textcache(stage.env, "scratch", now=NOW)
    assert restore(stage.env, "scratch", DAY, now=NOW).problems == []
    assert stage.p.rows("interviews") == []

    batch, again = drop_live_batch(stage)
    assert set(again).isdisjoint(docs)
    cached = debrief(stage, batch, NoCall())
    iv = stage.p.rows("interviews", id=cached)[0]
    assert (iv["status"], iv["analysis"]) == ("ready", None)
    [q] = stage.p.rows("interview_questions", interview_id=cached)
    assert sorted(q["affected_document_ids"]) == sorted(again)
    assert [e["document_id"] for e in q["evidence"]] == [again[0]]
