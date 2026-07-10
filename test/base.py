from __future__ import annotations

import logging
import re

from abc import ABC
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, fields
from typing import Any, TypeVar, cast, dataclass_transform, overload, Literal

from admin_helper.exceptions import BroadcastException
from admin_helper.settings import AdminHelperSettings

T = TypeVar("T", bound="BaseObject")

BROADCAST_METHODS: list[str] = []


class RegistryError(RuntimeError):
    """Basisklasse für Fehler beim Aufbau der Object-Registry."""


class DuplicateRegistrationNameError(RegistryError):
    pass


class UnregisteredSubclassError(RegistryError):
    pass


class ParentResolutionError(RegistryError):
    pass


class ObjectTreeLoopError(RegistryError):
    pass


ParentReference = str | type["BaseObject"] | None


@dataclass(slots=True)
class ObjectRegistration:
    name: str
    cls: type["BaseObject"]
    abstract: bool
    parent_reference: ParentReference

    constructor_args: tuple[Any, ...] = ()
    constructor_kwargs: dict[str, Any] = field(default_factory=dict)

    instance: BaseObject | None = None

    @property
    def instantiated(self) -> bool:
        return self.instance is not None


@dataclass(frozen=True, slots=True)
class ConstructionContext:
    registration: ObjectRegistration
    parent: BaseObject | None


_construction_context: ContextVar[ConstructionContext | None] = ContextVar("base_object_construction_context", default=None)


