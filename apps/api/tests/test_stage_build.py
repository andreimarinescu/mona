"""`mona stage-build` steps that run without a stack: sources, Hermes cleanup, the cache check."""

import hashlib
import json

import pytest
import yaml

from mona.demo import checks, stage
from mona.demo.tools import OpsEnv, OpsError
from mona.interviews.cache import fingerprint
from tests.demo_world import chat_in_hermes, make_hermes


def sources(tmp_path, corpus_bytes=b"%PDF corpus"):
    corpus, synthetic = tmp_path / "corpus", tmp_path / "synthetic"
    corpus.mkdir()
    synthetic.mkdir()
    (corpus / "scan one.pdf").write_bytes(corpus_bytes)
    (synthetic / "letter.pdf").write_bytes(b"%PDF syn")
    (synthetic / "manifest.json").write_text(
        json.dumps({"docs": {"syn-a": {"file": "letter.pdf"}}})
    )
    sha = hashlib.sha256(b"%PDF corpus").hexdigest()
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"id": sha[:12], "sha256": sha, "filename": "scan one.pdf"}))
    docs = [
        {"id": "syn-a", "group": "live", "position": 2, "source": "synthetic"},
        {"id": sha[:12], "group": "live", "position": 1, "source": "corpus"},
        {"id": "syn-b", "group": "extra", "source": "synthetic"},
    ]
    expectations = tmp_path / "expectations.yaml"
    expectations.write_text(yaml.safe_dump({"docs": docs}))
    return stage.Source(expectations, manifest, corpus, synthetic), sha


def test_a_group_resolves_to_files_in_drop_order(tmp_path):
    src, sha = sources(tmp_path)
    assert stage.documents(src, "live") == [
        (sha[:12], src.corpus / "scan one.pdf"),
        ("syn-a", src.synthetic / "letter.pdf"),
    ]
    with pytest.raises(OpsError, match="no documents"):
        stage.documents(src, "prefiled")


def test_a_corpus_file_that_differs_from_the_manifest_is_refused(tmp_path):
    src, sha = sources(tmp_path, corpus_bytes=b"%PDF changed")
    with pytest.raises(OpsError, match=f"{sha[:12]}: the corpus file is missing or differs"):
        stage.documents(src, "live")


def test_hermes_cleanup_passes_the_snapshot_check(tmp_path):
    home = make_hermes(tmp_path / "hermes")
    chat_in_hermes(home)
    assert checks.hermes_problems(home) != []
    stage.clean_hermes(home)
    assert checks.hermes_problems(home) == []
    assert (home / "SOUL.md").is_file() and (home / "cron" / "jobs.json").is_file()


def test_the_cache_check_needs_the_live_candidates_file(tmp_path):
    env = OpsEnv(url="postgresql+psycopg://x@localhost/x", data=tmp_path)
    shas = ["b" * 64, "a" * 64]
    with pytest.raises(OpsError, match="no debrief cache file"):
        stage.cache_check(env, shas, "c6-v1")
    d = tmp_path / "textcache" / "debrief"
    d.mkdir(parents=True)
    body = {"candidate_sha256s": sorted(shas), "questions": [{"affected_sha256s": ["a" * 64]}]}
    path = d / f"{fingerprint(shas)}.c6-v1.en.json"
    path.write_text(json.dumps(body))
    assert stage.cache_check(env, shas, "c6-v1") == (path.name, 1)
    body["questions"].append({"affected_sha256s": ["c" * 64]})
    path.write_text(json.dumps(body))
    with pytest.raises(OpsError, match="affects no live-batch document"):
        stage.cache_check(env, shas, "c6-v1")


def test_a_candidate_no_question_asks_about_is_uncovered():
    cands = {"doc_a": "a" * 64, "doc_b": "b" * 64}
    assert stage.uncovered(cands, [{"affects": ["doc_a", "doc_b"]}]) == []
    assert stage.uncovered(cands, [{"affects": ["doc_a"]}, {"affects": []}]) == ["b" * 12]


def test_build_reports_belong_to_the_data_owner(tmp_path, monkeypatch):
    owned = []
    monkeypatch.setattr("mona.demo.tools.os.geteuid", lambda: 0)
    monkeypatch.setattr("mona.demo.tools.os.lchown", lambda p, u, g: owned.append((p, u, g)))
    env = OpsEnv(url="postgresql+psycopg://x@localhost/x", data=tmp_path, data_owner=(1000, 1000))
    path = stage.write_state(env, "live", {"ok": True})
    assert {(str(p), u, g) for p, u, g in owned} == {
        (str(path.parent), 1000, 1000), (str(path), 1000, 1000),
    }  # fmt: skip
