import json
from pathlib import Path
from typing import Annotated

import typer

from mona import __version__

app = typer.Typer(no_args_is_help=True, add_completion=False)

DEFAULT_OPENAPI = Path(__file__).resolve().parents[2] / "openapi.json"


@app.command()
def version() -> None:
    """Print the Mona version."""
    typer.echo(__version__)


@app.command()
def migrate() -> None:
    """Upgrade the database: Alembic head, then the Procrastinate schema."""
    from mona.migrate import migrate as run

    run()
    typer.echo("database up to date")


@app.command()
def openapi(
    output: Annotated[Path, typer.Option(help="Where to write the schema.")] = DEFAULT_OPENAPI,
) -> None:
    """Write the OpenAPI schema without starting a server."""
    from mona.app import create_app

    schema = create_app().openapi()
    output.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
    typer.echo(f"wrote {output}")


seed_app = typer.Typer(no_args_is_help=True, help="Seed the registry and rules (C1 §9).")
app.add_typer(seed_app, name="seed")


@seed_app.command("load")
def seed_load(
    directory: Annotated[Path, typer.Argument(help="Holds practice.yaml and rules.yaml.")],
    tier: Annotated[
        str, typer.Option(help="preseeded: rules.yaml; all: also rules.learned.yaml.")
    ] = "preseeded",
    overlay: Annotated[
        Path | None,
        typer.Option(help="Private identifiers overlay; defaults to MONA_SEED_OVERLAY."),
    ] = None,
) -> None:
    """Load the seed in one transaction; loading the same files again changes nothing."""
    from mona.db import get_sync_engine
    from mona.seed.files import SeedError
    from mona.seed.loader import RULE_FILES, load_seed
    from mona.settings import get_settings

    if tier not in RULE_FILES:
        raise typer.BadParameter(f"choose one of {', '.join(RULE_FILES)}", param_hint="--tier")
    settings = get_settings()
    try:
        with get_sync_engine().begin() as conn:
            summary = load_seed(
                conn,
                directory,
                settings=settings,
                tier=tier,  # type: ignore[arg-type]
                overlay=overlay or settings.mona_seed_overlay,
            )
    except SeedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    typer.echo(str(summary))
    _render_memory(settings.mona_hermes_home)


def _render_memory(home: Path | None) -> None:
    from mona.db import get_sync_engine
    from mona.demo.memory import write
    from mona.demo.tools import OpsEnv, chown_tree
    from mona.settings import get_settings

    if home is None:
        typer.echo("Hermes memory not rendered: MONA_HERMES_HOME is not set")
        return
    with get_sync_engine().connect() as conn:
        paths = write(conn, home)
    chown_tree(home / "memories", OpsEnv.from_settings(get_settings()).hermes_owner)
    typer.echo("rendered " + ", ".join(p.name for p in paths))


@app.command("hermes-memory")
def hermes_memory(
    home: Annotated[
        Path | None, typer.Option(help="The Hermes profile; defaults to MONA_HERMES_HOME.")
    ] = None,
) -> None:
    """D12: render memories/MEMORY.md and USER.md from the loaded registry."""
    from mona.settings import get_settings

    _render_memory(home or get_settings().mona_hermes_home)


rules_app = typer.Typer(no_args_is_help=True, help="Import and export rules.yaml (C5 §10).")
app.add_typer(rules_app, name="rules")


@rules_app.command("import")
def rules_import(
    file: Annotated[Path, typer.Argument(help="A mona.rules/v1 file.")],
) -> None:
    """Upsert rules by key in one transaction; rules absent from the file are left alone."""
    from mona.db import get_sync_engine
    from mona.seed.files import SeedError
    from mona.seed.loader import import_rules

    try:
        with get_sync_engine().begin() as conn:
            summary = import_rules(conn, file)
    except SeedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    typer.echo(str(summary).replace("seed loaded", "rules imported"))


@rules_app.command("export")
def rules_export(
    output: Annotated[Path | None, typer.Option(help="Write here instead of stdout.")] = None,
) -> None:
    """Print (or write) the current rules in the rules.yaml schema."""
    from mona.db import get_sync_engine
    from mona.seed.rules_export import dump_rules_yaml, export_rules

    with get_sync_engine().connect() as conn:
        out = dump_rules_yaml(export_rules(conn))
    if output:
        output.write_text(out, encoding="utf-8")
    else:
        typer.echo(out, nl=False)


