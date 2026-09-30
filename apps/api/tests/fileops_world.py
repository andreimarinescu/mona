"""A temporary data root and database rows for file-ops tests, plus the C7 §9 invariants."""

import hashlib
import os
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, insert, select, text

from mona.fileops import Change, FileOps, Roots, badge_until, sha256_file, undo_state
from mona.fileops.state import T
from mona.ids import new_id

BADGE_HOURS = 24


class Clock:
    def __init__(self, start: datetime = datetime(2026, 10, 14, 7, 0, tzinfo=UTC)):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: Any) -> None:
        self.now += timedelta(**kw)


RESET = text("TRUNCATE documents, batches, op_groups, file_ops CASCADE")


class World:
    def __init__(self, engine: Engine, data_dir: Path, *, reset: bool = True, **kw: Any):
        if reset:
            with engine.begin() as conn:
                conn.execute(RESET)
        self.engine = engine
        self.roots = Roots.at(data_dir)
        self.clock = kw.pop("clock", None) or Clock()
        self.ops = FileOps(engine, self.roots, clock=self.clock, **kw)
        self.batch = new_id("bat")
        self.group = new_id("grp")
        with engine.begin() as conn:
            conn.execute(insert(T["batches"]).values(id=self.batch, source="drop"))
            conn.execute(
                insert(T["op_groups"]).values(
                    id=self.group, kind="intake_batch", actor="mona", via="pipeline",
                    batch_id=self.batch,
                )
            )  # fmt: skip
        self.docs: list[str] = []

    def ingest(self, content: bytes | None = None, *, status: str = "processing") -> str:
        doc_id = new_id("doc")
        data = content if content is not None else secrets.token_bytes(64)
        rel = f"{doc_id}.pdf"
        (self.roots.inbox / rel).write_bytes(data)

        with self.engine.begin() as conn:
            conn.execute(
                insert(T["documents"]).values(
                    id=doc_id, sha256=hashlib.sha256(data).hexdigest(), original_name="x.pdf",
                    mime_type="application/pdf", size_bytes=len(data), source="drop",
                    batch_id=self.batch, location="inbox", current_path=rel, status=status,
                    reasons=["low"] if status == "review" else [],
                )
            )  # fmt: skip
            if status == "review":
                conn.execute(
                    insert(T["review_items"]).values(
                        id=new_id("rev"), document_id=doc_id, reasons=["low"]
                    )
                )
        self.docs.append(doc_id)
        return doc_id

    def doc(self, doc_id: str) -> Any:
        d = T["documents"]
        with self.engine.connect() as conn:
            return conn.execute(select(d).where(d.c.id == doc_id)).mappings().one()

    def entry(self, entry_id: int) -> Any:
        f = T["file_ops"]
        with self.engine.connect() as conn:
            return conn.execute(select(f).where(f.c.id == entry_id)).mappings().one()

    def entries(self, doc_id: str, state: str | None = "done") -> list[Any]:
        f = T["file_ops"]
        q = select(f).where(f.c.document_id == doc_id).order_by(f.c.id)
        if state:
            q = q.where(f.c.fs_state == state)
        with self.engine.connect() as conn:
            return list(conn.execute(q).mappings())

    def state(self, entry_id: int) -> str:
        with self.engine.connect() as conn:
            f = T["file_ops"]
            e = conn.execute(select(f).where(f.c.id == entry_id)).mappings().one()
            return undo_state(conn, e)

    def change(self, doc_id: str, action: str, location: str, path: str, **kw: Any) -> Change:
        d = self.doc(doc_id)
        kw.setdefault("actor", "mona")
        kw.setdefault("via", "chat")
        if location == "archive":
            kw.setdefault("status", "filed")
            kw.setdefault("reasons", ())
        return Change(
            document_id=doc_id, action=action, location=location, path=path,  # type: ignore[arg-type]
            expected=(d["location"], d["current_path"]), **kw,
        )  # fmt: skip

    def file(self, doc_id: str, path: str, **kw: Any):
        kw.setdefault("group_id", self.group)
        kw.setdefault("via", "pipeline")
        return self.ops.move(self.change(doc_id, "file", "archive", path, **kw))

    def relocate(self, doc_id: str, path: str, **kw: Any):
        d = self.doc(doc_id)
        same = d["current_path"].rpartition("/")[0] == path.rpartition("/")[0]
        return self.ops.move(
            self.change(doc_id, "rename" if same else "move", "archive", path, **kw)
        )

    def unfile(self, doc_id: str, **kw: Any):
        kw.setdefault("actor", "user")
        kw.setdefault("via", "ui")
        return self.ops.move(
            self.change(doc_id, "unfile", "inbox", f"{doc_id}.pdf", status="review",
                        reasons=("low",), **kw)
        )  # fmt: skip

    def files(self, location: str) -> dict[str, str]:
        """Relative path -> sha256 of every file under a root."""
        root = self.roots.root(location)
        out = {}
        for dirpath, _, names in os.walk(root):
            for n in names:
                p = Path(dirpath) / n
                out[str(p.relative_to(root))] = sha256_file(p) or "not-regular"
        return out

    def tree(self) -> dict[str, dict[str, str]]:
        return {loc: self.files(loc) for loc in ("inbox", "archive", "trash")}

    def check(self, docs: Iterable[str] | None = None, *, archive_exact: bool = True) -> None:
        check_invariants(self, list(docs or self.docs), archive_exact=archive_exact)


