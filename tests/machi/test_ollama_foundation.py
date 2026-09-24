"""Ollama runtime substrate. Fixtures only: no weights and no inference."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import socket
import tarfile
from dataclasses import replace
from pathlib import Path

from tests.machi.test_plan import _capability, _foundation, _inputs, _plan

from machi.adapters.foundation.ollama_runtime import (
    InstalledPrefix,
    OllamaRuntime,
    PrefixRefusal,
    daemon_environment,
)
from machi.foundation.contracts import (
    FailureCode,
    FeatureState,
    FoundationEngine,
    SupportState,
)
from machi.foundation.ollama import (
    CloudMode,
    ExistingOllamaObservation,
    MetricAvailability,
    OllamaAssessment,
    OllamaProviderMode,
    OllamaRuntimeRecipe,
    OllamaSubstrate,
    assess_existing,
    channel_refusal,
    ollama_generation_id,
    pinned_recipe,
)
from machi.kernel.schema import from_dict, to_dict
from machi.model.qualification import qualification_identity
from machi.plan.contracts import PlanFailure

FIXED = dt.datetime(2026, 9, 24, 3, 0, tzinfo=dt.UTC)
FINGERPRINT = "exe_" + ("ab" * 16)
CAPACITY = "cap_ollama_fixture"
_FIXTURE = """#!/usr/bin/env python3
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if "--version" in sys.argv:
    sys.stdout.write("0.34.3\\n")
    raise SystemExit(0)
if os.environ.get("OLLAMA_NO_CLOUD") != "1":
    raise SystemExit(2)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] != "/api/version":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"version": "0.34.3"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return

class Server(ThreadingHTTPServer):
    allow_reuse_address = True

