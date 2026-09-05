"""The shape of a request and a response, independent of any transport.

Deliberately not an HTTP framework's request object. `docs/ROADMAP.md`
Part II §9 forbids a third-party component from owning a platform concept,
and a web framework that owns routing owns the API.

The practical benefit is that the entire Platform API is testable by
calling the router with one of these, which is what lets the Milestone 0
gate — "the Platform API answers from platform state" — be proven at `L1`
rather than needing a live port to demonstrate anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Method(StrEnum):
    """The HTTP methods the Platform API uses."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


@dataclass(frozen=True, slots=True)
class ApiRequest:
    """One call into the Platform API."""

    method: Method
    path: str
    query: dict[str, str] = field(default_factory=dict)
    body: dict[str, object] | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApiResponse:
    """One answer.

    The body is always a serialized `Result`, so a client parses one shape
    whether the call succeeded or failed.
    """

    status: int
    body: dict[str, object]
