"""A57's prompt check: the plugin's cut applied to a prompt Hermes stored, then A57's markers.

Lines name markers and sections only, never prompt text (C9 §7). Stdlib only: `doctor-host` pipes
this file into the Hermes container, where `main` reads the newest web session read-only."""

import contextlib
import json
import os
import sqlite3
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

GREEN, AMBER, RED = "green", "amber", "red"
MARKERS = (
    "# Hermes runtime environment",
    "Terminal backend: ",
    "/mnt/c/",
    "# Finishing the job",
    "# Parallel tool calls",
    "[OUT-OF-BAND USER MESSAGE",
    "hermes-agent.nousresearch.com",
    "The rendering layer is unknown — assume plain text. No markdown",
)
PLUGIN = "mona_prompt"
WEB_SOURCE = "api_server"
NO_CONVERSATION = "no conversation since the release"
STALE = "Hermes started before the installed plugin: restart Hermes"

Cut = Callable[[str], tuple[str, list[str]]]
Line = tuple[str, str, str]


def load_cut(path: Path) -> Cut:
    """`cut_system_prompt` from the plugin's `cut.py`, loaded by path without writing bytecode."""
    module = types.ModuleType("mona_prompt_cut")
    module.__file__ = str(path)
    exec(compile(Path(path).read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module.cut_system_prompt


def surviving_markers(prompt: str, cut: Cut) -> list[str]:
    text, _ = cut(prompt)
    return [m for m in MARKERS if m in text]


def prompt_line(prompt: str | None, cut: Cut | None) -> Line:
    if prompt is None:
        return AMBER, "prompt", NO_CONVERSATION
    if cut is None:
        return RED, "prompt", "the plugin's cut.py is not installed"
    left = surviving_markers(prompt, cut)
    if left:
        return RED, "prompt", "A57 markers survive the cut: " + "; ".join(repr(m) for m in left)
    _, removed = cut(prompt)
    detail = "newest web conversation: no A57 marker"
    return GREEN, "prompt", detail + (f" (cut: {', '.join(removed)})" if removed else "")


def plugin_line(
    state: dict[str, Any] | None, started: float | None, installed: float | None
) -> Line:
    """A fresh-process `plugin_state`, red unless the running gateway started after the install."""
    if state is None:
        return RED, "plugin", "Hermes' plugin manager could not be queried"
    if not state.get("found"):
        return RED, "plugin", f"{PLUGIN} is not installed in the Hermes profile"
    if not state.get("enabled") and not state.get("failed"):
        return RED, "plugin", f"{PLUGIN} is not enabled in plugins.enabled"
    if state.get("failed"):
        return RED, "plugin", f"{PLUGIN} failed to load"
    if not state.get("middleware"):
        return RED, "plugin", f"{PLUGIN} loaded but registered no llm_request middleware"
    if started is None:
        return RED, "plugin", "the running Hermes gateway's start time could not be read"
    if installed is None:
        return RED, "plugin", f"the installed {PLUGIN} files could not be read"
    if started < installed:
        return RED, "plugin", STALE
    return GREEN, "plugin", f"{PLUGIN} loaded, llm_request middleware registered"


def gateway_started(home: Path) -> float | None:
    """The mtime of `gateway.pid`, which the gateway creates once at start, while its PID lives."""
    path = home / "gateway.pid"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        pid = int(record["pid"] if isinstance(record, dict) else record)
        if not Path(f"/proc/{pid}").is_dir():
            return None
        return path.stat().st_mtime
    except (OSError, ValueError, KeyError, TypeError):
        return None


def plugin_installed(folder: Path) -> float | None:
    """The newest mtime of the installed plugin's folder and files."""
    try:
        return max(p.stat().st_mtime for p in (folder, *folder.iterdir()))
    except OSError:
        return None


def newest_web_prompt(db: Path, since: float) -> str | None:
    """The stored prompt of the newest web session started at or after `since`, read-only."""
    if not db.is_file():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT COALESCE(sp.prompt, s.system_prompt), s.started_at FROM sessions s"
            " LEFT JOIN system_prompts sp ON sp.hash = s.system_prompt_hash"
            " WHERE s.source = ? AND COALESCE(sp.prompt, s.system_prompt) IS NOT NULL"
            " ORDER BY s.started_at DESC LIMIT 1",
            (WEB_SOURCE,),
        ).fetchone()
    finally:
        con.close()
    if row is None or row[1] < since:
        return None
    return row[0]


def plugin_state() -> dict[str, Any]:
    """Runs inside the Hermes container: a fresh discovery by Hermes' own plugin manager."""
    sys.path.insert(0, "/opt/hermes")
    with contextlib.redirect_stdout(sys.stderr):
        from hermes_cli.plugins import get_plugin_manager

        manager = get_plugin_manager()
        manager.discover_and_load()
        entry = next((p for p in manager.list_plugins() if p.get("key") == PLUGIN), None)
    if entry is None:
        return {"found": False}
    error = str(entry.get("error") or "")
    return {
        "found": True,
        "enabled": bool(entry.get("enabled")),
        "failed": bool(error) and not error.startswith("not enabled"),
        "middleware": bool(entry.get("middleware")),
    }


def main() -> int:
    home = Path(os.environ.get("HERMES_HOME") or "/opt/data")
    cut_py = home / "plugins" / PLUGIN / "cut.py"
    cut = load_cut(cut_py) if cut_py.is_file() else None
    try:
        since = (home / "config.yaml").stat().st_mtime
    except OSError:
        since = 0.0
    try:
        state = plugin_state()
    except Exception:
        state = None
    plugin = plugin_line(state, gateway_started(home), plugin_installed(home / "plugins" / PLUGIN))
    lines = [plugin, prompt_line(newest_web_prompt(home / "state.db", since), cut)]
    sys.stdout.write("".join("\t".join(line) + "\n" for line in lines))
    sys.stdout.flush()
    return 0


def parse(text: str) -> dict[str, tuple[str, str]]:
    out = {}
    for raw in text.splitlines():
        parts = raw.split("\t")
        if len(parts) == 3 and parts[0] in (GREEN, AMBER, RED):
            out[parts[1]] = (parts[0], parts[2])
    return out


if __name__ == "__main__":
    sys.exit(main())
