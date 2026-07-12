import re
from enum import Enum
from typing import (
    Any,
    Iterable,
    TYPE_CHECKING,
    Union,
    overload,
    Literal,
    Callable,
    TypeVar,
    Mapping,
    dataclass_transform,
)
from dataclasses import fields as dataclass_fields, dataclass as dataclass_dataclass

from admin_helper.objects.config import (
    FieldFrameworkConfig,
    MaskingFrameworkConfig,
    ObjectRegistryConfig,
)
from admin_helper.objects.field import _field_info, field

if TYPE_CHECKING:
    from admin_helper.objects.registry import _ParentReference
    from admin_helper.objects.object import BaseObject


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


_bootstrap_field_config = FieldFrameworkConfig()
_bootstrap_masking_config = MaskingFrameworkConfig()
_registry_config: ObjectRegistryConfig | None = None


def _bind_registry_config(config: ObjectRegistryConfig) -> None:
    """Bind helpers to the configuration owned by the active registry."""

    global _registry_config
    _registry_config = config


def _field_framework_config() -> FieldFrameworkConfig:
    if _registry_config is None:
        return _bootstrap_field_config
    return _registry_config.fields


def _masking_framework_config() -> MaskingFrameworkConfig:
    if _registry_config is None:
        return _bootstrap_masking_config
    return _registry_config.logging.masking


def _values_equal(value: Any, candidate: Any) -> bool:
    if type(value) is not type(candidate):
        return False
    try:
        result = value == candidate
    except Exception:
        return value is candidate
    return result if isinstance(result, bool) else value is candidate


def _masked_value_is_set(value: Any, empty_values: Iterable[Any] = ()) -> bool:
    candidates = (*_field_framework_config().empty_values, *tuple(empty_values))
    return not any(_values_equal(value, candidate) for candidate in candidates)


def _format_display_value(
    value: Any, *, masked: bool = False, empty_values: Iterable[Any] = ()
) -> str:
    if masked:
        return (
            _field_framework_config().masked_value
            if _masked_value_is_set(value, empty_values)
            else _field_framework_config().not_set_value
        )
    return _format_log_value(value)


def is_abstract(obj: Union["BaseObject", type["BaseObject"], Any]) -> bool:
    """
    Return whether a registered class or object is marked as abstract.

    :param obj:
        The object to inspect or attach.

    :return:
        Returns True when the condition is satisfied; otherwise, returns False.
    """

    from admin_helper.objects.object import BaseObject
    from admin_helper.objects.registry import object_registry

    if isinstance(obj, type) and issubclass(obj, BaseObject):
        try:
            registration = object_registry._get_registration_by_class(obj)
        except KeyError:
            return bool(getattr(obj, "_abstract", False))
        return registration.abstract

    return bool(getattr(obj, "_abstract", False))


def _default_object_name(cls: type["BaseObject"]) -> str:
    """
    Convert a CamelCase class name into the default snake_case name.

    :return:
        Returns a value of type ``str``.
    """

    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()


def _validate_framework_field_names(cls: type["BaseObject"]) -> None:
    """Validate naming conventions required by framework field categories."""

    for _dataclass_field in dataclass_fields(cls):
        if _field_info(
            _dataclass_field
        ).internal and not _dataclass_field.name.startswith("_"):
            raise TypeError(
                f"Internal field '{_dataclass_field.name}' on "
                f"'{cls.__module__}.{cls.__qualname__}' must start with an underscore."
            )


_TClass = TypeVar("_TClass", bound=type)


@dataclass_transform(field_specifiers=(field,))
def dataclass(cls: _TClass) -> _TClass:
    return dataclass_dataclass(cls)


_T = TypeVar("_T", bound="BaseObject")


@overload
def register(
    *,
    abstract: Literal[True],
    name: str | None = None,
    parent: "_ParentReference" = None,
) -> Callable[[type[_T]], type[_T]]:
    """
    Transform and register a ``BaseObject`` subclass as a dataclass.  Abstract registrations define reusable templates and are never instantiated. Concrete registrations may store constructor arguments and an optional parent reference. Actual construction is delayed until ``instantiate_all`` runs.

    Examples:
        @register(name='app')
        class App(BaseObject):
            ...

    :param abstract:
        Whether the registration defines an abstract template.

    :param name:
        The name to process.

    :param parent:
        The parent object, registration, or logger selector.

    :return:
        Returns the configured callable.
    """

    ...


@overload
def register(
    *,
    abstract: Literal[False] = False,
    name: str | None = None,
    parent: "_ParentReference" = None,
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
) -> Callable[[type[_T]], type[_T]]:
    """
    Transform and register a ``BaseObject`` subclass as a dataclass.  Abstract registrations define reusable templates and are never instantiated. Concrete registrations may store constructor arguments and an optional parent reference. Actual construction is delayed until ``instantiate_all`` runs.

    Examples:
        @register(name='app')
        class App(BaseObject):
            ...

    :param abstract:
        Whether the registration defines an abstract template.

    :param name:
        The name to process.

    :param parent:
        The parent object, registration, or logger selector.

    :param args:
        The positional constructor arguments stored for delayed creation.

    :param kwargs:
        The keyword constructor arguments stored for delayed creation.

    :return:
        Returns the configured callable.
    """

    ...


@dataclass_transform(field_specifiers=(field,))
def register(
    *,
    abstract: bool = False,
    name: str | None = None,
    parent: "_ParentReference" = None,
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
) -> Callable[[type[_T]], type[_T]]:
    """
    Transform and register a ``BaseObject`` subclass as a dataclass.  Abstract registrations define reusable templates and are never instantiated. Concrete registrations may store constructor arguments and an optional parent reference. Actual construction is delayed until ``instantiate_all`` runs.

    Examples:
        @register(name='app')
        class App(BaseObject):
            ...

    :param abstract:
        Whether the registration defines an abstract template.

    :param name:
        The name to process.

    :param parent:
        The parent object, registration, or logger selector.

    :param args:
        The positional constructor arguments stored for delayed creation.

    :param kwargs:
        The keyword constructor arguments stored for delayed creation.

    :return:
        Returns the configured callable.
    """

    from admin_helper.objects.object import BaseObject
    from admin_helper.objects.registry import object_registry

    def decorator(cls: type[_T]) -> type[_T]:
        # Restrict the decorator to the framework hierarchy.
        if not issubclass(cls, BaseObject):
            raise TypeError(
                f"{cls.__module__}.{cls.__qualname__} must be a subclass of {BaseObject.__name__}."
            )

        # Copy caller-owned mappings and validate abstract template semantics.
        constructor_kwargs = dict(kwargs or {})
        if abstract and (args or constructor_kwargs):
            raise TypeError(
                f"Abstract class {cls.__qualname__!r} cannot define constructor arguments."
            )

        # Apply the runtime dataclass transformation, then record its delayed
        # construction metadata in the singleton registry.
        dataclass_cls = dataclass(cls)
        _validate_framework_field_names(dataclass_cls)
        return object_registry._register(
            name=name or _default_object_name(dataclass_cls),
            cls=dataclass_cls,
            abstract=abstract,
            parent=parent,
            constructor_args=args,
            constructor_kwargs=constructor_kwargs,
        )

    return decorator
