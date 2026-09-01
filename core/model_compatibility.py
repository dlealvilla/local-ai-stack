from copy import deepcopy


COMPATIBILITY_SCHEMA_VERSION = 1

# PROVISIONAL:
# A known model weight footprint occupying <= 75% of a single
# accelerator's total memory is treated as a reasonable static
# candidate.
#
# This is NOT an admission-control threshold.
# Capacity Planner / Resource Manager will make the final decision.
STATIC_GPU_WEIGHT_BUDGET = 0.75

STATIC_RAM_WEIGHT_BUDGET = 0.75


def _append_unique(items, value):
    if value and value not in items:
        items.append(value)


def _known_model_size_bytes(model):
    size = model.get(
        "size",
        {},
    )

    installed = size.get(
        "installed_bytes"
    )

    if isinstance(
        installed,
        (int, float),
    ):
        return int(installed)

    download = size.get(
        "download_bytes"
    )

    if isinstance(
        download,
        (int, float),
    ):
        return int(download)

    return None


def _largest_gpu_vram_gb(hardware):
    values = [
        gpu.get(
            "vram_total_gb"
        )
        for gpu in hardware.get(
            "gpus",
            []
        )
        if isinstance(
            gpu.get(
                "vram_total_gb"
            ),
            (int, float),
        )
    ]

    if not values:
        return None

    # Conservative v1:
    # do not assume tensor parallelism or pooled GPU memory.
    return max(values)


def _gpu_vendors(hardware):
    return {
        str(
            gpu.get(
                "vendor",
                ""
            )
        ).lower()
        for gpu in hardware.get(
            "gpus",
            []
        )
        if gpu.get("vendor")
    }


def _candidate_runtimes(
    model,
    hardware,
):
    weight_format = (
        model.get(
            "format",
            {}
        ).get(
            "weights"
        )
    )

    operating_system = str(
        hardware.get(
            "operating_system",
            ""
        )
    ).lower()

    architecture = str(
        hardware.get(
            "architecture",
            ""
        )
    ).lower()

    vendors = _gpu_vendors(
        hardware
    )

    candidates = []

    if weight_format in {
        "safetensors",
        "pytorch_bin",
    }:
        if (
            operating_system == "linux"
            and "nvidia" in vendors
        ):
            candidates.append(
                "vllm"
            )

        if (
            operating_system == "darwin"
            and architecture in {
                "arm64",
                "aarch64",
            }
        ):
            # FUTURE:
            # Exact architecture/model compatibility still needs
            # runtime-specific evaluation.
            candidates.append(
                "mlx"
            )

    if weight_format == "gguf":
        candidates.append(
            "llama_cpp"
        )

    return candidates


