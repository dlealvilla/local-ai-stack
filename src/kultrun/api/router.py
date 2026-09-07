"""Dispatch, and the one place a failure becomes a response.

Every handler is a function from a request to a value. It may return a
contract, a list of them, or a plain JSON-safe structure; the router
renders it. It may raise any `KultrunError`; the router renders that too,
through the error's own stable code.

That single rendering point is what makes the API's error vocabulary
identical to the platform's. A handler never builds an error body, so no
handler can invent a code, and an administrator who learns what
``precondition_failed`` means learns it once.

An unexpected exception is rendered as ``internal`` **without its detail**.
The message goes nowhere except the caller's own logs, because an error
from deep inside a subsystem is as likely to contain a filesystem path as
anything useful.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kultrun.api.contracts import ApiRequest, ApiResponse, Method
from kultrun.kernel.errors import (
    ErrorCode,
    KultrunError,
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.results import ErrorDetail, Result
from kultrun.kernel.schema import to_dict, to_payload

Handler = Callable[[ApiRequest], Any]

#: How a platform error code becomes an HTTP status. The mapping lives here
#: and nowhere else, so a new code has exactly one place to be considered.
_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION: 400,
    ErrorCode.UNKNOWN_KIND: 400,
    ErrorCode.UNKNOWN_VERSION: 400,
    ErrorCode.UNKNOWN_ADAPTER: 400,
    ErrorCode.CONFIG_INVALID: 400,
    ErrorCode.UNRESOLVED: 409,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.DUPLICATE_REGISTRATION: 409,
    ErrorCode.PRECONDITION_FAILED: 412,
    ErrorCode.CANCELLED: 499,
    ErrorCode.PERSISTENCE: 503,
    ErrorCode.INTERNAL: 500,
}


class Router:
    """The Platform API's route table."""

    def __init__(self, *, prefix: str = "/v1") -> None:
        self._prefix = prefix
        self._routes: dict[tuple[Method, str], Handler] = {}

    @property
    def prefix(self) -> str:
        """The version prefix every route sits under."""
        return self._prefix

    def route(self, method: Method, path: str, handler: Handler) -> None:
        """Register a handler. One method and path, one owner."""
        key = (method, self._normalize(path))
        if key in self._routes:
            raise ValidationError(
                "a handler is already registered for this route",
                method=method.value,
                path=path,
            )
        self._routes[key] = handler

    def post(self, path: str, handler: Handler) -> None:
        """Register a handler that changes something.

        Separate from `get` so a mutation cannot be reached by a read. The
        console loads and refreshes over GET only, which is what keeps a
        page view from performing storage work.
        """
        self.route(Method.POST, path, handler)

    def get(self, path: str, handler: Handler) -> None:
        """Register a read-only route."""
        self.route(Method.GET, path, handler)

    def delete(self, path: str, handler: Handler) -> None:
        """Register a delete mutation. Unreachable by GET."""
        self.route(Method.DELETE, path, handler)

    def paths(self) -> tuple[str, ...]:
        """Every registered route, for the Admin surface and for diagnosis."""
        return tuple(
            sorted(f"{method.value} {path}" for method, path in self._routes)
        )

    def handle(self, request: ApiRequest) -> ApiResponse:
        """Dispatch a request and render whatever comes back."""
        handler = self._routes.get((request.method, self._normalize(request.path)))
        if handler is None:
            return self._render_error(
                NotFoundError(
                    "no such route",
                    method=request.method.value,
                    path=request.path,
                ),
                request,
            )
        try:
            value = handler(request)
        except KultrunError as error:
            return self._render_error(error, request)
        except Exception:
            # Deliberately opaque: an exception from inside a subsystem is as
            # likely to carry a filesystem path as anything a caller can use.
            return self._render_error(
                KultrunError("an unexpected error occurred"), request
            )
        return self._render_success(value, request)

    def _render_success(self, value: Any, request: ApiRequest) -> ApiResponse:
        result = Result.success(
            _payload(value), correlation_id=request.correlation_id
        )
        return ApiResponse(status=200, body=to_dict(result))

    def _render_error(self, error: KultrunError, request: ApiRequest) -> ApiResponse:
        result = Result.failure(error, correlation_id=request.correlation_id)
        return ApiResponse(
            status=_STATUS.get(error.code, 500), body=to_dict(result)
        )

    def _normalize(self, path: str) -> str:
        trimmed = path.rstrip("/") or "/"
        if trimmed.startswith(self._prefix):
            return trimmed
        return f"{self._prefix}{trimmed}"


def _payload(value: Any) -> Any:
    """Render a handler's return value for the wire."""
    return to_payload(value)


__all__ = [
    "ErrorDetail",
    "Handler",
    "PreconditionFailedError",
    "Router",
]
