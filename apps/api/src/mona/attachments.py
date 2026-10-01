"""C4 §4.2 (with A13): the `ingest_attachment` path guard over Hermes' read-only media cache."""

import errno
import os
import re
import stat
from dataclasses import dataclass

SUBTREES = ("documents", "images")
MAX_PATH = 1024
HERMES_PREFIX = re.compile(r"^(doc_[0-9a-f]{12}_|img_[0-9a-f]{12})")


class Refused(Exception):
    """`code` is `forbidden_path` or `invalid_argument` (C4 §2.4)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Attachment:
    rel: str
    fd: int
    size: int


def _inside(root: str, real: str) -> bool:
    return any(real.startswith(f"{root}/{sub}/") for sub in SUBTREES)


def resolve(root: str, path: str) -> str:
    """Steps 1–4: the path relative to `root` (already realpath'd), checked on its real path."""
    if "\x00" in path or "\\" in path:
        raise Refused("forbidden_path", "That path is not an attachment.")
    if len(path) > MAX_PATH:
        raise Refused("invalid_argument", "The path is too long.")
    real = os.path.realpath(os.path.join(root, path))
    if not _inside(root, real):
        raise Refused("forbidden_path", "That path is not an attachment.")
    if not os.path.lexists(real):
        real = _by_prefix(root, real)
    return real[len(root) + 1 :]


def _by_prefix(root: str, real: str) -> str:
    """Step 4: a re-typed name (NFC for NFD) found by Hermes' unique `doc_<12 hex>_` prefix."""
    folder, name = os.path.split(real)
    m = HERMES_PREFIX.match(name)
    missing = Refused("invalid_argument", "No attachment at that path.")
    if m is None:
        raise missing
    try:
        found = [n for n in os.listdir(folder) if n.startswith(m.group(1))]
    except OSError:
        raise missing from None
    if len(found) != 1:
        raise missing
    real = os.path.realpath(os.path.join(folder, found[0]))
    if not _inside(root, real):
        raise Refused("forbidden_path", "That path is not an attachment.")
    return real


def open_rel(root: str, rel: str) -> Attachment:
    """Step 5: `openat` each component without following links; only a regular file passes, and
    `O_NONBLOCK` keeps a FIFO from blocking the open."""
    parts = rel.split("/")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except OSError as e:
        if e.errno == errno.ENOENT:
            raise Refused("invalid_argument", "No attachment at that path.") from None
        raise Refused("forbidden_path", "That path is not an attachment.") from None
    finally:
        os.close(fd)
    st = os.fstat(file_fd)
    if stat.S_ISREG(st.st_mode):
        return Attachment(rel, file_fd, st.st_size)
    os.close(file_fd)
    if stat.S_ISDIR(st.st_mode):
        raise Refused("invalid_argument", "That path is a folder, not a file.")
    raise Refused("forbidden_path", "That path is not an attachment.")


def open_attachment(root: str, path: str) -> Attachment:
    return open_rel(root, resolve(root, path))


def read_all(fd: int, limit: int) -> bytes | None:
    """The file's bytes, or None when it holds more than `limit`; closes `fd`."""
    chunks, total = [], 0
    try:
        while chunk := os.read(fd, 1024 * 1024):
            total += len(chunk)
            if total > limit:
                return None
            chunks.append(chunk)
    finally:
        os.close(fd)
    return b"".join(chunks)
