"""Ports for runtime launch and for the serve log. The domain starts nothing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from machi.serve.contracts import InferenceProof, ServeTransition, ServingInstance
from machi.serve.native import NativeProcessEvidence, NativeProcessExit


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    """What a provider needs to start. Paths stay in this request, not the instance."""

    instance_id: str
    evidence_id: str
    python_path: str
    model_path: str
    artifact_id: str
    settings: tuple[tuple[str, str], ...]
    port: int
    stdout_path: Path
    stderr_path: Path
    cwd: str


@dataclass(frozen=True, slots=True)
class InferResult:
    """Structural outcome. No prompt and no generated text."""

    status_code: int
    structurally_valid: bool
    completion_tokens: int | None


class ServeRuntime(Protocol):
    """One serving realization. vLLM is an adapter, not this protocol."""

    provider_name: str
    executor_kind: str

    def launch(self, request: LaunchRequest) -> NativeProcessEvidence:
        """Spawn the runtime and return native evidence."""
        ...

    def ready(self, evidence: NativeProcessEvidence) -> bool:
        """True only when the runtime itself reports ready."""
        ...

    def infer(self, evidence: NativeProcessEvidence, artifact_id: str) -> InferResult:
        """One request. The provider keeps the prompt."""
        ...

    def identity_ok(self, evidence: NativeProcessEvidence) -> bool:
        """True when the pid is still the process we started."""
        ...

    def alive(self, evidence: NativeProcessEvidence) -> bool:
        """True when that process is still running."""
        ...

    def stop(self, evidence: NativeProcessEvidence, *, grace_seconds: float) -> bool:
        """Stop the identified process. True when it is dead."""
        ...

    def returncode(self, evidence: NativeProcessEvidence) -> int | None:
        """Exit status when known."""
        ...


class ServeLog(Protocol):
    """Exclusive creates. Visible lifecycle is an overlay of transitions."""

    def create_instance(self, record: ServingInstance) -> ServingInstance:
        """Store the binding. Identical re-entry returns the stored record."""
        ...

    def create_transition(self, record: ServeTransition) -> ServeTransition:
        """Append one lifecycle step."""
        ...

    def create_evidence(self, record: NativeProcessEvidence) -> NativeProcessEvidence:
        """Store native process evidence."""
        ...

    def create_exit(self, record: NativeProcessExit) -> NativeProcessExit:
        """Store exit evidence once."""
        ...

    def create_proof(self, record: InferenceProof) -> InferenceProof:
        """Store one inference proof."""
        ...

    def instances(self) -> tuple[ServingInstance, ...]:
        """Stored bindings."""
        ...

    def transitions(self) -> tuple[ServeTransition, ...]:
        """Lifecycle steps."""
        ...

    def evidence(self) -> tuple[NativeProcessEvidence, ...]:
        """Native process records."""
        ...

    def exits(self) -> tuple[NativeProcessExit, ...]:
        """Exit records."""
        ...

    def proofs(self) -> tuple[InferenceProof, ...]:
        """Inference proofs."""
        ...
