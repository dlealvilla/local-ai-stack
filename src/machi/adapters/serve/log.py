"""Read and create serve records through the existing file store."""

from __future__ import annotations

from typing import TypeVar

from machi.adapters.persistence.file_store import FileStore
from machi.kernel.errors import ValidationError
from machi.serve.contracts import InferenceProof, ServeTransition, ServingInstance
from machi.serve.native import NativeProcessEvidence, NativeProcessExit


class StoreServeLog:
    """Exclusive creates. A bad file is skipped, not repaired."""

    def __init__(self, store: FileStore) -> None:
        self._store = store

    def create_instance(self, record: ServingInstance) -> ServingInstance:
        return _created(self._store, record.instance_id, record)

    def create_transition(self, record: ServeTransition) -> ServeTransition:
        return _created(self._store, record.transition_id, record)

    def create_evidence(self, record: NativeProcessEvidence) -> NativeProcessEvidence:
        return _created(self._store, record.evidence_id, record)

    def create_exit(self, record: NativeProcessExit) -> NativeProcessExit:
        return _created(self._store, record.exit_id, record)

    def create_proof(self, record: InferenceProof) -> InferenceProof:
        return _created(self._store, record.proof_id, record)

    def instances(self) -> tuple[ServingInstance, ...]:
        return _read(self._store, ServingInstance)

    def transitions(self) -> tuple[ServeTransition, ...]:
        return _read(self._store, ServeTransition)

    def evidence(self) -> tuple[NativeProcessEvidence, ...]:
        return _read(self._store, NativeProcessEvidence)

    def exits(self) -> tuple[NativeProcessExit, ...]:
        return _read(self._store, NativeProcessExit)

    def proofs(self) -> tuple[InferenceProof, ...]:
        return _read(self._store, InferenceProof)


RecordT = TypeVar(
    "RecordT",
    ServingInstance,
    ServeTransition,
    NativeProcessEvidence,
    NativeProcessExit,
    InferenceProof,
)


def _created(store: FileStore, key: str, record: RecordT) -> RecordT:
    stored = store.create(key, record).record
    if not isinstance(stored, type(record)):
        raise ValidationError("store returned an unexpected serve record")
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
