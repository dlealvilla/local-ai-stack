from __future__ import annotations

import copy
import math
import subprocess
from collections.abc import (
    Callable,
    Mapping,
)
from typing import Any

from adapters.resource_manager.phase8_planning import (
    Phase8ReservationPlanningProvider,
)


_MIB = 1024 * 1024

_DEFAULT_OVERHEAD_FLOOR_BYTES = (
    512 * _MIB
)

_DEFAULT_OVERHEAD_FRACTION = 0.02


class VllmRuntimePlanningError(
    RuntimeError
):
    pass


def _nvidia_total_vram_bytes() -> int:
    """Return physical VRAM for the current single-GPU reference host."""

    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        )

    except Exception as exc:
        raise VllmRuntimePlanningError(
            "Unable to resolve NVIDIA physical VRAM"
        ) from exc

    values = [
        line.strip()
        for line in raw.splitlines()
        if line.strip()
    ]

    if len(values) != 1:
        raise VllmRuntimePlanningError(
            "Phase 9 vLLM reservation adapter requires "
            "exactly one NVIDIA GPU"
        )

    try:
        total_mib = int(
            values[0]
        )

    except ValueError as exc:
        raise VllmRuntimePlanningError(
            "Invalid nvidia-smi memory.total result"
        ) from exc

    if total_mib <= 0:
        raise VllmRuntimePlanningError(
            "Physical VRAM must be positive"
        )

    return total_mib * _MIB


def vllm_runtime_requirement_bytes(
    *,
    total_vram_bytes: int,
    gpu_memory_utilization: float,
    overhead_floor_bytes: int = (
        _DEFAULT_OVERHEAD_FLOOR_BYTES
    ),
    overhead_fraction: float = (
        _DEFAULT_OVERHEAD_FRACTION
    ),
) -> dict[str, int | float]:
    """
    Convert vLLM's per-instance GPU-memory policy into a conservative
    ResourceManager reservation requirement.

    v1 policy:
        configured target
        + max(512 MiB, 2% physical VRAM)

    The extra margin covers process/CUDA/runtime memory observed outside
    vLLM's configured allocation target.

    This intentionally remains a replaceable adapter policy.
    """

    total_vram_bytes = int(
        total_vram_bytes
    )

    gpu_memory_utilization = float(
        gpu_memory_utilization
    )

    overhead_floor_bytes = int(
        overhead_floor_bytes
    )

    overhead_fraction = float(
        overhead_fraction
    )

    if total_vram_bytes <= 0:
        raise ValueError(
            "total_vram_bytes must be positive"
        )

    if not (
        0.0
        < gpu_memory_utilization
        <= 1.0
    ):
        raise ValueError(
            "gpu_memory_utilization must be in (0, 1]"
        )

    if overhead_floor_bytes < 0:
        raise ValueError(
            "overhead_floor_bytes cannot be negative"
        )

    if overhead_fraction < 0:
        raise ValueError(
            "overhead_fraction cannot be negative"
        )

    target_bytes = math.ceil(
        total_vram_bytes
        * gpu_memory_utilization
    )

    overhead_bytes = max(
        overhead_floor_bytes,
        math.ceil(
            total_vram_bytes
            * overhead_fraction
        ),
    )

    requirement_bytes = (
        target_bytes
        + overhead_bytes
    )

    return {
        "total_vram_bytes":
            total_vram_bytes,

        "gpu_memory_utilization":
            gpu_memory_utilization,

        "target_bytes":
            target_bytes,

        "overhead_floor_bytes":
            overhead_floor_bytes,

        "overhead_fraction":
            overhead_fraction,

        "overhead_bytes":
            overhead_bytes,

        "requirement_bytes":
            requirement_bytes,
    }


