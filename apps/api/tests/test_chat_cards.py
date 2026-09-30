import json

import pytest

from tests import rows
from tests.fixtures import S1_OVERLAY_STREAM, S5_SESSION_MESSAGES
from tests.hermes_fake import FakeHermes, chunk, meta, post_chat, sse_body, tool_event, types
from tests.mcp_http import call

pytestmark = pytest.mark.usefixtures("clean")

S1 = S1_OVERLAY_STREAM.read_bytes()
FIXTURE = json.loads(S5_SESSION_MESSAGES.read_text())["data"]
FIXTURE_REFS = ["crd_01m3sg44rengv1yevkp7ca1xg5", "crd_01m3sg4601h7fp4ffxx3enfd3d"]
QUESTION = "Find the URSSAF letter"


def history(*refs: str, earlier: list | None = None) -> list[dict]:
    """The S5 session fixture with its two card refs replaced by `refs`."""
    out = []
    for m in FIXTURE:
        content = m.get("content") or ""
        for old, new in zip(FIXTURE_REFS, refs, strict=False):
            content = content.replace(old, new)
        out.append({**m, "content": content})
    return (earlier or []) + out


def cards_in(chunks) -> list[tuple[str, str]]:
    return [(c["type"], c["id"]) for c in chunks if c != "[DONE]" and c["type"].startswith("data-")]


async def test_a_card_is_emitted_after_its_completion_once_despite_a_second_completion():
    doc = rows.document("URSSAF appel", counterparty="opco")
    refs: list[str] = []

    async def tools():
        refs.extend((await call("get_document", {"document_id": doc})).data["card_refs"])

    body = sse_body(
        [
            *tool_event("get_document", "c1", "running"),
            chunk({"content": "Opening it."}),
            *tool_event("get_document", "c1", "completed"),
            *tool_event("get_document", "c1", "completed"),
            chunk({}, "stop"),
            "data: [DONE]",
        ]
    )
    fake = FakeHermes(
        body,
        during_stream=tools,
        messages=lambda: [{"role": "user", "content": QUESTION}, *history(*refs)[1:]],
    )
    _, chunks = await post_chat(fake, message=QUESTION)
    t = types(chunks)
    assert t.count("data-doc") == 1
    first_done = t.index("tool-output-available")
    assert t.index("data-doc") == first_done + 1
    assert t.index("tool-input-available") < t.index("text-start") < first_done
    assert t.count("tool-input-available") == 1 and t.count("tool-output-available") == 2


async def test_a_card_waits_for_its_own_tool_to_complete():
    doc = rows.document("URSSAF appel", counterparty="opco")
    body = sse_body(
        [
            *tool_event("search_documents", "c1", "running"),
            *tool_event("search_documents", "c1", "completed"),
            *tool_event("get_document", "c2", "running"),
            chunk({"content": "Found it."}),
            *tool_event("get_document", "c2", "completed"),
            chunk({}, "stop"),
            "data: [DONE]",
        ]
    )
    fake = FakeHermes(body, during_stream=lambda: call("get_document", {"document_id": doc}))
    _, chunks = await post_chat(fake)
    t = types(chunks)
    outputs = [i for i, x in enumerate(t) if x == "tool-output-available"]
    assert t.index("data-doc") == outputs[1] + 1


async def test_a_card_whose_document_was_deleted_is_skipped():
    doc = rows.document("URSSAF appel", counterparty="opco")

    async def tools():
        await call("get_document", {"document_id": doc})
        with rows.connect() as conn:
            conn.execute(
                "UPDATE documents SET deleted_at = now(), location = 'trash' WHERE id = %s", (doc,)
            )

    _, chunks = await post_chat(FakeHermes(S1, during_stream=tools))
    assert cards_in(chunks) == []
    assert rows.card_rows()[0].emitted_at is not None
    assert types(chunks)[-3:] == ["finish-step", "finish", "[DONE]"]


# Reconciliation (C3 §8.5)


