from enum import Enum
from typing import Any, Iterable

from admin_helper.config import FieldFrameworkConfig, MaskingFrameworkConfig


def _format_log_value(value: Any) -> str:
    """
    Format structured log values consistently for human-readable messages.¬

    :param value:
        The value to validate or assign.

    :return:
        Returns a value of type ``str``.
    """

    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    return str(value)


def _field_framework_config() -> FieldFrameworkConfig:
    registry = globals().get("object_registry")
    return registry.config.fields if registry is not None else FieldFrameworkConfig()


def _masking_framework_config() -> MaskingFrameworkConfig:
    registry = globals().get("object_registry")
    return registry.config.logging.masking if registry is not None else MaskingFrameworkConfig()


def _values_equal(value: Any,
                  candidate: Any) -> bool:
    if type(value) is not type(candidate):
        return False
    try:
        result = value == candidate
    except Exception:
        return value is candidate
    return result if isinstance(result, bool) else value is candidate


def _masked_value_is_set(value: Any,
                         empty_values: Iterable[Any] = ()) -> bool:
    candidates = (*_field_framework_config().empty_values, *tuple(empty_values))
    return not any(_values_equal(value, candidate) for candidate in candidates)


def _format_display_value(value: Any,
                          *,
                          masked: bool = False,
                          empty_values: Iterable[Any] = ()) -> str:
    if masked:
        return _field_framework_config().masked_value if _masked_value_is_set(value, empty_values) else _field_framework_config().not_set_value
    return _format_log_value(value)