class ObjectRegistry:
    def __init__(self) -> None:
        self._registrations_by_name: dict[str, ObjectRegistration] = {}
        self._registrations_by_class: dict[type[BaseObject], ObjectRegistration] = {}

        self._building = False
        self._built = False

    def register(self,
                 *,
                 name: str,
                 cls: type[T],
                 abstract: bool,
                 parent: ParentReference = None,
                 constructor_args: tuple[Any, ...] = (),
                 constructor_kwargs: Mapping[str, Any] | None = None) -> type[T]:
        normalized_name = self._normalize_name(name)
        kwargs = dict(constructor_kwargs or {})

        if normalized_name in self._registrations_by_name:
            existing = self._registrations_by_name[normalized_name]

            raise DuplicateRegistrationNameError(f"Registration name {normalized_name!r} is already used by "
                                                 f"{existing.cls.__module__}.{existing.cls.__qualname__}.")

        if cls in self._registrations_by_class:
            existing = self._registrations_by_class[cls]

            raise RegistryError(f"Class {cls.__module__}.{cls.__qualname__} is already "
                                f"registered as {existing.name!r}.")

        if abstract:
            if parent is not None:
                raise RegistryError(f"Abstract registration {normalized_name!r} cannot have "
                                    "an object parent.")

            if constructor_args or kwargs:
                raise RegistryError(f"Abstract registration {normalized_name!r} cannot have "
                                    "constructor arguments.")

        registration = ObjectRegistration(name=normalized_name,
                                          cls=cls,
                                          abstract=abstract,
                                          parent_reference=parent,
                                          constructor_args=constructor_args,
                                          constructor_kwargs=kwargs)

        self._registrations_by_name[normalized_name] = registration
        self._registrations_by_class[cls] = registration

        cls._abstract = abstract

        return cls

    def instantiate_all(self) -> None:
        if self._building:
            raise RegistryError("The object registry is already being built.")

        if self._built:
            return

        self._building = True

        try:
            self._validate_all_subclasses_registered()
            self._validate_parent_references()
            self._validate_no_parent_loops()

            for registration in self._registrations_by_name.values():
                if registration.abstract:
                    continue

                self._instantiate_registration(registration)

            self._built = True

        except Exception:
            self._reset_instances()
            raise

        finally:
            self._building = False

    def _instantiate_registration(self,
                                  registration: ObjectRegistration) -> BaseObject:
        if registration.abstract:
            raise RegistryError(f"Abstract registration {registration.name!r} cannot be "
                                "instantiated.")

        if registration.instance is not None:
            return registration.instance

        parent_registration = self._resolve_parent_registration(registration)

        parent_instance: BaseObject | None = None

        if parent_registration is not None:
            if parent_registration.abstract:
                raise ParentResolutionError(f"Object {registration.name!r} uses abstract registration "
                                            f"{parent_registration.name!r} as its object parent.")

            parent_instance = self._instantiate_registration(parent_registration)

        context = ConstructionContext(registration=registration,
                                      parent=parent_instance)

        token = _construction_context.set(context)

        try:
            instance = registration.cls(*registration.constructor_args,
                                        **registration.constructor_kwargs)
        except Exception as error:
            raise RegistryError(f"Could not instantiate registration "
                                f"{registration.name!r} using "
                                f"{registration.cls.__module__}."
                                f"{registration.cls.__qualname__}: {error}") from error
        finally:
            _construction_context.reset(token)

        registration.instance = instance

        return instance

    def _validate_all_subclasses_registered(self) -> None:
        missing: list[type[BaseObject]] = []

        for subclass in self._all_subclasses(BaseObject):
            if subclass not in self._registrations_by_class:
                missing.append(subclass)

        if not missing:
            return

        missing_names = "\n".join(f"  - {cls.__module__}.{cls.__qualname__}" for cls in sorted(missing,
                                                                                               key=lambda item: (
                                                                                                   item.__module__,
                                                                                                   item.__qualname__)))

        raise UnregisteredSubclassError("The following BaseObject subclasses were not registered:\n"
                                        f"{missing_names}\n"
                                        "Decorate every subclass with @register_abstract(...) or "
                                        "@register_instance(...).")

    def _validate_parent_references(self) -> None:
        for registration in self._registrations_by_name.values():
            if registration.abstract:
                continue
            self._resolve_parent_registration(registration)

    def _validate_no_parent_loops(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(registration: ObjectRegistration) -> None:
            if registration.name in visited:
                return

            if registration.name in visiting:
                raise ObjectTreeLoopError(
                    f"Parent loop detected at registration "
                    f"{registration.name!r}."
                )

            visiting.add(registration.name)

            parent = self._resolve_parent_registration(registration)

            if parent is not None:
                visit(parent)

            visiting.remove(registration.name)
            visited.add(registration.name)

        for registration in self._registrations_by_name.values():
            if not registration.abstract:
                visit(registration)

    @staticmethod
    def _all_subclasses(cls: type[BaseObject]) -> tuple[type[BaseObject], ...]:
        result: list[type[BaseObject]] = []
        visited: set[type[BaseObject]] = set()

        def collect(current: type[BaseObject]) -> None:
            for subclass in current.__subclasses__():
                if subclass in visited:
                    continue

                visited.add(subclass)
                result.append(subclass)
                collect(subclass)

        collect(cls)

        return tuple(result)

    def _resolve_parent_registration(self,
                                     registration: ObjectRegistration) -> ObjectRegistration | None:
        reference = registration.parent_reference

        if reference is None:
            return None

        if isinstance(reference, str):
            normalized_name = self._normalize_name(reference)

            try:
                return self._registrations_by_name[normalized_name]
            except KeyError:
                raise ParentResolutionError(f"Parent {normalized_name!r} of registration "
                                            f"{registration.name!r} is not registered.") from None

        if isinstance(reference, type) and issubclass(reference, BaseObject):
            try:
                return self._registrations_by_class[reference]
            except KeyError:
                raise ParentResolutionError(f"Parent class {reference.__module__}."
                                            f"{reference.__qualname__} of registration "
                                            f"{registration.name!r} is not registered.") from None

        raise ParentResolutionError(f"Invalid parent reference {reference!r} for registration "
                                    f"{registration.name!r}.")

    def get_registration(self, name: str) -> ObjectRegistration:
        normalized_name = self._normalize_name(name)

        try:
            return self._registrations_by_name[normalized_name]
        except KeyError:
            raise KeyError(f"No object is registered as {normalized_name!r}.") from None

    def get_registration_by_class(self,
                                  cls: type[T]) -> ObjectRegistration:
        try:
            return self._registrations_by_class[cls]
        except KeyError:
            raise KeyError(f"Class {cls.__module__}.{cls.__qualname__} is not registered.") from None

    @overload
    def get_by_name(self, name: str) -> BaseObject:
        ...

    @overload
    def get_by_name(self,
                    name: str,
                    expected_type: type[T]) -> T:
        ...

    def get_by_name(self,
                    name: str,
                    expected_type: type[T] | None = None) -> BaseObject | T:
        registration = self.get_registration(name)

        if registration.abstract:
            raise TypeError(f"Registration {registration.name!r} is abstract and does "
                            "not have an instance.")

        if registration.instance is None:
            raise RuntimeError(f"Registration {registration.name!r} has not been "
                               "instantiated. Call object_registry.instantiate_all() first.")

        instance = registration.instance

        if (expected_type is not None and not isinstance(instance, expected_type)):
            raise TypeError(f"Registration {registration.name!r} contains "
                            f"{type(instance).__name__}, not "
                            f"{expected_type.__name__}.")

        return instance

    @overload
    def get_class(self, name: str) -> type[BaseObject]:
        ...

    @overload
    def get_class(self,
                  name: str,
                  expected_type: type[T]) -> type[T]:
        ...

    def get_class(self,
                  name: str,
                  expected_type: type[T] | None = None) -> type[BaseObject] | type[T]:
        registration = self.get_registration(name)
        cls = registration.cls

        if expected_type is not None and not issubclass(cls, expected_type):
            raise TypeError(f"Registered class {cls.__name__} is not a subclass of "
                            f"{expected_type.__name__}.")

        if expected_type is not None:
            return cast(type[T], cls)

        return cls

    def get_by_type(self,
                    expected_type: type[T]) -> tuple[T, ...]:
        result: list[T] = []

        for registration in self._registrations_by_name.values():
            instance = registration.instance

            if instance is not None and isinstance(instance, expected_type):
                result.append(instance)

        return tuple(result)

    def children_of(self,
                    parent: BaseObject) -> tuple[BaseObject, ...]:
        return tuple(parent._children)

    def get_child_by_name(self,
                          parent: BaseObject,
                          name: str, ) -> BaseObject | None:
        try:
            obj = self.get_by_name(name)
        except KeyError:
            return None

        if obj.parent is not parent:
            return None

        return obj

    def get_children_by_type(self,
                             parent: BaseObject,
                             expected_type: type[T]) -> tuple[T, ...]:
        return tuple(child
                     for child in self.children_of(parent)
                     if isinstance(child, expected_type))

    def attach_child(self,
                     parent: BaseObject,
                     child: T, ) -> T:
        if parent is child:
            raise ObjectTreeLoopError(f"{child.name!r} cannot be its own parent.")

        current: BaseObject | None = parent

        while current is not None:
            if current is child:
                raise ObjectTreeLoopError(f"Attaching {child.name!r} below {parent.name!r} "
                                          "would create a parent loop.")

            current = current.parent

        if child.parent is parent and child in parent._children:
            return child

        old_parent = child.parent

        if old_parent is not None and child in old_parent._children:
            old_parent._children.remove(child)

        with child._unlocked():
            child.parent = parent

        if child not in parent._children:
            parent._children.append(child)

        return child

    @property
    def built(self) -> bool:
        return self._built

    def registrations(self) -> tuple[ObjectRegistration, ...]:
        return tuple(self._registrations_by_name.values())

    def instances(self) -> tuple[BaseObject, ...]:
        return tuple(registration.instance
                     for registration in self._registrations_by_name.values()
                     if registration.instance is not None)

    def root_objects(self) -> tuple[BaseObject, ...]:
        return tuple(instance
                     for instance in self.instances()
                     if instance.parent is None)

    def __contains__(self, name: str) -> bool:
        return self._normalize_name(name) in self._registrations_by_name

    def __iter__(self) -> Iterator[ObjectRegistration]:
        return iter(self._registrations_by_name.values())

    def _reset_instances(self) -> None:
        for registration in self._registrations_by_name.values():
            instance = registration.instance

            if instance is not None:
                instance._children.clear()

            registration.instance = None

        self._built = False

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError("Registration name cannot be empty.")

        return normalized_name


object_registry = ObjectRegistry()


@dataclass
class BaseObject(ABC):
    # Öffentliche Attribute
    name: str = field(init=False,
                      metadata={"frozen": True})

    logger: logging.Logger = field(init=False,
                                   repr=False,
                                   metadata={"frozen": True})

    parent: BaseObject | None = field(default=None,
                                      init=False,
                                      repr=False,
                                      metadata={"frozen": True})

    # Private Attribute
    _init: bool = field(default=False,
                        init=False,
                        repr=False)

    _children: list[BaseObject] = field(default_factory=list,
                                        init=False,
                                        repr=False)

    _abstract: bool = field(default=False,
                            init=False,
                            repr=False,
                            metadata={"frozen": True})

    def __post_init__(self) -> None:
        context = _construction_context.get()

        if context is None:
            raise RuntimeError(f"{type(self).__module__}.{type(self).__qualname__} must be "
                               "instantiated through ObjectRegistry.instantiate_all().")

        registration = context.registration

        object.__setattr__(self, "_init", False)
        object.__setattr__(self, "name", registration.name)
        object.__setattr__(self, "parent", context.parent)
        object.__setattr__(self, "_abstract", registration.abstract)

        logger_name = registration.name

        if context.parent is not None:
            logger_name = f"{context.parent.logger.name}.{registration.name}"

        logger = logging.getLogger(logger_name)

        object.__setattr__(self, "logger", logger)

        if self._abstract:
            raise AttributeError(f"Object {self.name!r} is abstract and cannot be instantiated.")

        if self.parent is not None:
            object_registry.attach_child(self.parent, self)

        object.__setattr__(self, "_init", True)

        self.logger.debug("Initialized %s", self)

    def __setattr__(self,
                    key: str,
                    value: Any) -> None:
        if getattr(self, "_init", False):
            dataclass_field = next((dataclass_field for dataclass_field in fields(self) if dataclass_field.name == key), None)

            if dataclass_field is not None and dataclass_field.metadata.get("frozen", False):
                raise AttributeError(f"Field {dataclass_field.name!r} is frozen and cannot "
                                     "be modified.")

        super().__setattr__(key, value)

    @contextmanager
    def _unlocked(self) -> Iterator[BaseObject]:
        """
        Deaktiviert den Schreibschutz vorübergehend.

        Der vorherige Zustand wird auch bei einer Exception wiederhergestellt.
        """

        previous_state = self._init
        object.__setattr__(self, "_init", False)

        try:
            yield self
        finally:
            object.__setattr__(self, "_init", previous_state)

    @property
    def root_parent(self) -> BaseObject:
        current = self
        visited: set[int] = set()

        while current.parent is not None:
            identity = id(current)

            if identity in visited:
                raise ObjectTreeLoopError(f"Parent loop detected while resolving root of {self.name!r}.")

            visited.add(identity)
            current = current.parent

        return current

    @property
    def children(self) -> tuple[BaseObject, ...]:
        return object_registry.children_of(self)

    @property
    def children_flat(self) -> tuple[BaseObject, ...]:
        result: list[BaseObject] = []
        visited: set[int] = set()

        def collect(parent: BaseObject) -> None:
            for child in object_registry.children_of(parent):
                identity = id(child)

                if identity in visited:
                    raise ObjectTreeLoopError(f"Child loop detected below {self.name!r}.")

                visited.add(identity)
                result.append(child)
                collect(child)

        collect(self)

        return tuple(result)

    def add_child(self,
                  obj: T) -> T:
        if not isinstance(obj, BaseObject):
            raise TypeError(f"{obj!r} is not an instance of BaseObject.")

        return object_registry.attach_child(self, obj)

    @overload
    def get_child_by_name(self,
                          name: str) -> BaseObject | None:
        ...

    @overload
    def get_child_by_name(self,
                          name: str,
                          expected_type: type[T]) -> T | None:
        ...

    def get_child_by_name(self,
                          name: str,
                          expected_type: type[T] | None = None) -> BaseObject | T | None:
        child = object_registry.get_child_by_name(self, name)

        if child is None:
            return None

        if expected_type is not None and not isinstance(child, expected_type, ):
            raise TypeError(f"Child {name!r} is {type(child).__name__}, not  {expected_type.__name__}.")

        return child

    def get_child_by_type(self,
                          expected_type: type[T]) -> tuple[T, ...]:
        return object_registry.get_children_by_type(self, expected_type)

    def broadcast_call(self,
                       _method_name: str,
                       _wrap_errors: bool = not AdminHelperSettings.debug,
                       _stop_on_error: bool = True,
                       **method_kwargs: Any) -> list[Any]:
        self.logger.debug("Broadcasting %s -> %s", self, _method_name, )

        results: list[Any] = []

        for child in self.children:
            method = getattr(child, _method_name, None)

            if callable(method):
                try:
                    results.append(method(**method_kwargs))
                except Exception as error:
                    self.logger.error("Error while broadcasting %s -> %s: %s", self, _method_name, error, )

                    if not _wrap_errors:
                        raise

                    broadcast_error = BroadcastException(self, _method_name, error, )

                    results.append(broadcast_error)

                    if _stop_on_error:
                        broadcast_error.finalize()
                        raise broadcast_error
            else:
                results.append(child.broadcast_call(_method_name=_method_name, _wrap_errors=_wrap_errors, _stop_on_error=_stop_on_error, **method_kwargs, ))

        if _wrap_errors and not _stop_on_error:
            final_exception: BroadcastException | None = None

            for broadcast_result in results:
                if not isinstance(broadcast_result, BroadcastException, ):
                    continue

                if final_exception is None:
                    final_exception = BroadcastException()

                final_exception.errors.append(broadcast_result)

            if final_exception is not None:
                final_exception.finalize()
                raise final_exception

        return results


def is_abstract(obj: BaseObject | type[BaseObject] | Any) -> bool:
    if isinstance(obj, type) and issubclass(obj, BaseObject):
        try:
            registration = object_registry.get_registration_by_class(obj)
        except KeyError:
            return bool(getattr(obj, "_abstract", False))

        return registration.abstract

    return bool(getattr(obj, "_abstract", False))


def default_object_name(cls: type[BaseObject]) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__, ).lower()


