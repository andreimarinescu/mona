"""C5 §1.4 text extraction: pdftotext per page, OCR when a page is empty, images via img2pdf."""

import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from mona.pipeline import cache
from mona.pipeline.cache import Pages

OCR_PAGE_MIN = 20
UNREADABLE_MIN = 50
PDFTOTEXT_TIMEOUT = 60
OCR_TIMEOUT = 300
OCR_ARGS = ("--skip-text", "-l", "fra+eng+ron", "--rotate-pages",
            "--rotate-pages-threshold", "0.3", "--deskew", "--output-type", "pdf",
            "--jobs", "1")  # fmt: skip
_PAGES = re.compile(rb"^Pages:\s+(\d+)\s*$", re.M)
_WS = re.compile(r"\s")


class Runner(Protocol):
    def __call__(self, args: Sequence[str], timeout: float) -> bytes: ...


def run(args: Sequence[str], timeout: float) -> bytes:
    """Run a tool; a non-zero exit or a timeout fails the job (C5 §1.4.4, retries apply)."""
    return subprocess.run(list(args), capture_output=True, check=True, timeout=timeout).stdout


def solid_chars(text: str) -> int:
    return len(_WS.sub("", text))


def clean_page(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").replace("\x00", "").replace("\x0c", "")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def page_count(pdf: Path, runner: Runner) -> int:
    m = _PAGES.search(runner(["pdfinfo", str(pdf)], PDFTOTEXT_TIMEOUT))
    if not m:
        raise ValueError("pdfinfo reported no page count")
    return int(m.group(1))


def pdf_pages(pdf: Path, runner: Runner) -> list[str]:
    return [
        clean_page(
            runner(
                [
                    "pdftotext",
                    "-layout",
                    "-enc",
                    "UTF-8",
                    "-f",
                    str(n),
                    "-l",
                    str(n),
                    str(pdf),
                    "-",
                ],
                PDFTOTEXT_TIMEOUT,
            )
        )  # fmt: skip
        for n in range(1, page_count(pdf, runner) + 1)
    ]


def ocr(src: Path, textcache: Path, sha256: str, runner: Runner) -> Path:
    out = cache.ocr_path(textcache, sha256)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.tmp_of(out)
    runner(["ocrmypdf", *OCR_ARGS, str(src), str(tmp)], OCR_TIMEOUT)
    os.replace(tmp, out)
    return out


def extract(
    src: Path, mime_type: str, sha256: str, textcache: Path, runner: Runner = run,
    *, on_ocr=lambda: None,
) -> Pages:  # fmt: skip
    """The page texts, from the cache when present; writes the text cache and the OCR'd PDF."""
    hit = cache.read_pages(textcache, sha256)
    if hit is not None:
        return hit
    if mime_type == "application/pdf":
        pages = pdf_pages(src, runner)
        if all(solid_chars(p) >= OCR_PAGE_MIN for p in pages):
            result = Pages(sha256, "pdftotext", tuple(pages))
            cache.write_pages(textcache, result)
            return result
        on_ocr()
        ocred = ocr(src, textcache, sha256, runner)
    else:
        on_ocr()
        as_pdf = cache.directory(textcache, sha256) / f"{sha256}.img.pdf.tmp"
        as_pdf.parent.mkdir(parents=True, exist_ok=True)
        try:
            runner(["img2pdf", str(src), "-o", str(as_pdf)], OCR_TIMEOUT)
            ocred = ocr(as_pdf, textcache, sha256, runner)
        finally:
            as_pdf.unlink(missing_ok=True)
    result = Pages(sha256, "ocr", tuple(pdf_pages(ocred, runner)))
    cache.write_pages(textcache, result)
    return result


def viewer_pdf(src: Path, mime_type: str, textcache: Path, sha256: str) -> Path | None:
    """The PDF the viewer shows: the OCR'd copy if it exists, else the original (PDFs only)."""
    ocred = cache.ocr_path(textcache, sha256)
    if ocred.exists():
        return ocred
    return src if mime_type == "application/pdf" else None


def thumbnail(pdf: Path, textcache: Path, sha256: str, runner: Runner = run) -> Path:
    """C5 §1.3: page 1 at 60 dpi, `<sha>.p1.png`."""
    out = cache.thumbnail_path(textcache, sha256)
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    prefix = out.with_name(f"{sha256}.p1.tmp")
    runner(["pdftoppm", "-r", "60", "-f", "1", "-l", "1", "-png", "-singlefile", str(pdf),
            str(prefix)], PDFTOTEXT_TIMEOUT)  # fmt: skip
    os.replace(prefix.with_name(prefix.name + ".png"), out)
    return out
