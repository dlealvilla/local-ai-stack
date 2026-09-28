"""Customer-local analytics. This view is not the vendor export."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from machi.adapters.journal.jsonl import JOURNAL_FILENAME
from machi.adapters.rukan.read import load_records
from machi.kernel.events import EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import from_dict
from machi.kernel.unresolved import is_resolved
from machi.serve.contracts import InferenceProof
from machi.serve.provider import ProviderInferenceProof

_LOCAL = frozenset(
    {PrivacyClass.PUBLIC_OPS, PrivacyClass.OPERATIONAL, PrivacyClass.RESTRICTED}
)


def local_analytics(store_root: Path, journal_dir: Path | None) -> dict[str, object]:
    """Project the local journal and proofs. Customer content stays out."""
    events = _events(journal_dir)
    omitted = _omitted_customer_content(journal_dir)
    proofs = _proofs(store_root)
    by_outcome = Counter(item["outcome"] for item in events)
    lifecycle = Counter(
        item["event_type"]
        for item in events
        if item["event_type"].startswith(("serve.", "admit.", "inference."))
    )
    proven = sum(1 for item in proofs if item["outcome"] == "proven")
    failed = sum(1 for item in proofs if item["outcome"] == "failed")
    reported = [
        int(item["completion_tokens"])
        for item in proofs
        if item["completion_tokens"] != "not_recorded"
    ]
    return {
        "surface": "customer_local",
        "live_claim": False,
        "events_by_outcome": dict(sorted(by_outcome.items())),
        "lifecycle_counts": dict(sorted(lifecycle.items())),
        "timeline": events[-20:],
        "inference_proof_count": len(proofs),
        "inference_proven": proven,
        "inference_failed": failed,
        "completion_tokens_reported": sum(reported) if reported else "not_recorded",
        "completion_tokens_samples": len(reported),
        "omitted_customer_content_events": omitted,
        "missing": [
            "input tokens are not on the native inference proof",
            "request TTFT is not persisted",
            "queue time is not persisted",
            "historical request latency is not persisted",
            "cost, users, and utilization are not persisted",
        ],
    }


def _events(journal_dir: Path | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for event in _read(journal_dir):
        if event.privacy not in _LOCAL:
            continue
        rows.append(
            {
                "event_id": str(event.event_id),
                "event_type": str(event.event_type),
                "occurred_at": event.occurred_at.isoformat(),
                "outcome": str(event.outcome.value),
                "privacy": event.privacy.value,
                "block_id": str(event.block_id),
            }
        )
    return rows


def _omitted_customer_content(journal_dir: Path | None) -> int:
    return sum(
        1 for event in _read(journal_dir) if event.privacy is PrivacyClass.CUSTOMER_CONTENT  # noqa: E501
    )


def _read(journal_dir: Path | None) -> list[EventRecord]:
    if journal_dir is None:
        return []
    path = Path(journal_dir) / JOURNAL_FILENAME
    if not path.is_file():
        return []
    found: list[EventRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            document = json.loads(line)
            event = from_dict(document)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(event, EventRecord):
            found.append(event)
    return found


def _proofs(store_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in load_records(store_root, InferenceProof):
        if not isinstance(record, InferenceProof):
            continue
        tokens = record.completion_tokens
        proven = record.structurally_valid and record.failure.value == "none"
        rows.append(
            {
                "proof_id": record.proof_id,
                "model_identity": record.artifact_id,
                "outcome": "proven" if proven else "failed",
                "failure": record.failure.value,
                "completion_tokens": str(tokens) if is_resolved(tokens) else "not_recorded",  # noqa: E501
            }
        )
    for record in load_records(store_root, ProviderInferenceProof):
        if not isinstance(record, ProviderInferenceProof):
            continue
        tokens = record.output_tokens
        proven = record.structurally_valid and record.failure.value == "none"
        rows.append(
            {
                "proof_id": record.proof_id,
                "model_identity": record.digest,
                "outcome": "proven" if proven else "failed",
                "failure": record.failure.value,
                "completion_tokens": str(tokens) if is_resolved(tokens) else "not_recorded",  # noqa: E501
            }
        )
    return rows
