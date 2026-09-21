"""PrerequisiteReadiness contracts owned by capability 2.5.

Discover observations stay read-only. These documents record environment
readiness, policy, and bounded remediation. They do not authorize
capacity, and they are not serving or deployment recipes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.ids import Name, PrerequisiteActionId, PrerequisitePlanId
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe, Unresolved, is_resolved

_TOKEN_MAX = 64
_REASON_MAX = 240
_EXCERPT_MAX = 160
_PATH_MAX = 256
_ALLOWED_MAX = 160


class ReadinessState(StrEnum):
    """Truthful environment readiness. Unknown is never Ready or Missing."""

    READY = "ready"
    BLOCKED = "blocked"
    REMEDIABLE = "remediable"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"


class PolicyMode(StrEnum):
    """How far PrerequisiteReadiness may go on this invocation."""

    OBSERVE_ONLY = "observe_only"
    PLAN_ONLY = "plan_only"
    REMEDIATE = "remediate"


class DiagnosisCode(StrEnum):
    """Why the target is not ready, or that it is. Not a boolean."""

    NONE = "none"
    EXECUTABLE_MISSING = "executable_missing"
    INVOCATION_TIMEOUT = "invocation_timeout"
    PERMISSION_DENIED = "permission_denied"
    MISSING_INTERPRETER_DEPENDENCY = "missing_interpreter_dependency"
    INTERPRETER_AMBIGUOUS = "interpreter_ambiguous"
    UNRECOGNIZED_FAILURE = "unrecognized_failure"
    NOT_APPLICABLE_ON_HOST = "not_applicable_on_host"


class ActionKind(StrEnum):
    """Bounded actions this capability may plan. Not a package manager."""

    NO_OP = "no_op"
    INSTALL_INTERPRETER_DEPENDENCY = "install_interpreter_dependency"


class ActionStatus(StrEnum):
    """What happened to one planned action."""

    NOT_ATTEMPTED = "not_attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    NO_OP = "no_op"


class RemediationSourceKind(StrEnum):
    """Where a dependency would be obtained. Network is not intrinsic."""

    NETWORK = "network"
    LOCAL_ARTIFACT = "local_artifact"
    MANAGED_CACHE = "managed_cache"
    UNAVAILABLE = "unavailable"


class SettingProvenance(StrEnum):
    """Who selected a prerequisite setting. Not optimizer provenance."""

    PRODUCT_DEFAULT = "product_default"
    POLICY = "policy"
    ADMINISTRATOR = "administrator"
    DETECTED_ENVIRONMENT = "detected_environment"


class SettingSupportState(StrEnum):
    """Whether the control-plane setting is usable now."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"


class InterpreterResolution(StrEnum):
    """How the CLI interpreter was established, or why it was not."""

    SHEBANG_ABSOLUTE = "shebang_absolute"
    ENV_WHICH = "env_which"
    AMBIGUOUS = "ambiguous"
    NOT_PYTHON = "not_python"
    NOT_REQUIRED = "not_required"
    UNRESOLVED = "unresolved"


