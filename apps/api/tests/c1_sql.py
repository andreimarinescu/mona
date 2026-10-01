"""Turns the C1 contract's ```sql listings into executable DDL."""

import re
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[3] / "docs" / "contracts"
C1 = CONTRACTS / "C1-domain.md"
C2 = CONTRACTS / "C2-rest-api.md"
AMENDMENTS = CONTRACTS / "amendments.md"

TIMESTAMP = "timestamptz NOT NULL DEFAULT now()"
ID_CHECK = "CHECK (id ~ '^{}_[0-9a-hjkmnp-tv-z]{{26}}$')"
FK = re.compile(
    r"\s+REFERENCES\s+(\w+(?:\s*\([^)]*\))?(?:\s+ON DELETE (?:RESTRICT|CASCADE|SET NULL)"
    r"(?:\s*\([^)]*\))?)?)",
)


def sql_blocks(text: str) -> list[str]:
    return re.findall(r"```sql\n(.*?)```", text, re.S)


def split_top_level(body: str) -> list[str]:
    items, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(cur.strip())
    return items


def statements(block: str) -> list[tuple[str, str]]:
    """Yields ("table", "name(body)") and ("stmt", "CREATE ...;") items, comments kept."""
    out, i = [], 0
    while i < len(block):
        rest = block[i:]
        stripped = rest.lstrip()
        if not stripped:
            break
        i += len(rest) - len(stripped)
        if stripped.startswith(("CREATE", "ALTER")):
            end = block.index(";", i)
            out.append(("stmt", block[i : end + 1]))
            i = end + 1
            continue
        m = re.match(r"(\w+)\s*\(", stripped)
        assert m, f"unparsed C1 sql near: {stripped[:60]!r}"
        depth, j = 0, i + m.end() - 1
        while True:
            if block[j] == "(":
                depth += 1
            elif block[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            elif block[j] == "-" and block[j + 1] == "-":
                j = block.index("\n", j) - 1
            j += 1
        out.append(("table", block[i : j + 1]))
        i = j + 1
    return out


def translate_table(src: str) -> tuple[str, list[str]]:
    name = re.match(r"(\w+)", src).group(1)
    lines = []
    for line in src[src.index("(") + 1 : src.rindex(")")].splitlines():
        code, _, comment = line.partition("--")
        prefix = re.match(r"\s*([a-z]{3})_", comment)
        if prefix and re.match(r"\s*id\s+text\s+PRIMARY KEY", code):
            code = code.replace("PRIMARY KEY", "PRIMARY KEY " + ID_CHECK.format(prefix.group(1)))
        lines.append(code)
    columns, fks = [], []
    for item in split_top_level("\n".join(lines)):
        item = " ".join(item.split())
        if item in ("created_at", "updated_at"):
            columns.append(f"{item} {TIMESTAMP}")
            continue
        if item.startswith("FOREIGN KEY"):
            fks.append(f"ALTER TABLE {name} ADD {item}")
            continue
        m = FK.search(item)
        if m:
            column = item.split()[0]
            fks.append(f"ALTER TABLE {name} ADD FOREIGN KEY ({column}) REFERENCES {m.group(1)}")
            item = item[: m.start()] + item[m.end() :]
        columns.append(item)
    return f"CREATE TABLE {name} (\n  " + ",\n  ".join(columns) + "\n)", fks


def _a9_column() -> str:
    """Amendment A9's `debrief_early_min` line, added at the end as the migration does."""
    section = AMENDMENTS.read_text().split("## A9 ", 1)[1].split("\n## ", 1)[0]
    line = next(x for x in section.splitlines() if x.strip().startswith("debrief_early_min"))
    column = " ".join(line.partition("--")[0].split()).rstrip(",")
    return f"ALTER TABLE settings ADD COLUMN {column}"


def _a18_defaults() -> str:
    """Amendment A18's threshold defaults, altered as migration 0006 does."""
    section = AMENDMENTS.read_text().split("## A18 ", 1)[1].split("\n## ", 1)[0]
    high = re.search(r"`confidence_high` defaults to (\d+)", section).group(1)  # type: ignore[union-attr]
    low = re.search(r"`confidence_low` to (\d+)", section).group(1)  # type: ignore[union-attr]
    return (
        f"ALTER TABLE settings ALTER COLUMN confidence_high SET DEFAULT {high},"
        f" ALTER COLUMN confidence_low SET DEFAULT {low}"
    )


def contract_ddl() -> list[str]:
    creates, fks, others = [], [], []
    auth = [b for b in sql_blocks(C2.read_text()) if b.lstrip().startswith("auth_sessions")]
    for block in sql_blocks(C1.read_text()) + auth:
        for kind, src in statements(block):
            if kind == "table":
                ddl, table_fks = translate_table(src)
                creates.append(ddl)
                fks += table_fks
            else:
                others.append(" ".join(re.sub(r"--[^\n]*", "", src).split()))
    search = [s for s in others if "TEXT SEARCH" in s]
    indexes = [s for s in others if s not in search]
    return search + creates + fks + indexes + [_a9_column(), _a18_defaults()]
