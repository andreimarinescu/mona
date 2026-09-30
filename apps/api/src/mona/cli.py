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
    import logging

    from mona.db import get_sync_engine
    from mona.seed.files import SeedError
    from mona.seed.loader import RULE_FILES, load_seed
    from mona.settings import get_settings

    if tier not in RULE_FILES:
        raise typer.BadParameter(f"choose one of {', '.join(RULE_FILES)}", param_hint="--tier")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
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
    import logging

    from mona.jobs import app as jobs_app
    from mona.pipeline import runtime

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    wanted = [q.strip() for q in queues.split(",") if q.strip()]
    runtime.get_context()
    if "cpu" in wanted:
        runtime.startup()
    jobs_app.run_worker(queues=wanted, concurrency=concurrency)


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

    from mona.pipeline import runtime
    from mona.pipeline.intake import Upload, ingest_files
    from mona.pipeline.report import batch_report, format_report, wait_for_batch

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
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
