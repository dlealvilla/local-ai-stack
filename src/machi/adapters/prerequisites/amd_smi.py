"""AMD vendor-CLI prerequisite adapter (MACHI 2.5.1).

Determines whether ``amd-smi`` is operational. The first remediable
instance is a missing interpreter module such as yaml; the architecture
is the missing-module class, not PyYAML.
"""

from __future__ import annotations

import datetime as dt
import platform
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from machi.adapters.prerequisites.command import (
    CommandOutcome,
    CommandRunner,
    bounded_detail,
    run_command,
)
from machi.adapters.prerequisites.interpreter import (
    InterpreterIdentity,
    read_shebang_line,
    resolve_cli_interpreter,
)
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ValidationError
from machi.kernel.ids import Name, PrerequisiteActionId, PrerequisitePlanId
from machi.kernel.unresolved import Unresolved, UnresolvedReason, is_resolved
from machi.prerequisites.contracts import (
    ActionKind,
    ActionStatus,
    DiagnosisCode,
    InterpreterDependency,
    InterpreterResolution,
    PolicyMode,
    PrerequisiteAction,
    PrerequisiteDiagnosis,
    PrerequisiteInspection,
    PrerequisitePlan,
    PrerequisitePolicy,
    PrerequisiteSetting,
    PrerequisiteTarget,
    ReadinessState,
    RemediationResult,
    RemediationSourceKind,
    SettingProvenance,
    SettingSupportState,
    VerificationResult,
)
from machi.prerequisites.diagnose import (
    looks_like_permission_denied,
    missing_module_name,
)

ADAPTER_ID = "amd_smi"
TARGET_ID = Name("amd_smi")
EXECUTABLE_NAME = "amd-smi"
HEALTH_SUBCOMMAND: tuple[str, ...] = ("list", "--json")
INSPECT_TIMEOUT_SECONDS = 20.0
REMEDIATE_TIMEOUT_SECONDS = 120.0
DEFAULT_ALLOWLIST: Mapping[str, InterpreterDependency] = {
    "yaml": InterpreterDependency(
        module_name="yaml",
        package_name="PyYAML",
        constraint="==6.0.2",
    )
}
_MISSING_PATH = Unresolved(UnresolvedReason.NOT_MEASURED, "executable was not found")
_MISSING_INTERPRETER = Unresolved(
    UnresolvedReason.INCONCLUSIVE,
    "CLI interpreter could not be uniquely identified",
)
_MISSING_EXIT = Unresolved(UnresolvedReason.NOT_MEASURED, "no process exit code")


def _target() -> PrerequisiteTarget:
    return PrerequisiteTarget(
        target_id=TARGET_ID,
        adapter_id=ADAPTER_ID,
        target_kind="vendor_cli",
    )


