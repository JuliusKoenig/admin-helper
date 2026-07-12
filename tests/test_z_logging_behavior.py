from __future__ import annotations

import io
import logging
import tarfile
from pathlib import Path
from typing import Any, cast
from uuid import uuid4


from admin_helper.objects import (
    BaseObject,
    LoggerContextConfig,
    LoggerParent,
    MaskedValueFilter,
    ObjectLoggerConfig,
    ObjectLoggerContexts,
    field,
)
from admin_helper.objects.field import object_dataclass
from admin_helper.objects.registry import _ObjectRegistry, object_registry
from admin_helper.objects.sensitive_value_registry import _sensitive_value_registry


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _build_file_logger_registry(
    log_path: Path,
    *,
    max_bytes: int = 0,
    backup_count: int = 0,
    archive_backup_count: int = 0,
    contexts: ObjectLoggerContexts | None = None,
) -> tuple[_ObjectRegistry, Any]:
    registry = _ObjectRegistry()

    @object_dataclass
    class LoggedObject(BaseObject):
        secret: str = field(default="object-secret", masked=True)

    registry._register(
        name=_unique("logged"),
        cls=LoggedObject,
        abstract=False,
        constructor_kwargs={
            "logger_config": ObjectLoggerConfig(
                parent=LoggerParent.NONE,
                propagate=False,
                level=logging.DEBUG,
                console=False,
                file=True,
                file_path=log_path,
                file_level=logging.DEBUG,
                file_format="%(levelname)s|%(log_context)s|%(message)s|%(log_context_data)s",
                file_max_bytes=max_bytes,
                file_backup_count=backup_count,
                file_archive_backup_count=archive_backup_count,
                contexts=contexts or ObjectLoggerContexts(),
            )
        },
    )
    registry.instantiate_all()
    return registry, cast(Any, registry.instances()[0])


