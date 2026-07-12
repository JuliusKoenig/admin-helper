import logging
from _contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass, field as dataclass_field, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Any, Iterator, Mapping, TYPE_CHECKING

from admin_helper.exceptions import LoggerConfigurationError
from admin_helper.field import DEFAULT_MASKED_FIELD_VALUE, DEFAULT_NOT_SET_FIELD_VALUE, DEFAULT_EMPTY_FIELD_VALUES

if TYPE_CHECKING:
    from admin_helper.logger import ObjectLogger


class LoggerConfigValue(Enum):
    """Special values used by inheritable logger-configuration attributes."""

    INHERIT = "inherit"
    AUTO = "auto"


class LoggerParent(Enum):
    """Special values for selecting the actual ``logging.Logger.parent``."""

    OBJECT_PARENT = "object_parent"
    ROOT = "root"
    NONE = "none"


class RegistryConfigChange(Enum):
    """Identify runtime work required after a registry configuration change."""

    FIELD_RENDERING = "field_rendering"
    SENSITIVE_VALUES = "sensitive_values"
    LOGGER_TREE = "logger_tree"
    WARNING_CAPTURE = "warning_capture"


class _ObservableConfig:
    _on_change: Callable[[RegistryConfigChange], None] | None = None
    _change_kind: RegistryConfigChange | None = None
    _ready: bool = False

    def _finish_init(self, on_change: Callable[[RegistryConfigChange], None] | None, change_kind: RegistryConfigChange) -> None:
        object.__setattr__(self, "_on_change", on_change)
        object.__setattr__(self, "_change_kind", change_kind)
        object.__setattr__(self, "_ready", True)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if name.startswith("_") or not getattr(self, "_ready", False):
            return
        callback = getattr(self, "_on_change", None)
        change_kind = getattr(self, "_change_kind", None)
        if callback is not None and change_kind is not None:
            callback(change_kind)


@dataclass(slots=True)
class FieldFrameworkConfig(_ObservableConfig):
    masked_value: str = DEFAULT_MASKED_FIELD_VALUE
    not_set_value: str = DEFAULT_NOT_SET_FIELD_VALUE
    empty_values: tuple[Any, ...] = DEFAULT_EMPTY_FIELD_VALUES

    def __post_init__(self) -> None:
        self._finish_init(None, RegistryConfigChange.FIELD_RENDERING)


class SensitiveValueFilterMode(Enum):
    """Select which sensitive values are cached by the global log filter."""

    DISABLED = "disabled"
    FIELDS = "fields"
    FIELDS_AND_COMPUTED = "fields_and_computed"


@dataclass(slots=True)
class MaskingFrameworkConfig(_ObservableConfig):
    enabled: bool = True
    enforced: bool = False
    console: bool = True
    file: bool = True
    custom_handlers: bool = True
    mode: SensitiveValueFilterMode = SensitiveValueFilterMode.FIELDS

    def __post_init__(self) -> None:
        self._finish_init(None, RegistryConfigChange.SENSITIVE_VALUES)


@dataclass(slots=True)
class WarningFrameworkConfig(_ObservableConfig):
    capture: bool = False
    parent: LoggerParent | str = LoggerParent.ROOT

    def __post_init__(self) -> None:
        self._finish_init(None, RegistryConfigChange.WARNING_CAPTURE)


@dataclass(slots=True)
class LoggingFrameworkConfig:
    masking: MaskingFrameworkConfig = dataclass_field(default_factory=MaskingFrameworkConfig)
    warnings: WarningFrameworkConfig = dataclass_field(default_factory=WarningFrameworkConfig)


