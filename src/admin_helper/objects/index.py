from __future__ import annotations

import fnmatch

from typing import TYPE_CHECKING, TypeVar, cast, overload

from admin_helper.exceptions import AmbiguousObjectNameError
from admin_helper.objects.object import BaseObject

if TYPE_CHECKING:
    from admin_helper.objects.registry import _ObjectRegistration

_T = TypeVar("_T", bound=BaseObject)


class _ObjectIndex:
    """Store and query fully initialized objects for one registry instance."""

    def __init__(self) -> None:
        self._instances_by_name: dict[str, BaseObject] = {}
        self._instances_by_path: dict[str, list[BaseObject]] = {}
        self._registrations_by_instance: dict[int, _ObjectRegistration] = {}

    def add(
        self, instance: BaseObject, registration: _ObjectRegistration | None = None
    ) -> None:
        """Add an instance to the exact-name and suffix-path indexes."""

        self._instances_by_name[instance.name] = instance
        for object_path in self._name_paths(instance.name):
            path_instances = self._instances_by_path.setdefault(object_path, [])
            if not any(candidate is instance for candidate in path_instances):
                path_instances.append(instance)
        if registration is not None:
            self._registrations_by_instance[id(instance)] = registration

    def remove(self, instance: BaseObject, *, object_name: str | None = None) -> None:
        """Remove an instance from every index for one previously used name."""

        indexed_name = object_name or instance.name
        if self._instances_by_name.get(indexed_name) is instance:
            del self._instances_by_name[indexed_name]
        for object_path in self._name_paths(indexed_name):
            path_instances = self._instances_by_path.get(object_path)
            if path_instances is None:
                continue
            remaining = [
                candidate for candidate in path_instances if candidate is not instance
            ]
            if remaining:
                self._instances_by_path[object_path] = remaining
            else:
                del self._instances_by_path[object_path]

    def registration_for(self, instance: BaseObject) -> _ObjectRegistration | None:
        """Return the registration that created an indexed instance."""

        return self._registrations_by_instance.get(id(instance))

    def exact(self, name: str) -> BaseObject | None:
        """Return an object by exact full name without suffix fallback."""

        return self._instances_by_name.get(name)

    @overload
    def get_by_name(self, name: str) -> BaseObject: ...

    @overload
    def get_by_name(self, name: str, expected_type: type[_T]) -> _T: ...

    def get_by_name(
        self, name: str, expected_type: type[_T] | None = None
    ) -> BaseObject | _T:
        """Return exactly one object by full name or unique suffix."""

        instance = self._instances_by_name.get(name)
        if instance is None:
            matches = self._instances_by_path.get(name, [])
            if expected_type is not None:
                matches = [item for item in matches if isinstance(item, expected_type)]
            if not matches:
                raise KeyError(f"No instantiated object exists as {name!r}.")
            if len(matches) > 1:
                matching_names = tuple(item.name for item in matches)
                raise AmbiguousObjectNameError(
                    f"Object name {name!r} is ambiguous. "
                    f"Matching objects: {matching_names!r}."
                )
            instance = matches[0]

        if expected_type is not None and not isinstance(instance, expected_type):
            raise TypeError(
                f"Object {instance.name!r} contains {type(instance).__name__}, "
                f"not {expected_type.__name__}."
            )
        return instance

    @overload
    def find_by_name(self, pattern: str) -> tuple[BaseObject, ...]: ...

    @overload
    def find_by_name(self, pattern: str, expected_type: type[_T]) -> tuple[_T, ...]: ...

    def find_by_name(
        self, pattern: str, expected_type: type[_T] | None = None
    ) -> tuple[BaseObject, ...] | tuple[_T, ...]:
        """Find objects using segment-aware wildcard matching on every suffix."""

        result: list[BaseObject] = []
        visited: set[int] = set()
        for object_path, instances in self._instances_by_path.items():
            if not self._matches(object_path, pattern):
                continue
            for instance in instances:
                identity = id(instance)
                if identity in visited:
                    continue
                if expected_type is not None and not isinstance(
                    instance, expected_type
                ):
                    continue
                visited.add(identity)
                result.append(instance)
        if expected_type is not None:
            return cast(tuple[_T, ...], cast(object, tuple(result)))
        return tuple(result)

    def get_by_type(self, expected_type: type[_T]) -> tuple[_T, ...]:
        """Return all indexed objects compatible with ``expected_type``."""

        return tuple(
            instance
            for instance in self._instances_by_name.values()
            if isinstance(instance, expected_type)
        )

    def instances(self) -> tuple[BaseObject, ...]:
        """Return an immutable snapshot of all indexed instances."""

        return tuple(self._instances_by_name.values())

    def __contains__(self, name: str) -> bool:
        return name in self._instances_by_name

    def __len__(self) -> int:
        return len(self._instances_by_name)

    def clear(self) -> None:
        """Clear all runtime indexes and instance-registration mappings."""

        self._instances_by_name.clear()
        self._instances_by_path.clear()
        self._registrations_by_instance.clear()

    @staticmethod
    def _name_paths(object_name: str) -> tuple[str, ...]:
        name_parts = object_name.split(".")
        return tuple(".".join(name_parts[index:]) for index in range(len(name_parts)))

    @staticmethod
    def _matches(object_name: str, pattern: str) -> bool:
        object_parts = object_name.split(".")
        pattern_parts = pattern.split(".")

        def match(object_index: int, pattern_index: int) -> bool:
            if pattern_index == len(pattern_parts):
                return object_index == len(object_parts)
            pattern_part = pattern_parts[pattern_index]
            if pattern_part == "**":
                if pattern_index == len(pattern_parts) - 1:
                    return True
                return any(
                    match(next_index, pattern_index + 1)
                    for next_index in range(object_index, len(object_parts) + 1)
                )
            if object_index >= len(object_parts):
                return False
            if not fnmatch.fnmatchcase(object_parts[object_index], pattern_part):
                return False
            return match(object_index + 1, pattern_index + 1)

        return match(0, 0)
