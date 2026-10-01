"""D12 guard: no entity, person or counterparty name or alias from the seed in product code.

Reads demo/seed/practice.yaml and fails if any name appears (case-insensitive, word-bounded) in
apps/*/src, packages/ or deploy/hermes/ (outside the generated memories/). Tests, fixtures and
docs may use them as examples.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
# Not practice-specific: the product's own Visitors entity (C9 §5) and a national public body.
GENERIC = {"visitors", "urssaf"}
SKIP_DIRS = {
    "node_modules",
    "dist",
    "__pycache__",
    "tests",
    "__tests__",
    "e2e",
    "fixtures",
    "memories",
}
SKIP_FILE = re.compile(r"(\.(test|spec)\.[cm]?[jt]sx?$)|(^fixtures\.)")


def names(seed: Path) -> list[str]:
    data = yaml.safe_load(seed.read_text(encoding="utf-8"))
    out: set[str] = set()

    def add(*values) -> None:
        for v in values:
            if isinstance(v, str) and v.strip():
                out.add(v.strip())
            elif isinstance(v, list):
                add(*v)

    practice = data.get("practice", {})
    add(practice.get("name"), practice.get("owner_name"))
    for p in data.get("people", []):
        add(p.get("display_name"), p.get("short_name"), p.get("aliases"))
    for e in data.get("entities", []):
        add(e.get("display_name"), e.get("aliases"))
    for c in data.get("counterparties", []):
        add(c.get("name"), c.get("aliases"))
    return sorted(n for n in out if n.casefold() not in GENERIC)


def scanned(root: Path) -> list[Path]:
    bases = [*sorted((root / "apps").glob("*/src")), root / "packages", root / "deploy" / "hermes"]
    out = []
    for base in bases:
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(base).parts
            if p.is_file() and not SKIP_DIRS.intersection(rel) and not SKIP_FILE.search(p.name):
                out.append(p)
    return out


def hits(root: Path, seed: Path) -> list[str]:
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(n) for n in names(seed)) + r")(?!\w)", re.IGNORECASE
    )
    out = []
    for path in scanned(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                out.append(f"{path.relative_to(root)}:{n}: {m.group(0)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--seed", type=Path, default=None)
    args = ap.parse_args()
    seed = args.seed or args.root / "demo" / "seed" / "practice.yaml"
    found = hits(args.root, seed)
    for h in found:
        print(h)
    if found:
        print(f"{len(found)} practice names in product code (D12)", file=sys.stderr)
        return 1
    print(f"no practice names: {len(names(seed))} names, {len(scanned(args.root))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
