"""Versioning, the contract base, and the registry of known kinds.

Every persisted and API structure in Machi is a :class:`Contract`: it has
a stable ``kind``, an integer ``schema_version``, and typed fields that each
state what they mean.

Two invariants from Machi Kernel 0.1.1 are mechanised here.

*Nothing is parsed on a best-effort basis.* Serialization dispatches on the
pair ``(kind, schema_version)``, and an unregistered pair raises rather than
falling back — so a record the platform does not understand can never be
silently half-loaded.

*Field meaning must never change silently.* Every field declares its meaning
through :func:`meaning`, and :func:`fingerprint` renders the full declared
shape of every registered contract. The fingerprint is committed and a test
compares against it, so removing a field, changing its type or restating its
meaning without bumping ``schema_version`` fails the build. A change of
meaning that keeps both name and type still requires a human to read the
diff; that limit is recorded in `docs/DEBT.md` rather than papered over.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import types
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import (
    Any,
    ClassVar,
    Final,
    Literal,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from machi.kernel.clock import require_utc
from machi.kernel.errors import (
    DuplicateRegistrationError,
    InternalError,
    UnknownKindError,
    UnknownVersionError,
    ValidationError,
)
from machi.kernel.ids import EntityId, HierarchyId, Name
from machi.kernel.unresolved import Unresolved, UnresolvedReason

ExtraFields = Literal["forbid", "ignore"]

#: Anything that survives a JSON round trip unchanged.
#:
#: Containers are typed loosely on purpose. A recursive alias would contain a
#: forward reference, and ``get_type_hints`` rebuilds any annotation whose
#: forward references it resolves, so the resolved alias would no longer be
#: the same object this module can recognise. Depth is validated at runtime
#: by :func:`_encode_json` instead, which is where a JSON payload's shape can
#: actually be checked.
JsonValue = None | bool | int | float | str | list[Any] | dict[str, Any]

ContractT = TypeVar("ContractT", bound="Contract")

_REGISTRY: dict[tuple[str, int], type[Contract]] = {}

_METADATA_MEANING: Final = "machi.meaning"
_UNRESOLVED_TAG: Final = "$unresolved"
_RESERVED_FIELD_NAMES: Final = frozenset({"kind", "schema_version"})

#: Sizes are bytes at every contract boundary. The previous attempt carried
#: `minimum_reserve_bytes` in one place and `minimum_reserve_gb` in another;
#: unit drift in a value that authorizes a mutation is not cosmetic.
_BANNED_UNIT_SUFFIXES: Final = (
    "_kb",
    "_mb",
    "_gb",
    "_tb",
    "_kib",
    "_mib",
    "_gib",
    "_tib",
    "_kilobytes",
    "_megabytes",
    "_gigabytes",
    "_terabytes",
)

_KIND_SEGMENT: Final = "abcdefghijklmnopqrstuvwxyz0123456789_"

_JSON_VALUE_ARGS: Final = frozenset(get_args(JsonValue))


def _is_union(annotation: Any) -> bool:
    """True for a union written either as ``Union[X, Y]`` or as ``X | Y``.

    The two spellings produce different objects — ``typing.Union`` and
    ``types.UnionType`` — and both appear in contract annotations, so every
    union check has to accept both.
    """
    return get_origin(annotation) in (Union, types.UnionType)


def _is_json_value(annotation: Any) -> bool:
    """True for the JsonValue alias, by identity or by structure."""
    if annotation is JsonValue:
        return True
    return _is_union(annotation) and frozenset(get_args(annotation)) == _JSON_VALUE_ARGS


def meaning(text: str, **kwargs: Any) -> Any:
    """Declare a field together with what it means.

    Wraps :func:`dataclasses.field`, so defaults and factories pass through::

        created_at: dt.datetime = meaning("when the record was first written")
        labels: tuple[str, ...] = meaning("operator-supplied tags", default=())
    """
    if not text.strip():
        raise InternalError("a field's meaning must not be empty")
    metadata = dict(kwargs.pop("metadata", {}))
    metadata[_METADATA_MEANING] = text.strip()
    return dataclasses.field(metadata=metadata, **kwargs)


class Contract:
    """Base for every persisted and API structure.

    A contract is a frozen dataclass registered under a stable kind and an
    integer version::

        @contract(kind="host_capabilities", version=1)
        @dataclass(frozen=True, slots=True)
        class HostCapabilities(Contract):
            ...

    A subclass that is never passed to :func:`contract` is an abstract
    intermediate class: usable as a field type, not serializable itself.
    """

    __slots__ = ()

    kind: ClassVar[str] = ""
    schema_version: ClassVar[int] = 0


def contract(
    *, kind: str, version: int
) -> Callable[[type[ContractT]], type[ContractT]]:
    """Register a contract under a stable kind and version.

    Applied **above** ``@dataclass`` so that it registers the final class.
    That ordering is not cosmetic: ``dataclass(slots=True)`` builds a new
    class object rather than mutating the one in the class statement, so
    registering from ``__init_subclass__`` would record the discarded
    pre-slots class and every ``isinstance`` check against it would fail.
    """

    def register(cls: type[ContractT]) -> type[ContractT]:
        where = cls.__qualname__
        _validate_kind(kind, contract=where)
        if version < 1:
            raise InternalError(
                "schema_version starts at 1", contract=where, version=version
            )
        problem = _dataclass_problem(cls)
        if problem is not None:
            raise InternalError(f"a contract {problem}", contract=where)
        existing = _REGISTRY.get((kind, version))
        if existing is not None:
            raise DuplicateRegistrationError(
                "a contract with this kind and version is already registered",
                kind=kind,
                version=version,
                existing=existing.__qualname__,
                attempted=where,
            )
        cls.kind = kind
        cls.schema_version = version
        _REGISTRY[(kind, version)] = cls
        return cls

    return register


def _dataclass_problem(cls: type) -> str | None:
    """None when the class is a frozen dataclass, otherwise what is wrong.

    Both checks live here, taking a plain ``type``, because ``is_dataclass``
    narrows through a ``TypeGuard`` that a ``type[Contract]`` can never
    satisfy statically — ``Contract`` itself is not a dataclass. Doing the
    check inline would make everything after it look unreachable.
    """
    if not dataclasses.is_dataclass(cls):
        return (
            "must be a dataclass; apply @contract above "
            "@dataclass(frozen=True, slots=True)"
        )
    # Annotated Any because ``__dataclass_params__`` is not part of the
    # protocol ``is_dataclass`` narrows to.
    params: Any = getattr(cls, "__dataclass_params__", None)
    if params is None or not params.frozen:
        return "must be a frozen dataclass"
    return None


def _validate_kind(kind: str, *, contract: str) -> None:
    segments = kind.split(".")
    for segment in segments:
        if not segment or segment[0] not in _KIND_SEGMENT[:36]:
            raise InternalError(
                "kind segments must be lowercase snake_case, dot-separated",
                contract=contract,
                kind=kind,
            )
        if any(character not in _KIND_SEGMENT for character in segment):
            raise InternalError(
                "kind segments must be lowercase snake_case, dot-separated",
                contract=contract,
                kind=kind,
            )


def registered_contracts() -> Mapping[tuple[str, int], type[Contract]]:
    """Every known contract, keyed by ``(kind, schema_version)``."""
    return dict(_REGISTRY)


def resolve(kind: str, version: int) -> type[Contract]:
    """Look up a contract type, failing closed on anything unrecognised."""
    found = _REGISTRY.get((kind, version))
    if found is not None:
        return found
    known_versions = sorted(v for k, v in _REGISTRY if k == kind)
    if not known_versions:
        raise UnknownKindError("no contract is registered under this kind", kind=kind)
    raise UnknownVersionError(
        "contract kind is known, but not at this version",
        kind=kind,
        requested_version=version,
        known_versions=known_versions,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def to_dict(record: Contract) -> dict[str, Any]:
    """Render a contract to a JSON-safe dict, tagged with kind and version."""
    cls = type(record)
    if not cls.kind:
        raise InternalError(
            "contract type is abstract and cannot be serialized",
            contract=cls.__qualname__,
        )
    hints = _hints(cls)
    out: dict[str, Any] = {"kind": cls.kind, "schema_version": cls.schema_version}
    for field in _fields(cls):
        value = getattr(record, field.name)
        out[field.name] = _encode(value, hints[field.name], path=field.name)
    return out


def from_dict(data: Mapping[str, Any], *, extra: ExtraFields = "forbid") -> Contract:
    """Reconstruct a contract from its serialized form.

    The ``kind`` and ``schema_version`` in the document decide the type. An
    unknown pair or a missing field is an error. Unexpected fields are
    refused by default (``extra='forbid'``). Journal readback uses
    ``extra='ignore'`` so additive envelope evolution does not drop a
    historical line. A registered older version is upgraded before decode.
    """
    from machi.kernel.migrate import migrate_document

    document = migrate_document(data)
    kind = document.get("kind")
    version = document.get("schema_version")
    if not isinstance(kind, str):
        raise ValidationError("record has no 'kind'", got=_describe(data.get("kind")))
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError(
            "record has no integer 'schema_version'",
            kind=kind,
            got=_describe(data.get("schema_version")),
        )
    return _decode_contract(resolve(kind, version), document, path=kind, extra=extra)


def decode_as(contract_type: type[ContractT], data: Mapping[str, Any]) -> ContractT:
    """Decode a document whose type is already known.

    Used for configuration sections and other places where the caller knows
    the contract and the document carries no tags. Tags are accepted if
    present but must agree with the requested type.
    """
    kind = data.get("kind")
    if kind is not None and kind != contract_type.kind:
        raise ValidationError(
            "record kind does not match the requested contract",
            expected=contract_type.kind,
            got=kind,
        )
    version = data.get("schema_version")
    if version is not None and version != contract_type.schema_version:
        raise ValidationError(
            "record schema_version does not match the requested contract",
            kind=contract_type.kind,
            expected=contract_type.schema_version,
            got=version,
        )
    return _decode_contract(contract_type, data, path=contract_type.kind)


def to_payload(value: Any) -> Any:
    """Render a contract, or a container of them, for an API response body."""
    if isinstance(value, Contract):
        return to_dict(value)
    if isinstance(value, Mapping):
        return {str(k): to_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_payload(v) for v in value]
    if isinstance(value, Unresolved):
        return _encode_unresolved(value)
    if isinstance(value, (EntityId, HierarchyId, Name)):
        return value.value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dt.datetime):
        return _encode_datetime(value, path="<payload>")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValidationError(
        "value cannot be rendered to an API payload", value_type=type(value).__name__
    )


def unresolved_fields(record: Contract) -> tuple[str, ...]:
    """Every field of this record, by dotted path, whose value is not known.

    Derived rather than maintained by hand, which is what stops each contract
    keeping its own list and drifting from reality.
    """
    found: list[str] = []
    _collect_unresolved(record, prefix="", found=found)
    return tuple(found)


def _collect_unresolved(record: Contract, *, prefix: str, found: list[str]) -> None:
    for field in _fields(type(record)):
        value = getattr(record, field.name)
        path = f"{prefix}{field.name}"
        if isinstance(value, Unresolved):
            found.append(path)
        elif isinstance(value, Contract):
            _collect_unresolved(value, prefix=f"{path}.", found=found)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                if isinstance(item, Unresolved):
                    found.append(f"{path}[{index}]")
                elif isinstance(item, Contract):
                    _collect_unresolved(item, prefix=f"{path}[{index}].", found=found)


@dataclasses.dataclass(frozen=True, slots=True)
class _Shape:
    """A field annotation, with optionality and unknown-ness separated out."""

    base: Any
    optional: bool
    maybe: bool


def _analyze(annotation: Any) -> _Shape:
    if _is_json_value(annotation):
        # JsonValue includes None by definition, so such a field is nullable.
        return _Shape(base=JsonValue, optional=True, maybe=False)
    if not _is_union(annotation):
        return _Shape(base=annotation, optional=False, maybe=False)
    members = list(get_args(annotation))
    optional = type(None) in members
    maybe = Unresolved in members
    remaining = [m for m in members if m is not type(None) and m is not Unresolved]
    if len(remaining) != 1:
        raise InternalError(
            "only 'X', 'X | None', 'Maybe[X]' and 'Maybe[X] | None' are supported",
            annotation=_type_name(annotation),
        )
    return _Shape(base=remaining[0], optional=optional, maybe=maybe)


def _encode(value: Any, annotation: Any, *, path: str) -> Any:
    shape = _analyze(annotation)
    if isinstance(value, Unresolved):
        if not shape.maybe:
            raise InternalError(
                "field holds an unresolved value but is not declared Maybe[...]",
                at=path,
            )
        return _encode_unresolved(value)
    if value is None:
        if shape.optional:
            return None
        raise ValidationError("field is not optional but is None", at=path)
    return _encode_value(value, shape.base, path=path)


def _encode_value(value: Any, base: Any, *, path: str) -> Any:
    origin = get_origin(base)
    if origin in (list, tuple, Sequence):
        item_type = _sequence_arg(base, path=path)
        return [_encode(v, item_type, path=f"{path}[]") for v in value]
    if origin in (dict, Mapping):
        _require_str_keys(base, path=path)
        value_type = get_args(base)[1]
        return {
            str(k): _encode(v, value_type, path=f"{path}.{k}") for k, v in value.items()
        }
    if _is_json_value(base):
        return _encode_json(value, path=path)
    if isinstance(base, type):
        if issubclass(base, Contract):
            return to_dict(value)
        if issubclass(base, (EntityId, HierarchyId, Name)):
            return value.value
        if issubclass(base, StrEnum):
            return value.value
        if issubclass(base, dt.datetime):
            return _encode_datetime(value, path=path)
        if base is bool or base in (int, float, str):
            return value
    raise InternalError("unsupported field type", at=path, annotation=_type_name(base))


def _decode_contract(
    contract_type: type[ContractT],
    data: Mapping[str, Any],
    *,
    path: str,
    extra: ExtraFields = "forbid",
) -> ContractT:
    hints = _hints(contract_type)
    fields = _fields(contract_type)
    known = {f.name for f in fields} | _RESERVED_FIELD_NAMES
    unexpected = sorted(set(data) - known)
    if unexpected and extra == "forbid":
        raise ValidationError(
            "record contains fields this contract does not declare",
            at=path,
            kind=contract_type.kind,
            schema_version=contract_type.schema_version,
            unexpected=unexpected,
        )
    kwargs: dict[str, Any] = {}
    for field in fields:
        if field.name not in data:
            if _has_default(field):
                continue
            raise ValidationError(
                "record is missing a required field",
                at=path,
                kind=contract_type.kind,
                field=field.name,
            )
        kwargs[field.name] = _decode(
            data[field.name],
            hints[field.name],
            path=f"{path}.{field.name}",
            extra=extra,
        )
    return contract_type(**kwargs)


def _decode(
    raw: Any, annotation: Any, *, path: str, extra: ExtraFields = "forbid"
) -> Any:
    shape = _analyze(annotation)
    if isinstance(raw, dict) and _UNRESOLVED_TAG in raw:
        if not shape.maybe:
            raise ValidationError(
                "field carries an unresolved value but is not declared Maybe[...]",
                at=path,
            )
        return _decode_unresolved(raw[_UNRESOLVED_TAG], path=path)
    if raw is None:
        if shape.optional:
            return None
        raise ValidationError("field is required but null", at=path)
    return _decode_value(raw, shape.base, path=path, extra=extra)


def _decode_value(
    raw: Any, base: Any, *, path: str, extra: ExtraFields = "forbid"
) -> Any:
    origin = get_origin(base)
    if origin in (list, tuple, Sequence):
        item_type = _sequence_arg(base, path=path)
        if not isinstance(raw, list):
            raise ValidationError("expected a list", at=path, got=_describe(raw))
        items = [_decode(v, item_type, path=f"{path}[]", extra=extra) for v in raw]
        return tuple(items) if origin is tuple else items
    if origin in (dict, Mapping):
        _require_str_keys(base, path=path)
        value_type = get_args(base)[1]
        if not isinstance(raw, dict):
            raise ValidationError("expected an object", at=path, got=_describe(raw))
        return {
            str(k): _decode(v, value_type, path=f"{path}.{k}", extra=extra)
            for k, v in raw.items()
        }
    if _is_json_value(base):
        return _encode_json(raw, path=path)
    if isinstance(base, type):
        if issubclass(base, Contract):
            if not isinstance(raw, dict):
                raise ValidationError(
                    "expected a nested record", at=path, got=_describe(raw)
                )
            nested = from_dict(raw, extra=extra)
            if not isinstance(nested, base):
                raise ValidationError(
                    "nested record is of the wrong kind",
                    at=path,
                    expected=base.kind,
                    got=nested.kind,
                )
            return nested
        if issubclass(base, EntityId):
            return base.parse(raw)
        if issubclass(base, HierarchyId):
            return base(_require_str(raw, path=path))
        if issubclass(base, Name):
            return base(_require_str(raw, path=path))
        if issubclass(base, StrEnum):
            return _decode_enum(base, raw, path=path)
        if issubclass(base, dt.datetime):
            return _decode_datetime(_require_str(raw, path=path), path=path)
        if base is bool:
            if not isinstance(raw, bool):
                raise ValidationError("expected a boolean", at=path, got=_describe(raw))
            return raw
        if base is int:
            if not isinstance(raw, int) or isinstance(raw, bool):
                raise ValidationError(
                    "expected an integer", at=path, got=_describe(raw)
                )
            return raw
        if base is float:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValidationError("expected a number", at=path, got=_describe(raw))
            return float(raw)
        if base is str:
            return _require_str(raw, path=path)
    raise InternalError("unsupported field type", at=path, annotation=_type_name(base))


def _encode_unresolved(value: Unresolved) -> dict[str, Any]:
    return {_UNRESOLVED_TAG: {"reason": value.reason.value, "detail": value.detail}}


def _decode_unresolved(raw: Any, *, path: str) -> Unresolved:
    if not isinstance(raw, dict):
        raise ValidationError(
            "unresolved marker must be an object", at=path, got=_describe(raw)
        )
    reason_text = raw.get("reason")
    if not isinstance(reason_text, str):
        raise ValidationError("unresolved marker has no reason", at=path)
    try:
        reason = UnresolvedReason(reason_text)
    except ValueError:
        raise ValidationError(
            "unrecognised unresolved reason",
            at=path,
            got=reason_text,
            permitted=[member.value for member in UnresolvedReason],
        ) from None
    detail = raw.get("detail")
    if detail is not None and not isinstance(detail, str):
        raise ValidationError("unresolved detail must be a string", at=path)
    return Unresolved(reason=reason, detail=detail)


def _decode_enum(enum_type: type[StrEnum], raw: Any, *, path: str) -> StrEnum:
    text = _require_str(raw, path=path)
    try:
        return enum_type(text)
    except ValueError:
        # Fail closed: an unrecognised member is never mapped to a default.
        raise ValidationError(
            "value is not a member of this enumeration",
            at=path,
            got=text,
            permitted=[member.value for member in enum_type],
        ) from None


def _encode_datetime(value: dt.datetime, *, path: str) -> str:
    normalized = require_utc(value, what=f"field {path}")
    return normalized.isoformat().replace("+00:00", "Z")


def _decode_datetime(raw: str, *, path: str) -> dt.datetime:
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        raise ValidationError(
            "value is not an ISO 8601 timestamp", at=path, got=raw
        ) from None
    return require_utc(parsed, what=f"field {path}")


def _encode_json(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_encode_json(v, path=f"{path}[]") for v in value]
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise ValidationError(
                    "JSON object keys must be strings", at=path, got=_describe(key)
                )
        return {k: _encode_json(v, path=f"{path}.{k}") for k, v in value.items()}
    raise ValidationError(
        "value is not JSON-safe", at=path, value_type=type(value).__name__
    )


def _require_str(raw: Any, *, path: str) -> str:
    if not isinstance(raw, str):
        raise ValidationError("expected a string", at=path, got=_describe(raw))
    return raw


def _require_str_keys(base: Any, *, path: str) -> None:
    if get_args(base)[0] is not str:
        raise InternalError("mapping keys must be str", at=path)


def _sequence_arg(base: Any, *, path: str) -> Any:
    args = get_args(base)
    if get_origin(base) is tuple:
        if len(args) != 2 or args[1] is not Ellipsis:
            raise InternalError(
                "only homogeneous 'tuple[X, ...]' is supported", at=path
            )
        return args[0]
    if len(args) != 1:
        raise InternalError("a sequence must declare one item type", at=path)
    return args[0]


def _fields(cls: type[Contract]) -> tuple[dataclasses.Field[Any], ...]:
    return dataclasses.fields(cast("Any", cls))


def _has_default(field: dataclasses.Field[Any]) -> bool:
    return (
        field.default is not dataclasses.MISSING
        or field.default_factory is not dataclasses.MISSING
    )


def _hints(cls: type[Contract]) -> dict[str, Any]:
    return get_type_hints(cls, include_extras=False)


def _describe(value: Any) -> str:
    return "null" if value is None else type(value).__name__


def _type_name(annotation: Any) -> str:
    if _is_json_value(annotation):
        return "JsonValue"
    if annotation is type(None):
        return "None"
    if annotation is Ellipsis:
        return "..."
    if isinstance(annotation, type):
        return annotation.__name__
    if _is_union(annotation):
        return " | ".join(_type_name(a) for a in get_args(annotation))
    origin = get_origin(annotation)
    if origin is not None:
        name = getattr(origin, "__name__", str(origin))
        args = ", ".join(_type_name(a) for a in get_args(annotation))
        return f"{name}[{args}]"
    return str(annotation)


# ---------------------------------------------------------------------------
# Fingerprint and registry validation
# ---------------------------------------------------------------------------


def fingerprint(*, module_prefix: str = "machi.") -> dict[str, Any]:
    """Render the declared shape of every registered contract.

    The result is committed to ``tests/golden/schema_fingerprint.json``, and
    a diff to that file is the review surface for any change to a contract's
    shape or to what its fields mean.

    ``module_prefix`` restricts the output to production contracts, so that
    contracts defined by tests do not enter the committed record.
    """
    out: dict[str, Any] = {}
    for (kind, version), cls in sorted(_REGISTRY.items()):
        if not cls.__module__.startswith(module_prefix):
            continue
        hints = _hints(cls)
        fields: dict[str, Any] = {}
        for field in _fields(cls):
            shape = _analyze(hints[field.name])
            fields[field.name] = {
                "type": _type_name(hints[field.name]),
                "optional": _has_default(field),
                "nullable": shape.optional,
                "may_be_unresolved": shape.maybe,
                "meaning": field.metadata.get(_METADATA_MEANING),
            }
        out[f"{kind}@{version}"] = {"python": cls.__qualname__, "fields": fields}
    return out


def validate_contract(cls: type[Contract]) -> None:
    """Assert one contract is well formed.

    Checks the things that would otherwise surface the first time a record
    was written: that it is a frozen dataclass, that no field shadows a
    serialization tag, that every field states its meaning, that every field
    type is serializable, and that no field name carries a non-canonical
    unit.
    """
    where = f"{cls.kind}@{cls.schema_version} ({cls.__qualname__})"
    problem = _dataclass_problem(cls)
    if problem is not None:
        raise InternalError(f"a contract {problem}", contract=where)
    hints = _hints(cls)
    for field in _fields(cls):
        if field.name in _RESERVED_FIELD_NAMES:
            raise InternalError(
                "field name shadows a serialization tag",
                contract=where,
                field=field.name,
            )
        if not field.metadata.get(_METADATA_MEANING):
            raise InternalError(
                "field does not state its meaning; declare it with meaning()",
                contract=where,
                field=field.name,
            )
        for suffix in _BANNED_UNIT_SUFFIXES:
            if field.name.endswith(suffix):
                raise InternalError(
                    "sizes are bytes at every contract boundary; "
                    "rename this field to end in '_bytes'",
                    contract=where,
                    field=field.name,
                )
        _check_annotation(hints[field.name], path=f"{where}.{field.name}")


def validate_registry(*, module_prefix: str = "") -> None:
    """Assert every registered contract is well formed. Runs at startup."""
    for _, cls in sorted(_REGISTRY.items()):
        if cls.__module__.startswith(module_prefix):
            validate_contract(cls)


def _check_annotation(annotation: Any, *, path: str) -> None:
    base = _analyze(annotation).base
    origin = get_origin(base)
    if origin in (list, tuple, Sequence):
        _check_annotation(_sequence_arg(base, path=path), path=f"{path}[]")
        return
    if origin in (dict, Mapping):
        _require_str_keys(base, path=path)
        _check_annotation(get_args(base)[1], path=f"{path}.*")
        return
    if _is_json_value(base):
        return
    if isinstance(base, type) and (
        issubclass(base, (Contract, EntityId, HierarchyId, Name, StrEnum, dt.datetime))
        or base in (bool, int, float, str)
    ):
        return
    raise InternalError("unsupported field type", at=path, annotation=_type_name(base))
