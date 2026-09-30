"""C7 §9 invariants as a hypothesis state machine (C7 §10.1)."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)
from sqlalchemy import insert, select

from mona.fileops import FileOpError, SimulatedCrash, is_suffix_of
from mona.fileops.state import T, chain, entry
from mona.ids import new_id
from tests.fileops_world import World

FOLDERS = ["A", "A/B", "C", "C/Été"]
NAMES = ["2025-01-01_X.pdf", "2025-01-01_Y.pdf"]
TARGETS = st.sampled_from([f"{f}/{n}" for f in FOLDERS for n in NAMES])
ACTORS = st.sampled_from([("mona", "chat"), ("user", "ui"), ("mona", "telegram")])
CRASH_POINTS = st.sampled_from(["after_a", "after_b1", "after_b3", "in_c"])

PROFILE = "ci" if os.environ.get("CI") else "dev"
EXAMPLES = {"ci": 500, "dev": 60}[PROFILE]
STEPS = 15


class Journal(RuleBasedStateMachine):
    engine = None

    def __init__(self):
        super().__init__()
        self.tmp = Path(tempfile.mkdtemp(prefix="mona-prop-"))
        self.w = World(self.engine, self.tmp / "data")
        self.groups: list[str] = []

    def teardown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers ---

    def docs_at(self, *locations: str) -> list[str]:
        d = T["documents"]
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(d.c.id).where(d.c.batch_id == self.w.batch, d.c.location.in_(locations))
            )
            return sorted(rows.scalars())

    def done_entries(self) -> list[int]:
        f = T["file_ops"]
        with self.engine.connect() as conn:
            return list(
                conn.execute(
                    select(f.c.id)
                    .where(f.c.document_id.in_(self.w.docs or [""]), f.c.fs_state == "done")
                    .order_by(f.c.id)
                ).scalars()
            )

    def snapshot(self):
        f, d = T["file_ops"], T["documents"]
        with self.engine.connect() as conn:
            docs = [
                dict(r)
                for r in conn.execute(select(d).where(d.c.batch_id == self.w.batch)).mappings()
            ]
            ops = [dict(r) for r in conn.execute(select(f).order_by(f.c.id)).mappings()]
        return self.w.tree(), sorted(docs, key=lambda r: r["id"]), ops

    def new_group(self, kind: str, actor: str, via: str) -> str:
        g = new_id("grp")
        with self.engine.begin() as conn:
            conn.execute(insert(T["op_groups"]).values(id=g, kind=kind, actor=actor, via=via))
        return g

    def tolerate(self, fn):
        try:
            return fn()
        except FileOpError as e:
            assert e.code == "conflict" and e.hint == "collision_exhausted", e
            return None

    # --- rules ---

    @rule()
    def ingest(self):
        self.w.ingest()

    @precondition(lambda self: self.docs_at("inbox"))
    @rule(data=st.data(), dest=TARGETS, who=ACTORS)
    def file(self, data, dest, who):
        doc = data.draw(st.sampled_from(self.docs_at("inbox")))
        self.w.file(doc, dest, actor=who[0], via="pipeline" if who[0] == "mona" else "ui")

    @precondition(lambda self: self.docs_at("archive"))
    @rule(data=st.data(), dest=TARGETS, who=ACTORS)
    def move_or_rename(self, data, dest, who):
        doc = data.draw(st.sampled_from(self.docs_at("archive")))
        self.w.relocate(doc, dest, actor=who[0], via=who[1])

    @precondition(lambda self: self.docs_at("archive"))
    @rule(data=st.data())
    def unfile(self, data):
        self.w.unfile(data.draw(st.sampled_from(self.docs_at("archive"))))

    @precondition(lambda self: self.docs_at("inbox", "archive"))
    @rule(data=st.data(), go=st.integers(0, 2))
    def delete(self, data, go):
        if go:
            return
        doc = data.draw(st.sampled_from(self.docs_at("inbox", "archive")))
        self.w.ops.delete(doc, actor="user", via="ui")

    @precondition(lambda self: self.done_entries())
    @rule(data=st.data(), who=ACTORS)
    def undo(self, data, who):
        eid = data.draw(st.sampled_from(self.done_entries()))
        with self.engine.connect() as conn:
            tip = chain(conn, entry(conn, eid))[-1]
        before = self.snapshot()
        r = self.w.ops.undo(eid, actor=who[0], via=who[1])
        if r.state != "done":
            assert self.snapshot() == before, "a refused undo changed something"
            return
        doc = self.w.doc(r.document_id)
        want = tip["before"]
        assert doc["location"] == want["location"]
        assert is_suffix_of(doc["current_path"], want["path"])
        assert doc["classification_id"] == want["classification_id"]
        status = "review" if want["status"] == "processing" else want["status"]
        assert doc["status"] == status

    @precondition(lambda self: len(self.docs_at("archive")) >= 1)
    @rule(data=st.data(), who=ACTORS)
    def group_round_trip(self, data, who):
        docs = data.draw(st.lists(st.sampled_from(self.docs_at("archive")), min_size=1, max_size=4))
        targets = data.draw(st.lists(TARGETS, min_size=len(docs), max_size=len(docs)))
        g = self.new_group("rule_apply", *who)
        self.groups.append(g)
        tree_before = self.w.tree()
        for doc, target in zip(docs, targets, strict=True):
            self.tolerate(lambda d=doc, t=target: self.w.relocate(d, t, group_id=g, actor=who[0]))
        tree_after = self.w.tree()
        u = self.w.ops.undo_group(g, actor=who[0], via=who[1])
        assert self.w.tree() == tree_before, "group undo did not restore the tree"
        if u.group_id is None:
            return
        self.groups.append(u.group_id)
        redo = self.w.ops.undo_group(u.group_id, actor=who[0], via=who[1])
        assert self.w.tree() == tree_after, "group redo did not restore the tree after g"
        self.groups.append(redo.group_id)

    @precondition(lambda self: self.groups)
    @rule(data=st.data(), who=ACTORS)
    def undo_some_group(self, data, who):
        g = data.draw(st.sampled_from(self.groups))
        r = self.w.ops.undo_group(g, actor=who[0], via=who[1])
        if r.group_id:
            self.groups.append(r.group_id)

    @precondition(lambda self: self.docs_at("archive"))
    @rule(data=st.data(), dest=TARGETS, point=CRASH_POINTS)
    def crash_then_recover(self, data, dest, point):
        doc = data.draw(st.sampled_from(self.docs_at("archive")))
        self.w.ops.crash_at = point
        try:
            self.w.relocate(doc, dest)
        except SimulatedCrash:
            pass
        finally:
            self.w.ops.crash_at = None
        self.w.ops.recover_pending()

    @rule(hours=st.integers(min_value=0, max_value=30))
    def time_passes(self, hours):
        self.w.clock.advance(hours=hours)

    @invariant()
    def invariants_hold(self):
        self.w.check()


@pytest.mark.parametrize("_", [PROFILE])
def test_journal_invariants(migrated_engine, _):
    Journal.engine = migrated_engine
    run_state_machine_as_test(
        Journal,
        settings=settings(
            max_examples=EXAMPLES,
            stateful_step_count=STEPS,
            deadline=None,
            database=None,
            suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        ),
    )
