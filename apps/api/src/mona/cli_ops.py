"""`mona` commands for operations: the settings gate, `check-prod` (C9 §2) and
`profile set-password` (C2 §2.1)."""

import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from mona.settings import SettingsError

UNGATED = {"check-prod"}
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
    app.add_typer(profile_app, name="profile")
