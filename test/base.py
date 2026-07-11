"""
Hierarchical dataclass registration and object-tree construction.

The module provides a deliberately small public API:

* ``register`` transforms and records ``BaseObject`` subclasses.
* ``initialize_objects`` validates the complete definition graph and builds it.
* ``object_registry`` offers read-oriented lookup and search operations.
* ``BaseObject`` exposes safe tree navigation and controlled re-parenting.

All implementation details that can corrupt registry state are private. Python
privacy is conventional rather than enforced, but leading underscores and
``__all__`` make the supported API explicit to users, IDEs, and documentation
tools.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import tarfile

from abc import ABC
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, fields
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TypeVar, cast, dataclass_transform, overload, Literal

from rich.logging import RichHandler

from admin_helper.console import AdminHelperConsole
from admin_helper.exceptions import BroadcastException
from admin_helper.settings import AdminHelperSettings

__all__ = [
    "AmbiguousObjectNameError",
    "BaseObject",
    "DuplicateObjectNameError",
    "DuplicateRegistrationNameError",
    "ObjectLogger",
    "ObjectLoggerConfig",
    "LoggerConfigurationError",
    "ObjectTreeLoopError",
    "ParentResolutionError",
    "RegistryError",
    "UnregisteredSubclassError",
    "initialize_objects",
    "is_abstract",
    "object_registry",
    "register",
]


# Generic type variable used to preserve concrete BaseObject subclasses in the
# public lookup, child-access, and decorator APIs.
_T = TypeVar("_T", bound="BaseObject")

# Reserved method names may later be used to constrain or document broadcast
# operations. The collection is private because callers must not mutate global
# framework configuration directly.
_BROADCAST_METHODS: list[str] = []


# ---------------------------------------------------------------------------
# Public object-logger configuration
# ---------------------------------------------------------------------------

class LoggerConfigurationError(RuntimeError):
    """
    Raised when an object logger class or reconfiguration is invalid.

    The exception is separate from registry-construction failures because it
    may also be raised later when user code attempts to reconfigure an already
    initialized object logger.
    """


@dataclass(frozen=True, slots=True)
class ObjectLoggerConfig:
    """
    Declarative logging configuration for one ``BaseObject``.

    The configuration is intentionally independent from Pydantic and global
    application settings. It can therefore be passed directly through the
    ``kwargs`` argument of ``@register`` and reused as a normal dataclass value.

    By default, an object logger has no handlers, uses ``NOTSET`` as its own
    level, and forwards records to its parent object's logger. A root object
    forwards to Python's root logger.

    ``console`` and ``file`` are convenience switches that create fresh handler
    instances for every object. ``handlers`` may additionally contain custom
    handler instances for advanced use cases.
    """

    logger_class: type[ObjectLogger] | None = field(default=None,
                                                    repr=False)
    follow_parent: bool = True
    level: int | str | None = None
    disabled: bool = False

    handlers: tuple[logging.Handler, ...] = field(default_factory=tuple,
                                                  repr=False)
    formatter: logging.Formatter | None = field(default=None,
                                                repr=False)

    console: bool = False
    console_level: int | str | None = None
    console_format: str = "%(message)s"
    console_rich_show_time: bool = True
    console_rich_markup: bool = True
    console_rich_show_level: bool = True
    console_rich_show_path: bool = False

    file: bool = False
    file_path: str | Path | None = None
    file_mode: str = "a"
    file_level: int | str | None = None
    file_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file_max_bytes: int = 0
    file_backup_count: int = 0
    file_encoding: str | None = "utf-8"
    file_delay: bool = False
    file_archive_backup_count: int = 0

    def __post_init__(self) -> None:
        """
        Validate the configured logger implementation.

        ``None`` selects the framework's default ``ObjectLogger``. A custom
        value must be a class and must inherit from ``ObjectLogger`` so the
        framework can rely on the managed-handler and configuration behavior.

        :return: None
        """

        if self.logger_class is None:
            return

        if not isinstance(self.logger_class, type) or not issubclass(self.logger_class, ObjectLogger):
            raise LoggerConfigurationError(f"logger_class must inherit from {ObjectLogger.__name__}, "
                                           f"got {self.logger_class!r}.")

    @property
    def resolved_logger_class(self) -> type[ObjectLogger]:
        """
        Return the configured logger class or the framework default.


        :return: The configured logger class
        """

        return self.logger_class or ObjectLogger


class ObjectLogger(logging.Logger):
    """
    Logger implementation used by every ``BaseObject``.

    The class keeps track only of handlers installed through
    ``ObjectLoggerConfig``. Reconfiguration therefore removes and replaces
    framework-managed handlers without touching handlers installed externally.
    """

    class Formatter(logging.Formatter):
        """
        Preserve Rich markup messages while formatting ordinary log records.
        """

        def format(self,
                   record: logging.LogRecord) -> str:
            if hasattr(record, "markup"):
                return str(record.msg)

            return super().format(record)

    class TarRotatingFileHandler(RotatingFileHandler):
        """
        Rotate log files and optionally archive completed rotations as tar.gz.
        """

        def __init__(self,
                     name: str,
                     filename: str | Path,
                     mode: str = "a",
                     max_bytes: int = 0,
                     backup_count: int = 0,
                     encoding: str | None = None,
                     delay: bool = False,
                     archive_backup_count: int = 0):
            super().__init__(filename=filename,
                             mode=mode,
                             maxBytes=max_bytes,
                             backupCount=backup_count,
                             encoding=encoding,
                             delay=delay)
            self.set_name(name)
            self.archive_backup_count = archive_backup_count
            self.archive_base_filename = self.baseFilename[:self.baseFilename.rfind(".")] if "." in self.baseFilename else self.baseFilename

        def doRollover(self) -> None:
            """
            Rotate the active file and archive a complete backup generation.
            """

            super().doRollover()

            if self.backupCount <= 0 or self.archive_backup_count <= 0:
                return

            backup_log_pattern = self.baseFilename + ".%d"
            backup_logs = [Path(backup_log_pattern % index)
                           for index in range(1, self.backupCount + 1)]
            backup_logs = [log for log in backup_logs if log.exists()]

            if len(backup_logs) < self.backupCount:
                return

            archive_filename_pattern = self.archive_base_filename + "_logs.%d.tar.gz"
            archive_index = 0
            archive_filename = Path(archive_filename_pattern % archive_index)

            while archive_filename.exists():
                archive_index += 1
                archive_filename = Path(archive_filename_pattern % archive_index)

            if archive_index >= self.archive_backup_count:
                oldest_archive = Path(archive_filename_pattern % 0)
                if oldest_archive.exists():
                    os.remove(oldest_archive)
                archive_filename = oldest_archive

            with tarfile.open(archive_filename, "w:gz") as archive:
                for log in backup_logs:
                    archive.add(log, arcname=log.name)
                    os.remove(log)

    def __init__(self,
                 name: str,
                 level: int = logging.NOTSET):
        super().__init__(name=name,
                         level=level)
        self._managed_handlers: list[logging.Handler] = []
        self._object_logger_config: ObjectLoggerConfig | None = None

    def configure(self,
                  config: ObjectLoggerConfig,
                  parent_logger: logging.Logger | None,
                  *,
                  _framework_call: bool = False) -> None:
        """
        Apply one complete object-logger configuration atomically.

        Direct reconfiguration is forbidden after a logger has been configured
        with ``follow_parent=True``. Such loggers are controlled by their object
        hierarchy. The framework itself may refresh them after initialization
        or re-parenting through the private ``_framework_call`` flag.
        """

        if (not _framework_call
                and self._object_logger_config is not None
                and self._object_logger_config.follow_parent):
            raise LoggerConfigurationError(f"Logger {self.name!r} follows its parent and cannot be "
                                           "reconfigured directly. Configure the object at registration "
                                           "time or start it with follow_parent=False.")

        if not isinstance(config, ObjectLoggerConfig):
            raise LoggerConfigurationError(f"config must be an {ObjectLoggerConfig.__name__} instance.")

        for handler in tuple(self._managed_handlers):
            if handler in self.handlers:
                self.removeHandler(handler)
            try:
                handler.close()
            finally:
                self._managed_handlers.remove(handler)

        self.disabled = config.disabled
        self.setLevel(logging.NOTSET if config.level is None else config.level)

        if config.follow_parent:
            self.parent = parent_logger if parent_logger is not None else logging.getLogger()
            self.propagate = True
        else:
            self.parent = None
            self.propagate = False

        configured_handlers: list[logging.Handler] = []

        if config.console and not config.disabled:
            console_handler = RichHandler(console=AdminHelperConsole,
                                          show_time=config.console_rich_show_time,
                                          markup=config.console_rich_markup,
                                          show_level=config.console_rich_show_level,
                                          show_path=config.console_rich_show_path)
            console_handler.set_name(self.name)
            if config.console_level is not None:
                console_handler.setLevel(config.console_level)
            console_handler.setFormatter(self.Formatter(config.console_format))
            configured_handlers.append(console_handler)

        if config.file and not config.disabled:
            if config.file_path is None:
                raise ValueError(f"File logging is enabled for {self.name!r}, but file_path is not set.")

            file_path = Path(config.file_path)
            if not file_path.parent.exists():
                raise FileNotFoundError(f"Log file parent directory does not exist: {file_path.parent!s}")

            file_handler = self.TarRotatingFileHandler(name=self.name,
                                                       filename=file_path,
                                                       mode=config.file_mode,
                                                       max_bytes=config.file_max_bytes,
                                                       backup_count=config.file_backup_count,
                                                       encoding=config.file_encoding,
                                                       delay=config.file_delay,
                                                       archive_backup_count=config.file_archive_backup_count)
            if config.file_level is not None:
                file_handler.setLevel(config.file_level)
            file_handler.setFormatter(self.Formatter(config.file_format))
            configured_handlers.append(file_handler)

        for handler in config.handlers:
            if config.formatter is not None:
                handler.setFormatter(config.formatter)
            configured_handlers.append(handler)

        for handler in configured_handlers:
            self.addHandler(handler)
            self._managed_handlers.append(handler)

        self._object_logger_config = config


def _get_object_logger(name: str,
                       logger_class: type[ObjectLogger] = ObjectLogger) -> ObjectLogger:
    """
    Return the requested ``ObjectLogger`` subclass without changing the
    application's global logger class permanently.
    """

    if not isinstance(logger_class, type) or not issubclass(logger_class, ObjectLogger):
        raise LoggerConfigurationError(f"logger_class must inherit from {ObjectLogger.__name__}, "
                                       f"got {logger_class!r}.")

    existing = logging.Logger.manager.loggerDict.get(name)
    if isinstance(existing, logger_class):
        return existing
    if isinstance(existing, logging.Logger):
        raise LoggerConfigurationError(f"Logger {name!r} already exists as {type(existing).__name__}, "
                                       f"not {logger_class.__name__}.")

    previous_logger_class = logging.getLoggerClass()
    logging.setLoggerClass(logger_class)
    try:
        logger = logging.getLogger(name)
    finally:
        logging.setLoggerClass(previous_logger_class)

    if not isinstance(logger, logger_class):
        raise LoggerConfigurationError(f"Could not create {logger_class.__name__} {name!r}.")

    return logger


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------

class RegistryError(RuntimeError):
    """
    Base exception for registry definition, validation, and build errors.
    """


class DuplicateRegistrationNameError(RegistryError):
    """
    Raised when two class definitions use the same registration name.
    """


class DuplicateObjectNameError(RegistryError):
    """
    Raised when two instantiated nodes would receive the same full path.
    """


class AmbiguousObjectNameError(RegistryError):
    """
    Raised when a shortened object path identifies multiple instances.
    """


class UnregisteredSubclassError(RegistryError):
    """
    Raised when a loaded BaseObject subclass was not decorated.
    """


class ParentResolutionError(RegistryError):
    """
    Raised when a configured parent reference cannot be resolved.
    """


class ObjectTreeLoopError(RegistryError):
    """
    Raised when a registration or runtime parent relationship forms a cycle.
    """



# ---------------------------------------------------------------------------
# Private registration metadata
# ---------------------------------------------------------------------------

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
    constructor_kwargs: dict[str, Any] = field(default_factory=dict)

    # One template registration may create multiple instances below different
    # concrete parents, therefore instances are indexed by full object path.
    instances: dict[str, BaseObject] = field(default_factory=dict)

    @property
    def instantiated(self) -> bool:
        return bool(self.instances)


@dataclass(frozen=True, slots=True)
class _ConstructionContext:
    """
    Per-construction data passed safely through nested dataclass calls.
    """

    registration: _ObjectRegistration
    object_name: str
    parent: BaseObject | None


# The context variable prevents constructor metadata from becoming public
# dataclass parameters and remains safe across threads and asynchronous tasks.
_construction_context: ContextVar[_ConstructionContext | None] = ContextVar("base_object_construction_context", default=None)



# ---------------------------------------------------------------------------
# Private registry implementation
# ---------------------------------------------------------------------------

class _ObjectRegistry:
    """
    Own registration metadata, instances, indexes, and tree consistency.
    """

    def __init__(self) -> None:
        """
        Initialize all internal indexes and lifecycle flags.

        The registry stores registrations separately from instantiated objects. All
        mutable dictionaries remain private so callers cannot bypass validation,
        name uniqueness checks, or tree consistency rules.
        """

        self._registrations_by_name: dict[str, _ObjectRegistration] = {}
        self._registrations_by_class: dict[type[BaseObject], _ObjectRegistration] = {}
        self._instances_by_name: dict[str, BaseObject] = {}
        self._instances_by_path: dict[str, list[BaseObject]] = {}
        self._instance_registrations: dict[int, _ObjectRegistration] = {}
        self._building = False
        self._built = False

    def _register(self,
                  *,
                  name: str,
                  cls: type[_T],
                  abstract: bool,
                  parent: _ParentReference = None,
                  constructor_args: tuple[Any, ...] = (),
                  constructor_kwargs: Mapping[str, Any] | None = None) -> type[_T]:
        """
        Register a decorated ``BaseObject`` subclass.

        This method is intentionally private. User code should use the public
        ``@register(...)`` decorator, which first applies the dataclass transform and
        then delegates to this method.

        The method validates unique registration names, prevents the same class from
        being registered twice, rejects constructor arguments for abstract templates,
        and stores the resulting registration metadata.

        :param name: The name of the decorated class.
        :param cls: The class to register.
        :param abstract: Whether the decorated class is a subclass of ``BaseObject``.
        :param parent: The parent of the decorated class.
        :param constructor_args: Arguments to pass to the decorated class.
        :param constructor_kwargs: Keyword arguments to pass to the decorated class.
        """

        # Step 1: Normalize external input and copy mutable constructor data so
        # callers cannot alter the stored configuration after registration.
        normalized_name = self._normalize_name(name)
        kwargs = dict(constructor_kwargs or {})

        # Step 2: Enforce unique registration names and one registration per
        # class before modifying any registry state.
        if normalized_name in self._registrations_by_name:
            existing = self._registrations_by_name[normalized_name]

            raise DuplicateRegistrationNameError(f"Registration name {normalized_name!r} is already used by "
                                                 f"{existing.cls.__module__}.{existing.cls.__qualname__}.")
        if cls in self._registrations_by_class:
            existing = self._registrations_by_class[cls]
            raise RegistryError(f"Class {cls.__module__}.{cls.__qualname__} is already "
                                f"registered as {existing.name!r}.")

        # Step 3: Abstract registrations are templates, not constructible
        # objects, and therefore cannot own constructor arguments.
        if abstract and (constructor_args or kwargs):
            raise RegistryError(f"Abstract registration {normalized_name!r} cannot have "
                                "constructor arguments.")

        # Step 4: Store the validated definition in both lookup indexes.
        registration = _ObjectRegistration(name=normalized_name,
                                           cls=cls,
                                           abstract=abstract,
                                           parent_reference=parent,
                                           constructor_args=constructor_args,
                                           constructor_kwargs=kwargs)
        self._registrations_by_name[normalized_name] = registration
        self._registrations_by_class[cls] = registration

        # Step 5: Mirror the abstract marker on the class for cheap inspection
        # before instances exist, then preserve the decorated class type.
        cls._abstract = abstract

        # No object instance exists during registration. Use the future local
        # object logger name so the message participates in the same logging
        # namespace without adding handlers of its own.
        _get_object_logger(normalized_name).debug("Registered %s.%s as %s (abstract=%s, parent=%r)",
                                                  cls.__module__,
                                                  cls.__qualname__,
                                                  normalized_name,
                                                  abstract,
                                                  parent)

        return cls

    def instantiate_all(self) -> None:
        """
        Validate the complete registry and instantiate every concrete root.

        The build runs only once. It first verifies that every ``BaseObject`` subclass
        was decorated, that all parent references resolve, and that the registration
        graph has no cycles. Concrete root registrations are then instantiated; their
        children are created recursively from the registered parent relationships.

        :return: None
        """

        # Guard against recursive builds and make repeated successful calls
        # idempotent.
        if self._building:
            raise RegistryError("The object registry is already being built.")
        if self._built:
            return
        self._building = True
        registry_logger = logging.getLogger("object_registry")
        registry_logger.debug("Starting object-registry validation and construction")
        try:
            # Validate the complete definition graph before creating the first
            # object, so configuration errors cannot leave a partial tree.
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
                self._instantiate_registration(registration=registration, parent_instance=None)
            self._built = True
            registry_logger.debug("Object registry built successfully with %d instances", len(self._instances_by_name))
        except Exception:
            # Roll back every object and index created during a failed build.
            registry_logger.exception("Object registry build failed; rolling back created instances")
            self._reset_instances()
            raise
        finally:
            self._building = False

    def _instantiate_registration(self,
                                  registration: _ObjectRegistration,
                                  parent_instance: BaseObject | None) -> BaseObject:
        """
        Instantiate one concrete registration below an optional parent.

        The method derives the full hierarchical object name, reuses an already
        created instance for that exact path, creates a temporary construction context,
        invokes the dynamically typed dataclass constructor, indexes the instance, and
        finally materializes all matching child registrations.

        :param registration: The registration to instantiate.
        :param parent_instance: The parent registration to instantiate.
        :return: The instantiated object.
        """

        if registration.abstract:
            raise RegistryError(f"Abstract registration {registration.name!r} cannot be instantiated.")

        # Derive the unique full path from the concrete parent instance.
        object_name = self._build_object_name(registration=registration, parent_instance=parent_instance)
        if object_name in registration.instances:
            return registration.instances[object_name]
        if object_name in self._instances_by_name:
            existing = self._instances_by_name[object_name]
            raise DuplicateObjectNameError(f"Object name {object_name!r} is already used by {type(existing).__module__}.{type(existing).__qualname__}.")

        # Emit the creation message through the future object logger. It has no
        # handlers by default and therefore follows normal parent/root logging.
        configured_logger = registration.constructor_kwargs.get("logger_config")
        logger_class = (configured_logger.resolved_logger_class
                        if isinstance(configured_logger, ObjectLoggerConfig)
                        else ObjectLogger)
        construction_logger = _get_object_logger(name=object_name,
                                                 logger_class=logger_class)
        construction_logger.debug("Instantiating object %s from %s.%s",
                                  object_name,
                                  registration.cls.__module__,
                                  registration.cls.__qualname__)

        # Publish framework-owned values only for the duration of this one
        # constructor call. BaseObject.__post_init__ consumes this context.
        context = _ConstructionContext(registration=registration, object_name=object_name, parent=parent_instance)
        token = _construction_context.set(context)

        try:
            # Constructor signatures differ between registered dataclasses. At
            # this dynamic boundary the safe common result type is BaseObject.
            constructor = cast(Callable[..., BaseObject], registration.cls)
            instance = constructor(*registration.constructor_args, **registration.constructor_kwargs)
        except Exception as error:
            raise RegistryError(f"Could not instantiate registration {registration.name!r} as object {object_name!r} using "
                                f"{registration.cls.__module__}.{registration.cls.__qualname__}: {error}") from error
        finally:
            _construction_context.reset(token)

        # Commit the fully initialized instance to all internal indexes only
        # after construction succeeded.
        registration.instances[object_name] = instance
        self._index_instance(instance)
        self._instance_registrations[id(instance)] = registration
        self._instantiate_children(parent_instance=instance, parent_registration=registration)
        instance.logger.debug("Registered instantiated object %s in all lookup indexes", instance.name)

        return instance

    def _instantiate_children(self,
                              parent_instance: BaseObject,
                              parent_registration: _ObjectRegistration) -> None:
        """
        Instantiate all registrations that belong below one parent instance.

        Concrete parent references match one exact registration. Abstract parent
        references act as templates and match concrete instances derived from the
        abstract class. This is what allows template children to be cloned below every
        concrete implementation of an abstract registration.

        :param parent_instance: The parent registration to instantiate.
        :param parent_registration: The parent registration to instantiate.
        :return: None
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
            self._instantiate_registration(registration=child_registration, parent_instance=parent_instance)

    def _validate_all_subclasses_registered(self) -> None:
        """
        Ensure that every loaded ``BaseObject`` subclass uses ``@register``.

        The validation runs immediately before the build. It catches forgotten
        decorators after all definition modules have been imported, while still
        allowing normal class creation during module import.

        :return: None
        """

        # Collect first so the error can report every forgotten subclass in a
        # single diagnostic instead of failing one class at a time.
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
                                        "Decorate every subclass with @register(...).")

    def _validate_parent_references(self) -> None:
        """
        Resolve every configured parent reference once before construction.

        This provides an early, deterministic error for unknown parent names, classes
        that were not registered, and unsupported parent reference values.

        :return: None
        """

        for registration in self._registrations_by_name.values():
            self._resolve_parent_registration(registration)

    def _validate_no_parent_loops(self) -> None:
        """
        Detect cycles in the registration-level parent graph.

        A depth-first traversal maintains a temporary ``visiting`` set and a completed
        ``visited`` set. Encountering an entry that is already being visited proves
        that the parent chain contains a cycle.

        :return: None
        """

        # ``visiting`` contains the active recursion stack; ``visited`` holds
        # registrations whose complete parent chain is already known to be safe.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(_registration: _ObjectRegistration) -> None:
            if _registration.name in visited:
                return
            if _registration.name in visiting:
                raise ObjectTreeLoopError(f"Parent loop detected at registration {_registration.name!r}.")
            visiting.add(_registration.name)
            parent = self._resolve_parent_registration(_registration)
            if parent is not None:
                visit(parent)
            visiting.remove(_registration.name)
            visited.add(_registration.name)

        for registration in self._registrations_by_name.values():
            visit(registration)

    @staticmethod
    def _all_subclasses(cls: type[BaseObject]) -> tuple[type[BaseObject], ...]:
        """
        Return every direct and indirect subclass of ``BaseObject``.

        Python's ``__subclasses__`` typing is not precise enough for some static type
        checkers, therefore the runtime list is deliberately cast to
        ``list[type[BaseObject]]`` before traversal.

        :param cls: The class to inspect.
        :return: A tuple of the subclasses.
        """

        result: list[type[BaseObject]] = []
        visited: set[type[BaseObject]] = set()

        def collect(current: type[BaseObject]) -> None:
            subclasses = cast(list[type[BaseObject]], cast(object, current.__subclasses__()))
            for subclass in subclasses:
                if subclass in visited:
                    continue
                visited.add(subclass)
                result.append(subclass)
                collect(subclass)

        collect(cls)

        return tuple(result)

    def _resolve_parent_registration(self,
                                     registration: _ObjectRegistration) -> _ObjectRegistration | None:
        """
        Resolve a registration's parent reference to registration metadata.

        A parent may be omitted, referenced by its registration name, or referenced by
        the registered class object. The method never returns an instance because it
        operates on the definition graph before object construction.

        :param registration: The registration to resolve.
        :return: The parent registration or None if no parent registration was found.
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
                raise ParentResolutionError(f"Parent {normalized_name!r} of registration {registration.name!r} is not registered.") from None
        if isinstance(reference, type) and issubclass(reference, BaseObject):
            try:
                return self._registrations_by_class[reference]
            except KeyError:
                raise ParentResolutionError(f"Parent class {reference.__module__}.{reference.__qualname__} "
                                            f"of registration {registration.name!r} is not registered.") from None
        raise ParentResolutionError(f"Invalid parent reference {reference!r} for registration {registration.name!r}.")

    def _get_registration(self,
                          name: str) -> _ObjectRegistration:
        """
        Return registration metadata by its unique registration name.

        :param name: The unique registration name.
        :return: The registration or None if no registration was found.
        """

        normalized_name = self._normalize_name(name)
        try:
            return self._registrations_by_name[normalized_name]
        except KeyError:
            raise KeyError(f"No registration exists as {normalized_name!r}.") from None

    def _get_registration_by_class(self,
                                   cls: type[_T]) -> _ObjectRegistration:
        """
        Return registration metadata for one registered class.

        This helper is private because mutable registration metadata is an internal
        implementation detail and should not be exposed as normal user API.

        :param cls: The class to inspect.
        :return: The registration or None if no registration was found.
        """

        try:
            return self._registrations_by_class[cls]
        except KeyError:
            raise KeyError(f"Class {cls.__module__}.{cls.__qualname__} is not registered.") from None

    @overload
    def get_by_name(self,
                    name: str) -> BaseObject:
        """
        Return exactly one instantiated object by full name or unique suffix.

        Examples:
            ``app.apache_1.static_files`` resolves by its full path.
            ``apache_1.static_files`` resolves by a unique path suffix.
            ``static_files`` resolves only when that suffix identifies exactly one
            object, optionally after filtering by ``expected_type``.

        A missing object raises ``KeyError`` and an ambiguous suffix raises
        ``AmbiguousObjectNameError``.

        :param name: The full name to resolve.
        :return: The object or None if no object was found.
        """

        ...

    @overload
    def get_by_name(self,
                    name: str,
                    expected_type: type[_T]) -> _T:
        """
        Return exactly one instantiated object by full name or unique suffix.

        Examples:
            ``app.apache_1.static_files`` resolves by its full path.
            ``apache_1.static_files`` resolves by a unique path suffix.
            ``static_files`` resolves only when that suffix identifies exactly one
            object, optionally after filtering by ``expected_type``.

        A missing object raises ``KeyError`` and an ambiguous suffix raises
        ``AmbiguousObjectNameError``.

        :param name: The full name to resolve.
        :param expected_type: The expected type of the object.
        :return: The object or None if no object was found.
        """

        ...

    def get_by_name(self,
                    name: str,
                    expected_type: type[_T] | None = None) -> BaseObject | _T:
        """
        Return exactly one instantiated object by full name or unique suffix.

        Examples:
            ``app.apache_1.static_files`` resolves by its full path.
            ``apache_1.static_files`` resolves by a unique path suffix.
            ``static_files`` resolves only when that suffix identifies exactly one
            object, optionally after filtering by ``expected_type``.

        A missing object raises ``KeyError`` and an ambiguous suffix raises
        ``AmbiguousObjectNameError``.

        :param name: The full name to resolve.
        :param expected_type: The expected type of the object.
        :return: The object or None if no object was found.
        """

        # Prefer an exact full-path lookup because it is always unambiguous.
        normalized_name = self._normalize_name(name)
        instance = self._instances_by_name.get(normalized_name)
        if instance is None:
            # Fall back to the suffix index, optionally narrowing ambiguous
            # names with the caller-provided expected type.
            matching_instances = self._instances_by_path.get(normalized_name, [])
            if expected_type is not None:
                matching_instances = [matching_instance
                                      for matching_instance in matching_instances
                                      if isinstance(matching_instance, expected_type)]
            if not matching_instances:
                raise KeyError(f"No instantiated object exists as {normalized_name!r}.")
            if len(matching_instances) > 1:
                matching_names = tuple(matching_instance.name for matching_instance in matching_instances)
                raise AmbiguousObjectNameError(f"Object name {normalized_name!r} is ambiguous. "
                                               f"Matching objects: {matching_names!r}.")
            instance = matching_instances[0]

        if expected_type is not None and not isinstance(instance, expected_type):
            raise TypeError(f"Object {instance.name!r} contains {type(instance).__name__}, not {expected_type.__name__}.")

        return instance

    @overload
    def find_by_name(self,
                     pattern: str) -> tuple[BaseObject, ...]:
        """
        Find zero or more objects using segment-aware wildcard matching.

        ``*`` matches exactly one hierarchy segment, while ``**`` matches zero or more
        segments. The search also considers every valid suffix path and removes
        duplicate instances that matched through multiple suffixes.

        Examples:
            ``app.*.static_files`` matches one segment between ``app`` and
            ``static_files``.
            ``**.static_files`` matches ``static_files`` at any depth.
            Passing ``StaticFilesApacheObject`` returns a statically typed tuple of
            that concrete type.

        :param pattern: The wildcard pattern to match.
        :return: The object or None if no object was found.
        """

        ...

    @overload
    def find_by_name(self,
                     pattern: str,
                     expected_type: type[_T]) -> tuple[_T, ...]:
        """
        Find zero or more objects using segment-aware wildcard matching.

        ``*`` matches exactly one hierarchy segment, while ``**`` matches zero or more
        segments. The search also considers every valid suffix path and removes
        duplicate instances that matched through multiple suffixes.

        Examples:
            ``app.*.static_files`` matches one segment between ``app`` and
            ``static_files``.
            ``**.static_files`` matches ``static_files`` at any depth.
            Passing ``StaticFilesApacheObject`` returns a statically typed tuple of
            that concrete type.

        :param pattern: The wildcard pattern to match.
        :param expected_type: The expected type of the object.
        :return: The object or None if no object was found.
        """

        ...

    def find_by_name(self,
                     pattern: str,
                     expected_type: type[_T] | None = None) -> tuple[BaseObject, ...] | tuple[_T, ...]:
        """
        Find zero or more objects using segment-aware wildcard matching.

        ``*`` matches exactly one hierarchy segment, while ``**`` matches zero or more
        segments. The search also considers every valid suffix path and removes
        duplicate instances that matched through multiple suffixes.

        Examples:
            ``app.*.static_files`` matches one segment between ``app`` and
            ``static_files``.
            ``**.static_files`` matches ``static_files`` at any depth.
            Passing ``StaticFilesApacheObject`` returns a statically typed tuple of
            that concrete type.

        :param pattern: The wildcard pattern to match.
        :param expected_type: The expected type of the object.
        :return: The object or None if no object was found.
        """

        # Search every indexed suffix so callers may omit leading ancestors.
        normalized_pattern = self._normalize_name(pattern)

        # Build a new immutable snapshot rather than exposing the mutable child
        # lists owned by registry internals.
        result: list[BaseObject] = []

        # One instance may match through multiple suffixes; identity-based
        # de-duplication guarantees that it appears only once in the result.
        visited: set[int] = set()
        for object_path, instances in self._instances_by_path.items():
            if not self._match_object_path(object_name=object_path, pattern=normalized_pattern):
                continue
            for instance in instances:
                identity = id(instance)
                if identity in visited:
                    continue
                if expected_type is not None and not isinstance(instance, expected_type):
                    continue
                visited.add(identity)
                result.append(instance)
        if expected_type is not None:
            return cast(tuple[_T, ...], cast(object, tuple(result)))

        return tuple(result)

    @overload
    def get_class(self,
                  name: str) -> type[BaseObject]:
        """
        Return the registered class for a registration name.

        When ``expected_type`` is supplied, the method additionally verifies that the
        registered class is a subclass of the requested base type.

        :param name: The registration name to match.
        :return: The object or None if no object was found.
        """

        ...

    @overload
    def get_class(self,
                  name: str,
                  expected_type: type[_T]) -> type[_T]:
        """
        Return the registered class for a registration name.

        When ``expected_type`` is supplied, the method additionally verifies that the
        registered class is a subclass of the requested base type.

        :param name: The registration name to match.
        :param expected_type: The class to match.
        :return: The object or None if no object was found.
        """

        ...

    def get_class(self,
                  name: str,
                  expected_type: type[_T] | None = None) -> type[BaseObject] | type[_T]:
        """
        Return the registered class for a registration name.

        When ``expected_type`` is supplied, the method additionally verifies that the
        registered class is a subclass of the requested base type.

        :param name: The registration name to match.
        :param expected_type: The class to match.
        :return: The object or None if no object was found.
        """

        registration = self._get_registration(name)
        cls = registration.cls
        if expected_type is not None and not issubclass(cls, expected_type):
            raise TypeError(f"Registered class {cls.__name__} is not a subclass of "
                            f"{expected_type.__name__}.")
        if expected_type is not None:
            return cls

        return cls

    def get_by_type(self,
                    expected_type: type[_T]) -> tuple[_T, ...]:
        """
        Return all instantiated objects compatible with ``expected_type``.

        :param expected_type: The class to match.
        :return: The object or None if no object was found.
        """

        return tuple(instance for instance in self._instances_by_name.values() if isinstance(instance, expected_type))

    def _children_of(self,
                     parent: BaseObject) -> tuple[BaseObject, ...]:
        """
        Return a read-only tuple view of one object's direct children.

        :param parent: The parent object.
        :return: The object or None if no object was found.
        """

        return tuple(parent._children)

    def _get_child_by_name(self,
                           parent: BaseObject,
                           name: str) -> BaseObject | None:
        """
        Resolve a descendant path relative to one parent object.

        The supplied name may be relative, such as ``routes.static_files``, or already
        start with the parent's complete path. Only objects below the supplied parent
        are accepted.

        :param parent: The parent object.
        :param name: The name to match.
        :return: The object or None if no object was found.
        """

        # Convert relative descendant paths into an exact full path below the
        # selected parent while accepting an already-qualified path as well.
        normalized_name = self._normalize_name(name)
        if normalized_name.startswith(f"{parent.name}."):
            full_name = normalized_name
        else:
            full_name = f"{parent.name}.{normalized_name}"
        obj = self._instances_by_name.get(full_name)
        if obj is None:
            return None
        current = obj.parent
        while current is not None:
            if current is parent:
                return obj
            current = current.parent

        return None

    def _get_children_by_type(self,
                              parent: BaseObject,
                              expected_type: type[_T]) -> tuple[_T, ...]:
        """
        Return direct children compatible with ``expected_type``.

        :param parent: The parent object.
        :param expected_type: The class to match.
        :return: The object or None if no object was found.
        """

        return tuple(child for child in self._children_of(parent) if isinstance(child, expected_type))

    def _attach_child(self,
                      parent: BaseObject,
                      child: _T) -> _T:
        """
        Attach or move a child object while preserving registry consistency.

        The method rejects cycles, removes the object from its previous parent, checks
        all renamed subtree paths for collisions, updates the full names of the child
        and every descendant, refreshes all search indexes, and finally links the child
        to the new parent.

        It is private because directly moving tree nodes is a privileged operation;
        callers should use ``BaseObject.add_child``.

        :param parent: The parent object.
        :param child: The child object.
        :return: The new child object.
        """

        # Reject self-parenting and any move that would place an ancestor below
        # one of its own descendants.
        if parent is child:
            raise ObjectTreeLoopError(f"{child.name!r} cannot be its own parent.")
        current: BaseObject | None = parent
        while current is not None:
            if current is child:
                raise ObjectTreeLoopError(f"Attaching {child.name!r} below {parent.name!r} would create a parent loop.")
            current = current.parent
        if child.parent is parent and child in parent._children:
            child.logger.debug("Object %s is already attached to parent %s", child.name, parent.name)
            return child

        child.logger.debug("Preparing to move object %s below parent %s", child.name, parent.name)

        # Detach from the previous parent only after the target relationship is
        # proven cycle-free.
        old_parent = child.parent
        if old_parent is not None and child in old_parent._children:
            old_parent._children.remove(child)
        old_name = child.name
        new_name = f"{parent.name}.{child.registration_name}"

        # Moving one node changes the full path of its entire subtree. Compute
        # every old and new path before changing state.
        subtree = (child, *child.children_flat)
        old_names = {id(instance): instance.name for instance in subtree}
        new_names = {id(instance): new_name + instance.name[len(old_name):] for instance in subtree}
        subtree_ids = {id(instance) for instance in subtree}

        # Validate all future names as one transaction before unindexing or
        # mutating a single object.
        for instance in subtree:
            instance_name = new_names[id(instance)]
            existing = self._instances_by_name.get(instance_name)
            if existing is not None and id(existing) not in subtree_ids:
                raise DuplicateObjectNameError(f"Object name {instance_name!r} already exists.")

        # Remove stale search entries, update protected fields under the private
        # lock override, then rebuild registration and path indexes.
        for instance in subtree:
            self._unindex_instance(instance, object_name=old_names[id(instance)])
        with child._unlocked():
            child.parent = parent
        for instance in subtree:
            instance_old_name = old_names[id(instance)]
            instance_new_name = new_names[id(instance)]
            with instance._unlocked():
                instance.name = instance_new_name
            registration = self._instance_registrations.get(id(instance))
            if registration is not None:
                registration.instances.pop(instance_old_name, None)
                registration.instances[instance_new_name] = instance
            self._index_instance(instance)
        if child not in parent._children:
            parent._children.append(child)

        # Recreate the explicit logger-parent links for the renamed subtree.
        # This also moves local handlers and formatter configuration onto the
        # logger objects associated with the new hierarchical names.
        child._configure_logger_tree()
        child.logger.debug("Attached object %s below parent %s", child.name, parent.name)

        return child

    @property
    def built(self) -> bool:
        """
        Report whether the registry has completed a successful build.

        :return: Whether the registry has completed a successful build.
        """

        return self._built

    def _registrations(self) -> tuple[_ObjectRegistration, ...]:
        """
        Return an immutable snapshot of all internal registration records.

        :return: An immutable snapshot of all internal registration records.
        """

        return cast(tuple[_ObjectRegistration, ...], cast(object, tuple(self._registrations_by_name.values())))

    def instances(self) -> tuple[BaseObject, ...]:
        """
        Return an immutable snapshot of all instantiated objects.

        :return: An immutable snapshot of all instantiated objects.
        """

        return cast(tuple[BaseObject, ...], cast(object, tuple(self._instances_by_name.values())))

    def root_objects(self) -> tuple[BaseObject, ...]:
        """
        Return all instantiated objects that do not have a parent.

        :return: An immutable snapshot of all instantiated objects.
        """

        return tuple(instance for instance in self.instances() if instance.parent is None)

    def __contains__(self,
                     name: str) -> bool:
        """
        Test whether an exact full object name exists in the registry.

        :param name: The exact full object name to test.
        :return: Whether an exact full object name exists in the registry.
        """

        return self._normalize_name(name) in self._instances_by_name

    def _iter_registrations(self) -> Iterator[_ObjectRegistration]:
        """
        Iterate over registration records in registration order.

        :return: An immutable snapshot of all registration records.
        """

        return iter(self._registrations_by_name.values())

    def _index_instance(self,
                        instance: BaseObject) -> None:
        """
        Add an instance to the exact-name and suffix-path indexes.

        :param instance: The instance to index.
        :return: None
        """

        # The exact-name index provides O(1) full-path lookups.
        self._instances_by_name[instance.name] = instance

        # The suffix index supports shortened paths and wildcard searches.
        for object_path in self._get_object_name_paths(instance.name):
            path_instances = self._instances_by_path.setdefault(object_path, [])
            if not any(path_instance is instance for path_instance in path_instances):
                path_instances.append(instance)

    def _unindex_instance(self,
                          instance: BaseObject,
                          object_name: str | None = None) -> None:
        """
        Remove an instance from all indexes for one previously used name.

        :param instance: The instance to unindex.
        :param object_name: The object name to unindex.
        :return: None
        """

        indexed_name = object_name or instance.name
        if self._instances_by_name.get(indexed_name) is instance:
            del self._instances_by_name[indexed_name]
        for object_path in self._get_object_name_paths(indexed_name):
            path_instances = self._instances_by_path.get(object_path)
            if path_instances is None:
                continue
            self._instances_by_path[object_path] = [path_instance
                                                    for path_instance in path_instances
                                                    if path_instance is not instance]
            path_instances = self._instances_by_path[object_path]
            if not path_instances:
                del self._instances_by_path[object_path]

    @staticmethod
    def _get_object_name_paths(object_name: str) -> tuple[str, ...]:
        """
        Build every addressable suffix for one hierarchical object name.

        For ``app.apache.routes`` the result is
        ``('app.apache.routes', 'apache.routes', 'routes')``.

        :param object_name: The hierarchical object name to build.
        :return: A tuple of the addressable suffixes for ``object_name``.
        """

        name_parts = object_name.split(".")
        return tuple(".".join(name_parts[index:]) for index in range(len(name_parts)))

    @staticmethod
    def _match_object_path(object_name: str,
                           pattern: str) -> bool:
        """
        Match one dot-separated object path against a wildcard pattern.

        Matching is segment based: ordinary shell wildcards are applied inside one
        segment, ``*`` therefore cannot cross a dot, and the special segment ``**``
        can consume any number of hierarchy levels.

        :param object_name: The hierarchical object name to match.
        :param pattern: The wildcard pattern to match.
        :return: Whether the pattern matches ``object_name``.
        """

        # Split on hierarchy boundaries so ordinary fnmatch wildcards cannot
        # accidentally cross from one object name segment into another.
        object_parts = object_name.split(".")
        pattern_parts = pattern.split(".")

        def match(object_index: int,
                  pattern_index: int) -> bool:
            """
            Recursively compare object-path and pattern segments.

            :param object_index: The hierarchical object index to match.
            :param pattern_index: The wildcard pattern to match.
            :return: Whether the pattern matches ``object_index``.
            """

            if pattern_index == len(pattern_parts):
                return object_index == len(object_parts)
            pattern_part = pattern_parts[pattern_index]
            if pattern_part == "**":
                if pattern_index == len(pattern_parts) - 1:
                    return True
                for next_object_index in range(object_index, len(object_parts) + 1):
                    if match(next_object_index, pattern_index + 1):
                        return True
                return False
            if object_index >= len(object_parts):
                return False
            if not fnmatch.fnmatchcase(object_parts[object_index], pattern_part):
                return False
            return match(object_index + 1, pattern_index + 1)

        return match(0, 0)

    @classmethod
    def _build_object_name(cls,
                           registration: _ObjectRegistration,
                           parent_instance: BaseObject | None) -> str:
        """
        Build a full object name from a registration and optional parent.
        :param registration: The registration to build the object name from.
        :param parent_instance: The parent instance to build the object name from.
        :return: The full object name to build the object name from.
        """

        if parent_instance is None:
            return registration.name

        return f"{parent_instance.name}.{registration.name}"

    def _reset_instances(self) -> None:
        """
        Discard every partially or fully created instance and clear indexes.

        This rollback helper is used after a failed build so a later diagnostic run
        starts from a clean registry state.

        :return: None
        """

        # Break tree references first, then clear per-registration instances
        # and all global lookup indexes.
        for instance in self._instances_by_name.values():
            instance._children.clear()
        for registration in self._registrations_by_name.values():
            registration.instances.clear()
        self._instances_by_name.clear()
        self._instances_by_path.clear()
        self._instance_registrations.clear()
        self._built = False

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        Trim and validate a registration name, object name, or pattern.

        :param name: The registration name to normalize.
        """

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Name cannot be empty.")

        return normalized_name



