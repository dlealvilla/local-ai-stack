from core.storage_capacity_evidence import (
    build_storage_evidence,
)


STORAGE_SONAR_SCHEMA_VERSION = 1


def adaptive_capacity_search(
    *,
    probe,
    start_bytes,
    resolution_bytes,
    growth_factor=2.0,
    backoff_factor=0.5,
    max_attempts=32,
    initial_estimate_bytes=None,
    maximum_probe_bytes=None,
):
    """
    Find a conservative empirical capacity bracket.

    probe(size_bytes) must return True when that reservation size
    succeeds and False when it fails.

    Search strategy:

    A. Credible external estimate exists
       ---------------------------------
       Probe that estimate first.

       If it fails:
           geometrically back off until success.

       If it succeeds:
           expand upward until failure or policy ceiling.

    B. No external estimate
       --------------------
       Start small and expand geometrically.

    C. Success and failure bounds both exist
       -------------------------------------
       Binary-refine until the bracket is within resolution.

    IMPORTANT:
    The conservative result is always the largest CONFIRMED
    successful reservation.

    The midpoint is never treated as safe merely because it lies
    inside a bracket.
    """

    start_bytes = int(start_bytes)
    resolution_bytes = int(resolution_bytes)
    max_attempts = int(max_attempts)

    growth_factor = float(growth_factor)
    backoff_factor = float(backoff_factor)

    if start_bytes <= 0:
        raise ValueError(
            "start_bytes must be positive"
        )

    if resolution_bytes <= 0:
        raise ValueError(
            "resolution_bytes must be positive"
        )

    if growth_factor <= 1.0:
        raise ValueError(
            "growth_factor must be greater than 1"
        )

    if not (
        0.0
        < backoff_factor
        < 1.0
    ):
        raise ValueError(
            "backoff_factor must be between 0 and 1"
        )

    if max_attempts <= 0:
        raise ValueError(
            "max_attempts must be positive"
        )

    if maximum_probe_bytes is not None:
        maximum_probe_bytes = int(
            maximum_probe_bytes
        )

        if maximum_probe_bytes <= 0:
            raise ValueError(
                "maximum_probe_bytes must be positive"
            )

    attempts = []

    lower_success = None
    upper_failure = None

    def execute(
        requested_bytes,
        phase,
    ):
        nonlocal lower_success
        nonlocal upper_failure

        size = max(
            1,
            int(requested_bytes),
        )

        if maximum_probe_bytes is not None:
            size = min(
                size,
                maximum_probe_bytes,
            )

        success = bool(
            probe(size)
        )

        attempts.append({
            "attempt": len(attempts) + 1,
            "phase": phase,
            "requested_bytes": size,
            "success": success,
        })

        if success:
            if (
                lower_success is None
                or size > lower_success
            ):
                lower_success = size

        else:
            if (
                upper_failure is None
                or size < upper_failure
            ):
                upper_failure = size

        return success, size

    #
    # 1. Intelligent initial probe.
    #

    if (
        initial_estimate_bytes is not None
        and int(initial_estimate_bytes) > 0
    ):
        candidate = int(
            initial_estimate_bytes
        )

        initial_source = (
            "programmatic_estimate"
        )

    else:
        candidate = start_bytes
        initial_source = "default_start"

    if maximum_probe_bytes is not None:
        candidate = min(
            candidate,
            maximum_probe_bytes,
        )

    initial_success, candidate = execute(
        candidate,
        "initial",
    )

    #
    # 2. Programmatic estimate was too large:
    #    geometrically back off until success.
    #

    if not initial_success:
        failing = candidate

        while (
            lower_success is None
            and len(attempts) < max_attempts
        ):
            next_candidate = int(
                failing
                * backoff_factor
            )

            if next_candidate < start_bytes:
                next_candidate = start_bytes

            if next_candidate >= failing:
                break

            success, tested = execute(
                next_candidate,
                "backoff",
            )

            if success:
                break

            failing = tested

            if tested <= start_bytes:
                break

    #
    # 3. We have a lower bound but no upper failure:
    #    geometrically expand.
    #

    if (
        lower_success is not None
        and upper_failure is None
    ):
        candidate = lower_success

        while len(attempts) < max_attempts:
            next_candidate = int(
                candidate
                * growth_factor
            )

            if maximum_probe_bytes is not None:
                next_candidate = min(
                    next_candidate,
                    maximum_probe_bytes,
                )

            if next_candidate <= candidate:
                break

            success, tested = execute(
                next_candidate,
                "expand",
            )

            candidate = tested

            if not success:
                break

            if (
                maximum_probe_bytes is not None
                and tested >= maximum_probe_bytes
            ):
                break

    #
    # 4. Refine known success/failure bracket.
    #

    while (
        lower_success is not None
        and upper_failure is not None
        and (
            upper_failure
            - lower_success
        ) > resolution_bytes
        and len(attempts) < max_attempts
    ):
        midpoint = (
            lower_success
            + (
                upper_failure
                - lower_success
            )
            // 2
        )

        if (
            midpoint <= lower_success
            or midpoint >= upper_failure
        ):
            break

        execute(
            midpoint,
            "binary_refine",
        )

    #
    # 5. Determine why the algorithm stopped.
    #

    if lower_success is None:
        stopping_reason = (
            "no_successful_reservation"
        )

    elif upper_failure is None:
        if (
            maximum_probe_bytes is not None
            and lower_success
            >= maximum_probe_bytes
        ):
            stopping_reason = (
                "policy_ceiling_reached"
            )

        else:
            stopping_reason = (
                "no_upper_failure_observed"
            )

    elif (
        upper_failure
        - lower_success
    ) <= resolution_bytes:
        stopping_reason = (
            "resolution_reached"
        )

    elif len(attempts) >= max_attempts:
        stopping_reason = (
            "max_attempts_reached"
        )

    else:
        stopping_reason = (
            "search_stopped"
        )

    bracket_width = None

    if (
        lower_success is not None
        and upper_failure is not None
    ):
        bracket_width = (
            upper_failure
            - lower_success
        )

    return {
        "schema_version": (
            STORAGE_SONAR_SCHEMA_VERSION
        ),

        "algorithm": (
            "seeded_exponential_backoff_binary"
        ),

        "initial_source": (
            initial_source
        ),

        "verified_lower_bound_bytes": (
            lower_success
        ),

        "observed_upper_failure_bytes": (
            upper_failure
        ),

        "conservative_estimate_bytes": (
            lower_success
        ),

        "bracket_width_bytes": (
            bracket_width
        ),

        "resolution_bytes": (
            resolution_bytes
        ),

        "boundary_bracketed": (
            lower_success is not None
            and upper_failure is not None
        ),

        "attempt_count": len(
            attempts
        ),

        "stopping_reason": (
            stopping_reason
        ),

        "attempts": attempts,
    }


