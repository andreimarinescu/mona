"""C6 §4: `generate_interview`: two passes, checks, persisting, the cache and the budgets."""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, func, insert, select, update

from mona.db.models import Base
from mona.ids import new_id
from mona.interviews import cache
from mona.interviews.compile import Compiled, Compiler
from mona.interviews.config import (
    JOB_CAP_S,
    PASS2_TIMEOUT_S,
    PROMPT_VERSION,
    TARGETED_TIMEOUT_S,
    cache_after_s,
    cache_mode,
    pass1_budget_s,
)
from mona.interviews.coverage import about, cover, deterministic, input_clusters, reduced
from mona.interviews.model import LanguageModel, ModelError, get_model
from mona.interviews.prompt import (
    PASS1_SYSTEM,
    Input,
    build_input,
    build_seed_input,
    pass2_system,
    pass2_user,
)
from mona.interviews.schema import build, errors, registry_enums
from mona.services import Ctx

logger = logging.getLogger(__name__)
T = Base.metadata.tables

CUT_PREFIX = "(Working notes, cut at the time budget)\n"
NOTES_MAX = 12_000
POLL_S = 0.05


class Abandoned(Exception):
    pass


def pass1(model: LanguageModel, user: str, clock: Callable[[], datetime], budget_s: float) -> str:
    """§4.3: thinking on, streamed, read for at most `budget_s`; a cut keeps working notes."""
    start = clock()
    reasoning: list[str] = []
    content: list[str] = []
    cut = False
    stream = model.stream(
        PASS1_SYSTEM, user, temperature=0.6, max_tokens=12_000, timeout_s=budget_s
    )
    try:
        for kind, delta in stream:
            (reasoning if kind == "reasoning" else content).append(delta)
            if (clock() - start).total_seconds() >= budget_s:
                cut = True
                break
    except ModelError:
        if not reasoning and not content:
            raise
        cut = True
    finally:
        close = getattr(stream, "close", None)
        if close:
            close()
    answer = "".join(content)
    if not cut and answer.strip():
        return answer
    return CUT_PREFIX + ("".join(reasoning) + answer)[-NOTES_MAX:]


def pass2(model: LanguageModel, inp: Input, analysis: str, lang: str, schema: dict) -> dict:
    """§4.4: thinking off, strict schema; one retry on a transport error or invalid output."""
    last: Exception | None = None
    for _ in range(2):
        try:
            out = model.complete_json(
                pass2_system(lang),
                pass2_user(inp.text(), analysis),
                schema,
                name="mona_interview",
                temperature=0,
                max_tokens=6000,
                timeout_s=PASS2_TIMEOUT_S,
            )
        except ModelError as e:
            last = e
            continue
        if not errors(out, schema):
            return out
        last = ModelError("schema")
    raise ModelError(type(last).__name__ if last else "pass2")


def targeted_pass2(model: LanguageModel, inp: Input, lang: str, schema: dict) -> dict | None:
    """A25 step 1: one question over a reduced input, without pass 1's analysis (A26)."""
    one = {**schema, "properties": {**schema["properties"]}}
    one["properties"]["questions"] = {**schema["properties"]["questions"], "maxItems": 1}
    try:
        out = model.complete_json(
            pass2_system(lang),
            inp.text(),
            one,
            name="mona_interview",
            temperature=0,
            max_tokens=6000,
            timeout_s=TARGETED_TIMEOUT_S,
        )
    except ModelError:
        return None
    return None if errors(out, one) else out


@dataclass
class Live:
    """The live run, on its own thread; the supervisor may abandon it."""

    questions: list[Compiled] | None = None
    output: dict[str, Any] | None = None
    analysis: str | None = None
    inp: Input | None = None
    targeted: list[dict[str, Any]] = field(default_factory=list)
    rejected: int = 0
    timings: dict[str, float] = field(default_factory=dict)
    error: BaseException | None = None
    done: threading.Event = field(default_factory=threading.Event)


def _row(conn: Connection, interview_id: str, *, lock: bool = False) -> Any:
    i = T["interviews"]
    q = select(i).where(i.c.id == interview_id)
    return conn.execute(q.with_for_update() if lock else q).mappings().first()


def _impact(conn: Connection, c: Compiled, seed: bool) -> int:
    d = T["documents"]
    if seed:
        if c.counterparty_id is None:
            return len(c.affected)
        return conn.execute(
            select(func.count())
            .select_from(d)
            .where(d.c.counterparty_id == c.counterparty_id, d.c.deleted_at.is_(None))
        ).scalar_one()
    cps = (
        conn.execute(
            select(func.distinct(d.c.counterparty_id)).where(
                d.c.id.in_(c.affected), d.c.counterparty_id.is_not(None)
            )
        )
        .scalars()
        .all()
    )
    others = 0
    if cps:
        others = conn.execute(
            select(func.count())
            .select_from(d)
            .where(
                d.c.counterparty_id.in_(cps),
                d.c.status == "filed",
                d.c.deleted_at.is_(None),
                d.c.id.not_in(c.affected),
            )
        ).scalar_one()
    return len(c.affected) + others