# The singleton is the supported entry point for lookups. Creating additional
# registry instances is intentionally not part of the public API.
object_registry = _ObjectRegistry()



# ---------------------------------------------------------------------------
# Public object base class
# ---------------------------------------------------------------------------

@dataclass
class BaseObject(ABC):
    """
    Base class for every registered node in the hierarchical object tree.

    Framework-managed attributes are initialized by the registry and protected
    against reassignment after construction. Subclasses only declare their own
    dataclass fields and behavior.
    """

    # Public read-only framework attributes.
    #
    # These names are intentionally public because users need them for normal
    # inspection and navigation. The custom frozen metadata prevents replacing
    # them after initialization.
    name: str = field(init=False,
                      metadata={"frozen": True})
    logger: ObjectLogger = field(init=False,
                                 repr=False,
                                 metadata={"frozen": True})
    parent: BaseObject | None = field(default=None,
                                      init=False,
                                      repr=False,
                                      metadata={"frozen": True})

    # Public logger configuration.
    #
    # One immutable configuration object keeps the dataclass API compact and
    # allows complete logger profiles to be passed through @register kwargs.
    logger_config: ObjectLoggerConfig = field(default_factory=ObjectLoggerConfig,
                                              repr=False,
                                              kw_only=True)

    # Private mutable framework state.
    #
    # Direct access would bypass locking, indexing, or tree validation, so every
    # field is hidden behind safe properties and registry operations.
    _initialized: bool = field(default=False,
                               init=False,
                               repr=False)
    _children: list[BaseObject] = field(default_factory=list,
                                        init=False,
                                        repr=False)
    _abstract: bool = field(default=False,
                            init=False,
                            repr=False,
                            metadata={"frozen": True})
    _registration_name: str = field(init=False,
                                    repr=False,
                                    metadata={"frozen": True})

    def __post_init__(self) -> None:
        """
        Finalize a registry-created dataclass instance.

        The method reads the active construction context, assigns immutable framework
        attributes, creates the hierarchical logger, rejects accidental construction
        of abstract templates, attaches the object to its parent, and finally enables
        the custom frozen-field protection.

        :return: None
        """

        # Direct construction is forbidden because framework-owned attributes
        # and registry indexes would otherwise be missing or inconsistent.
        context = _construction_context.get()
        if context is None:
            raise RuntimeError(f"{type(self).__module__}.{type(self).__qualname__} must be instantiated through _ObjectRegistry.instantiate_all().")

        # Copy all immutable framework values without triggering the custom
        # __setattr__ guard, which is enabled only at the end.
        registration = context.registration
        object.__setattr__(self, "_initialized", False)
        object.__setattr__(self, "name", context.object_name)
        object.__setattr__(self, "parent", context.parent)
        object.__setattr__(self, "_abstract", registration.abstract)
        object.__setattr__(self, "_registration_name", registration.name)

        # Reject abstract templates before creating any runtime tree links.
        if self._abstract:
            raise AttributeError(f"Object {self.name!r} is abstract and cannot be instantiated.")

        # Create and configure the object logger before attaching the node. The
        # logger starts without handlers and forwards records to its parent by
        # default. Root loggers forward to Python's root logger.
        self._configure_logger()
        self.logger.debug("Initializing object %s", self.name)

        # Link the object into the runtime tree before enabling frozen-field
        # protection. The registry also keeps all indexes synchronized.
        if self.parent is not None:
            object_registry._attach_child(self.parent, self)
        object.__setattr__(self, "_initialized", True)
        self.logger.debug("Initialized object %s", self.name)

    def __setattr__(self,
                    key: str,
                    value: Any) -> None:
        """
        Prevent changes to dataclass fields marked with ``metadata={'frozen': True}``.

        The protection is enabled only after framework initialization. Internal code
        can temporarily disable it through the private ``_unlocked`` context manager.

        :param key: The field name to change.
        :param value: The field value to change.
        :return: None
        """

        # Before initialization, dataclass and framework assignments must pass.
        # Afterwards, only fields explicitly marked frozen are protected.
        initialized = getattr(self, "_initialized", False)
        if initialized and key == "logger_config":
            current_config = getattr(self, "logger_config", None)
            if isinstance(current_config, ObjectLoggerConfig) and current_config.follow_parent:
                raise LoggerConfigurationError(f"Logger {self.name!r} follows its parent and its logger_config "
                                               "cannot be replaced at runtime. Configure it through @register(...) "
                                               "or initialize it with follow_parent=False.")
            if not isinstance(value, ObjectLoggerConfig):
                raise LoggerConfigurationError(f"logger_config must be an {ObjectLoggerConfig.__name__} instance.")

        if initialized:
            dataclass_field = next((dataclass_field for dataclass_field in fields(self) if dataclass_field.name == key), None)
            if dataclass_field is not None and dataclass_field.metadata.get("frozen", False):
                raise AttributeError(f"Field {dataclass_field.name!r} is frozen and cannot be modified.")

        super().__setattr__(key, value)

        # Logger configuration fields are intentionally mutable. Reapply the
        # complete configuration after each change so parent linkage, level,
        # handlers, and formatter can never drift apart.
        if initialized and key == "logger_config":
            self._configure_logger_tree()

    def _configure_logger(self) -> None:
        """
        Create or refresh this object's logger from ``logger_config``.

        A default configuration installs no handlers and forwards records to
        the parent object's logger. Root objects forward to Python's root
        logger. Replacing ``logger_config`` after initialization automatically
        reapplies the complete configuration to this object and its descendants.

        :return: None
        """

        previous_logger = getattr(self, "logger", None)
        logger = _get_object_logger(name=self.name,
                                    logger_class=self.logger_config.resolved_logger_class)

        # A renamed object receives another named logger. Clear the previous
        # framework-managed configuration before switching references.
        if isinstance(previous_logger, ObjectLogger) and previous_logger is not logger:
            previous_logger.configure(ObjectLoggerConfig(follow_parent=False,
                                                         disabled=True),
                                      parent_logger=None,
                                      _framework_call=True)

        object.__setattr__(self, "logger", logger)
        logger.configure(config=self.logger_config,
                         parent_logger=self.parent.logger if self.parent is not None else None,
                         _framework_call=True)
        logger.debug("Configured object logger %s: follow_parent=%s, level=%s, handlers=%d",
                     logger.name,
                     self.logger_config.follow_parent,
                     logging.getLevelName(logger.level),
                     len(logger.handlers))

    def _configure_logger_tree(self) -> None:
        """
        Refresh this logger and every descendant logger.

        Descendant refresh is required after re-parenting because object names
        and explicit ``logging.Logger.parent`` references may both change.

        :return: None
        """

        self._configure_logger()
        for child in self._children:
            child._configure_logger_tree()

    @contextmanager
    def _unlocked(self) -> Iterator[BaseObject]:
        """
        Temporarily disable the custom frozen-field guard.

        The previous lock state is restored in ``finally`` even when an exception is
        raised. This method is private and reserved for registry-maintained updates.

        :return: A context manager that temporarily disables the frozen-field guard.
        """

        # Save and restore the prior state to support safe nesting.
        previous_state = self._initialized
        object.__setattr__(self, "_initialized", False)
        try:
            yield self
        finally:
            object.__setattr__(self, "_initialized", previous_state)

    @property
    def registration_name(self) -> str:
        """
        Return the stable local registration name without parent prefixes.

        :return: The stable local registration name without parent prefixes.
        """

        return self._registration_name

    @property
    def root_parent(self) -> BaseObject:
        """
        Return the highest parent in this object's hierarchy.

        A defensive identity set detects corrupted runtime cycles even though normal
        registry operations already prevent them.

        :return: The highest parent in this object's hierarchy.
        """

        # Walk upward iteratively and retain a defensive identity set in case
        # external code corrupted the supposedly protected parent links.
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
        """
        Return direct children as an immutable tuple.
        :return: Direct children as an immutable tuple.
        """

        return object_registry._children_of(self)

    @property
    def children_flat(self) -> tuple[BaseObject, ...]:
        """
        Return every descendant in depth-first order as an immutable tuple.
        :return: Every descendant in depth-first order as an immutable tuple.
        """

        result: list[BaseObject] = []
        visited: set[int] = set()

        def collect(parent: BaseObject) -> None:
            for child in object_registry._children_of(parent):
                identity = id(child)
                if identity in visited:
                    raise ObjectTreeLoopError(f"Child loop detected below {self.name!r}.")
                visited.add(identity)
                result.append(child)
                collect(child)

        collect(self)
        return tuple(result)

    def add_child(self,
                  obj: _T) -> _T:
        """
        Attach an existing registered object below this object.

        The registry performs loop detection, collision checks, recursive renaming,
        and search-index maintenance. The method returns the attached object with its
        concrete type preserved.

        :param obj: The object to be attached.
        :return: The attached object.
        """

        # Reject arbitrary objects before delegating the privileged tree update
        # to the registry.
        if not isinstance(obj, BaseObject):
            raise TypeError(f"{obj!r} is not an instance of BaseObject.")

        return object_registry._attach_child(self, obj)

    @overload
    def get_child_by_name(self,
                          name: str) -> BaseObject | None:
        """
        Return one descendant by a path relative to this object.

        The method returns ``None`` when no matching descendant exists. Supplying
        ``expected_type`` preserves the concrete return type and raises ``TypeError``
        when the located child has another type.

        :param name: The name of the descendant to be returned.
        :return: The attached object.
        """

        ...

    @overload
    def get_child_by_name(self,
                          name: str,
                          expected_type: type[_T]) -> _T | None:
        """
        Return one descendant by a path relative to this object.

        The method returns ``None`` when no matching descendant exists. Supplying
        ``expected_type`` preserves the concrete return type and raises ``TypeError``
        when the located child has another type.

        :param name: The name of the descendant to be returned.
        :param expected_type: The expected type of the descendant to be returned.
        :return: The attached object.
        """

        ...

    def get_child_by_name(self,
                          name: str,
                          expected_type: type[_T] | None = None) -> BaseObject | _T | None:
        """
        Return one descendant by a path relative to this object.

        The method returns ``None`` when no matching descendant exists. Supplying
        ``expected_type`` preserves the concrete return type and raises ``TypeError``
        when the located child has another type.

        :param name: The name of the descendant to be returned.
        :param expected_type: The expected type of the descendant to be returned.
        :return: The attached object.
        """

        # Resolve relative to this node; no global ambiguous-suffix search is
        # performed for child navigation.
        child = object_registry._get_child_by_name(self, name)
        if child is None:
            return None
        if expected_type is not None and not isinstance(child, expected_type):
            raise TypeError(f"Child {name!r} is {type(child).__name__}, not {expected_type.__name__}.")

        return child

    def get_child_by_type(self,
                          expected_type: type[_T]) -> tuple[_T, ...]:
        """
        Return all direct children compatible with ``expected_type``.

        :param expected_type: The expected type of the direct children to be returned.
        :return: The direct children compatible with ``expected_type``.
        """

        return object_registry._get_children_by_type(self, expected_type)

    def broadcast_call(self,
                       _method_name: str,
                       _wrap_errors: bool = not AdminHelperSettings.debug,
                       _stop_on_error: bool = True,
                       **method_kwargs: Any) -> list[Any]:
        """
        Call one method across the child tree.

        Each direct child receives the method call when it implements the named
        method. Otherwise the request is forwarded recursively to that child's
        children. Errors may be re-raised immediately or wrapped in
        ``BroadcastException`` according to the supplied flags.

        :param _method_name: The name of the method to be called.
        :param _wrap_errors: Whether or not to wrap errors during broadcasting.
        :param _stop_on_error: Whether or not to stop broadcasting when an error occurs.
        :param method_kwargs: Additional keyword arguments to be passed to the method.
        :return: The broadcasted results.
        """

        # Process direct children in tree order and preserve every return value
        # for the caller.
        self.logger.debug("Broadcasting %s -> %s", self, _method_name)
        results: list[Any] = []
        for child in self.children:
            method = getattr(child, _method_name, None)
            if callable(method):
                try:
                    results.append(method(**method_kwargs))
                except Exception as error:
                    self.logger.error("Error while broadcasting %s -> %s: %s", self, _method_name, error)
                    if not _wrap_errors:
                        raise
                    broadcast_error = BroadcastException(self, _method_name, error)
                    results.append(broadcast_error)
                    if _stop_on_error:
                        broadcast_error.finalize()
                        raise broadcast_error
            else:
                results.append(child.broadcast_call(_method_name=_method_name, _wrap_errors=_wrap_errors, _stop_on_error=_stop_on_error, **method_kwargs))
        if _wrap_errors and not _stop_on_error:
            final_exception: BroadcastException | None = None
            for broadcast_result in results:
                if not isinstance(broadcast_result, BroadcastException):
                    continue
                if final_exception is None:
                    final_exception = BroadcastException()
                final_exception.errors.append(broadcast_result)
            if final_exception is not None:
                final_exception.finalize()
                raise final_exception

        return results



