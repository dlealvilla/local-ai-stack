from core.config import load_config

from core.model_storage_requirements import (
    estimate_model_storage_requirement,
)

from core.storage_budget import (
    evaluate_storage_operation,
)


MODEL_STORAGE_FEASIBILITY_SCHEMA_VERSION = 1


def _gb_to_bytes(
    value,
):
    return int(
        float(value)
        * 1_000_000_000
    )


def evaluate_model_storage_feasibility(
    model,
    *,
    storage_budget,
    config=None,
):
    """
    Evaluate ONLY the storage dimension of model feasibility.

    Overall model feasibility will later combine this with:

        RAM
        VRAM / unified memory
        accelerator/runtime compatibility
        CPU architecture
        context/concurrency
        runtime overhead
        current resource reservations

    Classification semantics:

    compatible
        Storage requirement is sufficiently known and safely fits.

    conditionally_compatible
        Storage size or capacity is unresolved/approximate and must
        be verified before the operation is authorized.

    unsupported
        Strong storage evidence shows the model operation cannot fit.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    requirement = (
        estimate_model_storage_requirement(
            model,

            overhead_fraction=float(
                settings.get(
                    "model_operation_overhead_fraction",
                    0.10,
                )
            ),

            overhead_min_bytes=(
                _gb_to_bytes(
                    settings.get(
                        "model_operation_overhead_min_gb",
                        1.0,
                    )
                )
            ),
        )
    )

    #
    # Unknown artifact footprint.
    #

    if not requirement[
        "resolved"
    ]:
        return {
            "schema_version": (
                MODEL_STORAGE_FEASIBILITY_SCHEMA_VERSION
            ),

            "classification": (
                "conditionally_compatible"
            ),

            "feasible": None,

            "reason": (
                "artifact_size_must_be_resolved"
            ),

            "requirement": requirement,

            "budget": storage_budget,
        }

    #
    # Capacity/budget has not yet been resolved.
    #

    if not storage_budget.get(
        "resolved",
        False,
    ):
        return {
            "schema_version": (
                MODEL_STORAGE_FEASIBILITY_SCHEMA_VERSION
            ),

            "classification": (
                "conditionally_compatible"
            ),

            "feasible": None,

            "reason": (
                "platform_storage_budget_must_be_resolved"
            ),

            "requirement": requirement,

            "budget": storage_budget,
        }

    operation = (
        evaluate_storage_operation(
            storage_budget=(
                storage_budget
            ),

            required_bytes=(
                requirement[
                    "required_additional_bytes"
                ]
            ),
        )
    )

    size_confidence = (
        requirement[
            "confidence"
        ]
    )

    #
    # Known requirement fits.
    #

    if operation[
        "feasible"
    ]:
        if size_confidence == "high":
            classification = "compatible"
            reason = None

        else:
            classification = (
                "conditionally_compatible"
            )

            reason = (
                "artifact_size_estimate_requires_verification"
            )

        return {
            "schema_version": (
                MODEL_STORAGE_FEASIBILITY_SCHEMA_VERSION
            ),

            "classification": classification,

            "feasible": True,

            "reason": reason,

            "requirement": requirement,

            "budget": storage_budget,

            "operation_evaluation": (
                operation
            ),
        }

    #
    # Requirement exceeds budget.
    #
    # Only strong size evidence earns a definitive unsupported
    # classification.
    #

    if size_confidence == "high":
        classification = "unsupported"

        reason = (
            "confirmed_storage_requirement_exceeds_budget"
        )

        feasible = False

    else:
        classification = (
            "conditionally_compatible"
        )

        reason = (
            "estimated_storage_requirement_exceeds_budget"
        )

        feasible = None

    return {
        "schema_version": (
            MODEL_STORAGE_FEASIBILITY_SCHEMA_VERSION
        ),

        "classification": (
            classification
        ),

        "feasible": feasible,

        "reason": reason,

        "requirement": requirement,

        "budget": storage_budget,

        "operation_evaluation": (
            operation
        ),
    }
