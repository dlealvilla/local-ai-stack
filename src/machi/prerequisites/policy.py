"""Product-default PrerequisiteReadiness policy.

Sensible initial configuration: inspect and plan, do not mutate until
an administrator or bootstrap path selects remediate.
"""

from machi.prerequisites.contracts import (
    PolicyMode,
    PrerequisitePolicy,
    RemediationSourceKind,
    SettingProvenance,
)


def default_prerequisite_policy() -> PrerequisitePolicy:
    """PLAN_ONLY with network represented as the development proof source."""
    return PrerequisitePolicy(
        mode=PolicyMode.PLAN_ONLY,
        mode_provenance=SettingProvenance.PRODUCT_DEFAULT,
        mode_reason="mutation requires an explicit remediate policy",
        dependency_source=RemediationSourceKind.NETWORK,
        dependency_source_provenance=SettingProvenance.PRODUCT_DEFAULT,
        dependency_source_reason=(
            "network install is the development proof source; "
            "local-artifact and managed-cache remain representable"
        ),
    )


def policy_with_mode(
    mode: PolicyMode,
    *,
    provenance: SettingProvenance = SettingProvenance.ADMINISTRATOR,
    reason: str = "selected on the invocation",
    source: PrerequisitePolicy | None = None,
) -> PrerequisitePolicy:
    """Return a policy with an overridden mode and inspectable provenance."""
    base = source or default_prerequisite_policy()
    return PrerequisitePolicy(
        mode=mode,
        mode_provenance=provenance,
        mode_reason=reason,
        dependency_source=base.dependency_source,
        dependency_source_provenance=base.dependency_source_provenance,
        dependency_source_reason=base.dependency_source_reason,
    )