def evaluate_model_compatibility(
    model,
    hardware,
    config,
):
    """
    Evaluate static model/host compatibility.

    This answers:

        "Is this model a plausible candidate for this host?"

    It intentionally does NOT answer:

        "Can I start it right now?"

    Live RAM/VRAM usage, reservations, existing models and
    concurrency belong to Capacity Planner / Resource Manager.
    """

    evaluated = deepcopy(
        model
    )

    reasons = []
    recommendations = []

    conditional = False
    unsupported = False

    weight_format = (
        model.get(
            "format",
            {}
        ).get(
            "weights"
        )
    )

    family = model.get(
        "family"
    )

    architecture = model.get(
        "architecture"
    )

    discovery = model.get(
        "discovery",
        {},
    )

    runtime_candidates = (
        _candidate_runtimes(
            model,
            hardware,
        )
    )

    evaluated.setdefault(
        "runtime",
        {},
    )

    evaluated[
        "runtime"
    ][
        "supported"
    ] = runtime_candidates

    #
    # 1. Format/runtime compatibility
    #

    if weight_format in {
        "safetensors",
        "pytorch_bin",
    }:
        if runtime_candidates:
            _append_unique(
                reasons,
                (
                    f"{weight_format} weights have a candidate "
                    f"runtime for the detected host: "
                    f"{', '.join(runtime_candidates)}."
                ),
            )
        else:
            conditional = True

            _append_unique(
                reasons,
                (
                    f"{weight_format} weights were detected, "
                    "but no validated runtime candidate is "
                    "currently known for this host."
                ),
            )

            _append_unique(
                recommendations,
                (
                    "Select or install a compatible inference "
                    "runtime for this hardware."
                ),
            )

    elif weight_format == "gguf":
        conditional = True

        _append_unique(
            reasons,
            (
                "GGUF weights are suitable for the llama.cpp "
                "runtime family, but llama.cpp is not yet a "
                "working runtime adapter in this deployment."
            ),
        )

        _append_unique(
            recommendations,
            (
                "Use the future llama.cpp runtime adapter "
                "for this model format."
            ),
        )

    elif weight_format is None:
        conditional = True

        _append_unique(
            reasons,
            (
                "The model weight format is unknown, so runtime "
                "compatibility cannot yet be confirmed."
            ),
        )

        _append_unique(
            recommendations,
            (
                "Inspect the model artifacts before deployment."
            ),
        )

    else:
        conditional = True

        _append_unique(
            reasons,
            (
                f"Weight format '{weight_format}' is not yet "
                "covered by the compatibility rules."
            ),
        )

        _append_unique(
            recommendations,
            (
                "Use a runtime adapter that explicitly supports "
                "this model format."
            ),
        )

    #
    # 2. Compare with currently configured runtime
    #

    current_runtime = (
        config.get(
            "inference",
            {}
        ).get(
            "provider"
        )
    )

    if (
        runtime_candidates
        and current_runtime
        not in runtime_candidates
    ):
        conditional = True

        _append_unique(
            reasons,
            (
                f"The configured inference runtime "
                f"'{current_runtime}' is not one of the current "
                f"candidate runtimes for this artifact."
            ),
        )

        _append_unique(
            recommendations,
            (
                "Select an appropriate runtime before starting "
                "this model."
            ),
        )

    #
    # 3. Access restrictions
    #

    if discovery.get(
        "gated"
    ):
        conditional = True

        _append_unique(
            reasons,
            (
                "The source repository is gated and may require "
                "explicit access approval and credentials."
            ),
        )

        _append_unique(
            recommendations,
            (
                "Configure authorized source credentials before "
                "download."
            ),
        )

    if discovery.get(
        "private"
    ):
        conditional = True

        _append_unique(
            reasons,
            (
                "The source repository is private."
            ),
        )

        _append_unique(
            recommendations,
            (
                "Configure authorized private-registry "
                "credentials before download."
            ),
        )

    #
    # 4. Metadata quality
    #

    if (
        family is None
        and architecture is None
    ):
        conditional = True

        _append_unique(
            reasons,
            (
                "Model family and architecture metadata are "
                "missing."
            ),
        )

        _append_unique(
            recommendations,
            (
                "Inspect detailed source metadata before "
                "deployment."
            ),
        )

    #
    # 5. Static memory feasibility
    #
    # IMPORTANT:
    # Use TOTAL accelerator memory here, not currently free
    # accelerator memory.
    #
    # Current free memory is runtime state and belongs to the
    # Resource Manager / Capacity Planner.
    #

    model_size_bytes = (
        _known_model_size_bytes(
            model
        )
    )

    largest_gpu_gb = (
        _largest_gpu_vram_gb(
            hardware
        )
    )

    ram_total_gb = hardware.get(
        "ram_total_gb"
    )

    if model_size_bytes is None:
        conditional = True

        _append_unique(
            reasons,
            (
                "Model artifact size is not known, so static "
                "memory fit cannot yet be confirmed."
            ),
        )

        _append_unique(
            recommendations,
            (
                "Resolve model artifact size before download or "
                "deployment."
            ),
        )

    else:
        model_size_gb = (
            model_size_bytes
            / (1024 ** 3)
        )

        evaluated[
            "requirements"
        ][
            "weight_size_gb"
        ] = model_size_gb

        if largest_gpu_gb is not None:
            conservative_gpu_budget = (
                largest_gpu_gb
                * STATIC_GPU_WEIGHT_BUDGET
            )

            if (
                model_size_gb
                <= conservative_gpu_budget
            ):
                _append_unique(
                    reasons,
                    (
                        f"Known model artifact size "
                        f"({model_size_gb:.2f} GB) is within the "
                        f"conservative static single-GPU weight "
                        f"budget ({conservative_gpu_budget:.2f} "
                        "GB)."
                    ),
                )

            elif model_size_gb <= largest_gpu_gb:
                conditional = True

                _append_unique(
                    reasons,
                    (
                        f"Model weights ({model_size_gb:.2f} GB) "
                        "fit inside total accelerator memory, "
                        "but leave insufficient conservative "
                        "headroom for runtime and KV-cache "
                        "overhead."
                    ),
                )

                _append_unique(
                    recommendations,
                    (
                        "Consider a smaller or quantized variant, "
                        "lower context/concurrency, or offloading."
                    ),
                )

            elif (
                isinstance(
                    ram_total_gb,
                    (int, float),
                )
                and model_size_gb
                <= (
                    ram_total_gb
                    * STATIC_RAM_WEIGHT_BUDGET
                )
            ):
                conditional = True

                _append_unique(
                    reasons,
                    (
                        f"Model weights ({model_size_gb:.2f} GB) "
                        "exceed the largest single GPU "
                        f"({largest_gpu_gb:.2f} GB), but may fit "
                        "within system RAM."
                    ),
                )

                _append_unique(
                    recommendations,
                    (
                        "Use CPU/GPU offloading, a quantized "
                        "variant, or a runtime supporting the "
                        "required placement strategy."
                    ),
                )

            else:
                unsupported = True

                _append_unique(
                    reasons,
                    (
                        f"Model weights ({model_size_gb:.2f} GB) "
                        "exceed the conservative memory capacity "
                        "available to this single-host v1 "
                        "evaluation."
                    ),
                )

                _append_unique(
                    recommendations,
                    (
                        "Choose a smaller/quantized model or use "
                        "future multi-host/model-placement "
                        "capabilities."
                    ),
                )

        elif isinstance(
            ram_total_gb,
            (int, float),
        ):
            conservative_ram_budget = (
                ram_total_gb
                * STATIC_RAM_WEIGHT_BUDGET
            )

            if (
                model_size_gb
                <= conservative_ram_budget
            ):
                conditional = True

                _append_unique(
                    reasons,
                    (
                        f"Model weights ({model_size_gb:.2f} GB) "
                        "fit within the conservative system RAM "
                        f"budget ({conservative_ram_budget:.2f} "
                        "GB), but accelerator execution is not "
                        "available."
                    ),
                )

                _append_unique(
                    recommendations,
                    (
                        "Use an appropriate CPU runtime or add "
                        "a supported accelerator."
                    ),
                )

            else:
                unsupported = True

                _append_unique(
                    reasons,
                    (
                        f"Model weights ({model_size_gb:.2f} GB) "
                        "exceed the conservative RAM budget for "
                        "this host."
                    ),
                )

                _append_unique(
                    recommendations,
                    (
                        "Choose a smaller or quantized model."
                    ),
                )

        else:
            conditional = True

            _append_unique(
                reasons,
                (
                    "Host memory capacity could not be "
                    "determined."
                ),
            )

    #
    # 6. Final classification
    #

    if unsupported:
        status = "unsupported"
        confidence = "medium"

    elif conditional:
        status = "conditionally_compatible"
        confidence = "medium"

    else:
        status = "compatible"
        confidence = "medium"

    evaluated[
        "compatibility"
    ] = {
        "schema_version": (
            COMPATIBILITY_SCHEMA_VERSION
        ),

        "status": status,

        "confidence": confidence,

        "reasons": reasons,

        "recommendations": (
            recommendations
        ),

        "basis": {
            "static_hardware": True,

            # Explicitly document this distinction.
            "uses_total_gpu_memory": True,

            "uses_live_free_gpu_memory": False,

            "capacity_planner_required_before_start": True,
        },
    }

    return evaluated