def persist(
    ctx: Ctx, interview_id: str, questions: list[Compiled], *, analysis: str | None, seed: bool
) -> str | None:
    """§4.6 in one transaction; None when the interview is no longer `generating`."""
    i, q = T["interviews"], T["interview_questions"]
    with ctx.engine.begin() as conn:
        row = _row(conn, interview_id, lock=True)
        if row is None or row["status"] != "generating":
            return None
        now = ctx.clock()
        if not questions:
            conn.execute(
                update(i)
                .where(i.c.id == interview_id)
                .values(status="failed", error="no_questions")
            )
            return "failed"
        for c in questions:
            c.impact = _impact(conn, c, seed)
        ordered = sorted(questions, key=lambda c: (-c.impact, c.model_order))
        for n, c in enumerate(ordered, start=1):
            conn.execute(
                insert(q).values(
                    id=new_id("qst"),
                    interview_id=interview_id,
                    ordinal=n,
                    text=c.text,
                    impact=c.impact,
                    affected_document_ids=c.affected,
                    evidence=c.evidence,
                    options=c.options,
                    suggestion_confidence=c.suggestion_confidence,
                )
            )
        conn.execute(
            update(i)
            .where(i.c.id == interview_id)
            .values(status="ready", ready_at=now, analysis=analysis, error=None)
        )
    return "ready"


def made(questions: list[Compiled]) -> str:
    """How each question was made, in stored order (§4.6 after `persist` set `impact`)."""
    ordered = sorted(questions, key=lambda c: (-c.impact, c.model_order))
    how = ", ".join(c.made for c in ordered)
    return f"{len(ordered)} questions" + (f": {how}" if how else "")


def fail(ctx: Ctx, interview_id: str, error: str) -> None:
    i = T["interviews"]
    with ctx.engine.begin() as conn:
        conn.execute(
            update(i)
            .where(i.c.id == interview_id, i.c.status == "generating")
            .values(status="failed", error=error)
        )