@contract(kind="prerequisite.setting", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteSetting(Contract):
    """One inspectable control-plane setting for later command-center use."""

    name: str = meaning("dotted setting name, for example policy.mode")
    value: str = meaning("current selected/desired value as text")
    provenance: SettingProvenance = meaning("who selected this value")
    reason: str = meaning("why this value is in force")
    allowed_values: str = meaning("compact allowed-value description")
    support_state: SettingSupportState = meaning("whether this setting is usable")
    mutability: str = meaning("runtime or restart_required")
    invalidation: str = meaning(
        "what must re-run if this setting changes, for example reinspect"
    )

    def __post_init__(self) -> None:
        _require_token(self.name, what="setting name", maximum=_TOKEN_MAX)
        _require_bounded(self.value, what="setting value", maximum=_TOKEN_MAX)
        _require_bounded(self.reason, what="setting reason", maximum=_REASON_MAX)
        _require_bounded(
            self.allowed_values, what="allowed values", maximum=_ALLOWED_MAX
        )
        if self.mutability not in {"runtime", "restart_required"}:
            raise ValidationError(
                "setting mutability is not supported",
                mutability=self.mutability,
            )
        _require_token(self.invalidation, what="invalidation", maximum=_TOKEN_MAX)


@contract(kind="prerequisite.policy", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisitePolicy(Contract):
    """Selected remediation policy. Desired/selected, not running state."""

    mode: PolicyMode = meaning("observe_only, plan_only, or remediate")
    mode_provenance: SettingProvenance = meaning("who selected the policy mode")
    mode_reason: str = meaning("why this policy mode is in force")
    dependency_source: RemediationSourceKind = meaning(
        "where an allowlisted dependency would be obtained"
    )
    dependency_source_provenance: SettingProvenance = meaning(
        "who selected the dependency source"
    )
    dependency_source_reason: str = meaning("why this dependency source is in force")

    def __post_init__(self) -> None:
        _require_bounded(self.mode_reason, what="mode reason", maximum=_REASON_MAX)
        _require_bounded(
            self.dependency_source_reason,
            what="dependency source reason",
            maximum=_REASON_MAX,
        )

    def inspectable_settings(self) -> tuple[PrerequisiteSetting, ...]:
        """Typed settings a future command center can aggregate."""
        return (
            PrerequisiteSetting(
                name="policy.mode",
                value=self.mode.value,
                provenance=self.mode_provenance,
                reason=self.mode_reason,
                allowed_values="observe_only|plan_only|remediate",
                support_state=SettingSupportState.SUPPORTED,
                mutability="runtime",
                invalidation="reinspect",
            ),
            PrerequisiteSetting(
                name="policy.dependency_source",
                value=self.dependency_source.value,
                provenance=self.dependency_source_provenance,
                reason=self.dependency_source_reason,
                allowed_values="network|local_artifact|managed_cache|unavailable",
                support_state=SettingSupportState.SUPPORTED,
                mutability="runtime",
                invalidation="reinspect",
            ),
        )


@contract(kind="prerequisite.target", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteTarget(Contract):
    """What is being checked. Not a GPU and not a serving recipe."""

    target_id: Name = meaning("stable target identity, for example amd_smi")
    adapter_id: str = meaning("adapter identifier that owns inspection")
    target_kind: str = meaning("target class, for example vendor_cli")

    def __post_init__(self) -> None:
        _require_token(self.adapter_id, what="adapter id", maximum=_TOKEN_MAX)
        _require_token(self.target_kind, what="target kind", maximum=_TOKEN_MAX)


@contract(kind="prerequisite.inspection", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteInspection(Contract):
    """Facts from one inspect pass. Paths are operator-local, not events."""

    target: PrerequisiteTarget = meaning("which prerequisite was inspected")
    inspected_at: dt.datetime = meaning("when inspection ran; timezone-aware UTC")
    applicable: bool = meaning("whether this adapter applies on this host")
    executable_found: bool = meaning("whether the target executable was resolved")
    executable_basename: str = meaning("basename only; empty when not found")
    executable_path: Maybe[str] = meaning(
        "absolute executable path when known; Unresolved otherwise"
    )
    interpreter_resolution: InterpreterResolution = meaning(
        "how the CLI interpreter was established"
    )
    interpreter_basename: str = meaning(
        "interpreter basename when known; empty when unresolved"
    )
    interpreter_path: Maybe[str] = meaning(
        "absolute interpreter path when uniquely known; Unresolved otherwise"
    )
    invocation_ok: bool = meaning("whether the health invocation exited zero")
    timed_out: bool = meaning("whether the health invocation exceeded its timeout")
    permission_denied: bool = meaning("whether execution was refused by permissions")
    exit_code: Maybe[int] = meaning("process exit code when one was observed")
    stderr_excerpt: str = meaning("bounded, path-stripped stderr used for diagnosis")
    readiness: ReadinessState = meaning("readiness implied by this inspection alone")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "inspected_at", require_utc(self.inspected_at, what="inspected_at")
        )
        _require_bounded(
            self.executable_basename, what="executable basename", maximum=_TOKEN_MAX
        )
        _require_bounded(
            self.interpreter_basename, what="interpreter basename", maximum=_TOKEN_MAX
        )
        _require_bounded(
            self.stderr_excerpt, what="stderr excerpt", maximum=_EXCERPT_MAX
        )
        _require_maybe_path(self.executable_path, what="executable path")
        _require_maybe_path(self.interpreter_path, what="interpreter path")
        if "/" in self.executable_basename or "\\" in self.executable_basename:
            raise ValidationError("executable basename must not be a path")
        if "/" in self.interpreter_basename or "\\" in self.interpreter_basename:
            raise ValidationError("interpreter basename must not be a path")
        if (
            self.invocation_ok
            and self.readiness is not ReadinessState.READY
            and self.readiness is not ReadinessState.NOT_APPLICABLE
        ):
            raise ValidationError(
                "a successful invocation cannot leave the target unready",
                readiness=self.readiness.value,
            )


@contract(kind="prerequisite.diagnosis", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteDiagnosis(Contract):
    """Classified inspection. Missing is not unknown; unknown is not ready."""

    code: DiagnosisCode = meaning("stable diagnosis class")
    module_name: Maybe[str] = meaning(
        "imported module name when the class is a missing interpreter dependency"
    )
    detail: str = meaning("bounded human-readable diagnosis")
    readiness: ReadinessState = meaning("readiness after diagnosis")
    remediable: bool = meaning(
        "whether an allowlisted action exists for this diagnosis under policy"
    )

    def __post_init__(self) -> None:
        _require_bounded(self.detail, what="diagnosis detail", maximum=_REASON_MAX)
        if is_resolved(self.module_name):
            _require_token(self.module_name, what="module name", maximum=_TOKEN_MAX)
        if self.remediable and self.readiness is not ReadinessState.REMEDIABLE:
            raise ValidationError(
                "remediable diagnoses must use remediable readiness",
                readiness=self.readiness.value,
            )
        if (
            self.readiness is ReadinessState.READY
            and self.code is not DiagnosisCode.NONE
        ):
            raise ValidationError(
                "ready diagnoses must use code none",
                code=self.code.value,
            )


@contract(kind="prerequisite.interpreter_dependency", version=1)
@dataclass(frozen=True, slots=True)
class InterpreterDependency(Contract):
    """One allowlisted interpreter package. Never a free-form pip name."""

    module_name: str = meaning("import name that failed, for example yaml")
    package_name: str = meaning("install name from the adapter allowlist")
    constraint: str = meaning("exact version constraint, for example ==6.0.2")

    def __post_init__(self) -> None:
        _require_token(self.module_name, what="module name", maximum=_TOKEN_MAX)
        _require_token(self.package_name, what="package name", maximum=_TOKEN_MAX)
        if not self.constraint.startswith("=="):
            raise ValidationError(
                "dependency constraint must be an exact == pin",
                constraint=self.constraint,
            )
        _require_token(self.constraint, what="constraint", maximum=_TOKEN_MAX)
        if "/" in self.package_name or "\\" in self.package_name:
            raise ValidationError("package name must not be a path")

    def requirement(self) -> str:
        """pip requirement string from the allowlist pin."""
        return f"{self.package_name}{self.constraint}"


@contract(kind="prerequisite.action", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteAction(Contract):
    """One planned action. Proposals only until policy permits mutation."""

    action_id: PrerequisiteActionId = meaning("opaque identity of this action")
    action_kind: ActionKind = meaning("no_op or install_interpreter_dependency")
    status: ActionStatus = meaning(
        "not_attempted, succeeded, failed, blocked, or no_op"
    )
    source: RemediationSourceKind = meaning("where the dependency would be obtained")
    reason: str = meaning("why this action was planned")
    dependency: InterpreterDependency | None = meaning(
        "allowlisted dependency when this action installs one",
        default=None,
    )

    def __post_init__(self) -> None:
        _require_bounded(self.reason, what="action reason", maximum=_REASON_MAX)
        if (
            self.action_kind is ActionKind.INSTALL_INTERPRETER_DEPENDENCY
            and self.dependency is None
        ):
            raise ValidationError("install actions require an allowlisted dependency")
        if self.action_kind is ActionKind.NO_OP and self.dependency is not None:
            raise ValidationError("no-op actions cannot carry a dependency")


@contract(kind="prerequisite.plan", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisitePlan(Contract):
    """Exact remediation plan. Not executed until policy is remediate."""

    plan_id: PrerequisitePlanId = meaning("opaque identity of this plan")
    target: PrerequisiteTarget = meaning("target this plan applies to")
    diagnosis: PrerequisiteDiagnosis = meaning("diagnosis that produced the plan")
    actions: tuple[PrerequisiteAction, ...] = meaning("ordered bounded actions")
    policy_mode: PolicyMode = meaning("policy mode under which the plan was created")
    created_at: dt.datetime = meaning("when the plan was composed; timezone-aware UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", require_utc(self.created_at, what="created_at")
        )
        if not self.actions:
            raise ValidationError(
                "a prerequisite plan must contain at least one action"
            )
        if len(self.actions) > 4:
            raise ValidationError("a prerequisite plan exceeds the action bound")


@contract(kind="prerequisite.remediation_result", version=1)
@dataclass(frozen=True, slots=True)
class RemediationResult(Contract):
    """What a mutation attempt did. Success is not assumed without verify."""

    action: PrerequisiteAction = meaning("action after the attempt")
    attempted: bool = meaning("whether a host mutation was invoked")
    changed: bool = meaning("whether the adapter believes the environment changed")
    interpreter_basename: str = meaning(
        "interpreter that would receive the dependency; empty when unknown"
    )
    stdout_excerpt: str = meaning("bounded, path-stripped command stdout")
    stderr_excerpt: str = meaning("bounded, path-stripped command stderr")
    reason: str = meaning("what happened, including interpreter identity")

    def __post_init__(self) -> None:
        _require_bounded(
            self.interpreter_basename, what="interpreter basename", maximum=_TOKEN_MAX
        )
        _require_bounded(
            self.stdout_excerpt, what="stdout excerpt", maximum=_EXCERPT_MAX
        )
        _require_bounded(
            self.stderr_excerpt, what="stderr excerpt", maximum=_EXCERPT_MAX
        )
        _require_bounded(self.reason, what="remediation reason", maximum=_REASON_MAX)
        if "/" in self.interpreter_basename or "\\" in self.interpreter_basename:
            raise ValidationError("interpreter basename must not be a path")
        if self.changed and not self.attempted:
            raise ValidationError("an unattempted remediation cannot report a change")


@contract(kind="prerequisite.verification_result", version=1)
@dataclass(frozen=True, slots=True)
class VerificationResult(Contract):
    """Re-inspection after mutation, or confirmation that no mutation ran."""

    inspection: PrerequisiteInspection = meaning("inspection used for verification")
    diagnosis: PrerequisiteDiagnosis = meaning("diagnosis of the verification inspect")
    ready: bool = meaning("true only when verification readiness is ready")
    readiness: ReadinessState = meaning("readiness after verification")

    def __post_init__(self) -> None:
        if self.ready and self.readiness is not ReadinessState.READY:
            raise ValidationError("ready verification requires ready state")
        if self.readiness is ReadinessState.READY and not self.ready:
            raise ValidationError("ready state must set ready true")


@contract(kind="prerequisite.readiness_report", version=1)
@dataclass(frozen=True, slots=True)
class PrerequisiteReadinessReport(Contract):
    """Full inspect/diagnose/plan/optional-remediate/verify cycle."""

    target: PrerequisiteTarget = meaning("target evaluated")
    policy: PrerequisitePolicy = meaning("selected policy for this invocation")
    settings: tuple[PrerequisiteSetting, ...] = meaning(
        "inspectable settings for command-center aggregation"
    )
    inspection_before: PrerequisiteInspection = meaning("first inspection")
    diagnosis: PrerequisiteDiagnosis = meaning("diagnosis of the first inspection")
    readiness_before: ReadinessState = meaning("readiness before any mutation")
    readiness_after: ReadinessState = meaning("readiness at the end of the cycle")
    mutated: bool = meaning("whether this cycle invoked a host mutation")
    plan: PrerequisitePlan | None = meaning(
        "remediation plan when policy is plan_only or remediate",
        default=None,
    )
    remediation: RemediationResult | None = meaning(
        "mutation result when an action was considered",
        default=None,
    )
    verification: VerificationResult | None = meaning(
        "re-inspection after remediate, or none when not required",
        default=None,
    )

    def __post_init__(self) -> None:
        if self.mutated and self.policy.mode is not PolicyMode.REMEDIATE:
            raise ValidationError("non-remediate policy cannot mutate the host")
        if (
            self.readiness_after is ReadinessState.READY
            and self.mutated
            and (self.verification is None or not self.verification.ready)
        ):
            raise ValidationError(
                "mutation cannot report ready without successful verification"
            )


def _require_token(value: str, *, what: str, maximum: int) -> None:
    if not value:
        raise ValidationError(f"{what} is required", what=what)
    if len(value) > maximum:
        raise ValidationError(
            f"{what} is too long",
            what=what,
            maximum=maximum,
            length=len(value),
        )
    if "/" in value or "\\" in value or " " in value:
        raise ValidationError(f"{what} must be a path-free token", what=what)


def _require_bounded(value: str, *, what: str, maximum: int) -> None:
    if not isinstance(value, str):
        raise ValidationError(
            f"{what} must be a string",
            what=what,
            actual_type=type(value).__name__,
        )
    if len(value) > maximum:
        raise ValidationError(
            f"{what} is too long",
            what=what,
            maximum=maximum,
            length=len(value),
        )


def _require_maybe_path(value: object, *, what: str) -> None:
    if isinstance(value, Unresolved):
        return
    if not isinstance(value, str):
        raise ValidationError(f"{what} must be a string or Unresolved", what=what)
    if not value:
        raise ValidationError(f"{what} is empty", what=what)
    if len(value) > _PATH_MAX:
        raise ValidationError(
            f"{what} is too long",
            what=what,
            maximum=_PATH_MAX,
            length=len(value),
        )
