"""Loading and creating platform state.

Two rules govern this module and both are about not being clever.

**The installation identity is never regenerated.** If the state record
cannot be read, this refuses. The tempting alternative — mint a fresh
identity and carry on — turns every record that referenced the old one into
an orphan, silently, and the platform would look healthy while having lost
track of everything it owns.

**First run is a normal case, not an error.** No state means a new
installation, which is initialized and written. The previous attempt's
bootstrap deadlock came from treating an empty platform as a problem to be
solved before starting rather than as the state a platform starts in.
"""

from __future__ import annotations

from dataclasses import dataclass

from kultrun.identity.contracts import PrincipalKind, Subject, SubjectId
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import PersistenceError, PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.platform.contracts import (
    ComponentHealth,
    HealthStatus,
    InstallationId,
    PhaseReport,
    PlatformState,
)

#: The singleton key under which platform state is stored.
STATE_KEY = "current"

#: Name of the default local administrator created on first run.
DEFAULT_ADMINISTRATOR = "local-administrator"


@dataclass(frozen=True, slots=True)
class StateLoad:
    """The outcome of loading platform state on startup."""

    state: PlatformState
    administrator: Subject
    created: bool


class PlatformStateStore:
    """Reads and writes the single platform state record."""

    phase = Name("platform-state")
    component = Name("platform-state")

    def __init__(self, store: Store, clock: Clock, platform_version: str) -> None:
        self._store = store
        self._clock = clock
        self._platform_version = platform_version
        self._loaded: PlatformState | None = None
        self._administrator: Subject | None = None

    @property
    def administrator(self) -> Subject:
        """The local administrator's own record.

        Stored separately from platform state because a subject is an
        entity: it has its own identity, and at Stage 5.1 it will have its
        own directory. Embedding it in the installation record would have
        given one thing's shape two owners.
        """
        if self._administrator is None:
            raise PreconditionFailedError(
                "platform state has not been loaded; run startup first"
            )
        return self._administrator

    @property
    def current(self) -> PlatformState:
        """The loaded state, or a refusal if startup has not run."""
        if self._loaded is None:
            raise PreconditionFailedError(
                "platform state has not been loaded; run startup first"
            )
        return self._loaded

    @property
    def is_loaded(self) -> bool:
        """Whether startup has loaded or created state."""
        return self._loaded is not None

    def load_or_initialize(self) -> StateLoad:
        """Read the installation's state, creating it on first run."""
        try:
            existing = self._store.get(PlatformState, STATE_KEY)
        except PersistenceError as error:
            # Refuse rather than recreate. A fresh installation identity
            # would orphan every record that referenced the old one.
            raise PreconditionFailedError(
                "platform state exists but cannot be read; refusing to mint a "
                "new installation identity over it",
                reason=str(error),
            ) from error

        if existing is not None:
            administrator = self._store.get(
                Subject, existing.administrator_id.value
            )
            if administrator is None:
                raise PreconditionFailedError(
                    "platform state references an administrator whose record "
                    "is missing; refusing to invent one",
                    administrator_id=existing.administrator_id.value,
                )
            self._loaded = existing
            self._administrator = administrator
            return StateLoad(
                state=existing, administrator=administrator, created=False
            )

        administrator = Subject(
            subject_id=SubjectId.generate(),
            principal_kind=PrincipalKind.ADMINISTRATOR,
            display_name=DEFAULT_ADMINISTRATOR,
        )
        created = PlatformState(
            installation_id=InstallationId.generate(),
            platform_version=self._platform_version,
            initialized_at=self._clock.now(),
            administrator_id=administrator.subject_id,
        )
        # The subject first: a platform state that references a record which
        # was never written is worse than no platform state at all.
        self._store.put(administrator.subject_id.value, administrator)
        self._store.put(STATE_KEY, created)
        self._loaded = created
        self._administrator = administrator
        return StateLoad(state=created, administrator=administrator, created=True)

    def reconcile(self) -> PhaseReport:
        """Startup phase: make the installation's own state available."""
        try:
            outcome = self.load_or_initialize()
        except PreconditionFailedError as error:
            return PhaseReport(
                phase=self.phase, succeeded=False, detail=error.message
            )
        detail = (
            "initialized a new installation"
            if outcome.created
            else f"loaded installation {outcome.state.installation_id}"
        )
        return PhaseReport(phase=self.phase, succeeded=True, detail=detail)

    def check_health(self) -> ComponentHealth:
        """Healthy once state is available; unknown before startup has run."""
        if self._loaded is None:
            return ComponentHealth(
                component=self.component,
                status=HealthStatus.UNKNOWN,
                detail="startup has not run",
            )
        return ComponentHealth(component=self.component, status=HealthStatus.HEALTHY)