class Generation:
    """One `generate_interview` run."""

    def __init__(
        self,
        ctx: Ctx,
        interview_id: str,
        *,
        model_factory: Callable[[], LanguageModel] = get_model,
        clock: Callable[[], datetime] | None = None,
    ):
        self.ctx = ctx
        self.id = interview_id
        self.model_factory = model_factory
        self.clock = clock or ctx.clock
        self.abandon = threading.Event()

    def elapsed(self) -> float:
        return (self.clock() - self.start).total_seconds()

    def _live(self, row: Any, live: Live) -> None:
        try:
            seed = row["kind"] == "seed"
            scope = row["scope"]
            with self.ctx.engine.connect() as conn:
                if seed:
                    inp = build_seed_input(
                        conn,
                        scope["candidate_counterparty_ids"],
                        row["lang"],
                        self.ctx.textcache,
                        self.ctx.clock(),
                    )
                else:
                    inp = build_input(
                        conn,
                        scope["candidate_document_ids"],
                        row["lang"],
                        self.ctx.textcache,
                        self.ctx.clock(),
                    )
                enums = registry_enums(conn)
                schema = build(list(inp.aliases), enums, seed=seed)
            model = self.model_factory()
            t0 = time.monotonic()
            analysis = pass1(model, inp.text(), self.clock, pass1_budget_s())
            live.timings["pass1"] = time.monotonic() - t0
            if self.abandon.is_set():
                raise Abandoned
            t0 = time.monotonic()
            output = pass2(model, inp, analysis, row["lang"], schema)
            live.timings["pass2"] = time.monotonic() - t0
            if self.abandon.is_set():
                raise Abandoned
            with self.ctx.engine.connect() as conn:
                live.questions = Compiler(
                    conn, inp, row["lang"], self.ctx.textcache, seed=seed
                ).run(output)
            if not seed:
                self._cover(live, model, inp, row["lang"], enums)
            live.output, live.analysis, live.inp = output, analysis, inp
        except BaseException as e:  # noqa: BLE001
            live.error = e
        finally:
            live.done.set()

    def _cover(
        self,
        live: Live,
        model: LanguageModel,
        inp: Input,
        lang: str,
        enums: dict[str, list[str]],
    ) -> None:
        """A25: targeted pass 2 for an uncovered cluster, else a deterministic question."""
        live.timings["targeted"] = 0.0

        def targeted(cluster: list[str]) -> Compiled | None:
            if self.abandon.is_set():
                raise Abandoned
            if self.elapsed() + TARGETED_TIMEOUT_S > JOB_CAP_S:
                return None
            small = reduced(inp, cluster)
            t0 = time.monotonic()
            out = targeted_pass2(model, small, lang, build(list(small.aliases), enums))
            live.timings["targeted"] += time.monotonic() - t0
            if self.abandon.is_set():
                raise Abandoned
            if out is None:
                return None
            with self.ctx.engine.connect() as conn:
                compiler = Compiler(conn, inp, lang, self.ctx.textcache)
                kept = compiler.run(out)
                if kept and not about(compiler, cluster, kept[0].text):
                    live.rejected += 1
                    return None
            if not kept:
                return None
            live.targeted.append(out["questions"][0])
            kept[0].made = "targeted"
            return kept[0]

        def fixed(cluster: list[str]) -> Compiled | None:
            with self.ctx.engine.connect() as conn:
                return deterministic(Compiler(conn, inp, lang, self.ctx.textcache), cluster)

        live.questions = cover(
            live.questions or [], input_clusters(inp), targeted=targeted, fixed=fixed
        )

    def _cached(self, row: Any) -> cache.Match | None:
        if row["kind"] != "debrief" or row["scope"].get("type") != "batch":
            return None
        with self.ctx.engine.connect() as conn:
            return cache.match(
                conn,
                self.ctx.textcache,
                prompt_version=PROMPT_VERSION,
                lang=row["lang"],
                candidate_ids=row["scope"]["candidate_document_ids"],
            )

    def _use_cache(self, row: Any) -> bool:
        m = self._cached(row)
        if m is None:
            return False
        self.abandon.set()
        persist(self.ctx, self.id, m.questions, analysis=None, seed=False)
        logger.info("interview %s: cached debrief %s, %s", self.id, m.path.name, made(m.questions))
        return True

    def run(self) -> str:
        self.start = self.clock()
        with self.ctx.engine.connect() as conn:
            row = _row(conn, self.id)
        if row is None or row["status"] != "generating":
            return "skipped"
        mode = cache_mode()
        batch = row["kind"] == "debrief" and row["scope"].get("type") == "batch"
        if batch and mode == "prefer" and self._use_cache(row):
            return "cache"
        live = Live()
        worker = threading.Thread(target=self._live, args=(row, live), daemon=True)
        worker.start()
        tried = False
        while not live.done.wait(POLL_S):
            if batch and mode == "fallback" and not tried and self.elapsed() >= cache_after_s():
                tried = True
                if self._use_cache(row):
                    return "cache"
            if self.elapsed() >= JOB_CAP_S:
                self.abandon.set()
                if batch and mode != "off" and self._use_cache(row):
                    return "cache"
                fail(self.ctx, self.id, "timeout")
                return "timeout"
        if live.error is not None or not live.questions:
            if live.error is not None:
                logger.warning(
                    "interview %s: generation failed (%s)", self.id, type(live.error).__name__
                )
            if batch and mode != "off" and self._use_cache(row):
                return "cache"
            if live.error is not None:
                fail(self.ctx, self.id, "generation_failed")
                return "generation_failed"
        seed = row["kind"] == "seed"
        state = persist(self.ctx, self.id, live.questions or [], analysis=live.analysis, seed=seed)
        logger.info(
            "interview %s: %s, pass 1 %.1f s%s, pass 2 %.1f s, targeted %.1f s%s, %s",
            self.id,
            state,
            live.timings.get("pass1", 0),
            " (cut)" if (live.analysis or "").startswith(CUT_PREFIX) else "",
            live.timings.get("pass2", 0),
            live.timings.get("targeted", 0),
            f" ({live.rejected} targeted-rejected)" if live.rejected else "",
            made(live.questions or []),
        )
        if state == "ready" and batch and live.inp is not None and live.output is not None:
            self._write_cache(row, live)
        return state or "discarded"

    def _write_cache(self, row: Any, live: Live) -> None:
        assert live.inp is not None and live.output is not None
        d = T["documents"]
        ids = row["scope"]["candidate_document_ids"]
        with self.ctx.engine.connect() as conn:
            shas = dict(conn.execute(select(d.c.id, d.c.sha256).where(d.c.id.in_(ids))).all())
        sha_of = {alias: shas[doc] for alias, doc in live.inp.aliases.items() if doc in shas}
        cache.write(
            self.ctx.textcache,
            prompt_version=PROMPT_VERSION,
            lang=row["lang"],
            candidate_shas=list(shas.values()),
            output=live.output,
            targeted=live.targeted,
            sha_of=sha_of,
            now=self.ctx.clock(),
        )


def generate_interview(ctx: Ctx, interview_id: str, **kw: Any) -> str:
    try:
        return Generation(ctx, interview_id, **kw).run()
    except Exception as e:
        logger.error("interview %s: %s", interview_id, type(e).__name__)
        fail(ctx, interview_id, "generation_failed")
        return "generation_failed"
