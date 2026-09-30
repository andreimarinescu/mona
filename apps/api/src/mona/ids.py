import os
import time

_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"


def new_id(prefix: str) -> str:
    """`<prefix>_` + a lowercase Crockford ULID (48-bit ms time, 80 random bits)."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    chars = [_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5)]
    return f"{prefix}_{''.join(chars)}"
