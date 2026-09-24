"""Provider-owned catalog candidate. Not a warehouse artifact."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved

_TOKEN_MAX = 80
_HEX = frozenset("0123456789abcdef")


def canonical_digest(value: str) -> str:
    """Sha256 hex. A tag is not accepted as a digest."""
    text = value.strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(character not in _HEX for character in text):
        raise ValidationError("provider digest is not a sha256")
    return text


def candidate_id_for(digest: str) -> str:
    """Identity is the digest. The display name is not an input."""
    token = hashlib.sha256(f"ollama\n{digest}".encode()).hexdigest()
    return f"ocand_{token[:16]}"


@contract(kind="model.ollama_candidate", version=1)
@dataclass(frozen=True, slots=True)
class OllamaCatalogCandidate(Contract):
    """One Ollama catalog entry. Digest is the immutable identity."""

    candidate_id: str = meaning("digest identity; not a warehouse artifact id")
    digest: str = meaning("sha256 of the provider model, without a tag")
    display_name: str = meaning("tag or reference name; not immutable proof")
    size_bytes: Maybe[int] = meaning("published model bytes, or unresolved")
    family: Maybe[str] = meaning("public family label, or unresolved")
    quantization_label: Maybe[str] = meaning("public quant label, or unresolved")
    format_label: Maybe[str] = meaning("public format label, or unresolved")
    context_length: Maybe[int] = meaning("public context when explicit")
    dtype: Maybe[str] = meaning("public dtype when explicit; never guessed")
    layer_count: Maybe[int] = meaning("public layer count when explicit")
    key_value_heads: Maybe[int] = meaning("public kv heads when explicit")
    head_dim: Maybe[int] = meaning("public head dimension when explicit")

    def __post_init__(self) -> None:
        digest = canonical_digest(self.digest)
        object.__setattr__(self, "digest", digest)
        if self.candidate_id != candidate_id_for(digest):
            raise ValidationError("candidate id is not the digest identity")
        _text(self.display_name, what="display name")
        _optional_text(self.family, what="family")
        _optional_text(self.quantization_label, what="quantization")
        _optional_text(self.format_label, what="format")
        _optional_text(self.dtype, what="dtype")
        for label, value in (
            ("size", self.size_bytes),
            ("context", self.context_length),
            ("layers", self.layer_count),
            ("kv heads", self.key_value_heads),
            ("head dim", self.head_dim),
        ):
            if is_resolved(value) and value < 1:
                raise ValidationError(f"{label} must be a positive integer")


def public_candidate(
    *,
    display_name: str,
    digest: str,
    size_bytes: int | None = None,
    family: str | None = None,
    quantization_label: str | None = None,
    format_label: str | None = None,
    context_length: int | None = None,
    dtype: str | None = None,
    layer_count: int | None = None,
    key_value_heads: int | None = None,
    head_dim: int | None = None,
) -> OllamaCatalogCandidate:
    """Normalize public facts. Missing numbers stay unresolved."""
    resolved = canonical_digest(digest)
    return OllamaCatalogCandidate(
        candidate_id=candidate_id_for(resolved),
        digest=resolved,
        display_name=display_name,
        size_bytes=size_bytes if size_bytes is not None else NOT_PROVIDED,
        family=family if family else NOT_PROVIDED,
        quantization_label=(
            quantization_label if quantization_label else NOT_PROVIDED
        ),
        format_label=format_label if format_label else NOT_PROVIDED,
        context_length=(
            context_length if context_length is not None else NOT_PROVIDED
        ),
        dtype=dtype if dtype else NOT_PROVIDED,
        layer_count=layer_count if layer_count is not None else NOT_PROVIDED,
        key_value_heads=(
            key_value_heads if key_value_heads is not None else NOT_PROVIDED
        ),
        head_dim=head_dim if head_dim is not None else NOT_PROVIDED,
    )


def _text(value: str, *, what: str) -> None:
    if not value or len(value) > _TOKEN_MAX:
        raise ValidationError(f"{what} is empty or too long")


def _optional_text(value: Maybe[str], *, what: str) -> None:
    if isinstance(value, str):
        _text(value, what=what)
