"""A probe that allocates nothing, for fixture replay and for tests.

Fixture replay must never reserve real space. The captured mount advertises
hundreds of terabytes, and a development machine asked to verify a 64 GiB
policy bound against it would spend ten minutes and gigabytes learning
something about the *developer's laptop* rather than about the machine the
evidence came from.

So in fixture mode the reservation primitive is replaced while everything
above it — the ladder, the budgets, the stop reasons, the incremental
persistence, the interpretation in `capacity` — is the real implementation
running for real. That is the point: the controller is exercised, the
filesystem is not.

**Every surface labels this as replayed.** An operator must never mistake a
scripted outcome for physical verification, which is why the method name
says so rather than imitating the real one.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from kultrun.kernel.ids import Name
from kultrun.storage.contracts import ProbeOutcome
from kultrun.storage.ports import ReservationBudget, ReservationResult

METHOD: Final = Name("replayed-no-allocation")

#: The default script: verifies every rung, so replay demonstrates the
#: policy-cap-verified path. Other scenarios are supplied per instance.
_VERIFY_EVERYTHING: Final = ProbeOutcome.VERIFIED


class ReplayedProbe:
    """Returns scripted outcomes without touching a filesystem."""

    method = METHOD

    def __init__(
        self,
        outcomes: Mapping[int, ProbeOutcome] | None = None,
        *,
        default: ProbeOutcome = _VERIFY_EVERYTHING,
    ) -> None:
        self._outcomes = dict(outcomes or {})
        self._default = default
        self.attempted: list[int] = []

    def reserve(
        self, path: Path, target_bytes: int, budget: ReservationBudget
    ) -> ReservationResult:
        """Report a scripted outcome. Creates nothing, deletes nothing."""
        self.attempted.append(target_bytes)
        outcome = self._outcomes.get(target_bytes, self._default)
        reserved = target_bytes if outcome is ProbeOutcome.VERIFIED else 0
        return ReservationResult(
            outcome=outcome,
            reserved_bytes=reserved,
            detail="replayed outcome; no space was reserved",
        )


def build(outcomes: Mapping[int, ProbeOutcome] | None = None) -> ReplayedProbe:
    """Factory for the adapter registry."""
    return ReplayedProbe(outcomes)
