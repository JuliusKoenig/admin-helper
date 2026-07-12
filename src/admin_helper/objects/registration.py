"""Public decorators for framework-compatible dataclasses and objects."""

import re

from collections.abc import Callable, Mapping
from dataclasses import fields as dataclass_fields
from typing import Any, Literal, TypeVar, dataclass_transform, overload

from admin_helper.objects.field import _field_info, field, object_dataclass
from admin_helper.objects.object import BaseObject
from admin_helper.objects.registry import (
    _ObjectRegistry,
    _ParentReference,
    object_registry,
)

_TClass = TypeVar("_TClass", bound=type)
_T = TypeVar("_T", bound=BaseObject)


@dataclass_transform(field_specifiers=(field,))
def dataclass(cls: _TClass) -> _TClass:
    """Transform a class into a dataclass compatible with framework fields."""

    return object_dataclass(cls)


def is_abstract(obj: BaseObject | type[BaseObject] | Any) -> bool:
    """Return whether a registered class or object is marked as abstract."""

    if isinstance(obj, type) and issubclass(obj, BaseObject):
        try:
            registration = object_registry._get_registration_by_class(obj)
        except KeyError:
            return bool(getattr(obj, "_abstract", False))
        return registration.abstract

    return bool(getattr(obj, "_abstract", False))


def _default_object_name(cls: type[BaseObject]) -> str:
    """Convert a CamelCase class name into its default snake_case name."""

    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()


def _validate_framework_field_names(cls: type[BaseObject]) -> None:
    """Validate naming conventions required by framework field categories."""

    for dataclass_field in dataclass_fields(cls):
        if _field_info(
            dataclass_field
        ).internal and not dataclass_field.name.startswith("_"):
            raise TypeError(
                f"Internal field '{dataclass_field.name}' on "
                f"'{cls.__module__}.{cls.__qualname__}' must start with an underscore."
            )


@overload
def register(
    *,
    abstract: Literal[True],
    name: str | None = None,
    parent: _ParentReference = None,
) -> Callable[[type[_T]], type[_T]]: ...


@overload
def register(
    *,
    abstract: Literal[False] = False,
    name: str | None = None,
    parent: _ParentReference = None,
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
) -> Callable[[type[_T]], type[_T]]: ...


def _register_with_registry(
    registry: _ObjectRegistry,
    *,
    abstract: bool = False,
    name: str | None = None,
    parent: _ParentReference = None,
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
) -> Callable[[type[_T]], type[_T]]:
    """Create a framework registration decorator bound to one registry."""

    def decorator(cls: type[_T]) -> type[_T]:
        if not issubclass(cls, BaseObject):
            raise TypeError(
                f"{cls.__module__}.{cls.__qualname__} must be a subclass of "
                f"{BaseObject.__name__}."
            )

        constructor_kwargs = dict(kwargs or {})
        if abstract and (args or constructor_kwargs):
            raise TypeError(
                f"Abstract class {cls.__qualname__!r} cannot define constructor arguments."
            )

        dataclass_cls = dataclass(cls)
        _validate_framework_field_names(dataclass_cls)
        return registry._register(
            name=name or _default_object_name(dataclass_cls),
            cls=dataclass_cls,
            abstract=abstract,
            parent=parent,
            constructor_args=args,
            constructor_kwargs=constructor_kwargs,
        )

    return decorator


@dataclass_transform(field_specifiers=(field,))
def register(
    *,
    abstract: bool = False,
    name: str | None = None,
    parent: _ParentReference = None,
    args: tuple[Any, ...] = (),
    kwargs: Mapping[str, Any] | None = None,
) -> Callable[[type[_T]], type[_T]]:
    """Transform and register a class in the default object application."""

    return _register_with_registry(
        object_registry,
        abstract=abstract,
        name=name,
        parent=parent,
        args=args,
        kwargs=kwargs,
    )