@app.command()
def worker(
    queues: Annotated[str, typer.Option(help="Comma-separated queues: cpu, llm.")] = "cpu",
    concurrency: Annotated[int, typer.Option(help="Jobs run in parallel.")] = 1,
) -> None:
    """Run a Procrastinate worker after the pipeline startup (C7 §1.2 check, §4.3 recovery)."""
    from mona.jobs import app as jobs_app
    from mona.logs import configure_logging
    from mona.pipeline import runtime

    configure_logging()
    wanted = [q.strip() for q in queues.split(",") if q.strip()]
    runtime.get_context()
    if "cpu" in wanted:
        runtime.startup()
    jobs_app.run_worker(queues=wanted, concurrency=concurrency)


@app.command("purge-visitors")
def purge_visitors(
    now: Annotated[
        bool, typer.Option("--now", help="Ignore the age: purge every visitor batch now.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="List what would be purged; change nothing.")
    ] = False,
) -> None:
    """C9 §5: delete visitor-batch documents and everything derived from them."""
    from mona.fileops.purge import purge_visitors as purge
    from mona.pipeline import runtime

    out = purge(runtime.get_context().ops, ignore_age=now, dry_run=dry_run)
    if dry_run:
        for doc_id, batch_id in out.due:
            typer.echo(f"would purge visitor document {doc_id} (batch {batch_id})")
        typer.echo(f"{len(out.due)} documents due")
        return
    typer.echo(f"purged {len(out.purged)} documents, {len(out.batches)} batches")
    if out.failed:
        typer.echo(f"failed: {', '.join(out.failed)}", err=True)
        raise typer.Exit(1)


pipeline_app = typer.Typer(no_args_is_help=True, help="Run documents through the pipeline.")
app.add_typer(pipeline_app, name="pipeline")


@pipeline_app.command("run")
def pipeline_run(
    files: Annotated[list[Path], typer.Argument(help="PDF, JPEG or PNG files, in drop order.")],
    visitor: Annotated[bool, typer.Option(help="A visitor batch (R38).")] = False,
    inline: Annotated[
        bool, typer.Option(help="Run the jobs in this process instead of the stack's workers.")
    ] = False,
    timeout: Annotated[int, typer.Option(help="Seconds to wait for the batch.")] = 1800,
    report: Annotated[Path | None, typer.Option(help="Also write the results as JSON.")] = None,
) -> None:
    """Ingest the files as one batch, wait until it is done, print each document's outcome."""
    import logging

    from mona.logs import configure_logging
    from mona.pipeline import runtime
    from mona.pipeline.intake import Upload, ingest_files
    from mona.pipeline.report import batch_report, format_report, wait_for_batch

    configure_logging(logging.WARNING)
    ctx = runtime.get_context()
    runtime.startup()
    intake = ingest_files(ctx, [Upload(f, f.name) for f in files], visitor=visitor)
    typer.echo(f"batch {intake.batch_id}: " + ", ".join(i.outcome for i in intake.items))
    run_jobs = None
    if inline:
        from mona.jobs import app as jobs_app

        def run_jobs() -> None:
            jobs_app.run_worker(queues=["cpu", "llm"], wait=False, install_signal_handlers=False)

    if not wait_for_batch(ctx, intake.batch_id, timeout, run_jobs):
        typer.echo("the batch did not finish in time", err=True)
    rows = batch_report(ctx, intake.batch_id)
    typer.echo(format_report(rows))
    if report:
        import json

        report.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str))


@pipeline_app.command("evidence")
def pipeline_evidence(
    out: Annotated[Path, typer.Option(help="Where to write the cases (JSON).")],
    batch: Annotated[str | None, typer.Option(help="Only this batch.")] = None,
) -> None:
    """Write every verified quote's findQuery, page and viewer PDF, for the pdf.js check."""
    import json

    from mona.pipeline import runtime
    from mona.pipeline.report import evidence_cases

    cases = evidence_cases(runtime.get_context(), batch)
    out.write_text(json.dumps(cases, indent=1, ensure_ascii=False))
    typer.echo(f"{len(cases)} cases → {out}")


