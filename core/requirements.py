import os


WEIGHT_EXTENSIONS = (
    ".safetensors",
    ".gguf",
    ".bin",
)


def get_weight_size_gb(model_path):
    total_bytes = 0

    for root, dirs, files in os.walk(model_path):
        for filename in files:
            if filename.lower().endswith(WEIGHT_EXTENSIONS):
                file_path = os.path.join(root, filename)

                try:
                    total_bytes += os.path.getsize(file_path)
                except OSError:
                    pass

    return total_bytes / (1024 ** 3)


def estimate_model_requirements(model):
    weight_size_gb = get_weight_size_gb(model["path"])

    return {
        "weight_size_gb": weight_size_gb,
        "runtime_overhead_gb": None,
        "kv_cache_gb": None,
        "estimated_total_vram_gb": None,
        "confidence": "incomplete"
    }


# ---------------------------------------------------------------------------
# Phase 8B model-resource requirement contract.
#
# The legacy estimate_model_requirements() function above remains intact for
# the existing deployment planner.
#
# This newer contract deliberately separates:
#
#     model weight files on disk
#
# from:
#
#     runtime memory actually required to start and serve the model.
#
# Runtime-specific adapters will fill those unresolved values later.
# ---------------------------------------------------------------------------


MODEL_RESOURCE_REQUIREMENTS_SCHEMA_VERSION = 1


def get_weight_size_bytes(
    model_path,
):
    """
    Measure known local model weight files exactly.

    This measures artifact bytes on disk.

    It does NOT claim those bytes equal:
        - RAM residency
        - VRAM residency
        - unified-memory residency
        - runtime overhead
        - KV cache
        - activation peaks
    """

    total_bytes = 0

    found_weight_file = False


    for root, dirs, files in os.walk(
        model_path
    ):

        for filename in files:

            if not filename.lower().endswith(
                WEIGHT_EXTENSIONS
            ):
                continue


            file_path = os.path.join(
                root,
                filename,
            )


            try:
                size = os.path.getsize(
                    file_path
                )

            except OSError:
                continue


            found_weight_file = True

            total_bytes += max(
                0,
                int(
                    size
                ),
            )


    return {
        "resolved": (
            found_weight_file
        ),

        "bytes": (
            total_bytes
            if found_weight_file
            else None
        ),

        "confidence": (
            "high"
            if found_weight_file
            else "unresolved"
        ),

        "method": (
            "exact_local_weight_file_measurement"
            if found_weight_file
            else "no_known_weight_files_found"
        ),
    }


def build_model_resource_requirements(
    model,
):
    """
    Build the platform-owned model resource requirement envelope.

    This answers only what is currently known.

    It does NOT yet answer:
        "Can this model start now?"

    The initial Phase 8B implementation knows exact local weight-file
    artifact bytes when the model exists locally, but deliberately leaves
    runtime memory components unresolved.

    Future runtime adapters may resolve:
        - weight residency
        - runtime/framework overhead
        - activation peak
        - graph/capture memory
        - KV cache
        - CPU offload
        - total RAM
        - total dedicated VRAM
        - total unified memory
    """

    if not isinstance(
        model,
        dict,
    ):
        raise TypeError(
            "model must be a mapping"
        )


    model_id = (
        model.get(
            "model_id"
        )
        or model.get(
            "name"
        )
        or model.get(
            "id"
        )
    )


    model_path = (
        model.get(
            "path"
        )
    )


    if model_path:

        weight_artifact = (
            get_weight_size_bytes(
                model_path
            )
        )

    else:

        weight_artifact = {
            "resolved": False,

            "bytes": None,

            "confidence": (
                "unresolved"
            ),

            "method": (
                "local_model_path_unavailable"
            ),
        }


    runtime = (
        (
            model.get(
                "deployment"
            )
            or {}
        ).get(
            "runtime"
        )
        or (
            model.get(
                "runtime"
            )
            if isinstance(
                model.get(
                    "runtime"
                ),
                str,
            )
            else None
        )
    )


    runtime_components = {
        #
        # Weight artifact bytes are evidence only.
        # Residency may differ by runtime, format, quantization,
        # conversion and offload strategy.
        #
        "weight_residency_bytes": None,

        "runtime_overhead_bytes": None,

        "activation_peak_bytes": None,

        "graph_capture_bytes": None,

        "kv_cache_bytes": None,

        "cpu_offload_bytes": None,

        "total_runtime_memory_bytes": None,
    }


    target_requirements = {
        "system_ram_bytes": None,

        "dedicated_vram_bytes": None,

        "unified_memory_bytes": None,
    }


    unresolved = [
        "weight_residency_bytes",
        "runtime_overhead_bytes",
        "activation_peak_bytes",
        "kv_cache_bytes",
        "total_runtime_memory_bytes",
        "system_ram_bytes",
        "dedicated_vram_bytes",
        "unified_memory_bytes",
    ]


    return {
        "schema_version": (
            MODEL_RESOURCE_REQUIREMENTS_SCHEMA_VERSION
        ),

        "model": {
            "model_id": (
                model_id
            ),

            "path": (
                model_path
            ),
        },

        "runtime": {
            "provider": (
                runtime
            ),
        },

        "artifact_evidence": {
            "weight_files": (
                weight_artifact
            ),
        },

        "runtime_components": (
            runtime_components
        ),

        "target_requirements": (
            target_requirements
        ),

        "unresolved_fields": (
            unresolved
        ),

        "dependency_chain": [
            "model_artifact_evidence",
            "runtime_specific_weight_residency",
            "runtime_overhead",
            "activation_peak",
            "graph_capture_memory",
            "kv_cache",
            "offload_strategy",
            "target_memory_requirements",
            "dynamic_resource_admission",
        ],

        "runtime_requirements_ready": False,

        "admission_ready": False,

        "admission_not_ready_reasons": [
            "runtime_weight_residency_unresolved",
            "runtime_overhead_unresolved",
            "activation_peak_unresolved",
            "kv_cache_unresolved",
            "target_memory_requirements_unresolved",
            "resource_manager_reservations_not_applied",
            "dynamic_resource_admission_not_applied",
        ],
    }