class VllmRuntimeAwareReservationPlanningProvider:
    """
    Decorate the existing Phase 8 -> Phase 9 planning view with the
    runtime commitment implied by the active vLLM configuration.

    ResourceManager remains runtime-agnostic.
    Phase 8 remains unchanged.
    """

    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        performance: Mapping[str, Any],
        base_provider: Any | None = None,
        total_vram_bytes_provider: (
            Callable[[], int] | None
        ) = None,
        overhead_floor_bytes: int = (
            _DEFAULT_OVERHEAD_FLOOR_BYTES
        ),
        overhead_fraction: float = (
            _DEFAULT_OVERHEAD_FRACTION
        ),
    ) -> None:
        inference = config.get(
            "inference"
        )

        if not isinstance(
            inference,
            Mapping,
        ):
            raise ValueError(
                "config.inference mapping is required"
            )

        provider = str(
            inference.get(
                "provider",
                "",
            )
        ).strip().lower()

        if provider != "vllm":
            raise ValueError(
                "VllmRuntimeAwareReservationPlanningProvider "
                "requires inference.provider='vllm'"
            )

        try:
            utilization = float(
                performance[
                    "gpu_memory_utilization"
                ]
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "performance.gpu_memory_utilization "
                "is required"
            ) from exc

        if not (
            0.0
            < utilization
            <= 1.0
        ):
            raise ValueError(
                "gpu_memory_utilization must be in (0, 1]"
            )

        self._base_provider = (
            base_provider
            if base_provider is not None
            else Phase8ReservationPlanningProvider()
        )

        self._total_vram_bytes_provider = (
            total_vram_bytes_provider
            or _nvidia_total_vram_bytes
        )

        self._gpu_memory_utilization = (
            utilization
        )

        self._overhead_floor_bytes = int(
            overhead_floor_bytes
        )

        self._overhead_fraction = float(
            overhead_fraction
        )

    def build_view(
        self,
    ) -> dict[str, Any]:
        raw_view = (
            self._base_provider.build_view()
        )

        if not isinstance(
            raw_view,
            Mapping,
        ):
            raise VllmRuntimePlanningError(
                "Base planning provider returned "
                "a non-mapping view"
            )

        view = copy.deepcopy(
            dict(raw_view)
        )

        capacities = view.get(
            "capacities"
        )

        requirements_by_model = view.get(
            "requirements_by_model"
        )

        resolutions = view.get(
            "requirement_resolutions_by_model"
        )

        if not isinstance(
            capacities,
            Mapping,
        ):
            raise VllmRuntimePlanningError(
                "Planning view has no capacities mapping"
            )

        if not isinstance(
            requirements_by_model,
            Mapping,
        ):
            raise VllmRuntimePlanningError(
                "Planning view has no "
                "requirements_by_model mapping"
            )

        if not isinstance(
            resolutions,
            Mapping,
        ):
            raise VllmRuntimePlanningError(
                "Planning view has no "
                "requirement_resolutions_by_model mapping"
            )

        accelerator_pools = [
            str(pool_id)
            for pool_id in capacities
            if (
                str(pool_id).startswith(
                    "accelerator:"
                )
                and str(pool_id).endswith(
                    ":memory"
                )
            )
        ]

        if len(
            accelerator_pools
        ) != 1:
            raise VllmRuntimePlanningError(
                "Phase 9 vLLM runtime reservation "
                "requires exactly one accelerator "
                "memory pool"
            )

        pool_id = accelerator_pools[0]

        runtime = (
            vllm_runtime_requirement_bytes(
                total_vram_bytes=int(
                    self._total_vram_bytes_provider()
                ),
                gpu_memory_utilization=(
                    self._gpu_memory_utilization
                ),
                overhead_floor_bytes=(
                    self._overhead_floor_bytes
                ),
                overhead_fraction=(
                    self._overhead_fraction
                ),
            )
        )

        runtime_requirement = int(
            runtime[
                "requirement_bytes"
            ]
        )

        adjusted_requirements: dict[
            str,
            dict[str, int],
        ] = {}

        adjusted_resolutions: dict[
            str,
            dict[str, Any],
        ] = {}

        for (
            raw_model_id,
            raw_requirements,
        ) in requirements_by_model.items():
            model_id = str(
                raw_model_id
            )

            if not isinstance(
                raw_requirements,
                Mapping,
            ):
                raise VllmRuntimePlanningError(
                    f"Invalid requirements for {model_id}"
                )

            model_requirements = {
                str(key):
                    int(value)

                for key, value
                in raw_requirements.items()
            }

            base_requirement = int(
                model_requirements.get(
                    pool_id,
                    0,
                )
            )

            adjusted_requirement = max(
                base_requirement,
                runtime_requirement,
            )

            model_requirements[
                pool_id
            ] = adjusted_requirement

            adjusted_requirements[
                model_id
            ] = model_requirements

            raw_resolution = (
                resolutions.get(
                    raw_model_id
                )
            )

            if raw_resolution is None:
                raw_resolution = (
                    resolutions.get(
                        model_id
                    )
                )

            if not isinstance(
                raw_resolution,
                Mapping,
            ):
                raise VllmRuntimePlanningError(
                    f"Missing resolution for {model_id}"
                )

            resolution = copy.deepcopy(
                dict(raw_resolution)
            )

            base_basis = resolution.get(
                "basis"
            )

            resolution[
                "requirements"
            ] = dict(
                model_requirements
            )

            resolution[
                "basis"
            ] = (
                "runtime_aware_vllm_config"
            )

            resolution[
                "base_requirement_basis"
            ] = base_basis

            resolution[
                "runtime_reservation"
            ] = {
                "provider":
                    "vllm",

                "pool_id":
                    pool_id,

                "policy":
                    (
                        "configured_gpu_fraction_"
                        "plus_runtime_overhead_v1"
                    ),

                "base_requirement_bytes":
                    base_requirement,

                "runtime_requirement_bytes":
                    runtime_requirement,

                "selected_requirement_bytes":
                    adjusted_requirement,

                **runtime,
            }

            adjusted_resolutions[
                model_id
            ] = resolution

        view[
            "requirements_by_model"
        ] = adjusted_requirements

        view[
            "requirement_resolutions_by_model"
        ] = adjusted_resolutions

        phase9 = view.get(
            "phase9"
        )

        if not isinstance(
            phase9,
            Mapping,
        ):
            phase9 = {}

        phase9 = dict(
            phase9
        )

        phase9[
            "runtime_reservation"
        ] = {
            "provider":
                "vllm",

            "pool_id":
                pool_id,

            "gpu_memory_utilization":
                self._gpu_memory_utilization,

            "requirement_bytes":
                runtime_requirement,

            "policy":
                (
                    "configured_gpu_fraction_"
                    "plus_runtime_overhead_v1"
                ),
        }

        view[
            "phase9"
        ] = phase9

        return view
