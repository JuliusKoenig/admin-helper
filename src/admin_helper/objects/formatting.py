"""Value formatting helpers used by fields and object logging."""

from collections.abc import Iterable
from enum import Enum
from typing import Any

from admin_helper.objects.runtime import _field_framework_config


def _format_log_value(value: Any) -> str:
    """Format a value for human-readable log output."""

    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    return str(value)


def _values_equal(value: Any, candidate: Any) -> bool:
    """Compare values conservatively without accepting non-boolean results."""

    if type(value) is not type(candidate):
        return False
    try:
        result = value == candidate
    except Exception:
        return value is candidate
    return result if isinstance(result, bool) else value is candidate


def _masked_value_is_set(value: Any, empty_values: Iterable[Any] = ()) -> bool:
    """Return whether a masked value differs from all configured empty values."""

    candidates = (*_field_framework_config().empty_values, *tuple(empty_values))
    return not any(_values_equal(value, candidate) for candidate in candidates)


def _format_display_value(
    value: Any, *, masked: bool = False, empty_values: Iterable[Any] = ()
) -> str:
    """Format a field value for object display output."""

    if masked:
        return (
            _field_framework_config().masked_value
            if _masked_value_is_set(value, empty_values)
            else _field_framework_config().not_set_value
        )
    return _format_log_value(value)
