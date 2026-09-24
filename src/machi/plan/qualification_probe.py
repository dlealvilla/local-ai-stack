"""Qualification probe request. It is not a deployment configuration."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.plan.identity import plan_fingerprint

_TOKEN_MAX = 80
_PURPOSE = "qualification"


@contract(kind="plan.qualification_probe", version=1)
@dataclass(frozen=True, slots=True)
class QualificationProbe(Contract):
    """One admission hold for a qualification attempt."""

    probe_id: str = meaning("identity of this probe request")
    purpose: str = meaning("qualification; distinct from deployment")
    provider: str = meaning("runtime provider")
    candidate_id: str = meaning("normalized candidate")
    digest: str = meaning("provider model digest")
    foundation_id: str = meaning("foundation identity")
    generation_id: str = meaning("foundation generation")
    capacity_evidence_id: str = meaning("capacity snapshot")
    accelerator_identity: str = meaning("device this probe asks to hold")
    accelerator_memory_bytes: int = meaning("SAFE accelerator bytes requested")
    host_memory_bytes: int = meaning("SAFE host bytes requested")
    persistent_bytes: int = meaning("persistent bytes requested")
    transient_bytes: int = meaning("transient bytes requested")
    cpu_count: int = meaning("process slots requested")
    fingerprint: str = meaning("purpose-sensitive token of this probe")
    policy_version: str = meaning("plan policy cited by the fingerprint")

    def __post_init__(self) -> None:
        if self.purpose != _PURPOSE:
            raise ValidationError("probe purpose must be qualification")
        for label, value in (
            ("probe", self.probe_id),
            ("provider", self.provider),
            ("candidate", self.candidate_id),
            ("digest", self.digest),
            ("foundation", self.foundation_id),
            ("generation", self.generation_id),
            ("capacity", self.capacity_evidence_id),
            ("accelerator", self.accelerator_identity),
            ("fingerprint", self.fingerprint),
            ("policy", self.policy_version),
        ):
            if not value or len(value) > _TOKEN_MAX:
                raise ValidationError(f"{label} is empty or too long")
        if self.accelerator_memory_bytes < 1 or self.host_memory_bytes < 1:
            raise ValidationError("probe memory requests must be positive")
        if self.persistent_bytes < 0 or self.transient_bytes < 0:
            raise ValidationError("probe storage requests must not be negative")
        if self.cpu_count < 1:
            raise ValidationError("probe cpu request must be positive")


def make_qualification_probe(
    *,
    provider: str,
    candidate_id: str,
    digest: str,
    foundation_id: str,
    generation_id: str,
    capacity_evidence_id: str,
    accelerator_identity: str,
    accelerator_memory_bytes: int,
    host_memory_bytes: int,
    policy_version: str,
    persistent_bytes: int = 0,
    transient_bytes: int = 0,
    cpu_count: int = 1,
) -> QualificationProbe:
    """Build a probe whose fingerprint includes the qualification purpose."""
    token = plan_fingerprint(
        _PURPOSE,
        policy_version,
        provider,
        candidate_id,
        digest,
        foundation_id,
        generation_id,
        capacity_evidence_id,
        accelerator_identity,
        str(accelerator_memory_bytes),
        str(host_memory_bytes),
        str(persistent_bytes),
        str(transient_bytes),
        str(cpu_count),
    )
    return QualificationProbe(
        probe_id=f"qprb_{token[:16]}",
        purpose=_PURPOSE,
        provider=provider,
        candidate_id=candidate_id,
        digest=digest,
        foundation_id=foundation_id,
        generation_id=generation_id,
        capacity_evidence_id=capacity_evidence_id,
        accelerator_identity=accelerator_identity,
        accelerator_memory_bytes=accelerator_memory_bytes,
        host_memory_bytes=host_memory_bytes,
        persistent_bytes=persistent_bytes,
        transient_bytes=transient_bytes,
        cpu_count=cpu_count,
        fingerprint=token,
        policy_version=policy_version,
    )
