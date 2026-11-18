"""A57: `privacy.provider_extra_body` reads the installed config in both forms, the seeded
`custom_providers` and the `providers.<key>` Hermes' boot migration writes, for A5 and for
`mona chat-replay --extra-from`."""

import copy

import pytest
import yaml

from mona import chat_replay as cr
from mona.privacy import LLM_EXTRA_BODY, hermes_config_problems, provider_extra_body
from tests.hermes_image import HERMES, PROD_ENV
from tests.hermes_replay import MIGRATED

SEEDED = HERMES / "config.prod.yaml"
FORMS = {"seeded": SEEDED, "migrated": MIGRATED}
RESOLVE = lambda host: ["10.0.0.5"]  # noqa: E731


def load(form: str) -> dict:
    return yaml.safe_load(FORMS[form].read_text())


def entry_of(cfg: dict) -> dict:
    return (
        cfg["custom_providers"][0] if "custom_providers" in cfg else cfg["providers"]["mona-local"]
    )


@pytest.mark.parametrize("form", FORMS)
def test_both_forms_give_the_a57_extra_body_and_pass_a5(form):
    cfg = load(form)
    assert ("providers" in cfg) == (form == "migrated")
    assert provider_extra_body(cfg, PROD_ENV) == LLM_EXTRA_BODY
    assert hermes_config_problems(cfg, PROD_ENV, RESOLVE) == []


@pytest.mark.parametrize("form", FORMS)
def test_extra_from_reads_both_forms(form, monkeypatch):
    for k, v in PROD_ENV.items():
        monkeypatch.setenv(k, v)
    assert cr.merge_extra(FORMS[form], None, none=False) == (LLM_EXTRA_BODY, "config")
    assert cr.config_effort(FORMS[form]) == ("medium", "config")


@pytest.mark.parametrize("form", FORMS)
def test_a_base_url_mismatch_or_a_model_key_is_caught_in_both_forms(form):
    cfg = load(form)
    other = copy.deepcopy(cfg)
    entry = entry_of(other)
    entry["api" if "api" in entry else "base_url"] = "http://other:8080/v1"
    assert provider_extra_body(other, PROD_ENV) == {}
    assert hermes_config_problems(other, PROD_ENV, RESOLVE) == [
        "custom_providers has no entry whose base_url is model.base_url"
    ]
    named = copy.deepcopy(cfg)
    entry_of(named)["default_model" if form == "migrated" else "model"] = "qwen36"
    assert hermes_config_problems(named, PROD_ENV, RESOLVE) == [
        "custom_providers entry for model.base_url names a model"
    ]


def test_the_first_matching_entry_with_an_extra_body_wins_as_in_hermes():
    cfg = load("seeded")
    first = {"name": "bare", "base_url": cfg["model"]["base_url"] + "/"}
    cfg["custom_providers"].insert(0, first)
    assert provider_extra_body(cfg, PROD_ENV) == LLM_EXTRA_BODY
    assert hermes_config_problems(cfg, PROD_ENV, RESOLVE) == []
    first["extra_body"] = {"presence_penalty": 0.5}
    assert provider_extra_body(cfg, PROD_ENV) == {"presence_penalty": 0.5}
    assert "custom_providers extra_body.presence_penalty is not 1.5" in hermes_config_problems(
        cfg, PROD_ENV, RESOLVE
    )
