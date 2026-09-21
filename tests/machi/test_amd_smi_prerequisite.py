"""AMD vendor-CLI PrerequisiteReadiness adapter (MACHI 2.5.1)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import pytest

from machi.adapters.prerequisites.amd_smi import AmdSmiPrerequisiteAdapter
from machi.adapters.prerequisites.command import CommandOutcome
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import is_resolved
from machi.prerequisites.contracts import (
    ActionKind,
    ActionStatus,
    DiagnosisCode,
    InterpreterDependency,
    InterpreterResolution,
    PolicyMode,
    PrerequisiteAction,
    PrerequisitePolicy,
    ReadinessState,
    RemediationSourceKind,
    SettingProvenance,
)
from machi.prerequisites.policy import default_prerequisite_policy, policy_with_mode
from machi.prerequisites.service import PrerequisiteReadiness

FIXED = dt.datetime(2026, 9, 21, 11, 0, tzinfo=dt.UTC)
YAML_STDERR = "ModuleNotFoundError: No module named 'yaml'\n"


def _ok() -> CommandOutcome:
    return CommandOutcome(
        found=True,
        timed_out=False,
        permission_denied=False,
        returncode=0,
        stdout="[]\n",
        stderr="",
    )


def _fail(stderr: str, *, returncode: int = 1) -> CommandOutcome:
    return CommandOutcome(
        found=True,
        timed_out=False,
        permission_denied=False,
        returncode=returncode,
        stdout="",
        stderr=stderr,
    )


@dataclass
class ScriptedHost:
    """Fixture host: PATH, shebang, and command outcomes without real mutation."""

    platform_name: str = "Linux"
    executable: str | None = "/opt/rocm/bin/amd-smi"
    shebang: str = "#!/usr/bin/env python3"
    python: str | None = "/opt/rocm/bin/python3"
    inspect_outcome: CommandOutcome = field(default_factory=_ok)
    pip_outcome: CommandOutcome = field(default_factory=_ok)
    flip_ready_after_pip: bool = False
    calls: list[tuple[str, ...]] = field(default_factory=list)
    _ready: bool = False

    def which(self, name: str) -> str | None:
        if name == "amd-smi":
            return self.executable
        if name in {"python3", "python"}:
            return self.python
        return None

    def read_shebang(self, path: str) -> str:
        if path != self.executable:
            raise FileNotFoundError(path)
        return self.shebang

    def runner(self, argv: Sequence[str], timeout: float) -> CommandOutcome:
        recorded = tuple(argv)
        self.calls.append(recorded)
        if len(recorded) >= 4 and recorded[1:4] == ("-m", "pip", "install"):
            if self.flip_ready_after_pip:
                self._ready = True
            return self.pip_outcome
        if self.flip_ready_after_pip and self._ready:
            return _ok()
        return self.inspect_outcome

    def adapter(self) -> AmdSmiPrerequisiteAdapter:
        return AmdSmiPrerequisiteAdapter(
            runner=self.runner,
            which=self.which,
            read_shebang=self.read_shebang,
            platform_name=self.platform_name,
            clock=FixedClock(FIXED),
        )


def test_ready_inspect_is_ready_and_plan_is_no_op() -> None:
    host = ScriptedHost()
    report, events = PrerequisiteReadiness().evaluate(
        host.adapter(),
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    assert report.readiness_after is ReadinessState.READY
    assert report.diagnosis.code is DiagnosisCode.NONE
    assert report.mutated is False
    assert report.plan is not None
    assert report.plan.actions[0].action_kind is ActionKind.NO_OP
    assert not any("-m" in call for call in host.calls)
    assert any(event.event_type.value == "prerequisite.inspected" for event in events)


def test_missing_executable_is_blocked_and_not_remediable() -> None:
    host = ScriptedHost(executable=None)
    inspection = host.adapter().inspect()
    diagnosis = host.adapter().diagnose(inspection)
    assert inspection.executable_found is False
    assert diagnosis.code is DiagnosisCode.EXECUTABLE_MISSING
    assert diagnosis.readiness is ReadinessState.BLOCKED
    assert diagnosis.remediable is False


def test_missing_yaml_module_is_remediable_missing_interpreter_dependency() -> None:
    host = ScriptedHost(inspect_outcome=_fail(YAML_STDERR))
    adapter = host.adapter()
    inspection = adapter.inspect()
    diagnosis = adapter.diagnose(inspection)
    assert diagnosis.code is DiagnosisCode.MISSING_INTERPRETER_DEPENDENCY
    assert diagnosis.module_name == "yaml"
    assert diagnosis.remediable is True
    assert diagnosis.readiness is ReadinessState.REMEDIABLE
    assert inspection.interpreter_resolution is InterpreterResolution.ENV_WHICH
    assert inspection.interpreter_basename == "python3"
    assert is_resolved(inspection.interpreter_path)


def test_unrecognized_failure_is_failed() -> None:
    host = ScriptedHost(inspect_outcome=_fail("boom: unknown vendor error"))
    diagnosis = host.adapter().diagnose(host.adapter().inspect())
    assert diagnosis.code is DiagnosisCode.UNRECOGNIZED_FAILURE
    assert diagnosis.readiness is ReadinessState.FAILED
    assert diagnosis.remediable is False


def test_timeout_is_failed() -> None:
    host = ScriptedHost(
        inspect_outcome=CommandOutcome(
            found=True,
            timed_out=True,
            permission_denied=False,
            returncode=None,
            stdout="",
            stderr="",
        )
    )
    diagnosis = host.adapter().diagnose(host.adapter().inspect())
    assert diagnosis.code is DiagnosisCode.INVOCATION_TIMEOUT
    assert diagnosis.readiness is ReadinessState.FAILED


def test_permission_denied_is_blocked() -> None:
    host = ScriptedHost(
        inspect_outcome=CommandOutcome(
            found=True,
            timed_out=False,
            permission_denied=True,
            returncode=None,
            stdout="",
            stderr="PermissionError: [Errno 13] Permission denied",
        )
    )
    diagnosis = host.adapter().diagnose(host.adapter().inspect())
    assert diagnosis.code is DiagnosisCode.PERMISSION_DENIED
    assert diagnosis.readiness is ReadinessState.BLOCKED
    assert diagnosis.remediable is False


def test_not_applicable_off_linux() -> None:
    host = ScriptedHost(platform_name="Darwin")
    inspection = host.adapter().inspect()
    diagnosis = host.adapter().diagnose(inspection)
    assert inspection.applicable is False
    assert diagnosis.readiness is ReadinessState.NOT_APPLICABLE
    assert diagnosis.code is DiagnosisCode.NOT_APPLICABLE_ON_HOST
    assert host.calls == []


def test_observe_only_never_mutates() -> None:
    host = ScriptedHost(inspect_outcome=_fail(YAML_STDERR))
    report, _events = PrerequisiteReadiness().evaluate(
        host.adapter(),
        policy_with_mode(PolicyMode.OBSERVE_ONLY),
        clock=FixedClock(FIXED),
    )
    assert report.plan is None
    assert report.mutated is False
    assert report.diagnosis.remediable is True
    assert not any("-m" in call for call in host.calls)


def test_plan_only_returns_plan_and_does_not_mutate() -> None:
    host = ScriptedHost(inspect_outcome=_fail(YAML_STDERR))
    report, events = PrerequisiteReadiness().evaluate(
        host.adapter(),
        default_prerequisite_policy(),
        clock=FixedClock(FIXED),
    )
    assert report.policy.mode is PolicyMode.PLAN_ONLY
    assert report.plan is not None
    action = report.plan.actions[0]
    assert action.action_kind is ActionKind.INSTALL_INTERPRETER_DEPENDENCY
    assert action.dependency is not None
    assert action.dependency.requirement() == "PyYAML==6.0.2"
    assert report.mutated is False
    assert report.remediation is None
    assert any(
        event.event_type.value == "prerequisite.plan_created" for event in events
    )
    assert not any("-m" in call for call in host.calls)


def test_remediate_executes_only_allowlisted_action_then_verifies_ready() -> None:
    host = ScriptedHost(
        inspect_outcome=_fail(YAML_STDERR),
        flip_ready_after_pip=True,
    )
    report, events = PrerequisiteReadiness().evaluate(
        host.adapter(),
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    assert report.mutated is True
    assert report.readiness_after is ReadinessState.READY
    assert report.verification is not None
    assert report.verification.ready is True
    pip_calls = [call for call in host.calls if call[1:4] == ("-m", "pip", "install")]
    assert pip_calls == [
        ("/opt/rocm/bin/python3", "-m", "pip", "install", "PyYAML==6.0.2")
    ]
    types = [event.event_type.value for event in events]
    assert "prerequisite.remediation_started" in types
    assert "prerequisite.remediation_completed" in types
    assert "prerequisite.verified" in types


def test_remediation_failure_is_not_ready() -> None:
    host = ScriptedHost(
        inspect_outcome=_fail(YAML_STDERR),
        pip_outcome=_fail("Could not install"),
    )
    report, events = PrerequisiteReadiness().evaluate(
        host.adapter(),
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    assert report.mutated is True
    assert report.readiness_after is not ReadinessState.READY
    assert report.remediation is not None
    assert report.remediation.action.status is ActionStatus.FAILED
    assert "prerequisite.remediation_failed" in [
        event.event_type.value for event in events
    ]


def test_already_ready_remediate_is_idempotent_no_op() -> None:
    host = ScriptedHost()
    first, _ = PrerequisiteReadiness().evaluate(
        host.adapter(),
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    second, _ = PrerequisiteReadiness().evaluate(
        host.adapter(),
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    assert first.readiness_after is ReadinessState.READY
    assert second.readiness_after is ReadinessState.READY
    assert first.mutated is False
    assert second.mutated is False
    assert not any("-m" in call for call in host.calls)


def test_second_cycle_after_success_is_ready_without_mutation() -> None:
    host = ScriptedHost(
        inspect_outcome=_fail(YAML_STDERR),
        flip_ready_after_pip=True,
    )
    adapter = host.adapter()
    first, _ = PrerequisiteReadiness().evaluate(
        adapter,
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    pip_after_first = [
        call for call in host.calls if call[1:4] == ("-m", "pip", "install")
    ]
    second, _ = PrerequisiteReadiness().evaluate(
        adapter,
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    pip_after_second = [
        call for call in host.calls if call[1:4] == ("-m", "pip", "install")
    ]
    assert first.readiness_after is ReadinessState.READY
    assert second.readiness_after is ReadinessState.READY
    assert second.mutated is False
    assert pip_after_second == pip_after_first


def test_ambiguous_interpreter_fails_closed() -> None:
    host = ScriptedHost(
        inspect_outcome=_fail(YAML_STDERR),
        shebang="#!/bin/bash",
    )
    diagnosis = host.adapter().diagnose(host.adapter().inspect())
    assert diagnosis.code is DiagnosisCode.INTERPRETER_AMBIGUOUS
    assert diagnosis.readiness is ReadinessState.UNKNOWN
    assert diagnosis.remediable is False


def test_env_python_missing_from_path_fails_closed() -> None:
    host = ScriptedHost(
        inspect_outcome=_fail(YAML_STDERR),
        python=None,
    )
    inspection = host.adapter().inspect()
    diagnosis = host.adapter().diagnose(inspection)
    assert inspection.interpreter_resolution is InterpreterResolution.AMBIGUOUS
    assert diagnosis.code is DiagnosisCode.INTERPRETER_AMBIGUOUS
    assert diagnosis.remediable is False


def test_non_allowlisted_module_is_not_installed() -> None:
    host = ScriptedHost(
        inspect_outcome=_fail("ModuleNotFoundError: No module named 'evil'\n")
    )
    adapter = host.adapter()
    report, _ = PrerequisiteReadiness().evaluate(
        adapter,
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    assert report.diagnosis.module_name == "evil"
    assert report.diagnosis.remediable is False
    assert report.mutated is False
    assert not any("-m" in call for call in host.calls)


def test_forged_dependency_is_refused() -> None:
    host = ScriptedHost(inspect_outcome=_fail(YAML_STDERR))
    adapter = host.adapter()
    inspection = adapter.inspect()
    diagnosis = adapter.diagnose(inspection)
    policy = policy_with_mode(PolicyMode.REMEDIATE)
    plan = adapter.plan(inspection, diagnosis, policy)
    forged = InterpreterDependency(
        module_name="yaml",
        package_name="evil",
        constraint="==1.0.0",
    )
    bad_action = PrerequisiteAction(
        action_id=plan.actions[0].action_id,
        action_kind=ActionKind.INSTALL_INTERPRETER_DEPENDENCY,
        status=ActionStatus.NOT_ATTEMPTED,
        dependency=forged,
        source=RemediationSourceKind.NETWORK,
        reason="forged",
    )
    bad_plan = replace(plan, actions=(bad_action,))
    with pytest.raises(ValidationError, match="allowlist"):
        adapter.remediate(bad_plan, policy, inspection)


def test_offline_source_plans_but_does_not_install() -> None:
    host = ScriptedHost(inspect_outcome=_fail(YAML_STDERR))
    policy = replace_source(
        default_prerequisite_policy(), RemediationSourceKind.LOCAL_ARTIFACT
    )
    report, _ = PrerequisiteReadiness().evaluate(
        host.adapter(),
        policy_with_mode(PolicyMode.REMEDIATE, source=policy),
        clock=FixedClock(FIXED),
    )
    assert report.plan is not None
    assert report.plan.actions[0].status is ActionStatus.BLOCKED
    assert report.mutated is False
    assert not any("-m" in call for call in host.calls)


def replace_source(
    policy: PrerequisitePolicy, source: RemediationSourceKind
) -> PrerequisitePolicy:
    return PrerequisitePolicy(
        mode=policy.mode,
        mode_provenance=policy.mode_provenance,
        mode_reason=policy.mode_reason,
        dependency_source=source,
        dependency_source_provenance=SettingProvenance.ADMINISTRATOR,
        dependency_source_reason="selected local artifact source",
    )


def test_absolute_shebang_interpreter_is_used() -> None:
    host = ScriptedHost(
        inspect_outcome=_fail(YAML_STDERR),
        shebang="#!/opt/rocm/bin/python3",
        flip_ready_after_pip=True,
    )
    report, _ = PrerequisiteReadiness().evaluate(
        host.adapter(),
        policy_with_mode(PolicyMode.REMEDIATE),
        clock=FixedClock(FIXED),
    )
    assert report.inspection_before.interpreter_resolution is (
        InterpreterResolution.SHEBANG_ABSOLUTE
    )
    pip_calls = [call for call in host.calls if call[1:4] == ("-m", "pip", "install")]
    assert pip_calls[0][0] == "/opt/rocm/bin/python3"


def test_settings_remain_typed_on_the_report() -> None:
    host = ScriptedHost()
    report, _ = PrerequisiteReadiness().evaluate(
        host.adapter(),
        default_prerequisite_policy(),
        clock=FixedClock(FIXED),
    )
    names = {item.name for item in report.settings}
    assert "policy.mode" in names
    assert "policy.dependency_source" in names
    assert "allowlist.interpreter_dependencies" in names
    assert "inspect.timeout_seconds" in names
