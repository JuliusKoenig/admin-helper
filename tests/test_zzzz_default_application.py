from __future__ import annotations

import pytest

from admin_helper.objects import (
    Application,
    BaseObject,
    application,
    get_default_application,
    object_registry,
    register,
    set_default_application,
)


def test_default_application_switch_updates_existing_public_handles() -> None:
    """Verify existing imports follow a newly selected default application.

    Created: 2026-07-12
    Purpose: Prevent import order from pinning convenience APIs to an old runtime.
    """

    previous = get_default_application()
    replacement = Application()

    try:
        returned = set_default_application(replacement)

        @register(name="switched_default_root")
        class SwitchedDefaultRoot(BaseObject):
            pass

        application.build()
        instance = object_registry.get_by_name(
            "switched_default_root", SwitchedDefaultRoot
        )

        assert returned is previous
        assert get_default_application() is replacement
        assert application.config is replacement.config
        assert application.instances() == (instance,)
        assert object_registry.instances() == (instance,)
    finally:
        set_default_application(previous)


def test_application_bound_registration_ignores_default_switch() -> None:
    """Verify explicit application decorators remain bound to their application.

    Created: 2026-07-12
    Purpose: Keep explicit runtimes isolated from process-wide convenience state.
    """

    previous = get_default_application()
    explicit = Application()
    replacement = Application()

    try:
        decorator = explicit.register(name="explicit_root")
        set_default_application(replacement)

        @decorator
        class ExplicitRoot(BaseObject):
            pass

        explicit.build()
        instance = explicit.get_by_name("explicit_root", ExplicitRoot)

        assert explicit.instances() == (instance,)
        assert replacement.instances() == ()
    finally:
        set_default_application(previous)


def test_set_default_application_rejects_non_application_values() -> None:
    """Verify invalid default application assignments fail without mutation.

    Created: 2026-07-12
    Purpose: Preserve a valid global convenience runtime after caller mistakes.
    """

    previous = get_default_application()

    with pytest.raises(TypeError):
        set_default_application(object())  # type: ignore[arg-type]

    assert get_default_application() is previous
