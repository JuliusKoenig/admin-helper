from __future__ import annotations

from admin_helper.objects import Application, BaseObject, application, object_registry


def test_default_application_wraps_legacy_registry() -> None:
    """Verify that the default facade and legacy registry share one runtime.

    Created: 2026-07-12
    Purpose: Preserve compatibility while Application becomes the public facade.
    """

    assert application.config is object_registry.config
    assert application.instances() == object_registry.instances()
    assert application.root_objects() == object_registry.root_objects()
    assert application.built is object_registry.built


def test_application_registers_builds_and_queries_isolated_objects() -> None:
    """Verify registration, build, and lookup through an isolated Application.

    Created: 2026-07-12
    Purpose: Confirm the facade delegates one complete static runtime workflow.
    """

    app = Application()

    @app.register(name="application_test_root")
    class ApplicationTestRoot(BaseObject):
        pass

    @app.register(name="child", parent=ApplicationTestRoot)
    class ApplicationTestChild(BaseObject):
        pass

    app.build()

    root = app.get_by_name("application_test_root", ApplicationTestRoot)
    child = app.get_by_name("application_test_root.child", ApplicationTestChild)

    assert app.built is True
    assert root.children == (child,)
    assert child.parent is root
    assert app.get_by_type(ApplicationTestChild) == (child,)
    assert app.find_by_name("application_test_root.*") == (child,)
    assert "application_test_root.child" in app


def test_application_instances_are_isolated() -> None:
    """Verify that separate applications own separate definitions and indexes.

    Created: 2026-07-12
    Purpose: Establish the namespace boundary required by future runtimes.
    """

    first = Application()
    second = Application()

    @first.register(name="shared_name")
    class FirstObject(BaseObject):
        pass

    @second.register(name="shared_name")
    class SecondObject(BaseObject):
        pass

    first.build()
    second.build()

    first_object = first.get_by_name("shared_name", FirstObject)
    second_object = second.get_by_name("shared_name", SecondObject)

    assert first_object is not second_object
    assert first.instances() == (first_object,)
    assert second.instances() == (second_object,)
