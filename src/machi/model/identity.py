"""Stable ids. A branch name is not an artifact id."""

from __future__ import annotations

import hashlib

from machi.model.contracts import ModelSourceKind


def model_id(source: ModelSourceKind, repository: str) -> str:
    digest = hashlib.sha256(f"{source.value}\n{repository}".encode()).hexdigest()
    return f"mdl_{digest[:16]}"


def artifact_id(model: str, revision: str, variant: str) -> str:
    digest = hashlib.sha256(f"{model}\n{revision}\n{variant}".encode()).hexdigest()
    return f"mart_{digest[:16]}"


def input_token(*parts: str) -> str:
    digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return digest[:32]
