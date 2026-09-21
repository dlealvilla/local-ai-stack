"""PrerequisiteReadiness contracts, policy, and orchestration (MACHI 2.5.1)."""

from __future__ import annotations

import datetime as dt
import json

from machi.kernel.clock import FixedClock
from machi.kernel.ids import Name, PrerequisiteActionId, PrerequisitePlanId
from machi.kernel.privacy import FORBIDDEN_PUBLIC_OPS_KEYS, PrivacyClass
from machi.kernel.schema import from_dict, to_dict
from machi.kernel.unresolved import Unresolved, UnresolvedReason, is_resolved
from machi.prerequisites.contracts import (
    ActionKind,
    ActionStatus,
    DiagnosisCode,
    InterpreterResolution,
    PolicyMode,
    PrerequisiteAction,
    PrerequisiteDiagnosis,
    PrerequisiteInspection,
    PrerequisitePlan,
    PrerequisitePolicy,
    PrerequisiteReadinessReport,
    PrerequisiteTarget,
    ReadinessState,
    RemediationSourceKind,
    SettingProvenance,
)
from machi.prerequisites.diagnose import missing_module_name
from machi.prerequisites.events import prerequisite_inspected
from machi.prerequisites.policy import default_prerequisite_policy, policy_with_mode

FIXED = dt.datetime(2026, 9, 21, 11, 0, tzinfo=dt.UTC)


def _target() -> PrerequisiteTarget:
    return PrerequisiteTarget(
        target_id=Name("amd_smi"),
        adapter_id="amd_smi",
        target_kind="vendor_cli",
    )


def test_missing_module_diagnosis_is_generic_not_yaml_specific() -> None:
    assert missing_module_name("ModuleNotFoundError: No module named 'yaml'") == "yaml"
    assert missing_module_name("ModuleNotFoundError: No module named 'requests'") == (
        "requests"
    )
    assert missing_module_name("command failed") is None


def test_unknown_is_not_ready_or_missing() -> None:
    values = {item.value for item in ReadinessState}
    assert values == {
        "ready",
        "blocked",
        "remediable",
        "unknown",
        "not_applicable",
        "failed",
    }
    assert "missing" not in values


def test_default_policy_is_plan_only_and_inspectable() -> None:
    policy = default_prerequisite_policy()
    assert policy.mode is PolicyMode.PLAN_ONLY
    assert policy.mode_provenance is SettingProvenance.PRODUCT_DEFAULT
    names = {item.name: item for item in policy.inspectable_settings()}
    assert names["policy.mode"].value == "plan_only"
    assert names["policy.dependency_source"].value == "network"


def test_policy_override_records_administrator_provenance() -> None:
    policy = policy_with_mode(PolicyMode.REMEDIATE)
    assert policy.mode is PolicyMode.REMEDIATE
    assert policy.mode_provenance is SettingProvenance.ADMINISTRATOR


def test_readiness_report_round_trips() -> None:
    inspection = PrerequisiteInspection(
        target=_target(),
        inspected_at=FIXED,
        applicable=True,
        executable_found=True,
        executable_basename="cli",
        executable_path="/usr/bin/cli",
        interpreter_resolution=InterpreterResolution.ENV_WHICH,
        interpreter_basename="python3",
        interpreter_path="/usr/bin/python3",
        invocation_ok=True,
        timed_out=False,
        permission_denied=False,
        exit_code=0,
        stderr_excerpt="",
        readiness=ReadinessState.READY,
    )
    diagnosis = PrerequisiteDiagnosis(
        code=DiagnosisCode.NONE,
        module_name=Unresolved(UnresolvedReason.NOT_PROVIDED, "not a module failure"),
        detail="vendor CLI health invocation succeeded",
        readiness=ReadinessState.READY,
        remediable=False,
    )
    plan = PrerequisitePlan(
        plan_id=PrerequisitePlanId.generate(),
        target=_target(),
        diagnosis=diagnosis,
        actions=(
            PrerequisiteAction(
                action_id=PrerequisiteActionId.generate(),
                action_kind=ActionKind.NO_OP,
                status=ActionStatus.NO_OP,
                dependency=None,
                source=RemediationSourceKind.NETWORK,
                reason="prerequisite is already ready",
            ),
        ),
        policy_mode=PolicyMode.PLAN_ONLY,
        created_at=FIXED,
    )
    policy = default_prerequisite_policy()
    report = PrerequisiteReadinessReport(
        target=_target(),
        policy=policy,
        settings=policy.inspectable_settings(),
        inspection_before=inspection,
        diagnosis=diagnosis,
        plan=plan,
        remediation=None,
        verification=None,
        readiness_before=ReadinessState.READY,
        readiness_after=ReadinessState.READY,
        mutated=False,
    )
    restored = from_dict(to_dict(report))
    assert restored == report
    assert isinstance(restored, PrerequisiteReadinessReport)
    assert is_resolved(restored.inspection_before.interpreter_path)


