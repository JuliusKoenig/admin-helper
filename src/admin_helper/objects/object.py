from __future__ import annotations

import logging
import os

from abc import ABC
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import MISSING, fields as dataclass_fields
from typing import TYPE_CHECKING, Any, TypeVar, overload

from admin_helper.exceptions import (
    BroadcastException,
    LoggerConfigurationError,
    ObjectTreeLoopError,
)
from admin_helper.objects.config import (
    LoggerParent,
    ObjectLoggerConfig,
    ObjectStatus,
    SensitiveValueFilterMode,
    _ResolvedObjectLoggerConfig,
)
from admin_helper.objects.construction import (
    _ObjectConstructionContext,
    _construction_context,
)
from admin_helper.objects.field import _field_info, field, fields, object_dataclass
from admin_helper.objects.formatting import _format_display_value
from admin_helper.objects.logger import ObjectLogger, _get_object_logger
from admin_helper.objects.runtime import _masking_framework_config
from admin_helper.objects.sensitive_value_registry import _sensitive_value_registry

if TYPE_CHECKING:
    from admin_helper.objects.registry import _ObjectRegistry

# Generic type variable used to preserve concrete BaseObject subclasses in the
# public lookup, child-access, and decorator APIs.
_T = TypeVar("_T", bound="BaseObject")

# Reserved method names may later be used to constrain or document broadcast
# operations. The collection is private because callers must not mutate global
# framework configuration directly.
_BROADCAST_METHODS: list[str] = []


