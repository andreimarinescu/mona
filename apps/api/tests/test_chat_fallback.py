"""A28's fallback text and A29's reply-language check, on the chat adapter."""

import json
import logging
from pathlib import Path

import pytest

from mona.chat.stream import run_turn
from mona.chat.turns import open_turn
from mona.db import get_engine
from mona.i18n import t
from tests import rows
from tests.hermes_fake import FakeHermes, chunk, meta, post_chat, sse_body, types

pytestmark = pytest.mark.usefixtures("clean")

TOOL_STORM = (Path(__file__).parent / "fixtures" / "hermes" / "tool-storm-no-text.sse").read_bytes()
EMPTY = sse_body([chunk({"role": "assistant"}), chunk({}, "stop"), "data: [DONE]"])
FR_REPLY = (
    "Voici les documents à payer de ce mois : la facture du fournisseur est due le 14 octobre, "
    "et nous avons aussi un appel de cotisations pour le cabinet. Souhaitez-vous un rappel ?"
)
EN_REPLY = (
    "Here are the documents to pay this month: the supplier invoice is due on 14 October, "
    "and there is also a payment demand for the practice. Would you like a reminder for it?"
)


def text_of(chunks: list) -> str:
    return "".join(c["delta"] for c in chunks if c != "[DONE]" and c["type"] == "text-delta")


def reply(text: str) -> bytes:
    return sse_body([chunk({"content": text}), chunk({}, "stop"), "data: [DONE]"])


# A28: the fallback text


async def test_a_tool_storm_with_no_text_ends_with_the_fallback_text():
    _, chunks = await post_chat(FakeHermes(TOOL_STORM))
    t_ = types(chunks)
    assert t_.count("tool-output-available") == 12
    assert t_[-6:] == ["text-start", "text-delta", "text-end", "finish-step", "finish", "[DONE]"]
    assert text_of(chunks) == t("chat.fallback.too_complex", "en")
    assert chunks[-2]["finishReason"] == "stop"
    turn = rows.turn_row(meta(chunks)["turnId"])
    assert turn.status == "closed"
    assert turn.parts[-1] == {"type": "text", "text": t("chat.fallback.too_complex", "en")}


@pytest.mark.parametrize(
    ("body", "lang", "start"),
    [
        ({"message": "Pouvez-vous extraire les IBAN et créer un fichier ?"}, "fr", "Cette demande"),
        ({"replyLanguage": "ro"}, "ro", "Această cerere"),
        ({}, "en", "That needs more steps"),
    ],
)
async def test_an_empty_reply_gets_the_fallback_in_the_reply_language(body, lang, start):
    _, chunks = await post_chat(FakeHermes(EMPTY), **body)
    assert meta(chunks)["replyLanguage"] == lang
    assert text_of(chunks) == t("chat.fallback.too_complex", lang)
    assert text_of(chunks).startswith(start)


async def test_a_whitespace_reply_gets_the_fallback_and_a_real_reply_does_not():
    _, chunks = await post_chat(FakeHermes(reply("\n\n")))
    assert text_of(chunks) == "\n\n" + t("chat.fallback.too_complex", "en")
    _, chunks = await post_chat(FakeHermes(reply(EN_REPLY)))
    assert text_of(chunks) == EN_REPLY


async def _abort_after(frame_type: str) -> str:
    engine = get_engine()
    turn = await open_turn(engine, None, "Make a spreadsheet of every IBAN", "en", None)
    frames = run_turn(engine, FakeHermes(TOOL_STORM).client(), turn, "/", "Home")
    async for frame in frames:
        if f'"type": "{frame_type}"' in frame:
            break
    await frames.aclose()
    return turn.id


async def test_an_abort_after_tool_calls_stores_the_fallback_text():
    turn = rows.turn_row(await _abort_after("tool-output-available"))
    assert turn.status == "aborted"
    assert [p["type"] for p in turn.parts][-2:] == ["tool", "text"]
    assert turn.parts[-1]["text"] == t("chat.fallback.too_complex", "en")


async def test_an_abort_before_any_tool_call_stores_no_text():
    turn = rows.turn_row(await _abort_after("reasoning-delta"))
    assert turn.status == "aborted"
    assert [p["type"] for p in turn.parts] == ["reasoning"]


# A29: the reply language is checked


async def test_a_reply_in_another_language_is_logged_without_its_text(caplog):
    caplog.set_level(logging.WARNING)
    _, chunks = await post_chat(FakeHermes(reply(FR_REPLY)))
    turn_id = meta(chunks)["turnId"]
    assert f"turn {turn_id}: replied in fr, not en" in caplog.text
    assert "fournisseur" not in caplog.text


async def test_a_reply_in_the_right_language_is_not_logged(caplog):
    caplog.set_level(logging.WARNING)
    await post_chat(FakeHermes(reply(EN_REPLY)))
    assert "replied in" not in caplog.text


def overlay_of(fake: FakeHermes) -> str:
    req = next(r for r in fake.requests if r.url.path == "/v1/chat/completions")
    return json.loads(req.content)["messages"][0]["content"]


async def test_the_next_turn_is_told_its_previous_reply_was_in_another_language():
    cid, _ = rows.turn(status="closed", parts=[{"type": "text", "text": FR_REPLY}])
    fake = FakeHermes(reply(EN_REPLY))
    await post_chat(fake, conversationId=cid, message="And what is due next week?")
    assert overlay_of(fake).endswith(
        "- The person wrote in English. Reply in English.\n"
        "- Your previous reply was in French; reply in English."
    )
    fake = FakeHermes(EMPTY)
    await post_chat(fake, conversationId=cid, message="And what about the week after?")
    assert "previous reply" not in overlay_of(fake)


@pytest.mark.parametrize(
    "parts",
    [
        [{"type": "text", "text": "Voici la facture du fournisseur, due le 14 octobre."}],
        [{"type": "text", "text": EN_REPLY}],
        [{"type": "reasoning", "text": FR_REPLY}],
    ],
)
async def test_a_short_or_matching_previous_reply_adds_no_line(parts):
    cid, _ = rows.turn(status="closed", parts=parts)
    fake = FakeHermes(EMPTY)
    await post_chat(fake, conversationId=cid, message="And what is due next week?")
    assert "previous reply" not in overlay_of(fake)


async def test_no_line_when_the_person_now_writes_in_the_language_of_the_slip():
    cid, _ = rows.turn(status="closed", parts=[{"type": "text", "text": FR_REPLY}])
    fake = FakeHermes(EMPTY)
    await post_chat(
        fake, conversationId=cid, message="Et qu'avons-nous à payer la semaine prochaine ?"
    )
    assert "previous reply" not in overlay_of(fake)
