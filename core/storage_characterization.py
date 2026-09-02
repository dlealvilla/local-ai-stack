"""Decision-bounded storage characterization policy.

AI_DEPLOYMENT_STORAGE_CHARACTERIZATION_C3B

See docs/CAPACITY_ARCHITECTURE.md sections 13 to 22.

The defect this replaces: characterization used to search for the
storage pool's ceiling regardless of the question being asked. On the
real host a 6.70 GiB transaction requirement was already answered by a
successful 32 GiB probe, yet the search kept climbing and spent roughly
48 minutes refining a boundary near 47 GiB. Precision has value only
while it can still change a decision.

Layering, deliberately not collapsed:

    core.storage_probe                  low-level probe mechanism
    core.storage_capacity_cache         durable EmpiricalProbeEvidence
    THIS MODULE                         policy + CharacterizationResult
    core.storage_commit_admission       admission, unchanged

This module is model-agnostic by construction. It never imports the
model catalogue, model requirements, feasibility or any selector: a
caller supplies generic byte thresholds, and this module reports only
which of those thresholds are proven feasible, proven infeasible or
unresolved. Which model wins is not a storage question.

Nothing here is wired into production capacity resolution or admission.
`resolve_storage_capacity()` and `calibrate_storage_capacity()` behave
exactly as they did at C3A; this is an additive entry point.

The conservative usable figure is always the largest verified
successful lower bound. Never a midpoint, an interpolation, an
estimated threshold, raw filesystem capacity or an unverified upper
bound.
"""

from __future__ import annotations

import time

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from core.config import load_config

from core.storage_capacity_cache import (
    PROBE_OUTCOME_CAPACITY_FAILURE,
    PROBE_OUTCOME_SUCCESS,
    classify_probe_result,
    eligible_empirical_probe_evidence,
    inspect_storage_identity,
    read_storage_generation,
    record_empirical_probe_evidence,
)

from core.storage_probe import (
    probe_required_capacity,
)


STORAGE_CHARACTERIZATION_SCHEMA_VERSION = 1


GIB = 1024 ** 3
MIB = 1024 ** 2


#
# Characterization modes. Each mode exists to answer a different
# question, and the question determines when to stop.
#
MODE_TRANSACTION = "transaction"
MODE_SELECTION = "selection"
MODE_DEEP = "deep"

CHARACTERIZATION_MODES = frozenset({
    MODE_TRANSACTION,
    MODE_SELECTION,
    MODE_DEEP,
})


#
# Threshold verdicts. Three values only: a threshold we could not
# resolve is unresolved, never infeasible.
#
THRESHOLD_PROVEN_FEASIBLE = "proven_feasible"
THRESHOLD_PROVEN_INFEASIBLE = "proven_infeasible"
THRESHOLD_UNRESOLVED = "unresolved"


#
# Stop reasons, in priority order of the stopping hierarchy.
#
STOP_TRANSACTION_PROVEN_FEASIBLE = (
    "transaction_proven_feasible"
)
STOP_TRANSACTION_PROVEN_INFEASIBLE = (
    "transaction_proven_infeasible"
)
STOP_SELECTION_THRESHOLDS_RESOLVED = (
    "selection_thresholds_resolved"
)
STOP_USEFUL_HORIZON_VERIFIED = (
    "useful_horizon_verified"
)
STOP_NUMERICAL_TOLERANCE_REACHED = (
    "numerical_tolerance_reached"
)
STOP_TIME_BUDGET_REACHED = "time_budget_reached"
STOP_ATTEMPT_BUDGET_REACHED = (
    "attempt_budget_reached"
)
STOP_PROBE_LIMIT_REACHED = "probe_limit_reached"
STOP_INCONCLUSIVE_PROBE_FAILURE = (
    "inconclusive_probe_failure"
)


