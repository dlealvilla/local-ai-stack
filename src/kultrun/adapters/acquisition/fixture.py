"""Deterministic acquisition adapter for offline lifecycle tests.

Writes tiny representative files. Same staging/verify/promote contracts.
Not fake inference.
"""

from __future__ import annotations

import json
from pathlib import Path

from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.model.contracts import AcquisitionFailureReason, ModelAcquisitionRequest
from kultrun.model.ports import AcquisitionProviderError, ProviderFetchResult

IDENTITY = Name("fixture")
VERSION = "1.4C.0"
DEFAULT_REVISION = "fixture-rev-1"


class FixtureAcquisitionProvider:
    """Create tiny artifact files without network access."""

    def __init__(self, *, fail: str | None = None) -> None:
        self._fail = fail

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def version(self) -> str:
        return VERSION

    def pin_revision(self, request: ModelAcquisitionRequest) -> str:
        if is_resolved(request.requested_revision) and request.requested_revision:
            return str(request.requested_revision)
        return DEFAULT_REVISION

    def fetch(
        self, request: ModelAcquisitionRequest, staging_dir: Path
    ) -> ProviderFetchResult:
        if self._fail == "network":
            (staging_dir / "partial.bin").write_bytes(b"partial")
            raise AcquisitionProviderError(
                AcquisitionFailureReason.NETWORK_FAILURE.value,
                "fixture network failure",
            )
        if self._fail == "interrupt":
            (staging_dir / "partial.bin").write_bytes(b"partial")
            raise AcquisitionProviderError(
                AcquisitionFailureReason.INTERRUPTED.value,
                "fixture interrupted",
            )
        revision = self.pin_revision(request)
        files = {
            "config.json": json.dumps(
                {
                    "model_type": "fixture",
                    "logical_name": request.logical_name.value,
                    "quantization": (
                        request.quantization
                        if is_resolved(request.quantization)
                        else None
                    ),
                }
            ).encode("utf-8"),
            "tokenizer.json": b"{}",
            "README.md": b"fixture artifact; not a production model\n",
        }
        if self._fail == "corrupt":
            files["weights.bin"] = b""
        else:
            files["weights.bin"] = bytes(range(64))
        written = 0
        names: list[str] = []
        for name, payload in files.items():
            path = staging_dir / name
            path.write_bytes(payload)
            written += len(payload)
            names.append(name)
        return ProviderFetchResult(
            resolved_revision=revision,
            files=tuple(names),
            bytes_written=written,
            integrity_evidence=("fixture:deterministic-bytes",),
        )


def build(*, fail: str | None = None) -> FixtureAcquisitionProvider:
    return FixtureAcquisitionProvider(fail=fail)
