import json
import logging

import typer
from typer.testing import CliRunner

from mona import __version__, logs
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


def _leaf_commands(group, prefix=()):
    for name, cmd in group.commands.items():
        if hasattr(cmd, "commands"):
            yield from _leaf_commands(cmd, (*prefix, name))
        else:
            yield (*prefix, name)


class LoggingConfigured(Exception):
    pass


def test_every_command_configures_logging_first(monkeypatch):
    def stop(level=logging.INFO):
        raise LoggingConfigured

    monkeypatch.setattr(logs, "configure_logging", stop)
    paths = list(_leaf_commands(typer.main.get_command(app)))
    assert {("pipeline", "run"), ("purge-visitors",), ("seed", "load"), ("ops", "verify")} <= set(
        paths
    )
    for path in paths:
        res = runner.invoke(app, [*path, "--help"])
        assert isinstance(res.exception, LoggingConfigured), path


def test_a_command_runs_with_the_log_hygiene_filter():
    assert runner.invoke(app, ["version"]).exit_code == 0
    handlers = logging.getLogger().handlers
    assert any(isinstance(f, logs.SafeExceptions) for h in handlers for f in h.filters)
    assert logging.getLogger("mona").level == logging.INFO
