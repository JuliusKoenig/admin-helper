"""Public application facade for the object runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, TypeVar, dataclass_transform, overload

from admin_helper.objects.config import ObjectRegistryConfig
from admin_helper.objects.field import field
from admin_helper.objects.object import BaseObject
from admin_helper.objects.registration import _register_with_registry
from admin_helper.objects.registry import (
    _ObjectRegistry,
    _ParentReference,
    object_registry,
)

_T = TypeVar("_T", bound=BaseObject)


class Application:
    """Own and expose one hierarchical object runtime.

    The application is the public facade. Its registry remains an internal
    implementation detail responsible for definitions, runtime indexes, and
    tree consistency.
    """

    def __init__(self, *, _registry: _ObjectRegistry | None = None) -> None:
        """Create an application with an isolated internal registry."""

        self._registry = _registry or _ObjectRegistry()

    @property
    def config(self) -> ObjectRegistryConfig:
        """Return the configuration of this application runtime."""

        return self._registry.config

    @property
    def built(self) -> bool:
        """Return whether the initial object graph has been built."""

        return self._registry.built

    @overload
    def register(
        self,
        *,
        abstract: Literal[True],
        name: str | None = None,
        parent: _ParentReference = None,
    ) -> Callable[[type[_T]], type[_T]]: ...

    @overload
    def register(
        self,
        *,
        abstract: Literal[False] = False,
        name: str | None = None,
        parent: _ParentReference = None,
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any] | None = None,
    ) -> Callable[[type[_T]], type[_T]]: ...

    @dataclass_transform(field_specifiers=(field,))
    def register(
        self,
        *,
        abstract: bool = False,
        name: str | None = None,
        parent: _ParentReference = None,
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any] | None = None,
    ) -> Callable[[type[_T]], type[_T]]:
        """Register a framework object definition in this application."""

        return _register_with_registry(
            self._registry,
            abstract=abstract,
            name=name,
            parent=parent,
            args=args,
            kwargs=kwargs,
        )

    def build(self) -> None:
        """Validate definitions and construct the initial object graph."""

        self._registry.instantiate_all()

    def instantiate_all(self) -> None:
        """Build the initial graph using the legacy registry terminology."""

        self.build()

    @overload
    def get_by_name(self, name: str) -> BaseObject: ...

    @overload
    def get_by_name(self, name: str, expected_type: type[_T]) -> _T: ...

    def get_by_name(
        self, name: str, expected_type: type[_T] | None = None
    ) -> BaseObject | _T:
        """Return one object resolved by full name or unique suffix."""

        if expected_type is None:
            return self._registry.get_by_name(name)
        return self._registry.get_by_name(name, expected_type)

    @overload
    def find_by_name(self, pattern: str) -> tuple[BaseObject, ...]: ...

    @overload
    def find_by_name(
        self, pattern: str, expected_type: type[_T]
    ) -> tuple[_T, ...]: ...

    def find_by_name(
        self, pattern: str, expected_type: type[_T] | None = None
    ) -> tuple[BaseObject, ...] | tuple[_T, ...]:
        """Return all objects matching a wildcard name pattern."""

        if expected_type is None:
            return self._registry.find_by_name(pattern)
        return self._registry.find_by_name(pattern, expected_type)

    def get_by_type(self, expected_type: type[_T]) -> tuple[_T, ...]:
        """Return all runtime objects compatible with the supplied type."""

        return self._registry.get_by_type(expected_type)

    @overload
    def get_class(self, name: str) -> type[BaseObject]: ...

    @overload
    def get_class(self, name: str, expected_type: type[_T]) -> type[_T]: ...

    def get_class(
        self, name: str, expected_type: type[_T] | None = None
    ) -> type[BaseObject] | type[_T]:
        """Return the registered class identified by its registration name."""

        if expected_type is None:
            return self._registry.get_class(name)
        return self._registry.get_class(name, expected_type)

    def instances(self) -> tuple[BaseObject, ...]:
        """Return an immutable snapshot of all runtime objects."""

        return self._registry.instances()

    def root_objects(self) -> tuple[BaseObject, ...]:
        """Return all runtime objects without a parent."""

        return self._registry.root_objects()

    def __contains__(self, name: str) -> bool:
        """Return whether an exact full object name exists."""

        return name in self._registry


application = Application(_registry=object_registry)
"""Default application backing the legacy module-level API."""
