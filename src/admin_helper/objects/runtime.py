"""Runtime bindings shared by object-framework components."""

from admin_helper.objects.config import (
    FieldFrameworkConfig,
    MaskingFrameworkConfig,
    ObjectRegistryConfig,
)

_bootstrap_field_config = FieldFrameworkConfig()
_bootstrap_masking_config = MaskingFrameworkConfig()
_registry_config: ObjectRegistryConfig | None = None


def _bind_registry_config(config: ObjectRegistryConfig) -> None:
    """Bind helpers to the configuration owned by the active registry."""

    global _registry_config
    _registry_config = config


def _field_framework_config() -> FieldFrameworkConfig:
    """Return the field configuration of the active registry."""

    if _registry_config is None:
        return _bootstrap_field_config
    return _registry_config.fields


def _masking_framework_config() -> MaskingFrameworkConfig:
    """Return the masking configuration of the active registry."""

    if _registry_config is None:
        return _bootstrap_masking_config
    return _registry_config.logging.masking
