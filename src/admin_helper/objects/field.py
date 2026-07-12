import warnings
from dataclasses import (
    dataclass,
    field as dataclass_field,
    fields as dataclass_fields,
    Field,
    MISSING,
)
from enum import Enum
from typing import Iterable, Any, Callable, Mapping, get_type_hints

from admin_helper.warnings import FieldConfigurationWarning

FIELD_INFO_METADATA_KEY = "field_info"
DEFAULT_MASKED_FIELD_VALUE = "<MASKED>"
DEFAULT_NOT_SET_FIELD_VALUE = "<NOT SET>"
DEFAULT_EMPTY_FIELD_VALUES: tuple[Any, ...] = (
    None,
    "",
    b"",
    (),
    [],
    {},
    set(),
    frozenset(),
)


@dataclass(frozen=True, slots=True)
class FieldInfo:
    """
    Store framework metadata for one normal dataclass field.

    :param title:
        The human-readable title used by generated interfaces.

    :param description:
        The longer explanation used by generated interfaces.

    :param read_only:
        Whether the value becomes read-only after object initialization.

    :param internal:
        Whether the value is reserved for internal implementation details.

    :param masked:
        Whether the value must be hidden in visual output and managed logs.

    :param display:
        Whether the value is included in ``BaseObject.__str__``.

    :param empty_values:
        Additional values treated as not set for this field.
    """

    title: str | None = dataclass_field(default=None)
    description: str | None = dataclass_field(default=None)
    read_only: bool = dataclass_field(default=False)
    internal: bool = dataclass_field(default=False)
    masked: bool = dataclass_field(default=False)
    display: bool = dataclass_field(default=False)
    empty_values: Iterable[Any] = dataclass_field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ComputedFieldInfo(FieldInfo):
    """Store framework metadata for one computed field."""

    as_property: bool = True


class ObjectFieldSource(Enum):
    """Identify whether a queried field is stored or computed."""

    DATACLASS = "dataclass"
    COMPUTED = "computed"


@dataclass(frozen=True, slots=True)
class ObjectFieldDefinition:
    """Describe one stored or computed field exposed by an object class."""

    name: str
    owner: type[Any]
    annotation: Any
    info: FieldInfo
    source: ObjectFieldSource
    dataclass_field: Field[Any] | None = None
    descriptor: property | Callable[..., Any] | None = None

    def get_value(self, obj: Any) -> Any:
        """
        Read the field value from an object instance.

        :param obj:
            The object instance from which the field is read.

        :return:
            Returns the current field value.
        """

        value = getattr(obj, self.name)
        if self.source is ObjectFieldSource.COMPUTED and callable(value):
            return value()
        return value


_UNSET = object()


