import subprocess

from pathlib import Path

from core.config import load_config
from core.storage_capacity import (
    inspect_storage_capacity,
)
from core.storage_capacity_evidence import (
    build_storage_evidence,
)


STORAGE_CAPACITY_RESOLUTION_SCHEMA_VERSION = 1


NETWORK_OR_SHARED_FILESYSTEMS = {
    "fuse",
    "fuseblk",
    "nfs",
    "nfs4",
    "cifs",
    "smb3",
    "ceph",
    "glusterfs",
    "lustre",
}


def _gb_to_bytes(
    value,
):
    return int(
        float(value)
        * 1_000_000_000
    )


def _measure_namespace_usage(
    path,
    *,
    timeout_seconds,
):
    """
    Best-effort namespace usage measurement.

    This is intentionally evidence rather than absolute truth:
    snapshots, deduplication, sparse files and provider accounting
    can produce different billing/storage semantics.
    """

    try:
        result = subprocess.run(
            [
                "du",
                "-sx",
                "-B1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=True,
        )

        first = (
            result.stdout
            .strip()
            .split()[0]
        )

        return {
            "available": True,
            "bytes": int(first),
            "reason": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "bytes": None,
            "reason": "timeout",
        }

    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        ValueError,
        IndexError,
    ):
        return {
            "available": False,
            "bytes": None,
            "reason": "measurement_failed",
        }


def _filesystem_remaining_is_credible(
    capacity,
):
    """
    Decide whether filesystem free-space figures can reasonably
    represent this allocation rather than a shared backend.

    Provider-specific adapters may later expose this explicitly.
    """

    mount = (
        capacity.get(
            "mount"
        )
        or {}
    )

    fs_type = str(
        mount.get(
            "filesystem_type",
            ""
        )
    ).lower()

    source = str(
        mount.get(
            "source",
            ""
        )
    ).lower()

    provider = capacity.get(
        "provider"
    )

    if provider == "runpod_network_volume":
        return False

    if fs_type in NETWORK_OR_SHARED_FILESYSTEMS:
        return False

    if (
        "runpod.net" in source
        or "/networkvolumes/" in source
    ):
        return False

    return True


def _consensus(
    point_estimates,
    *,
    relative_tolerance,
    absolute_tolerance_bytes,
):
    """
    Reconcile comparable remaining-capacity point estimates.

    Conservative rule:
        resolved value = smallest credible accepted estimate.

    Agreement is evaluated separately and affects confidence.
    """

    values = sorted(
        int(
            item[
                "value_bytes"
            ]
        )
        for item
        in point_estimates
        if (
            item.get(
                "accepted"
            )
            and item.get(
                "value_bytes"
            )
            is not None
        )
    )

    if not values:
        return {
            "resolved_bytes": None,
            "agreement": None,
            "spread_bytes": None,
            "allowed_spread_bytes": None,
        }

    minimum = values[0]
    maximum = values[-1]

    spread = (
        maximum
        - minimum
    )

    allowed = max(
        int(
            maximum
            * relative_tolerance
        ),
        absolute_tolerance_bytes,
    )

    agreement = (
        spread <= allowed
    )

    return {
        "resolved_bytes": minimum,
        "agreement": agreement,
        "spread_bytes": spread,
        "allowed_spread_bytes": allowed,
    }


