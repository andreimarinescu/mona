"""The interview calls on the pipeline's model client: request shapes, deltas, the stall cut."""

import asyncio
import json
import time

import httpx
import pytest

pytest.importorskip("mona.pipeline.model")

from mona.interviews.llm import InterviewClient  # noqa: E402
from mona.interviews.model import ModelError  # noqa: E402

FLASH, QWEN36 = "qwen/qwen3.7-flash", "qwen/qwen3.6-35b-a3b"


def sse(*deltas: dict, pause_after: int | None = None, pause_s: float = 0.0):
    async def body():
        for n, delta in enumerate(deltas):
            chunk = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m",
                     "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}  # fmt: skip
            yield f"data: {json.dumps(chunk)}\n\n".encode()
            if pause_after == n:
                await asyncio.sleep(pause_s)
        yield b"data: [DONE]\n\n"

    return body()


def make(model: str, respond, backend: str = "openrouter") -> tuple[InterviewClient, list]:
    seen: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return respond(request)

    base = "http://llama:8080/v1" if backend == "llama-server" else None
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return InterviewClient(model=model, backend=backend, base_url=base, http_client=http), seen


def streamed(*deltas: dict, **kw):
    return lambda _: httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content=sse(*deltas, **kw)
    )


@pytest.mark.parametrize("model", [FLASH, QWEN36])
def test_pass1_streams_with_thinking_on_and_splits_reasoning_from_content(model):
    llm, seen = make(model, streamed({"reasoning": "think "}, {"content": "- AGIPI: split."}))
    out = list(llm.stream("sys", "user", temperature=0.6, max_tokens=12000, timeout_s=5))
    assert out == [("reasoning", "think "), ("content", "- AGIPI: split.")]
    body = seen[0]
    assert body["stream"] is True and body["model"] == model
    assert (body["temperature"], body["max_tokens"]) == (0.6, 12000)
    assert body["reasoning"] == {"enabled": True}
    assert ("provider" in body) is (model == QWEN36)
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_llama_server_thinking_uses_the_template_flag():
    llm, seen = make(QWEN36, streamed({"reasoning_content": "hm"}), backend="llama-server")
    assert list(llm.stream("s", "u", temperature=0.6, max_tokens=10, timeout_s=5)) == [
        ("reasoning", "hm")
    ]
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": True}
    assert "reasoning" not in seen[0] and "provider" not in seen[0]


def test_a_silent_stream_ends_at_the_time_box():
    llm, _ = make(FLASH, streamed({"reasoning": "a"}, {"content": "late"}, pause_after=0,
                                  pause_s=5))  # fmt: skip
    start = time.monotonic()
    out = list(llm.stream("s", "u", temperature=0.6, max_tokens=10, timeout_s=0.5))
    assert out == [("reasoning", "a")]
    assert time.monotonic() - start < 2


def test_pass2_is_a_named_strict_schema_with_thinking_off():
    schema = {"type": "object", "properties": {"questions": {"type": "array", "items":
              {"type": "string", "maxLength": 5}}}, "required": ["questions"],
              "additionalProperties": False}  # fmt: skip
    message = {"role": "assistant", "content": json.dumps({"questions": ["Q?"]})}
    reply = {"id": "c", "object": "chat.completion", "created": 0, "model": FLASH,
             "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]}  # fmt: skip
    llm, seen = make(FLASH, lambda _: httpx.Response(200, json=reply))
    out = llm.complete_json("sys", "user", schema, name="mona_interview", temperature=0,
                            max_tokens=6000, timeout_s=60)  # fmt: skip
    assert out == {"questions": ["Q?"]}
    body = seen[0]
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["name"] == "mona_interview"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["properties"]["questions"]["items"]["maxLength"] == 5
    assert (body["temperature"], body["max_tokens"]) == (0, 6000)
    assert body["reasoning"] == {"enabled": False}


def test_transport_failures_are_model_errors():
    llm, _ = make(FLASH, lambda _: httpx.Response(503, json={"error": {"message": "down"}}))
    with pytest.raises(ModelError):
        list(llm.stream("s", "u", temperature=0.6, max_tokens=10, timeout_s=5))
    with pytest.raises(ModelError):
        llm.complete_json("s", "u", {"type": "object"}, name="x", temperature=0, max_tokens=10,
                          timeout_s=5)  # fmt: skip
