"""C9 §8 test 5 capture, run on the pinned image with the prod profile as its config:

docker run --rm -i -v "$PWD/deploy/hermes/config.prod.yaml:/opt/data/config.yaml:ro" \
  --entrypoint /opt/hermes/.venv/bin/python <image> - < apps/api/tests/hermes_lockdown.py
"""

import json
import os
import sys

sys.path.insert(0, "/opt/hermes")
os.chdir("/opt/hermes")

from hermes_cli.config import load_config  # noqa: E402
from hermes_cli.tools_config import PLATFORMS, _get_platform_tools  # noqa: E402

cfg = load_config()
resolved = {p: sorted(_get_platform_tools(cfg, p)) for p in sorted(PLATFORMS)}
resolved.setdefault("cron", sorted(_get_platform_tools(cfg, "cron")))
print(
    json.dumps(
        {
            "disabled_toolsets": cfg["agent"]["disabled_toolsets"],
            "terminal_backend": cfg["terminal"]["backend"],
            "platform_tools": resolved,
        },
        indent=2,
    )
)
