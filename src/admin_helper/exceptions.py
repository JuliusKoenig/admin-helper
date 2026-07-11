from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from admin_helper.objects import BaseObject


class AdminHelperException(Exception):
    """Base exception for all application-specific errors."""


class OperatingSystemNotSupportedException(AdminHelperException):
    """Raised when the current operating system is not supported."""

class RegistryError(RuntimeError):
    """
    Base exception for registry definition, validation, and build errors.
    """


class DuplicateRegistrationNameError(RegistryError):
    """
    Raised when two class definitions use the same registration name.
    """


class DuplicateObjectNameError(RegistryError):
    """
    Raised when two instantiated nodes would receive the same full path.
    """


class AmbiguousObjectNameError(RegistryError):
    """
    Raised when a shortened object path identifies multiple instances.
    """


class UnregisteredSubclassError(RegistryError):
    """
    Raised when a loaded BaseObject subclass was not decorated.
    """


class ParentResolutionError(RegistryError):
    """
    Raised when a configured parent reference cannot be resolved.
    """


class ObjectTreeLoopError(RegistryError):
    """
    Raised when a registration or runtime parent relationship forms a cycle.
    """


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