# ---------------------------------------------------------------------------
# Public helper functions and decorator
# ---------------------------------------------------------------------------

def is_abstract(obj: BaseObject | type[BaseObject] | Any) -> bool:
    """
    Return whether a registered class or object is marked as abstract.

    :param obj: The object to be checked.
    :return: A boolean indicating whether or not the object is abstract.
    """

    if isinstance(obj, type) and issubclass(obj, BaseObject):
        try:
            registration = object_registry._get_registration_by_class(obj)
        except KeyError:
            return bool(getattr(obj, "_abstract", False))
        return registration.abstract

    return bool(getattr(obj, "_abstract", False))


def _default_object_name(cls: type[BaseObject]) -> str:
    """
    Convert a CamelCase class name into the default snake_case name.

    :param cls: The object to be converted.
    :return: The default snake_case class name.
    """

    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()


@overload
def register(*,
             abstract: Literal[True],
             name: str | None = None,
             parent: _ParentReference = None) -> Callable[[type[_T]], type[_T]]:
    """
    Transform and register a ``BaseObject`` subclass as a dataclass.

    Abstract registrations define reusable templates and are never instantiated.
    Concrete registrations may store constructor arguments and an optional parent
    reference. Actual construction is delayed until ``instantiate_all`` runs.

    Examples:
        ``@register(abstract=True, name='service')`` defines a template.
        ``@register(name='app')`` defines a root object.
        ``@register(name='worker', parent=App, kwargs={'enabled': True})`` defines
        a concrete child whose constructor arguments are stored for the build.

    :param abstract: Whether or not to register an abstract class.
    :param name: The name of the class to register.
    :param parent: The parent of the class to register.
    :return: A decorator that registers the class.
    """

    ...


