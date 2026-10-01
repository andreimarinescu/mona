"""The synthetic set through `POST /api/intake` on a dev stack, checked against
`demo/expectations.yaml` (`before`). Run on the host:

MONA_OWNER_PASSWORD=… uv run python -m tests.live_intake --base http://localhost:<API_PORT> \
    --synthetic ~/DevFiles/mona-hq/demo-data/synthetic

Exits 1 when an intake check fails (a batch not done in time, a wrong intake outcome, the
duplicate missed); pipeline outcomes against the expectations are reported, not enforced.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[3]
STATUS = {"file": "filed", "filed": "filed", "queue": "review", "unreadable": "unreadable"}


def unlock(client: httpx.Client) -> None:
    res = client.post("/api/auth/unlock", json={"password": os.environ["MONA_OWNER_PASSWORD"]})
    res.raise_for_status()
    client.headers["x-csrf-token"] = res.json()["csrfToken"]
    client.headers["cookie"] = f"mona_session={res.cookies['mona_session']}"  # Secure on localhost


def upload(client: httpx.Client, paths: list[Path], visitor: bool) -> dict:
    files = [("file", (p.name, p.read_bytes(), "application/octet-stream")) for p in paths]
    res = client.post("/api/intake", files=files, data={"visitor": str(visitor).lower()})
    res.raise_for_status()
    return res.json()


def wait_done(client: httpx.Client, batch_id: str, timeout: float) -> tuple[dict, float]:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        detail = client.get(f"/api/batches/{batch_id}").json()
        if detail["batch"]["status"] == "done":
            return detail, time.monotonic() - t0
        time.sleep(2)
    raise SystemExit(f"batch {batch_id} not done after {timeout}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--synthetic", type=Path, required=True)
    ap.add_argument("--timeout", type=float, default=300)
    args = ap.parse_args()
    manifest = json.loads((args.synthetic / "manifest.json").read_text())["docs"]
    expected = {
        d["id"]: d for d in yaml.safe_load((ROOT / "demo/expectations.yaml").read_text())["docs"]
    }
    order = sorted((k for k in expected if k in manifest),
                   key=lambda k: expected[k]["group"] != "prefiled")  # fmt: skip
    drop = [k for k in order if expected[k]["before"].get("basis") != "visitor"]
    visitors = [k for k in order if k not in drop]
    problems: list[str] = []
    report: list[dict] = []
    with httpx.Client(base_url=args.base, timeout=60) as client:
        unlock(client)
        entities = {e["id"]: e["key"] for e in client.get("/api/entities").json()["items"]}
        for keys, visitor in ((drop, False), (visitors, True)):
            result = upload(client, [args.synthetic / manifest[k]["file"] for k in keys], visitor)
            detail, waited = wait_done(client, result["batch"]["id"], args.timeout)
            batch = detail["batch"]
            print(f"batch {batch['id']} visitor={visitor} done in {waited:.1f}s "
                  f"counts={json.dumps(batch['counts'])}")  # fmt: skip
            if batch["visitor"] != visitor:
                problems.append(f"{batch['id']}: visitor flag {batch['visitor']}")
            by_doc = {
                i["documentId"]: k
                for k, i in zip(keys, detail["items"], strict=True)
                if i["outcome"] == "accepted"
            }
            for key, item in zip(keys, detail["items"], strict=True):
                if item["sha256"] != manifest[key]["sha256"]:
                    problems.append(f"{key}: sha256 differs from the manifest")
                want = expected[key]["before"]
                doc = item["document"] or {}
                if want["outcome"] == "duplicate":
                    got = item["outcome"]
                    twin = by_doc.get(item["documentId"])
                    if got != "duplicate" or twin != expected[key]["duplicate_of"]:
                        problems.append(f"{key}: {got}, duplicate of {twin}")
                else:
                    got = doc.get("status") if item["outcome"] == "accepted" else item["outcome"]
                    if item["outcome"] != "accepted":
                        problems.append(f"{key}: intake outcome {item['outcome']}")
                row = {
                    "id": key,
                    "expected": STATUS.get(want["outcome"], want["outcome"]),
                    "got": got,
                    "entity": entities.get(doc.get("entityId")),
                    "expected_entity": want.get("entity"),
                    "category": doc.get("categoryId"),
                    "expected_category": want.get("category"),
                    "path": "/".join(doc.get("path") or []) or None,
                    "expected_path": want.get("path"),
                    "band": doc.get("band"),
                    "confidence": doc.get("confidence"),
                }
                row["match"] = row["expected"] == row["got"]
                report.append(row)
    for row in report:
        print(json.dumps(row, ensure_ascii=False))
    matched = sum(r["match"] for r in report)
    print(f"outcomes matching expectations.yaml (before): {matched}/{len(report)}")
    for p in problems:
        print(f"INTAKE PROBLEM: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
