from __future__ import annotations

from collections.abc import Iterator

import pytest

from admin_helper.objects.registry import object_registry
from admin_helper.objects.sensitive_value_registry import _sensitive_value_registry


@pytest.fixture(autouse=True)
def restore_runtime_configuration() -> Iterator[None]:
    """Restore mutable global framework configuration after every test."""

    fields_config = object_registry.config.fields
    masking_config = object_registry.config.logging.masking
    original_values = {
        "masked_value": fields_config.masked_value,
        "not_set_value": fields_config.not_set_value,
        "masking_enabled": masking_config.enabled,
        "masking_mode": masking_config.mode,
    }
    _sensitive_value_registry().clear()

    try:
        yield
    finally:
        with object_registry.config.batch_update():
            fields_config.masked_value = original_values["masked_value"]
            fields_config.not_set_value = original_values["not_set_value"]
            masking_config.enabled = original_values["masking_enabled"]
            masking_config.mode = original_values["masking_mode"]
        _sensitive_value_registry().clear()