@overload
def register(*,
             abstract: Literal[False] = False,
             name: str | None = None,
             parent: _ParentReference = None,
             args: tuple[Any, ...] = (),
             kwargs: Mapping[str, Any] | None = None) -> Callable[[type[_T]], type[_T]]:
    """
    Transform and register a ``BaseObject`` subclass as a dataclass.

    Abstract registrations define reusable templates and are never instantiated.
    Concrete registrations may store constructor arguments and an optional parent
    reference. Actual construction is delayed until ``instantiate_all`` runs.

    Examples:
        ``@register(abstract=True, name='service')`` defines a template.
        ``@register(name='app')`` defines a root object.
        ``@register(name='worker', parent=App, kwargs={'enabled': True})`` defines
        a concrete child whose constructor arguments are stored for the build.

    :param abstract: Whether or not to register an abstract class.
    :param name: The name of the class to register.
    :param parent: The parent of the class to register.
    :param args: The arguments to register.
    :param kwargs: The keyword arguments to register.
    :return: A decorator that registers the class.
    """

    ...


@dataclass_transform()
def register(*,
             abstract: bool = False,
             name: str | None = None,
             parent: _ParentReference = None,
             args: tuple[Any, ...] = (),
             kwargs: Mapping[str, Any] | None = None) -> Callable[[type[_T]], type[_T]]:
    """
    Transform and register a ``BaseObject`` subclass as a dataclass.

    Abstract registrations define reusable templates and are never instantiated.
    Concrete registrations may store constructor arguments and an optional parent
    reference. Actual construction is delayed until ``instantiate_all`` runs.

    Examples:
        ``@register(abstract=True, name='service')`` defines a template.
        ``@register(name='app')`` defines a root object.
        ``@register(name='worker', parent=App, kwargs={'enabled': True})`` defines
        a concrete child whose constructor arguments are stored for the build.

    :param abstract: Whether or not to register an abstract class.
    :param name: The name of the class to register.
    :param parent: The parent of the class to register.
    :param args: The arguments to register.
    :param kwargs: The keyword arguments to register.
    :return: A decorator that registers the class.
    """

    def decorator(cls: type[_T]) -> type[_T]:
        # Restrict the decorator to the framework hierarchy.
        if not issubclass(cls, BaseObject):
            raise TypeError(f"{cls.__module__}.{cls.__qualname__} must be a subclass of {BaseObject.__name__}.")

        # Copy caller-owned mappings and validate abstract template semantics.
        constructor_kwargs = dict(kwargs or {})
        if abstract and (args or constructor_kwargs):
            raise TypeError(f"Abstract class {cls.__qualname__!r} cannot define constructor arguments.")

        # Apply the runtime dataclass transformation, then record its delayed
        # construction metadata in the singleton registry.
        dataclass_cls = dataclass(cls)
        return object_registry._register(name=name or _default_object_name(dataclass_cls),
                                         cls=dataclass_cls,
                                         abstract=abstract,
                                         parent=parent,
                                         constructor_args=args,
                                         constructor_kwargs=constructor_kwargs)

    return decorator



