"""C5 §8.1 template grammar."""

from dataclasses import dataclass
from typing import Literal

TOKENS = frozenset(
    {"entity", "year", "fy", "category", "sub", "counterparty", "issuer", "reference", "date"}
)
DATE_UNITS = ("YYYY", "YY", "MM", "DD")
DATE_SEPARATORS = "-_."


class TemplateError(ValueError):
    def __init__(self, message: str, offset: int):
        super().__init__(f"{message} at offset {offset}")
        self.message = message
        self.offset = offset


@dataclass(frozen=True)
class Token:
    name: str
    format: str | None
    offset: int


Part = str | Token


def _check_date_format(fmt: str, offset: int) -> None:
    i = 0
    while i < len(fmt):
        unit = next((u for u in DATE_UNITS if fmt.startswith(u, i)), None)
        if unit:
            i += len(unit)
        elif fmt[i] in DATE_SEPARATORS:
            i += 1
        else:
            raise TemplateError(f"bad date format {fmt!r}", offset + i)


def parse(template: str, kind: Literal["path", "file"]) -> list[Part]:
    """Parse a path or file template; raises TemplateError with the character offset."""
    parts: list[Part] = []
    literal, i = "", 0
    while i < len(template):
        ch = template[i]
        if ch == "}":
            raise TemplateError("stray '}'", i)
        if ch != "{":
            literal += ch
            i += 1
            continue
        end = template.find("}", i + 1)
        nested = template.find("{", i + 1)
        if end == -1 or (nested != -1 and nested < end):
            raise TemplateError("unclosed '{'", i)
        name, sep, fmt = template[i + 1 : end].partition(":")
        if name not in TOKENS:
            raise TemplateError(f"unknown token {{{name}}}", i)
        if sep and name != "date":
            raise TemplateError(f"format on non-date token {{{name}}}", i)
        if sep and not fmt:
            raise TemplateError("empty date format", i)
        if fmt:
            _check_date_format(fmt, i + len(name) + 2)
        if literal:
            parts.append(literal)
            literal = ""
        parts.append(Token(name, fmt or None, i))
        i = end + 1
    if literal:
        parts.append(literal)
    if kind == "file":
        _check_file(template, parts)
    else:
        _check_path(template)
    return parts


def _check_file(template: str, parts: list[Part]) -> None:
    if "/" in template:
        raise TemplateError("'/' in a file template", template.index("/"))
    if not parts or not (isinstance(parts[0], Token) and parts[0].name == "date"):
        raise TemplateError("a file template must start with a {date} token", 0)


def _check_path(template: str) -> None:
    if not template:
        raise TemplateError("empty path template", 0)
    offset = 0
    for segment in template.split("/"):
        if segment == "":
            raise TemplateError("empty path segment", offset)
        if segment in (".", ".."):
            raise TemplateError(f"'{segment}' path segment", offset)
        offset += len(segment) + 1
