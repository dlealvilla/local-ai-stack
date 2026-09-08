"""Catalogue of runtime adapters. Does not start processes."""

from __future__ import annotations

from collections.abc import Sequence

from kultrun.kernel.errors import NotFoundError
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)
from kultrun.runtime.ports import InferenceRuntime

_HARNESS_TIERS = frozenset(
    {
        RuntimeSupportTier.REFERENCE,
        RuntimeSupportTier.TEST_ONLY,
        RuntimeSupportTier.FUTURE,
    }
)


class RuntimeCatalogue:
    """Every registered runtime adapter. Plural from v1."""

    def __init__(self, adapters: Sequence[InferenceRuntime]) -> None:
        self._adapters = {adapter.identity: adapter for adapter in adapters}

    def get(self, runtime: Name) -> InferenceRuntime:
        adapter = self._adapters.get(runtime)
        if adapter is None:
            raise NotFoundError(
                "no such runtime adapter",
                runtime=runtime.value,
                known=[name.value for name in self._adapters],
            )
        return adapter

    def profiles(self) -> tuple[RuntimeProfile, ...]:
        """Every profile, in registration order of identity."""
        return tuple(
            self._adapters[name].profile() for name in sorted(self._adapters, key=str)
        )

    def descriptors(self) -> tuple[RuntimeSupportDescriptor, ...]:
        """Every declared support descriptor. Not verification evidence."""
        return tuple(
            self._adapters[name].support() for name in sorted(self._adapters, key=str)
        )

    def product_identities(self) -> tuple[str, ...]:
        """Runtimes that may serve a model. Reference harnesses are not among them."""
        return tuple(
            descriptor.runtime.value
            for descriptor in self.descriptors()
            if descriptor.production_candidate
            and descriptor.support_tier not in _HARNESS_TIERS
        )

    def launch(
        self, runtime: Name, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        """The recipe for one runtime. Does not exec it."""
        return self.get(runtime).launch_spec(request)

    def inspect_readiness(
        self,
        runtime: Name,
        *,
        stdout: str,
        stderr: str,
        execution_alive: bool,
        bound_address: str | None = None,
        bound_port: int | None = None,
        expected_served_model: str | None = None,
    ) -> RuntimeReadiness:
        """Ask the runtime whether its workload is READY."""
        return self.get(runtime).inspect_readiness(
            stdout=stdout,
            stderr=stderr,
            execution_alive=execution_alive,
            bound_address=bound_address,
            bound_port=bound_port,
            expected_served_model=expected_served_model,
        )