# ---------------------------------------------------------------------------
# Example object definitions
# ---------------------------------------------------------------------------

# Registration messages are emitted before object instances and their handlers
# exist. The example therefore configures Python's root logger first so those
# early framework messages are visible as well. In a real application this
# belongs in the executable entry point before importing object-definition
# modules.
def _configure_example_bootstrap_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if any(handler.get_name() == "example-bootstrap-console"
           for handler in root_logger.handlers):
        return

    console_handler = RichHandler(console=AdminHelperConsole,
                                  show_time=True,
                                  markup=True,
                                  show_level=True,
                                  show_path=False)
    console_handler.set_name("example-bootstrap-console")
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(ObjectLogger.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)


# Create the directory before handler construction. ObjectLoggerConfig never
# creates directories implicitly because a misspelled path should fail loudly.
_EXAMPLE_LOG_DIRECTORY = Path("logs")
_EXAMPLE_LOG_DIRECTORY.mkdir(parents=True,
                             exist_ok=True)

_configure_example_bootstrap_logging()

class ApacheObjectLogger(ObjectLogger):
    """Example custom logger class accepted by ObjectLoggerConfig."""

    def apache_event(self,
                     message: str,
                     *args: Any) -> None:
        self.info("[apache] " + message, *args)


# The root object owns the central console and application-file handlers.
# ``follow_parent=False`` prevents duplicate output through Python's root logger
# after the object tree has been initialized. All descendants use their default
# configuration and therefore forward records to this logger.
_APP_LOGGER_CONFIG = ObjectLoggerConfig(follow_parent=False,
                                        level=logging.DEBUG,
                                        console=True,
                                        console_level=logging.DEBUG,
                                        console_format="%(message)s",
                                        file=True,
                                        file_path=_EXAMPLE_LOG_DIRECTORY / "application.log",
                                        file_level=logging.DEBUG,
                                        file_format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                                        file_max_bytes=1_000_000,
                                        file_backup_count=3,
                                        file_archive_backup_count=2)

