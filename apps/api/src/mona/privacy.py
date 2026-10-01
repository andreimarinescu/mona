"""C9 §1.2 and §2.1: the prod assertions. Messages name the check and the variable or key, never
a value."""

import ipaddress
import os
import re
import socket
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from mona.settings import Settings, SettingsError

CLOUD_KEYS = (
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
    "GEMINI_API_KEY", "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY", "GROQ_API_KEY",
    "TOGETHER_API_KEY", "NOUS_API_KEY", "HF_TOKEN",
)  # fmt: skip
CLOUD_HOSTS = (
    "openrouter.ai", "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com",
    "api.mistral.ai", "api.deepseek.com", "api.x.ai", "api.groq.com", "api.together.xyz",
)  # fmt: skip
PRIVATE_NETS = [
    ipaddress.ip_network(n)
    for n in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
              "::1/128", "fe80::/10", "fc00::/7")
]  # fmt: skip
DISABLED_TOOLSETS = (
    "terminal", "code_execution", "file", "web", "browser", "computer_use", "delegation",
    "image_gen", "tts", "vision", "session_search", "cronjob", "skills", "todo",
)  # fmt: skip
NEVER_DISABLED = ("mona", "mona_tg", "memory")
AUXILIARY_TASKS = (
    "vision", "compression", "skills_hub", "approval", "review", "mcp", "title_generation",
    "memory_query_rewrite", "tts_audio_tags", "triage_specifier", "kanban_decomposer",
    "profile_describer", "goal_judge", "curator", "monitor", "background_review",
    "moa_reference", "moa_aggregator",
)  # fmt: skip
PLATFORM_TOOLSETS = {
    "api_server": ["memory", "mona"],
    "telegram": ["memory", "mona_tg"],
    "cron": ["mona_tg"],
}
MCP_URL = "http://api:8765/mcp"
CHANNELS = {"mona": "web", "mona_tg": "telegram"}


class ProdCheckFailed(SettingsError):
    def __init__(self, check: str, subject: str, why: str) -> None:
        super().__init__(f"prod check {check} failed: {subject} {why}")
        self.check, self.subject = check, subject


Resolver = Callable[[str], Iterable[str]]


