"""Declarative, nestable collections of object registrations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeVar, dataclass_transform, overload

from admin_helper.exceptions import BlueprintIncludeCycleError
from admin_helper.objects.field import field
from admin_helper.objects.object import BaseObject
from admin_helper.objects.registration import (
    _default_object_name,
    _prepare_registration_class,
)
from admin_helper.objects.registry import _ParentReference

_T = TypeVar("_T", bound=BaseObject)


@dataclass(frozen=True, slots=True)
class _BlueprintRegistration:
    """Store one object definition until a blueprint is included."""

    name: str
    cls: type[BaseObject]
    abstract: bool
    parent: _ParentReference
    args: tuple[Any, ...]
    kwargs: Mapping[str, Any]


class Blueprint:
    """Collect object definitions for later inclusion in an application."""

    def __init__(
        self,
        name: str,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        """Create a named declarative blueprint."""

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("A blueprint name cannot be empty.")

        self.name = normalized_name
        self.title = title
        self.description = description
        self._registrations: list[_BlueprintRegistration] = []
        self._included_blueprints: list[Blueprint] = []

    def include(self, blueprint: Blueprint) -> Blueprint:
        """Include another blueprint while rejecting recursive cycles."""

        if blueprint is self or blueprint._contains_blueprint(self):
            raise BlueprintIncludeCycleError(
                f"Including blueprint {blueprint.name!r} in {self.name!r} "
                "would create an include cycle."
            )
        if blueprint not in self._included_blueprints:
            self._included_blueprints.append(blueprint)
        return blueprint

    def _contains_blueprint(self, expected: Blueprint) -> bool:
        """Return whether this include graph already contains a blueprint."""

        visited: set[int] = set()

        def contains(current: Blueprint) -> bool:
            current_id = id(current)
            if current_id in visited:
                return False
            visited.add(current_id)
            if current is expected:
                return True
            return any(contains(child) for child in current._included_blueprints)

        return contains(self)

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
        """Store a framework-compatible object definition on this blueprint."""

        def decorator(cls: type[_T]) -> type[_T]:
            dataclass_cls = _prepare_registration_class(
                cls,
                abstract=abstract,
                args=args,
                kwargs=kwargs,
            )
            registration_name = name or _default_object_name(dataclass_cls)
            normalized_name = registration_name.strip()
            if not normalized_name:
                raise ValueError("A blueprint registration name cannot be empty.")
            if any(
                registration.name == normalized_name
                for registration in self._registrations
            ):
                raise ValueError(
                    f"Blueprint {self.name!r} already contains registration "
                    f"{normalized_name!r}."
                )
            self._registrations.append(
                _BlueprintRegistration(
                    name=normalized_name,
                    cls=dataclass_cls,
                    abstract=abstract,
                    parent=parent,
                    args=args,
                    kwargs=dict(kwargs or {}),
                )
            )
            return dataclass_cls

        return decorator

    def __repr__(self) -> str:
        """Return a concise diagnostic representation."""

        return f"Blueprint(name={self.name!r})"