# This profile is used only by ``apache_2``. Its records are written to a
# dedicated rotating file and still propagate to App, so they also appear in
# the central console and application.log.
_APACHE_2_LOGGER_CONFIG = ObjectLoggerConfig(logger_class=ApacheObjectLogger,
                                             follow_parent=True,
                                             level=logging.DEBUG,
                                             file=True,
                                             file_path=_EXAMPLE_LOG_DIRECTORY / "apache_2.log",
                                             file_level=logging.DEBUG,
                                             file_format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                                             file_max_bytes=500_000,
                                             file_backup_count=2,
                                             file_archive_backup_count=2)

@register(abstract=True,
          name="apache_object")
class ApacheObject(BaseObject):
    enabled: bool


@register(name="static_files",
          parent=ApacheObject,
          kwargs={"enabled": True,
                  "url_path": "/static",
                  "directory": "/var/www/static"})
class StaticFilesApacheObject(ApacheObject):
    url_path: str
    directory: str


@register(name="reverse_proxy",
          parent=ApacheObject,
          kwargs={"enabled": True,
                  "source": "/api",
                  "target": "http://127.0.0.1:8000"})
class ReverseProxyApacheObject(ApacheObject):
    source: str
    target: str


@register(name="app",
          kwargs={"logger_config": _APP_LOGGER_CONFIG})
