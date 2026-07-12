"""Warning categories emitted by the admin-helper framework."""


class AdminHelperWarning(UserWarning):
    """Base warning for every warning emitted by admin-helper."""


class ObjectRegistryWarning(AdminHelperWarning):
    """Base warning for object-registry configuration issues."""


class FieldConfigurationWarning(ObjectRegistryWarning):
    """Warn about a field conflict that the framework resolved safely."""


class LoggerConfigurationWarning(ObjectRegistryWarning):
    """Warn about a non-fatal logger configuration inconsistency."""


class SensitiveValueWarning(ObjectRegistryWarning):
    """Warn about a potentially unsafe sensitive-value configuration."""