class ObjectRegistryConfig:
    def __init__(self, on_change: Callable[[RegistryConfigChange], None]):
        self.fields = FieldFrameworkConfig()
        self.logging = LoggingFrameworkConfig()
        self._on_change = on_change
        self._batch_depth = 0
        self._auto_apply = True
        self._pending: set[RegistryConfigChange] = set()
        self._bind_children()

    def _bind_children(self) -> None:
        self.fields._finish_init(self._mark_changed, RegistryConfigChange.FIELD_RENDERING)
        self.logging.masking._finish_init(self._mark_changed, RegistryConfigChange.SENSITIVE_VALUES)
        self.logging.warnings._finish_init(self._mark_changed, RegistryConfigChange.WARNING_CAPTURE)

    def _mark_changed(self, change: RegistryConfigChange) -> None:
        self._pending.add(change)
        if self._batch_depth == 0 and self._auto_apply:
            self.apply()

    @contextmanager
    def batch_update(self, *, apply: bool = True) -> Iterator["ObjectRegistryConfig"]:
        previous_auto_apply = self._auto_apply
        self._batch_depth += 1
        self._auto_apply = apply
        try:
            yield self
        finally:
            self._batch_depth -= 1
            self._auto_apply = previous_auto_apply
            if self._batch_depth == 0 and apply:
                self.apply()

    def apply(self) -> None:
        order = (RegistryConfigChange.FIELD_RENDERING, RegistryConfigChange.SENSITIVE_VALUES,
                 RegistryConfigChange.WARNING_CAPTURE, RegistryConfigChange.LOGGER_TREE)
        pending = tuple(change for change in order if change in self._pending)
        self._pending.clear()
        for change in pending:
            self._on_change(change)


class ObjectStatus(Enum):
    """Read-only lifecycle state exposed by every ``BaseObject``."""

    INITIALIZING = "initializing"
    READY = "ready"
    RECONFIGURING = "reconfiguring"
    MOVING = "moving"
    BROADCASTING = "broadcasting"


class LoggerContextStatus(Enum):
    """Defined state of a named context entry in ``ObjectLoggerContexts``."""

    UNDEFINED = "undefined"
    INHERIT = "inherit"
    CONFIGURED = "configured"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class _LoggerContextFrame:
    """One dynamically scoped logging context frame."""

    name: str
    values: Mapping[str, Any]


_logger_context_stack: ContextVar[tuple[_LoggerContextFrame, ...]] = ContextVar(
    "object_logger_context_stack",
    default=(),
)


@dataclass(frozen=True, slots=True)
class _ResolvedLoggerContextConfig:
    """Store complete thresholds and formats for one resolved context."""

    disabled: bool
    level: int
    console_level: int
    file_level: int
    format: str
    console_format: str
    file_format: str
    masking: bool
    console_masking: bool
    file_masking: bool


