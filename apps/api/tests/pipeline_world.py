"""The pipeline over the demo seed: synthetic documents, recorded model outputs, real job SQL."""

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from procrastinate.schema import SchemaManager
from sqlalchemy import Engine, insert, select, text

from mona.ids import new_id
from mona.pipeline import cache, stages
from mona.pipeline.intake import Intake, Upload, ingest_files
from mona.pipeline.model import ModelResult
from mona.pipeline.schema import PROMPT_VERSION
from mona.seed.loader import load_seed
from mona.services import make_context
from mona.services.registry import T
from mona.settings import Settings
from tests.fileops_world import Clock

REPO = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "pipeline"
DEMO_SEED = REPO / "demo" / "seed"
OVERLAY = FIXTURES / "demo-overlay.yaml"
SYNTHETIC = json.loads((FIXTURES / "synthetic.json").read_text(encoding="utf-8"))
_RECORDED_FILE = FIXTURES / "model_outputs.json"
RECORDED = (
    json.loads(_RECORDED_FILE.read_text(encoding="utf-8"))
    if _RECORDED_FILE.exists()
    else {"model": "test/none", "outputs": {}}
)
ANCHOR = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)
RECORDED_MODEL = RECORDED["model"]


def load_demo_seed(engine: Engine, url: str, tier: str) -> None:
    settings = Settings(database_url=url, mona_owner_password="correct horse battery staple")
    with engine.begin() as conn:
        load_seed(conn, DEMO_SEED, settings=settings, tier=tier, overlay=OVERLAY)  # type: ignore[arg-type]


def apply_jobs_schema(libpq: str) -> None:
    with psycopg.connect(libpq) as conn:
        conn.execute(SchemaManager.get_schema())


def mini_pdf(pages: Sequence[str]) -> bytes:
    """A text PDF (Helvetica, WinAnsi) that pdftotext and pdf.js read back line by line."""
    objs: list[bytes] = [b"", b""]
    kids = []
    font = 3
    objs.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    for page in pages:
        lines = []
        for line in page.split("\n"):
            raw = line.encode("cp1252", errors="replace")
            esc = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            lines.append(b"(" + esc + b") Tj T*")
        stream = b"BT /F1 9 Tf 11 TL 40 800 Td " + b" ".join(lines) + b" ET"
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content = len(objs)
        objs.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents %d 0 R "
            b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (content, font)
        )
        kids.append(len(objs))
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )
    out = b"%PDF-1.4\n"
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def content_for(doc_id: str) -> bytes:
    """Deterministic stand-in bytes for a synthetic document (its text is in the cache)."""
    s = SYNTHETIC[doc_id]
    if s["mime"] == "image/jpeg":
        return b"\xff\xd8\xff\xe0" + hashlib.sha256(doc_id.encode()).digest()
    return mini_pdf(s["pages"])


class NoModel:
    """Fails the test if a model call happens; outputs come through the model-output cache."""

    model = RECORDED_MODEL

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> ModelResult:
        self.calls += 1
        raise AssertionError("unexpected model call")


class FakeModel:
    """Answers by file name: a raw output, or an exception to raise."""

    def __init__(self, answers: dict[str, Any], model: str = RECORDED_MODEL):
        self.model = model
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> ModelResult:
        name = next(line[10:] for line in user.split("\n") if line.startswith("Filename: "))
        self.calls.append((system, user))
        answer = self.answers[name]
        if isinstance(answer, BaseException):
            raise answer
        return ModelResult(answer, 5, 100, 50)


@dataclass
class Tools:
    """A fake subprocess runner that records every tool call; `pdftoppm` writes a PNG."""

    calls: list[list[str]] = field(default_factory=list)
    handler: Callable[[list[str]], bytes] | None = None

    def __call__(self, args: Sequence[str], timeout: float) -> bytes:
        self.calls.append(list(args))
        if self.handler is not None:
            return self.handler(list(args))
        if args[0] == "pdftoppm":
            Path(args[-1] + ".png").write_bytes(b"\x89PNG\r\n\x1a\n")
            return b""
        raise AssertionError(f"unexpected tool call: {args[0]}")


JOB_ARGS = text(
    "SELECT id, task_name, args->>'document_id' AS doc, priority, queue_name, queueing_lock,"
    " status, attempts FROM procrastinate_jobs ORDER BY id"
)