async def test_finish_emits_unattributed_cards_of_this_turn_and_unattributes_strays():
    found, stray = rows.document("URSSAF appel", counterparty="opco"), rows.document("EDF")
    refs: dict[str, str] = {}

    async def tools():
        tg = await call("get_document", {"document_id": found}, channel="telegram")
        refs["found"] = tg.data["card_refs"][0]
        web = await call("search_documents", {"query": "EDF"})
        refs["stray"] = web.data["card_refs"][0]

    fake = FakeHermes(S1, during_stream=tools, messages=lambda: history(refs["found"]))
    _, chunks = await post_chat(fake, message=QUESTION)
    assert cards_in(chunks) == [("data-doc", found)]
    assert types(chunks)[-4:] == ["data-doc", "finish-step", "finish", "[DONE]"]
    by_id = {r.id: r for r in rows.card_rows()}
    turn_id = meta(chunks)["turnId"]
    assert (by_id[refs["found"]].turn_id, by_id[refs["found"]].emitted_at is not None) == (
        turn_id,
        True,
    )
    assert (by_id[refs["stray"]].turn_id, by_id[refs["stray"]].emitted_at) == (None, None)
    parts = rows.turn_row(turn_id).parts
    assert parts[-1] == {"type": "data", "kind": "doc", "id": found}
    assert stray not in json.dumps(parts)


async def test_after_a_mona_offline_turn_the_slice_is_still_this_turns():
    earlier_doc, doc = rows.document("Earlier"), rows.document("URSSAF appel", counterparty="opco")
    cid, earlier = rows.turn(status="closed", user_text="Show the earlier one")
    earlier_ref = (await call("get_document", {"document_id": earlier_doc})).data["card_refs"][0]
    with rows.connect() as conn:
        conn.execute(
            "UPDATE card_events SET turn_id = %s, emitted_at = now() WHERE id = %s",
            (earlier, earlier_ref),
        )
    _, offline = await post_chat(FakeHermes(S1, down={"/v1/chat"}), conversationId=cid)
    assert types(offline)[2] == "error"
    ref = (await call("get_document", {"document_id": doc}, channel="telegram")).data["card_refs"]
    earlier_msgs = [
        {"role": "user", "content": "Show the earlier one"},
        {"role": "assistant", "content": ""},
        {
            "role": "tool",
            "content": json.dumps({"result": json.dumps({"card_refs": [earlier_ref]})}),
        },
        {"role": "assistant", "content": "Here it is."},
    ]
    fake = FakeHermes(S1, messages=history(ref[0], earlier=earlier_msgs))
    _, chunks = await post_chat(fake, conversationId=cid, message=QUESTION)
    assert cards_in(chunks) == [("data-doc", doc)]
    by_id = {r.id: r for r in rows.card_rows()}
    assert by_id[earlier_ref].turn_id == earlier


async def test_nothing_is_reconciled_when_the_last_user_message_is_not_this_turns():
    found = rows.document("URSSAF appel", counterparty="opco")
    rows.document("EDF")
    refs: dict[str, str] = {}

    async def tools():
        tg = await call("get_document", {"document_id": found}, channel="telegram")
        refs["found"] = tg.data["card_refs"][0]
        refs["stray"] = (await call("search_documents", {"query": "EDF"})).data["card_refs"][0]

    def messages():
        return [*history(refs["found"]), {"role": "user", "content": "Something else"}]

    fake = FakeHermes(S1, during_stream=tools, messages=messages)
    _, chunks = await post_chat(fake, message=QUESTION)
    assert cards_in(chunks) == []
    by_id = {r.id: r for r in rows.card_rows()}
    assert by_id[refs["found"]].turn_id is None
    assert by_id[refs["stray"]].turn_id == meta(chunks)["turnId"]


async def test_a_failed_messages_fetch_skips_reconciliation_and_keeps_emitted_cards():
    doc = rows.document("URSSAF appel", counterparty="opco")
    fake = FakeHermes(
        S1,
        during_stream=lambda: call("get_document", {"document_id": doc}),
        down={"/api/sessions/"},
    )
    _, chunks = await post_chat(fake)
    assert cards_in(chunks) == [("data-doc", doc)]
    assert types(chunks)[-3:] == ["finish-step", "finish", "[DONE]"]


async def test_a_card_ref_of_another_turn_is_skipped():
    doc = rows.document("URSSAF appel", counterparty="opco")
    _, other = rows.turn(status="closed")
    ref = (await call("get_document", {"document_id": doc}, channel="telegram")).data["card_refs"][
        0
    ]
    with rows.connect() as conn:
        conn.execute("UPDATE card_events SET turn_id = %s WHERE id = %s", (other, ref))
    _, chunks = await post_chat(FakeHermes(S1, messages=history(ref)), message=QUESTION)
    assert cards_in(chunks) == []
    assert rows.card_rows()[0].turn_id == other
