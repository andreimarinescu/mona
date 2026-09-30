import json

from typer.testing import CliRunner

from mona import __version__
from mona.cli import DEFAULT_OPENAPI, app

runner = CliRunner()


def test_version():
    res = runner.invoke(app, ["version"])
    assert res.exit_code == 0
    assert res.output.strip() == __version__


def test_openapi_export_matches_committed_schema(tmp_path):
    out = tmp_path / "openapi.json"
    res = runner.invoke(app, ["openapi", "--output", str(out)])
    assert res.exit_code == 0
    assert "/api/health" in json.loads(out.read_text())["paths"]
    assert out.read_text() == DEFAULT_OPENAPI.read_text(), "run `uv run mona openapi`"
