"""Rukan support snapshot (Kernel projection).

The product name is Rukan. This contract is a non-authoritative export
of identities already stored. It does not admit, serve, or carry
customer content.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from machi.kernel.errors import ValidationError
from machi.kernel.privacy import FORBIDDEN_PUBLIC_OPS_KEYS
from machi.kernel.schema import Contract, contract, from_dict, meaning, to_dict

NOT_RECORDED = "not_recorded"
SNAPSHOT_SCHEMA = "rukan.support_snapshot"
_TOKEN_MAX = 240
_EVENT_MAX = 32
_EXTRA_FORBIDDEN = frozenset(
    {
        "prompt",
        "response",
        "messages",
        "document",
        "documents",
        "rag",
        "file_path",
        "absolute_path",
        "email",
        "email_display",
        "email_normalized",
    }
)


@contract(kind="kernel.support_event", version=1)
@dataclass(frozen=True, slots=True)
class SupportEvent(Contract):
    """Envelope of one operational event. The payload is omitted."""

    event_type: str = meaning("dotted event name")
    outcome: str = meaning("pass, fail, blocked, info, or unresolved")
    occurred_at: str = meaning("UTC timestamp of the event")
    privacy: str = meaning("public_ops or operational only")

    def __post_init__(self) -> None:
        for label, value in (
            ("event type", self.event_type),
            ("outcome", self.outcome),
            ("occurred", self.occurred_at),
            ("privacy", self.privacy),
        ):
            _token(label, value)
        if self.privacy not in {"public_ops", "operational"}:
            raise ValidationError("support event privacy is not exportable")


@contract(kind="kernel.support_snapshot", version=1)
@dataclass(frozen=True, slots=True)
class SupportSnapshot(Contract):
    """Imported deployment summary. Not live host truth and not admission."""

    snapshot_id: str = meaning("deterministic identity of this export")
    schema_name: str = meaning("rukan.support_snapshot")
    exported_at: str = meaning("when this projection was written; UTC")
    install_id: str = meaning("install identity, or not_recorded")
    install_created_at: str = meaning(
        "when the install record was first written, or not_recorded"
    )
    product_name: str = meaning("customer product name")
    package_name: str = meaning("internal package namespace")
    version: str = meaning("running product version")
    build_id: str = meaning("build id, or not_recorded for a checkout")
    source_commit: str = meaning("source commit when known, or not_recorded")
    os_family: str = meaning("normalized OS family, or not_recorded")
    architecture: str = meaning("normalized CPU architecture, or not_recorded")
    accelerator_summary: str = meaning("short device summary, or not_recorded")
    safe_host_bytes: str = meaning("SAFE host memory ceiling, or not_recorded")
    safe_accelerator_bytes: str = meaning(
        "SAFE accelerator ceiling for the cited device, or not_recorded"
    )
    capacity_observed_at: str = meaning(
        "when the cited capacity envelope was derived, or not_recorded"
    )
    macropath: str = meaning("selected engine, or not_recorded")
    foundation_generation_id: str = meaning("foundation generation, or not_recorded")
    model_identity: str = meaning("warehouse artifact id or provider digest")
    model_identity_kind: str = meaning(
        "warehouse_artifact, provider_digest, or not_recorded"
    )
    qualification_id: str = meaning("qualification evidence id, or not_recorded")
    qualification_outcome: str = meaning("qualification outcome, or not_recorded")
    plan_id: str = meaning("plan id, or not_recorded")
    reservation_id: str = meaning("reservation id, or not_recorded")
    reservation_state: str = meaning("reserved, released, or not_recorded")
    instance_id: str = meaning("serving instance id, or not_recorded")
    instance_state: str = meaning("instance state, or not_recorded")
    witness_verdict: str = meaning("witness reading of the cited chain")
    witness_reason: str = meaning("why the witness reading was reached")
    physical_register: str = meaning(
        "product qualification register; not a live host status"
    )
    pending_coverage: str = meaning("physical coverage still pending")
    support_events: tuple[SupportEvent, ...] = meaning(
        "bounded operational events without payloads"
    )

    def __post_init__(self) -> None:
        if self.schema_name != SNAPSHOT_SCHEMA:
            raise ValidationError("support snapshot schema name is not Rukan's")
        if self.product_name != "Rukan":
            raise ValidationError("support snapshot product name must be Rukan")
        if self.package_name != "machi":
            raise ValidationError("support snapshot package name must be machi")
        if len(self.support_events) > _EVENT_MAX:
            raise ValidationError("support snapshot has too many events")
        for label, value in (
            ("snapshot", self.snapshot_id),
            ("exported", self.exported_at),
            ("version", self.version),
            ("witness verdict", self.witness_verdict),
            ("witness reason", self.witness_reason),
            ("physical register", self.physical_register),
            ("pending coverage", self.pending_coverage),
        ):
            _token(label, value)
        encoded = to_dict(self)
        reject_customer_content(encoded)


def snapshot_id_for(material: str) -> str:
    """Stable id. The caller supplies the canonical material, not a clock."""
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"snap_{digest}"


def accept_snapshot(document: object) -> SupportSnapshot:
    """Validate an untrusted import. Unknown content fails closed."""
    if not isinstance(document, dict):
        raise ValidationError("support snapshot is not an object")
    if len(json.dumps(document)) > 262_144:
        raise ValidationError("support snapshot is too large")
    reject_customer_content(document)
    loaded = from_dict(document)
    if not isinstance(loaded, SupportSnapshot):
        raise ValidationError("support snapshot kind is not recognised")
    return loaded


def reject_customer_content(document: object) -> None:
    """Fail closed when an export or import carries prohibited keys."""
    if isinstance(document, dict):
        for key, value in document.items():
            if key in FORBIDDEN_PUBLIC_OPS_KEYS or key in _EXTRA_FORBIDDEN:
                raise ValidationError("support snapshot contains a prohibited field")
            reject_customer_content(value)
        return
    if isinstance(document, list | tuple):
        for item in document:
            reject_customer_content(item)


def _token(label: str, value: str) -> None:
    if not value or len(value) > _TOKEN_MAX:
        raise ValidationError(f"support snapshot {label} is empty or too long")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValidationError(f"support snapshot {label} must not contain controls")
