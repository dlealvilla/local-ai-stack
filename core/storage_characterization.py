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
model catalogue, model requirements, feasibility or any selector.
Initial host characterization takes no input at all beyond policy,
because capacity must describe the server before any catalogue is
consulted. Which model wins is not a storage question.

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
#   HOST         describe the SERVER, before any catalogue exists.
#   TRANSACTION  answer one specific mutation at commit time.
#   DEEP         optional broader characterization, never required.
#
MODE_HOST = "host"
MODE_TRANSACTION = "transaction"
MODE_DEEP = "deep"

CHARACTERIZATION_MODES = frozenset({
    MODE_HOST,
    MODE_TRANSACTION,
    MODE_DEEP,
})


#
# Stop reasons, in priority order of the stopping hierarchy.
#
STOP_TRANSACTION_PROVEN_FEASIBLE = (
    "transaction_proven_feasible"
)
STOP_TRANSACTION_PROVEN_INFEASIBLE = (
    "transaction_proven_infeasible"
)
STOP_NUMERICAL_TOLERANCE_REACHED = (
    "numerical_tolerance_reached"
)

#
# HOST budgets are reported separately: knowing WHICH budget ended a
# search is what tells an operator whether to raise the climb, the
# backoff or the refinement allowance.
#
STOP_UPWARD_BUDGET_REACHED = (
    "upward_iteration_budget_reached"
)
STOP_DOWNWARD_BUDGET_REACHED = (
    "downward_iteration_budget_reached"
)
STOP_REFINEMENT_BUDGET_REACHED = (
    "refinement_iteration_budget_reached"
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
# answered the transaction is not evidence that characterized the pool,
# and a search that ran out of iterations is bounded, not complete.
#
STATUS_COMPLETE_FOR_TRANSACTION = (
    "complete_for_transaction"
)
STATUS_COMPLETE_FOR_HOST = "complete_for_host"
STATUS_BOUNDED_INCOMPLETE = "bounded_incomplete"
STATUS_INCONCLUSIVE = "inconclusive"


#
# Probe phases. `initial` is transient: the first probe is relabelled
# by its own outcome, because the direction it establishes is the
# direction whose budget it consumes.
#
PHASE_INITIAL = "initial"
PHASE_UPWARD = "upward"
PHASE_DOWNWARD = "downward"
PHASE_REFINEMENT = "refinement"
PHASE_SANITY = "sanity"
PHASE_TARGET = "target"


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
    computes its ceiling, so there is no competing third number. It is
    also what keeps the search from ever reaching the probe
    implementation's own refusal, which would return
    `probe_limit_exceeded` and be classified inconclusive.

    HOST-mode fields:

    `initial_probe_bytes` is where a fresh host characterization
    starts. It is deliberately a fixed server-scale figure rather than
    anything derived from a model, because storage characterization
    must describe the machine before a catalogue is consulted.

    HOST is bounded by three separate iteration budgets rather than by
    time or probe size:

        max_upward_iterations       climbing, before a bracket exists
        max_downward_iterations     backing off, before a bracket exists
        max_refinement_iterations   midpoint probes, once bracketed

    The upward budget is deliberately small. Each doubling probe writes
    real bytes on backends like the reference network volume, so the
    cost of the climb grows with the same factor as the probe size: a
    generous allowance buys precision nobody asked for at a price
    measured in days.

    All three are provisional and intended to become
    administrator-facing settings: trading probe time for a tighter
    bound is exactly an operator's call. No UI exists yet.

    HOST deliberately ignores `max_foreground_duration_seconds` and
    `max_single_probe_bytes`; the iteration budgets are its only bound.
    TRANSACTION and DEEP keep both.

    `relative_tolerance` is the HOST convergence rule on its own, as a
    pure ratio. DEEP additionally honours
    `absolute_tolerance_bytes` as a floor, which matters on small
    pools where a percentage alone would chase bytes.
    """

    schema_version: int
    relative_tolerance: float
    absolute_tolerance_bytes: int
    max_foreground_duration_seconds: float
    attempt_budget: int
    max_single_probe_bytes: int
    sanity_probe_bytes: int
    growth_factor: float
    initial_probe_bytes: int
    max_upward_iterations: int
    max_downward_iterations: int
    max_refinement_iterations: int

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
                0.15,
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

        initial_probe_bytes=int(
            float(
                settings.get(
                    "characterization_initial_probe_gb",
                    32.0,
                )
            )
            * GIB
        ),

        max_upward_iterations=int(
            settings.get(
                "characterization_max_upward_iterations",
                8,
            )
        ),

        max_downward_iterations=int(
            settings.get(
                "characterization_max_downward_iterations",
                8,
            )
        ),

        max_refinement_iterations=int(
            settings.get(
                "characterization_max_refinement_iterations",
                5,
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


def _relative_uncertainty_within(
    lower_bound: int | None,
    upper_bound: int | None,
    policy: StorageCharacterizationPolicy,
) -> bool:
    """The HOST convergence rule: a pure relative ratio.

    Deliberately without an absolute floor, so the stated policy is
    exactly what runs: stop once (U - L) / L is within
    `relative_tolerance`.
    """

    _, relative = _uncertainty(
        lower_bound,
        upper_bound,
    )

    if relative is None:
        return False

    return relative <= policy.relative_tolerance


def characterize_storage(
    *,
    mode,
    required_bytes=None,
    provider=None,
    config=None,
    policy=None,
    probe_implementation: Callable[..., Mapping[str, Any]] | None = None,
    monotonic=None,
):
    """Characterize storage only as far as the current decision needs.

    HOST describes the server itself, taking no input beyond policy.
    It starts at `initial_probe_bytes`, doubles on success and halves
    on a classified capacity failure until a success/failure bracket
    exists, then refines by midpoint until the relative uncertainty is
    within tolerance or the iteration cap is reached. Nothing about a
    model influences it, because capacity characterization precedes
    catalogue evaluation:

        host hardware
          -> safe CPU/RAM/accelerator characterization
            -> storage characterization
              -> CapacityEnvelope
                -> catalogue metadata
                  -> feasibility
                    -> model selection

    TRANSACTION answers "can this exact operation reserve
    `required_bytes`?". `required_bytes` is expected to be the safe
    requirement already produced by the storage-planning layer, so no
    further reserve is added here: doing so would double-account the
    headroom that layer already applied. It is for commit-time
    admission and must never drive initial host characterization.

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

    #
    # HOST has no probe-size ceiling: its bound is the iteration
    # budget. Every other mode keeps the configured safety limit,
    # which is also what the probe implementation would resolve on its
    # own.
    #
    probe_ceiling = (
        None
        if mode == MODE_HOST
        else policy.max_single_probe_bytes
    )

    def phase_count(phase):
        return len([
            entry
            for entry in probes
            if entry["phase"] == phase
        ])

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
            max_probe_bytes=probe_ceiling,
        )

        outcome, classification = (
            classify_probe_result(
                result
            )
        )

        #
        # The first probe belongs to whichever direction its own
        # outcome establishes, and counts as iteration 1 of that
        # direction.
        #
        if phase == PHASE_INITIAL:
            if outcome == PROBE_OUTCOME_SUCCESS:
                phase = PHASE_UPWARD

            elif outcome == (
                PROBE_OUTCOME_CAPACITY_FAILURE
            ):
                phase = PHASE_DOWNWARD

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

        if mode == MODE_HOST:
            #
            # Converged once the bracket is tight enough. The
            # iteration cap is enforced separately, in the loop,
            # because it is a hard stop BETWEEN probes rather than a
            # statement about the evidence.
            #
            if _relative_uncertainty_within(
                lower_bound,
                upper_bound,
                policy,
            ):
                return (
                    STOP_NUMERICAL_TOLERANCE_REACHED
                )

            return None

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
        """The next (size, phase) worth probing, or (None, None).

        The phase matters because HOST budgets are per-direction: a
        climb, a backoff and a midpoint refinement each have their own
        allowance.
        """

        if mode == MODE_TRANSACTION:
            return required_bytes, PHASE_TARGET

        if mode == MODE_HOST:
            #
            # No bracket yet and nothing known: start at the fixed
            # server-scale figure. This probe consumes iteration 1 of
            # whichever direction its outcome establishes.
            #
            if (
                lower_bound is None
                and upper_bound is None
            ):
                return (
                    policy.initial_probe_bytes,
                    PHASE_INITIAL,
                )

            #
            # Succeeding, with no ceiling found: double.
            #
            if upper_bound is None:
                candidate = int(
                    lower_bound
                    * policy.growth_factor
                )

                if candidate <= lower_bound:
                    return None, None

                return candidate, PHASE_UPWARD

            #
            # Failing, with no floor found: halve.
            #
            if lower_bound is None:
                candidate = upper_bound // 2

                if candidate <= 0:
                    return None, None

                return candidate, PHASE_DOWNWARD

            #
            # Bracketed: refine by midpoint.
            #
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
                return None, None

            return midpoint, PHASE_REFINEMENT

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
                return None, None

            return candidate, PHASE_TARGET

        #
        # DEEP with a real bracket: midpoint refinement.
        #
        if lower_bound is None:
            return None, None

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
            return None, None

        return midpoint, PHASE_TARGET

    #
    # 2. Sanity probe for a genuinely uncharacterized pool.
    #
    #    Purpose is to confirm the probe mechanism works and to
    #    establish a real lower bound before committing to a large
    #    target. An unsupported or erroring mechanism must be
    #    discovered cheaply, not at 64 GiB.
    #
    #    HOST mode skips it: its own first probe IS the fixed starting
    #    figure, and an inconclusive result there stops the search
    #    just as safely. Spending an iteration on a separate sanity
    #    probe would contradict the stated five-iteration budget.
    #
    stop_reason = decision_stop_reason()

    if (
        stop_reason is None
        and mode != MODE_HOST
        and lower_bound is None
    ):
        if (
            elapsed_seconds()
            >= policy.max_foreground_duration_seconds
        ):
            stop_reason = STOP_TIME_BUDGET_REACHED

        else:
            run_probe(
                policy.sanity_probe_bytes,
                PHASE_SANITY,
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
        target, phase = next_target()

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
        # HOST budgets are HARD stops between probes, per direction.
        # Once a budget is exhausted no further probe of that kind
        # starts, and the strongest conservative evidence collected so
        # far is returned.
        #
        if mode == MODE_HOST:
            budget_stop = None

            if phase in {
                PHASE_INITIAL,
                PHASE_UPWARD,
            }:
                if (
                    phase_count(PHASE_UPWARD)
                    >= policy.max_upward_iterations
                ):
                    budget_stop = (
                        STOP_UPWARD_BUDGET_REACHED
                    )

            elif phase == PHASE_DOWNWARD:
                if (
                    phase_count(PHASE_DOWNWARD)
                    >= policy.max_downward_iterations
                ):
                    budget_stop = (
                        STOP_DOWNWARD_BUDGET_REACHED
                    )

            elif phase == PHASE_REFINEMENT:
                if (
                    phase_count(PHASE_REFINEMENT)
                    >= policy.max_refinement_iterations
                ):
                    budget_stop = (
                        STOP_REFINEMENT_BUDGET_REACHED
                    )

            if budget_stop is not None:
                stop_reason = budget_stop
                break

        else:
            #
            # A target beyond the safety limit is NOT infeasible. It
            # is simply outside what policy currently permits us to
            # verify. This also keeps the search from reaching the
            # probe implementation's own refusal, which would come
            # back classified inconclusive.
            #
            if (
                target
                > policy.max_single_probe_bytes
            ):
                stop_reason = (
                    STOP_PROBE_LIMIT_REACHED
                )
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
            # after it completes. C3B cannot stop a probe that is
            # already running; see the module notes and C3C.
            #
            # HOST deliberately has no time limit: its bound is the
            # iteration budget above.
            #
            if (
                elapsed_seconds()
                >= policy.max_foreground_duration_seconds
            ):
                stop_reason = (
                    STOP_TIME_BUDGET_REACHED
                )
                break

        run_probe(
            target,
            phase,
        )

        if state["inconclusive"] is not None:
            stop_reason = (
                STOP_INCONCLUSIVE_PROBE_FAILURE
            )
            break

        stop_reason = decision_stop_reason()

        if (
            stop_reason is None
            and mode != MODE_HOST
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

    elif (
        mode == MODE_HOST
        and stop_reason
        == STOP_NUMERICAL_TOLERANCE_REACHED
    ):
        status = STATUS_COMPLETE_FOR_HOST

    else:
        status = STATUS_BOUNDED_INCOMPLETE

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

        #
        # One completed probe is one iteration, which is what the
        # iteration cap counts.
        #
        "probe_count_this_run": len(
            probes
        ),

        "iterations": len(probes),

        "upward_iterations": phase_count(
            PHASE_UPWARD
        ),

        "downward_iterations": phase_count(
            PHASE_DOWNWARD
        ),

        "refinement_iterations": phase_count(
            PHASE_REFINEMENT
        ),

        "iteration_budgets": (
            {
                "upward": (
                    policy.max_upward_iterations
                ),
                "downward": (
                    policy.max_downward_iterations
                ),
                "refinement": (
                    policy.max_refinement_iterations
                ),
            }
            if mode == MODE_HOST
            else None
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
    }
