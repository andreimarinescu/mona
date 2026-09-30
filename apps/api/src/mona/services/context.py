"""The services' shared context: database, file ops (with the pipeline hooks) and clock."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path

from sqlalchemy import Engine

from mona.fileops import FileOps, Fs, Roots
from mona.fileops.ops import utcnow


@dataclass
class Ctx:
    engine: Engine
    ops: FileOps
    clock: Callable[[], datetime] = utcnow
    on_batch_done: Callable[[str], None] | None = None
    on_document_settled: Callable[[str], None] | None = None

    @property
    def data_dir(self) -> Path:
        return self.ops.roots.data

    @property
    def textcache(self) -> Path:
        return self.data_dir / "textcache"

    @property
    def config_dir(self) -> Path:
        return self.data_dir / "config"


def make_context(
    engine: Engine,
    data_dir: Path | str,
    *,
    clock: Callable[[], datetime] = utcnow,
    fs: Fs | None = None,
    on_batch_done: Callable[[str], None] | None = None,
    on_document_settled: Callable[[str], None] | None = None,
) -> Ctx:
    """Resolve the roots, check they share one filesystem (C7 §1.2), wire the hooks."""
    from mona.services.pipeline import on_commit, on_failed

    roots = Roots.at(data_dir)
    roots.check_single_filesystem()
    commit = partial(on_commit, textcache=roots.data / "textcache")
    ops = FileOps(engine, roots, clock=clock, fs=fs, on_commit=commit, on_failed=on_failed)
    return Ctx(engine, ops, clock, on_batch_done, on_document_settled)
