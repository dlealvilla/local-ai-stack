"""A runtime adapter that produces a launch spec for the acceptance harness.

Not vLLM, not llama.cpp. Stage 1.3 needs a deterministic process, not a
model. This adapter only writes a recipe; the executor starts it.
"""

from __future__ import annotations

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)

IDENTITY = Name("reference-process")
EXECUTOR_KIND = Name("native-process")
CONTAINER_EXECUTOR = Name("container-docker")
PYTHON_COMPONENT = "python"

#: Module executed as the child process. Packaged in the wheel so a clean
#: install can prove the lifecycle without a source checkout.
WORKLOAD_MODULE = "kultrun.adapters.runtime.reference_workload"


class ReferenceProcessRuntime:
    """Translates the reference profile into argv. Does not exec."""

    def __init__(self, *, hold: bool = True) -> None:
        self._hold = hold

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="Reference process (acceptance harness)",
            executor_kind=EXECUTOR_KIND,
            capabilities=("process-lifecycle", "bounded-output"),
        )

    def support(self) -> RuntimeSupportDescriptor:
        return RuntimeSupportDescriptor(
            runtime=self.identity,
            display_name="Reference process (acceptance harness)",
            support_tier=RuntimeSupportTier.TEST_ONLY,
            production_candidate=False,
            supported_os_families=("linux", "darwin"),
            supported_architectures=("x86_64", "arm64"),
            compatible_executor_types=(
                EXECUTOR_KIND,
                Name("recording"),
                CONTAINER_EXECUTOR,
            ),
            required_features=(
                "process_execution",
                "structured_argv",
                "environment_variables",
            ),
            limitations=("not a model-serving runtime", "TEST_ONLY harness"),
            evidence=("stage-1.3-reference-process",),
            confidence=Confidence.HIGH,
        )

    def inspect_readiness(
        self,
        *,
        stdout: str,
        stderr: str,
        execution_alive: bool,
        bound_address: str | None = None,
        bound_port: int | None = None,
    ) -> RuntimeReadiness:
        del stdout, stderr, bound_address, bound_port
        if not execution_alive:
            return RuntimeReadiness(
                ready=False, reason="execution is not alive"
            )
        return RuntimeReadiness(
            ready=True,
            reason="process harness has no HTTP probe; liveness is enough",
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        del request
        mode = "--hold" if self._hold else "--once"
        return RuntimeLaunchSpec(
            runtime=self.identity,
            profile=self.identity,
            executable=PYTHON_COMPONENT,
            arguments=("-m", WORKLOAD_MODULE, mode),
            environment=("KULTRUN_REFERENCE_WORKLOAD=1",),
        )


def build(*, hold: bool = True) -> ReferenceProcessRuntime:
    """The composition root's constructor."""
    return ReferenceProcessRuntime(hold=hold)
