#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Inventory the practice corpus into the private demo-data directory (manifest.jsonl + manifest-summary.md)."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HOME = Path.home()
ROOT = HOME / "DevFiles" / "mona-hq"
DEMO_DATA = ROOT / "demo-data"
DEFAULT_SRC = ROOT / "100 PDF neclasificate"
DEFAULT_CACHE = ROOT / "bench" / "corpus" / "textcache"

STOPWORDS = {
    "fr": {
        "le",
        "la",
        "les",
        "des",
        "du",
        "de",
        "et",
        "un",
        "une",
        "pour",
        "vous",
        "votre",
        "nous",
        "est",
        "sur",
        "au",
        "par",
        "dans",
        "avec",
    },
    "en": {"the", "and", "of", "to", "for", "you", "your", "is", "with", "this", "that", "are", "from", "by", "on"},
    "ro": {
        "si",
        "sau",
        "pentru",
        "este",
        "care",
        "din",
        "cu",
        "nu",
        "sunt",
        "la",
        "un",
        "o",
        "prin",
        "dumneavoastra",
        "conform",
    },
    "es": {"el", "los", "las", "del", "y", "para", "con", "por", "una", "que", "es", "en", "su", "usted", "gracias"},
}


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120, errors="replace", check=False).stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def guess_lang(text: str) -> str:
    words = re.findall(r"[a-z]+", strip_accents(text.lower()))
    if len(words) < 20:
        return "other"
    counts = {lang: sum(1 for w in words if w in sw) for lang, sw in STOPWORDS.items()}
    lang, hits = max(counts.items(), key=lambda kv: kv[1])
    return lang if hits / len(words) >= 0.05 else "other"


def page_info(path: Path) -> tuple[int | None, list[int], list[int]]:
    out = run(["pdfinfo", "-f", "1", "-l", "10000", str(path)])
    m = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
    if not m:
        return None, [], []
    rotated = [int(p) for p, r in re.findall(r"^Page\s+(\d+)\s+rot:\s+(-?\d+)", out, re.MULTILINE) if int(r) % 360]
    sizes = [
        (int(p), float(w), float(h))
        for p, w, h in re.findall(r"^Page\s+(\d+)\s+size:\s+([\d.]+) x ([\d.]+)", out, re.MULTILINE)
    ]
    portrait = sum(1 for _, w, h in sizes if h >= w)
    majority_portrait = portrait * 2 >= len(sizes)
    odd = [p for p, w, h in sizes if (h < w) == majority_portrait]
    return int(m.group(1)), rotated, odd


def pdftotext(path: Path, first: int | None = None, last: int | None = None) -> str:
    cmd = ["pdftotext", "-layout"]
    if first:
        cmd += ["-f", str(first), "-l", str(last or first)]
    return run(cmd + [str(path), "-"]).replace("\x00", "")


def norm_text_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\W+", "", strip_accents(text.lower())).encode()).hexdigest()[:12]


def inventory(src: Path, cache: Path) -> list[dict]:
    rows = []
    for path in sorted(p for p in src.iterdir() if p.is_file()):
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        cache_file = cache / f"{path.name}.txt"
        has_cache = cache_file.exists()
        cached = cache_file.read_text(encoding="utf-8", errors="replace") if has_cache else ""
        valid = data[:5] == b"%PDF-"
        if valid:
            pages, rotated, odd = page_info(path)
            all_text = pdftotext(path)
            head_text = pdftotext(path, 1, 2)
        else:
            pages, rotated, odd, all_text, head_text = None, [], [], "", ""
        body = all_text if len(all_text.strip()) >= 50 else cached
        rows.append(
            {
                "id": sha[:12],
                "sha256": sha,
                "filename": path.name,
                "pages": pages,
                "text_chars": len(all_text.strip()),
                "needs_ocr": valid and len(head_text.strip()) < 50,
                "rotated_pages": rotated,
                "orientation_mismatch_pages": odd,
                "lang_guess": guess_lang(body),
                "has_textcache": has_cache,
                "textcache_chars": len(cached.strip()),
                "valid_pdf": valid,
                "text_hash": norm_text_hash(body) if len(body.strip()) >= 50 else None,
                "size": len(data),
            }
        )
    return rows


def summarize(rows: list[dict]) -> str:
    n = len(rows)
    shas = Counter(r["sha256"] for r in rows)
    texts = Counter(r["text_hash"] for r in rows if r["text_hash"])
    langs = Counter(r["lang_guess"] for r in rows)
    pages = [r["pages"] for r in rows if r["pages"]]
    lines = [
        "# Corpus manifest summary (counts only)",
        "",
        f"- files: {n}",
        f"- valid PDFs: {sum(r['valid_pdf'] for r in rows)}",
        f"- not valid PDFs (placeholder stubs, text in cache only): {sum(not r['valid_pdf'] for r in rows)}",
        f"- has textcache: {sum(r['has_textcache'] for r in rows)}",
        f"- needs_ocr (valid PDFs, <50 chars on pages 1-2): {sum(r['needs_ocr'] for r in rows)}",
        f"- no usable text anywhere (pdftotext and cache <50 chars): {sum(1 for r in rows if max(r['text_chars'], r['textcache_chars']) < 50)}",
        f"- files with rotated pages (/Rotate != 0): {sum(bool(r['rotated_pages']) for r in rows)}",
        f"- files with orientation-mismatch pages: {sum(bool(r['orientation_mismatch_pages']) for r in rows)}",
        f"- multi-page files (>1): {sum(1 for p in pages if p > 1)}; max pages: {max(pages, default=0)}; total pages: {sum(pages)}",
        f"- identical-sha256 groups: {sum(1 for c in shas.values() if c > 1)}",
        f"- identical-normalised-text groups: {sum(1 for c in texts.values() if c > 1)}",
        "- lang_guess: " + ", ".join(f"{k}={v}" for k, v in sorted(langs.items())),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--out", type=Path, default=DEMO_DATA / "corpus")
    args = ap.parse_args()
    out = args.out.expanduser().resolve()
    if DEMO_DATA.resolve() not in (out, *out.parents):
        print(f"refusing to write outside {DEMO_DATA}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    rows = inventory(args.src.expanduser(), args.cache.expanduser())
    (out / "manifest.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    summary = summarize(rows)
    (out / "manifest-summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