def _resolve(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def _private(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in net for net in PRIVATE_NETS)


def llm_endpoint_problem(url: str | None, resolve: Resolver = _resolve) -> str | None:
    """Why `url` isn't an acceptable prod model endpoint (§1.2), or None."""
    if not url:
        return "is not set"
    parts = urlsplit(url)
    host = (parts.hostname or "").rstrip(".").lower()
    if parts.scheme not in ("http", "https") or not host:
        return "is not an http(s) URL"
    if any(host == h or host.endswith("." + h) for h in CLOUD_HOSTS):
        return "names a cloud API host"
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = list(resolve(host))
        except (OSError, UnicodeError):
            addresses = []
        if not addresses:
            if "." not in host:
                return None
            return "does not resolve"
    if not all(_private(a) for a in addresses):
        return "resolves to a public address"
    return None


def require_local_llm(url: str | None, resolve: Resolver = _resolve) -> str:
    """The guard for `mona.llm` in prod: returns the URL or raises (A2)."""
    problem = llm_endpoint_problem(url, resolve)
    if problem:
        raise ProdCheckFailed("A2", "MONA_LLM_BASE_URL", problem)
    return url  # type: ignore[return-value]


def cloud_keys_set(env: Mapping[str, str]) -> list[str]:
    return [k for k in CLOUD_KEYS if (env.get(k) or "").strip()]


def check_env(env: Mapping[str, str], check: str) -> None:
    """A1 (this process) or A3 (a container's environment, by name)."""
    found = cloud_keys_set(env)
    if found:
        raise ProdCheckFailed(check, ", ".join(found), "is set; prod has no cloud key")


def assert_process_env(settings: Settings, env: Mapping[str, str] | None = None) -> None:
    """A1 and A2, at the start of every prod process (§2.2)."""
    check_env(os.environ if env is None else env, "A1")
    require_local_llm(settings.mona_llm_base_url)


def check_hermes_env_file(path: Path) -> None:
    """A4: no cloud key with a non-empty value in the profile's `.env`."""
    if not path.exists():
        return
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    check_env(values, "A4")


def _get(cfg: Mapping[str, Any], dotted: str) -> Any:
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return _MISSING
        node = node[part]
    return node


_MISSING = object()
_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(value: Any, env: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return _VAR.sub(lambda m: env.get(m.group(1), ""), value)
    return value


def hermes_config_problems(
    cfg: Mapping[str, Any], env: Mapping[str, str], resolve: Resolver = _resolve
) -> list[str]:
    """A5: every §4.1 key, compared; returns one line per wrong key (key names only)."""
    out: list[str] = []

    def expect(key: str, wanted: Any) -> None:
        if _get(cfg, key) != wanted:
            out.append(f"{key} is not {wanted!r}")

    expect("model.provider", "custom")
    problem = llm_endpoint_problem(_expand(_get(cfg, "model.base_url"), env) or None, resolve)
    if problem:
        out.append(f"model.base_url {problem}")
    if not _expand(_get(cfg, "model.default"), env) or _get(cfg, "model.default") is _MISSING:
        out.append("model.default is empty")
    expect("model.context_length", 65536)
    expect("agent.reasoning_effort", "medium")
    disabled = _get(cfg, "agent.disabled_toolsets")
    disabled = disabled if isinstance(disabled, list) else []
    for name in DISABLED_TOOLSETS:
        if name not in disabled:
            out.append(f"agent.disabled_toolsets lacks {name}")
    for name in NEVER_DISABLED:
        if name in disabled:
            out.append(f"agent.disabled_toolsets names {name}")
    expect("platform_toolsets", PLATFORM_TOOLSETS)
    servers = _get(cfg, "mcp_servers")
    if not isinstance(servers, Mapping) or set(servers) != set(CHANNELS):
        out.append("mcp_servers is not exactly mona and mona_tg")
    else:
        for name, channel in CHANNELS.items():
            s = servers[name] or {}
            headers = s.get("headers") or {}
            if s.get("url") != MCP_URL or headers.get("X-Mona-Channel") != channel:
                out.append(f"mcp_servers.{name} is not {MCP_URL} on channel {channel}")
            if headers.get("Authorization") != "Bearer ${MONA_SERVICE_KEY}":
                out.append(f"mcp_servers.{name}.headers.Authorization is not the service key")
    expect("tools.tool_search.enabled", False)
    expect("skills.write_approval", True)
    expect("skills.project_discovery", False)
    expect("memory.write_approval", False)
    aux = _get(cfg, "auxiliary")
    aux = aux if isinstance(aux, Mapping) else {}
    for task in sorted(set(AUXILIARY_TASKS) | set(aux)):
        if _get(aux, f"{task}.provider") != "main":
            out.append(f"auxiliary.{task}.provider is not 'main'")
    expect("auxiliary.title_generation.enabled", False)
    expect("auxiliary.background_review.enabled", False)
    expect("curator.enabled", False)
    expect("updates.check", False)
    expect("openrouter.response_cache", False)
    expect("telemetry.shared_metrics.enabled", False)
    if _get(cfg, "provider_routing") is not _MISSING:
        out.append("provider_routing is set")
    return out


def check_hermes_config(path: Path, env: Mapping[str, str], resolve: Resolver = _resolve) -> None:
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        raise ProdCheckFailed("A5", str(path.name), "can't be read") from None
    problems = hermes_config_problems(cfg, env, resolve)
    if problems:
        raise ProdCheckFailed("A5", "config.yaml", "; ".join(problems))


def check_hermes_home(home: Path, env: Mapping[str, str] | None = None) -> None:
    """A4 and A5 on an installed Hermes profile (`hermes-seed`, §2.2)."""
    check_hermes_env_file(home / ".env")
    check_hermes_config(home / "config.yaml", os.environ if env is None else env)


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class ModelEndpoint:
    base_url: str
    local: bool


def model_endpoint(settings: Settings) -> ModelEndpoint:
    """The one model endpoint (§1.2) for `mona.llm`: in prod the checked local URL, never the
    cloud; in dev `MONA_LLM_BASE_URL` when set, else OpenRouter."""
    if settings.mona_env == "prod":
        return ModelEndpoint(require_local_llm(settings.mona_llm_base_url), True)
    if settings.mona_llm_base_url:
        return ModelEndpoint(settings.mona_llm_base_url, True)
    return ModelEndpoint(OPENROUTER_BASE_URL, False)


def guard_model_url(url: str, settings: Settings) -> str:
    """Fail closed at call time: in prod a request may only go to the configured local endpoint."""
    if settings.mona_env != "prod":
        return url
    base = urlsplit(model_endpoint(settings).base_url)
    target = urlsplit(url)
    if (target.scheme, target.hostname, target.port) != (base.scheme, base.hostname, base.port):
        raise ProdCheckFailed("A2", "model request", "targets a host other than MONA_LLM_BASE_URL")
    return url
