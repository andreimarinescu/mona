"""Practice-document access for S6: the v2 prompt, the 10-doc sample and page text (read-only)."""
import ast
import hashlib
import pathlib
import subprocess
import sys

CLASSIFY_DIR = pathlib.Path("~/DevFiles/mona-hq/classify").expanduser()
CORPUS = pathlib.Path("~/DevFiles/mona-hq/100 PDF neclasificate").expanduser()
TEXTCACHE = pathlib.Path("~/DevFiles/mona-hq/bench/corpus/textcache").expanduser()
REVIEW = pathlib.Path("~/DevFiles/mona-hq/classified/review.md").expanduser()
REVIEW_REF = pathlib.Path("~/DevFiles/mona-hq/classified/cls-35bnt/report.jsonl").expanduser()

SAMPLE = {
    "d946beb4fc08": "personal questionnaire",
    "90f3898a7337": "accountant approval-of-accounts letter",
    "110c37b2aaa1": "insurer/pension notice (21 pp)",
    "945a8bd4c054": "training-fund payment call",
    "aaf7383d5692": "bank letter",
    "2fa37b7d01cf": "insurance notice",
    "8701e7c358dc": "supplier invoice",
    "c8bea28024ed": "car-rental receipt",
    "0ee7c1361fce": "local purchase invoice",
    "437dfdbb789d": "payroll declaration (DSN)",
}


def v2_definitions() -> dict:
    """CATEGORIES, SCHEMA and SYSTEM from classify_llm.py, kept out of the repo (real names)."""
    tree = ast.parse((CLASSIFY_DIR / "classify_llm.py").read_text())
    ns: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id in {"CATEGORIES", "SCHEMA", "SYSTEM"}:
            exec(compile(ast.Module([node], []), "classify_llm.py", "exec"), ns)  # noqa: S102
    return {k: ns[k] for k in ("CATEGORIES", "SCHEMA", "SYSTEM")}


def ground_truth() -> dict:
    sys.path.insert(0, str(CLASSIFY_DIR))
    from compare import load
    from score import ground_truth as gt

    return gt(str(REVIEW), load(str(REVIEW_REF)))[0]


def sample_docs() -> list[dict]:
    by_sha = {}
    for p in sorted(CORPUS.glob("*.pdf")):
        sha = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        if sha in SAMPLE:
            by_sha[sha] = p
    missing = set(SAMPLE) - set(by_sha)
    if missing:
        raise RuntimeError(f"sample docs not found: {sorted(missing)}")
    gt = ground_truth()
    return [{"sha12": s, "label": SAMPLE[s], "path": by_sha[s], "gt": gt.get(by_sha[s].name)}
            for s in SAMPLE]


def cache_text(path: pathlib.Path) -> str:
    return (TEXTCACHE / (path.name + ".txt")).read_text(encoding="utf-8", errors="replace")


def page_count(path: pathlib.Path) -> int:
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=False).stdout
    return next(int(line.split()[-1]) for line in info.splitlines() if line.startswith("Pages:"))


def page_texts(path: pathlib.Path, max_pages: int = 3, layout: bool = True) -> list[str]:
    n = min(page_count(path), max_pages)
    args = ["pdftotext"] + (["-layout"] if layout else [])
    return [subprocess.run(args + ["-f", str(i), "-l", str(i), str(path), "-"],
                           capture_output=True, text=True, timeout=60, check=False).stdout.replace("\x00", "")
            for i in range(1, n + 1)]