@object_dataclass
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
    # inspection and navigation. The custom read_only metadata prevents replacing
    # them after initialization.
    name: str = field(
        read_only=True, init=False, title="Name", description="The name of the object."
    )
    logger: ObjectLogger = field(
        read_only=True,
        init=False,
        repr=False,
        title="Logger",
        description="The logger of the object.",
    )
    parent: BaseObject | None = field(
        read_only=True,
        init=False,
        repr=False,
        default=None,
        title="Parent",
        description="The parent of the object.",
    )

    # Public logger configuration.
    logger_config: ObjectLoggerConfig = field(
        kw_only=True,
        repr=False,
        default_factory=ObjectLoggerConfig,
        title="Logger Configuration",
        description="The configuration for the object's logger.",
    )

    # Private mutable framework state.
    _resolved_logger_config: _ResolvedObjectLoggerConfig = field(
        internal=True,
        init=False,
        title="Resolved logger configuration",
        description="The configuration for the object's logger.",
    )
    _initialized: bool = field(
        internal=True,
        init=False,
        default=False,
        title="Initialized",
        description="Whether the object is initialized.",
    )
    _status: ObjectStatus = field(
        internal=True,
        read_only=True,
        init=False,
        default=ObjectStatus.INITIALIZING,
        title="Status",
        description="The status of the object.",
    )
    _children: list[BaseObject] = field(
        internal=True,
        init=False,
        default_factory=list,
        title="Children",
        description="The children of the object.",
    )
    _abstract: bool = field(
        internal=True,
        read_only=True,
        init=False,
        default=False,
        title="Abstract",
        description="Whether the object is abstract.",
    )
    _registration_name: str = field(
        internal=True,
        read_only=True,
        init=False,
        title="Registration name",
        description="The name of the object.",
    )
    _registry: _ObjectRegistry = field(
        internal=True,
        read_only=True,
        init=False,
        repr=False,
        title="Registry",
        description="The registry that owns the object.",
    )

    def __post_init__(self) -> None:
        """Initialize framework-owned state from the active construction context."""

        context = _construction_context.get()
        if context is None:
            raise RuntimeError(
                f"{type(self).__module__}.{type(self).__qualname__} must be instantiated through _ObjectRegistry.instantiate_all()."
            )
        self._initialize_framework_state(context)

    def _initialize_framework_state(self, context: _ObjectConstructionContext) -> None:
        """Assign object-local framework state without mutating registry indexes."""

        object.__setattr__(self, "_initialized", False)
        object.__setattr__(self, "_status", ObjectStatus.INITIALIZING)
        object.__setattr__(self, "_registry", context.registry)
        object.__setattr__(self, "name", context.object_name)
        object.__setattr__(self, "parent", context.parent)
        object.__setattr__(self, "_abstract", context.abstract)
        object.__setattr__(self, "_registration_name", context.registration_name)

        if self._abstract:
            raise AttributeError(
                f"Object {self.name!r} is abstract and cannot be instantiated."
            )

        configured_logger_config = self.logger_config.copy()
        object.__setattr__(self, "logger_config", configured_logger_config)
        configured_logger_config._bind(self._configure_logger_tree)
        self._configure_logger()
        self.logger.debug("Initializing %s.", self)

    def _finalize_framework_initialization(self) -> None:
        """Enable field protection after the registry committed tree state."""

        object.__setattr__(self, "_initialized", True)
        object.__setattr__(self, "_status", ObjectStatus.READY)
        self._register_masked_fields()
        self.logger.debug("Initialized %s.", self)

    def __str__(self) -> str:
        """Return a concise representation built from display fields."""

        parts = [f"name='{self.name}'"]
        for definition in fields(self, display=True, internal=False):
            if definition.name == "name":
                continue
            try:
                value = definition.get_value(self)
            except Exception:
                continue
            parts.append(
                f"{definition.name}={_format_display_value(value, masked=definition.info.masked, empty_values=definition.info.empty_values)}"
            )
        return f"{type(self).__name__}({', '.join(parts)})"

    def _register_masked_fields(self, *, include_computed: bool | None = None) -> None:
        """Register sensitive values according to the global protection mode."""

        if (
            _masking_framework_config().mode is SensitiveValueFilterMode.DISABLED
            or not _masking_framework_config().enabled
        ):
            return
        if include_computed is None:
            include_computed = (
                _masking_framework_config().mode
                is SensitiveValueFilterMode.FIELDS_AND_COMPUTED
            )
        for definition in fields(
            self, masked=True, computed=None if include_computed else False
        ):
            try:
                value = definition.get_value(self)
            except Exception:
                continue
            _sensitive_value_registry().register(value)

    def _unregister_masked_fields(self) -> None:
        """Remove sensitive values according to the global protection mode."""

        if (
            _masking_framework_config().mode is SensitiveValueFilterMode.DISABLED
            or not _masking_framework_config().enabled
        ):
            return
        include_computed = (
            _masking_framework_config().mode
            is SensitiveValueFilterMode.FIELDS_AND_COMPUTED
        )
        for definition in fields(
            self, masked=True, computed=None if include_computed else False
        ):
            try:
                value = definition.get_value(self)
            except Exception:
                continue
            _sensitive_value_registry().unregister(value)

    def __setattr__(self, key: str, value: Any) -> None:
        """
        Prevent changes to dataclass fields marked with ``metadata={'read_only': True}``.  The protection is enabled only after framework initialization. Internal code can temporarily disable it through the private ``_unlocked`` context manager.

        :param key:
            The attribute or configuration-field name.

        :param value:
            The value to validate or assign.

        :return:
            Returns None.
        """

        # Before initialization, dataclass and framework assignments must pass.
        # Afterwards, only fields explicitly marked read_only are protected.
        initialized = getattr(self, "_initialized", False)
        if key == "logger_config":
            if not isinstance(value, ObjectLoggerConfig):
                raise LoggerConfigurationError(
                    f"logger_config must be an {ObjectLoggerConfig.__name__} instance."
                )
            value = value.copy()
            current_config = getattr(self, "logger_config", None)
            if isinstance(current_config, ObjectLoggerConfig):
                current_config._unbind()

        dataclass_field = None
        previous_masked_value = MISSING
        refresh_all_sensitive_values = (
            initialized
            and _masking_framework_config().mode
            is SensitiveValueFilterMode.FIELDS_AND_COMPUTED
        )

        if initialized:
            dataclass_field = next(
                (
                    dataclass_field
                    for dataclass_field in dataclass_fields(self)
                    if dataclass_field.name == key
                ),
                None,
            )
            if dataclass_field is not None and _field_info(dataclass_field).read_only:
                raise AttributeError(
                    f"Field {dataclass_field.name!r} is read_only and cannot be modified."
                )
            if refresh_all_sensitive_values:
                self._unregister_masked_fields()
            elif dataclass_field is not None and _field_info(dataclass_field).masked:
                previous_masked_value = getattr(self, key, MISSING)

        super().__setattr__(key, value)

        if refresh_all_sensitive_values:
            self._register_masked_fields()
        elif (
            initialized
            and dataclass_field is not None
            and _field_info(dataclass_field).masked
        ):
            if previous_masked_value is not MISSING:
                _sensitive_value_registry().unregister(previous_masked_value)
            _sensitive_value_registry().register(value)

        # Logger configuration fields are intentionally mutable. Reapply the
        # complete configuration after each change so parent linkage, level,
        # handlers, and formatter can never drift apart.
        if key == "logger_config":
            self.logger_config._bind(self._configure_logger_tree)
            if initialized:
                self._configure_logger_tree()

    def _configure_logger(self) -> None:
        """
        Resolve the inheritable configuration and refresh this object's logger.  The parent object's effective config is used only as a configuration source. The actual logging parent is selected independently through ``logger_config.parent``.

        :return:
            Returns None.
        """

        parent_config = (
            self.parent._resolved_logger_config if self.parent is not None else None
        )
        resolved_config = self.logger_config.resolve(parent_config)
        object.__setattr__(self, "_resolved_logger_config", resolved_config)

        previous_logger = getattr(self, "logger", None)
        logger = _get_object_logger(
            name=self.name, logger_class=resolved_config.logger_class
        )

        if isinstance(previous_logger, ObjectLogger) and previous_logger is not logger:
            previous_logger.configure(
                config=ObjectLoggerConfig._framework_defaults(),
                parent_logger=None,
                path_values=self._logger_path_values(),
            )
            previous_logger.disabled = True

        object.__setattr__(self, "logger", logger)
        logger._bind_status_provider(lambda: self.status)
        logger.configure(
            config=resolved_config,
            parent_logger=self._resolve_logger_parent(resolved_config.parent),
            path_values=self._logger_path_values(),
        )
        logger.debug(
            "Configured logger '%s' with level %s and %d handlers.",
            logger.name,
            logging.getLevelName(logger.level),
            len(logger.handlers),
        )

    def _resolve_logger_parent(
        self, parent: LoggerParent | str
    ) -> logging.Logger | None:
        """
        Resolve the configured logging parent independently of config inheritance.

        :param parent:
            The parent object, registration, or logger selector.

        :return:
            Returns a value of type ``logging.Logger | None``.
        """

        if parent is LoggerParent.OBJECT_PARENT:
            return (
                self.parent.logger if self.parent is not None else logging.getLogger()
            )
        if parent is LoggerParent.ROOT:
            return logging.getLogger()
        if parent is LoggerParent.NONE:
            return None
        return logging.getLogger(parent)

    def _logger_path_values(self) -> dict[str, str]:
        """
        Return supported placeholders for file-path templates.

        :return:
            Returns a value of type ``dict[str, str]``.
        """

        parent_name = self.parent.name if self.parent is not None else ""
        root_name = self.root_parent.registration_name
        return {
            "name": self.name,
            "name_path": self.name.replace(".", os.sep),
            "registration_name": self.registration_name,
            "parent_name": parent_name,
            "parent_path": parent_name.replace(".", os.sep),
            "root_name": root_name,
        }

    def _configure_logger_tree(self) -> None:
        """
        Refresh this logger and every descendant inside one logging context.

        :return:
            Returns None.
        """

        logger = getattr(self, "logger", None)
        if isinstance(logger, ObjectLogger):
            with logger.context("logger.reconfigure", object_name=self.name):
                self._configure_logger_subtree()
        else:
            self._configure_logger_subtree()

    def _configure_logger_subtree(self) -> None:
        """
        Reconfigure this subtree while exposing ``RECONFIGURING`` status.

        :return:
            Returns None.
        """

        previous_status = self._status
        object.__setattr__(self, "_status", ObjectStatus.RECONFIGURING)
        try:
            self._configure_logger()
            for child in self._children:
                child._configure_logger_subtree()
        finally:
            object.__setattr__(self, "_status", previous_status)

    @contextmanager
    def _unlocked(self) -> Iterator[BaseObject]:
        """
        Temporarily disable the custom read_only-field guard.  The previous lock state is restored in ``finally`` even when an exception is raised. This method is private and reserved for registry-maintained updates.

        :return:
            Returns an iterator over the requested values.
        """

        # Save and restore the prior state to support safe nesting.
        previous_state = self._initialized
        object.__setattr__(self, "_initialized", False)
        try:
            yield self
        finally:
            object.__setattr__(self, "_initialized", previous_state)

    @property
    def status(self) -> ObjectStatus:
        """
        Return the framework-managed lifecycle state of this object.

        :return:
            Returns a value of type ``ObjectStatus``.
        """

        return self._status

    @contextmanager
    def logging_context(self, name: str, **values: Any) -> Iterator[BaseObject]:
        """
        Open a dynamic logging context and yield this object for convenience.

        Examples:
            with obj.logging_context('apache.reload', virtual_host='example.org'):
                obj.logger.info('Reloading the virtual host.')

        :param name:
            The name to process.

        :param values:
            The 'values' value used by the operation.

        :return:
            Returns an iterator over the requested values.
        """

        with self.logger.context(name, **values):
            yield self

    @property
    def registration_name(self) -> str:
        """
        Return the stable local registration name without parent prefixes.

        :return:
            Returns a value of type ``str``.
        """

        return self._registration_name

    @property
    def root_parent(self) -> BaseObject:
        """
        Return the highest parent in this object's hierarchy.  A defensive identity set detects corrupted runtime cycles even though normal registry operations already prevent them.

        :return:
            Returns a value of type ``BaseObject``.
        """

        # Walk upward iteratively and retain a defensive identity set in case
        # external code corrupted the supposedly protected parent links.
        current = self
        visited: set[int] = set()
        while current.parent is not None:
            identity = id(current)
            if identity in visited:
                raise ObjectTreeLoopError(
                    f"Parent loop detected while resolving root of {self.name!r}."
                )
            visited.add(identity)
            current = current.parent

        return current

    @property
    def children(self) -> tuple[BaseObject, ...]:
        """
        Return direct children as an immutable tuple.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        return tuple(self._children)

    @property
    def children_flat(self) -> tuple[BaseObject, ...]:
        """
        Return every descendant in depth-first order as an immutable tuple.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        result: list[BaseObject] = []
        visited: set[int] = set()

        def collect(parent: BaseObject) -> None:
            for child in parent._children:
                identity = id(child)
                if identity in visited:
                    raise ObjectTreeLoopError(
                        f"Child loop detected below {self.name!r}."
                    )
                visited.add(identity)
                result.append(child)
                collect(child)

        collect(self)
        return tuple(result)

    def add_child(self, obj: _T) -> _T:
        """
        Attach an existing registered object below this object.  The registry performs loop detection, collision checks, recursive renaming, and search-index maintenance. The method returns the attached object with its concrete type preserved.

        Examples:
            new_parent.add_child(child)
                Moves the child and its complete subtree below the new parent.

        :param obj:
            The object to inspect or attach.

        :return:
            Returns a value of type ``_T``.
        """

        # Reject arbitrary objects before delegating the privileged tree update
        # to the registry.
        if not isinstance(obj, BaseObject):
            raise TypeError(f"{obj!r} is not an instance of BaseObject.")

        if self._registry is not obj._registry:
            raise ValueError(
                "Parent and child must belong to the same object registry."
            )

        return self._registry._attach_child(self, obj)

    @overload
    def get_child_by_name(self, name: str) -> BaseObject | None:
        """
        Return one descendant by a path relative to this object.  The method returns ``None`` when no matching descendant exists. Supplying ``expected_type`` preserves the concrete return type and raises ``TypeError`` when the located child has another type.

        :param name:
            The name to process.

        :return:
            Returns the matching object, or None when no object matches.
        """

        ...

    @overload
    def get_child_by_name(self, name: str, expected_type: type[_T]) -> _T | None:
        """
        Return one descendant by a path relative to this object.  The method returns ``None`` when no matching descendant exists. Supplying ``expected_type`` preserves the concrete return type and raises ``TypeError`` when the located child has another type.

        :param name:
            The name to process.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns a value of type ``_T | None``.
        """

        ...

    def get_child_by_name(
        self, name: str, expected_type: type[_T] | None = None
    ) -> BaseObject | _T | None:
        """
        Return one descendant by a path relative to this object.  The method returns ``None`` when no matching descendant exists. Supplying ``expected_type`` preserves the concrete return type and raises ``TypeError`` when the located child has another type.

        :param name:
            The name to process.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns the matching object, or None when no object matches.
        """

        # Resolve relative to this node; no global ambiguous-suffix search is
        # performed for child navigation.
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Name cannot be empty.")
        full_name = (
            normalized_name
            if normalized_name.startswith(f"{self.name}.")
            else f"{self.name}.{normalized_name}"
        )
        child = next(
            (
                descendant
                for descendant in self.children_flat
                if descendant.name == full_name
            ),
            None,
        )
        if child is None:
            return None
        if expected_type is not None and not isinstance(child, expected_type):
            raise TypeError(
                f"Child {name!r} is {type(child).__name__}, not {expected_type.__name__}."
            )

        return child

    def get_child_by_type(self, expected_type: type[_T]) -> tuple[_T, ...]:
        """
        Return all direct children compatible with ``expected_type``.

        :param expected_type:
            The type used to validate or filter returned objects.

        :return:
            Returns an immutable tuple containing the requested values.
        """

        return tuple(
            child for child in self._children if isinstance(child, expected_type)
        )

    def broadcast_call(
        self,
        _method_name: str,
        _wrap_errors: bool = not False,  # ToDo: configure this default value with something like debug mode
        _stop_on_error: bool = True,
        **method_kwargs: Any,
    ) -> list[Any]:
        """
        Call one method across the child tree inside a broadcast context.

        Examples:
            root.broadcast_call('reload', force=True)
                Calls reload on matching descendants and returns their results.

        :param _method_name:
            The descendant method name to broadcast.

        :param _wrap_errors:
            Whether raised errors are wrapped in BroadcastException.

        :param _stop_on_error:
            Whether broadcasting stops after the first error.

        :param method_kwargs:
            The keyword arguments forwarded to the broadcast method.

        :return:
            Returns a value of type ``list[Any]``.
        """

        previous_status = self._status
        object.__setattr__(self, "_status", ObjectStatus.BROADCASTING)
        try:
            with self.logger.context(
                "broadcast",
                method=_method_name,
                stop_on_error=_stop_on_error,
                wrap_errors=_wrap_errors,
            ):
                self.logger.debug(
                    "Broadcasting method '%s' from %s.", _method_name, self
                )
                results: list[Any] = []
                for child in self.children:
                    method = getattr(child, _method_name, None)
                    if callable(method):
                        try:
                            results.append(method(**method_kwargs))
                        except Exception as error:
                            self.logger.error(
                                "Broadcasting method '%s' from %s failed with %s!",
                                _method_name,
                                self,
                                error,
                            )
                            if not _wrap_errors:
                                raise
                            broadcast_error = BroadcastException(
                                self, _method_name, error
                            )
                            results.append(broadcast_error)
                            if _stop_on_error:
                                broadcast_error.finalize()
                                raise broadcast_error
                    else:
                        results.append(
                            child.broadcast_call(
                                _method_name=_method_name,
                                _wrap_errors=_wrap_errors,
                                _stop_on_error=_stop_on_error,
                                **method_kwargs,
                            )
                        )
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
        finally:
            object.__setattr__(self, "_status", previous_status)
