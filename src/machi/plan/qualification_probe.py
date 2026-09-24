"""Qualification probe request. Bytes are computed at admission."""

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
    """Intent to qualify. The hold size is the remaining SAFE envelope."""

    probe_id: str = meaning("identity of this probe request")
    purpose: str = meaning("qualification; distinct from deployment")
    provider: str = meaning("runtime provider")
    candidate_id: str = meaning("normalized candidate")
    digest: str = meaning("provider model digest")
    foundation_id: str = meaning("foundation identity")
    generation_id: str = meaning("foundation generation")
    capacity_evidence_id: str = meaning("capacity snapshot")
    accelerator_identity: str = meaning("device this probe asks to hold")
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


def make_qualification_probe(
    *,
    provider: str,
    candidate_id: str,
    digest: str,
    foundation_id: str,
    generation_id: str,
    capacity_evidence_id: str,
    accelerator_identity: str,
    policy_version: str,
) -> QualificationProbe:
    """Build a probe. Callers do not choose the reserved byte counts."""
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
        fingerprint=token,
        policy_version=policy_version,
    )