def field(
    default: Any = MISSING,
    default_factory: Any = MISSING,
    init: bool | object = _UNSET,
    repr: bool | object = _UNSET,
    compare: bool | object = _UNSET,
    hash: bool | None = None,
    kw_only: bool | Any = MISSING,
    read_only: bool = False,
    internal: bool = False,
    masked: bool = False,
    display: bool = False,
    title: str | None = None,
    description: str | None = None,
    empty_values: Iterable[Any] = (),
    metadata: Mapping[str, Any] | None = None,
) -> Field[Any]:
    """
    Define a framework-aware dataclass field.

    The switches are resolved centrally. Hard incompatibilities raise an
    exception, while harmless explicit options that must be overridden emit a
    warning.

    Examples:
        password: str = field(masked=True, display=True)
            Creates a displayed field whose actual value is never rendered.

        _cache: dict[str, Any] = field(
            internal=True,
            default_factory=dict,
        )
            Creates an implementation-only field excluded from the constructor.

    :param default:
        The default value assigned to the field.

    :param default_factory:
        The callable used to create a default value.

    :param init:
        Whether the field is included in the generated constructor.

    :param repr:
        Whether the field is included in the generated dataclass representation.

    :param compare:
        Whether the field participates in generated comparisons.

    :param hash:
        Whether the field participates in the generated hash.

    :param kw_only:
        Whether the field is keyword-only.

    :param read_only:
        Whether reassignment is blocked after object initialization.

    :param internal:
        Whether the field is reserved for internal implementation details.

    :param masked:
        Whether the value is hidden in visual output and managed logs.

    :param display:
        Whether the value is included in ``BaseObject.__str__``.

    :param title:
        The human-readable title stored in ``FieldInfo``.

    :param description:
        The longer description stored in ``FieldInfo``.

    :param empty_values:
        Additional field-specific values treated as not set.

    :param metadata:
        Additional metadata stored alongside ``FieldInfo``.

    :return:
        Returns the configured dataclass field.
    """

    if default is not MISSING and default_factory is not MISSING:
        raise ValueError("default and default_factory cannot be used together.")

    resolved_init = True if init is _UNSET else bool(init)
    resolved_repr = True if repr is _UNSET else bool(repr)
    resolved_compare = True if compare is _UNSET else bool(compare)

    if internal:
        if init is not _UNSET and resolved_init:
            warnings.warn(
                "Internal fields cannot be constructor parameters; init=True was ignored.",
                FieldConfigurationWarning,
                stacklevel=3,
            )
        if repr is not _UNSET and resolved_repr:
            warnings.warn(
                "Internal fields cannot appear in repr; repr=True was ignored.",
                FieldConfigurationWarning,
                stacklevel=3,
            )
        if compare is not _UNSET and resolved_compare:
            warnings.warn(
                "Internal fields do not participate in comparisons; compare=True was ignored.",
                FieldConfigurationWarning,
                stacklevel=3,
            )
        if display:
            warnings.warn(
                "Internal fields cannot be display fields; display=True was ignored.",
                FieldConfigurationWarning,
                stacklevel=3,
            )
        resolved_init = False
        resolved_repr = False
        resolved_compare = False
        display = False

    if masked and resolved_repr:
        if repr is not _UNSET:
            warnings.warn(
                "Masked fields cannot appear in the dataclass repr; repr=True was ignored.",
                FieldConfigurationWarning,
                stacklevel=3,
            )
        resolved_repr = False

    info = FieldInfo(
        title=title,
        description=description,
        read_only=read_only,
        internal=internal,
        masked=masked,
        display=display,
        empty_values=empty_values,
    )
    field_metadata = dict(metadata or {})
    if FIELD_INFO_METADATA_KEY in field_metadata:
        raise ValueError(
            f"metadata key {FIELD_INFO_METADATA_KEY!r} is reserved by the framework."
        )
    field_metadata[FIELD_INFO_METADATA_KEY] = info

    return dataclass_field(
        default=default,
        default_factory=default_factory,
        init=resolved_init,
        repr=resolved_repr,
        hash=hash,
        compare=resolved_compare,
        metadata=field_metadata,
        kw_only=kw_only,
    )


def computed_field(
    *,
    title: str | None = None,
    description: str | None = None,
    read_only: bool = True,
    internal: bool = False,
    masked: bool = False,
    display: bool = False,
    empty_values: Iterable[Any] = (),
    as_property: bool = True,
) -> Callable[[Callable[..., Any]], property | Callable[..., Any]]:
    """
    Mark a method as a computed object field.

    By default, the decorated method is converted into a property. Set
    ``as_property=False`` when callers should keep explicit control over when
    the computation runs; the global field-query API still discovers it.

    Examples:
        @computed_field(display=True)
        def address(self) -> str:
            return f"{self.host}:{self.port}"

    :param title:
        The human-readable title used by generated interfaces.

    :param description:
        The longer explanation used by generated interfaces.

    :param read_only:
        Whether the computed value is conceptually read-only.

    :param internal:
        Whether the computed value is an internal implementation detail.

    :param masked:
        Whether the computed value is hidden in visual output and managed logs.

    :param display:
        Whether the computed value is included in ``BaseObject.__str__``.

    :param empty_values:
        Additional values treated as not set.

    :param as_property:
        Whether the method is converted into a property automatically.

    :return:
        Returns a decorator for the computed method.
    """

    if internal and display:
        warnings.warn(
            "Internal computed fields cannot be display fields; display=True was ignored.",
            FieldConfigurationWarning,
            stacklevel=3,
        )
        display = False

    info = ComputedFieldInfo(
        title=title,
        description=description,
        read_only=read_only,
        internal=internal,
        masked=masked,
        display=display,
        empty_values=empty_values,
        as_property=as_property,
    )

    def decorator(func: Callable[..., Any]) -> property | Callable[..., Any]:
        setattr(func, "__object_computed_field_info__", info)
        return property(func) if as_property else func

    return decorator


