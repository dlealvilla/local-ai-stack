from core.config import load_config

from core.storage_capacity_resolution import (
    resolve_storage_capacity,
)

from core.storage_probe import (
    probe_required_capacity,
)

from core.storage_sonar import (
    adaptive_capacity_search,
    sonar_result_to_evidence,
)


STORAGE_CALIBRATION_SCHEMA_VERSION = 1


def _mb_to_bytes(
    value,
):
    return int(
        float(value)
        * 1024
        * 1024
    )


def _gb_to_bytes(
    value,
):
    return int(
        float(value)
        * 1024
        * 1024
        * 1024
    )


def calibrate_storage_capacity(
    *,
    config=None,
    maximum_probe_bytes=None,
    force_verify=False,
):
    """
    Resolve storage using normal evidence first.

    If that cannot determine a safe remaining-capacity value,
    automatically fall back to bounded Capacity Sonar.

    IMPORTANT:
    This is an explicit calibration workflow.

    Ordinary read-only capacity/status calls should NOT allocate
    probe files on every request.

    Future onboarding/admin workflows can invoke this coordinator
    when calibration is required.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    before = resolve_storage_capacity(
        config
    )

    sonar_required = bool(
        before[
            "fallback"
        ][
            "sonar_required"
        ]
    )

    sonar_enabled = bool(
        settings.get(
            "sonar_fallback_enabled",
            True,
        )
    )

    if (
        not force_verify
        and not sonar_required
    ):
        return {
            "schema_version": (
                STORAGE_CALIBRATION_SCHEMA_VERSION
            ),

            "performed": False,

            "reason": (
                "capacity_already_resolved"
            ),

            "before": before,

            "sonar": None,

            "empirical_evidence": [],

            "after": before,
        }

    if not sonar_enabled:
        return {
            "schema_version": (
                STORAGE_CALIBRATION_SCHEMA_VERSION
            ),

            "performed": False,

            "reason": (
                "sonar_fallback_disabled"
            ),

            "before": before,

            "sonar": None,

            "empirical_evidence": [],

            "after": before,
        }

    start_bytes = _mb_to_bytes(
        settings.get(
            "sonar_start_mb",
            64,
        )
    )

    resolution_bytes = _mb_to_bytes(
        settings.get(
            "sonar_resolution_mb",
            256,
        )
    )

    configured_maximum = _gb_to_bytes(
        settings.get(
            "sonar_max_automatic_gb",
            64.0,
        )
    )

    #
    # Never exceed the lower of:
    #
    # - automatic sonar policy ceiling
    # - the underlying individual-probe safety ceiling
    #

    probe_maximum = _gb_to_bytes(
        settings.get(
            "probe_max_gb",
            64.0,
        )
    )

    effective_maximum = min(
        configured_maximum,
        probe_maximum,
    )

    if maximum_probe_bytes is not None:
        effective_maximum = min(
            effective_maximum,
            int(
                maximum_probe_bytes
            ),
        )

    if effective_maximum < start_bytes:
        raise ValueError(
            "Effective sonar ceiling is smaller "
            "than sonar starting size."
        )

    initial_estimate = (
        before[
            "resolved"
        ][
            "remaining_bytes"
        ]
    )

    def real_probe(
        requested_bytes,
    ):
        result = probe_required_capacity(
            requested_bytes,
            config=config,
        )

        return bool(
            result.get(
                "supported",
                False,
            )
            and result.get(
                "success",
                False,
            )
            and result.get(
                "reservation_accepted",
                result.get(
                    "success",
                    False,
                ),
            )
        )

    sonar = adaptive_capacity_search(
        probe=real_probe,

        start_bytes=(
            start_bytes
        ),

        resolution_bytes=(
            resolution_bytes
        ),

        growth_factor=float(
            settings.get(
                "sonar_growth_factor",
                2.0,
            )
        ),

        backoff_factor=float(
            settings.get(
                "sonar_backoff_factor",
                0.5,
            )
        ),

        max_attempts=int(
            settings.get(
                "sonar_max_attempts",
                32,
            )
        ),

        initial_estimate_bytes=(
            initial_estimate
        ),

        maximum_probe_bytes=(
            effective_maximum
        ),
    )

    empirical_evidence = (
        sonar_result_to_evidence(
            sonar,
            source=(
                "capacity_sonar_posix_fallocate"
            ),
            scope=(
                before.get(
                    "provider"
                )
                or "storage_allocation"
            ),
            confidence="medium",
        )
    )

    after = resolve_storage_capacity(
        config,
        empirical_evidence=(
            empirical_evidence
        ),
    )

    return {
        "schema_version": (
            STORAGE_CALIBRATION_SCHEMA_VERSION
        ),

        "performed": True,

        "reason": (
            "sonar_fallback"
            if sonar_required
            else "verification_requested"
        ),

        "maximum_probe_bytes": (
            effective_maximum
        ),

        "before": before,

        "sonar": sonar,

        "empirical_evidence": (
            empirical_evidence
        ),

        "after": after,
    }
