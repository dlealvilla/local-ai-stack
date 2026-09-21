"""PrerequisiteReadiness (MACHI 2.5.1).

Inspect, diagnose, plan, and optionally remediate bounded environment
prerequisites. Discover remains read-only. This capability does not
admit resources, compose serving plans, optimize, or manage packages.
"""

from machi.prerequisites.contracts import (
    PrerequisitePolicy,
    PrerequisiteReadinessReport,
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
from machi.prerequisites.policy import default_prerequisite_policy
from machi.prerequisites.ports import PrerequisiteAdapter
from machi.prerequisites.service import PrerequisiteReadiness

__all__ = [
    "PrerequisiteAdapter",
    "PrerequisitePolicy",
    "PrerequisiteReadiness",
    "PrerequisiteReadinessReport",
    "ReadinessState",
    "default_prerequisite_policy",
    "prerequisite_diagnosed",
    "prerequisite_inspected",
    "prerequisite_plan_created",
    "prerequisite_remediation_completed",
    "prerequisite_remediation_failed",
    "prerequisite_remediation_started",
    "prerequisite_verified",
]