class App(BaseObject):
    ...


@register(name="apache_1",
          parent=App,
          kwargs={"enabled": True,
                  "config_file": "/etc/apache2/httpd.conf"})
class ApacheRoot(ApacheObject):
    config_file: str


@register(name="apache_2",
          parent=App,
          kwargs={"enabled": False,
                  "config_file": "/tmp/apache2.conf",
                  "logger_config": _APACHE_2_LOGGER_CONFIG})
class SecondApacheRoot(ApacheObject):
    config_file: str



# ---------------------------------------------------------------------------
# Application bootstrap and usage examples
# ---------------------------------------------------------------------------

def initialize_objects() -> None:
    """Build and validate the global object registry once.
    """
    object_registry.instantiate_all()


if __name__ == "__main__":
    initialize_objects()

    apache_1 = object_registry.get_by_name("app.apache_1", ApacheRoot)
    apache_2 = object_registry.get_by_name("apache_2", SecondApacheRoot)

    static_files_1_a = object_registry.get_by_name("app.apache_1.static_files", StaticFilesApacheObject)
    static_files_2_a = object_registry.get_by_name("apache_2.static_files", StaticFilesApacheObject)


    static_files_1_b = apache_1.get_child_by_name("static_files", StaticFilesApacheObject)
    static_files_2_b = apache_2.get_child_by_name("static_files", StaticFilesApacheObject)

    static_files_1_c = object_registry.find_by_name("app.*.static_files", StaticFilesApacheObject)
    static_files_2_c = object_registry.find_by_name("**.static_files", StaticFilesApacheObject)

    # All of these messages reach the App console and application.log because
    # the child loggers follow their parent by default.
    apache_1.logger.debug("Apache 1 debug message through the central logger configuration")
    static_files_1_a.logger.info("Static-files information through the central logger configuration")

    # apache_2 additionally writes to logs/apache_2.log through its local file
    # handler, while propagation still forwards the same record to App.
    apache_2.logger.warning("Apache 2 warning written centrally and to its dedicated file")

    # apache_2 uses the custom logger class configured at registration time.
    if isinstance(apache_2.logger, ApacheObjectLogger):
        apache_2.logger.apache_event("Custom ApacheObjectLogger method called for %s", apache_2.name)

    # A logger that follows its parent is hierarchy-managed. Runtime replacement
    # of its complete configuration therefore raises LoggerConfigurationError.
    try:
        static_files_2_a.logger_config = ObjectLoggerConfig(follow_parent=False,
                                                            level=logging.DEBUG)
    except LoggerConfigurationError as error:
        static_files_2_a.logger.warning("Expected logger reconfiguration error: %s", error)

    print()