def _flush(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        handler.flush()


def test_file_logging_writes_levels_context_and_masked_values(tmp_path: Path) -> None:
    path = tmp_path / "object.log"
    contexts = ObjectLoggerContexts(
        {
            "task": LoggerContextConfig(
                level=logging.DEBUG,
                file_level=logging.INFO,
                file_format="CTX|%(log_context)s|%(message)s|%(log_context_data)s",
            )
        }
    )
    _, obj = _build_file_logger_registry(path, contexts=contexts)

    obj.logger.debug("default debug")
    obj.logger.info("secret=%s", obj.secret)
    with obj.logger.context("task", job="import", token=obj.secret):
        obj.logger.debug("context debug filtered")
        obj.logger.info("context info %s", obj.secret)
    _flush(obj.logger)

    content = path.read_text(encoding="utf-8")
    masked = object_registry.config.fields.masked_value
    assert "DEBUG|-|default debug|-" in content
    assert f"INFO|-|secret={masked}|-" in content
    assert f"CTX|task|context info {masked}|job: 'import', token: '{masked}'" in content
    assert "context debug filtered" not in content
    assert obj.secret not in content


def test_nested_logging_context_uses_most_specific_config_and_merges_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested.log"
    contexts = ObjectLoggerContexts(
        {
            "operation": LoggerContextConfig(
                file_level=logging.WARNING,
                file_format="PARENT|%(log_context)s|%(message)s|%(log_context_data)s",
            ),
            "operation.step": LoggerContextConfig(
                file_level=logging.DEBUG,
                file_format="CHILD|%(log_context)s|%(message)s|%(log_context_data)s",
            ),
        }
    )
    _, obj = _build_file_logger_registry(path, contexts=contexts)

    with obj.logger.context("operation", request="one"):
        obj.logger.info("parent filtered")
        with obj.logger.context("step", request="two", item=3):
            obj.logger.debug("nested accepted")
    _flush(obj.logger)

    content = path.read_text(encoding="utf-8")
    assert "parent filtered" not in content
    assert "CHILD|operation.step|nested accepted|request: 'two', item: 3" in content


def test_disabled_logging_context_suppresses_records(tmp_path: Path) -> None:
    path = tmp_path / "disabled.log"
    contexts = ObjectLoggerContexts()
    contexts.disable("silent")
    _, obj = _build_file_logger_registry(path, contexts=contexts)

    obj.logger.info("visible")
    with obj.logger.context("silent"):
        obj.logger.critical("hidden")
    _flush(obj.logger)

    content = path.read_text(encoding="utf-8")
    assert "visible" in content
    assert "hidden" not in content


def test_file_rotation_retains_numbered_backups(tmp_path: Path) -> None:
    path = tmp_path / "rotate.log"
    _, obj = _build_file_logger_registry(path, max_bytes=80, backup_count=2)

    for index in range(20):
        obj.logger.info("record-%02d-%s", index, "x" * 30)
    _flush(obj.logger)

    assert path.exists()
    assert (tmp_path / "rotate.log.1").exists()
    assert (tmp_path / "rotate.log.2").exists()
    assert not (tmp_path / "rotate.log.3").exists()


def test_file_rotation_archives_full_backup_sets(tmp_path: Path) -> None:
    path = tmp_path / "archive.log"
    _, obj = _build_file_logger_registry(
        path,
        max_bytes=70,
        backup_count=2,
        archive_backup_count=2,
    )

    for index in range(30):
        obj.logger.info("archive-%02d-%s", index, "y" * 35)
    _flush(obj.logger)

    archives = sorted(tmp_path.glob("archive_logs.*.tar.gz"))
    assert 1 <= len(archives) <= 2
    with tarfile.open(archives[0], "r:gz") as archive:
        names = archive.getnames()
    assert any(name.endswith("archive.log.1") for name in names)
    assert any(name.endswith("archive.log.2") for name in names)


def test_masked_value_filter_sanitizes_standard_logger_messages_and_arguments() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(MaskedValueFilter(None, "custom"))
    logger = logging.Logger(_unique("standard"), logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False

    cache = _sensitive_value_registry()
    cache.register("global-secret")
    logger.info("value=%s", "global-secret")

    assert stream.getvalue().strip() == (
        f"value={object_registry.config.fields.masked_value}"
    )


def test_object_logger_masks_custom_handler_and_can_respect_local_disable() -> None:
    stream = io.StringIO()

    def factory() -> logging.Handler:
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s|%(log_context_data)s"))
        return handler

    registry = _ObjectRegistry()

    @object_dataclass
    class LoggedObject(BaseObject):
        secret: str = field(default="custom-secret", masked=True)

    registry._register(
        name=_unique("custom"),
        cls=LoggedObject,
        abstract=False,
        constructor_kwargs={
            "logger_config": ObjectLoggerConfig(
                parent=LoggerParent.NONE,
                propagate=False,
                level=logging.DEBUG,
                console=False,
                file=False,
                handler_factories=(factory,),
                masking=True,
                custom_handler_masking=True,
            )
        },
    )
    registry.instantiate_all()
    obj = cast(Any, registry.instances()[0])

    with obj.logger.context("event", token=obj.secret):
        obj.logger.info("secret=%s", obj.secret)
    assert obj.secret not in stream.getvalue()

    stream.seek(0)
    stream.truncate(0)
    obj.logger_config.custom_handler_masking = False
    obj.logger.info("secret=%s", obj.secret)
    assert obj.secret in stream.getvalue()


def test_logger_parent_and_inherited_configuration_update_recursively() -> None:
    registry = _ObjectRegistry()

    @object_dataclass
    class Root(BaseObject):
        pass

    @object_dataclass
    class Child(BaseObject):
        pass

    @object_dataclass
    class Grandchild(BaseObject):
        pass

    registry._register(
        name=_unique("logger_root"),
        cls=Root,
        abstract=False,
        constructor_kwargs={
            "logger_config": ObjectLoggerConfig(
                parent=LoggerParent.NONE,
                propagate=False,
                level=logging.INFO,
                console=False,
                file=False,
            )
        },
    )
    registry._register(name="child", cls=Child, abstract=False, parent=Root)
    registry._register(name="grandchild", cls=Grandchild, abstract=False, parent=Child)
    registry.instantiate_all()
    root = registry.get_by_type(Root)[0]
    child = registry.get_by_type(Child)[0]
    grandchild = registry.get_by_type(Grandchild)[0]

    assert child.logger.parent is root.logger
    assert grandchild.logger.parent is child.logger
    assert child._resolved_logger_config.default_level == logging.INFO
    assert grandchild._resolved_logger_config.default_level == logging.INFO

    root.logger_config.level = logging.DEBUG
    assert child._resolved_logger_config.default_level == logging.DEBUG
    assert grandchild._resolved_logger_config.default_level == logging.DEBUG

    child.logger_config.level = logging.WARNING
    assert child._resolved_logger_config.default_level == logging.WARNING
    assert grandchild._resolved_logger_config.default_level == logging.WARNING

    root.logger_config.level = logging.ERROR
    assert child._resolved_logger_config.default_level == logging.WARNING
    assert grandchild._resolved_logger_config.default_level == logging.WARNING


def test_explicit_logger_parent_variants_resolve_correctly() -> None:
    registry = _ObjectRegistry()

    @object_dataclass
    class Root(BaseObject):
        pass

    @object_dataclass
    class Child(BaseObject):
        pass

    named_parent = logging.getLogger(_unique("named_parent"))
    root_name = _unique("parent_root")
    registry._register(
        name=root_name,
        cls=Root,
        abstract=False,
        constructor_kwargs={
            "logger_config": ObjectLoggerConfig(parent=LoggerParent.ROOT)
        },
    )
    registry._register(
        name="child",
        cls=Child,
        abstract=False,
        parent=Root,
        constructor_kwargs={
            "logger_config": ObjectLoggerConfig(parent=named_parent.name)
        },
    )
    registry.instantiate_all()
    root = registry.get_by_type(Root)[0]
    child = registry.get_by_type(Child)[0]

    assert root.logger.parent is logging.getLogger()
    assert child.logger.parent is named_parent

    child.logger_config.parent = LoggerParent.NONE
    assert child.logger.parent is None
    assert child.logger.propagate is False
