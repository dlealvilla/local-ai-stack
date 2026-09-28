"""Rukan analytics bundle. A non-authoritative export, not admission.

JSONL interchange. The first record is the manifest. Later records are
allow-listed projections. Payloads and customer content are absent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, from_dict, meaning, to_dict
from machi.kernel.snapshot import SupportSnapshot, reject_customer_content

BUNDLE_SCHEMA = "rukan.analytics_bundle"
PRIVACY_POLICY = "rukan.analytics.export.1"
NOT_RECORDED = "not_recorded"
_TOKEN_MAX = 240


@contract(kind="kernel.analytics_manifest", version=1)
@dataclass(frozen=True, slots=True)
class AnalyticsManifest(Contract):
    """Identity of one export. Counts must match the following records."""

    bundle_id: str = meaning("deterministic identity of this bundle")
    schema_name: str = meaning("rukan.analytics_bundle")
    install_id: str = meaning("installation this export describes")
    exported_at: str = meaning("when the bundle was written; UTC")
    version: str = meaning("Rukan version when known")
    build_id: str = meaning("build id, or not_recorded")
    source_commit: str = meaning("source commit when known, or not_recorded")
    privacy_policy: str = meaning("export allow-list version")
    snapshot_count: int = meaning("support snapshots in this bundle")
    event_count: int = meaning("event projections in this bundle")
    inference_count: int = meaning("inference projections in this bundle")

    def __post_init__(self) -> None:
        if self.schema_name != BUNDLE_SCHEMA:
            raise ValidationError("analytics bundle schema name is not Rukan's")
        if self.privacy_policy != PRIVACY_POLICY:
            raise ValidationError("analytics privacy policy is not the v1 allow-list")
        for label, value in (
            ("bundle", self.bundle_id),
            ("install", self.install_id),
            ("exported", self.exported_at),
            ("version", self.version),
        ):
            _token(label, value)
        counts = (
            ("snapshots", self.snapshot_count),
            ("events", self.event_count),
            ("inferences", self.inference_count),
        )
        for label, count in counts:
            if count < 0:
                raise ValidationError(f"analytics {label} count is invalid")


@contract(kind="kernel.analytics_event", version=1)
@dataclass(frozen=True, slots=True)
class AnalyticsEvent(Contract):
    """Event envelope. The payload is not part of this projection."""

    event_id: str = meaning("journal event identity")
    event_type: str = meaning("dotted event name")
    occurred_at: str = meaning("UTC timestamp")
    install_id: str = meaning("install id, or not_recorded")
    block_id: str = meaning("emitting block")
    component_id: str = meaning("emitting component")
    outcome: str = meaning("pass, fail, blocked, info, or unresolved")
    privacy: str = meaning("public_ops or operational")

    def __post_init__(self) -> None:
        if self.privacy not in {"public_ops", "operational"}:
            raise ValidationError("analytics event privacy is not exportable")
        for label, value in (
            ("event", self.event_id),
            ("type", self.event_type),
            ("occurred", self.occurred_at),
            ("outcome", self.outcome),
        ):
            _token(label, value)


@contract(kind="kernel.analytics_inference", version=1)
@dataclass(frozen=True, slots=True)
class AnalyticsInference(Contract):
    """Persisted proof facts. No prompt and no generated text."""

    proof_id: str = meaning("proof identity")
    install_id: str = meaning("install id, or not_recorded")
    instance_id: str = meaning("serving instance")
    plan_id: str = meaning("plan")
    reservation_id: str = meaning("reservation")
    generation_id: str = meaning("foundation generation")
    model_identity: str = meaning("artifact id or provider digest")
    model_identity_kind: str = meaning("warehouse_artifact or provider_digest")
    request_kind: str = meaning("protocol request kind")
    status_code: int = meaning("HTTP status when recorded; 0 when the proof has none")
    completion_tokens: str = meaning("reported completion tokens, or not_recorded")
    structurally_valid: bool = meaning("the runtime returned the expected structure")
    failure: str = meaning("typed failure, or none")
    outcome: str = meaning("proven or failed")

    def __post_init__(self) -> None:
        if self.model_identity_kind not in {"warehouse_artifact", "provider_digest"}:
            raise ValidationError("analytics model identity kind is unknown")
        if self.outcome not in {"proven", "failed"}:
            raise ValidationError("analytics inference outcome is unknown")
        if isinstance(self.status_code, bool) or not isinstance(self.status_code, int):
            raise ValidationError("analytics status code is invalid")
        if self.status_code < 0 or self.status_code > 599:
            raise ValidationError("analytics status code is outside 0..599")
        _token("proof", self.proof_id)
        _token("tokens", self.completion_tokens)


@dataclass(frozen=True, slots=True)
class AnalyticsBundle:
    """One validated bundle. Not a second operational store."""

    manifest: AnalyticsManifest
    snapshots: tuple[SupportSnapshot, ...]
    events: tuple[AnalyticsEvent, ...]
    inferences: tuple[AnalyticsInference, ...]


def bundle_id_for(material: str) -> str:
    """Stable id from caller-supplied material."""
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"ban_{digest}"


def dump_bundle(bundle: AnalyticsBundle) -> str:
    """Canonical JSONL. Counts are checked before any bytes are returned."""
    _check_counts(bundle)
    lines = [to_dict(bundle.manifest)]
    lines.extend(to_dict(item) for item in bundle.snapshots)
    lines.extend(to_dict(item) for item in bundle.events)
    lines.extend(to_dict(item) for item in bundle.inferences)
    for line in lines:
        reject_customer_content(line)
        if "payload" in line:
            raise ValidationError("analytics bundle must not carry an event payload")
    return "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines)


def load_bundle(text: str) -> AnalyticsBundle:
    """Validate an untrusted JSONL bundle. A bad line fails the whole file."""
    if len(text) > 2_000_000:
        raise ValidationError("analytics bundle is too large")
    documents = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError("analytics bundle line is not json") from exc
        if not isinstance(document, dict):
            raise ValidationError("analytics bundle line is not an object")
        reject_customer_content(document)
        if "payload" in document:
            raise ValidationError("analytics bundle must not carry an event payload")
        documents.append(document)
    if not documents:
        raise ValidationError("analytics bundle is empty")
    manifest = from_dict(documents[0])
    if not isinstance(manifest, AnalyticsManifest):
        raise ValidationError("analytics bundle does not start with a manifest")
    snapshots: list[SupportSnapshot] = []
    events: list[AnalyticsEvent] = []
    inferences: list[AnalyticsInference] = []
    for document in documents[1:]:
        record = from_dict(document)
        if isinstance(record, SupportSnapshot):
            snapshots.append(record)
        elif isinstance(record, AnalyticsEvent):
            events.append(record)
        elif isinstance(record, AnalyticsInference):
            inferences.append(record)
        else:
            raise ValidationError("analytics bundle contains an unsupported record")
    bundle = AnalyticsBundle(manifest, tuple(snapshots), tuple(events), tuple(inferences))  # noqa: E501
    _check_counts(bundle)
    return bundle


def _check_counts(bundle: AnalyticsBundle) -> None:
    manifest = bundle.manifest
    if manifest.snapshot_count != len(bundle.snapshots):
        raise ValidationError("analytics snapshot count does not match the bundle")
    if manifest.event_count != len(bundle.events):
        raise ValidationError("analytics event count does not match the bundle")
    if manifest.inference_count != len(bundle.inferences):
        raise ValidationError("analytics inference count does not match the bundle")
    for snapshot in bundle.snapshots:
        if snapshot.install_id != manifest.install_id:
            raise ValidationError("analytics snapshot install id does not match")


def _token(label: str, value: str) -> None:
    if not value or len(value) > _TOKEN_MAX:
        raise ValidationError(f"analytics {label} is empty or too long")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValidationError(f"analytics {label} must not contain controls")
