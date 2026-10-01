"""`mona` commands for operations: the settings gate, `check-prod` (C9 §2), `doctor` and
`profile set-password` (C2 §2.1)."""

import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from mona.settings import SettingsError

UNGATED = {"check-prod", "doctor"}
MIN_PASSWORD = 8


def gate(ctx: typer.Context) -> None:
    """Every command needs valid settings (`MONA_ENV` has no default; prod runs A1–A2)."""
    from mona.logs import configure_logging

    configure_logging()
    if ctx.invoked_subcommand in UNGATED:
        return
    from mona.settings import get_settings

    try:
        get_settings()
    except SettingsError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2) from None


def _line(check: str, problem: str | None) -> bool:
    typer.echo(f"{check} {'ok' if problem is None else 'FAILED: ' + problem}")
    return problem is None


def _run(check: str, fn: Any) -> bool:
    from mona.privacy import ProdCheckFailed

    try:
        fn()
    except ProdCheckFailed as e:
        return _line(check, str(e).split(": ", 1)[-1])
    return _line(check, None)


def compose_env(rendered: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Each service's environment from `docker compose config --format json`."""
    out = {}
    for name, svc in (rendered.get("services") or {}).items():
        env = svc.get("environment") or {}
        if isinstance(env, list):
            env = dict(e.split("=", 1) if "=" in e else (e, "") for e in env)
        out[name] = {k: "" if v is None else str(v) for k, v in env.items()}
    return out


def check_prod(
    hermes_home: Annotated[
        Path | None, typer.Option(help="An installed Hermes profile: checks A4 and A5.")
    ] = None,
    compose_json: Annotated[
        Path | None,
        typer.Option(help="`docker compose config --format json` output: checks A3."),
    ] = None,
) -> None:
    """C9 §2.1 prod assertions A1–A5; names variables and keys, never values."""
    from mona import privacy
    from mona.settings import Settings

    results = []
    try:
        settings = Settings()  # type: ignore[call-arg]
        url = settings.mona_llm_base_url
    except Exception:  # noqa: BLE001
        url = os.environ.get("MONA_LLM_BASE_URL")
    results.append(_run("A1", lambda: privacy.check_env(os.environ, "A1")))
    results.append(_run("A2", lambda: privacy.require_local_llm(url)))
    if compose_json is not None:
        services = compose_env(json.loads(compose_json.read_text()))

        def a3() -> None:
            for name, env in sorted(services.items()):
                found = privacy.cloud_keys_set(env)
                if found:
                    raise privacy.ProdCheckFailed("A3", f"{name}: {', '.join(found)}", "is set")

        results.append(_run("A3", a3))
    if hermes_home is not None:
        results.append(_run("A4", lambda: privacy.check_hermes_env_file(hermes_home / ".env")))
        results.append(
            _run("A5", lambda: privacy.check_hermes_config(hermes_home / "config.yaml", os.environ))
        )
    if not all(results):
        raise typer.Exit(1)


def doctor(
    privacy: Annotated[
        bool, typer.Option("--privacy", help="Also run A1-A5 and the memory scan, in any env.")
    ] = False,
    host_lines: Annotated[
        str | None,
        typer.Option("--host-lines", help="Host-side check lines (file, or - for stdin)."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="One JSON object per line.")] = False,
) -> None:
    """One line per check, green/amber/red; exits 1 when any check is red."""
    import sys

    from mona import doctor as d
    from mona.migrate import head_revision
    from mona.settings import Settings

    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception:  # noqa: BLE001
        checks = [d.Check("settings", d.RED, "invalid or missing settings (see `mona version`)")]
    else:
        host: list[d.Check] = []
        if host_lines:
            text = sys.stdin.read() if host_lines == "-" else Path(host_lines).read_text()
            host = d.parse_host_lines(text)
        checks = d.run_checks(
            settings, os.environ, head=head_revision(), host=host, privacy_asked=privacy
        )
    if as_json:
        for c in checks:
            typer.echo(json.dumps({"name": c.name, "level": c.level, "detail": c.detail}))
    else:
        for line in d.render(checks, color=sys.stdout.isatty()):
            typer.echo(line)
    if d.worst(checks) == d.RED:
        raise typer.Exit(1)


def perf(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Write the report skeleton only.")
    ] = False,
    batch: Annotated[
        Path | None, typer.Option(help="Folder holding the rehearsed live batch's files.")
    ] = None,
    order: Annotated[
        Path | None, typer.Option(help="File names in drop order, one per line.")
    ] = None,
    beats: Annotated[
        Path | None, typer.Option(help="JSON [{id, prompt}]; default: generic.")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Report folder; default <data>/perf.")] = None,
    cold: Annotated[bool, typer.Option(help="Unload llama-swap before the cold pass.")] = True,
    delay: Annotated[float, typer.Option(help="Seconds into the batch before chat starts.")] = 20.0,
    timeout: Annotated[
        float, typer.Option(help="Seconds to wait for the batch to finish.")
    ] = 900.0,
    vram_csv: Annotated[
        Path | None, typer.Option(help="nvidia-smi samples taken by the host wrapper.")
    ] = None,
) -> None:
    """Oct 8 budgets: classification per document, chat beats cold, warm and during a batch,
    llama-swap reloads, VRAM headroom. Writes perf-<time>.md and .json."""
    import asyncio

    from mona import perf as p
    from mona.settings import get_settings

    settings = get_settings()
    if batch is not None and not batch.is_dir():
        raise typer.BadParameter("not a folder", param_hint="--batch")
    if not dry_run and batch is None:
        raise typer.BadParameter("a real run needs the batch folder", param_hint="--batch")
    files = p.batch_files(batch, order) if batch else []
    beat_list = p.load_beats(beats)
    report = p.skeleton(settings, beat_list, files, dry_run=dry_run)
    if not dry_run:
        from sqlalchemy import select

        from mona.chat.hermes import get_hermes
        from mona.pipeline import runtime
        from mona.pipeline.intake import Upload, ingest_files
        from mona.pipeline.report import batch_report
        from mona.services.registry import T

        ctx = runtime.get_context()
        runtime.startup()

        def start() -> str:
            return ingest_files(ctx, [Upload(f, f.name) for f in files]).batch_id

        def done(batch_id: str) -> bool:
            with ctx.engine.connect() as conn:
                status = conn.execute(
                    select(T["batches"].c.status).where(T["batches"].c.id == batch_id)
                ).scalar()
            return status == "done"

        report = asyncio.run(
            p.measure(
                settings,
                beat_list,
                start,
                done,
                lambda b: batch_report(ctx, b),
                hermes=get_hermes(),
                cold=cold,
                delay_s=delay,
                batch_timeout_s=timeout,
                report=report,
            )
        )
        local = report["endpoint"] == "local"
        report["vram"] = p.vram_stats(vram_csv.read_text()) if vram_csv and local else None
        report["verdicts"] = p.verdicts(report)
    from mona.demo.tools import OpsEnv, chown_tree

    folder = out or settings.mona_data_dir / "perf"
    path = p.write_report(report, folder)
    chown_tree(folder, OpsEnv.from_settings(settings).data_owner)
    typer.echo(f"report: {path}")
    for name, verdict in (report["verdicts"] or {}).items():
        typer.echo(f"{verdict.upper():<12} {name}")
    if "fail" in (report["verdicts"] or {}).values():
        raise typer.Exit(1)


profile_app = typer.Typer(no_args_is_help=True, help="The owner profile (C2 §2.1).")


@profile_app.command("set-password")
def set_password() -> None:
    """Reset the unlock password (prompted, never an argument); ends every session."""
    from sqlalchemy import update

    from mona import clock
    from mona.api.auth import hasher
    from mona.db import get_sync_engine
    from mona.db.models import AuthSession, Profile

    password = typer.prompt("New password", hide_input=True, confirmation_prompt=True)
    if len(password) < MIN_PASSWORD:
        typer.echo(f"The password needs at least {MIN_PASSWORD} characters.", err=True)
        raise typer.Exit(1)
    now = clock.now()
    with get_sync_engine().begin() as conn:
        found = conn.execute(
            update(Profile).values(
                password_hash=hasher.hash(password), password_changed_at=now, updated_at=now
            )
        ).rowcount
        conn.execute(
            update(AuthSession)
            .where(AuthSession.revoked_at.is_(None))
            .values(revoked_at=now, updated_at=now)
        )
    if not found:
        typer.echo("No profile yet: load the seed first.", err=True)
        raise typer.Exit(1)
    typer.echo("password changed; every session must unlock again")


def register(app: typer.Typer) -> None:
    app.callback()(gate)
    app.command("check-prod")(check_prod)
    app.command("doctor")(doctor)
    app.command("perf")(perf)
    app.add_typer(profile_app, name="profile")