@dataclass(slots=True)
class LoggerContextConfig:
    """Configure levels and formats for one named logging context."""

    status: LoggerContextStatus = LoggerContextStatus.CONFIGURED
    level: int | str | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_level: int | str | LoggerConfigValue = LoggerConfigValue.AUTO
    file_level: int | str | LoggerConfigValue = LoggerConfigValue.AUTO
    format: str | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_format: str | LoggerConfigValue = LoggerConfigValue.AUTO
    file_format: str | LoggerConfigValue = LoggerConfigValue.AUTO
    masking: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO
    file_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO

    _on_change: Callable[[], None] | None = dataclass_field(default=None,
                                                            init=False,
                                                            repr=False,
                                                            compare=False)
    _notifications_enabled: bool = dataclass_field(default=False,
                                                   init=False,
                                                   repr=False,
                                                   compare=False)

    def __post_init__(self) -> None:
        self._validate()
        object.__setattr__(self, "_notifications_enabled", True)

    def __setattr__(self,
                    key: str,
                    value: Any) -> None:
        if not key.startswith("_") and getattr(self, "_notifications_enabled", False):
            self._validate_value(key, value)
        object.__setattr__(self, key, value)
        if not key.startswith("_") and getattr(self, "_notifications_enabled", False):
            self._notify()

    def copy(self) -> "LoggerContextConfig":
        result = replace(self)
        object.__setattr__(result, "_on_change", None)
        object.__setattr__(result, "_notifications_enabled", True)
        return result

    def configure(self,
                  *,
                  level: int | str | LoggerConfigValue = LoggerConfigValue.INHERIT,
                  console_level: int | str | LoggerConfigValue = LoggerConfigValue.AUTO,
                  file_level: int | str | LoggerConfigValue = LoggerConfigValue.AUTO,
                  format: str | LoggerConfigValue = LoggerConfigValue.INHERIT,
                  console_format: str | LoggerConfigValue = LoggerConfigValue.AUTO,
                  file_format: str | LoggerConfigValue = LoggerConfigValue.AUTO,
                  masking: bool | LoggerConfigValue = LoggerConfigValue.INHERIT,
                  console_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO,
                  file_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO) -> None:
        """Apply context-specific level and format overrides."""

        values = {"level": level,
                  "console_level": console_level,
                  "file_level": file_level,
                  "format": format,
                  "console_format": console_format,
                  "file_format": file_format,
                  "masking": masking,
                  "console_masking": console_masking,
                  "file_masking": file_masking}
        for name, value in values.items():
            self._validate_value(name, value)
        object.__setattr__(self, "status", LoggerContextStatus.CONFIGURED)
        for name, value in values.items():
            object.__setattr__(self, name, value)
        self._notify()

    def inherit(self) -> None:
        object.__setattr__(self, "status", LoggerContextStatus.INHERIT)
        for name in ("level", "console_level", "file_level", "format", "console_format", "file_format", "masking", "console_masking", "file_masking"):
            object.__setattr__(self, name, LoggerConfigValue.INHERIT)
        self._notify()

    def disable(self) -> None:
        object.__setattr__(self, "status", LoggerContextStatus.DISABLED)
        self._notify()

    def _bind(self,
              on_change: Callable[[], None]) -> None:
        object.__setattr__(self, "_on_change", on_change)

    def _unbind(self) -> None:
        object.__setattr__(self, "_on_change", None)

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def _validate(self) -> None:
        for name in ("status", "level", "console_level", "file_level", "format", "console_format", "file_format"):
            self._validate_value(name, getattr(self, name))

    @staticmethod
    def _validate_value(name: str,
                        value: Any) -> None:
        if name == "status":
            if not isinstance(value, LoggerContextStatus) or value is LoggerContextStatus.UNDEFINED:
                raise LoggerConfigurationError("A stored logging context must use INHERIT, CONFIGURED, or DISABLED.")
            return
        if value is LoggerConfigValue.INHERIT:
            return
        if value is LoggerConfigValue.AUTO:
            if name in {"console_level", "file_level", "console_format", "file_format", "console_masking", "file_masking"}:
                return
            raise LoggerConfigurationError(f"{name} cannot use LoggerConfigValue.AUTO.")
        if name in {"masking", "console_masking", "file_masking"}:
            if not isinstance(value, bool):
                raise LoggerConfigurationError(f"{name} must be bool, INHERIT, or AUTO.")
            return
        if name.endswith("format") or name == "format":
            if not isinstance(value, str):
                raise LoggerConfigurationError(f"{name} must be str or LoggerConfigValue.INHERIT.")
            return
        ObjectLoggerConfig._normalize_level(value)