def _adoption_copies(conn, doc_ids: list[str]) -> set[str]:
    f = T["file_ops"]
    rows = conn.execute(
        select(f).where(f.c.document_id.in_(doc_ids), f.c.fs_state == "done")
    ).mappings()
    out = set()
    for e in rows:
        a = e["after"] or {}
        if a.get("adopted") and undo_state(conn, e) != "undone":
            out.add(a["trash_copy"])
    return out


def check_invariants(w: World, doc_ids: list[str], *, archive_exact: bool = True) -> None:
    """C7 §9 invariants 1–4, 7, 10 and 11 over `doc_ids`."""
    d, f, r = T["documents"], T["file_ops"], T["review_items"]
    with w.engine.connect() as conn:
        docs = list(conn.execute(select(d).where(d.c.id.in_(doc_ids))).mappings())
        tree = w.tree()
        current = {loc: {} for loc in tree}
        inodes = set()
        for doc in docs:
            p = w.roots.root(doc["location"]) / doc["current_path"]
            # 1 mirror
            assert p.is_file() and not p.is_symlink(), f"missing file for {doc['id']}"
            assert sha256_file(p) == doc["sha256"], f"wrong bytes for {doc['id']}"
            # 3 unique, no shared inode
            st = os.lstat(p)
            assert (st.st_dev, st.st_ino) not in inodes, f"shared inode {doc['id']}"
            inodes.add((st.st_dev, st.st_ino))
            current[doc["location"]][doc["current_path"]] = doc["id"]
        # 2 no strays
        copies = _adoption_copies(conn, doc_ids)
        for loc in ("inbox", "trash"):
            strays = set(tree[loc]) - set(current[loc]) - (copies if loc == "trash" else set())
            assert not strays, f"strays in {loc}: {strays}"
        if archive_exact:
            assert set(tree["archive"]) == set(current["archive"]), "archive tree != DB paths"
        for doc in docs:
            entries = list(
                conn.execute(
                    select(f)
                    .where(f.c.document_id == doc["id"], f.c.fs_state == "done",
                           f.c.action.in_(("file", "move", "rename", "unfile", "delete",
                                           "undo", "redo")))
                    .order_by(f.c.id)
                ).mappings()
            )  # fmt: skip
            # 4 replay
            if entries:
                at = (entries[0]["before"]["location"], entries[0]["before"]["path"])
                for e in entries:
                    assert (e["before"]["location"], e["before"]["path"]) == at, "replay gap"
                    at = (e["after"]["location"], e["after"]["path"])
                assert at == (doc["location"], doc["current_path"]), "replay end"
                assert doc["filed_op_id"] == entries[-1]["id"]
            # 7 supersede, from the definition
            for e in entries:
                chain = [e]
                while chain[-1]["undone_by"] is not None:
                    chain.append(
                        conn.execute(select(f).where(f.c.id == chain[-1]["undone_by"]))
                        .mappings()
                        .one()
                    )
                tip = chain[-1]["after"]
                expect = (
                    "undone"
                    if (len(chain) - 1) % 2
                    else "undoable"
                    if (doc["location"], doc["current_path"]) == (tip["location"], tip["path"])
                    else "superseded"
                )
                assert undo_state(conn, e, doc) == expect, f"undo state of {e['id']}"
            # 10 review invariant
            n_open = len(
                conn.execute(
                    select(r.c.id).where(r.c.document_id == doc["id"], r.c.status == "open")
                ).all()
            )
            want = doc["status"] in ("review", "unreadable") and doc["deleted_at"] is None
            assert n_open == (1 if want else 0), f"review invariant {doc['id']}"
            assert (doc["location"] == "trash") == (doc["deleted_at"] is not None)
            # 11 badge
            now = w.clock()
            fresh = (
                doc["status"] == "filed"
                and doc["filed_by"] == "mona"
                and doc["filed_at"] is not None
                and now < doc["filed_at"] + timedelta(hours=BADGE_HOURS)
            )
            assert (badge_until(doc, BADGE_HOURS, now) is not None) == fresh
        # 12 Mona never deletes
        mona_trash = conn.execute(
            select(f.c.id).where(
                f.c.document_id.in_(doc_ids), f.c.fs_state == "done", f.c.actor == "mona",
                f.c.after["location"].astext == "trash",
            )
        ).all()  # fmt: skip
        assert not mona_trash, "Mona moved a document to the trash"
