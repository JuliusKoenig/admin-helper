from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from admin_helper.objects import BaseObject


class AdminHelperException(Exception):
    ...

class OperatingSystemNotSupportedException(AdminHelperException):
    ...

class BroadcastException(AdminHelperException):
    def __init__(self,
                 obj: Optional["BaseObject"] = None,
                 method_name: str | None = None,
                 original_exception: Exception | None = None):
        self.object = obj
        self.method_name = method_name
        self.original_exception = original_exception
        self.errors: list[BroadcastException] = []

    @property
    def message(self) -> str:
        message = ""
        for error in self.errors:
            if isinstance(error, BroadcastException):
                if message:
                    message += ", "
                message += f"{error.message}"
        if self.object is not None and self.method_name is not None and self.original_exception is not None:
            message += f"{self.object}"
        if self.object is not None and self.method_name is not None and self.original_exception is not None:
            message += f".{self.method_name}"
        if self.object is not None and self.method_name is not None and self.original_exception is not None:
            message += f" -> {self.original_exception.__class__.__name__}({self.original_exception})\n"
        return message

    def finalize(self) -> None:
        super().__init__(self.message)

