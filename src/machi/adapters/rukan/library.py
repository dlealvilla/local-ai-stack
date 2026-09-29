"""Model library projection. Cards do not invent a second identity."""

from __future__ import annotations

from pathlib import Path

from machi.adapters.rukan.project import project_admin
from machi.adapters.rukan.read import load_records
from machi.kernel.build import BuildIdentity
from machi.kernel.unresolved import is_resolved
from machi.model.contracts import AvailableModels, ModelArtifact, ModelDefinition
from machi.model.provider_candidate import OllamaCatalogCandidate
from machi.model.provider_qualification import OllamaQualificationEvidence

NOT_RECORDED = "not_recorded"


def model_library(store_root: Path, build: BuildIdentity, journal_dir: Path | None) -> dict[str, object]:  # noqa: E501
    """Group exact artifacts. Family is shown only when the catalog stored it."""
    view = project_admin(store_root, build, journal_dir=journal_dir)
    running = view.chain.model_identity if view.chain.instance_state == "ready" else ""
    cards: list[dict[str, str]] = []
    definitions = {
        item.model_id: item
        for item in load_records(store_root, ModelDefinition)
        if isinstance(item, ModelDefinition)
    }
    for artifact in load_records(store_root, ModelArtifact):
        if not isinstance(artifact, ModelArtifact):
            continue
        definition = definitions.get(artifact.model_id)
        cards.append(
            _card(
                identity=artifact.artifact_id,
                kind="warehouse_artifact",
                family=NOT_RECORDED,
                generation=NOT_RECORDED,
                variant=artifact.variant or NOT_RECORDED,
                quantization=definition.quantization.value if definition else NOT_RECORDED,  # noqa: E501
                display_name=definition.display_name if definition else artifact.artifact_id,  # noqa: E501
                lifecycle=artifact.lifecycle.value,
                running=artifact.artifact_id == running,
                compatible=False,
            )
        )
    qualified = {
        item.digest: item
        for item in load_records(store_root, OllamaQualificationEvidence)
        if isinstance(item, OllamaQualificationEvidence)
    }
    for candidate in load_records(store_root, OllamaCatalogCandidate):
        if not isinstance(candidate, OllamaCatalogCandidate):
            continue
        evidence = qualified.get(candidate.digest)
        cards.append(
            _card(
                identity=candidate.digest,
                kind="provider_digest",
                family=_text(candidate.family),
                generation=NOT_RECORDED,
                variant=_text(candidate.quantization_label),
                quantization=_text(candidate.quantization_label),
                display_name=candidate.display_name,
                lifecycle=evidence.outcome.value if evidence else NOT_RECORDED,
                running=candidate.digest == running,
                compatible=evidence is not None and evidence.outcome.value == "pass",
            )
        )
    available = 0
    for snapshot in load_records(store_root, AvailableModels):
        if isinstance(snapshot, AvailableModels):
            available += len(snapshot.entries)
    return {
        "cards": cards,
        "collections": {
            "running": [card["identity"] for card in cards if card["running"] == "true"],  # noqa: E501
            "installed": [
                card["identity"]
                for card in cards
                if card["lifecycle"] in {"stored", "pass"}
            ],
            "compatible": [card["identity"] for card in cards if card["compatible"] == "true"],  # noqa: E501
            "available_count": available,
        },
        "recommended": [],
        "live_claim": False,
    }


def _card(
    *,
    identity: str,
    kind: str,
    family: str,
    generation: str,
    variant: str,
    quantization: str,
    display_name: str,
    lifecycle: str,
    running: bool,
    compatible: bool,
) -> dict[str, str]:
    return {
        "identity": identity,
        "kind": kind,
        "family": family,
        "generation": generation,
        "variant": variant,
        "quantization": quantization,
        "display_name": display_name,
        "lifecycle": lifecycle,
        "running": "true" if running else "false",
        "compatible": "true" if compatible else "false",
    }


def _text(value: object) -> str:
    if is_resolved(value):
        return str(value)
    return NOT_RECORDED