class Pipeline:
    def __init__(self, engine: Engine, data_dir: Path, *, model=None, tools=None, **kw: Any):
        self.engine = engine
        self.clock = kw.pop("clock", None) or Clock(ANCHOR)
        self.done_batches: list[str] = []
        self.settled: list[str] = []
        self.ctx = make_context(
            engine, data_dir, clock=self.clock, on_batch_done=self.done_batches.append,
            on_document_settled=self.settled.append, fs=kw.pop("fs", None),
        )  # fmt: skip
        self.model = model or NoModel()
        self.tools = tools or Tools()
        self.ran: list[tuple[str, str, str]] = []

    def cache_text(self, content: bytes, doc_id: str) -> str:
        s = SYNTHETIC[doc_id]
        sha = hashlib.sha256(content).hexdigest()
        cache.write_pages(self.ctx.textcache, cache.Pages(sha, s["method"], tuple(s["pages"])))
        return sha

    def cache_model(self, sha: str, raw: dict[str, Any], model: str = RECORDED_MODEL) -> None:
        cache.write_model(self.ctx.textcache, sha, PROMPT_VERSION, model, raw)

    def drop_synthetic(
        self, ids: Sequence[str], *, visitor: bool = False, outputs: bool = True
    ) -> Intake:
        """Drop synthetic documents with their text (and recorded outputs) already cached."""
        uploads = []
        for i in ids:
            content = content_for(i)
            sha = self.cache_text(content, i)
            if outputs and i in RECORDED["outputs"]:
                self.cache_model(sha, RECORDED["outputs"][i])
            uploads.append(Upload(content, SYNTHETIC[i]["file"]))
        return ingest_files(self.ctx, uploads, visitor=visitor)

    def set_thresholds(self, high: int, low: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(T["settings"].update().values(confidence_high=high, confidence_low=low))

    def filed_history(self, *counterparties: str) -> list[str]:
        """One filed document per counterparty name, so the A17 first-seen signal stays quiet."""
        from mona.services.corrections import resolve_counterparty

        now = self.clock()
        out = []
        with self.engine.begin() as conn:
            batch = new_id("bat")
            conn.execute(
                insert(T["batches"]).values(
                    id=batch, source="drop", status="done", started_at=now, finished_at=now
                )
            )  # fmt: skip
            for i, name in enumerate(counterparties):
                cp = resolve_counterparty(conn, name)
                doc, data = new_id("doc"), f"history {name}".encode()
                path = f"History/{i}.pdf"
                target = self.ctx.ops.roots.archive / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                conn.execute(
                    insert(T["documents"]).values(
                        id=doc, sha256=hashlib.sha256(data).hexdigest(),
                        original_name=f"{i}.pdf", mime_type="application/pdf",
                        size_bytes=len(data), source="drop", batch_id=batch, arrived_at=now,
                        location="archive", current_path=path, status="filed",
                        pipeline_stage="done", counterparty_id=cp, filed_at=now, filed_by="user",
                    )
                )  # fmt: skip
                out.append(doc)
        return out

    def drain(self, queues: Sequence[str] = ("cpu", "llm"), limit: int = 500) -> list[tuple]:
        """Run queued jobs through Procrastinate's own fetch/finish/retry SQL, in its order."""
        raw = self.engine.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute("SELECT worker_id FROM procrastinate_register_worker_v1()")
            worker = cur.fetchone()[0]
            raw.commit()
            for _ in range(limit):
                cur.execute(
                    "SELECT id, task_name, args->>'document_id', attempts"
                    " FROM procrastinate_fetch_job_v2(%s::varchar[], %s)",
                    (list(queues), worker),
                )
                job = cur.fetchone()
                raw.commit()
                if job is None or job[0] is None:
                    break
                job_id, task, doc, attempts = job
                try:
                    out = stages.run(
                        self.ctx, task, doc, attempts=attempts, model=lambda: self.model,
                        runner=self.tools,
                    )  # fmt: skip
                except Exception:
                    cur.execute(
                        "SELECT procrastinate_retry_job_v2(%s, now(), NULL, NULL, NULL)", (job_id,)
                    )
                    raw.commit()
                    self.ran.append((task, doc, "retry"))
                    continue
                cur.execute("SELECT procrastinate_finish_job_v1(%s, 'succeeded', false)", (job_id,))
                raw.commit()
                self.ran.append((task, doc, out))
            return self.ran
        finally:
            raw.close()

    def jobs(self) -> list[Any]:
        with self.engine.connect() as conn:
            return list(conn.execute(JOB_ARGS))

    def row(self, doc_id: str) -> Any:
        d = T["documents"]
        with self.engine.connect() as conn:
            return conn.execute(select(d).where(d.c.id == doc_id)).mappings().one()

    def rows(self, table: str, **where: Any) -> list[Any]:
        t = T[table]
        q = select(t)
        for k, v in where.items():
            q = q.where(t.c[k] == v)
        with self.engine.connect() as conn:
            return list(conn.execute(q).mappings())

    def path(self, doc_id: str) -> str:
        r = self.row(doc_id)
        return (
            r["current_path"]
            if r["location"] == "archive"
            else f"{r['location']}:{r['current_path']}"
        )
