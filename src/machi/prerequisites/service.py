"""PrerequisiteReadiness orchestration (MACHI 2.5.1).

Owns the inspect, diagnose, plan, optional remediate, and verify cycle.
Adapters perform host I/O. This module does not import Discover, pip,
or later Blocks.
"""

from __future__ import annotations

from machi.kernel.clock import Clock, SystemClock
from machi.kernel.events import EventRecord
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.unresolved import Maybe
from machi.prerequisites.contracts import (
    ActionKind,
    ActionStatus,
    PolicyMode,
    PrerequisitePolicy,
    PrerequisiteReadinessReport,
    PrerequisiteSetting,
    ReadinessState,
)
from machi.prerequisites.events import (
    prerequisite_diagnosed,
    prerequisite_inspected,
    prerequisite_plan_created,
    prerequisite_remediation_completed,
    prerequisite_remediation_failed,
    prerequisite_remediation_started,
    prerequisite_verified,
)
from machi.prerequisites.ports import PrerequisiteAdapter


class PrerequisiteReadiness:
    """Run one bounded readiness cycle against a single adapter."""

    def evaluate(
        self,
        adapter: PrerequisiteAdapter,
        policy: PrerequisitePolicy,
        *,
        install_id: Maybe[InstallId] | None = None,
        install_run_id: Maybe[InstallRunId] | None = None,
        clock: Clock | None = None,
    ) -> tuple[PrerequisiteReadinessReport, tuple[EventRecord, ...]]:
        """Inspect, diagnose, and optionally plan/remediate/verify.

        OBSERVE_ONLY never plans or mutates. PLAN_ONLY never mutates.
        REMEDIATE mutates only an allowlisted action, then re-inspects.
        READY is never claimed from a mutation without verification.
        """
        time = clock or SystemClock()
        events: list[EventRecord] = []
        inspection = adapter.inspect()
        diagnosis = adapter.diagnose(inspection)
        settings = _inspectable_settings(adapter, policy)
        events.append(
            prerequisite_inspected(
                inspection,
                install_id=install_id,
                install_run_id=install_run_id,
                clock=time,
            )
        )
        events.append(
            prerequisite_diagnosed(
                diagnosis,
                target_id=inspection.target.target_id,
                adapter_id=inspection.target.adapter_id,
                install_id=install_id,
                install_run_id=install_run_id,
                clock=time,
            )
        )
        if policy.mode is PolicyMode.OBSERVE_ONLY:
            report = PrerequisiteReadinessReport(
                target=inspection.target,
                policy=policy,
                settings=settings,
                inspection_before=inspection,
                diagnosis=diagnosis,
                plan=None,
                remediation=None,
                verification=None,
                readiness_before=diagnosis.readiness,
                readiness_after=diagnosis.readiness,
                mutated=False,
            )
            return report, tuple(events)

        plan = adapter.plan(inspection, diagnosis, policy)
        events.append(
            prerequisite_plan_created(
                plan,
                install_id=install_id,
                install_run_id=install_run_id,
                clock=time,
            )
        )
        primary = plan.actions[0]
        should_mutate = (
            policy.mode is PolicyMode.REMEDIATE
            and primary.action_kind is not ActionKind.NO_OP
            and primary.status is ActionStatus.NOT_ATTEMPTED
        )
        if not should_mutate:
            report = PrerequisiteReadinessReport(
                target=inspection.target,
                policy=policy,
                settings=settings,
                inspection_before=inspection,
                diagnosis=diagnosis,
                plan=plan,
                remediation=None,
                verification=None,
                readiness_before=diagnosis.readiness,
                readiness_after=diagnosis.readiness,
                mutated=False,
            )
            return report, tuple(events)

        events.append(
            prerequisite_remediation_started(
                plan,
                install_id=install_id,
                install_run_id=install_run_id,
                clock=time,
            )
        )
        result = adapter.remediate(plan, policy, inspection)
        failed = result.action.status in {ActionStatus.FAILED, ActionStatus.BLOCKED}
        if failed:
            events.append(
                prerequisite_remediation_failed(
                    plan,
                    result,
                    install_id=install_id,
                    install_run_id=install_run_id,
                    clock=time,
                )
            )
        else:
            events.append(
                prerequisite_remediation_completed(
                    plan,
                    result,
                    install_id=install_id,
                    install_run_id=install_run_id,
                    clock=time,
                )
            )
        after = adapter.inspect()
        verification = adapter.verify(after)
        events.append(
            prerequisite_verified(
                verification,
                target_id=inspection.target.target_id,
                adapter_id=inspection.target.adapter_id,
                install_id=install_id,
                install_run_id=install_run_id,
                clock=time,
            )
        )
        readiness_after = verification.readiness
        if (
            result.attempted
            and readiness_after is ReadinessState.READY
            and not verification.ready
        ):
            readiness_after = ReadinessState.FAILED
        report = PrerequisiteReadinessReport(
            target=inspection.target,
            policy=policy,
            settings=settings,
            inspection_before=inspection,
            diagnosis=diagnosis,
            plan=plan,
            remediation=result,
            verification=verification,
            readiness_before=diagnosis.readiness,
            readiness_after=readiness_after,
            mutated=result.attempted,
        )
        return report, tuple(events)


def _inspectable_settings(
    adapter: PrerequisiteAdapter,
    policy: PrerequisitePolicy,
) -> tuple[PrerequisiteSetting, ...]:
    return policy.inspectable_settings() + adapter.extra_settings()
