from __future__ import annotations

from admin_helper.objects.config import SensitiveValueFilterMode
from admin_helper.objects.formatting import _format_display_value
from admin_helper.objects.runtime import (
    _field_framework_config,
    _masking_framework_config,
)
from admin_helper.objects.registry import object_registry
from admin_helper.objects.sensitive_value_registry import _sensitive_value_registry


def test_helpers_use_registry_owned_configuration() -> None:
    object_registry.config.fields.masked_value = "<redacted>"
    object_registry.config.fields.not_set_value = "<unset>"

    assert _field_framework_config() is object_registry.config.fields
    assert _masking_framework_config() is object_registry.config.logging.masking
    assert _format_display_value("secret", masked=True) == "<redacted>"
    assert _format_display_value(None, masked=True) == "<unset>"


def test_sensitive_values_use_registry_owned_cache() -> None:
    cache = _sensitive_value_registry()

    assert cache is object_registry._sensitive_values

    object_registry.config.fields.masked_value = "[hidden]"
    object_registry.config.logging.masking.enabled = True
    object_registry.config.logging.masking.mode = SensitiveValueFilterMode.FIELDS
    cache.register("very-secret-value")

    assert cache.sanitize("token=very-secret-value") == "token=[hidden]"


def test_disabling_masking_is_observed_immediately() -> None:
    cache = _sensitive_value_registry()
    cache.register("very-secret-value")
    object_registry.config.logging.masking.enabled = False

    assert cache.sanitize("very-secret-value") == "very-secret-value"
