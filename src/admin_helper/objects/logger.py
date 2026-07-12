import logging
import os
import tarfile
import warnings
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Any, Iterator, Mapping, Union, Optional

from rich.logging import RichHandler

from admin_helper.objects.config import (
    _ResolvedObjectLoggerConfig,
    ObjectStatus,
    _ResolvedLoggerContextConfig,
    _logger_context_stack,
    _LoggerContextFrame,
)
from admin_helper.console import AdminHelperConsole
from admin_helper.exceptions import LoggerConfigurationError
from admin_helper.objects.helper import _format_log_value, _masking_framework_config
from admin_helper.objects.sensitive_value_registry import _sensitive_value_registry
from admin_helper.warnings import SensitiveValueWarning


class ContextThresholdFilter(logging.Filter):
    """Apply the active context threshold to one concrete output channel."""

    def __init__(self, logger: "ObjectLogger", channel: str):
        """
        Initialize the instance and its private runtime state.

        :param logger:
            The 'logger' value used by the operation.

        :param channel:
            The handler channel whose effective level is requested.

        :return:
            Returns the result of the operation.
        """
        super().__init__()
        self._logger = logger
        self._channel = channel

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Return whether the current record passes the configured filter.

        :param record:
            The log record to inspect or format.

        :return:
            Returns True when the condition is satisfied; otherwise, returns False.
        """
        return record.levelno >= self._logger._context_threshold(self._channel)


class MaskedValueFilter(logging.Filter):
    """Redact cached sensitive values before a managed handler formats them."""

    def __init__(
        self, logger: Optional["ObjectLogger"] = None, channel: str = "custom"
    ) -> None:
        super().__init__()
        self._logger = logger
        self._channel = channel

    def filter(self, record: logging.LogRecord) -> bool:
        global_config = _masking_framework_config()
        channel_enabled = {
            "console": global_config.console,
            "file": global_config.file,
            "custom": global_config.custom_handlers,
        }.get(self._channel, global_config.enabled)
        if not global_config.enabled or not channel_enabled:
            return True
        if self._logger is not None and not self._logger._masking_enabled(
            self._channel
        ):
            if global_config.enforced:
                warnings.warn(
                    "A local logger configuration attempted to disable enforced sensitive-value masking.",
                    SensitiveValueWarning,
                    stacklevel=2,
                )
            else:
                return True
        record.msg = _sensitive_value_registry().sanitize(record.msg)
        record.args = _sensitive_value_registry().sanitize(record.args)
        if hasattr(record, "log_context_data"):
            setattr(
                record,
                "log_context_data",
                _sensitive_value_registry().sanitize(
                    getattr(record, "log_context_data")
                ),
            )
        if hasattr(record, "log_context_values"):
            setattr(
                record,
                "log_context_values",
                _sensitive_value_registry().sanitize(
                    getattr(record, "log_context_values")
                ),
            )
        return True


class Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """
        Execute the 'format' operation.

        :param record:
            The log record to inspect or format.

        :return:
            Returns a value of type ``str``.
        """
        if (
            hasattr(record, "markup")
            and getattr(self._style, "_fmt", None) == "%(message)s"
        ):
            return record.getMessage()
        return super().format(record)


class ContextAwareFormatter(logging.Formatter):
    """Select and cache a formatter based on the active logging context."""

    def __init__(self, logger: "ObjectLogger", channel: str):
        super().__init__()
        self._logger = logger
        self._channel = channel
        self._cache: dict[str, Formatter] = {}

    def format(self, record: logging.LogRecord) -> str:
        format_string = self._logger._context_format(self._channel)
        formatter = self._cache.get(format_string)
        if formatter is None:
            formatter = Formatter(format_string)
            self._cache[format_string] = formatter
        return formatter.format(record)


class ObjectLogger(logging.Logger):
    """Logger implementation used by every ``BaseObject``."""

    class TarRotatingFileHandler(RotatingFileHandler):
        def __init__(
            self,
            name: str,
            filename: str | Path,
            mode: str = "a",
            max_bytes: int = 0,
            backup_count: int = 0,
            encoding: str | None = None,
            delay: bool = False,
            archive_backup_count: int = 0,
        ):
            """
            Initialize the instance and its private runtime state.

            :param name:
                The name to process.

            :param filename:
                The file path used by the logging handler.

            :param mode:
                The file-opening mode.

            :param max_bytes:
                The maximum file size before rotation.

            :param backup_count:
                The number of rotated files to retain.

            :param encoding:
                The text encoding used for the log file.

            :param delay:
                Whether opening the log file is delayed until the first record.

            :param archive_backup_count:
                The number of compressed archives to retain.

            :return:
                Returns the result of the operation.
            """
            super().__init__(
                filename=filename,
                mode=mode,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding=encoding,
                delay=delay,
            )
            self.set_name(name)
            self.archive_backup_count = archive_backup_count
            self.archive_base_filename = (
                self.baseFilename[: self.baseFilename.rfind(".")]
                if "." in self.baseFilename
                else self.baseFilename
            )

        def doRollover(self) -> None:
            """
            Execute the 'doRollover' operation.

            :return:
                Returns None.
            """
            super().doRollover()
            if self.backupCount <= 0 or self.archive_backup_count <= 0:
                return
            backup_log_pattern = self.baseFilename + ".%d"
            backup_logs = [
                Path(backup_log_pattern % index)
                for index in range(1, self.backupCount + 1)
            ]
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
            # noinspection PyTypeChecker
            with tarfile.open(archive_filename, "w:gz") as archive:
                for log in backup_logs:
                    archive.add(log, arcname=log.name)
                    os.remove(log)

    def __init__(self, name: str, level: int = logging.NOTSET):
        """
        Initialize the instance and its private runtime state.

        :param name:
            The name to process.

        :param level:
            The logging level to apply.

        :return:
            Returns the result of the operation.
        """
        super().__init__(name=name, level=level)
        self._managed_handlers: list[logging.Handler] = []
        self._resolved_config: _ResolvedObjectLoggerConfig | None = None
        self._status_provider: Callable[[], ObjectStatus | str] | None = None
        self._default_level = logging.NOTSET
        self._default_console_level = logging.NOTSET
        self._default_file_level = logging.NOTSET
        self._default_format = "%(message)s"
        self._default_console_format = "%(message)s"
        self._default_file_format = "%(message)s"
        self._contexts: dict[str, _ResolvedLoggerContextConfig] = {}

    def _bind_status_provider(
        self, provider: Callable[[], Union["ObjectStatus", str]]
    ) -> None:
        """
        Execute the '_bind_status_provider' operation.

        :param provider:
            The 'provider' value used by the operation.

        :return:
            Returns None.
        """
        self._status_provider = provider

    def _active_context_config(self) -> _ResolvedLoggerContextConfig | None:
        """
        Execute the '_active_context_config' operation.

        :return:
            Returns a value of type ``_ResolvedLoggerContextConfig | None``.
        """
        stack = _logger_context_stack.get()
        if not stack:
            return None
        context_name = ".".join(frame.name for frame in stack)
        matches = [
            (name, config)
            for name, config in self._contexts.items()
            if context_name == name or context_name.startswith(f"{name}.")
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: len(item[0]))[1]

    def _context_threshold(self, channel: str) -> int:
        """
        Execute the '_context_threshold' operation.

        :param channel:
            The handler channel whose effective level is requested.

        :return:
            Returns a value of type ``int``.
        """
        context = self._active_context_config()
        if context is not None:
            if context.disabled:
                return logging.CRITICAL + 1
            if channel == "console":
                return context.console_level
            if channel == "file":
                return context.file_level
            return context.level
        if channel == "console":
            return self._default_console_level
        if channel == "file":
            return self._default_file_level
        return self._default_level

    def _context_format(self, channel: str) -> str:
        """Return the active format string for one output channel."""

        context = self._active_context_config()
        if context is not None and not context.disabled:
            if channel == "console":
                return context.console_format
            if channel == "file":
                return context.file_format
            return context.format
        if channel == "console":
            return self._default_console_format
        if channel == "file":
            return self._default_file_format
        return self._default_format

    def isEnabledFor(self, level: int) -> bool:
        """
        Return whether a record at the supplied level can be emitted.

        :param level:
            The logging level to apply.

        :return:
            Returns True when the condition is satisfied; otherwise, returns False.
        """
        if self.disabled:
            return False
        if level < self.getEffectiveLevel():
            return False
        return level >= self._context_threshold("logger")

    @contextmanager
    def context(self, name: str, **values: Any) -> Iterator["ObjectLogger"]:
        """
        Add a dynamic context without defining logging policy in business code.

        Examples:
            with logger.context('broadcast', method='reload'):
                logger.debug('Broadcasting the method.')

        :param name:
            The name to process.

        :param values:
            The 'values' value used by the operation.

        :return:
            Returns an iterator over the requested values.
        """

        normalized_name = name.strip()
        if not normalized_name:
            raise LoggerConfigurationError("Logging context name cannot be empty.")
        frame = _LoggerContextFrame(name=normalized_name, values=dict(values))
        stack = _logger_context_stack.get()
        token = _logger_context_stack.set((*stack, frame))
        try:
            yield self
        finally:
            _logger_context_stack.reset(token)

    def makeRecord(self, *args: Any, **kwargs: Any) -> logging.LogRecord:
        """
        Create a log record and attach object status and context metadata.

        :param args:
            The positional constructor arguments stored for delayed creation.

        :param kwargs:
            The keyword constructor arguments stored for delayed creation.

        :return:
            Returns a value of type ``logging.LogRecord``.
        """
        record = super().makeRecord(*args, **kwargs)
        stack = _logger_context_stack.get()
        context_values: dict[str, Any] = {}
        for frame in stack:
            context_values.update(frame.values)
        status: ObjectStatus | str = ObjectStatus.READY
        if self._status_provider is not None:
            status = self._status_provider()
        record.object_status = (
            status.value if isinstance(status, ObjectStatus) else str(status)
        )
        record.log_context = ".".join(frame.name for frame in stack) if stack else "-"
        record.log_context_depth = len(stack)
        record.log_context_values = context_values
        record.log_context_data = (
            ", ".join(
                f"{key}: {_format_log_value(value)}"
                for key, value in context_values.items()
            )
            or "-"
        )
        return record

    def _masking_enabled(self, channel: str) -> bool:
        """Return the effective masking state for the active context and channel."""

        context = self._active_context_config()
        if context is not None:
            if channel == "console":
                return context.console_masking
            if channel == "file":
                return context.file_masking
            return context.masking
        config = self._resolved_config
        if config is None:
            return True
        if channel == "console":
            return config.console_masking
        if channel == "file":
            return config.file_masking
        return config.custom_handler_masking

    def configure(
        self,
        config: "_ResolvedObjectLoggerConfig",
        parent_logger: logging.Logger | None,
        *,
        path_values: Mapping[str, str],
    ) -> None:
        """
        Apply the supplied configuration values and notify the owner.

        :param config:
            The configuration to apply.

        :param parent_logger:
            The logger that receives propagated records.

        :param path_values:
            The values available while rendering path templates.

        :return:
            Returns None.
        """
        for handler in tuple(self._managed_handlers):
            if handler in self.handlers:
                self.removeHandler(handler)
            try:
                handler.close()
            finally:
                self._managed_handlers.remove(handler)

        self.disabled = config.disabled
        self._default_level = config.default_level
        self._default_console_level = config.console_level
        self._default_file_level = config.file_level
        self._default_format = config.format
        self._default_console_format = config.console_format
        self._default_file_format = config.file_format
        self._contexts = dict(config.contexts)
        self.setLevel(config.level)
        self.parent = parent_logger
        self.propagate = config.propagate and parent_logger is not None

        configured_handlers: list[logging.Handler] = []
        if config.console and not config.disabled:
            console_handler = RichHandler(
                console=AdminHelperConsole,
                show_time=config.console_rich_show_time,
                markup=config.console_rich_markup,
                show_level=config.console_rich_show_level,
                show_path=config.console_rich_show_path,
            )
            console_handler.set_name(self.name)
            console_handler.setLevel(logging.NOTSET)
            console_handler.addFilter(ContextThresholdFilter(self, "console"))
            console_handler.setFormatter(ContextAwareFormatter(self, "console"))
            configured_handlers.append(console_handler)

        if config.file and not config.disabled:
            try:
                rendered_path = str(config.file_path).format_map(path_values)
            except KeyError as error:
                raise LoggerConfigurationError(
                    f"Unknown file_path placeholder '{error.args[0]}' for logger '{self.name}'."
                ) from error
            file_path = Path(rendered_path)
            if not file_path.parent.exists():
                raise FileNotFoundError(
                    f"Log file parent directory does not exist: '{file_path.parent}'!"
                )
            file_handler = self.TarRotatingFileHandler(
                name=self.name,
                filename=file_path,
                mode=config.file_mode,
                max_bytes=config.file_max_bytes,
                backup_count=config.file_backup_count,
                encoding=config.file_encoding,
                delay=config.file_delay,
                archive_backup_count=config.file_archive_backup_count,
            )
            file_handler.setLevel(logging.NOTSET)
            file_handler.addFilter(ContextThresholdFilter(self, "file"))
            file_handler.setFormatter(ContextAwareFormatter(self, "file"))
            configured_handlers.append(file_handler)

        for factory in config.handler_factories:
            handler = factory()
            if not isinstance(handler, logging.Handler):
                raise LoggerConfigurationError(
                    "Every handler factory must return a logging.Handler instance."
                )
            handler.addFilter(ContextThresholdFilter(self, "logger"))
            if config.formatter is not None:
                handler.setFormatter(config.formatter)
            configured_handlers.append(handler)

        for handler in configured_handlers:
            if not any(
                isinstance(filter_, MaskedValueFilter) for filter_ in handler.filters
            ):
                handler.addFilter(MaskedValueFilter(self, "custom"))
            self.addHandler(handler)
            self._managed_handlers.append(handler)
        self._resolved_config = config


def _get_object_logger(
    name: str, logger_class: type[ObjectLogger] = ObjectLogger
) -> ObjectLogger:
    """
    Return or create the requested ``ObjectLogger`` subclass.

    :param name:
        The name to process.

    :param logger_class:
        The ObjectLogger subclass to create.

    :return:
        Returns a value of type ``ObjectLogger``.
    """

    if not isinstance(logger_class, type) or not issubclass(logger_class, ObjectLogger):
        raise LoggerConfigurationError(
            f"logger_class must inherit from {ObjectLogger.__name__}, got {logger_class!r}."
        )

    existing = logging.Logger.manager.loggerDict.get(name)
    if isinstance(existing, logger_class):
        return existing
    if isinstance(existing, ObjectLogger):
        try:
            replacement = logger_class(name)
        except Exception as error:
            raise LoggerConfigurationError(
                f"Could not replace logger {name!r} with {logger_class.__name__}: {error}"
            ) from error
        replacement.manager = logging.Logger.manager
        logging.Logger.manager.loggerDict[name] = replacement
        return replacement
    if isinstance(existing, logging.Logger):
        raise LoggerConfigurationError(
            f"Logger {name!r} already exists as {type(existing).__name__}, not {logger_class.__name__}."
        )

    previous_logger_class = logging.getLoggerClass()
    logging.setLoggerClass(logger_class)
    try:
        logger = logging.getLogger(name)
    finally:
        logging.setLoggerClass(previous_logger_class)

    if not isinstance(logger, logger_class):
        raise LoggerConfigurationError(
            f"Could not create {logger_class.__name__} {name!r}."
        )
    return logger
