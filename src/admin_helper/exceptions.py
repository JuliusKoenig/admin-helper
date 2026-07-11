from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from admin_helper.objects import BaseObject


class AdminHelperException(Exception):
    """Base exception for all application-specific errors."""


class OperatingSystemNotSupportedException(AdminHelperException):
    """Raised when the current operating system is not supported."""


class LoggerConfigurationError(AdminHelperException):
    """Raised when an object-logger configuration is invalid."""


class BroadcastException(AdminHelperException):
    """Collect one or more errors raised during a tree broadcast."""

    def __init__(self,
                 obj: BaseObject | None = None,
                 method_name: str | None = None,
                 original_exception: Exception | None = None):
        self.object = obj
        self.method_name = method_name
        self.original_exception = original_exception
        self.errors: list[BroadcastException] = []
        super().__init__()

    @property
    def message(self) -> str:
        """Build the complete nested broadcast-error message."""

        parts = [error.message
                 for error in self.errors
                 if isinstance(error, BroadcastException)]

        if (self.object is not None
                and self.method_name is not None
                and self.original_exception is not None):
            parts.append(f"{self.object}.{self.method_name} -> "
                         f"{self.original_exception.__class__.__name__}"
                         f"({self.original_exception})")

        return ", ".join(part for part in parts if part)

    def finalize(self) -> None:
        """Store the final aggregated message on the exception instance."""

        self.args = (self.message,)
