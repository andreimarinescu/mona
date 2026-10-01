"""C9 §7 log hygiene: exceptions are logged by class and constraint name, never their text."""

import logging

_FORMAT = "%(levelname)s %(name)s: %(message)s"
_SAFE_LOGGERS = ("", "uvicorn", "uvicorn.error", "procrastinate")


def exc_summary(exc: BaseException) -> str:
    """`ClassName` plus the violated constraint when the database names one."""
    orig = getattr(exc, "orig", None) or exc
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    name = type(exc).__name__
    return f"{name} ({constraint})" if constraint else name


class SafeExceptions(logging.Filter):
    """Replaces a record's traceback, whose message may quote rows or documents, by its class."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[1] is not None:
            summary = exc_summary(record.exc_info[1])
            record.msg = f"{record.getMessage()} [{summary}]"
            record.args = None
            record.exc_info = None
            record.exc_text = None
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent: a stderr handler, `mona` at `level`, and the filter on every handler we own."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
    logging.getLogger("mona").setLevel(level)
    for name in _SAFE_LOGGERS:
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, SafeExceptions) for f in handler.filters):
                handler.addFilter(SafeExceptions())
