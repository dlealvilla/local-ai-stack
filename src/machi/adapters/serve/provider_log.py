"""Persist provider serve records through the shared file store."""

from __future__ import annotations

from typing import TypeVar

from machi.adapters.persistence.file_store import FileStore
from machi.kernel.errors import ValidationError
from machi.serve.contracts import ServeTransition
from machi.serve.provider import ProviderInferenceProof, ProviderServingInstance


class StoreProviderServeLog:
    """Exclusive creates for the Ollama serve path."""

    def __init__(self, store: FileStore) -> None:
        self._store = store

    def create_instance(
        self, record: ProviderServingInstance
    ) -> ProviderServingInstance:
        return _created(self._store, record.instance_id, record)

    def create_transition(self, record: ServeTransition) -> ServeTransition:
        return _created(self._store, record.transition_id, record)

    def create_proof(self, record: ProviderInferenceProof) -> ProviderInferenceProof:
        return _created(self._store, record.proof_id, record)

    def instances(self) -> tuple[ProviderServingInstance, ...]:
        return _read(self._store, ProviderServingInstance)

    def transitions(self) -> tuple[ServeTransition, ...]:
        return _read(self._store, ServeTransition)

    def proofs(self) -> tuple[ProviderInferenceProof, ...]:
        return _read(self._store, ProviderInferenceProof)


RecordT = TypeVar(
    "RecordT", ProviderServingInstance, ServeTransition, ProviderInferenceProof
)


def _created(store: FileStore, key: str, record: RecordT) -> RecordT:
    stored = store.create(key, record).record
    if not isinstance(stored, type(record)):
        raise ValidationError("store returned an unexpected provider serve record")
    return stored


def _read(store: FileStore, contract_type: type[RecordT]) -> tuple[RecordT, ...]:
    directory = store.root / contract_type.kind
    if not directory.is_dir():
        return ()
    found: list[RecordT] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            found.append(store.get(contract_type, path.stem))
        except (ValidationError, OSError):
            continue
    return tuple(found)
