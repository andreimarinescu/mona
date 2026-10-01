"""C9 §8 test 9's judge (L6): `egress-analyze` on tcpdump text, and `egress-test --plan`."""

import stat
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[3] / "deploy" / "bin"
INTERNAL = ["--internal", "172.29.250.0/24"]
RESOLVER = "192.168.1.1"
TG_IP = "149.154.167.220"

QUERY = "1700000000.1 IP 172.29.250.5.40001 > {r}.53: 4242+ A? api.telegram.org. (34)"
ANSWER = "1700000000.2 IP {r}.53 > 172.29.250.5.40001: 4242 1/0/0 A {ip} (50)"
HTTPS = "1700000001.0 IP 172.29.250.5.40002 > {ip}.443: Flags [S], seq 1, length 0"


def judge(tmp_path: Path, *lines: str, extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    capture = tmp_path / "capture.txt"
    capture.write_text("\n".join(lines) + "\n")
    return subprocess.run(
        [sys.executable, str(BIN / "egress-analyze"), str(capture), *INTERNAL, *extra],
        capture_output=True, text=True,
    )  # fmt: skip


def telegram(ip: str = TG_IP) -> list[str]:
    return [QUERY.format(r=RESOLVER), ANSWER.format(r=RESOLVER, ip=ip), HTTPS.format(ip=ip)]


def test_no_outbound_packet_at_all_passes(tmp_path):
    internal = "1700000000.1 IP 172.29.250.5.40001 > 172.29.250.2.5432: Flags [S], length 0"
    r = judge(tmp_path, internal)
    assert r.returncode == 0 and "no packet left the compose subnets" in r.stdout


def test_telegram_only_passes_and_names_the_basis(tmp_path):
    r = judge(tmp_path, *telegram())
    assert r.returncode == 0, r.stdout
    assert f"{TG_IP}" in r.stdout and "dns answer for api.telegram.org" in r.stdout
    assert f"{RESOLVER}" in r.stdout and "resolver" in r.stdout


def test_a_telegram_address_outside_the_answers_passes_on_the_published_ranges(tmp_path):
    r = judge(tmp_path, HTTPS.format(ip="149.154.175.50"))
    assert r.returncode == 0 and "telegram range" in r.stdout


def test_an_ip_outside_telegram_fails_and_is_named(tmp_path):
    r = judge(tmp_path, *telegram(), HTTPS.format(ip="104.18.2.115"))
    assert r.returncode == 1 and "FAIL: destination 104.18.2.115" in r.stdout
    assert "NOT ALLOWED" in r.stdout


def test_a_dns_query_for_another_name_fails_even_without_traffic(tmp_path):
    other = "1700000000.1 IP 172.29.250.5.40001 > 192.168.1.1.53: 7+ A? openrouter.ai. (30)"
    r = judge(tmp_path, other)
    assert r.returncode == 1 and "DNS query for openrouter.ai" in r.stdout


def test_an_edns_query_and_ipv6_destinations_are_understood(tmp_path):
    q = "1700000000.1 IP6 fd00::5.40001 > fd00::1.53: 9+ [1au] AAAA? api.telegram.org. (45)"
    a = "1700000000.2 IP6 fd00::1.53 > fd00::5.40001: 9 1/0/0 AAAA 2001:67c:4e8:f004::9 (70)"
    t = "1700000001.0 IP6 fd00::5.40003 > 2001:67c:4e8:f004::9.443: Flags [S], length 0"
    r = judge(tmp_path, q, a, t, extra=("--internal", "fd00::/64"))
    assert r.returncode == 0, r.stdout


def test_multicast_and_replies_from_outside_are_not_destinations(tmp_path):
    noise = [
        "1700000000.1 IP 172.29.250.5.5353 > 224.0.0.251.5353: UDP, length 40",
        f"1700000002.0 IP {TG_IP}.443 > 172.29.250.5.40002: Flags [S.], length 0",
    ]
    assert judge(tmp_path, *noise).returncode == 0


def test_an_extra_allowed_range_is_honoured(tmp_path):
    line = HTTPS.format(ip="203.0.113.7")
    assert judge(tmp_path, line).returncode == 1
    assert judge(tmp_path, line, extra=("--allow-cidr", "203.0.113.0/24")).returncode == 0


def stub(tmp_path: Path) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    docker = bindir / "docker"
    docker.write_text(
        """#!/bin/sh
case "$*" in
  *"ps -q api"*) echo c1 ;;
  *"inspect -f"*Networks*) printf 'mona_default' ;;
  *"network inspect -f {{.Id}}"*) echo 0123456789abcdef0123 ;;
  *"network inspect"*) printf '172.29.250.0/24\\n' ;;
esac
"""
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    return {"PATH": f"{bindir}:/usr/bin:/bin", "MONA_ROOT": str(BIN.parents[1]),
            "MONA_COMPOSE": "docker compose", "HOME": str(tmp_path)}  # fmt: skip


def test_plan_resolves_the_bridge_without_capturing(tmp_path):
    r = subprocess.run(
        [str(BIN / "egress-test"), "--plan", "--idle", "60"], env=stub(tmp_path),
        capture_output=True, text=True,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    assert "interface:  br-0123456789ab" in r.stdout and "172.29.250.0/24" in r.stdout
    assert "idle:       60 s" in r.stdout and "demo-reset --yes" in r.stdout


@pytest.mark.skipif(
    subprocess.run(["id", "-u"], capture_output=True, text=True).stdout.strip() == "0",
    reason="root can capture",
)
def test_capture_refuses_without_root(tmp_path):
    env = stub(tmp_path)
    (tmp_path / "bin" / "tcpdump").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "tcpdump").chmod(0o755)
    r = subprocess.run([str(BIN / "egress-test")], env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "run with sudo" in r.stderr