@overload
def register(*,
             abstract: Literal[True],
             name: str | None = None) -> Callable[[type[T]], type[T]]:
    ...


@overload
def register(*,
             abstract: Literal[False] = False,
             name: str | None = None,
             parent: ParentReference = None,
             args: tuple[Any, ...] = (),
             kwargs: Mapping[str, Any] | None = None) -> Callable[[type[T]], type[T]]:
    ...


@dataclass_transform()
def register(*,
             abstract: bool = False,
             name: str | None = None,
             parent: ParentReference = None,
             args: tuple[Any, ...] = (),
             kwargs: Mapping[str, Any] | None = None) -> Callable[[type[T]], type[T]]:
    def decorator(cls: type[T]) -> type[T]:
        if not issubclass(cls, BaseObject):
            raise TypeError(f"{cls.__module__}.{cls.__qualname__} must be "
                            f"a subclass of {BaseObject.__name__}.")

        constructor_kwargs = dict(kwargs or {})

        if abstract and (parent is not None or args or constructor_kwargs):
            raise TypeError(f"Abstract class {cls.__qualname__!r} cannot define "
                            "parent or constructor arguments.")

        dataclass_cls = dataclass(cls)

        return object_registry.register(name=name or default_object_name(dataclass_cls),
                                        cls=dataclass_cls,
                                        abstract=abstract,
                                        parent=parent,
                                        constructor_args=args,
                                        constructor_kwargs=constructor_kwargs)

    return decorator


