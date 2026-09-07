"""Catalogue of runtime adapters. Does not start processes."""

from __future__ import annotations

from collections.abc import Sequence

from kultrun.kernel.errors import NotFoundError
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
)
from kultrun.runtime.ports import InferenceRuntime


class RuntimeCatalogue:
    """Every registered runtime adapter. Plural from v1."""

    def __init__(self, adapters: Sequence[InferenceRuntime]) -> None:
        self._adapters = {adapter.identity: adapter for adapter in adapters}

    def profiles(self) -> tuple[RuntimeProfile, ...]:
        """Every profile, in registration order of identity."""
        return tuple(
            self._adapters[name].profile() for name in sorted(self._adapters, key=str)
        )

    def product_identities(self) -> tuple[str, ...]:
        """Runtimes that may serve a model. Reference harnesses are not among them."""
        harness = frozenset({"reference-process", "reference-serving"})
        return tuple(
            profile.runtime.value
            for profile in self.profiles()
            if profile.runtime.value not in harness
        )

    def launch(
        self, runtime: Name, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        """The recipe for one runtime. Does not exec it."""
        adapter = self._adapters.get(runtime)
        if adapter is None:
            raise NotFoundError(
                "no such runtime adapter",
                runtime=runtime.value,
                known=[name.value for name in self._adapters],
            )
        return adapter.launch_spec(request)
