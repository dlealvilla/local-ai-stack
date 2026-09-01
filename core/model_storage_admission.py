from core.config import load_config

from core.model_storage_requirements import (
    estimate_model_install_storage,
)

from core.storage_budget import (
    evaluate_storage_operation,
)

from core.storage_planning import (
    build_storage_plan,
)


MODEL_STORAGE_ADMISSION_SCHEMA_VERSION = 1


def _gb_to_bytes(
    value,
):
    return int(
        float(value)
        * 1_000_000_000
    )


def _model_id(
    model,
):
    for key in [
        "model_id",
        "id",
        "name",
    ]:
        value = model.get(
            key
        )

        if value:
            return str(
                value
            )

    return None


def evaluate_model_storage_admission(
    model,
    *,
    config=None,
    storage_plan=None,
    calibrate_if_required=False,
    maximum_probe_bytes=None,
):
    """
    Evaluate whether this candidate may be installed NOW.

    This result is intentionally DYNAMIC.

    It is NOT persisted as immutable Model Catalog metadata.

    Every normal evaluation can rebuild the current Storage Plan,
    which means its answer changes automatically when:

        models are installed
        models are deleted
        staging/cache usage changes
        safe capacity changes
        administrator allocation percentage changes
        calibration changes

    Classification:

        compatible
            Strong storage evidence says the install fits now.

        conditionally_compatible
            Artifact size or current safe budget must be verified.

        unsupported
            Strong current storage evidence says the install does
            not fit now.

    "unsupported" here means "cannot be admitted in the current
    state", not "this model can never run on this machine."
    """

    if config is None:
        config = load_config()

    if storage_plan is None:
        storage_plan = build_storage_plan(
            config=config,
            calibrate_if_required=(
                calibrate_if_required
            ),
            maximum_probe_bytes=(
                maximum_probe_bytes
            ),
        )

    settings = config.get(
        "storage_capacity",
        {},
    )

    requirement = (
        estimate_model_install_storage(
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

    budget = storage_plan[
        "platform_budget"
    ]

    state_snapshot = {
        "platform_allocation_percent": (
            budget.get(
                "platform_allocation_percent"
            )
        ),

        "platform_used_bytes": (
            budget.get(
                "platform_used_bytes"
            )
        ),

        "available_for_new_platform_bytes": (
            budget.get(
                "available_for_new_platform_bytes"
            )
        ),

        "capacity_remaining_bytes": (
            storage_plan[
                "capacity"
            ][
                "resolved"
            ].get(
                "remaining_bytes"
            )
        ),

        "capacity_basis": (
            storage_plan[
                "capacity"
            ][
                "resolved"
            ].get(
                "basis"
            )
        ),

        "capacity_confidence": (
            storage_plan[
                "capacity"
            ][
                "resolved"
            ].get(
                "confidence"
            )
        ),

        "usage_source": (
            storage_plan.get(
                "platform_usage_source"
            )
        ),
    }

    #
    # Unknown candidate artifact size.
    #

    if not requirement[
        "resolved"
    ]:
        return {
            "schema_version": (
                MODEL_STORAGE_ADMISSION_SCHEMA_VERSION
            ),

            "dynamic": True,

            "model_id": (
                _model_id(
                    model
                )
            ),

            "dimension": "storage",

            "classification": (
                "conditionally_compatible"
            ),

            "admitted_now": None,

            "reason": (
                "artifact_size_must_be_resolved"
            ),

            "requirement": requirement,

            "state": state_snapshot,
        }

    #
    # Current platform storage state unresolved.
    #

    if not budget.get(
        "resolved",
        False,
    ):
        return {
            "schema_version": (
                MODEL_STORAGE_ADMISSION_SCHEMA_VERSION
            ),

            "dynamic": True,

            "model_id": (
                _model_id(
                    model
                )
            ),

            "dimension": "storage",

            "classification": (
                "conditionally_compatible"
            ),

            "admitted_now": None,

            "reason": (
                "current_platform_storage_budget_unresolved"
            ),

            "requirement": requirement,

            "state": state_snapshot,
        }

    operation = (
        evaluate_storage_operation(
            storage_budget=budget,

            required_bytes=(
                requirement[
                    "peak_additional_bytes"
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
    # Candidate fits current dynamic budget.
    #

    if operation[
        "feasible"
    ]:
        if size_confidence == "high":
            classification = "compatible"

            admitted_now = True

            reason = None

        else:
            classification = (
                "conditionally_compatible"
            )

            admitted_now = None

            reason = (
                "artifact_size_estimate_requires_pre_download_verification"
            )

    #
    # Candidate exceeds current dynamic budget.
    #

    else:
        if size_confidence == "high":
            classification = "unsupported"

            admitted_now = False

            reason = (
                "current_platform_storage_budget_exceeded"
            )

        else:
            classification = (
                "conditionally_compatible"
            )

            admitted_now = None

            reason = (
                "estimated_artifact_exceeds_current_budget_but_exact_size_is_unresolved"
            )

    return {
        "schema_version": (
            MODEL_STORAGE_ADMISSION_SCHEMA_VERSION
        ),

        "dynamic": True,

        "model_id": (
            _model_id(
                model
            )
        ),

        "dimension": "storage",

        "classification": (
            classification
        ),

        "admitted_now": (
            admitted_now
        ),

        "reason": reason,

        "requirement": requirement,

        "operation_evaluation": (
            operation
        ),

        "state": state_snapshot,
    }