class ObjectLoggerContexts:
    """Manage named context-specific level and format configurations."""

    def __init__(self,
                 entries: Mapping[str, LoggerContextConfig] | None = None):
        self._entries: dict[str, LoggerContextConfig] = {}
        self._on_change: Callable[[], None] | None = None
        for name, config in (entries or {}).items():
            self._store(name, config.copy(), notify=False)

    def __contains__(self,
                     name: str) -> bool:
        return self.status(name) is not LoggerContextStatus.UNDEFINED

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def copy(self) -> "ObjectLoggerContexts":
        return ObjectLoggerContexts(self._entries)

    def status(self,
               name: str) -> LoggerContextStatus:
        entry = self._entries.get(self._normalize_name(name))
        return entry.status if entry is not None else LoggerContextStatus.UNDEFINED

    def get(self,
            name: str) -> LoggerContextConfig | None:
        return self._entries.get(self._normalize_name(name))

    def require(self,
                name: str) -> LoggerContextConfig:
        normalized_name = self._normalize_name(name)
        try:
            return self._entries[normalized_name]
        except KeyError:
            raise KeyError(f"Logging context '{normalized_name}' is undefined.") from None

    def configure(self,
                  name: str,
                  *,
                  level: int | str | LoggerConfigValue = LoggerConfigValue.INHERIT,
                  console_level: int | str | LoggerConfigValue = LoggerConfigValue.AUTO,
                  file_level: int | str | LoggerConfigValue = LoggerConfigValue.AUTO,
                  format: str | LoggerConfigValue = LoggerConfigValue.INHERIT,
                  console_format: str | LoggerConfigValue = LoggerConfigValue.AUTO,
                  file_format: str | LoggerConfigValue = LoggerConfigValue.AUTO,
                  masking: bool | LoggerConfigValue = LoggerConfigValue.INHERIT,
                  console_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO,
                  file_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO) -> LoggerContextConfig:
        """Create or replace one context configuration."""

        entry = LoggerContextConfig(status=LoggerContextStatus.CONFIGURED,
                                    level=level,
                                    console_level=console_level,
                                    file_level=file_level,
                                    format=format,
                                    console_format=console_format,
                                    file_format=file_format,
                                    masking=masking,
                                    console_masking=console_masking,
                                    file_masking=file_masking)
        self._store(name, entry)
        return entry

    def inherit(self,
                name: str) -> LoggerContextConfig:
        entry = LoggerContextConfig(status=LoggerContextStatus.INHERIT)
        self._store(name, entry)
        return entry

    def disable(self,
                name: str) -> LoggerContextConfig:
        entry = LoggerContextConfig(status=LoggerContextStatus.DISABLED)
        self._store(name, entry)
        return entry

    def remove(self,
               name: str) -> None:
        normalized_name = self._normalize_name(name)
        entry = self._entries.pop(normalized_name, None)
        if entry is not None:
            entry._unbind()
            self._notify()

    def clear(self) -> None:
        if not self._entries:
            return
        for entry in self._entries.values():
            entry._unbind()
        self._entries.clear()
        self._notify()

    def items(self) -> tuple[tuple[str, LoggerContextConfig], ...]:
        return tuple(self._entries.items())

    def _bind(self,
              on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        for entry in self._entries.values():
            entry._bind(on_change)

    def _unbind(self) -> None:
        self._on_change = None
        for entry in self._entries.values():
            entry._unbind()

    def _store(self,
               name: str,
               entry: LoggerContextConfig,
               *,
               notify: bool = True) -> None:
        normalized_name = self._normalize_name(name)
        old_entry = self._entries.get(normalized_name)
        if old_entry is not None:
            old_entry._unbind()
        entry._bind(self._notify)
        self._entries[normalized_name] = entry
        if notify:
            self._notify()

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise LoggerConfigurationError("Logging context name cannot be empty.")
        return normalized_name

    def _resolve(self,
                 parent_contexts: Mapping[str, _ResolvedLoggerContextConfig],
                 *,
                 default_level: int,
                 default_console_level: int,
                 default_file_level: int,
                 default_format: str,
                 default_console_format: str,
                 default_file_format: str,
                 default_masking: bool,
                 default_console_masking: bool,
                 default_file_masking: bool) -> dict[str, _ResolvedLoggerContextConfig]:
        result = dict(parent_contexts)
        for name, entry in self._entries.items():
            parent = parent_contexts.get(name)
            if entry.status is LoggerContextStatus.DISABLED:
                result[name] = _ResolvedLoggerContextConfig(disabled=True,
                                                            level=logging.CRITICAL + 1,
                                                            console_level=logging.CRITICAL + 1,
                                                            file_level=logging.CRITICAL + 1,
                                                            format=default_format,
                                                            console_format=default_console_format,
                                                            file_format=default_file_format,
                                                            masking=default_masking,
                                                            console_masking=default_console_masking,
                                                            file_masking=default_file_masking)
                continue
            if entry.status is LoggerContextStatus.INHERIT:
                if parent is None:
                    result.pop(name, None)
                else:
                    result[name] = parent
                continue

            inherited_level = parent.level if parent is not None else default_level
            inherited_console_level = parent.console_level if parent is not None else default_console_level
            inherited_file_level = parent.file_level if parent is not None else default_file_level
            inherited_format = parent.format if parent is not None else default_format
            inherited_console_format = parent.console_format if parent is not None else default_console_format
            inherited_file_format = parent.file_format if parent is not None else default_file_format
            inherited_masking = parent.masking if parent is not None else default_masking
            inherited_console_masking = parent.console_masking if parent is not None else default_console_masking
            inherited_file_masking = parent.file_masking if parent is not None else default_file_masking

            level = inherited_level if entry.level is LoggerConfigValue.INHERIT else ObjectLoggerConfig._normalize_level(entry.level)
            console_level = level if entry.console_level is LoggerConfigValue.AUTO else (
                inherited_console_level if entry.console_level is LoggerConfigValue.INHERIT else ObjectLoggerConfig._normalize_level(entry.console_level))
            file_level = level if entry.file_level is LoggerConfigValue.AUTO else (
                inherited_file_level if entry.file_level is LoggerConfigValue.INHERIT else ObjectLoggerConfig._normalize_level(entry.file_level))
            common_format = inherited_format if entry.format is LoggerConfigValue.INHERIT else entry.format
            console_format = common_format if entry.console_format is LoggerConfigValue.AUTO else (
                inherited_console_format if entry.console_format is LoggerConfigValue.INHERIT else entry.console_format)
            file_format = common_format if entry.file_format in {LoggerConfigValue.AUTO,
                                                                 LoggerConfigValue.INHERIT} and entry.format is not LoggerConfigValue.INHERIT else (
                inherited_file_format if entry.file_format is LoggerConfigValue.INHERIT else entry.file_format)
            masking = inherited_masking if entry.masking is LoggerConfigValue.INHERIT else bool(entry.masking)
            console_masking = masking if entry.console_masking is LoggerConfigValue.AUTO else (
                inherited_console_masking if entry.console_masking is LoggerConfigValue.INHERIT else bool(entry.console_masking))
            file_masking = masking if entry.file_masking is LoggerConfigValue.AUTO else (
                inherited_file_masking if entry.file_masking is LoggerConfigValue.INHERIT else bool(entry.file_masking))

            result[name] = _ResolvedLoggerContextConfig(disabled=False,
                                                        level=level,
                                                        console_level=console_level,
                                                        file_level=file_level,
                                                        format=common_format,
                                                        console_format=console_format,
                                                        file_format=file_format,
                                                        masking=masking,
                                                        console_masking=console_masking,
                                                        file_masking=file_masking)
        return result


@dataclass(frozen=True, slots=True)
class _ResolvedObjectLoggerConfig:
    logger_class: type["ObjectLogger"]
    parent: LoggerParent | str
    propagate: bool
    level: int
    default_level: int
    disabled: bool

    handler_factories: tuple[Callable[[], logging.Handler], ...]
    formatter: logging.Formatter | None
    format: str
    show_time: bool
    show_level: bool
    show_name: bool
    show_status: bool
    show_context: bool
    show_context_data: bool
    masking: bool
    console_masking: bool
    file_masking: bool
    custom_handler_masking: bool

    console: bool
    console_level: int
    console_format: str
    console_rich_show_time: bool
    console_rich_markup: bool
    console_rich_show_level: bool
    console_rich_show_path: bool

    file: bool
    file_path: str | Path
    file_mode: str
    file_level: int
    file_format: str
    file_max_bytes: int
    file_backup_count: int
    file_encoding: str | None
    file_delay: bool
    file_archive_backup_count: int

    contexts: Mapping[str, _ResolvedLoggerContextConfig]


@dataclass(slots=True)
class ObjectLoggerConfig:
    """Mutable, inheritable logging interface for one ``BaseObject``."""

    logger_class: type["ObjectLogger"] | LoggerConfigValue = LoggerConfigValue.INHERIT
    parent: LoggerParent | str = LoggerParent.OBJECT_PARENT
    propagate: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    level: int | str | None | LoggerConfigValue = LoggerConfigValue.INHERIT
    disabled: bool | LoggerConfigValue = LoggerConfigValue.INHERIT

    handler_factories: tuple[Callable[[], logging.Handler], ...] | LoggerConfigValue = LoggerConfigValue.INHERIT
    formatter: logging.Formatter | None | LoggerConfigValue = LoggerConfigValue.INHERIT
    format: str | LoggerConfigValue = LoggerConfigValue.INHERIT
    show_time: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    show_level: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    show_name: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    show_status: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    show_context: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    show_context_data: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    masking: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO
    file_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO
    custom_handler_masking: bool | LoggerConfigValue = LoggerConfigValue.AUTO

    console: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_level: int | str | None | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_format: str | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_rich_show_time: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_rich_markup: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_rich_show_level: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    console_rich_show_path: bool | LoggerConfigValue = LoggerConfigValue.INHERIT

    file: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_path: str | Path | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_mode: str | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_level: int | str | None | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_format: str | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_max_bytes: int | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_backup_count: int | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_encoding: str | None | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_delay: bool | LoggerConfigValue = LoggerConfigValue.INHERIT
    file_archive_backup_count: int | LoggerConfigValue = LoggerConfigValue.INHERIT

    contexts: ObjectLoggerContexts = dataclass_field(default_factory=ObjectLoggerContexts)

    _on_change: Callable[[], None] | None = dataclass_field(default=None,
                                                            init=False,
                                                            repr=False,
                                                            compare=False)
    _notifications_enabled: bool = dataclass_field(default=False,
                                                   init=False,
                                                   repr=False,
                                                   compare=False)

    def __post_init__(self) -> None:
        """
        Validate and finalize the newly created instance.

        :return:
            Returns None.
        """
        self._validate_all()
        self.contexts._bind(self._notify)
        object.__setattr__(self, "_notifications_enabled", True)

    def __setattr__(self,
                    key: str,
                    value: Any) -> None:
        """
        Validate and apply an attribute assignment.

        :param key:
            The attribute or configuration-field name.

        :param value:
            The value to validate or assign.

        :return:
            Returns None.
        """
        if (not key.startswith("_")
                and getattr(self, "_notifications_enabled", False)):
            self._validate_field(key, value)
        old_contexts = getattr(self, "contexts", None) if key == "contexts" else None
        object.__setattr__(self, key, value)
        if key == "contexts" and isinstance(value, ObjectLoggerContexts):
            if isinstance(old_contexts, ObjectLoggerContexts):
                old_contexts._unbind()
            value._bind(self._notify)
        if key.startswith("_") or not getattr(self, "_notifications_enabled", False):
            return
        self._notify()

    def copy(self) -> "ObjectLoggerConfig":
        """
        Return an independent copy that is safe to bind to another owner.

        :return:
            Returns an independent logger-configuration copy.
        """
        result = replace(self, contexts=self.contexts.copy())
        object.__setattr__(result, "_on_change", None)
        result.contexts._bind(result._notify)
        object.__setattr__(result, "_notifications_enabled", True)
        return result

    def _bind(self,
              on_change: Callable[[], None]) -> None:
        """
        Execute the '_bind' operation.

        :param on_change:
            The callback invoked after a configuration change.

        :return:
            Returns None.
        """
        object.__setattr__(self, "_on_change", on_change)
        self.contexts._bind(on_change)

    def _unbind(self) -> None:
        """
        Execute the '_unbind' operation.

        :return:
            Returns None.
        """
        object.__setattr__(self, "_on_change", None)
        self.contexts._unbind()

    def _notify(self) -> None:
        """
        Execute the '_notify' operation.

        :return:
            Returns None.
        """
        callback = self._on_change
        if callback is not None:
            callback()

    def resolve(self,
                parent_config: _ResolvedObjectLoggerConfig | None) -> _ResolvedObjectLoggerConfig:
        """
        Resolve local overrides against the inherited configuration.

        :param parent_config:
            The resolved parent configuration used for inheritance.

        :return:
            Returns a value of type ``_ResolvedObjectLoggerConfig``.
        """
        defaults = self._framework_defaults()

        def inherited(name: str) -> Any:
            value = getattr(self, name)
            if value is not LoggerConfigValue.INHERIT:
                return value
            if parent_config is not None:
                return getattr(parent_config, name)
            return getattr(defaults, name)

        resolved_parent = self.parent
        resolved_propagate = (resolved_parent is not LoggerParent.NONE
                              if self.propagate is LoggerConfigValue.INHERIT
                              else self.propagate)
        base_level_value = inherited("level")
        base_level = self._normalize_level(base_level_value if base_level_value is not None else logging.NOTSET)

        console_level_value = inherited("console_level")
        if self.console_level is LoggerConfigValue.AUTO:
            console_level_value = base_level
        resolved_console_level = self._normalize_level(console_level_value if console_level_value is not None else base_level)

        file_level_value = inherited("file_level")
        if self.file_level is LoggerConfigValue.AUTO:
            file_level_value = base_level
        resolved_file_level = self._normalize_level(file_level_value if file_level_value is not None else base_level)

        show_time = bool(inherited("show_time"))
        show_level = bool(inherited("show_level"))
        show_name = bool(inherited("show_name"))
        show_status = bool(inherited("show_status"))
        show_context = bool(inherited("show_context"))
        show_context_data = bool(inherited("show_context_data"))

        def automatic_format(channel: str) -> str:
            parts: list[str] = []
            if show_time:
                parts.append("%(asctime)s")
            if show_level:
                parts.append("[%(levelname)s]")
            if show_status:
                parts.append("[%(object_status)s]")
            if show_context:
                parts.append("[%(log_context)s]")
            if show_name:
                parts.append("%(name)s:")
            parts.append("%(message)s")
            if show_context_data:
                parts.append("| %(log_context_data)s")
            return " ".join(parts)

        common_format_value = inherited("format")
        common_format = automatic_format("common") if common_format_value is LoggerConfigValue.AUTO else common_format_value
        console_value = inherited("console_format")
        console_format = common_format if console_value is LoggerConfigValue.AUTO else console_value
        file_value = inherited("file_format")
        file_format = common_format if file_value is LoggerConfigValue.AUTO else file_value

        resolved_masking = bool(inherited("masking"))
        console_masking_value = inherited("console_masking")
        resolved_console_masking = resolved_masking if console_masking_value is LoggerConfigValue.AUTO else bool(console_masking_value)
        file_masking_value = inherited("file_masking")
        resolved_file_masking = resolved_masking if file_masking_value is LoggerConfigValue.AUTO else bool(file_masking_value)
        custom_masking_value = inherited("custom_handler_masking")
        resolved_custom_masking = resolved_masking if custom_masking_value is LoggerConfigValue.AUTO else bool(custom_masking_value)

        resolved_contexts = self.contexts._resolve(parent_config.contexts if parent_config is not None else {},
                                                   default_level=base_level,
                                                   default_console_level=resolved_console_level,
                                                   default_file_level=resolved_file_level,
                                                   default_format=common_format,
                                                   default_console_format=console_format,
                                                   default_file_format=file_format,
                                                   default_masking=resolved_masking,
                                                   default_console_masking=resolved_console_masking,
                                                   default_file_masking=resolved_file_masking)
        technical_levels = [base_level]
        if inherited("console"):
            technical_levels.append(resolved_console_level)
        if inherited("file"):
            technical_levels.append(resolved_file_level)
        for context in resolved_contexts.values():
            if not context.disabled:
                technical_levels.extend((context.level,
                                         context.console_level,
                                         context.file_level))

        return _ResolvedObjectLoggerConfig(logger_class=inherited("logger_class"),
                                           parent=resolved_parent,
                                           propagate=resolved_propagate,
                                           level=min(technical_levels),
                                           default_level=base_level,
                                           disabled=inherited("disabled"),
                                           handler_factories=inherited("handler_factories"),
                                           formatter=inherited("formatter"),
                                           format=common_format,
                                           show_time=show_time,
                                           show_level=show_level,
                                           show_name=show_name,
                                           show_status=show_status,
                                           show_context=show_context,
                                           show_context_data=show_context_data,
                                           masking=resolved_masking,
                                           console_masking=resolved_console_masking,
                                           file_masking=resolved_file_masking,
                                           custom_handler_masking=resolved_custom_masking,
                                           console=inherited("console"),
                                           console_level=resolved_console_level,
                                           console_format=console_format,
                                           console_rich_show_time=inherited("console_rich_show_time"),
                                           console_rich_markup=inherited("console_rich_markup"),
                                           console_rich_show_level=inherited("console_rich_show_level"),
                                           console_rich_show_path=inherited("console_rich_show_path"),
                                           file=inherited("file"),
                                           file_path=inherited("file_path"),
                                           file_mode=inherited("file_mode"),
                                           file_level=resolved_file_level,
                                           file_format=file_format,
                                           file_max_bytes=inherited("file_max_bytes"),
                                           file_backup_count=inherited("file_backup_count"),
                                           file_encoding=inherited("file_encoding"),
                                           file_delay=inherited("file_delay"),
                                           file_archive_backup_count=inherited("file_archive_backup_count"),
                                           contexts=resolved_contexts)

    @staticmethod
    def _framework_defaults() -> _ResolvedObjectLoggerConfig:
        """
        Execute the '_framework_defaults' operation.

        :return:
            Returns a value of type ``_ResolvedObjectLoggerConfig``.
        """

        from admin_helper.logger import ObjectLogger

        return _ResolvedObjectLoggerConfig(logger_class=ObjectLogger,
                                           parent=LoggerParent.OBJECT_PARENT,
                                           propagate=True,
                                           level=logging.NOTSET,
                                           default_level=logging.NOTSET,
                                           disabled=False,
                                           handler_factories=(),
                                           formatter=None,
                                           format="%(message)s",
                                           show_time=True,
                                           show_level=True,
                                           show_name=True,
                                           show_status=True,
                                           show_context=True,
                                           show_context_data=True,
                                           masking=True,
                                           console_masking=True,
                                           file_masking=True,
                                           custom_handler_masking=True,
                                           console=False,
                                           console_level=logging.NOTSET,
                                           console_format="[%(object_status)s] [%(log_context)s] %(message)s",
                                           console_rich_show_time=True,
                                           console_rich_markup=True,
                                           console_rich_show_level=True,
                                           console_rich_show_path=False,
                                           file=False,
                                           file_path="logs/{name}.log",
                                           file_mode="a",
                                           file_level=logging.NOTSET,
                                           file_format="%(asctime)s [%(levelname)s] [%(object_status)s] [%(log_context)s] %(name)s: %(message)s | %(log_context_data)s",
                                           file_max_bytes=0,
                                           file_backup_count=0,
                                           file_encoding="utf-8",
                                           file_delay=False,
                                           file_archive_backup_count=0,
                                           contexts={})

    @staticmethod
    def _normalize_level(value: int | str) -> int:
        """
        Execute the '_normalize_level' operation.

        :param value:
            The value to validate or assign.

        :return:
            Returns a value of type ``int``.
        """
        if isinstance(value, int):
            return value
        normalized = logging.getLevelName(value.upper())
        if not isinstance(normalized, int):
            raise LoggerConfigurationError(f"Unknown logging level '{value}'.")
        return normalized

    def _validate_all(self) -> None:
        """
        Execute the '_validate_all' operation.

        :return:
            Returns None.
        """
        for name in self.__dataclass_fields__:
            if not name.startswith("_"):
                self._validate_field(name, getattr(self, name))

    @staticmethod
    def _validate_field(name: str,
                        value: Any) -> None:
        """
        Execute the '_validate_field' operation.

        :param name:
            The name to process.

        :param value:
            The value to validate or assign.

        :return:
            Returns None.
        """

        from admin_helper.logger import ObjectLogger

        if value is LoggerConfigValue.INHERIT:
            if name == "parent":
                raise LoggerConfigurationError("parent cannot use LoggerConfigValue.INHERIT.")
            return
        if value is LoggerConfigValue.AUTO:
            if name not in {"format", "console_level", "file_level", "console_format", "file_format",
                            "console_masking", "file_masking", "custom_handler_masking"}:
                raise LoggerConfigurationError(f"{name} cannot use LoggerConfigValue.AUTO.")
            return
        if name == "logger_class":
            if not isinstance(value, type) or not issubclass(value, ObjectLogger):
                raise LoggerConfigurationError(f"logger_class must inherit from {ObjectLogger.__name__}, got {value!r}.")
            return
        if name == "parent":
            if not isinstance(value, (LoggerParent, str)):
                raise LoggerConfigurationError("parent must be LoggerParent or a logger-name string.")
            if isinstance(value, str) and not value.strip():
                raise LoggerConfigurationError("parent logger name cannot be empty.")
            return
        if name == "contexts":
            if not isinstance(value, ObjectLoggerContexts):
                raise LoggerConfigurationError("contexts must be an ObjectLoggerContexts instance.")
            return
        boolean_fields = {"propagate", "disabled", "show_time", "show_level", "show_name",
                          "show_status", "show_context", "show_context_data", "masking",
                          "console_masking", "file_masking", "custom_handler_masking",
                          "console", "console_rich_show_time",
                          "console_rich_markup", "console_rich_show_level", "console_rich_show_path",
                          "file", "file_delay"}
        if name in boolean_fields and not isinstance(value, bool):
            raise LoggerConfigurationError(f"{name} must be bool or LoggerConfigValue.INHERIT.")
        integer_fields = {"file_max_bytes", "file_backup_count", "file_archive_backup_count"}
        if name in integer_fields and (not isinstance(value, int) or value < 0):
            raise LoggerConfigurationError(f"{name} must be a non-negative integer or LoggerConfigValue.INHERIT.")
        if name == "handler_factories":
            if not isinstance(value, tuple) or not all(callable(factory) for factory in value):
                raise LoggerConfigurationError("handler_factories must be a tuple of callables.")
        if name == "formatter" and value is not None and not isinstance(value, logging.Formatter):
            raise LoggerConfigurationError("formatter must be logging.Formatter, None, or INHERIT.")
        if name in {"level", "console_level", "file_level"} and value is not None:
            ObjectLoggerConfig._normalize_level(value)
        if name in {"format", "console_format", "file_format"} and not isinstance(value, str):
            raise LoggerConfigurationError(f"{name} must be str or LoggerConfigValue.INHERIT.")
