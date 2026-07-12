from __future__ import annotations

import inspect
import logging

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field as dataclass_field, fields as dataclass_fields
from typing import Any, Optional, TypeVar, cast, overload

from admin_helper.exceptions import (
    DuplicateObjectNameError,
    DuplicateRegistrationNameError,
    ObjectTreeLoopError,
    ParentResolutionError,
    RegistryError,
    UnregisteredSubclassError,
)
from admin_helper.objects.construction import (
    _ObjectConstructionContext,
    _construction_context,
)
from admin_helper.objects.config import (
    LoggerParent,
    ObjectLoggerConfig,
    ObjectRegistryConfig,
    ObjectStatus,
    RegistryConfigChange,
)
from admin_helper.objects.field import _field_info
from admin_helper.objects.index import _ObjectIndex
from admin_helper.objects.logger import ObjectLogger, _get_object_logger
from admin_helper.objects.object import BaseObject
from admin_helper.objects.runtime import _bind_registry_config
from admin_helper.objects.sensitive_value_registry import (
    _SensitiveValueRegistry,
    _bind_sensitive_value_registry,
    _sensitive_value_registry,
)

_T = TypeVar("_T", bound="BaseObject")

# Parent definitions are accepted only by the public decorator. Internally they
# are resolved to _ObjectRegistration objects before construction begins.
_ParentReference = str | type["BaseObject"] | None


@dataclass(slots=True)
class _ObjectRegistration:
    """
    Mutable internal metadata for one decorated class definition.
    """

    # Immutable-by-convention definition data captured by @register.
    name: str
    cls: type["BaseObject"]
    abstract: bool
    parent_reference: _ParentReference

    # Delayed constructor input for concrete registrations.
    constructor_args: tuple[Any, ...] = ()
    constructor_kwargs: dict[str, Any] = dataclass_field(default_factory=dict)

    # One template registration may create multiple instances below different
    # concrete parents, therefore instances are indexed by full object path.
    instances: dict[str, BaseObject] = dataclass_field(default_factory=dict)

    @property
    def instantiated(self) -> bool:
        """
        Execute the 'instantiated' operation.

        :return:
            Returns True when the condition is satisfied; otherwise, returns False.
        """
        return bool(self.instances)


# ---------------------------------------------------------------------------
# Private registry implementation
# ---------------------------------------------------------------------------


