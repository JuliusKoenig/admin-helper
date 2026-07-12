from __future__ import annotations

from admin_helper.objects.config import SensitiveValueFilterMode
from admin_helper.objects.registry import object_registry
from admin_helper.objects.sensitive_value_registry import _sensitive_value_registry


def test_sensitive_value_reference_counting() -> None:
    """Test description.

    Created: 2026-07-12
    Purpose: Verify the following behavior: sensitive value reference counting.
    """
    cache = _sensitive_value_registry()
    cache.register("shared-secret")
    cache.register("shared-secret")

    cache.unregister("shared-secret")
    assert cache.sanitize("shared-secret") == object_registry.config.fields.masked_value

    cache.unregister("shared-secret")
    assert cache.sanitize("shared-secret") == "shared-secret"


def test_nested_values_are_registered_and_sanitized() -> None:
    """Test description.

    Created: 2026-07-12
    Purpose: Verify the following behavior: nested values are registered and sanitized.
    """
    cache = _sensitive_value_registry()
    cache.register("abc123")
    cache.register("second-secret")

    sanitized = cache.sanitize(
        {
            "message": "token=abc123",
            "items": ["second-secret", "public"],
        }
    )

    masked = object_registry.config.fields.masked_value
    assert sanitized == {
        "message": f"token={masked}",
        "items": [masked, "public"],
    }


def test_disabled_mode_does_not_replace_registered_values() -> None:
    """Test description.

    Created: 2026-07-12
    Purpose: Verify the following behavior: disabled mode does not replace registered values.
    """
    cache = _sensitive_value_registry()
    cache.register("secret")
    object_registry.config.logging.masking.mode = SensitiveValueFilterMode.DISABLED

    assert cache.sanitize("secret") == "secret"
