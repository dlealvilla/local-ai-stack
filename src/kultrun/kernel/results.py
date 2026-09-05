"""The result envelope.

This is the **control-plane response envelope** — what the Platform API
returns, and what an internal operation returns when it must report success
or failure structurally. It is deliberately not a monad threaded through
call sites.

The division of labour, stated once here so it is not relitigated in every
module:

- an **expected domain refusal** is its own contract, with reasons attached.
  `docs/ROADMAP.md` Part II §6 requires that verdicts are never booleans, so
  `AdmissionDecision` and `FeasibilityResult` are decisions carrying
  explanations, not error values;
- a **programming error or invariant violation** raises;
- a **boundary** — the API, or a stage's own operation surface — renders
  either of those into this envelope.

`ErrorDetail` lives here rather than in ``errors`` because ``errors`` is the
root of the kernel's own dependency graph and must not import ``schema``.
The taxonomy lives there; its wire form lives with the envelope that carries
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from kultrun.kernel.errors import ErrorCode, InternalError, KultrunError
from kultrun.kernel.schema import Contract, JsonValue, contract, meaning, to_payload


@contract(kind="error_detail", version=1)
@dataclass(frozen=True, slots=True)
class ErrorDetail(Contract):
    """The wire form of a failure."""

    code: str = meaning("stable error code; never renamed once shipped")
    message: str = meaning("human-readable description of the failure")
    retryable: bool = meaning("whether an identical retry could succeed")
    context: dict[str, JsonValue] = meaning(
        "structured detail naming what failed and where", default_factory=dict
    )

    @classmethod
    def from_error(cls, error: KultrunError) -> Self:
        """Render a raised platform error into its wire form."""
        return cls(
            code=error.code.value,
            message=error.message,
            retryable=error.retryable,
            context={key: _json_safe(value) for key, value in error.context.items()},
        )


@contract(kind="result", version=1)
@dataclass(frozen=True, slots=True)
class Result(Contract):
    """The outcome of one operation.

    Exactly one of ``payload`` and ``error`` is meaningful. There is no
    separate ``ok`` field, because a redundant flag can disagree with the
    thing it describes.
    """

    payload: JsonValue = meaning(
        "the operation's rendered output, absent on failure", default=None
    )
    error: ErrorDetail | None = meaning(
        "the failure, absent on success", default=None
    )
    correlation_id: str | None = meaning(
        "identifier tying this outcome to the request that caused it",
        default=None,
    )

    def __post_init__(self) -> None:
        if self.error is not None and self.payload is not None:
            raise InternalError(
                "a result carries either a payload or an error, never both",
                code=self.error.code,
            )

    @property
    def ok(self) -> bool:
        """True when the operation succeeded."""
        return self.error is None

    @classmethod
    def success(cls, payload: Any = None, *, correlation_id: str | None = None) -> Self:
        """A successful outcome. The payload is rendered for the wire."""
        return cls(
            payload=to_payload(payload) if payload is not None else None,
            correlation_id=correlation_id,
        )

    @classmethod
    def failure(
        cls, error: KultrunError | ErrorDetail, *, correlation_id: str | None = None
    ) -> Self:
        """A failed outcome, from either a raised error or an already-made detail."""
        detail = (
            error if isinstance(error, ErrorDetail) else ErrorDetail.from_error(error)
        )
        return cls(error=detail, correlation_id=correlation_id)

    def unwrap(self) -> JsonValue:
        """Return the payload, or raise the carried failure.

        Convenience for callers that treat a failure as exceptional. The
        original exception type is not recoverable from the wire form, so
        this raises a generic platform error carrying the original code.
        """
        if self.error is None:
            return self.payload
        raise KultrunError(
            self.error.message,
            original_code=self.error.code,
            **self.error.context,
        )


def _json_safe(value: Any) -> JsonValue:
    """Reduce error context to something that survives serialization.

    Error context is assembled at raise sites all over the platform, so it
    cannot be assumed JSON-safe. Anything unexpected becomes its repr rather
    than causing a second failure while reporting the first.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return repr(value)


__all__ = ["ErrorCode", "ErrorDetail", "Result"]
