class FileOpError(Exception):
    """A refused or failed operation; `code` is a C4 §2.4 error code or a C7 undo state."""

    def __init__(self, code: str, message: str = "", *, hint: str | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.hint = hint


class ForbiddenPath(FileOpError):
    """C7 §3: raised before any change; `rel` is the relative path, never file contents."""

    def __init__(self, rel: str, why: str):
        super().__init__("forbidden_path", f"{why}: {rel!r}")
        self.rel = rel


class RootsError(RuntimeError):
    """C7 §1.2: inbox, archive and trash must share one filesystem."""


class SimulatedCrash(BaseException):
    """Test-only: stands for the process dying at a C7 §10.2 injection point."""
