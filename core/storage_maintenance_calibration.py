from adapters.maintenance import (
    get_maintenance_lifecycle_adapter,
)

from core.config import (
    load_config,
)

from core.storage_capacity_calibration import (
    calibrate_storage_capacity,
)

from core.storage_maintenance import (
    storage_maintenance_session,
)

from core.platform_storage_reconciliation import (
    reconcile_platform_storage_usage,
)

from core.storage_capacity_cache import (
    record_capacity_calibration,
)


STORAGE_MAINTENANCE_CALIBRATION_SCHEMA_VERSION = 1


def calibrate_storage_capacity_in_maintenance(
    *,
    config=None,
    maximum_probe_bytes=None,
    emergency_reserve_bytes=None,
    lifecycle_provider="current_cli",
    force_verify=False,
):
    """
    Run the EXISTING storage-capacity calibration algorithm inside
    the validated maintenance safety envelope.

    Sequence:

        maintenance lock
        capture original workload state
        quiesce workload
        hold emergency reserve
        run existing calibration coordinator
        clean probe files
        release emergency reserve
        restore original workload state
        release maintenance lock

    This function deliberately does NOT implement another sonar
    algorithm.

    The existing calibrate_storage_capacity() remains responsible
    for:

        provider/local evidence
        sonar fallback
        exponential expansion/backoff
        binary refinement
        lower/upper-bound evidence
        capacity consensus

    Safety gates:

        maintenance_sonar_enabled
            Required for this maintenance workflow.

        boundary_search_enabled
            NOT required for a bounded verification whose explicit
            maximum_probe_bytes remains below a true capacity-boundary
            search policy.

    A later aggressive/exact-ish boundary mode will additionally
    require boundary_search_enabled.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    if not settings.get(
        "maintenance_sonar_enabled",
        False,
    ):
        return {
            "schema_version": (
                STORAGE_MAINTENANCE_CALIBRATION_SCHEMA_VERSION
            ),

            "performed": False,

            "reason": (
                "maintenance_sonar_disabled"
            ),

            "maintenance": None,

            "calibration": None,

            "post_state": None,
        }

    if maximum_probe_bytes is None:
        raise ValueError(
            "maximum_probe_bytes must be explicitly supplied "
            "for bounded maintenance calibration."
        )

    maximum_probe_bytes = int(
        maximum_probe_bytes
    )

    if maximum_probe_bytes <= 0:
        raise ValueError(
            "maximum_probe_bytes must be positive."
        )

    lifecycle = (
        get_maintenance_lifecycle_adapter(
            lifecycle_provider
        )
    )

    maintenance_summary = None
    calibration = None

    with storage_maintenance_session(
        config=config,

        emergency_reserve_bytes=(
            emergency_reserve_bytes
        ),

        lifecycle_provider=(
            lifecycle_provider
        ),
    ) as session:

        maintenance_summary = {
            "prior_state": (
                session[
                    "prior_state"
                ]
            ),

            "quiesced_state": (
                session[
                    "quiesced_state"
                ]
            ),

            "emergency_reserve": (
                session[
                    "emergency_reserve"
                ]
            ),

            "lock": (
                session[
                    "lock"
                ]
            ),

            "maximum_probe_bytes": (
                maximum_probe_bytes
            ),

            "boundary_search_enabled": bool(
                session[
                    "boundary_search_enabled"
                ]
            ),
        }

        calibration = (
            calibrate_storage_capacity(
                config=config,

                maximum_probe_bytes=(
                    maximum_probe_bytes
                ),

                force_verify=(
                    force_verify
                ),
            )
        )

    #
    # Context has exited here:
    #
    # emergency reserve released
    # original workload restored
    # maintenance lock released
    #

    post_state = (
        lifecycle.capture_workload_state()
    )

    #
    # Persist empirical calibration only AFTER:
    #
    #   probe files are gone
    #   emergency reserve is released
    #   original workload state is restored
    #
    # The empirical remaining-capacity bound itself was observed
    # while the emergency reserve was held, so reusing it later is
    # conservative: actual free capacity after reserve release is
    # not smaller merely because the reserve was removed.
    #

    post_platform_usage = (
        reconcile_platform_storage_usage(
            config
        )
    )

    platform_used_bytes = (
        post_platform_usage.get(
            "total_platform_used_bytes"
        )
    )

    if (
        calibration
        and calibration.get(
            "performed",
            False,
        )
        and platform_used_bytes is not None
    ):
        capacity_cache = (
            record_capacity_calibration(
                calibration,

                platform_used_bytes=(
                    int(
                        platform_used_bytes
                    )
                ),

                config=config,
            )
        )

    elif not calibration:
        capacity_cache = {
            "recorded": False,

            "reason": (
                "calibration_missing"
            ),
        }

    elif not calibration.get(
        "performed",
        False,
    ):
        capacity_cache = {
            "recorded": False,

            "reason": (
                "calibration_not_performed"
            ),
        }

    else:
        capacity_cache = {
            "recorded": False,

            "reason": (
                "platform_usage_unresolved"
            ),
        }

    return {
        "schema_version": (
            STORAGE_MAINTENANCE_CALIBRATION_SCHEMA_VERSION
        ),

        "performed": bool(
            calibration
            and calibration.get(
                "performed",
                False,
            )
        ),

        "reason": (
            calibration.get(
                "reason"
            )
            if calibration
            else None
        ),

        "maintenance": (
            maintenance_summary
        ),

        "calibration": (
            calibration
        ),

        "post_state": (
            post_state
        ),

        "post_platform_usage": (
            post_platform_usage
        ),

        "capacity_cache": (
            capacity_cache
        ),
    }
