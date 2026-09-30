"""C5 §1.3 caches under `/data/textcache/<sha[0:2]>/`, keyed by the document's sha256."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION = 1


def directory(textcache: Path, sha256: str) -> Path:
    return textcache / sha256[:2]


def pages_path(textcache: Path, sha256: str) -> Path:
    return directory(textcache, sha256) / f"{sha256}.pages.json"


def ocr_path(textcache: Path, sha256: str) -> Path:
    return directory(textcache, sha256) / f"{sha256}.ocr.pdf"


def thumbnail_path(textcache: Path, sha256: str) -> Path:
    return directory(textcache, sha256) / f"{sha256}.p1.png"


def model_path(textcache: Path, sha256: str, prompt_version: str) -> Path:
    return directory(textcache, sha256) / f"{sha256}.model.{prompt_version}.json"


def tmp_of(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def write_atomic(path: Path, data: bytes) -> None:
    """Write `<name>.tmp`, then rename it into place: a reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_of(path)
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("v") == VERSION else None


@dataclass(frozen=True)
class Pages:
    sha256: str
    method: str
    pages: tuple[str, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return sum(len(p) for p in self.pages)


def read_pages(textcache: Path, sha256: str) -> Pages | None:
    data = _read_json(pages_path(textcache, sha256))
    if data is None or data.get("sha256") != sha256 or not isinstance(data.get("pages"), list):
        return None
    return Pages(sha256, data["method"], tuple(data["pages"]))


def write_pages(textcache: Path, p: Pages) -> None:
    body = {"v": VERSION, "sha256": p.sha256, "method": p.method, "page_count": p.page_count,
            "pages": list(p.pages)}  # fmt: skip
    write_atomic(pages_path(textcache, p.sha256), json.dumps(body, ensure_ascii=False).encode())


def read_model(textcache: Path, sha256: str, prompt_version: str, model: str) -> dict | None:
    """The cached raw output when `v`, `prompt_version` and `model` match; the caller validates."""
    data = _read_json(model_path(textcache, sha256, prompt_version))
    if data is None or data.get("sha256") != sha256:
        return None
    if data.get("prompt_version") != prompt_version or data.get("model") != model:
        return None
    raw = data.get("raw_output")
    return raw if isinstance(raw, dict) else None


def write_model(textcache: Path, sha256: str, prompt_version: str, model: str, raw: dict) -> None:
    body = {"v": VERSION, "sha256": sha256, "prompt_version": prompt_version, "model": model,
            "raw_output": raw}  # fmt: skip
    path = model_path(textcache, sha256, prompt_version)
    write_atomic(path, json.dumps(body, ensure_ascii=False, indent=1).encode())
