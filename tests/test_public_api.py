from __future__ import annotations

from dataclasses import is_dataclass

import admin_helper.objects as objects


def test_expected_public_api_is_exported() -> None:
    """Test description.

    Created: 2026-07-12
    Purpose: Verify the following behavior: expected public api is exported.
    """
    expected_names = {
        "BaseObject",
        "FieldInfo",
        "Formatter",
        "MaskedValueFilter",
        "ObjectFieldDefinition",
        "ObjectLogger",
        "ObjectRegistryConfig",
        "SensitiveValueFilterMode",
        "computed_field",
        "dataclass",
        "field",
        "fields",
        "is_abstract",
        "object_registry",
        "register",
    }

    assert expected_names <= set(objects.__all__)
    assert all(hasattr(objects, name) for name in expected_names)


def test_public_dataclass_supports_framework_fields() -> None:
    """Test description.

    Created: 2026-07-12
    Purpose: Verify the following behavior: public dataclass supports framework fields.
    """
    @objects.dataclass
    class Configuration:
        token: str = objects.field(default="secret", masked=True)

    assert is_dataclass(Configuration)
    assert objects.fields(Configuration)[0].info.masked is True
