"""R11 (D15): the stage seed's disabled AGIPI and Hello bank copies are the Apply-failure
fallback; Rules › enable → preview lists the moves the debrief would have made."""

import pytest

from mona.app import create_app
from mona.db import get_engine, get_sync_engine
from mona.settings import get_settings
from tests.api_client import api_client
from tests.conftest import SERVICE_KEY, _clear_caches
from tests.pg import scratch_db, sqlalchemy_url_for
from tests.pipeline_world import Pipeline

AGIPI_PER = "AGIPI PER, filed under the insured person"
HELLO = "Hello bank statements of the LMNP accounts"


@pytest.fixture
async def fix3_stage(l1m2_demo_template, tmp_path):
    """The demo seed (pre-seeded tier) behind the app, with its own data dir."""
    with scratch_db(template=l1m2_demo_template) as db, pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", sqlalchemy_url_for(db))
        mp.setenv("MONA_SERVICE_KEY", SERVICE_KEY)
        mp.setenv("MONA_DATA_DIR", str(tmp_path / "data"))
        _clear_caches()
        try:
            p = Pipeline(get_sync_engine(), get_settings().mona_data_dir)
            p.set_thresholds(85, 60)
            yield p
        finally:
            await get_engine().dispose()
            get_sync_engine().dispose()
            _clear_caches()


async def test_enabling_a_fallback_copy_previews_and_applies_the_expected_moves(fix3_stage):
    p = fix3_stage
    out = p.drop_synthetic(["syn-agipi-per", "syn-hello-fy-crossing"])
    p.drain()
    agipi, hello = (i.document_id for i in out.items)
    assert [p.row(d)["status"] for d in (agipi, hello)] == ["review", "review"]
    async with api_client(create_app()) as cl:
        listed = (await cl.get("/api/rules", params={"state": "disabled"})).json()["items"]
        by_name = {i["rule"]["name"]: i["rule"] for i in listed}
        assert {by_name[n]["source"] for n in (AGIPI_PER, HELLO)} == {"seed"}
        moves = {}
        for name in (AGIPI_PER, HELLO):
            rule_id = by_name[name]["id"]
            enabled = await cl.patch(f"/api/rules/{rule_id}", json={"enabled": True})
            assert enabled.json()["rule"]["state"] == "active"
            preview = (await cl.get(f"/api/rules/{rule_id}/preview")).json()
            assert preview["movesTotal"] == 1, name
            moves |= {m["documentId"]: "/".join(m["to"]) for m in preview["moves"]}
            applied = (await cl.post(f"/api/rules/{rule_id}/apply", json={})).json()
            assert (applied["moved"], applied["failed"]) == (1, [])
    assert moves == {
        agipi: "Personnel/Christine/Assurances/AGIPI/PER/2026",
        hello: "LMNP/Angers-Strasbourg/Banque/2026",
    }
    for d in (agipi, hello):
        r = p.row(d)
        assert (r["status"], r["location"]) == ("filed", "archive")
        assert r["current_path"].startswith(moves[d] + "/")