class _ObjectRegistry:
    """
    Own registration metadata, instances, indexes, and tree consistency.
    """

    def __init__(self, *, validate_all_subclasses: bool = False) -> None:
        """
        Initialize all internal indexes and lifecycle flags.  The registry stores registrations separately from instantiated objects. All mutable dictionaries remain private so callers cannot bypass validation, name uniqueness checks, or tree consistency rules.

        :return:
            Returns None.
        """

        self.config = ObjectRegistryConfig(self._apply_config_change)
        self._validate_loaded_subclasses = validate_all_subclasses
        self._sensitive_values = _SensitiveValueRegistry()
        self._registrations_by_name: dict[str, _ObjectRegistration] = {}
        self._registrations_by_class: dict[type[BaseObject], _ObjectRegistration] = {}
        self._index = _ObjectIndex()
        self._building = False
        self._built = False

    def _apply_config_change(self, change: RegistryConfigChange) -> None:
        """Apply one framework configuration side effect."""

        if change in {
            RegistryConfigChange.FIELD_RENDERING,
            RegistryConfigChange.SENSITIVE_VALUES,
        }:
            self._sensitive_values.rebuild(
                self.instances(), self.config.logging.masking.mode
            )
        if change is RegistryConfigChange.WARNING_CAPTURE:
            logging.captureWarnings(self.config.logging.warnings.capture)
            warning_logger = logging.getLogger("py.warnings")
            parent = self.config.logging.warnings.parent
            if parent is LoggerParent.ROOT:
                warning_logger.parent = logging.getLogger()
            elif parent is LoggerParent.NONE:
                warning_logger.parent = None
            elif isinstance(parent, str):
                warning_logger.parent = logging.getLogger(parent)
            warning_logger.propagate = warning_logger.parent is not None
        if change is RegistryConfigChange.LOGGER_TREE and self._built:
            for root in self.root_objects():
                root._configure_logger_tree()

    def _register(
        self,
        *,
        name: str,
        cls: type[_T],
        abstract: bool,
        parent: _ParentReference = None,
        constructor_args: tuple[Any, ...] = (),
        constructor_kwargs: Mapping[str, Any] | None = None,
    ) -> type[_T]:
        """
        Register a decorated ``BaseObject`` subclass.  This method is intentionally private. User code should use the public ``@register(...)`` decorator, which first applies the dataclass transform and then delegates to this method.  The method validates unique registration names, prevents the same class from being registered twice, rejects constructor arguments for abstract templates, and stores the resulting registration metadata.

        :param name:
            The name to process.

        :param abstract:
            Whether the registration defines an abstract template.

        :param parent:
            The parent object, registration, or logger selector.

        :param constructor_args:
            The 'constructor_args' value used by the operation.

        :param constructor_kwargs:
            The 'constructor_kwargs' value used by the operation.

        :return:
            Returns the matching class.
        """

        # Step 1: Normalize external input and copy mutable constructor data so
        # callers cannot alter the stored configuration after registration.
        normalized_name = self._normalize_name(name)
        kwargs = dict(constructor_kwargs or {})

        # Step 2: Enforce unique registration names and one registration per
        # class before modifying any registry state.
        if normalized_name in self._registrations_by_name:
            existing = self._registrations_by_name[normalized_name]

            raise DuplicateRegistrationNameError(
                f"Registration name {normalized_name!r} is already used by "
                f"{existing.cls.__module__}.{existing.cls.__qualname__}."
            )
        if cls in self._registrations_by_class:
            existing = self._registrations_by_class[cls]
            raise RegistryError(
                f"Class {cls.__module__}.{cls.__qualname__} is already "
                f"registered as {existing.name!r}."
            )

        # Step 3: Abstract registrations are templates, not constructible
        # objects, and therefore cannot own constructor arguments.
        if abstract and (constructor_args or kwargs):
            raise RegistryError(
                f"Abstract registration {normalized_name!r} cannot have "
                "constructor arguments."
            )

        # Step 4: Store the validated definition in both lookup indexes.
        registration = _ObjectRegistration(
            name=normalized_name,
            cls=cls,
            abstract=abstract,
            parent_reference=parent,
            constructor_args=constructor_args,
            constructor_kwargs=kwargs,
        )
        self._registrations_by_name[normalized_name] = registration
        self._registrations_by_class[cls] = registration

        # Step 5: Mirror the abstract marker on the class for cheap inspection
        # before instances exist, then preserve the decorated class type.
        cls._abstract = abstract

        # No object instance exists during registration. Use the future local
        # object logger name so the message participates in the same logging
        # namespace without adding handlers of its own.
        _get_object_logger(normalized_name).debug(
            "Registered class '%s.%s' as '%s'.",
            cls.__module__,
            cls.__qualname__,
            normalized_name,
        )

        return cls

    def instantiate_all(self) -> None:
        """
        Validate the complete registry and instantiate every concrete root.  The build runs only once. It first verifies that every ``BaseObject`` subclass was decorated, that all parent references resolve, and that the registration graph has no cycles. Concrete root registrations are then instantiated; their children are created recursively from the registered parent relationships.

        :return:
            Returns None.
        """

        # Guard against recursive builds and make repeated successful calls
        # idempotent.
        if self._building:
            raise RegistryError("The object registry is already being built.")
        if self._built:
            return
        self._building = True
        registry_logger = logging.getLogger("object_registry")
        registry_logger.debug("Starting object-registry validation and construction.")
        try:
            # Validate the complete definition graph before creating the first
            # object, so configuration errors cannot leave a partial tree.
            if self._validate_loaded_subclasses:
                self._validate_all_subclasses_registered()
            self._validate_parent_references()
            self._validate_no_parent_loops()

            # Only concrete root registrations start construction directly.
            # Descendants are created recursively by _instantiate_children.
            for registration in self._registrations_by_name.values():
                if registration.abstract:
                    continue
                if registration.parent_reference is not None:
                    continue
                self._instantiate_registration(
                    registration=registration, parent_instance=None
                )
            self._built = True
            registry_logger.debug(
                "Built the object registry successfully with %d instances.",
                len(self._index),
            )
        except Exception:
            # Roll back every object and index created during a failed build.
            registry_logger.exception(
                "The object registry build failed! Rolling back all created instances!"
            )
            self._reset_instances()
            raise
        finally:
            self._building = False

    @staticmethod
    def _constructor_masked_values(
        registration: _ObjectRegistration,
    ) -> tuple[Any, ...]:
        """
        Return masked constructor values before the object instance exists.

        Registering these values temporarily protects constructor-time logs and
        exception messages. After successful construction, ``BaseObject``
        registers the same values permanently for the lifetime of the object.

        :param registration:
            The registration whose delayed constructor arguments are inspected.

        :return:
            Returns the masked values present in the delayed constructor input.
        """

        try:
            bound_arguments = inspect.signature(registration.cls).bind_partial(
                *registration.constructor_args,
                **registration.constructor_kwargs,
            )
        except (TypeError, ValueError):
            return ()

        masked_names = {
            dataclass_field.name
            for dataclass_field in dataclass_fields(registration.cls)
            if _field_info(dataclass_field).masked
        }

        return tuple(
            bound_arguments.arguments[name]
            for name in masked_names
            if name in bound_arguments.arguments
        )

    def _instantiate_registration(
        self, registration: _ObjectRegistration, parent_instance: Optional["BaseObject"]
    ) -> "BaseObject":
        """
        Instantiate one concrete registration below an optional parent.  The method derives the full hierarchical object name, reuses an already created instance for that exact path, creates a temporary construction context, invokes the dynamically typed dataclass constructor, indexes the instance, and finally materializes all matching child registrations.

        :param registration:
            The registration metadata to process.

        :param parent_instance:
            The concrete parent instance, or None for a root object.

        :return:
            Returns a value of type ``BaseObject``.
        """

        if registration.abstract:
            raise RegistryError(
                f"Abstract registration {registration.name!r} cannot be instantiated."
            )

        # Derive the unique full path from the concrete parent instance.
        object_name = self._build_object_name(
            registration=registration, parent_instance=parent_instance
        )
        if object_name in registration.instances:
            return registration.instances[object_name]
        existing = self._index.exact(object_name)
        if existing is not None:
            raise DuplicateObjectNameError(
                f"Object name {object_name!r} is already used by {type(existing).__module__}.{type(existing).__qualname__}."
            )

        # Emit the creation message through the future object logger. It has no
        # handlers by default and therefore follows normal parent/root logging.
        configured_logger = registration.constructor_kwargs.get("logger_config")
        if isinstance(configured_logger, ObjectLoggerConfig) and isinstance(
            configured_logger.logger_class, type
        ):
            logger_class = configured_logger.logger_class
        elif parent_instance is not None:
            logger_class = parent_instance._resolved_logger_config.logger_class
        else:
            logger_class = ObjectLogger
        construction_logger = _get_object_logger(
            name=object_name, logger_class=logger_class
        )
        construction_logger.debug(
            "Instantiating '%s' from class '%s.%s'.",
            object_name,
            registration.cls.__module__,
            registration.cls.__qualname__,
        )

        # Publish framework-owned values only for the duration of this one
        # constructor call. BaseObject.__post_init__ consumes this context.
        context = _ObjectConstructionContext(
            registry=self,
            object_name=object_name,
            registration_name=registration.name,
            abstract=registration.abstract,
            parent=parent_instance,
        )
        token = _construction_context.set(context)

        temporary_masked_values = self._constructor_masked_values(registration)
        for masked_value in temporary_masked_values:
            _sensitive_value_registry().register(masked_value)

        instance: BaseObject | None = None
        attached_to_parent = False
        try:
            # Constructor signatures differ between registered dataclasses. At
            # this dynamic boundary the safe common result type is BaseObject.
            constructor = cast(Callable[..., BaseObject], registration.cls)
            instance = constructor(
                *registration.constructor_args, **registration.constructor_kwargs
            )
            if parent_instance is not None:
                self._attach_new_child(parent_instance, instance)
                attached_to_parent = True
            instance._finalize_framework_initialization()
        except Exception as error:
            if (
                attached_to_parent
                and instance is not None
                and parent_instance is not None
            ):
                if instance in parent_instance._children:
                    parent_instance._children.remove(instance)
            raise RegistryError(
                f"Could not instantiate registration {registration.name!r} as object {object_name!r} using "
                f"{registration.cls.__module__}.{registration.cls.__qualname__}: {error}"
            ) from error
        finally:
            for masked_value in temporary_masked_values:
                _sensitive_value_registry().unregister(masked_value)
            _construction_context.reset(token)

        # Commit the fully initialized instance to all internal indexes only
        # after construction succeeded.
        assert instance is not None
        registration.instances[object_name] = instance
        self._index.add(instance, registration)
        self._instantiate_children(
            parent_instance=instance, parent_registration=registration
        )
        instance.logger.debug("Added %s to all lookup indexes.", instance)

        return instance

    def _instantiate_children(
        self, parent_instance: BaseObject, parent_registration: _ObjectRegistration
    ) -> None:
        """
        Instantiate all registrations that belong below one parent instance.  Concrete parent references match one exact registration. Abstract parent references act as templates and match concrete instances derived from the abstract class. This is what allows template children to be cloned below every concrete implementation of an abstract registration.

        :param parent_instance:
            The concrete parent instance, or None for a root object.

        :param parent_registration:
            The registration metadata belonging to the parent instance.

        :return:
            Returns None.
        """

        # Resolve the current instance's own template parent once. This avoids
        # cloning template children into an object that already represents the
        # same template edge.
        own_parent_registration = self._resolve_parent_registration(parent_registration)

        # Evaluate every concrete definition against the current parent. The
        # registry is definition-driven rather than dependent on import order.
        for child_registration in self._registrations_by_name.values():
            if child_registration.abstract:
                continue
            template_parent = self._resolve_parent_registration(child_registration)
            if template_parent is None:
                continue
            if template_parent.abstract:
                if template_parent is own_parent_registration:
                    continue
                if not isinstance(parent_instance, template_parent.cls):
                    continue
            elif template_parent is not parent_registration:
                continue
            self._instantiate_registration(
                registration=child_registration, parent_instance=parent_instance
            )

    def _validate_all_subclasses_registered(self) -> None:
        """
        Ensure that every loaded ``BaseObject`` subclass uses ``@register``.  The validation runs immediately before the build. It catches forgotten decorators after all definition modules have been imported, while still allowing normal class creation during module import.

        :return:
            Returns None.
        """

        # Collect first so the error can report every forgotten subclass in a
        # single diagnostic instead of failing one class at a time.
        missing: list[type[BaseObject]] = []

        for subclass in self._all_subclasses(BaseObject):
            if subclass not in self._registrations_by_class:
                missing.append(subclass)
        if not missing:
            return
        missing_names = "\n".join(
            f"  - {cls.__module__}.{cls.__qualname__}"
            for cls in sorted(
                missing, key=lambda item: (item.__module__, item.__qualname__)
            )
        )
        raise UnregisteredSubclassError(
            "The following BaseObject subclasses were not registered:\n"
            f"{missing_names}\n"
            "Decorate every subclass with @register(...)."
        )

    def _validate_parent_references(self) -> None:
        """
        Resolve every configured parent reference once before construction.  This provides an early, deterministic error for unknown parent names, classes that were not registered, and unsupported parent reference values.

        :return:
            Returns None.
        """

        for registration in self._registrations_by_name.values():
            self._resolve_parent_registration(registration)

    def _validate_no_parent_loops(self) -> None:
        """
        Detect cycles in the registration-level parent graph.  A depth-first traversal maintains a temporary ``visiting`` set and a completed ``visited`` set. Encountering an entry that is already being visited proves that the parent chain contains a cycle.

        :return:
            Returns None.
        """

        # ``visiting`` contains the active recursion stack; ``visited`` holds
        # registrations whose complete parent chain is already known to be safe.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(_registration: _ObjectRegistration) -> None:
            if _registration.name in visited:
                return
            if _registration.name in visiting:
                raise ObjectTreeLoopError(
                    f"Parent loop detected at registration {_registration.name!r}."
                )
            visiting.add(_registration.name)
            parent = self._resolve_parent_registration(_registration)
            if parent is not None:
                visit(parent)
            visiting.remove(_registration.name)
            visited.add(_registration.name)

        for registration in self._registrations_by_name.values():
            visit(registration)

    @staticmethod
    def _all_subclasses(root_cls: type[BaseObject]) -> tuple[type[BaseObject], ...]:
        """
        Return every direct and indirect subclass of ``BaseObject``.  Python's ``__subclasses__`` typing is not precise enough for some static type checkers, therefore the runtime list is deliberately cast to ``list[type[BaseObject]]`` before traversal.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        result: list[type[BaseObject]] = []
        visited: set[type[BaseObject]] = set()

        def collect(current: type[BaseObject]) -> None:
            subclasses = cast(
                list[type[BaseObject]], cast(object, current.__subclasses__())
            )
            for subclass in subclasses:
                if subclass in visited:
                    continue
                visited.add(subclass)
                result.append(subclass)
                collect(subclass)

        collect(root_cls)

        return tuple(result)

    def _resolve_parent_registration(
        self, registration: _ObjectRegistration
    ) -> _ObjectRegistration | None:
        """
        Resolve a registration's parent reference to registration metadata.  A parent may be omitted, referenced by its registration name, or referenced by the registered class object. The method never returns an instance because it operates on the definition graph before object construction.

        :param registration:
            The registration metadata to process.

        :return:
            Returns a value of type ``_ObjectRegistration | None``.
        """

        # Parent references are definition-level values and intentionally do
        # not depend on whether any object has already been instantiated.
        reference = registration.parent_reference
        if reference is None:
            return None
        if isinstance(reference, str):
            normalized_name = self._normalize_name(reference)
            try:
                return self._registrations_by_name[normalized_name]
            except KeyError:
                raise ParentResolutionError(
                    f"Parent {normalized_name!r} of registration {registration.name!r} is not registered."
                ) from None
        if isinstance(reference, type) and issubclass(reference, BaseObject):
            try:
                return self._registrations_by_class[reference]
            except KeyError:
                raise ParentResolutionError(
                    f"Parent class {reference.__module__}.{reference.__qualname__} "
                    f"of registration {registration.name!r} is not registered."
                ) from None
        raise ParentResolutionError(
            f"Invalid parent reference {reference!r} for registration {registration.name!r}."
        )

    def _get_registration(self, name: str) -> _ObjectRegistration:
        """
        Return registration metadata by its unique registration name.

        :param name:
            The name to process.

        :return:
            Returns a value of type ``_ObjectRegistration``.
        """

        normalized_name = self._normalize_name(name)
        try:
            return self._registrations_by_name[normalized_name]
        except KeyError:
            raise KeyError(f"No registration exists as {normalized_name!r}.") from None

    def _get_registration_by_class(self, cls: type[_T]) -> _ObjectRegistration:
        """
        Return registration metadata for one registered class.  This helper is private because mutable registration metadata is an internal implementation detail and should not be exposed as normal user API.

        :return:
            Returns a value of type ``_ObjectRegistration``.
        """

        try:
            return self._registrations_by_class[cls]
        except KeyError:
            raise KeyError(
                f"Class {cls.__module__}.{cls.__qualname__} is not registered."
            ) from None

    @overload
    def get_by_name(self, name: str) -> BaseObject:
        """
        Return exactly one instantiated object by full name or unique suffix.

        Examples:
            object_registry.get_by_name('app.apache_1', ApacheRoot)
                Returns the uniquely matching ApacheRoot instance.

        :param name:
            The name to process.

        :return:
            Returns a value of type ``BaseObject``.
        """

        ...

    @overload
    def get_by_name(self, name: str, expected_type: type[_T]) -> _T:
        """
        Return exactly one instantiated object by full name or unique suffix.

        Examples:
            object_registry.get_by_name('app.apache_1', ApacheRoot)
                Returns the uniquely matching ApacheRoot instance.

        :param name:
            The name to process.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns a value of type ``_T``.
        """

        ...

    def get_by_name(
        self, name: str, expected_type: type[_T] | None = None
    ) -> BaseObject | _T:
        """
        Return exactly one instantiated object by full name or unique suffix.

        Examples:
            object_registry.get_by_name('app.apache_1', ApacheRoot)
                Returns the uniquely matching ApacheRoot instance.

        :param name:
            The name to process.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns a value of type ``BaseObject | _T``.
        """

        normalized_name = self._normalize_name(name)
        if expected_type is None:
            return self._index.get_by_name(normalized_name)
        return self._index.get_by_name(normalized_name, expected_type)

    @overload
    def find_by_name(self, pattern: str) -> tuple[BaseObject, ...]:
        """
        Find zero or more objects using segment-aware wildcard matching.  ``*`` matches exactly one hierarchy segment, while ``**`` matches zero or more segments. The search also considers every valid suffix path and removes duplicate instances that matched through multiple suffixes.

        Examples:
            object_registry.find_by_name('app.*.static_files', StaticFilesApacheObject)
                Returns all matching static-file objects.

        :param pattern:
            The segment-aware wildcard pattern to match.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        ...

    @overload
    def find_by_name(self, pattern: str, expected_type: type[_T]) -> tuple[_T, ...]:
        """
        Find zero or more objects using segment-aware wildcard matching.  ``*`` matches exactly one hierarchy segment, while ``**`` matches zero or more segments. The search also considers every valid suffix path and removes duplicate instances that matched through multiple suffixes.

        Examples:
            object_registry.find_by_name('app.*.static_files', StaticFilesApacheObject)
                Returns all matching static-file objects.

        :param pattern:
            The segment-aware wildcard pattern to match.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        ...

    def find_by_name(
        self, pattern: str, expected_type: type[_T] | None = None
    ) -> tuple[BaseObject, ...] | tuple[_T, ...]:
        """
        Find zero or more objects using segment-aware wildcard matching.  ``*`` matches exactly one hierarchy segment, while ``**`` matches zero or more segments. The search also considers every valid suffix path and removes duplicate instances that matched through multiple suffixes.

        Examples:
            object_registry.find_by_name('app.*.static_files', StaticFilesApacheObject)
                Returns all matching static-file objects.

        :param pattern:
            The segment-aware wildcard pattern to match.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        normalized_pattern = self._normalize_name(pattern)
        if expected_type is None:
            return self._index.find_by_name(normalized_pattern)
        return self._index.find_by_name(normalized_pattern, expected_type)

    @overload
    def get_class(self, name: str) -> type[BaseObject]:
        """
        Return the registered class for a registration name.  When ``expected_type`` is supplied, the method additionally verifies that the registered class is a subclass of the requested base type.

        :param name:
            The name to process.

        :return:
            Returns the matching class.
        """

        ...

    @overload
    def get_class(self, name: str, expected_type: type[_T]) -> type[_T]:
        """
        Return the registered class for a registration name.  When ``expected_type`` is supplied, the method additionally verifies that the registered class is a subclass of the requested base type.

        :param name:
            The name to process.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns the matching class.
        """

        ...

    def get_class(
        self, name: str, expected_type: type[_T] | None = None
    ) -> type[BaseObject] | type[_T]:
        """
        Return the registered class for a registration name.  When ``expected_type`` is supplied, the method additionally verifies that the registered class is a subclass of the requested base type.

        :param name:
            The name to process.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns the matching class.
        """

        registration = self._get_registration(name)
        cls = registration.cls
        if expected_type is not None and not issubclass(cls, expected_type):
            raise TypeError(
                f"Registered class {cls.__name__} is not a subclass of "
                f"{expected_type.__name__}."
            )
        if expected_type is not None:
            return cls

        return cls

    def get_by_type(self, expected_type: type[_T]) -> tuple[_T, ...]:
        """
        Return all instantiated objects compatible with ``expected_type``.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        return self._index.get_by_type(expected_type)

    def _attach_new_child(self, parent: BaseObject, child: BaseObject) -> None:
        """Attach a newly constructed child before committing registry indexes."""

        if parent._registry is not self or child._registry is not self:
            raise ValueError(
                "Parent and child must belong to the registry performing the attachment."
            )
        if child.parent is not parent:
            raise ValueError(
                "A newly constructed child must reference its construction parent."
            )
        if child in parent._children:
            raise RegistryError(
                f"Object {child.name!r} is already attached to {parent.name!r}."
            )
        parent._children.append(child)

    def _attach_child(self, parent: BaseObject, child: _T) -> _T:
        """
        Attach or move a child while preserving tree, index, and logger state.

        :param parent:
            The parent object, registration, or logger selector.

        :param child:
            The child object to attach or move.

        :return:
            Returns a value of type ``_T``.
        """

        if parent._registry is not self or child._registry is not self:
            raise ValueError(
                "Parent and child must belong to the registry performing the attachment."
            )

        old_parent_name = child.parent.name if child.parent is not None else None
        previous_status = child._status
        object.__setattr__(child, "_status", ObjectStatus.MOVING)

        try:
            with child.logger.context(
                "object.move",
                object_name=child.name,
                old_parent=old_parent_name,
                new_parent=parent.name,
            ):
                # Reject self-parenting and moves that would create a cycle.
                if parent is child:
                    raise ObjectTreeLoopError(
                        f"{child.name!r} cannot be its own parent."
                    )
                current: BaseObject | None = parent
                while current is not None:
                    if current is child:
                        raise ObjectTreeLoopError(
                            f"Attaching {child.name!r} below {parent.name!r} would create a parent loop."
                        )
                    current = current.parent
                if child.parent is parent and child in parent._children:
                    child.logger.debug("%s is already attached to %s.", child, parent)
                    return child

                child.logger.debug("Moving %s to %s.", child, parent)

                # Compute and validate every future subtree name before changing
                # the existing tree or lookup indexes.
                old_parent = child.parent
                old_name = child.name
                new_name = f"{parent.name}.{child.registration_name}"

                # Compute and validate every future subtree name transactionally.
                subtree = (child, *child.children_flat)
                old_names = {id(instance): instance.name for instance in subtree}
                new_names = {
                    id(instance): new_name + instance.name[len(old_name) :]
                    for instance in subtree
                }
                subtree_ids = {id(instance) for instance in subtree}
                for instance in subtree:
                    instance_name = new_names[id(instance)]
                    existing = self._index.exact(instance_name)
                    if existing is not None and id(existing) not in subtree_ids:
                        raise DuplicateObjectNameError(
                            f"Object name {instance_name!r} already exists."
                        )

                # Detach only after the complete target state is proven safe.
                if old_parent is not None and child in old_parent._children:
                    old_parent._children.remove(child)

                # Replace names, parent links, registration indexes, and suffix indexes.
                for instance in subtree:
                    self._index.remove(instance, object_name=old_names[id(instance)])
                with child._unlocked():
                    child.parent = parent
                for instance in subtree:
                    instance_old_name = old_names[id(instance)]
                    instance_new_name = new_names[id(instance)]
                    with instance._unlocked():
                        instance.name = instance_new_name
                    registration = self._index.registration_for(instance)
                    if registration is not None:
                        registration.instances.pop(instance_old_name, None)
                        registration.instances[instance_new_name] = instance
                    self._index.add(instance, registration)
                if child not in parent._children:
                    parent._children.append(child)

                # Re-resolve inherited logger configs and explicit logger parents.
                child._configure_logger_tree()
                child.logger.debug("Attached %s to %s.", child, parent)
                return child
        finally:
            object.__setattr__(child, "_status", previous_status)

    @property
    def built(self) -> bool:
        """
        Report whether the registry has completed a successful build.

        :return:
            Returns True when the condition is satisfied; otherwise, returns False.
        """

        return self._built

    def _registrations(self) -> tuple[_ObjectRegistration, ...]:
        """
        Return an immutable snapshot of all internal registration records.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        return tuple(self._registrations_by_name.values())

    def instances(self) -> tuple[BaseObject, ...]:
        """
        Return an immutable snapshot of all instantiated objects.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        return self._index.instances()

    def root_objects(self) -> tuple[BaseObject, ...]:
        """
        Return all instantiated objects that do not have a parent.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        return tuple(
            instance for instance in self.instances() if instance.parent is None
        )

    def __contains__(self, name: str) -> bool:
        """
        Test whether an exact full object name exists in the registry.

        :param name:
            The name to process.

        :return:
            Returns True when the condition is satisfied; otherwise, returns False.
        """

        return self._normalize_name(name) in self._index

    def _iter_registrations(self) -> Iterator[_ObjectRegistration]:
        """
        Iterate over registration records in registration order.

        :return:
            Returns an iterator over the requested values.
        """

        return iter(self._registrations_by_name.values())

    @classmethod
    def _build_object_name(
        cls, registration: _ObjectRegistration, parent_instance: BaseObject | None
    ) -> str:
        """
        Build a full object name from a registration and optional parent.

        :param registration:
            The registration metadata to process.

        :param parent_instance:
            The concrete parent instance, or None for a root object.

        :return:
            Returns a value of type ``str``.
        """

        if parent_instance is None:
            return registration.name

        return f"{parent_instance.name}.{registration.name}"

    def _reset_instances(self) -> None:
        """
        Discard every partially or fully created instance and clear indexes.  This rollback helper is used after a failed build so a later diagnostic run starts from a clean registry state.

        :return:
            Returns None.
        """

        # Break tree references first, then clear per-registration instances
        # and all global lookup indexes.
        for instance in self._index.instances():
            instance._unregister_masked_fields()
            instance._children.clear()
        for registration in self._registrations_by_name.values():
            registration.instances.clear()
        self._index.clear()
        self._built = False

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        Trim and validate a registration name, object name, or pattern.

        :param name:
            The name to process.

        :return:
            Returns a value of type ``str``.
        """

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Name cannot be empty.")

        return normalized_name


# The singleton is the supported entry point for lookups. Creating additional
# registry instances is intentionally not part of the public API.
object_registry = _ObjectRegistry(validate_all_subclasses=True)
_bind_registry_config(object_registry.config)
_bind_sensitive_value_registry(object_registry._sensitive_values)