ops_app = typer.Typer(
    no_args_is_help=True, help="Snapshot steps run by the host wrapper deploy/bin/mona (C9 §6.3)."
)
app.add_typer(ops_app, name="ops")


def _ops_env():
    from mona.demo.tools import OpsEnv
    from mona.settings import get_settings

    return OpsEnv.from_settings(get_settings())


def _finish(rep) -> None:
    for line in rep.lines:
        typer.echo(line)
    if rep.problems:
        for p in rep.problems:
            typer.echo(f"refused: {p}", err=True)
        raise typer.Exit(1)


def _ops_errors(fn):
    import functools

    @functools.wraps(fn)
    def run(*args, **kwargs):
        from mona.demo.tools import OpsError

        try:
            return fn(*args, **kwargs)
        except OpsError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(2) from None

    return run


@ops_app.command("snapshot")
@_ops_errors
def ops_snapshot(
    name: Annotated[str, typer.Option(help="Snapshot directory under /data/snapshots.")],
    reference: Annotated[
        str | None, typer.Option(help="ISO instant the snapshot stands for (default now).")
    ] = None,
    findquery: Annotated[
        Path | None, typer.Option(help="pdf.js-checked `mona pipeline evidence` cases; - = stdin.")
    ] = None,
) -> None:
    """C9 §6.2 checks, then the copy (the wrapper stops the workers and Hermes around it)."""
    import sys
    from datetime import datetime

    from mona.demo.snapshot import take

    ref = datetime.fromisoformat(reference) if reference else None
    cases = None
    if findquery is not None:
        cases = sys.stdin.buffer.read() if str(findquery) == "-" else findquery.read_bytes()
    _finish(take(_ops_env(), name, ref, cases))


@ops_app.command("refresh-textcache")
@_ops_errors
def ops_refresh_textcache(name: Annotated[str, typer.Option()]) -> None:
    """Replace the snapshot's data/textcache/ with the current one (C9 §6.3)."""
    from mona.demo.snapshot import refresh_textcache

    refresh_textcache(_ops_env(), name)
    typer.echo(f"snapshot {name}: text cache refreshed")


@ops_app.command("verify")
@_ops_errors
def ops_verify(name: Annotated[str, typer.Option()]) -> None:
    """§6.3 step 1: sha256sums and the schema head."""
    from mona.demo.snapshot import verify

    m = verify(_ops_env(), name)
    counts = ", ".join(f"{k} {v}" for k, v in m["counts"].items())
    typer.echo(f"snapshot {name}: reference {m['reference_instant']}; {counts}")


@ops_app.command("restore")
@_ops_errors
def ops_restore(
    name: Annotated[str, typer.Option()],
    anchor: Annotated[str, typer.Option(help="today or YYYY-MM-DD.")] = "today",
) -> None:
    """§6.3 steps 1 and 3–5 with the services stopped."""
    from datetime import date

    from mona.demo.snapshot import restore

    day = None if anchor == "today" else date.fromisoformat(anchor)
    _finish(restore(_ops_env(), name, day))


@ops_app.command("postcheck")
@_ops_errors
def ops_postcheck(name: Annotated[str, typer.Option()]) -> None:
    """§6.3 step 7 once the services are healthy."""
    from mona.demo.snapshot import postcheck

    _finish(postcheck(_ops_env(), name))


@ops_app.command("fingerprint")
@_ops_errors
def ops_fingerprint(
    hermes_only: Annotated[bool, typer.Option(help="Only the restored Hermes files.")] = False,
    files: Annotated[bool, typer.Option(help="Also every Hermes file's sha256.")] = False,
) -> None:
    """Digests of the database, the data trees and the Hermes profile, for comparing resets."""
    import json

    from mona.demo.fingerprint import fingerprint

    typer.echo(json.dumps(fingerprint(_ops_env(), hermes_only=hermes_only, files=files), indent=1))


from mona.cli_ops import register  # noqa: E402

register(app)
