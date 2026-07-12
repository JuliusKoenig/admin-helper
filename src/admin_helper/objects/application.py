"""Public application facade for the object runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, TypeVar, cast, dataclass_transform, overload

from admin_helper.exceptions import BlueprintError, DuplicateBlueprintNameError
from admin_helper.objects.blueprint import Blueprint, _BlueprintRegistration
from admin_helper.objects.config import ObjectRegistryConfig
from admin_helper.objects.field import field
from admin_helper.objects.object import BaseObject
from admin_helper.objects.registration import _register_with_registry
from admin_helper.objects.registry import (
    _get_default_object_registry,
    _ObjectRegistry,
    _ParentReference,
    _set_default_object_registry,
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
        self._blueprints_by_name: dict[str, Blueprint] = {}
        self._blueprint_parents: dict[int, _ParentReference] = {}
        self._registration_blueprints: dict[
            type[BaseObject], tuple[Blueprint, ...]
        ] = {}

    @property
    def blueprints(self) -> tuple[Blueprint, ...]:
        """Return all included blueprints in deterministic resolution order."""

        return tuple(self._blueprints_by_name.values())

    def get_blueprint(self, name: str) -> Blueprint:
        """Return an included blueprint by its application-local name."""

        try:
            return self._blueprints_by_name[name]
        except KeyError as exc:
            raise KeyError(f"Blueprint {name!r} is not included.") from exc

    def include_blueprint(
        self,
        blueprint: Blueprint,
        *,
        parent: _ParentReference = None,
    ) -> Blueprint:
        """Copy one complete blueprint definition graph into this application.

        Included blueprints remain declarative source objects. Runtime objects do
        not retain blueprint references. The supplied parent replaces the parent
        of every root registration in the resolved blueprint graph.
        """

        if self.built:
            raise BlueprintError(
                "Blueprints cannot be included after the initial application build."
            )

        resolved = self._resolve_blueprints(blueprint)
        self._validate_blueprint_names(resolved)

        for included in resolved:
            included_id = id(included)
            if included_id not in self._blueprint_parents:
                continue
            if self._blueprint_parents[included_id] != parent:
                raise BlueprintError(
                    f"Blueprint {included.name!r} is already included with a "
                    "different parent binding."
                )

        if id(blueprint) in self._blueprint_parents:
            return blueprint

        new_blueprints = tuple(
            included
            for included in resolved
            if id(included) not in self._blueprint_parents
        )
        registrations = [
            (owner, registration)
            for owner in new_blueprints
            for registration in owner._registrations
        ]
        self._validate_blueprint_registrations(registrations)

        origins_by_class: dict[type[BaseObject], list[Blueprint]] = {}
        for owner, registration in registrations:
            effective_parent = (
                parent if registration.parent is None else registration.parent
            )
            self._registry._register(
                name=registration.name,
                cls=registration.cls,
                abstract=registration.abstract,
                parent=effective_parent,
                constructor_args=registration.args,
                constructor_kwargs=registration.kwargs,
            )
            origins_by_class.setdefault(registration.cls, []).append(owner)

        for included in new_blueprints:
            self._blueprints_by_name[included.name] = included
            self._blueprint_parents[id(included)] = parent
        for cls, origins in origins_by_class.items():
            self._registration_blueprints[cls] = tuple(origins)
        return blueprint

    def blueprints_for_class(
        self,
        cls: type[BaseObject],
    ) -> tuple[Blueprint, ...]:
        """Return blueprint-origin metadata for one registered class."""

        return self._registration_blueprints.get(cls, ())

    @staticmethod
    def _resolve_blueprints(root: Blueprint) -> tuple[Blueprint, ...]:
        """Resolve nested includes depth-first while preserving declaration order."""

        resolved: list[Blueprint] = []
        visited: set[int] = set()
        active: list[Blueprint] = []

        def visit(current: Blueprint) -> None:
            current_id = id(current)
            if current_id in {id(item) for item in active}:
                cycle = " -> ".join(item.name for item in (*active, current))
                raise BlueprintError(f"Blueprint include cycle detected: {cycle}.")
            if current_id in visited:
                return
            active.append(current)
            for included in current._included_blueprints:
                visit(included)
            active.pop()
            visited.add(current_id)
            resolved.append(current)

        visit(root)
        return tuple(resolved)

    def _validate_blueprint_names(self, blueprints: tuple[Blueprint, ...]) -> None:
        """Reject application-local name ambiguity before mutating the registry."""

        pending: dict[str, Blueprint] = {}
        for blueprint in blueprints:
            existing = self._blueprints_by_name.get(blueprint.name)
            if existing is not None and existing is not blueprint:
                raise DuplicateBlueprintNameError(
                    f"Blueprint name {blueprint.name!r} is already used by a "
                    "different blueprint in this application."
                )
            other = pending.get(blueprint.name)
            if other is not None and other is not blueprint:
                raise DuplicateBlueprintNameError(
                    f"Blueprint graph contains multiple blueprints named "
                    f"{blueprint.name!r}."
                )
            pending[blueprint.name] = blueprint

    def _validate_blueprint_registrations(
        self,
        registrations: list[tuple[Blueprint, _BlueprintRegistration]],
    ) -> None:
        """Validate a complete blueprint import before registering any class."""

        pending_names: dict[str, type[BaseObject]] = {}
        pending_classes: set[type[BaseObject]] = set()
        for _, registration in registrations:
            normalized_name = self._registry._normalize_name(registration.name)
            existing = self._registry._registrations_by_name.get(normalized_name)
            if existing is not None:
                raise BlueprintError(
                    f"Registration name {normalized_name!r} is already present in "
                    "the application."
                )
            if registration.cls in self._registry._registrations_by_class:
                raise BlueprintError(
                    f"Class {registration.cls.__module__}."
                    f"{registration.cls.__qualname__} is already registered in "
                    "the application."
                )
            pending_class = pending_names.get(normalized_name)
            if pending_class is not None and pending_class is not registration.cls:
                raise BlueprintError(
                    f"Blueprint graph contains duplicate registration name "
                    f"{normalized_name!r}."
                )
            if registration.cls in pending_classes:
                raise BlueprintError(
                    f"Blueprint graph registers class {registration.cls.__module__}."
                    f"{registration.cls.__qualname__} more than once."
                )
            pending_names[normalized_name] = registration.cls
            pending_classes.add(registration.cls)

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


_default_application = Application(_registry=_get_default_object_registry())


def get_default_application() -> Application:
    """Return the application used by module-level convenience APIs."""

    return _default_application


def set_default_application(application: Application) -> Application:
    """Set the process-wide default application and return the previous one.

    Existing imports of ``application``, ``object_registry``, and ``register``
    remain valid because they resolve the active default lazily.
    """

    if not isinstance(application, Application):
        raise TypeError("The default application must be an Application instance.")

    global _default_application
    previous = _default_application
    _default_application = application
    _set_default_object_registry(application._registry)
    return previous


class _DefaultApplicationProxy:
    """Stable public handle delegating to the active default application."""

    def __getattr__(self, name: str) -> object:
        return getattr(get_default_application(), name)

    def __contains__(self, name: str) -> bool:
        return name in get_default_application()


application = cast(Application, _DefaultApplicationProxy())
"""Stable handle for the active default application."""
