"""Read-only Rukan analytics export. It does not mutate the store or journal."""

from __future__ import annotations

import json
from pathlib import Path

from machi.adapters.journal.jsonl import JOURNAL_FILENAME
from machi.adapters.rukan.project import export_snapshot, project_admin
from machi.adapters.rukan.read import load_records
from machi.kernel.analytics import (
    NOT_RECORDED,
    PRIVACY_POLICY,
    AnalyticsBundle,
    AnalyticsEvent,
    AnalyticsInference,
    AnalyticsManifest,
    bundle_id_for,
    dump_bundle,
)
from machi.kernel.build import BuildIdentity
from machi.kernel.events import EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import from_dict
from machi.kernel.unresolved import is_resolved
from machi.serve.contracts import InferenceProof
from machi.serve.provider import ProviderInferenceProof

_EXPORTABLE = frozenset({PrivacyClass.PUBLIC_OPS, PrivacyClass.OPERATIONAL})


def export_analytics(
    store_root: Path,
    journal_dir: Path | None,
    build: BuildIdentity,
    *,
    exported_at: str,
) -> str:
    """Build one JSONL bundle from persisted facts. No network and no writes."""
    view = project_admin(store_root, build, journal_dir=journal_dir)
    snapshot = export_snapshot(view, exported_at=exported_at, journal_dir=journal_dir)
    events = _events(journal_dir, view.install_id)
    inferences = _inferences(store_root, view.install_id)
    material = "\n".join(
        (
            exported_at,
            view.install_id,
            snapshot.snapshot_id,
            str(len(events)),
            str(len(inferences)),
        )
    )
    manifest = AnalyticsManifest(
        bundle_id=bundle_id_for(material),
        schema_name="rukan.analytics_bundle",
        install_id=view.install_id,
        exported_at=exported_at,
        version=view.version,
        build_id=view.build_id,
        source_commit=view.source_commit,
        privacy_policy=PRIVACY_POLICY,
        snapshot_count=1,
        event_count=len(events),
        inference_count=len(inferences),
    )
    return dump_bundle(AnalyticsBundle(manifest, (snapshot,), tuple(events), tuple(inferences)))  # noqa: E501


def write_analytics(path: Path, text: str) -> None:
    """Write a finished bundle. The caller already validated the text."""
    Path(path).write_text(text, encoding="utf-8")


def _events(journal_dir: Path | None, install_id: str) -> list[AnalyticsEvent]:
    if journal_dir is None:
        return []
    path = Path(journal_dir) / JOURNAL_FILENAME
    if not path.is_file():
        return []
    found: list[AnalyticsEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            document = json.loads(line)
            event = from_dict(document)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(event, EventRecord):
            continue
        if event.privacy not in _EXPORTABLE:
            continue
        found.append(
            AnalyticsEvent(
                event_id=str(event.event_id),
                event_type=str(event.event_type),
                occurred_at=event.occurred_at.isoformat(),
                install_id=_shown(event.install_id, install_id),
                block_id=str(event.block_id),
                component_id=str(event.component_id),
                outcome=str(event.outcome.value),
                privacy=event.privacy.value,
            )
        )
    return found


def _inferences(store_root: Path, install_id: str) -> list[AnalyticsInference]:
    found: list[AnalyticsInference] = []
    for record in load_records(store_root, InferenceProof):
        if not isinstance(record, InferenceProof):
            continue
        tokens = record.completion_tokens
        proven = record.structurally_valid and record.failure.value == "none"
        found.append(
            AnalyticsInference(
                proof_id=record.proof_id,
                install_id=install_id,
                instance_id=record.instance_id,
                plan_id=record.plan_id,
                reservation_id=record.reservation_id,
                generation_id=record.generation_id,
                model_identity=record.artifact_id,
                model_identity_kind="warehouse_artifact",
                request_kind=record.request_kind,
                status_code=record.status_code,
                completion_tokens=str(tokens) if is_resolved(tokens) else NOT_RECORDED,
                structurally_valid=record.structurally_valid,
                failure=record.failure.value,
                outcome="proven" if proven else "failed",
            )
        )
    for record in load_records(store_root, ProviderInferenceProof):
        if not isinstance(record, ProviderInferenceProof):
            continue
        tokens = record.output_tokens
        proven = record.structurally_valid and record.failure.value == "none"
        found.append(
            AnalyticsInference(
                proof_id=record.proof_id,
                install_id=install_id,
                instance_id=record.instance_id,
                plan_id=record.plan_id,
                reservation_id=record.reservation_id,
                generation_id=record.generation_id,
                model_identity=record.digest,
                model_identity_kind="provider_digest",
                request_kind=record.request_kind,
                status_code=0,
                completion_tokens=str(tokens) if is_resolved(tokens) else NOT_RECORDED,
                structurally_valid=record.structurally_valid,
                failure=record.failure.value,
                outcome="proven" if proven else "failed",
            )
        )
    return found


def _shown(value: object, fallback: str) -> str:
    if is_resolved(value):
        return str(value)
    return fallback if fallback else NOT_RECORDED