def sonar_result_to_evidence(
    result,
    *,
    source="capacity_sonar",
    scope="storage_allocation",
    confidence="medium",
):
    """
    Convert sonar semantics into evidence the consensus resolver
    can understand correctly.

    Success establishes a LOWER bound.
    Failure establishes an UPPER bound.

    They are deliberately NOT converted into point estimates.
    """

    evidence = []

    lower = result.get(
        "verified_lower_bound_bytes"
    )

    upper = result.get(
        "observed_upper_failure_bytes"
    )

    if lower is not None:
        evidence.append(
            build_storage_evidence(
                evidence_id=(
                    "sonar_lower_bound"
                ),
                source=source,
                scope=scope,
                evidence_type=(
                    "remaining_lower_bound"
                ),
                value_bytes=lower,
                confidence=confidence,
                detail=(
                    "Empirically verified successful "
                    "storage reservation."
                ),
            )
        )

    if upper is not None:
        evidence.append(
            build_storage_evidence(
                evidence_id=(
                    "sonar_upper_bound"
                ),
                source=source,
                scope=scope,
                evidence_type=(
                    "remaining_upper_bound"
                ),
                value_bytes=upper,
                confidence=confidence,
                detail=(
                    "Empirical reservation failed at "
                    "this requested size."
                ),
            )
        )

    return evidence
