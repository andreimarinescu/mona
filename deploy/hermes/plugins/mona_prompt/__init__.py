"""Mona's Hermes plugin (A57): an `llm_request` middleware that applies `cut.py` to the system
message of every LLM request and leaves the rest of the request as it is."""

import logging

from .cut import cut_system_prompt, unrecognized

logger = logging.getLogger(__name__)
_warned = False


def _warn_once(what: str) -> None:
    global _warned
    if not _warned:
        _warned = True
        logger.warning("mona_prompt: %s; left whole", what)


def _cut(content):
    if isinstance(content, str):
        text, removed = cut_system_prompt(content)
        return text, removed, unrecognized(text)
    if not isinstance(content, list):
        return None, [], []
    parts, removed, left = [], [], []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
            text, cut = cut_system_prompt(part["text"])
            parts.append({**part, "text": text} if cut else part)
            removed += cut
            left += unrecognized(text)
        else:
            parts.append(part)
    return parts, removed, left


def on_llm_request(request=None, **_):
    messages = request.get("messages") if isinstance(request, dict) else None
    if not isinstance(messages, list):
        _warn_once("an LLM request without a messages list")
        return None
    out, removed = list(messages), []
    for i, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") not in ("system", "developer"):
            continue
        content, cut, left = _cut(message.get("content"))
        if content is None:
            _warn_once("a system message of an unknown shape")
            continue
        if left:
            _warn_once("unrecognized prompt sections " + ", ".join(left))
        if cut:
            out[i] = {**message, "content": content}
            removed += cut
    if not removed:
        return None
    return {"request": {**request, "messages": out}, "name": "mona_prompt",
            "reason": "cut " + ", ".join(dict.fromkeys(removed))}


def register(ctx) -> None:
    ctx.register_middleware("llm_request", on_llm_request)
