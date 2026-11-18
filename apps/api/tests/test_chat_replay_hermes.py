"""`mona chat-replay` against the pinned Hermes image: the replayed request carries the tools and
the reasoning effort Hermes sends, and the provider extra body is read from the config Hermes'
boot migration writes."""

import json

import pytest
import yaml

from mona import chat_replay as cr
from mona import privacy
from mona.mcp.server import mcp
from tests.hermes_image import DEV_ENV, HERMES, PROD_ENV
from tests.hermes_replay import MIGRATED, migrated, request_kwargs

CONFIGS = {
    "dev": (HERMES / "config.yaml", DEV_ENV),
    "prod": (HERMES / "config.prod.yaml", PROD_ENV),
}


@pytest.fixture(scope="module")
def served():
    """Mona's tools as its MCP server lists them, `ingest_attachment` included."""
    import asyncio

    tools = asyncio.run(mcp.list_tools())
    return [
        {"name": t.name, "description": t.description, "inputSchema": t.parameters} for t in tools
    ]


@pytest.fixture(scope="module")
def image(served):
    return {name: request_kwargs(path, env, served) for name, (path, env) in CONFIGS.items()}


@pytest.mark.parametrize("config", ["dev", "prod"])
async def test_the_replayed_tools_are_byte_for_byte_the_ones_hermes_sends(image, config):
    sent = [t for t in image[config]["tools"] if t["function"]["name"] != "memory"]
    assert len(sent) == len(image[config]["tools"]) - 1
    assert json.dumps(await cr.mona_tools()) == json.dumps(sent)


def test_the_replayed_request_carries_hermes_reasoning_effort_and_extra_body(image, monkeypatch):
    path, env = CONFIGS["prod"]
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    extra, _ = cr.merge_extra(path, None, none=False)
    effort, source = cr.config_effort(path)
    body = cr.request_body("m", {"user": "U", "history": []}, "S", [], extra, effort)
    sent = image["prod"]
    assert body["reasoning_effort"] == sent["reasoning_effort"] == "medium" and source == "config"
    assert extra == sent["extra_body"] == privacy.LLM_EXTRA_BODY
    assert {k: body[k] for k in sent["extra_body"]} == sent["extra_body"]
    _, no_extra = cr.merge_extra(path, None, none=True)
    bare = cr.request_body("m", {"user": "U", "history": []}, "S", [], {}, effort)
    assert bare["reasoning_effort"] == sent["reasoning_effort"] and no_extra == "none"
    dev_path, _ = CONFIGS["dev"]
    assert cr.config_effort(dev_path)[0] == image["dev"]["extra_body"]["reasoning"]["effort"]


def test_the_migrated_fixture_is_what_the_pinned_image_writes():
    written = migrated(HERMES / "config.prod.yaml")
    assert "custom_providers" not in written and set(written["providers"]) == {"mona-local"}
    assert written == yaml.safe_load(MIGRATED.read_text())


def test_hermes_reads_the_migrated_providers_entry_as_provider_extra_body_does(served):
    sent = request_kwargs(MIGRATED, PROD_ENV, served)
    cfg = yaml.safe_load(MIGRATED.read_text())
    assert sent["extra_body"] == privacy.provider_extra_body(cfg, PROD_ENV)
    assert sent["reasoning_effort"] == cr.config_effort(MIGRATED)[0]
