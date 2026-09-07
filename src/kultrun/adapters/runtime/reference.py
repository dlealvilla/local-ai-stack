"""A runtime adapter that produces a launch spec for the acceptance harness.

Not vLLM, not llama.cpp. Stage 1.3 needs a deterministic process, not a
model. This adapter only writes a recipe; the executor starts it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
)

IDENTITY = Name("reference-process")
EXECUTOR_KIND = Name("native-process")

#: Module executed as the child process. Packaged in the wheel so a clean
#: install can prove the lifecycle without a source checkout.
WORKLOAD_MODULE = "kultrun.adapters.runtime.reference_workload"

#: `src/` in a checkout, or `site-packages` when installed. The child
#: interpreter does not inherit pytest's pythonpath.
_IMPORT_ROOT = str(Path(__file__).resolve().parents[3])


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

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        del request
        mode = "--hold" if self._hold else "--once"
        return RuntimeLaunchSpec(
            runtime=self.identity,
            profile=self.identity,
            executable=sys.executable,
            arguments=("-m", WORKLOAD_MODULE, mode),
            environment=(
                "KULTRUN_REFERENCE_WORKLOAD=1",
                f"PYTHONPATH={_child_pythonpath()}",
            ),
        )


def _child_pythonpath() -> str:
    """Make `-m kultrun...` resolvable in a source checkout and an install."""
    current = os.environ.get("PYTHONPATH", "")
    if not current:
        return _IMPORT_ROOT
    parts = current.split(os.pathsep)
    if _IMPORT_ROOT in parts:
        return current
    return _IMPORT_ROOT + os.pathsep + current


def build(*, hold: bool = True) -> ReferenceProcessRuntime:
    """The composition root's constructor."""
    return ReferenceProcessRuntime(hold=hold)
