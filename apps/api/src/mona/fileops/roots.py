"""C7 §1 roots and the §3 move-inside-root guard."""

import os
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from mona.fileops.errors import ForbiddenPath, RootsError

LOCATIONS = ("inbox", "archive", "trash")
DIR_MODE = 0o750


@dataclass(frozen=True)
class Roots:
    data: Path
    inbox: Path
    archive: Path
    trash: Path

    @classmethod
    def at(cls, data_dir: Path | str) -> "Roots":
        """Create the roots if missing and resolve them with `realpath` once."""
        data = Path(os.path.realpath(data_dir))
        paths = {}
        for name in LOCATIONS:
            p = data / name
            p.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
            paths[name] = Path(os.path.realpath(p))
        return cls(data=data, **paths)

    def root(self, location: str) -> Path:
        return {"inbox": self.inbox, "archive": self.archive, "trash": self.trash}[location]

    def check_single_filesystem(self, lstat=os.lstat) -> None:
        devs = {name: lstat(self.root(name)).st_dev for name in LOCATIONS}
        if len(set(devs.values())) != 1:
            raise RootsError(f"inbox, archive and trash are on different filesystems: {devs}")


def _check_dir(p: Path, rel: str, dev: int) -> None:
    st = os.lstat(p)
    if stat.S_ISLNK(st.st_mode):
        raise ForbiddenPath(rel, "symlinked directory in the path")
    if not stat.S_ISDIR(st.st_mode):
        raise ForbiddenPath(rel, "a path component is not a directory")
    if st.st_dev != dev:
        raise ForbiddenPath(rel, "a path component is on another filesystem")


def inside(root: Path, p: Path) -> bool:
    real, root_real = os.path.realpath(p), str(root)
    return real == root_real or real.startswith(root_real + "/")


def resolve_inside(root: Path, rel: str, *, create: bool = False, taken_ok: bool = False) -> Path:
    """C7 §3: the absolute path of `rel` under `root`, or ForbiddenPath before any change.

    `create` makes missing parents one at a time; `taken_ok` accepts a directory at the final
    component (a §8.1 collision), never a symlink."""
    if not rel or rel.startswith("/") or "\x00" in rel or "\\" in rel:
        raise ForbiddenPath(rel, "absolute path, NUL or backslash")
    rel = unicodedata.normalize("NFC", rel)
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ForbiddenPath(rel, "empty, '.' or '..' segment")
    dev = os.lstat(root).st_dev
    current = root
    for part in parts[:-1]:
        current = current / part
        try:
            _check_dir(current, rel, dev)
        except FileNotFoundError:
            if not create:
                return root.joinpath(*parts)
            try:
                os.mkdir(current, DIR_MODE)
            except FileExistsError:
                pass
            _check_dir(current, rel, dev)
    target = root.joinpath(*parts)
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        st = None
    if st is not None and stat.S_ISLNK(st.st_mode):
        raise ForbiddenPath(rel, "symlinked file")
    if st is not None and not stat.S_ISREG(st.st_mode) and not taken_ok:
        raise ForbiddenPath(rel, "the final component is not a regular file")
    if not inside(root, target.parent):
        raise ForbiddenPath(rel, "resolves outside its root")
    return target
