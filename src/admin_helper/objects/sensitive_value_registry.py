from __future__ import annotations

from collections import Counter
from threading import RLock

from collections.abc import Iterable
from typing import Any, TYPE_CHECKING

from admin_helper.objects.config import SensitiveValueFilterMode
from admin_helper.objects.helper import (
    _field_framework_config,
    _masking_framework_config,
)

if TYPE_CHECKING:
    from admin_helper.objects.object import BaseObject


class _SensitiveValueRegistry:
    """Cache sensitive values used by the optional defensive logging filter."""

    def __init__(self) -> None:
        self._values: Counter[str] = Counter()
        self._lock = RLock()

    @staticmethod
    def _token(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode(errors="replace")
        elif not isinstance(value, str):
            value = str(value)
        return value if value else None

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def rebuild(
        self, objects: Iterable[BaseObject], mode: SensitiveValueFilterMode
    ) -> None:
        """Rebuild cached values from the supplied object snapshot."""

        self.clear()
        if mode is SensitiveValueFilterMode.DISABLED:
            return
        for obj in objects:
            obj._register_masked_fields(
                include_computed=mode is SensitiveValueFilterMode.FIELDS_AND_COMPUTED
            )

    def register(self, value: Any) -> None:
        token = self._token(value)
        if token is None:
            return
        with self._lock:
            self._values[token] += 1

    def unregister(self, value: Any) -> None:
        token = self._token(value)
        if token is None:
            return
        with self._lock:
            count = self._values.get(token, 0)
            if count <= 1:
                self._values.pop(token, None)
            else:
                self._values[token] = count - 1

    def redact_text(self, value: str) -> str:
        with self._lock:
            tokens = sorted(
                (token for token in self._values if len(token) >= 4),
                key=len,
                reverse=True,
            )
        for token in tokens:
            value = value.replace(token, _field_framework_config().masked_value)
        return value

    def sanitize(self, value: Any) -> Any:
        if (
            _masking_framework_config().mode is SensitiveValueFilterMode.DISABLED
            or not _masking_framework_config().enabled
        ):
            return value
        with self._lock:
            tokens = set(self._values)
        if isinstance(value, str):
            if value in tokens:
                return _field_framework_config().masked_value
            return self.redact_text(value)
        if isinstance(value, bytes):
            decoded = value.decode(errors="replace")
            if decoded in tokens:
                return _field_framework_config().masked_value.encode()
            return self.redact_text(decoded).encode()
        if isinstance(value, tuple):
            return tuple(self.sanitize(item) for item in value)
        if isinstance(value, list):
            return [self.sanitize(item) for item in value]
        if isinstance(value, dict):
            return {
                self.sanitize(key): self.sanitize(item) for key, item in value.items()
            }
        if str(value) in tokens:
            return _field_framework_config().masked_value
        return value


_bootstrap_sensitive_values = _SensitiveValueRegistry()
_active_sensitive_values = _bootstrap_sensitive_values


def _bind_sensitive_value_registry(registry: _SensitiveValueRegistry) -> None:
    """Bind logging and object helpers to the registry-owned cache."""

    global _active_sensitive_values
    _active_sensitive_values = registry


def _sensitive_value_registry() -> _SensitiveValueRegistry:
    return _active_sensitive_values
