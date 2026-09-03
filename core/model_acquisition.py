"""Select and then acquire or reuse one model for this host.

AI_DEPLOYMENT_MODEL_ACQUISITION

    capacity + candidates -> requirements -> feasibility -> selection
                          -> reuse or acquire -> inventory

This composes existing modules and owns no mechanism of its own. It
does not size storage, decide feasibility, rank candidates, admit a
mutation, stage bytes or write inventory; each of those already has an
owner, and reproducing any of them here would create a second version
of a rule that must not disagree with the first.

Two attempts at most. The chosen configuration is tried, and if it
fails in a way the acquisition seam can prove left nothing behind, the
one precomputed lower-resource alternative is tried. There is no retry
loop and no third attempt: repeatedly trying models on a host that
just refused one is how a bootstrap turns into an outage.

Source-neutral by construction. The provider for an acquisition comes
from the candidate's own metadata and is passed through to the existing
acquisition seam, so a private registry or an offline directory needs a
transfer adapter rather than a change here. Nothing in this module
names a model source, an accelerator vendor or an inference runtime.

Stops at an installed, inventory-visible artifact. Starting a runtime
is a separate concern with separate safety requirements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.capacity_contracts import (
    build_capacity_envelope,
)
from core.capacity_feasibility import (
    evaluate_capacity_feasibility,
)
from core.capacity_snapshot import (
    build_capacity_snapshot,
)
from core.config import load_config
from core.model_candidates import (
    load_curated_candidates,
)
from core.model_requirement import (
    build_model_requirement,
)
from core.model_selection import (
    STATUS_NO_SELECTION,
    SelectionCandidate,
    select_model,
)
from core.model_storage_requirements import (
    estimate_model_install_storage,
)
from core.resource_capacity import (
    build_resource_capacity,
)
from core.resource_reservation_bridge import (
    reservation_capacities_from_resource_safety,
)
from core.resource_reservations import (
    ResourceReservationLedger,
)
from core.resource_safety import (
    build_resource_safety,
)


MODEL_ACQUISITION_SCHEMA_VERSION = 1


STATUS_ACQUIRED = "acquired"
STATUS_REUSED = "reused"
STATUS_FALLBACK_ACQUIRED = "fallback_acquired"
STATUS_FALLBACK_REUSED = "fallback_reused"
STATUS_FAILED = "failed"
STATUS_NO_SELECTION_RESULT = STATUS_NO_SELECTION


ATTEMPT_REUSED = "reused"
ATTEMPT_ACQUIRED = "acquired"
ATTEMPT_FAILED = "failed"


#
# Failures after which the one alternative may be tried. Each is either
# decided before any mutation begins, or raised by a transfer that
# stages outside model storage and removes that staging on failure, so
# the platform is known to be in the state it started in.
#
# Everything else — a concurrent operation holding the storage lock, an
# unrecognized code, an escaping exception — leaves state this module
# cannot prove clean, and fails closed instead.
#
RECOVERABLE_ERROR_CODES = frozenset(
    {
        "storage_admission_denied",
        "storage_preflight_failed",
        "transfer_failed",
        "provider_not_enabled",
        "storage_safety_not_implemented",
    }
)


#
# The destination already holding this artifact is reuse, not failure.
#
ALREADY_INSTALLED_ERROR_CODE = "already_exists"


@dataclass(frozen=True)
class AcquisitionAttempt:
    """What happened for one candidate. Concise by intent."""

    candidate_id: str
    outcome: str
    provider: str | None = None
    error_code: str | None = None
    reason: str | None = None
    inventory_id: str | None = None
    path: str | None = None
    revision: str | None = None
    admission_reason: str | None = None
    recoverable: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "outcome": self.outcome,
            "provider": self.provider,
            "error_code": self.error_code,
            "reason": self.reason,
            "inventory_id": self.inventory_id,
            "path": self.path,
            "revision": self.revision,
            "admission_reason": (
                self.admission_reason
            ),
            "recoverable": self.recoverable,
        }


@dataclass(frozen=True)
class ModelAcquisitionSelectionResult:
    schema_version: int
    status: str
    selected_candidate_id: str | None
    acquired_candidate_id: str | None
    fallback_candidate_id: str | None
    selection_provider: str | None
    eligibility_tier: str | None
    acquisition_provider: str | None
    inventory_id: str | None
    artifact_path: str | None
    primary_attempt: AcquisitionAttempt | None
    fallback_attempt: AcquisitionAttempt | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "selected_candidate_id": (
                self.selected_candidate_id
            ),
            "acquired_candidate_id": (
                self.acquired_candidate_id
            ),
            "fallback_candidate_id": (
                self.fallback_candidate_id
            ),
            "selection_provider": (
                self.selection_provider
            ),
            "eligibility_tier": (
                self.eligibility_tier
            ),
            "acquisition_provider": (
                self.acquisition_provider
            ),
            "inventory_id": self.inventory_id,
            "artifact_path": self.artifact_path,
            "primary_attempt": (
                self.primary_attempt.to_dict()
                if self.primary_attempt
                else None
            ),
            "fallback_attempt": (
                self.fallback_attempt.to_dict()
                if self.fallback_attempt
                else None
            ),
            "reason": self.reason,
        }


def build_host_capacity_envelope(config=None):
    """The platform's current safe capacity, from one observation.

    Reading the host more than once would let separate figures drift
    apart and be compared against each other.
    """

    snapshot = build_capacity_snapshot()

    safety = build_resource_safety(
        build_resource_capacity(snapshot)
    )

    ledger = ResourceReservationLedger(
        reservation_capacities_from_resource_safety(
            safety
        )
    )

    return build_capacity_envelope(
        capacity_snapshot=snapshot,
        resource_safety=safety,
        reservation_snapshot=(
            ledger.snapshot().to_dict()
        ),
    )


def _overheads(config):
    settings = config.get(
        "storage_capacity",
        {},
    )

    return (
        settings.get(
            "model_operation_overhead_fraction",
            0.10,
        ),
        int(
            settings.get(
                "model_operation_overhead_min_bytes",
                1024 ** 3,
            )
        ),
    )


def build_selection_candidates(
    *,
    candidates,
    envelope,
    storage_characterization,
    config,
):
    """Size, normalize and gate each candidate using the existing owners."""

    overhead_fraction, overhead_min = _overheads(
        config
    )

    built = []

    for record in candidates:
        install_storage = (
            estimate_model_install_storage(
                record,
                overhead_fraction=overhead_fraction,
                overhead_min_bytes=overhead_min,
            )
        )

        requirement = build_model_requirement(
            model=record,
            install_storage=install_storage,
            compatibility=record,
        )

        feasibility = (
            evaluate_capacity_feasibility(
                requirement=requirement,
                envelope=envelope,
                storage_characterization=(
                    storage_characterization
                ),
            )
        )

        built.append(
            (
                record,
                SelectionCandidate(
                    candidate_id=record[
                        "candidate_id"
                    ],
                    requirement=requirement,
                    feasibility=feasibility,
                    evaluation_id=record.get(
                        "evaluation_id"
                    ),
                ),
            )
        )

    return built


def _required_primary_memory(candidate):
    return (
        candidate.requirement.primary_inference_memory.required_bytes
    )


def _lower_resource_alternatives(
    *,
    candidates,
    primary,
):
    """Candidates needing strictly less primary inference memory.

    Inference-resource intensity is the memory the model needs to
    serve, not its parameter count or its download size: a heavily
    quantized large model can be cheaper to run than a small
    unquantized one, and falling back to something that costs more
    memory would defeat the purpose.
    """

    threshold = _required_primary_memory(primary)

    if threshold is None:
        return []

    alternatives = []

    for candidate in candidates:
        if (
            candidate.candidate_id
            == primary.candidate_id
        ):
            continue

        required = _required_primary_memory(
            candidate
        )

        if required is None:
            continue

        if required < threshold:
            alternatives.append(candidate)

    return alternatives


def _installed_record(
    *,
    inventory,
    record,
):
    """An installed artifact for this candidate, or None.

    Matched on the source the candidate declares rather than on a local
    directory name, so an artifact is recognized as the same model
    however it came to be installed. A pinned revision must match; an
    unpinned candidate accepts whatever revision is installed, since
    there is nothing to compare against.
    """

    source = record.get("source") or {}

    provider = source.get("provider")
    source_model_id = source.get(
        "source_model_id"
    )
    wanted_revision = source.get("revision")

    unpinned = wanted_revision in (
        None,
        "",
        "main",
    )

    for entry in inventory.get("models") or []:
        entry_source = entry.get("source") or {}

        if (
            entry_source.get("provider")
            != provider
        ):
            continue

        if (
            entry_source.get("source_model_id")
            != source_model_id
        ):
            continue

        if not unpinned:
            if (
                entry_source.get("revision")
                != wanted_revision
            ):
                continue

        artifact = entry.get("artifact") or {}

        if artifact.get("state") != "stored":
            continue

        management = entry.get("management") or {}

        download_state = management.get(
            "download_state"
        )

        #
        # An interrupted or failed transfer is not a reusable
        # artifact. A record with no management block is a model
        # discovered on disk, which is stored and usable.
        #
        if download_state not in (
            None,
            "completed",
        ):
            continue

        return entry

    return None


def _attempt(
    *,
    record,
    candidate,
    acquire,
    inventory_of,
):
    """Reuse the artifact if it is already installed, otherwise acquire it."""

    source = record.get("source") or {}
    provider = source.get("provider")

    existing = _installed_record(
        inventory=inventory_of(),
        record=record,
    )

    if existing is not None:
        return AcquisitionAttempt(
            candidate_id=candidate.candidate_id,
            outcome=ATTEMPT_REUSED,
            provider=provider,
            inventory_id=existing.get(
                "inventory_id"
            ),
            path=existing.get("path"),
            revision=(
                existing.get("source") or {}
            ).get("revision"),
            reason=(
                "artifact already installed and "
                "usable"
            ),
        )

    #
    # The acquisition seam owns the storage lock, the sized admission
    # decision, staging and inventory. Its provider comes from the
    # candidate, which is what keeps this orchestration free of any
    # one model source.
    #
    outcome = acquire(
        provider=provider,
        source_model_id=source.get(
            "source_model_id"
        ),
        revision=source.get("revision")
        or "main",
        target_name=record.get("target_name"),
    )

    if not isinstance(outcome, dict):
        return AcquisitionAttempt(
            candidate_id=candidate.candidate_id,
            outcome=ATTEMPT_FAILED,
            provider=provider,
            error_code="unexpected_result",
            reason=(
                "acquisition returned "
                + type(outcome).__name__
            ),
            recoverable=False,
        )

    admission = (
        outcome.get("storage_admission") or {}
    )

    admission_reason = admission.get("reason")

    if outcome.get("ok"):
        result = outcome.get("result") or {}

        return AcquisitionAttempt(
            candidate_id=candidate.candidate_id,
            outcome=ATTEMPT_ACQUIRED,
            provider=provider,
            inventory_id=result.get(
                "inventory_id"
            ),
            path=result.get("path"),
            revision=(
                result.get("source") or {}
            ).get("resolved_revision"),
            admission_reason=admission_reason,
            reason="acquired through the platform "
            "acquisition seam",
        )

    error = outcome.get("error") or {}
    code = error.get("code")

    if code == ALREADY_INSTALLED_ERROR_CODE:
        #
        # The destination is occupied, so the artifact exists even
        # though inventory did not associate it with this candidate.
        #
        return AcquisitionAttempt(
            candidate_id=candidate.candidate_id,
            outcome=ATTEMPT_REUSED,
            provider=provider,
            error_code=code,
            admission_reason=admission_reason,
            reason=(
                "artifact already present at the "
                "destination"
            ),
        )

    return AcquisitionAttempt(
        candidate_id=candidate.candidate_id,
        outcome=ATTEMPT_FAILED,
        provider=provider,
        error_code=code,
        reason=error.get("detail")
        or error.get("reason"),
        admission_reason=admission_reason,
        recoverable=code
        in RECOVERABLE_ERROR_CODES,
    )


def _result(
    *,
    status,
    selection,
    primary_id,
    fallback_id,
    primary,
    fallback,
    reason,
):
    succeeded = None

    for attempt in (fallback, primary):
        if (
            attempt is not None
            and attempt.outcome
            != ATTEMPT_FAILED
        ):
            succeeded = attempt
            break

    return ModelAcquisitionSelectionResult(
        schema_version=(
            MODEL_ACQUISITION_SCHEMA_VERSION
        ),
        status=status,
        selected_candidate_id=primary_id,
        acquired_candidate_id=(
            succeeded.candidate_id
            if succeeded
            else None
        ),
        fallback_candidate_id=fallback_id,
        selection_provider=(
            selection.selection_provider
            if selection
            else None
        ),
        eligibility_tier=(
            selection.eligibility_tier
            if selection
            else None
        ),
        acquisition_provider=(
            succeeded.provider
            if succeeded
            else None
        ),
        inventory_id=(
            succeeded.inventory_id
            if succeeded
            else None
        ),
        artifact_path=(
            succeeded.path if succeeded else None
        ),
        primary_attempt=primary,
        fallback_attempt=fallback,
        reason=reason,
    )


def select_and_acquire_model(
    *,
    candidates=None,
    envelope=None,
    storage_characterization=None,
    config=None,
    evaluation_provider=None,
    acquire=None,
    list_inventory=None,
):
    """Choose one model for this host and make it locally available.

    `acquire` and `list_inventory` default to the platform's existing
    acquisition and inventory seams and exist as parameters so the
    orchestration can be exercised without moving real bytes.
    """

    if config is None:
        config = load_config()

    if candidates is None:
        candidates = load_curated_candidates(
            config
        )

    candidates = list(candidates)

    if acquire is None:
        from core.control import (
            download_inventory_model,
        )

        acquire = download_inventory_model

    if list_inventory is None:
        from core.model_inventory import (
            list_model_inventory,
        )

        list_inventory = list_model_inventory

    if envelope is None:
        envelope = build_host_capacity_envelope(
            config
        )

    if not candidates:
        return _result(
            status=STATUS_NO_SELECTION_RESULT,
            selection=None,
            primary_id=None,
            fallback_id=None,
            primary=None,
            fallback=None,
            reason="no candidate configurations "
            "are declared",
        )

    built = build_selection_candidates(
        candidates=candidates,
        envelope=envelope,
        storage_characterization=(
            storage_characterization
        ),
        config=config,
    )

    record_of = {
        candidate.candidate_id: record
        for record, candidate in built
    }

    selection_candidates = [
        candidate for _record, candidate in built
    ]

    selection = select_model(
        candidates=selection_candidates,
        envelope=envelope,
        evaluation_provider=evaluation_provider,
        config=config,
    )

    if selection.status == STATUS_NO_SELECTION:
        return _result(
            status=STATUS_NO_SELECTION_RESULT,
            selection=selection,
            primary_id=None,
            fallback_id=None,
            primary=None,
            fallback=None,
            reason=selection.reason,
        )

    primary = next(
        candidate
        for candidate in selection_candidates
        if candidate.candidate_id
        == selection.selected_candidate_id
    )

    #
    # The one alternative is decided before anything is attempted, and
    # by the same selector over the lower-resource subset. Re-selecting
    # after a failure, or applying a different rule to the fallback,
    # would mean two ranking policies that can disagree.
    #
    alternatives = _lower_resource_alternatives(
        candidates=selection_candidates,
        primary=primary,
    )

    fallback = None

    if alternatives:
        fallback_selection = select_model(
            candidates=alternatives,
            envelope=envelope,
            evaluation=selection.evaluation,
            config=config,
        )

        if (
            fallback_selection.status
            != STATUS_NO_SELECTION
        ):
            fallback = next(
                candidate
                for candidate in alternatives
                if candidate.candidate_id
                == fallback_selection.selected_candidate_id
            )

    fallback_id = (
        fallback.candidate_id
        if fallback
        else None
    )

    primary_attempt = _attempt(
        record=record_of[primary.candidate_id],
        candidate=primary,
        acquire=acquire,
        inventory_of=list_inventory,
    )

    if primary_attempt.outcome == ATTEMPT_REUSED:
        return _result(
            status=STATUS_REUSED,
            selection=selection,
            primary_id=primary.candidate_id,
            fallback_id=fallback_id,
            primary=primary_attempt,
            fallback=None,
            reason=(
                "selected model was already "
                "installed and was reused"
            ),
        )

    if (
        primary_attempt.outcome
        == ATTEMPT_ACQUIRED
    ):
        return _result(
            status=STATUS_ACQUIRED,
            selection=selection,
            primary_id=primary.candidate_id,
            fallback_id=fallback_id,
            primary=primary_attempt,
            fallback=None,
            reason=(
                "selected model was acquired"
            ),
        )

    if not primary_attempt.recoverable:
        return _result(
            status=STATUS_FAILED,
            selection=selection,
            primary_id=primary.candidate_id,
            fallback_id=fallback_id,
            primary=primary_attempt,
            fallback=None,
            reason=(
                "primary acquisition failed in a "
                "state the platform cannot prove "
                "safe, so no alternative was "
                "attempted: "
                + str(primary_attempt.error_code)
            ),
        )

    if fallback is None:
        return _result(
            status=STATUS_FAILED,
            selection=selection,
            primary_id=primary.candidate_id,
            fallback_id=None,
            primary=primary_attempt,
            fallback=None,
            reason=(
                "primary acquisition failed and no "
                "lower-resource alternative is "
                "available"
            ),
        )

    fallback_attempt = _attempt(
        record=record_of[fallback.candidate_id],
        candidate=fallback,
        acquire=acquire,
        inventory_of=list_inventory,
    )

    if fallback_attempt.outcome == ATTEMPT_REUSED:
        return _result(
            status=STATUS_FALLBACK_REUSED,
            selection=selection,
            primary_id=primary.candidate_id,
            fallback_id=fallback_id,
            primary=primary_attempt,
            fallback=fallback_attempt,
            reason=(
                "lower-resource alternative was "
                "already installed and was reused"
            ),
        )

    if (
        fallback_attempt.outcome
        == ATTEMPT_ACQUIRED
    ):
        return _result(
            status=STATUS_FALLBACK_ACQUIRED,
            selection=selection,
            primary_id=primary.candidate_id,
            fallback_id=fallback_id,
            primary=primary_attempt,
            fallback=fallback_attempt,
            reason=(
                "lower-resource alternative was "
                "acquired after the selected model "
                "failed"
            ),
        )

    #
    # Both attempts are spent. There is no third.
    #
    return _result(
        status=STATUS_FAILED,
        selection=selection,
        primary_id=primary.candidate_id,
        fallback_id=fallback_id,
        primary=primary_attempt,
        fallback=fallback_attempt,
        reason=(
            "selected model and its lower-resource "
            "alternative both failed to be acquired"
        ),
    )