@register(abstract=True, name="apache_object")
class ApacheObject(BaseObject):
    enabled: bool


@register(name="apache",
          kwargs={"enabled": True,
                  "config_file": "/etc/apache2/httpd.conf"})
class ApacheRoot(ApacheObject):
    config_file: str


@register(name="static_files",
          parent="apache",
          kwargs={"enabled": True,
                  "url_path": "/static",
                  "directory": "/var/www/static"})
class StaticFilesApacheObject(ApacheObject):
    url_path: str
    directory: str


@register(name="reverse_proxy",
          parent=ApacheRoot,
          kwargs={"enabled": True,
                  "source": "/api",
                  "target": "http://127.0.0.1:8000"})
class ReverseProxyApacheObject(ApacheObject):
    source: str
    target: str


# class ForgottenObject(BaseObject):
#     value: str

# @register_instance(
#     name="first",
#     parent="second",
# )
# class First(BaseObject):
#     ...
#
#
# @register_instance(
#     name="second",
#     parent="first",
# )
# class Second(BaseObject):
#     ...

def initialize_objects() -> None:
    object_registry.instantiate_all()


if __name__ == "__main__":
    initialize_objects()

    apache = object_registry.get_by_name("apache", ApacheRoot)

    static_files = object_registry.get_by_name("static_files", StaticFilesApacheObject)

    print(apache.children)
    print(apache.children_flat)

    print(static_files.parent is apache)
    # True

    print(static_files.root_parent is apache)
    # True

    static_files = apache.get_child_by_name("static_files", StaticFilesApacheObject)

    proxy_objects = apache.get_child_by_type(ReverseProxyApacheObject)

    print()
