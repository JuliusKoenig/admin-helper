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