#
# Completeness. Honesty matters more than a tidy label: evidence that
# answered the transaction is not evidence that characterized the pool.
#
STATUS_COMPLETE_FOR_TRANSACTION = (
    "complete_for_transaction"
)
STATUS_COMPLETE_FOR_SELECTION = (
    "complete_for_selection"
)
STATUS_BOUNDED_INCOMPLETE = "bounded_incomplete"
STATUS_INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class StorageCharacterizationPolicy:
    """Configurable limits and tolerances for characterization.

    `relative_tolerance` and `absolute_tolerance_bytes` govern how
    tightly a success/failure BRACKET must be narrowed before further
    refinement is pointless. They are deliberately NOT the existing
    `consensus_relative_tolerance` (0.10) and `consensus_absolute_gb`
    (2.0), which govern whether two independent capacity ESTIMATES
    agree closely enough to be believed. Conflating the two would let
    a change to evidence-agreement policy silently retune search
    termination.

    `max_single_probe_bytes` is a safety limit, not a capacity claim.
    It is seeded from the lower of the existing `sonar_max_automatic_gb`
    and `probe_max_gb`, exactly as the existing calibration coordinator
    computes its ceiling, so there is no competing third number.
    """

    schema_version: int
    relative_tolerance: float
    absolute_tolerance_bytes: int
    max_foreground_duration_seconds: float
    attempt_budget: int
    max_single_probe_bytes: int
    sanity_probe_bytes: int
    growth_factor: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_storage_characterization_policy(
    config: Mapping[str, Any] | None = None,
) -> StorageCharacterizationPolicy:
    """Seed policy from existing authoritative configuration.

    Existing keys are reused rather than duplicated:

        sonar_start_mb          -> sanity probe size
        sonar_max_attempts      -> attempt budget
        sonar_growth_factor     -> DEEP expansion factor
        sonar_max_automatic_gb  -> max single probe (lower of the two)
        probe_max_gb            -> max single probe (lower of the two)

    The three genuinely new values default in code and are honoured
    from configuration when present, so reverting this step cannot
    orphan configuration keys.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    ) or {}

    sonar_ceiling = float(
        settings.get(
            "sonar_max_automatic_gb",
            64.0,
        )
    )

    probe_ceiling = float(
        settings.get(
            "probe_max_gb",
            64.0,
        )
    )

    return StorageCharacterizationPolicy(
        schema_version=(
            STORAGE_CHARACTERIZATION_SCHEMA_VERSION
        ),

        relative_tolerance=float(
            settings.get(
                "characterization_relative_tolerance",
                0.05,
            )
        ),

        absolute_tolerance_bytes=int(
            float(
                settings.get(
                    "characterization_absolute_tolerance_gb",
                    1.0,
                )
            )
            * GIB
        ),

        max_foreground_duration_seconds=float(
            settings.get(
                "characterization_max_foreground_seconds",
                900.0,
            )
        ),

        attempt_budget=int(
            settings.get(
                "sonar_max_attempts",
                32,
            )
        ),

        max_single_probe_bytes=int(
            min(
                sonar_ceiling,
                probe_ceiling,
            )
            * GIB
        ),

        sanity_probe_bytes=int(
            float(
                settings.get(
                    "sonar_start_mb",
                    64,
                )
            )
            * MIB
        ),

        growth_factor=float(
            settings.get(
                "sonar_growth_factor",
                2.0,
            )
        ),
    )


def bounds_from_evidence(
    records: Sequence[Mapping[str, Any]],
) -> tuple[int | None, int | None, list[str]]:
    """Derive conservative bounds from durable empirical facts.

        L = largest successful requested_bytes
        U = smallest CLASSIFIED capacity-failure requested_bytes

    Inconclusive records are ignored entirely. An unsupported
    primitive, a permission error or our own policy ceiling says
    nothing about how much space exists, so none of them may bound
    anything.
    """

    lower = None
    upper = None
    used = []

    for record in records:
        requested = record.get(
            "requested_bytes"
        )

        if not isinstance(
            requested,
            int,
        ):
            continue

        outcome = record.get(
            "outcome"
        )

        if outcome == PROBE_OUTCOME_SUCCESS:
            if (
                lower is None
                or requested > lower
            ):
                lower = requested

            used.append(
                record.get(
                    "record_id"
                )
            )

        elif outcome == (
            PROBE_OUTCOME_CAPACITY_FAILURE
        ):
            if (
                upper is None
                or requested < upper
            ):
                upper = requested

            used.append(
                record.get(
                    "record_id"
                )
            )

    return lower, upper, used


def classify_threshold(
    threshold_bytes: int,
    *,
    lower_bound: int | None,
    upper_bound: int | None,
) -> str:
    if (
        lower_bound is not None
        and threshold_bytes <= lower_bound
    ):
        return THRESHOLD_PROVEN_FEASIBLE

    if (
        upper_bound is not None
        and threshold_bytes >= upper_bound
    ):
        return THRESHOLD_PROVEN_INFEASIBLE

    return THRESHOLD_UNRESOLVED


def _uncertainty(
    lower_bound: int | None,
    upper_bound: int | None,
) -> tuple[int | None, float | None]:
    if (
        lower_bound is None
        or upper_bound is None
    ):
        return None, None

    absolute = upper_bound - lower_bound

    relative = None

    if lower_bound > 0:
        relative = absolute / lower_bound

    return absolute, relative


def _within_tolerance(
    lower_bound: int | None,
    upper_bound: int | None,
    policy: StorageCharacterizationPolicy,
) -> bool:
    absolute, _ = _uncertainty(
        lower_bound,
        upper_bound,
    )

    if absolute is None:
        return False

    allowed = max(
        policy.absolute_tolerance_bytes,

        int(
            policy.relative_tolerance
            * lower_bound
        ),
    )

    return absolute <= allowed


def _normalized_thresholds(
    candidate_thresholds_bytes,
) -> list[int]:
    if not candidate_thresholds_bytes:
        return []

    thresholds = set()

    for value in candidate_thresholds_bytes:
        value = int(
            value
        )

        if value <= 0:
            raise ValueError(
                "candidate thresholds must be positive"
            )

        thresholds.add(
            value
        )

    return sorted(
        thresholds
    )


def characterize_storage(
    *,
    mode,
    required_bytes=None,
    candidate_thresholds_bytes=None,
    useful_horizon_bytes=None,
    provider=None,
    config=None,
    policy=None,
    probe_implementation: Callable[..., Mapping[str, Any]] | None = None,
    monotonic=None,
):
    """Characterize storage only as far as the current decision needs.

    TRANSACTION answers "can this exact operation reserve
    `required_bytes`?". `required_bytes` is expected to be the safe
    requirement already produced by the storage-planning layer, so no
    further reserve is added here: doing so would double-account the
    headroom that layer already applied.

    SELECTION classifies the caller's supplied
    `candidate_thresholds_bytes` and, optionally,
    `useful_horizon_bytes`. The caller decides which thresholds still
    matter; this function never learns what they represent.

    DEEP approximates a broader ceiling for reporting and planning. It
    is never required for bootstrap.

    Every completed probe is persisted through C3A before the next one
    starts, so an interruption keeps whatever was learned.
    """

    if mode not in CHARACTERIZATION_MODES:
        raise ValueError(
            "Unsupported characterization mode: "
            + str(mode)
        )

    if config is None:
        config = load_config()

    if policy is None:
        policy = (
            build_storage_characterization_policy(
                config
            )
        )

    if probe_implementation is None:
        probe_implementation = (
            probe_required_capacity
        )

    if monotonic is None:
        monotonic = time.monotonic

    if mode == MODE_TRANSACTION:
        if required_bytes is None:
            raise ValueError(
                "TRANSACTION characterization requires "
                "required_bytes"
            )

        required_bytes = int(
            required_bytes
        )

        if required_bytes <= 0:
            raise ValueError(
                "required_bytes must be positive"
            )

    thresholds = _normalized_thresholds(
        candidate_thresholds_bytes
    )

    if useful_horizon_bytes is not None:
        useful_horizon_bytes = int(
            useful_horizon_bytes
        )

        if useful_horizon_bytes <= 0:
            raise ValueError(
                "useful_horizon_bytes must be positive"
            )

    if mode == MODE_SELECTION and not (
        thresholds
        or useful_horizon_bytes
    ):
        raise ValueError(
            "SELECTION characterization requires "
            "candidate thresholds or a useful horizon"
        )

    started_at = datetime.now(
        timezone.utc
    )

    started_monotonic = monotonic()

    #
    # Established once. Neither can change underneath a single
    # characterization run, and re-statting the mount before every
    # probe would add cost without adding truth.
    #
    storage_identity = (
        inspect_storage_identity(
            config=config
        )
    )

    storage_generation = (
        read_storage_generation(
            config
        ).get(
            "generation"
        )
    )

    #
    # 1. Reuse durable evidence before considering any probe. A
    #    previous run's 32 GiB success can answer a 7 GiB question
    #    with no probing at all.
    #
    eligibility = (
        eligible_empirical_probe_evidence(
            config
        )
    )

    lower_bound, upper_bound, reused_ids = (
        bounds_from_evidence(
            eligibility[
                "eligible"
            ]
        )
    )

    probes = []
    created_ids = []

    state = {
        "stop_reason": None,
        "inconclusive": None,
    }

    def elapsed_seconds():
        return (
            monotonic()
            - started_monotonic
        )

    def run_probe(
        requested_bytes,
        phase,
    ):
        """Probe, persist, then update bounds. In that order."""

        nonlocal lower_bound
        nonlocal upper_bound

        result = probe_implementation(
            requested_bytes,
            config=config,
        )

        outcome, classification = (
            classify_probe_result(
                result
            )
        )

        #
        # Durability first: the fact must survive whatever happens to
        # the next probe or to this process.
        #
        record = (
            record_empirical_probe_evidence(
                result,

                requested_bytes=(
                    requested_bytes
                ),

                provider=provider,

                config=config,

                storage_identity=(
                    storage_identity
                ),

                storage_generation=(
                    storage_generation
                ),
            )
        )

        created_ids.append(
            record[
                "record_id"
            ]
        )

        probes.append({
            "phase": phase,

            "requested_bytes": int(
                requested_bytes
            ),

            "outcome": outcome,

            "failure_classification": (
                classification
            ),

            "duration_seconds": (
                result.get(
                    "duration_seconds"
                )
            ),

            "record_id": record[
                "record_id"
            ],
        })

        if outcome == PROBE_OUTCOME_SUCCESS:
            if (
                lower_bound is None
                or requested_bytes > lower_bound
            ):
                lower_bound = int(
                    requested_bytes
                )

        elif outcome == (
            PROBE_OUTCOME_CAPACITY_FAILURE
        ):
            if (
                upper_bound is None
                or requested_bytes < upper_bound
            ):
                upper_bound = int(
                    requested_bytes
                )

        else:
            #
            # The probe mechanism itself is unreliable here. Treating
            # this as "not enough space" would be a false capacity
            # conclusion, so characterization stops and says so.
            #
            state[
                "inconclusive"
            ] = classification

        return outcome

    def decision_stop_reason():
        """The decision-based stopping conditions, in priority order."""

        if mode == MODE_TRANSACTION:
            if (
                lower_bound is not None
                and lower_bound >= required_bytes
            ):
                return (
                    STOP_TRANSACTION_PROVEN_FEASIBLE
                )

            if (
                upper_bound is not None
                and upper_bound <= required_bytes
            ):
                return (
                    STOP_TRANSACTION_PROVEN_INFEASIBLE
                )

            return None

        if mode == MODE_SELECTION:
            unresolved = [
                threshold
                for threshold in thresholds

                if classify_threshold(
                    threshold,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
                == THRESHOLD_UNRESOLVED
            ]

            horizon_unresolved = (
                useful_horizon_bytes is not None
                and classify_threshold(
                    useful_horizon_bytes,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
                == THRESHOLD_UNRESOLVED
            )

            if unresolved or horizon_unresolved:
                return None

            if (
                not thresholds
                and useful_horizon_bytes is not None
            ):
                return (
                    STOP_USEFUL_HORIZON_VERIFIED
                )

            return (
                STOP_SELECTION_THRESHOLDS_RESOLVED
            )

        #
        # DEEP: refine only while the bracket is still loose.
        #
        if _within_tolerance(
            lower_bound,
            upper_bound,
            policy,
        ):
            return (
                STOP_NUMERICAL_TOLERANCE_REACHED
            )

        return None

    def next_target():
        """The next size worth probing, or None when nothing is."""

        if mode == MODE_TRANSACTION:
            return required_bytes

        if mode == MODE_SELECTION:
            #
            # A decision threshold outranks an arbitrary numeric
            # midpoint: probing 55 GiB resolves a candidate, whereas
            # bisecting toward the true boundary resolves nothing.
            #
            unresolved = [
                threshold
                for threshold in thresholds

                if classify_threshold(
                    threshold,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
                == THRESHOLD_UNRESOLVED
                and threshold
                <= policy.max_single_probe_bytes
            ]

            if unresolved:
                return max(
                    unresolved
                )

            if (
                useful_horizon_bytes is not None
                and useful_horizon_bytes
                <= policy.max_single_probe_bytes
                and classify_threshold(
                    useful_horizon_bytes,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
                == THRESHOLD_UNRESOLVED
            ):
                return useful_horizon_bytes

            #
            # Anything still unresolved lies beyond the safety limit.
            # It stays unresolved rather than being called infeasible.
            #
            return None

        #
        # DEEP with no failure bound yet: expand geometrically from
        # the strongest known success.
        #
        if upper_bound is None:
            base = (
                lower_bound
                or policy.sanity_probe_bytes
            )

            candidate = min(
                int(
                    base
                    * policy.growth_factor
                ),

                policy.max_single_probe_bytes,
            )

            #
            # Clamped to the safety limit rather than abandoned, so
            # DEEP can still verify the ceiling policy permits.
            #
            if candidate <= base:
                return None

            return candidate

        #
        # DEEP with a real bracket: midpoint refinement.
        #
        if lower_bound is None:
            return None

        midpoint = (
            lower_bound
            + (
                upper_bound
                - lower_bound
            )
            // 2
        )

        if (
            midpoint <= lower_bound
            or midpoint >= upper_bound
        ):
            return None

        return midpoint

    #
    # 2. Sanity probe for a genuinely uncharacterized pool.
    #
    #    Purpose is to confirm the probe mechanism works and to
    #    establish a real lower bound before committing to a large
    #    target. An unsupported or erroring mechanism must be
    #    discovered cheaply, not at 64 GiB.
    #
    stop_reason = decision_stop_reason()

    if stop_reason is None and lower_bound is None:
        if (
            elapsed_seconds()
            >= policy.max_foreground_duration_seconds
        ):
            stop_reason = STOP_TIME_BUDGET_REACHED

        else:
            run_probe(
                policy.sanity_probe_bytes,
                "sanity",
            )

            if state["inconclusive"] is not None:
                stop_reason = (
                    STOP_INCONCLUSIVE_PROBE_FAILURE
                )

            else:
                stop_reason = (
                    decision_stop_reason()
                )

    #
    # 3. Target-first loop.
    #
    #    No geometric climb from 64 MiB toward the pool ceiling: the
    #    decision names its own target, so probe that.
    #
    while stop_reason is None:
        target = next_target()

        if target is None:
            stop_reason = (
                STOP_NUMERICAL_TOLERANCE_REACHED
                if _within_tolerance(
                    lower_bound,
                    upper_bound,
                    policy,
                )
                else STOP_PROBE_LIMIT_REACHED
            )

            break

        target = int(
            target
        )

        #
        # A target beyond the safety limit is NOT infeasible. It is
        # simply outside what policy currently permits us to verify,
        # and a future approved limit can resolve it without touching
        # this algorithm.
        #
        if target > policy.max_single_probe_bytes:
            stop_reason = STOP_PROBE_LIMIT_REACHED
            break

        if (
            len(probes)
            >= policy.attempt_budget
        ):
            stop_reason = (
                STOP_ATTEMPT_BUDGET_REACHED
            )
            break

        #
        # The budget is checked before starting a probe and again
        # after it completes. C3B cannot stop a probe that is already
        # running; see the module notes and C3C.
        #
        if (
            elapsed_seconds()
            >= policy.max_foreground_duration_seconds
        ):
            stop_reason = STOP_TIME_BUDGET_REACHED
            break

        run_probe(
            target,
            "target",
        )

        if state["inconclusive"] is not None:
            stop_reason = (
                STOP_INCONCLUSIVE_PROBE_FAILURE
            )
            break

        stop_reason = decision_stop_reason()

        if (
            stop_reason is None
            and elapsed_seconds()
            >= policy.max_foreground_duration_seconds
        ):
            stop_reason = STOP_TIME_BUDGET_REACHED

    completed_at = datetime.now(
        timezone.utc
    )

    absolute_uncertainty, relative_uncertainty = (
        _uncertainty(
            lower_bound,
            upper_bound,
        )
    )

    if stop_reason == (
        STOP_INCONCLUSIVE_PROBE_FAILURE
    ):
        status = STATUS_INCONCLUSIVE

    elif stop_reason in {
        STOP_TRANSACTION_PROVEN_FEASIBLE,
        STOP_TRANSACTION_PROVEN_INFEASIBLE,
    }:
        status = (
            STATUS_COMPLETE_FOR_TRANSACTION
        )

    elif stop_reason in {
        STOP_SELECTION_THRESHOLDS_RESOLVED,
        STOP_USEFUL_HORIZON_VERIFIED,
    }:
        status = STATUS_COMPLETE_FOR_SELECTION

    else:
        status = STATUS_BOUNDED_INCOMPLETE

    threshold_classifications = [
        {
            "threshold_bytes": threshold,

            "classification": classify_threshold(
                threshold,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            ),
        }

        for threshold in thresholds
    ]

    total_duration = sum(
        entry["duration_seconds"] or 0.0
        for entry in probes
    )

    return {
        "schema_version": (
            STORAGE_CHARACTERIZATION_SCHEMA_VERSION
        ),

        "mode": mode,

        "policy": policy.to_dict(),

        "storage_identity": (
            storage_identity
        ),

        "storage_generation": (
            storage_generation
        ),

        "started_at": (
            started_at.isoformat()
        ),

        "completed_at": (
            completed_at.isoformat()
        ),

        "elapsed_seconds": round(
            elapsed_seconds(),
            6,
        ),

        "required_bytes": (
            required_bytes
            if mode == MODE_TRANSACTION
            else None
        ),

        "useful_horizon_bytes": (
            useful_horizon_bytes
        ),

        "verified_lower_bound_bytes": (
            lower_bound
        ),

        "capacity_failure_upper_bound_bytes": (
            upper_bound
        ),

        #
        # The only figure that may authorize anything.
        #
        "conservative_usable_bytes": (
            lower_bound
        ),

        "absolute_uncertainty_bytes": (
            absolute_uncertainty
        ),

        "relative_uncertainty": (
            relative_uncertainty
        ),

        "status": status,

        "stop_reason": stop_reason,

        "inconclusive_reason": (
            state["inconclusive"]
        ),

        "probe_count_this_run": len(
            probes
        ),

        "total_requested_probe_bytes_this_run": sum(
            entry["requested_bytes"]
            for entry in probes
        ),

        "total_probe_duration_seconds": round(
            total_duration,
            6,
        ),

        "probes": probes,

        "reused_evidence_record_ids": (
            reused_ids
        ),

        "created_evidence_record_ids": (
            created_ids
        ),

        "threshold_classifications": (
            threshold_classifications
        ),
    }