def _field_info(dataclass_field: Field[Any]) -> FieldInfo:
    value = dataclass_field.metadata.get(FIELD_INFO_METADATA_KEY)
    return value if isinstance(value, FieldInfo) else FieldInfo()


def fields(
    obj_or_cls: Any,
    *,
    name: str | None = None,
    display: bool | None = None,
    masked: bool | None = None,
    internal: bool | None = None,
    read_only: bool | None = None,
    computed: bool | None = None,
) -> tuple[ObjectFieldDefinition, ...]:
    """
    Query stored and computed fields through one stable interface.

    Examples:
        get_object_fields(database, display=True)
            Returns all fields included in the concise representation.

        get_object_fields(DatabaseService, masked=True, computed=False)
            Returns only stored masked dataclass fields.

    :param obj_or_cls:
        The object instance or class whose fields are inspected.

    :param name:
        Optional exact field name.

    :param display:
        Optional filter for display fields.

    :param masked:
        Optional filter for masked fields.

    :param internal:
        Optional filter for internal fields.

    :param read_only:
        Optional filter for read-only fields.

    :param computed:
        ``True`` selects computed fields, ``False`` selects stored fields, and
        ``None`` includes both.

    :return:
        Returns an immutable tuple containing the matching field definitions.
    """

    cls = obj_or_cls if isinstance(obj_or_cls, type) else type(obj_or_cls)
    annotations: dict[str, Any] = {}
    for owner in reversed(cls.__mro__):
        try:
            annotations.update(get_type_hints(owner))
        except Exception:
            annotations.update(getattr(owner, "__annotations__", {}))

    result: list[ObjectFieldDefinition] = []
    if computed is not True:
        for item in dataclass_fields(cls):
            info = _field_info(item)
            result.append(
                ObjectFieldDefinition(
                    name=item.name,
                    owner=cls,
                    annotation=annotations.get(item.name, Any),
                    info=info,
                    source=ObjectFieldSource.DATACLASS,
                    dataclass_field=item,
                )
            )

    if computed is not False:
        seen: set[str] = set()
        for owner in cls.__mro__:
            for item_name, descriptor in vars(owner).items():
                if item_name in seen:
                    continue
                func = (
                    descriptor.fget if isinstance(descriptor, property) else descriptor
                )
                info = getattr(func, "__object_computed_field_info__", None)
                if not isinstance(info, ComputedFieldInfo):
                    continue
                seen.add(item_name)
                result.append(
                    ObjectFieldDefinition(
                        name=item_name,
                        owner=owner,
                        annotation=getattr(func, "__annotations__", {}).get(
                            "return", Any
                        ),
                        info=info,
                        source=ObjectFieldSource.COMPUTED,
                        descriptor=descriptor,
                    )
                )

    def matches(_item: ObjectFieldDefinition) -> bool:
        if name is not None and _item.name != name:
            return False
        if display is not None and _item.info.display is not display:
            return False
        if masked is not None and _item.info.masked is not masked:
            return False
        if internal is not None and _item.info.internal is not internal:
            return False
        if read_only is not None and _item.info.read_only is not read_only:
            return False
        return True

    return tuple(item for item in result if matches(item))
