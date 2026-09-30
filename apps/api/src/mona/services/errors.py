"""C4 §2.4 error codes raised by the services; L2 maps them to MCP and REST errors."""

from typing import Any

from mona.fileops.errors import FileOpError


class ServiceError(FileOpError):
    """`code` is a C4 §2.4 code; `field` and `valid` follow its `invalid_argument` shape."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        valid: list[Any] | None = None,
        hint: str | None = None,
    ):
        super().__init__(code, message, hint=hint)
        self.field = field
        self.valid = valid
