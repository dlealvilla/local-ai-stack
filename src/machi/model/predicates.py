"""Runtime predicates. A vacuous claim is not executable support."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe, is_resolved
from machi.model.metadata import NormalizedMetadata

_TOKEN_MAX = 80


class PredicateSupport(StrEnum):
    FINITE = "finite"
    VACUOUS = "vacuous"
    UNRESOLVED = "unresolved"


class PredicateRule(StrEnum):
    MULTIPLE_OF = "multiple_of"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    EQUALS = "equals"
    ANY = "any"


class StructuralVerdict(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNRESOLVED = "unresolved"


@contract(kind="model.runtime_predicate", version=1)
@dataclass(frozen=True, slots=True)
class RuntimePredicate(Contract):
    """One installed-runtime constraint. Not a model name."""

    name: str = meaning("predicate source, such as a backend name")
    subject: str = meaning("what the predicate constrains")
    support: PredicateSupport = meaning("finite, vacuous, or unresolved")
    rule: PredicateRule = meaning("how parameter applies")
    parameter: Maybe[int] = meaning("rule parameter when the predicate is finite")
    ceiling: Maybe[int] = meaning("upper bound for a multiple_of rule")
    value: str = meaning("equals-rule token, or empty")

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > _TOKEN_MAX:
            raise ValidationError("predicate name is empty or too long")
        if not self.subject or len(self.subject) > _TOKEN_MAX:
            raise ValidationError("predicate subject is empty or too long")
        if len(self.value) > _TOKEN_MAX:
            raise ValidationError("predicate value is too long")


def head_dimension(metadata: NormalizedMetadata) -> Maybe[int]:
    """Explicit head size wins. Otherwise hidden size divided by query heads."""
    if is_resolved(metadata.explicit_head_dim):
        return metadata.explicit_head_dim
    return metadata.derived_head_dim


def structural_verdict(
    metadata: NormalizedMetadata,
    predicates: tuple[RuntimePredicate, ...],
) -> StructuralVerdict:
    """Accept only a finite predicate that matches. Vacuous support does not."""
    head_rules = tuple(
        item for item in predicates if item.subject == "head_size"
    )
    if not head_rules:
        return StructuralVerdict.UNRESOLVED
    finite = tuple(item for item in head_rules if _finite(item))
    if not finite:
        return StructuralVerdict.UNRESOLVED
    head = head_dimension(metadata)
    if not isinstance(head, int):
        return StructuralVerdict.UNRESOLVED
    if any(_matches_head(item, head) for item in finite):
        return _dtype_verdict(metadata, predicates)
    return StructuralVerdict.UNSUPPORTED


def _dtype_verdict(
    metadata: NormalizedMetadata,
    predicates: tuple[RuntimePredicate, ...],
) -> StructuralVerdict:
    rules = tuple(
        item for item in predicates if item.subject == "dtype" and _finite(item)
    )
    if not rules:
        return StructuralVerdict.SUPPORTED
    if not isinstance(metadata.dtype, str):
        return StructuralVerdict.UNRESOLVED
    matched = any(
        item.rule is PredicateRule.EQUALS and item.value == metadata.dtype
        for item in rules
    )
    if matched:
        return StructuralVerdict.SUPPORTED
    return StructuralVerdict.UNSUPPORTED


def _finite(item: RuntimePredicate) -> bool:
    return (
        item.support is PredicateSupport.FINITE and item.rule is not PredicateRule.ANY
    )


def _matches_head(item: RuntimePredicate, head: int) -> bool:
    if not isinstance(item.parameter, int):
        return False
    if item.rule is PredicateRule.MULTIPLE_OF:
        if item.parameter < 1 or head % item.parameter != 0:
            return False
        return not isinstance(item.ceiling, int) or head <= item.ceiling
    if item.rule is PredicateRule.AT_LEAST:
        return head >= item.parameter
    if item.rule is PredicateRule.AT_MOST:
        return head <= item.parameter
    if item.rule is PredicateRule.EQUALS:
        return head == item.parameter
    return False
