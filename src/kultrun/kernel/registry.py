"""Adapter registration and resolution.

`docs/ROADMAP.md` Part II §9 requires every third-party component to sit
behind a Kultrun-owned contract. This is the mechanism that makes that
structurally true rather than aspirational: Docker, vLLM, LiteLLM, Hugging
Face and llmfit all arrive through here, named, and none of them is ever
imported by the code that uses it.

There is no module-level registry instance. Registries are created by
whoever composes the system — the test suite at this stage, the `platform`
module from Stage 0.3 — because a global mutable registry is shared state
that makes composition implicit and tests order-dependent.

Resolving an unregistered name fails closed. There is no default adapter,
ever: a missing implementation is a configuration error the operator must
see, not something to paper over with a fallback that nobody chose.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, TypeVar

from kultrun.kernel.errors import DuplicateRegistrationError, UnknownAdapterError
from kultrun.kernel.ids import Name

PortT = TypeVar("PortT")


class AdapterRegistry(Generic[PortT]):
    """The named implementations of one port."""

    def __init__(self, port: str) -> None:
        self._port = port
        self._factories: dict[str, Callable[..., PortT]] = {}

    @property
    def port(self) -> str:
        """The name of the port these adapters implement."""
        return self._port

    def register(self, name: str, factory: Callable[..., PortT]) -> None:
        """Register an implementation. One name, one owner."""
        validated = Name(name).value
        existing = self._factories.get(validated)
        if existing is not None:
            raise DuplicateRegistrationError(
                "an adapter is already registered under this name",
                port=self._port,
                name=validated,
                existing=getattr(existing, "__qualname__", repr(existing)),
            )
        self._factories[validated] = factory

    def create(self, name: str, *args: Any, **kwargs: Any) -> PortT:
        """Build the named implementation, or fail closed."""
        factory = self._factories.get(name)
        if factory is None:
            raise UnknownAdapterError(
                "no adapter is registered under this name",
                port=self._port,
                name=name,
                registered=sorted(self._factories),
            )
        return factory(*args, **kwargs)

    def names(self) -> tuple[str, ...]:
        """Every registered implementation name, for the Admin surface."""
        return tuple(sorted(self._factories))

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._factories