def test_observe_only_cannot_claim_mutation() -> None:
    policy = PrerequisitePolicy(
        mode=PolicyMode.OBSERVE_ONLY,
        mode_provenance=SettingProvenance.PRODUCT_DEFAULT,
        mode_reason="observe",
        dependency_source=RemediationSourceKind.NETWORK,
        dependency_source_provenance=SettingProvenance.PRODUCT_DEFAULT,
        dependency_source_reason="network",
    )
    inspection = PrerequisiteInspection(
        target=_target(),
        inspected_at=FIXED,
        applicable=False,
        executable_found=False,
        executable_basename="",
        executable_path=Unresolved(
            UnresolvedReason.NOT_MEASURED, "executable was not found"
        ),
        interpreter_resolution=InterpreterResolution.NOT_REQUIRED,
        interpreter_basename="",
        interpreter_path=Unresolved(
            UnresolvedReason.INCONCLUSIVE,
            "CLI interpreter could not be uniquely identified",
        ),
        invocation_ok=False,
        timed_out=False,
        permission_denied=False,
        exit_code=Unresolved(UnresolvedReason.NOT_MEASURED, "no process exit code"),
        stderr_excerpt="",
        readiness=ReadinessState.NOT_APPLICABLE,
    )
    diagnosis = PrerequisiteDiagnosis(
        code=DiagnosisCode.NOT_APPLICABLE_ON_HOST,
        module_name=Unresolved(UnresolvedReason.NOT_PROVIDED, "not a module failure"),
        detail="AMD vendor CLI observation is Linux-only",
        readiness=ReadinessState.NOT_APPLICABLE,
        remediable=False,
    )
    report = PrerequisiteReadinessReport(
        target=_target(),
        policy=policy,
        settings=policy.inspectable_settings(),
        inspection_before=inspection,
        diagnosis=diagnosis,
        plan=None,
        remediation=None,
        verification=None,
        readiness_before=ReadinessState.NOT_APPLICABLE,
        readiness_after=ReadinessState.NOT_APPLICABLE,
        mutated=False,
    )
    assert report.mutated is False


def test_inspected_event_omits_paths_and_customer_keys() -> None:
    inspection = PrerequisiteInspection(
        target=_target(),
        inspected_at=FIXED,
        applicable=True,
        executable_found=True,
        executable_basename="cli",
        executable_path="/secret/path/cli",
        interpreter_resolution=InterpreterResolution.SHEBANG_ABSOLUTE,
        interpreter_basename="python3",
        interpreter_path="/secret/path/python3",
        invocation_ok=True,
        timed_out=False,
        permission_denied=False,
        exit_code=0,
        stderr_excerpt="",
        readiness=ReadinessState.READY,
    )
    event = prerequisite_inspected(inspection, clock=FixedClock(FIXED))
    assert event.privacy is PrivacyClass.OPERATIONAL
    document = json.dumps(to_dict(event.payload))
    assert "/secret/path" not in document
    assert "prompt" not in document
    for key in FORBIDDEN_PUBLIC_OPS_KEYS:
        assert f'"{key}"' not in document
