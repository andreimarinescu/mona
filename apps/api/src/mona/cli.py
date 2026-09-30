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
