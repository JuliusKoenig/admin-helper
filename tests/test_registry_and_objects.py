from __future__ import annotations

import pytest

from admin_helper.exceptions import BroadcastException
from admin_helper.objects import (
    BaseObject,
    computed_field,
    field,
    object_registry,
    register,
)
from admin_helper.objects.field import object_dataclass


@register(abstract=True, name="abstract_service")
class AbstractService(BaseObject):
    pass


@register(name="test_app")
class ExampleApplication(BaseObject):
    environment: str = field(default="test", display=True, read_only=True)


@register(name="service", parent=ExampleApplication)
class ExampleService(BaseObject):
    secret: str = field(default="service-secret", masked=True, display=True)
    calls: list[str] = field(default_factory=list)

    @computed_field(display=True)
    def endpoint(self) -> str:
        return f"/{self.registration_name}"

    def record(self, value: str) -> None:
        self.calls.append(value)

    def fail(self) -> None:
        raise ValueError("expected failure")


@register(name="worker", parent=ExampleService)
class ExampleWorker(BaseObject):
    calls: list[str] = field(default_factory=list)

    def record(self, value: str) -> None:
        self.calls.append(value)


@register(name="second_app")
class SecondApplication(BaseObject):
    pass


@register(name="service_two", parent=SecondApplication)
class SecondService(BaseObject):
    pass


@pytest.fixture(scope="module", autouse=True)
def build_registry() -> None:
    object_registry.instantiate_all()


def test_abstract_registration_is_publicly_detectable() -> None:
    from admin_helper.objects import is_abstract

    assert is_abstract(AbstractService) is True
    assert object_registry.get_by_type(AbstractService) == ()


def test_registry_builds_expected_tree() -> None:
    (app,) = object_registry.get_by_type(ExampleApplication)
    (service,) = object_registry.get_by_type(ExampleService)
    (worker,) = object_registry.get_by_type(ExampleWorker)

    assert app.name == "test_app"
    assert service.name == "test_app.service"
    assert worker.name == "test_app.service.worker"
    assert service.parent is app
    assert worker.parent is service
    assert app.children == (service,)
    assert app.children_flat == (service, worker)
    assert worker.root_parent is app


def test_name_and_type_lookups_return_same_instances() -> None:
    (service,) = object_registry.get_by_type(ExampleService)

    assert object_registry.get_by_name("test_app.service") is service
    assert object_registry.get_by_name("test_app.service", ExampleService) is service
    assert object_registry.find_by_name("test_app.*") == (service,)
    assert object_registry.find_by_name("test_app.**") == (
        object_registry.get_by_type(ExampleApplication)[0],
        service,
        object_registry.get_by_type(ExampleWorker)[0],
    )


def test_unique_suffix_lookup_resolves_object() -> None:
    (worker,) = object_registry.get_by_type(ExampleWorker)

    assert object_registry.get_by_name("worker") is worker


def test_read_only_field_cannot_be_changed_after_initialization() -> None:
    (app,) = object_registry.get_by_type(ExampleApplication)

    with pytest.raises(AttributeError, match="read_only"):
        app.environment = "production"


def test_direct_instantiation_is_forbidden() -> None:
    with pytest.raises(RuntimeError, match="must be instantiated through"):
        ExampleService()


def test_string_representation_masks_secret_and_includes_computed_field() -> None:
    (service,) = object_registry.get_by_type(ExampleService)
    rendered = str(service)

    assert "service-secret" not in rendered
    assert object_registry.config.fields.masked_value in rendered
    assert "endpoint='/service'" in rendered


def test_broadcast_calls_method_on_descendants() -> None:
    (app,) = object_registry.get_by_type(ExampleApplication)
    (service,) = object_registry.get_by_type(ExampleService)
    (worker,) = object_registry.get_by_type(ExampleWorker)
    service.calls.clear()
    worker.calls.clear()

    app.broadcast_call("record", value="reload")
    service.broadcast_call("record", value="reload")

    assert service.calls == ["reload"]
    assert worker.calls == ["reload"]


def test_broadcast_wraps_failures() -> None:
    (app,) = object_registry.get_by_type(ExampleApplication)

    with pytest.raises(BroadcastException):
        app.broadcast_call("fail")


def test_framework_initialization_finishes_after_tree_attachment() -> None:
    (app,) = object_registry.get_by_type(ExampleApplication)
    (service,) = object_registry.get_by_type(ExampleService)

    assert service.parent is app
    assert app.children.count(service) == 1
    assert service.status.name == "READY"
    assert service.logger is not None


def test_object_local_child_navigation() -> None:
    (app,) = object_registry.get_by_type(ExampleApplication)
    (service,) = object_registry.get_by_type(ExampleService)
    (worker,) = object_registry.get_by_type(ExampleWorker)

    assert app.get_child_by_name("service") is service
    assert app.get_child_by_name("service.worker", ExampleWorker) is worker
    assert app.get_child_by_name("test_app.service.worker") is worker
    assert service.get_child_by_type(ExampleWorker) == (worker,)
    assert service.get_child_by_name("missing") is None


def test_objects_from_different_registries_cannot_be_attached() -> None:
    from admin_helper.objects.registry import _ObjectRegistry

    first_registry = _ObjectRegistry()
    second_registry = _ObjectRegistry()

    @object_dataclass
    class FirstRoot(BaseObject):
        pass

    @object_dataclass
    class SecondRoot(BaseObject):
        pass

    first_registry._register(name="phase4_first", cls=FirstRoot, abstract=False)
    second_registry._register(name="phase4_second", cls=SecondRoot, abstract=False)
    first_registry.instantiate_all()
    second_registry.instantiate_all()

    (first,) = first_registry.get_by_type(FirstRoot)
    (second,) = second_registry.get_by_type(SecondRoot)

    with pytest.raises(ValueError, match="same object registry"):
        first.add_child(second)


def test_failed_child_construction_leaves_no_tree_or_index_entry() -> None:
    from admin_helper.objects.registry import _ObjectRegistry

    registry = _ObjectRegistry()
    created_roots: list[BaseObject] = []

    @object_dataclass
    class Root(BaseObject):
        def __post_init__(self) -> None:
            super().__post_init__()
            created_roots.append(self)

    @object_dataclass
    class BrokenChild(BaseObject):
        def _finalize_framework_initialization(self) -> None:
            super()._finalize_framework_initialization()
            raise RuntimeError("broken child")

    registry._register(name="phase4_root", cls=Root, abstract=False)
    registry._register(
        name="phase4_broken",
        cls=BrokenChild,
        abstract=False,
        parent=Root,
    )

    with pytest.raises(Exception, match="broken child"):
        registry.instantiate_all()

    assert registry.instances() == ()
    assert registry.get_by_type(Root) == ()
    assert registry.get_by_type(BrokenChild) == ()
    assert created_roots[0].children == ()

