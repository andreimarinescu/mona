"""The dev stack's host-owned mounts (compose, Makefile) and the e2e worker count (Makefile, CI)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def services() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]


def make_rule(target: str) -> tuple[str, list[str]]:
    m = re.search(
        rf"^{re.escape(target)}:(.*)\n((?:\t.*\n)*)", (ROOT / "Makefile").read_text(), re.M
    )
    assert m, target
    return m.group(1), [line.strip() for line in m.group(2).splitlines()]


def test_the_web_container_runs_as_the_host_user_like_the_python_ones():
    s = services()
    assert s["web"]["user"] == s["api"]["user"] == "${MONA_UID:-1000}:${MONA_GID:-1000}"
    assert s["web"]["environment"]["HOME"] == "/tmp"


def test_its_node_modules_volumes_are_chowned_to_the_host_user_first():
    s = services()
    init = s["web-volumes"]
    assert init["user"] == "0:0" and init["restart"] == "no"
    assert s["web"]["depends_on"]["web-volumes"] == {"condition": "service_completed_successfully"}
    web_volumes = {v.split(":")[0] for v in s["web"]["volumes"] if not v.startswith("./")}
    assert {v.split(":")[0] for v in init["volumes"]} == web_volumes
    script = init["command"][0]
    assert "chown -R ${MONA_UID:-1000}:${MONA_GID:-1000}" in script
    assert script.count("/volumes/") == len(web_volumes)


def test_make_up_creates_the_bind_mountpoints_before_compose():
    prereqs, _ = make_rule("up")
    assert {"node_modules", "apps/web/node_modules", "data"} <= set(prereqs.split())
    assert make_rule("apps/web/node_modules")[1] == ["mkdir -p apps/web/node_modules"]


def test_make_e2e_and_the_ci_job_run_playwright_at_two_workers():
    assert make_rule("e2e")[1] == ["$(WEB) e2e -- --workers=2"]
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    assert {"run": "make e2e"} in ci["jobs"]["e2e"]["steps"]


def test_workers_run_under_an_init_so_a_stop_right_after_start_is_not_ignored():
    s = services()
    assert s["worker-llm"]["init"] is True and s["worker-cpu"]["init"] is True
