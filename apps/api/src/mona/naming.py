def to_camel(name: str) -> str:
    """C1 §1.1.2: split on `_`, capitalise every part after the first."""
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


def to_snake(name: str) -> str:
    """Inverse of `to_camel` for C1 names."""
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in name)
