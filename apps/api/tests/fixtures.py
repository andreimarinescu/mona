import json
from pathlib import Path

SPIKES = Path(__file__).resolve().parents[3] / "docs" / "spikes"
S1_OVERLAY_STREAM = SPIKES / "s1" / "fixtures" / "completions-stream-overlay.sse"
S1_OVERLAY_GOLDEN = SPIKES / "s5" / "fixtures" / "completions-stream-overlay.ui-chunks.json"
S5_TWO_TOOLS_STREAM = SPIKES / "s5" / "fixtures" / "completions-stream-two-tools.sse"
S5_SESSION_MESSAGES = SPIKES / "s5" / "fixtures" / "session-messages.json"


def fixture_lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def upstream_deltas(path: Path, key: str) -> str:
    out = ""
    for line in fixture_lines(path):
        if line.startswith('data: {"id"'):
            for choice in json.loads(line[6:])["choices"]:
                out += choice["delta"].get(key) or ""
    return out