raw = os.environ["OLLAMA_HOST"]
host, port = raw.rsplit(":", 1)
Server((host, int(port)), Handler).serve_forever()
"""


def _archive(*extra: tuple[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as handle:
        payload = _FIXTURE.encode()
        info = tarfile.TarInfo("bin/ollama")
        info.size = len(payload)
        info.mode = 0o755
        handle.addfile(info, io.BytesIO(payload))
        library = tarfile.TarInfo("lib/ollama")
        library.type = tarfile.DIRTYPE
        library.mode = 0o755
        handle.addfile(library)
        marker = b"layout"
        keep = tarfile.TarInfo("lib/ollama/cuda_v12.keep")
        keep.size = len(marker)
        handle.addfile(keep, io.BytesIO(marker))
        for name, body in extra:
            member = tarfile.TarInfo(name)
            member.size = len(body)
            handle.addfile(member, io.BytesIO(body))
    return buffer.getvalue()


def _recipe(archive: bytes, *, version: str = "0.34.3") -> OllamaRuntimeRecipe:
    return OllamaRuntimeRecipe(
        recipe_id=f"ollama-{version}-fixture",
        version=version,
        artifact_name="fixture.tar",
        artifact_sha256=hashlib.sha256(archive).hexdigest(),
        artifact_bytes=len(archive),
        source_url=(
            "https://github.com/ollama/ollama/releases/download/v0.34.3/fixture.tar"
        ),
        checksum_url=(
            "https://github.com/ollama/ollama/releases/download/v0.34.3/sha256sum.txt"
        ),
        license_name="MIT",
        stable=True,
    )


def _observation(**overrides: object) -> ExistingOllamaObservation:
    fields: dict[str, object] = {
        "identified_by": "executed_binary",
        "executable_path": "/opt/local/bin/ollama",
        "version_text": "ollama version is 0.34.3",
        "endpoint": "http://127.0.0.1:11434",
        "api_version": "0.34.3",
        "cloud_disabled": True,
        "auto_update": False,
        "binary_sha256": None,
    }
    fields.update(overrides)
    return ExistingOllamaObservation(**fields)  # type: ignore[arg-type]


def _assess(**overrides: object) -> OllamaAssessment:
    return assess_existing(
        _observation(**overrides),
        pinned_recipe(),
        execution_environment_fingerprint=FINGERPRINT,
        capacity_evidence_id=CAPACITY,
        observed_at=FIXED,
        verify_seconds=0.01,
    )


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_pinned_release_is_the_frozen_stable_artifact() -> None:
    recipe = pinned_recipe()
    assert recipe.version == "0.34.3"
    assert recipe.stable is True
    assert recipe.artifact_sha256 == (
        "e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9"
    )
    assert recipe.artifact_name == "ollama-linux-amd64.tar.zst"
    assert channel_refusal(tag="v0.34.3", prerelease=False, draft=False) is None


def test_prerelease_and_unpinned_stable_tags_are_refused() -> None:
    assert channel_refusal(tag="v0.34.3", prerelease=True, draft=False)
    assert channel_refusal(tag="v0.34.3-rc1", prerelease=False, draft=False)
    assert channel_refusal(tag="v0.99.0", prerelease=False, draft=False)
    assert channel_refusal(tag="v0.34.3", prerelease=False, draft=True)


def test_verified_existing_exact_version_round_trips() -> None:
    assessment = _assess()
    assert assessment.failure is FailureCode.NONE
    substrate = assessment.substrate
    assert substrate is not None
    restored = from_dict(to_dict(substrate))
    assert isinstance(restored, OllamaSubstrate)
    assert restored.selection.engine is FoundationEngine.OLLAMA
    assert restored.capability.engine is FoundationEngine.OLLAMA
    assert restored.capability.server_launch is FeatureState.UNSUPPORTED
    assert restored.capability.version == "0.34.3"
    assert restored.generation.cloud_mode is CloudMode.DISABLED
    assert "model residency is not claimed" in assessment.reason
    names = {item.name: item for item in restored.metrics.metrics}
    assert names["foundation.engine"].value == "ollama"
    assert names["cloud.mode"].availability is MetricAvailability.OBSERVED
    assert (
        names["install.footprint_bytes"].availability is MetricAvailability.UNRESOLVED
    )
    assert names["artifact.sha256"].availability is MetricAvailability.UNRESOLVED


def test_wrong_version_prerelease_bind_cloud_and_identity_are_refused() -> None:
    wrong = _assess(version_text="ollama version is 0.33.0")
    assert wrong.failure is FailureCode.VERIFICATION_FAILED
    preview = _assess(version_text="0.34.3-rc1")
    assert preview.support is SupportState.UNSUPPORTED
    public = _assess(endpoint="http://0.0.0.0:11434")
    assert public.failure is FailureCode.VERIFICATION_FAILED
    enabled = _assess(cloud_disabled=False)
    assert enabled.reason == "cloud is enabled"
    unknown = _assess(cloud_disabled=None)
    assert unknown.reason == "cloud mode is unresolved"
    down = _assess(api_version=None)
    assert down.reason == "daemon api is unavailable"
    mismatch = _assess(api_version="0.34.2")
    assert mismatch.reason == "daemon version does not match the executable"
    for identified in ("process_name", "systemd_unit", "container_tag", "path_entry"):
        refused = _assess(identified_by=identified)
        assert refused.substrate is None
    bare = _assess(executable_path="ollama")
    assert bare.substrate is None
    moving = _assess(auto_update=True)
    assert "auto-update" in moving.reason


def _qualification(generation_id: str) -> str:
    return qualification_identity(
        revision="digest",
        generation_id=generation_id,
        engine="ollama",
        engine_version="0.34.3",
        backend="cuda",
        hardware_class="cc-8.9",
        execution_environment_fingerprint=FINGERPRINT,
        dtype="bfloat16",
        quantization="none",
        context=4096,
        concurrency=1,
        tensor_parallel=1,
        policy_version="m6.qualify.1",
    )


def test_generation_change_changes_qualification_identity() -> None:
    current = ollama_generation_id(
        recipe_id="ollama-0.34.3-linux-amd64",
        provider_mode=OllamaProviderMode.VERIFIED_EXISTING,
        version="0.34.3",
        artifact_sha256="unresolved",
        execution_environment_fingerprint=FINGERPRINT,
        cloud_mode=CloudMode.DISABLED,
        endpoint="http://127.0.0.1:11434",
    )
    shifted = ollama_generation_id(
        recipe_id="ollama-0.34.3-linux-amd64",
        provider_mode=OllamaProviderMode.MANAGED_PREFIX,
        version="0.34.3",
        artifact_sha256="unresolved",
        execution_environment_fingerprint=FINGERPRINT,
        cloud_mode=CloudMode.DISABLED,
        endpoint="http://127.0.0.1:11434",
    )
    assert current != shifted
    assert _qualification(current) != _qualification(shifted)


def test_plan_does_not_accept_the_ollama_engine() -> None:
    foundation = _foundation(engine=FoundationEngine.OLLAMA)
    capability = replace(
        _capability(), engine=FoundationEngine.OLLAMA, version="0.34.3"
    )
    decision = _plan(_inputs(foundation=foundation, capability=capability))
    assert decision.failure is PlanFailure.FOUNDATION_NOT_READY


def test_checksum_mismatch_does_not_extract(tmp_path: Path) -> None:
    sentinel = tmp_path / "outside"
    sentinel.mkdir()
    (sentinel / "keep").write_text("stay", encoding="utf-8")
    refused = OllamaRuntime().install(tmp_path / "state", _archive(), pinned_recipe())
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.PACKAGE_DOWNLOAD_FAILED
    assert (sentinel / "keep").read_text(encoding="utf-8") == "stay"
    assert not (tmp_path / "state").exists()


def test_escape_and_short_storage_do_not_leave_a_prefix(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    escaped = _archive(("../escaped", b"nope"))
    refused = OllamaRuntime().install(tmp_path / "state", escaped, _recipe(escaped))
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.PACKAGE_INSTALL_FAILED
    assert not (outside / "escaped").exists()
    assert not any((tmp_path / "state").rglob("bin/ollama"))
    archive = _archive()
    short = OllamaRuntime().install(
        tmp_path / "state",
        archive,
        _recipe(archive),
        safe_bytes=1,
    )
    assert isinstance(short, PrefixRefusal)
    assert short.failure is FailureCode.PACKAGE_INSTALL_FAILED
    assert not any((tmp_path / "state").rglob("bin/ollama"))


def test_managed_prefix_verifies_restarts_and_stops(tmp_path: Path) -> None:
    archive = _archive()
    recipe = _recipe(archive)
    runtime = OllamaRuntime()
    state = tmp_path / "state"
    installed = runtime.install(state, archive, recipe)
    assert isinstance(installed, InstalledPrefix)
    again = runtime.install(state, archive, recipe)
    assert isinstance(again, InstalledPrefix)
    assert again.environment_id == installed.environment_id
    prefix = installed.prefix
    assert (prefix / "bin" / "ollama").is_file()
    assert (prefix / "lib" / "ollama").is_dir()
    assert list((prefix / "models").iterdir()) == []
    config = json.loads((prefix / "config" / "server.json").read_text(encoding="utf-8"))
    assert config["disable_ollama_cloud"] is True
    env = daemon_environment(prefix, 11434)
    assert env["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert env["OLLAMA_NO_CLOUD"] == "1"
    assert "OLLAMA_API_KEY" not in env
    assert str(prefix) in env["OLLAMA_MODELS"]
    started = runtime.start(
        prefix,
        port=_port(),
        recipe=recipe,
        execution_environment_fingerprint=FINGERPRINT,
        capacity_evidence_id=CAPACITY,
        footprint_bytes=installed.footprint_bytes,
        install_seconds=installed.install_seconds,
    )
    try:
        assert started.failure is FailureCode.NONE
        substrate = started.substrate
        assert substrate is not None
        assert substrate.capability.server_launch is FeatureState.UNSUPPORTED
        names = {item.name: item for item in substrate.metrics.metrics}
        assert names["provider.mode"].value == "managed_prefix"
        assert (
            names["install.footprint_bytes"].availability is MetricAvailability.OBSERVED
        )
        assert (
            names["daemon.startup_seconds"].availability is MetricAvailability.OBSERVED
        )
        restarted = runtime.restart()
        assert restarted.failure is FailureCode.NONE
        assert restarted.substrate is not None
        assert restarted.substrate.generation.generation_id == (
            substrate.generation.generation_id
        )
    finally:
        assert runtime.stop() == "stopped"
    assert list((prefix / "models").iterdir()) == []