def resolve_storage_capacity(
    config=None,
    *,
    empirical_evidence=None,
):
    """
    Produce the normalized storage-capacity result consumed by
    Capacity Planner.

    Resolution order is evidence-driven rather than provider-driven.

    If remaining space cannot be resolved credibly, the result
    explicitly requests empirical sonar fallback.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    capacity = (
        inspect_storage_capacity(
            config
        )
    )

    evidence = []

    #
    # 1. Explicit administrator quota.
    #

    override_gb = float(
        settings.get(
            "quota_override_gb",
            0.0,
        )
        or 0.0
    )

    if override_gb > 0:
        evidence.append(
            build_storage_evidence(
                evidence_id=(
                    "admin_quota"
                ),
                source=(
                    "administrator_override"
                ),
                scope=(
                    "configured_storage_allocation"
                ),
                evidence_type=(
                    "quota_total"
                ),
                value_bytes=(
                    _gb_to_bytes(
                        override_gb
                    )
                ),
                confidence=(
                    "authoritative"
                ),
                detail=(
                    "Administrator-provided storage quota."
                ),
            )
        )

    #
    # 2. Provider-native quota.
    #

    quota = (
        capacity.get(
            "quota"
        )
        or {}
    )

    if (
        quota.get(
            "known"
        )
        and quota.get(
            "total_bytes"
        )
        is not None
    ):
        evidence.append(
            build_storage_evidence(
                evidence_id=(
                    "provider_quota"
                ),
                source=(
                    quota.get(
                        "source"
                    )
                    or capacity.get(
                        "provider"
                    )
                ),
                scope=(
                    "provider_storage_allocation"
                ),
                evidence_type=(
                    "quota_total"
                ),
                value_bytes=(
                    quota[
                        "total_bytes"
                    ]
                ),
                confidence=(
                    "authoritative"
                ),
                detail=(
                    "Provider-reported provisioned storage."
                ),
            )
        )

    #
    # 3. Filesystem free-space observation.
    #

    filesystem = (
        capacity.get(
            "filesystem"
        )
        or {}
    )

    fs_free = filesystem.get(
        "free_bytes"
    )

    fs_credible = (
        _filesystem_remaining_is_credible(
            capacity
        )
    )

    if fs_free is not None:
        evidence.append(
            build_storage_evidence(
                evidence_id=(
                    "filesystem_free"
                ),
                source=(
                    "filesystem_statvfs"
                ),
                scope=(
                    "mounted_filesystem"
                ),
                evidence_type=(
                    "remaining_point"
                    if fs_credible
                    else "diagnostic"
                ),
                value_bytes=(
                    fs_free
                ),
                confidence=(
                    "high"
                    if fs_credible
                    else "rejected"
                ),
                accepted=(
                    fs_credible
                ),
                detail=(
                    (
                        "Filesystem free space is treated as "
                        "credible for this mount."
                    )
                    if fs_credible
                    else (
                        "Filesystem figure appears to describe "
                        "a shared/provider backing filesystem "
                        "and is not accepted as customer quota."
                    )
                ),
            )
        )

    #
    # 4. Namespace usage.
    #
    # If a credible quota total exists, quota - observed namespace
    # usage provides another remaining-space estimate.
    #

    quota_totals = [
        item
        for item in evidence
        if (
            item[
                "type"
            ]
            == "quota_total"
            and item[
                "accepted"
            ]
        )
    ]

    usage = None

    if quota_totals:
        data_root = Path(
            config[
                "platform"
            ][
                "data_root"
            ]
        ).resolve()

        usage = (
            _measure_namespace_usage(
                data_root,
                timeout_seconds=int(
                    settings.get(
                        "namespace_usage_timeout_seconds",
                        20,
                    )
                ),
            )
        )

        if usage[
            "available"
        ]:
            evidence.append(
                build_storage_evidence(
                    evidence_id=(
                        "namespace_usage"
                    ),
                    source=(
                        "du_namespace_scan"
                    ),
                    scope=(
                        str(
                            data_root
                        )
                    ),
                    evidence_type=(
                        "usage_point"
                    ),
                    value_bytes=(
                        usage[
                            "bytes"
                        ]
                    ),
                    confidence=(
                        "medium"
                    ),
                    detail=(
                        "Mounted namespace usage estimate."
                    ),
                )
            )

            # Conservative quota selection if authoritative totals
            # themselves disagree.
            effective_quota = min(
                item[
                    "value_bytes"
                ]
                for item
                in quota_totals
            )

            derived_remaining = max(
                0,
                effective_quota
                - usage[
                    "bytes"
                ],
            )

            evidence.append(
                build_storage_evidence(
                    evidence_id=(
                        "quota_minus_namespace_usage"
                    ),
                    source=(
                        "derived"
                    ),
                    scope=(
                        "configured_storage_allocation"
                    ),
                    evidence_type=(
                        "remaining_point"
                    ),
                    value_bytes=(
                        derived_remaining
                    ),
                    confidence=(
                        "medium"
                    ),
                    detail=(
                        "Conservative quota total minus "
                        "namespace usage."
                    ),
                )
            )

    #
    # 5. Empirical evidence can be supplied by Capacity Sonar.
    #

    for item in (
        empirical_evidence
        or []
    ):
        evidence.append(
            item
        )

    point_estimates = [
        item
        for item in evidence
        if (
            item[
                "type"
            ]
            == "remaining_point"
            and item[
                "accepted"
            ]
        )
    ]

    lower_bounds = [
        item
        for item in evidence
        if (
            item[
                "type"
            ]
            == "remaining_lower_bound"
            and item[
                "accepted"
            ]
            and item.get(
                "value_bytes"
            )
            is not None
        )
    ]

    upper_bounds = [
        item
        for item in evidence
        if (
            item[
                "type"
            ]
            == "remaining_upper_bound"
            and item[
                "accepted"
            ]
            and item.get(
                "value_bytes"
            )
            is not None
        )
    ]

    relative_tolerance = float(
        settings.get(
            "consensus_relative_tolerance",
            0.10,
        )
    )

    absolute_tolerance = (
        _gb_to_bytes(
            settings.get(
                "consensus_absolute_gb",
                2.0,
            )
        )
    )

    consensus = _consensus(
        point_estimates,
        relative_tolerance=(
            relative_tolerance
        ),
        absolute_tolerance_bytes=(
            absolute_tolerance
        ),
    )

    point_resolved = (
        consensus[
            "resolved_bytes"
        ]
    )

    strongest_lower_bound = (
        max(
            item[
                "value_bytes"
            ]
            for item in lower_bounds
        )
        if lower_bounds
        else None
    )

    smallest_upper_failure = (
        min(
            item[
                "value_bytes"
            ]
            for item in upper_bounds
        )
        if upper_bounds
        else None
    )

    resolution_basis = None
    bound_disagreement = False

    #
    # Reconcile point estimates and empirical bounds.
    #
    # A successful reservation is a SAFE lower bound.
    # A failed reservation is NOT itself safe capacity.
    #

    if point_resolved is not None:
        resolved_remaining = (
            point_resolved
        )

        resolution_basis = (
            "conservative_point_estimate"
        )

        comparison_reference = max(
            point_resolved,
            strongest_lower_bound
            or 0,
            smallest_upper_failure
            or 0,
        )

        bound_tolerance = max(
            int(
                comparison_reference
                * relative_tolerance
            ),
            absolute_tolerance,
        )

        #
        # A point estimate below a verified lower bound is
        # inconsistent, but the smaller point remains the more
        # conservative safe planning value.
        #

        if (
            strongest_lower_bound
            is not None
            and (
                strongest_lower_bound
                - point_resolved
            ) > bound_tolerance
        ):
            bound_disagreement = True

        #
        # If a point estimate lies materially ABOVE an observed
        # failed reservation, the point estimate is questionable.
        #
        # If a successful lower bound is available, fall back to
        # that verified-safe value.
        #
        # Without a successful lower bound, do not invent a safe
        # value from the failure boundary.
        #

        if (
            smallest_upper_failure
            is not None
            and (
                point_resolved
                - smallest_upper_failure
            ) > bound_tolerance
        ):
            bound_disagreement = True

            if strongest_lower_bound is not None:
                resolved_remaining = min(
                    point_resolved,
                    strongest_lower_bound,
                )

                resolution_basis = (
                    "verified_lower_bound_after_disagreement"
                )

            else:
                resolved_remaining = None

                resolution_basis = (
                    "unresolved_after_upper_bound_disagreement"
                )

    elif strongest_lower_bound is not None:
        #
        # No programmatic/local point estimate exists, but sonar
        # has empirically proved that at least this much storage
        # was reservable.
        #
        # Using the successful lower bound is conservative.
        #

        resolved_remaining = (
            strongest_lower_bound
        )

        resolution_basis = (
            "verified_lower_bound"
        )

    else:
        resolved_remaining = None
        resolution_basis = "unresolved"

    credible_quota_values = [
        item[
            "value_bytes"
        ]
        for item in quota_totals
    ]

    effective_total = (
        min(
            credible_quota_values
        )
        if credible_quota_values
        else None
    )

    protected_fraction = float(
        settings.get(
            "protected_free_fraction",
            0.15,
        )
    )

    warning_fraction = float(
        settings.get(
            "warning_free_fraction",
            0.20,
        )
    )

    minimum_reserve = (
        _gb_to_bytes(
            settings.get(
                "minimum_reserve_gb",
                10.0,
            )
        )
    )

    reserve_bytes = None
    safe_allocatable = None

    if resolved_remaining is not None:
        reserve_basis = (
            effective_total
            if effective_total
            is not None
            else resolved_remaining
        )

        reserve_bytes = max(
            minimum_reserve,
            int(
                reserve_basis
                * protected_fraction
            ),
        )

        safe_allocatable = max(
            0,
            resolved_remaining
            - reserve_bytes,
        )

    sonar_needed = (
        resolved_remaining
        is None
        and bool(
            settings.get(
                "sonar_fallback_enabled",
                True,
            )
        )
    )

    if resolved_remaining is None:
        confidence = "unknown"

    elif bound_disagreement:
        confidence = "low"

    elif (
        consensus[
            "agreement"
        ]
        is False
    ):
        confidence = "low"

    elif len(
        point_estimates
    ) >= 2:
        confidence = "high"

    elif (
        resolution_basis
        == "verified_lower_bound"
    ):
        confidence = "medium"

    else:
        confidence = "medium"

    warnings = []

    if (
        consensus[
            "agreement"
        ]
        is False
    ):
        warnings.append(
            (
                "Credible remaining-capacity estimates "
                "disagree beyond policy tolerance. "
                "The smallest credible estimate was used."
            )
        )

    if bound_disagreement:
        warnings.append(
            (
                "Programmatic and empirical storage evidence "
                "disagree beyond configured tolerance. "
                "The most conservative verified-safe value "
                "was selected."
            )
        )

    if sonar_needed:
        warnings.append(
            (
                "Programmatic/local evidence did not "
                "resolve remaining capacity. "
                "Empirical Capacity Sonar is required."
            )
        )

    if (
        resolved_remaining is not None
        and effective_total
        and effective_total > 0
    ):
        remaining_fraction = (
            resolved_remaining
            / effective_total
        )

        if (
            remaining_fraction
            < warning_fraction
        ):
            warnings.append(
                (
                    "Storage is below the configured "
                    "free-space warning threshold."
                )
            )

    return {
        "schema_version": (
            STORAGE_CAPACITY_RESOLUTION_SCHEMA_VERSION
        ),

        "provider": (
            capacity.get(
                "provider"
            )
        ),

        "provider_detection": (
            capacity.get(
                "detection"
            )
        ),

        "evidence": evidence,

        "consensus": {
            **consensus,

            "relative_tolerance": (
                relative_tolerance
            ),

            "absolute_tolerance_bytes": (
                absolute_tolerance
            ),

            "strongest_verified_lower_bound_bytes": (
                strongest_lower_bound
            ),

            "smallest_observed_upper_failure_bytes": (
                smallest_upper_failure
            ),

            "bound_disagreement": (
                bound_disagreement
            ),
        },

        "resolved": {
            "remaining_bytes": (
                resolved_remaining
            ),

            "effective_total_bytes": (
                effective_total
            ),

            "basis": (
                resolution_basis
            ),

            "confidence": (
                confidence
            ),
        },

        "allocation_policy": {
            "warning_free_fraction": (
                warning_fraction
            ),

            "protected_free_fraction": (
                protected_fraction
            ),

            "minimum_reserve_bytes": (
                minimum_reserve
            ),

            "reserve_bytes": (
                reserve_bytes
            ),

            "safe_allocatable_bytes": (
                safe_allocatable
            ),
        },

        "fallback": {
            "sonar_required": (
                sonar_needed
            ),

            "maintenance_sonar_enabled": (
                bool(
                    settings.get(
                        "maintenance_sonar_enabled",
                        False,
                    )
                )
            ),
        },

        "warnings": warnings,
    }