class AmdSmiPrerequisiteAdapter:
    """Inspect and optionally remediate the AMD vendor CLI environment."""

    adapter_id = ADAPTER_ID

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        which: Callable[[str], str | None] | None = None,
        read_shebang: Callable[[str], str] | None = None,
        platform_name: str | None = None,
        allowlist: Mapping[str, InterpreterDependency] | None = None,
        clock: Clock | None = None,
        inspect_timeout_seconds: float = INSPECT_TIMEOUT_SECONDS,
        remediate_timeout_seconds: float = REMEDIATE_TIMEOUT_SECONDS,
    ) -> None:
        self._runner = runner or run_command
        self._which = which or shutil.which
        self._read_shebang = read_shebang or read_shebang_line
        self._platform_name = platform_name or platform.system()
        self._allowlist = dict(allowlist or DEFAULT_ALLOWLIST)
        self._clock = clock or SystemClock()
        self._inspect_timeout = inspect_timeout_seconds
        self._remediate_timeout = remediate_timeout_seconds

    def extra_settings(self) -> tuple[PrerequisiteSetting, ...]:
        """Typed adapter settings for later command-center aggregation."""
        packages = ",".join(
            sorted(item.requirement() for item in self._allowlist.values())
        )
        return (
            PrerequisiteSetting(
                name="inspect.timeout_seconds",
                value=str(int(self._inspect_timeout)),
                provenance=SettingProvenance.PRODUCT_DEFAULT,
                reason="bounded vendor CLI health timeout",
                allowed_values="positive integer seconds",
                support_state=SettingSupportState.SUPPORTED,
                mutability="runtime",
                invalidation="reinspect",
            ),
            PrerequisiteSetting(
                name="remediate.timeout_seconds",
                value=str(int(self._remediate_timeout)),
                provenance=SettingProvenance.PRODUCT_DEFAULT,
                reason="bounded allowlisted pip timeout",
                allowed_values="positive integer seconds",
                support_state=SettingSupportState.SUPPORTED,
                mutability="runtime",
                invalidation="reinspect",
            ),
            PrerequisiteSetting(
                name="allowlist.interpreter_dependencies",
                value=packages,
                provenance=SettingProvenance.PRODUCT_DEFAULT,
                reason="only these pins may be installed",
                allowed_values=packages,
                support_state=SettingSupportState.SUPPORTED,
                mutability="restart_required",
                invalidation="reinspect",
            ),
        )

    def inspect(self) -> PrerequisiteInspection:
        """Read amd-smi health. Never mutates."""
        now = self._clock.now()
        if self._platform_name != "Linux":
            return PrerequisiteInspection(
                target=_target(),
                inspected_at=now,
                applicable=False,
                executable_found=False,
                executable_basename="",
                executable_path=_MISSING_PATH,
                interpreter_resolution=InterpreterResolution.NOT_REQUIRED,
                interpreter_basename="",
                interpreter_path=_MISSING_INTERPRETER,
                invocation_ok=False,
                timed_out=False,
                permission_denied=False,
                exit_code=_MISSING_EXIT,
                stderr_excerpt="",
                readiness=ReadinessState.NOT_APPLICABLE,
            )
        located = self._which(EXECUTABLE_NAME)
        if not located:
            return PrerequisiteInspection(
                target=_target(),
                inspected_at=now,
                applicable=True,
                executable_found=False,
                executable_basename="",
                executable_path=_MISSING_PATH,
                interpreter_resolution=InterpreterResolution.UNRESOLVED,
                interpreter_basename="",
                interpreter_path=_MISSING_INTERPRETER,
                invocation_ok=False,
                timed_out=False,
                permission_denied=False,
                exit_code=_MISSING_EXIT,
                stderr_excerpt="",
                readiness=ReadinessState.BLOCKED,
            )
        identity = resolve_cli_interpreter(
            located,
            which=self._which,
            read_shebang=self._read_shebang,
        )
        outcome = self._runner((located, *HEALTH_SUBCOMMAND), self._inspect_timeout)
        return self._inspection_from_outcome(
            now=now,
            located=located,
            identity=identity,
            outcome=outcome,
        )

    def diagnose(self, inspection: PrerequisiteInspection) -> PrerequisiteDiagnosis:
        """Classify an inspection without mutating."""
        if not inspection.applicable:
            return PrerequisiteDiagnosis(
                code=DiagnosisCode.NOT_APPLICABLE_ON_HOST,
                module_name=Unresolved(
                    UnresolvedReason.NOT_PROVIDED, "not a module failure"
                ),
                detail="AMD vendor CLI observation is Linux-only",
                readiness=ReadinessState.NOT_APPLICABLE,
                remediable=False,
            )
        if inspection.invocation_ok:
            return PrerequisiteDiagnosis(
                code=DiagnosisCode.NONE,
                module_name=Unresolved(
                    UnresolvedReason.NOT_PROVIDED, "not a module failure"
                ),
                detail="vendor CLI health invocation succeeded",
                readiness=ReadinessState.READY,
                remediable=False,
            )
        if not inspection.executable_found:
            return PrerequisiteDiagnosis(
                code=DiagnosisCode.EXECUTABLE_MISSING,
                module_name=Unresolved(
                    UnresolvedReason.NOT_PROVIDED, "not a module failure"
                ),
                detail="vendor CLI executable was not found",
                readiness=ReadinessState.BLOCKED,
                remediable=False,
            )
        if inspection.timed_out:
            return PrerequisiteDiagnosis(
                code=DiagnosisCode.INVOCATION_TIMEOUT,
                module_name=Unresolved(
                    UnresolvedReason.NOT_PROVIDED, "not a module failure"
                ),
                detail="vendor CLI health invocation timed out",
                readiness=ReadinessState.FAILED,
                remediable=False,
            )
        if inspection.permission_denied or looks_like_permission_denied(
            inspection.stderr_excerpt
        ):
            return PrerequisiteDiagnosis(
                code=DiagnosisCode.PERMISSION_DENIED,
                module_name=Unresolved(
                    UnresolvedReason.NOT_PROVIDED, "not a module failure"
                ),
                detail="vendor CLI execution was refused by permissions",
                readiness=ReadinessState.BLOCKED,
                remediable=False,
            )
        module = missing_module_name(inspection.stderr_excerpt)
        if module is None:
            return PrerequisiteDiagnosis(
                code=DiagnosisCode.UNRECOGNIZED_FAILURE,
                module_name=Unresolved(
                    UnresolvedReason.NOT_PROVIDED, "not a module failure"
                ),
                detail=inspection.stderr_excerpt or "vendor CLI exited non-zero",
                readiness=ReadinessState.FAILED,
                remediable=False,
            )
        allowlisted = self._allowlist.get(module)
        interpreter_ok = inspection.interpreter_resolution in {
            InterpreterResolution.SHEBANG_ABSOLUTE,
            InterpreterResolution.ENV_WHICH,
        }
        if not interpreter_ok:
            return PrerequisiteDiagnosis(
                code=DiagnosisCode.INTERPRETER_AMBIGUOUS,
                module_name=module,
                detail=(
                    "missing interpreter dependency was identified but the "
                    "CLI interpreter could not be uniquely resolved"
                ),
                readiness=ReadinessState.UNKNOWN,
                remediable=False,
            )
        if allowlisted is None:
            return PrerequisiteDiagnosis(
                code=DiagnosisCode.MISSING_INTERPRETER_DEPENDENCY,
                module_name=module,
                detail="missing interpreter module is not on the adapter allowlist",
                readiness=ReadinessState.BLOCKED,
                remediable=False,
            )
        return PrerequisiteDiagnosis(
            code=DiagnosisCode.MISSING_INTERPRETER_DEPENDENCY,
            module_name=module,
            detail="vendor CLI interpreter is missing an allowlisted module",
            readiness=ReadinessState.REMEDIABLE,
            remediable=True,
        )

    def plan(
        self,
        inspection: PrerequisiteInspection,
        diagnosis: PrerequisiteDiagnosis,
        policy: PrerequisitePolicy,
    ) -> PrerequisitePlan:
        """Produce an exact plan. Never mutates."""
        now = self._clock.now()
        if diagnosis.readiness is ReadinessState.READY:
            action = PrerequisiteAction(
                action_id=PrerequisiteActionId.generate(),
                action_kind=ActionKind.NO_OP,
                status=ActionStatus.NO_OP,
                dependency=None,
                source=policy.dependency_source,
                reason="prerequisite is already ready",
            )
        elif diagnosis.remediable and is_resolved(diagnosis.module_name):
            dependency = self._allowlist[diagnosis.module_name]
            status = ActionStatus.NOT_ATTEMPTED
            reason = f"install {dependency.requirement()} into the CLI interpreter"
            if policy.dependency_source is not RemediationSourceKind.NETWORK:
                status = ActionStatus.BLOCKED
                reason = (
                    "allowlisted dependency is planned but the selected "
                    "source is not an implemented installer"
                )
            action = PrerequisiteAction(
                action_id=PrerequisiteActionId.generate(),
                action_kind=ActionKind.INSTALL_INTERPRETER_DEPENDENCY,
                status=status,
                dependency=dependency,
                source=policy.dependency_source,
                reason=reason,
            )
        else:
            action = PrerequisiteAction(
                action_id=PrerequisiteActionId.generate(),
                action_kind=ActionKind.NO_OP,
                status=ActionStatus.BLOCKED,
                dependency=None,
                source=policy.dependency_source,
                reason="no allowlisted remediation exists for this diagnosis",
            )
        return PrerequisitePlan(
            plan_id=PrerequisitePlanId.generate(),
            target=inspection.target,
            diagnosis=diagnosis,
            actions=(action,),
            policy_mode=policy.mode,
            created_at=now,
        )

    def remediate(
        self,
        plan: PrerequisitePlan,
        policy: PrerequisitePolicy,
        inspection: PrerequisiteInspection,
    ) -> RemediationResult:
        """Install only an allowlisted pin into the resolved interpreter."""
        if policy.mode is not PolicyMode.REMEDIATE:
            raise ValidationError("remediate requires remediate policy")
        action = plan.actions[0]
        if (
            action.action_kind is ActionKind.NO_OP
            or action.status is ActionStatus.NO_OP
        ):
            return RemediationResult(
                action=action,
                attempted=False,
                changed=False,
                interpreter_basename=inspection.interpreter_basename,
                stdout_excerpt="",
                stderr_excerpt="",
                reason="no-op; environment was not mutated",
            )
        if action.status is ActionStatus.BLOCKED:
            return RemediationResult(
                action=action,
                attempted=False,
                changed=False,
                interpreter_basename=inspection.interpreter_basename,
                stdout_excerpt="",
                stderr_excerpt="",
                reason=action.reason,
            )
        if action.dependency is None:
            raise ValidationError("unsupported prerequisite action")
        if not is_resolved(inspection.interpreter_path):
            blocked = _with_status(action, ActionStatus.FAILED)
            return RemediationResult(
                action=blocked,
                attempted=False,
                changed=False,
                interpreter_basename=inspection.interpreter_basename,
                stdout_excerpt="",
                stderr_excerpt="",
                reason=(
                    "refused to install: CLI interpreter was not uniquely identified"
                ),
            )
        argv = self._allowlisted_pip_argv(
            interpreter=inspection.interpreter_path,
            dependency=action.dependency,
        )
        outcome = self._runner(argv, self._remediate_timeout)
        interpreter_name = Path(inspection.interpreter_path).name
        if outcome.timed_out or outcome.permission_denied or outcome.returncode != 0:
            failed = _with_status(action, ActionStatus.FAILED)
            excerpt = bounded_detail(outcome.stderr) or "dependency install failed"
            return RemediationResult(
                action=failed,
                attempted=True,
                changed=False,
                interpreter_basename=interpreter_name,
                stdout_excerpt=bounded_detail(outcome.stdout),
                stderr_excerpt=excerpt,
                reason=(
                    f"failed installing {action.dependency.requirement()} "
                    f"with {interpreter_name}"
                ),
            )
        succeeded = _with_status(action, ActionStatus.SUCCEEDED)
        return RemediationResult(
            action=succeeded,
            attempted=True,
            changed=True,
            interpreter_basename=interpreter_name,
            stdout_excerpt=bounded_detail(outcome.stdout),
            stderr_excerpt=bounded_detail(outcome.stderr),
            reason=(
                f"installed {action.dependency.requirement()} into the "
                f"environment used by {EXECUTABLE_NAME} via {interpreter_name}"
            ),
        )

    def verify(self, inspection: PrerequisiteInspection) -> VerificationResult:
        """Classify a re-inspection. Does not mutate."""
        diagnosis = self.diagnose(inspection)
        ready = diagnosis.readiness is ReadinessState.READY
        return VerificationResult(
            inspection=inspection,
            diagnosis=diagnosis,
            ready=ready,
            readiness=diagnosis.readiness,
        )

    def _inspection_from_outcome(
        self,
        *,
        now: dt.datetime,
        located: str,
        identity: InterpreterIdentity,
        outcome: CommandOutcome,
    ) -> PrerequisiteInspection:
        invocation_ok = (
            outcome.found
            and not outcome.timed_out
            and not outcome.permission_denied
            and outcome.returncode == 0
        )
        if invocation_ok:
            readiness = ReadinessState.READY
        elif not outcome.found or outcome.permission_denied:
            readiness = ReadinessState.BLOCKED
        elif outcome.timed_out:
            readiness = ReadinessState.FAILED
        else:
            readiness = ReadinessState.FAILED
        stderr = outcome.stderr
        module = missing_module_name(stderr)
        if module is not None:
            stderr_excerpt = f"ModuleNotFoundError: No module named '{module}'"
            if readiness is not ReadinessState.READY:
                readiness = ReadinessState.FAILED
        else:
            stderr_excerpt = bounded_detail(stderr)
            if outcome.permission_denied:
                stderr_excerpt = stderr_excerpt or "permission denied"
        exit_code: object
        if outcome.returncode is None:
            exit_code = _MISSING_EXIT
        else:
            exit_code = outcome.returncode
        interpreter_path = identity.path
        return PrerequisiteInspection(
            target=_target(),
            inspected_at=now,
            applicable=True,
            executable_found=True,
            executable_basename=EXECUTABLE_NAME,
            executable_path=located,
            interpreter_resolution=identity.resolution,
            interpreter_basename=identity.basename,
            interpreter_path=interpreter_path,
            invocation_ok=invocation_ok,
            timed_out=outcome.timed_out,
            permission_denied=outcome.permission_denied,
            exit_code=exit_code,
            stderr_excerpt=stderr_excerpt,
            readiness=readiness,
        )

    def _allowlisted_pip_argv(
        self,
        *,
        interpreter: str,
        dependency: InterpreterDependency,
    ) -> tuple[str, ...]:
        expected = self._allowlist.get(dependency.module_name)
        if expected is None or expected != dependency:
            raise ValidationError(
                "refusing to install a dependency that is not on the allowlist",
                module=dependency.module_name,
            )
        argv = (
            interpreter,
            "-m",
            "pip",
            "install",
            dependency.requirement(),
        )
        self._assert_allowlisted_pip(
            argv, interpreter=interpreter, dependency=dependency
        )
        return argv

    def _assert_allowlisted_pip(
        self,
        argv: Sequence[str],
        *,
        interpreter: str,
        dependency: InterpreterDependency,
    ) -> None:
        if len(argv) != 5:
            raise ValidationError("pip argv is not the allowlisted shape")
        if argv[0] != interpreter:
            raise ValidationError("pip argv must use the resolved CLI interpreter")
        if tuple(argv[1:4]) != ("-m", "pip", "install"):
            raise ValidationError("pip argv must be python -m pip install")
        if argv[4] != dependency.requirement():
            raise ValidationError("pip argv package is not the allowlisted pin")


def _with_status(
    action: PrerequisiteAction, status: ActionStatus
) -> PrerequisiteAction:
    return PrerequisiteAction(
        action_id=action.action_id,
        action_kind=action.action_kind,
        status=status,
        dependency=action.dependency,
        source=action.source,
        reason=action.reason,
    )
