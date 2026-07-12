from __future__ import annotations

import pytest

from admin_helper.exceptions import (
    BlueprintError,
    BlueprintIncludeCycleError,
    DuplicateBlueprintNameError,
)
from admin_helper.objects import Application, BaseObject, Blueprint


def test_blueprint_builds_root_and_child_definitions() -> None:
    """Verify that a blueprint transfers its object graph into an application.

    Created: 2026-07-12
    Purpose: Confirm direct blueprint registrations preserve internal parents.
    """

    blueprint = Blueprint("services", title="Services")

    @blueprint.register(name="service_root")
    class ServiceRoot(BaseObject):
        pass

    @blueprint.register(name="worker", parent=ServiceRoot)
    class Worker(BaseObject):
        pass

    app = Application()
    app.include_blueprint(blueprint)
    app.build()

    root = app.get_by_name("service_root", ServiceRoot)
    worker = app.get_by_name("service_root.worker", Worker)

    assert root.children == (worker,)
    assert worker.parent is root
    assert app.get_blueprint("services") is blueprint
    assert app.blueprints_for_class(Worker) == (blueprint,)


def test_blueprint_parent_binding_attaches_all_resolved_roots() -> None:
    """Verify that an include parent replaces only blueprint root parents.

    Created: 2026-07-12
    Purpose: Attach all root definitions while retaining internal relationships.
    """

    app = Application()

    @app.register(name="container")
    class Container(BaseObject):
        pass

    blueprint = Blueprint("features")

    @blueprint.register(name="first")
    class First(BaseObject):
        pass

    @blueprint.register(name="child", parent=First)
    class Child(BaseObject):
        pass

    @blueprint.register(name="second")
    class Second(BaseObject):
        pass

    app.include_blueprint(blueprint, parent=Container)
    app.build()

    container = app.get_by_name("container", Container)
    first = app.get_by_name("container.first", First)
    child = app.get_by_name("container.first.child", Child)
    second = app.get_by_name("container.second", Second)

    assert container.children == (first, second)
    assert child.parent is first


def test_nested_blueprints_resolve_depth_first_and_deduplicate_identity() -> None:
    """Verify nested blueprints are included once in deterministic order.

    Created: 2026-07-12
    Purpose: Support reusable nested definition groups without duplicate classes.
    """

    shared = Blueprint("shared")
    first = Blueprint("first")
    second = Blueprint("second")
    root = Blueprint("root")

    @shared.register(name="shared_object")
    class SharedObject(BaseObject):
        pass

    @first.register(name="first_object")
    class FirstObject(BaseObject):
        pass

    @second.register(name="second_object")
    class SecondObject(BaseObject):
        pass

    first.include(shared)
    second.include(shared)
    root.include(first)
    root.include(second)

    app = Application()
    app.include_blueprint(root)
    app.build()

    assert app.blueprints == (shared, first, second, root)
    assert isinstance(app.get_by_name("shared_object"), SharedObject)
    assert isinstance(app.get_by_name("first_object"), FirstObject)
    assert isinstance(app.get_by_name("second_object"), SecondObject)


def test_blueprint_include_rejects_direct_and_indirect_cycles() -> None:
    """Verify blueprint definitions cannot create recursive include graphs.

    Created: 2026-07-12
    Purpose: Prevent infinite recursive resolution during application inclusion.
    """

    first = Blueprint("first")
    second = Blueprint("second")
    third = Blueprint("third")

    with pytest.raises(BlueprintIncludeCycleError):
        first.include(first)

    first.include(second)
    second.include(third)

    with pytest.raises(BlueprintIncludeCycleError):
        third.include(first)


def test_application_rejects_different_blueprints_with_the_same_name() -> None:
    """Verify blueprint names remain unambiguous inside one application.

    Created: 2026-07-12
    Purpose: Keep future configuration and diagnostic lookup deterministic.
    """

    first = Blueprint("duplicate")
    second = Blueprint("duplicate")
    wrapper = Blueprint("wrapper")
    wrapper.include(first)
    wrapper.include(second)

    app = Application()

    with pytest.raises(DuplicateBlueprintNameError):
        app.include_blueprint(wrapper)

    assert app.blueprints == ()
    assert app.instances() == ()


def test_blueprint_registration_conflicts_are_transactional() -> None:
    """Verify a conflicting graph adds none of its preceding definitions.

    Created: 2026-07-12
    Purpose: Prevent partial application mutation after blueprint validation fails.
    """

    app = Application()

    @app.register(name="existing")
    class Existing(BaseObject):
        pass

    blueprint = Blueprint("conflicting")

    @blueprint.register(name="new_object")
    class NewObject(BaseObject):
        pass

    @blueprint.register(name="existing")
    class ConflictingObject(BaseObject):
        pass

    with pytest.raises(BlueprintError):
        app.include_blueprint(blueprint)

    with pytest.raises(KeyError):
        app.get_class("new_object")
    assert app.blueprints == ()


def test_repeated_include_is_idempotent_but_parent_binding_is_stable() -> None:
    """Verify one blueprint can be included repeatedly only with one parent.

    Created: 2026-07-12
    Purpose: Avoid duplicate definitions and ambiguous parent rebinding.
    """

    app = Application()

    @app.register(name="first_parent")
    class FirstParent(BaseObject):
        pass

    @app.register(name="second_parent")
    class SecondParent(BaseObject):
        pass

    blueprint = Blueprint("feature")

    @blueprint.register(name="feature_object")
    class FeatureObject(BaseObject):
        pass

    assert app.include_blueprint(blueprint, parent=FirstParent) is blueprint
    assert app.include_blueprint(blueprint, parent=FirstParent) is blueprint

    with pytest.raises(BlueprintError):
        app.include_blueprint(blueprint, parent=SecondParent)


def test_blueprint_cannot_be_included_after_build() -> None:
    """Verify static phase-two inclusion closes after the initial build.

    Created: 2026-07-12
    Purpose: Preserve current registry guarantees until dynamic creation exists.
    """

    app = Application()
    app.build()

    with pytest.raises(BlueprintError):
        app.include_blueprint(Blueprint("late"))


def test_nested_blueprint_can_be_included_after_shared_dependency() -> None:
    """Verify an already included dependency is reused by a later wrapper.

    Created: 2026-07-12
    Purpose: Support modular composition without registering shared classes twice.
    """

    shared = Blueprint("shared_dependency")
    wrapper = Blueprint("wrapper_with_dependency")

    @shared.register(name="shared_dependency_object")
    class SharedDependencyObject(BaseObject):
        pass

    @wrapper.register(name="wrapper_object")
    class WrapperObject(BaseObject):
        pass

    wrapper.include(shared)

    app = Application()
    app.include_blueprint(shared)
    app.include_blueprint(wrapper)
    app.build()

    assert app.blueprints == (shared, wrapper)
    assert isinstance(
        app.get_by_name("shared_dependency_object"), SharedDependencyObject
    )
    assert isinstance(app.get_by_name("wrapper_object"), WrapperObject)
