"""`mona stage-build` steps (C9 §6.3 build order): a clean slate, demo/expectations.yaml's
documents through `POST /api/intake`, the §6.7 settings, and the cached-debrief check.

Practice documents are named in output by `sha256[:12]` only."""

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg
import yaml

from mona.demo.tools import OpsEnv, OpsError, chown_tree, empty_dir
from mona.migrate import migrate

DATA_TREES = ("inbox", "archive", "trash", "config", "exports")
HERMES_CONVERSATIONS = ("sessions", "messages", "system_prompts")
STATE = "stage-build"
STAGE_SETTINGS = {"debriefQueueThreshold": 5, "autoLockMinutes": 120}
THRESHOLDS = {"confidenceHigh": 90, "confidenceLow": 75}


def clean(env: OpsEnv) -> list[str]:
    """An empty schema at head, empty data trees and no debrief cache; text and model-output
    caches are content-addressed and kept. Hermes keeps its profile but no conversation."""
    with psycopg.connect(env.conninfo, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    migrate(env.url)
    for tree in DATA_TREES:
        empty_dir(env.data / tree)
    debrief = env.data / "textcache" / "debrief"
    if debrief.exists():
        empty_dir(debrief)
    empty_dir(env.data / STATE)
    out = ["database at head, data trees emptied, debrief cache emptied"]
    if env.hermes is not None:
        out.append(clean_hermes(env.hermes))
    return out


def clean_hermes(home: Path) -> str:
    """C9 §6.2 item 6 on a profile that has been used: no conversation rows or files."""
    db = home / "state.db"
    if db.is_file():
        con = sqlite3.connect(db)
        try:
            with con:
                tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
                for t in HERMES_CONVERSATIONS:
                    if t in tables:
                        con.execute(f"DELETE FROM {t}")
        finally:
            con.close()
    for sub in ("sessions", "cron/output", "cache/documents", "cache/images"):
        if (home / sub).is_dir():
            empty_dir(home / sub)
    return "Hermes conversations removed"


@dataclass(frozen=True)
class Source:
    """Where `demo/expectations.yaml`'s documents live on this host."""

    expectations: Path
    manifest: Path
    corpus: Path
    synthetic: Path


def documents(src: Source, group: str) -> list[tuple[str, Path]]:
    """(id, path) of an expectations group, in drop order; corpus files are sha256-checked."""
    docs = yaml.safe_load(src.expectations.read_text(encoding="utf-8"))["docs"]
    chosen = [d for d in docs if d["group"] == group]
    if group == "live":
        chosen.sort(key=lambda d: d["position"])
    corpus = {}
    for line in src.manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            corpus[entry["id"]] = entry
    synthetic = json.loads((src.synthetic / "manifest.json").read_text(encoding="utf-8"))["docs"]
    out = []
    for d in chosen:
        if d["source"] == "synthetic":
            path = src.synthetic / synthetic[d["id"]]["file"]
        else:
            entry = corpus.get(d["id"])
            if entry is None:
                raise OpsError(f"{d['id']}: not in the corpus manifest")
            path = src.corpus / entry["filename"]
            if not path.is_file() or _sha256(path) != entry["sha256"]:
                raise OpsError(f"{d['id']}: the corpus file is missing or differs")
        out.append((d["id"], path))
    if not out:
        raise OpsError(f"no documents in group {group!r}")
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Api:
    """The stack's REST API with an unlocked owner session (C2 §2)."""

    def __init__(self, base: str, password: str, timeout: float = 120.0):
        self.http = httpx.Client(base_url=base, timeout=timeout)
        res = self.http.post("/api/auth/unlock", json={"password": password})
        if res.status_code != 200:
            raise OpsError(f"unlock failed: HTTP {res.status_code}")
        self.http.headers["x-csrf-token"] = res.json()["csrfToken"]
        self.http.cookies.set("mona_session", res.cookies["mona_session"])

    def call(self, method: str, path: str, **kw: Any) -> Any:
        res = self.http.request(method, path, **kw)
        if res.status_code >= 400:
            code = (res.json().get("error") or {}).get("code") if res.content else None
            raise OpsError(f"{method} {path}: HTTP {res.status_code} {code or ''}".strip())
        return res.json() if res.content else None


def drop(api: Api, files: list[tuple[str, Path]]) -> str:
    upload = [("file", (p.name, p.read_bytes(), "application/octet-stream")) for _, p in files]
    return api.call("POST", "/api/intake", files=upload, data={"visitor": "false"})["batch"]["id"]


def wait(
    api: Api, batch_id: str, done: Callable[[dict[str, Any]], bool], timeout: float, step=2.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        detail = api.call("GET", f"/api/batches/{batch_id}")
        if done(detail):
            return detail
        if time.monotonic() > deadline:
            raise OpsError(f"batch {batch_id}: not settled after {timeout:.0f} s")
        time.sleep(step)


def batch_done(detail: dict[str, Any]) -> bool:
    return detail["batch"]["status"] == "done"


def debrief_settled(detail: dict[str, Any]) -> bool:
    d = detail["batch"]["debrief"]
    return batch_done(detail) and d is not None and d["status"] not in ("generating",)


def rows(files: list[tuple[str, Path]], detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Per document: the expectations id, sha12, intake outcome and the pipeline's decision."""
    by_sha = {i["sha256"]: i for i in detail["items"]}
    out = []
    for doc_id, path in files:
        item = by_sha[_sha256(path)]
        d = item.get("document") or {}
        out.append({
            "id": doc_id, "sha12": item["sha256"][:12], "outcome": item["outcome"],
            "document_id": item["documentId"], "status": d.get("status"),
            "reasons": d.get("reasons"), "band": d.get("band"),
            "confidence": d.get("confidence"), "entity_id": d.get("entityId"),
        })  # fmt: skip
    return out


def settle_history(api: Api, src: Source, report: list[dict[str, Any]]) -> list[str]:
    """Pre-filed documents left in review are filed as the person would: confirmed when the
    suggestion is the expected destination, corrected to it otherwise (no rule is drafted)."""
    expected = {
        d["id"]: d["before"]
        for d in yaml.safe_load(src.expectations.read_text(encoding="utf-8"))["docs"]
    }
    entities = {e["key"]: e["id"] for e in api.call("GET", "/api/entities")["items"]}
    units = {
        (e["key"], u["key"]): u["id"]
        for e in api.call("GET", "/api/entities")["items"]
        for u in e.get("subUnits", [])
    }
    lines = []
    for r in report:
        if r["status"] not in ("review",):
            continue
        want = expected[r["id"]]
        doc = api.call("GET", f"/api/documents/{r['document_id']}")
        s = doc.get("suggestion") or {}
        same = (
            s.get("entityId") == entities[want["entity"]]
            and s.get("categoryId") == want["category"]
            and s.get("fileName")
        )
        if same and not want.get("unit"):
            api.call("POST", f"/api/documents/{r['document_id']}/confirm")
            how = "confirmed"
        else:
            body = {"entityId": entities[want["entity"]], "categoryId": want["category"]}
            if want.get("subcategory"):
                body["subcategoryKey"] = want["subcategory"]
            if want.get("unit"):
                body["subUnitId"] = units[(want["entity"], want["unit"])]
            api.call("POST", f"/api/documents/{r['document_id']}/correct", json=body)
            how = "corrected"
        r["settled"] = how
        lines.append(f"{r['sha12'] if r['id'][:4] != 'syn-' else r['id']}: {how}")
    return lines


def cancel_debrief(api: Api, batch_id: str, wait_s: float = 60.0) -> str | None:
    """The history batch's own debrief would show on stage as pending questions; cancel it."""
    deadline = time.monotonic() + wait_s
    while (d := api.call("GET", f"/api/batches/{batch_id}")["batch"]["debrief"]) is None:
        if time.monotonic() > deadline:
            return None
        time.sleep(2)
    if d["status"] in ("generating", "ready"):
        api.call("POST", f"/api/interviews/{d['interviewId']}/cancel")
    return d["interviewId"]


def apply_settings(api: Api, early: int) -> dict[str, Any]:
    """C9 §6.7 with A18's thresholds; the owner's form of address comes from the seed."""
    return api.call(
        "PATCH", "/api/settings", json={**STAGE_SETTINGS, **THRESHOLDS, "debriefEarlyMin": early}
    )


def candidates(env: OpsEnv, interview_id: str) -> dict[str, str]:
    """Document id → sha256 of the debrief's candidates (C6 §4.7 binds the cache to them)."""
    with psycopg.connect(env.conninfo) as conn:
        rows_ = conn.execute(
            "SELECT d.id, d.sha256 FROM interviews i"
            " JOIN documents d ON d.id = ANY(ARRAY(SELECT jsonb_array_elements_text("
            "   i.scope->'candidate_document_ids')))"
            " WHERE i.id = %s",
            (interview_id,),
        ).fetchall()
    return dict(rows_)


def uncovered(cands: dict[str, str], questions: list[dict[str, Any]]) -> list[str]:
    """Candidates no surviving question asks about (D15: check every model output)."""
    asked = {d for q in questions for d in q["affects"]}
    return sorted(sha[:12] for doc, sha in cands.items() if doc not in asked)


def write_state(env: OpsEnv, name: str, body: Any) -> Path:
    d = env.data / STATE
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.json"
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
    chown_tree(d, env.data_owner)
    return path


def read_state(env: OpsEnv, name: str) -> Any:
    path = env.data / STATE / f"{name}.json"
    if not path.is_file():
        raise OpsError(f"{path.name} is missing: run the live step first")
    return json.loads(path.read_text(encoding="utf-8"))


def cache_check(env: OpsEnv, shas: list[str], prompt_version: str) -> tuple[str, int]:
    """§8 test 8's stage half: a debrief cache file for exactly these candidates survives the
    reset, and each of its questions affects at least one of them."""
    from mona.interviews.cache import cache_dir, fingerprint

    fp = fingerprint(shas)
    found = sorted(cache_dir(env.data / "textcache").glob(f"{fp}.{prompt_version}.*.json"))
    if not found:
        raise OpsError(f"no debrief cache file {fp}.{prompt_version}.* after the reset")
    body = json.loads(found[-1].read_text(encoding="utf-8"))
    if sorted(body["candidate_sha256s"]) != sorted(shas):
        raise OpsError("the debrief cache file's candidates differ from the live batch's")
    live = set(shas)
    if not body["questions"] or any(
        not live & set(q["affected_sha256s"]) for q in body["questions"]
    ):
        raise OpsError("a cached question affects no live-batch document")
    return found[-1].name, len(body["questions"])
