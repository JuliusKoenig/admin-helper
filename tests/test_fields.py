from __future__ import annotations

from dataclasses import dataclass, fields as dataclass_fields

import pytest

from admin_helper.objects.field import (
    ObjectFieldSource,
    computed_field,
    field,
    fields,
)
from admin_helper.warnings import FieldConfigurationWarning


@dataclass
class ExampleFields:
    visible: str = field(default="value", display=True, title="Visible")
    password: str = field(default="secret", masked=True, display=True)
    _cache: dict[str, str] = field(internal=True, default_factory=dict)

    @computed_field(display=True)
    def summary(self) -> str:
        return self.visible.upper()

    @computed_field(as_property=False)
    def explicit_computation(self) -> str:
        return "computed"


def test_field_metadata_controls_dataclass_flags() -> None:
    definitions = {definition.name: definition for definition in fields(ExampleFields)}
    raw_fields = {
        definition.name: definition for definition in dataclass_fields(ExampleFields)
    }

    assert definitions["visible"].info.display is True
    assert definitions["visible"].info.title == "Visible"
    assert raw_fields["password"].repr is False
    assert raw_fields["_cache"].init is False
    assert raw_fields["_cache"].repr is False
    assert raw_fields["_cache"].compare is False


def test_fields_discovers_stored_and_computed_fields() -> None:
    instance = ExampleFields()
    definitions = {definition.name: definition for definition in fields(instance)}

    assert definitions["visible"].source is ObjectFieldSource.DATACLASS
    assert definitions["summary"].source is ObjectFieldSource.COMPUTED
    assert definitions["summary"].get_value(instance) == "VALUE"
    assert definitions["explicit_computation"].get_value(instance) == "computed"


def test_fields_can_filter_by_metadata() -> None:
    instance = ExampleFields()

    assert {item.name for item in fields(instance, display=True)} == {
        "visible",
        "password",
        "summary",
    }
    assert {item.name for item in fields(instance, masked=True)} == {"password"}
    assert {item.name for item in fields(instance, internal=True)} == {"_cache"}


def test_reserved_metadata_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="reserved"):
        field(metadata={"field_info": "invalid"})


def test_internal_field_options_are_overridden_with_warnings() -> None:
    with pytest.warns(FieldConfigurationWarning) as warnings:
        configured = field(
            internal=True,
            init=True,
            repr=True,
            compare=True,
            display=True,
            default=None,
        )

    assert len(warnings) == 4
    assert configured.init is False
    assert configured.repr is False
    assert configured.compare is False
