"""Ollama runtime substrate. Fixtures only: no weights and no inference."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import socket
import subprocess
import sys
import tarfile
from dataclasses import replace
from pathlib import Path

from tests.machi.test_plan import _capability, _foundation, _inputs, _plan

from machi.adapters.foundation.ollama_runtime import (
    InstalledPrefix,
    InstallFaults,
    OllamaRuntime,
    PrefixRefusal,
    SystemZstdDecompressor,
    daemon_environment,
    unregistered_owned_generations,
)
from machi.foundation.contracts import (
    FailureCode,
    FeatureState,
    FoundationEngine,
    SupportState,
)
from machi.foundation.metrics import MetricAvailability
from machi.foundation.ollama import (
    CloudMode,
    ExistingOllamaObservation,
    OllamaAssessment,
    OllamaProviderMode,
    OllamaRuntimeRecipe,
    OllamaSubstrate,
    assess_existing,
    channel_refusal,
    ollama_generation_id,
    pinned_recipe,
    runtime_environment_id,
)
from machi.kernel.schema import from_dict, to_dict
from machi.model.qualification import qualification_identity
from machi.plan.contracts import PlanFailure

FIXED = dt.datetime(2026, 9, 24, 3, 0, tzinfo=dt.UTC)
FINGERPRINT = "exe_" + ("ab" * 16)
CAPACITY = "cap_ollama_fixture"
SAFE_BYTES = 2_000_000
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


def _linked_archive() -> bytes:
    buffer = io.BytesIO()
    payload = _archive()
    with tarfile.open(fileobj=buffer, mode="w") as handle:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as source:
            for member in source.getmembers():
                extracted = source.extractfile(member)
                handle.addfile(member, extracted)
        link = tarfile.TarInfo("bin/escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "../outside"
        handle.addfile(link)
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


def _file(directory: Path, data: bytes, name: str = "artifact.tar") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(data)
    return target


def _zst(directory: Path, data: bytes, name: str = "artifact.tar.zst") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    subprocess.run(
        ["zstd", "-q", "-f", "-o", str(target)],
        input=data,
        check=True,
    )
    return target


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
    assert restored.generation.qualification_reusable is False
    assert restored.generation.identity_strength == "absent"
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
        content_sha256="ab" * 32,
        identity_strength="runtime_closure",
        execution_environment_fingerprint=FINGERPRINT,
        security_class="loopback_cloud_disabled",
    )
    shifted = ollama_generation_id(
        recipe_id="ollama-0.34.3-linux-amd64",
        provider_mode=OllamaProviderMode.MANAGED_PREFIX,
        version="0.34.3",
        content_sha256="ab" * 32,
        identity_strength="archive",
        execution_environment_fingerprint=FINGERPRINT,
        security_class="loopback_cloud_disabled",
    )
    same_port = ollama_generation_id(
        recipe_id="ollama-0.34.3-linux-amd64",
        provider_mode=OllamaProviderMode.VERIFIED_EXISTING,
        version="0.34.3",
        content_sha256="ab" * 32,
        identity_strength="runtime_closure",
        execution_environment_fingerprint=FINGERPRINT,
        security_class="loopback_cloud_disabled",
    )
    changed_bytes = ollama_generation_id(
        recipe_id="ollama-0.34.3-linux-amd64",
        provider_mode=OllamaProviderMode.VERIFIED_EXISTING,
        version="0.34.3",
        content_sha256="cd" * 32,
        identity_strength="runtime_closure",
        execution_environment_fingerprint=FINGERPRINT,
        security_class="loopback_cloud_disabled",
    )
    assert current != shifted
    assert current == same_port
    assert current != changed_bytes
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
    payload = _archive()
    refused = OllamaRuntime().install(
        tmp_path / "state",
        _file(tmp_path, payload, "mismatch.tar"),
        pinned_recipe(),
        safe_bytes=SAFE_BYTES,
    )
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.PACKAGE_DOWNLOAD_FAILED
    assert (sentinel / "keep").read_text(encoding="utf-8") == "stay"
    assert not any((tmp_path / "state").rglob("bin/ollama"))
    staging = tmp_path / "state" / "foundation" / "staging"
    assert not staging.exists()


def test_escape_and_short_storage_do_not_leave_a_prefix(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    escaped = _archive(("../escaped", b"nope"))
    refused = OllamaRuntime().install(
        tmp_path / "state",
        _file(tmp_path, escaped, "escape.tar"),
        _recipe(escaped),
        safe_bytes=SAFE_BYTES,
    )
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.PACKAGE_INSTALL_FAILED
    assert not (outside / "escaped").exists()
    assert not any((tmp_path / "state").rglob("bin/ollama"))
    archive = _archive()
    short = OllamaRuntime().install(
        tmp_path / "state",
        _file(tmp_path, archive, "short.tar"),
        _recipe(archive),
        safe_bytes=1,
    )
    assert isinstance(short, PrefixRefusal)
    assert short.failure is FailureCode.INSUFFICIENT_CAPACITY
    assert not any((tmp_path / "state").rglob("bin/ollama"))


def test_managed_prefix_verifies_restarts_and_stops(tmp_path: Path) -> None:
    archive = _archive()
    recipe = _recipe(archive)
    runtime = OllamaRuntime()
    state = tmp_path / "state"
    archive_path = _file(tmp_path, archive, "incoming.tar")
    installed = runtime.install(state, archive_path, recipe, safe_bytes=SAFE_BYTES)
    assert isinstance(installed, InstalledPrefix)
    again = runtime.install(state, archive_path, recipe, safe_bytes=SAFE_BYTES)
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
        assert substrate.generation.qualification_reusable is True
        assert substrate.generation.identity_strength == "archive"
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


def test_delivery_url_is_not_the_artifact_identity(tmp_path: Path) -> None:
    archive = _archive()
    path = _file(tmp_path, archive, "local.tar")
    upstream = _recipe(archive)
    mirror = replace(upstream, source_url="offline-bundle:customer")
    assert runtime_environment_id(upstream) == runtime_environment_id(mirror)
    installed = OllamaRuntime().install(
        tmp_path / "state", path, mirror, safe_bytes=SAFE_BYTES
    )
    assert isinstance(installed, InstalledPrefix)
    assert installed.environment_id == runtime_environment_id(upstream)


def test_zst_realization_rejects_bad_archives_without_touching_active(
    tmp_path: Path,
) -> None:
    compressed = _zst(tmp_path, _archive(), "good.tar.zst")
    recipe = _recipe(compressed.read_bytes())
    state = tmp_path / "state"
    installed = OllamaRuntime().install(
        state, compressed, recipe, safe_bytes=SAFE_BYTES
    )
    assert isinstance(installed, InstalledPrefix)
    marker = installed.prefix / "lib" / "ollama" / "cuda_v12.keep"
    marker.write_bytes(b"keep-me")
    mismatch = _file(tmp_path, b"not-the-archive", "bad.bin")
    refused = OllamaRuntime().install(
        state, mismatch, recipe, safe_bytes=SAFE_BYTES
    )
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.PACKAGE_DOWNLOAD_FAILED
    assert marker.read_bytes() == b"keep-me"
    escaped = _zst(tmp_path, _archive(("../escaped", b"nope")), "escape.tar.zst")
    escaped_result = OllamaRuntime().install(
        state, escaped, _recipe(escaped.read_bytes()), safe_bytes=SAFE_BYTES
    )
    assert isinstance(escaped_result, PrefixRefusal)
    assert escaped_result.reason == "archive member escapes the prefix"
    linked = _zst(tmp_path, _linked_archive(), "link.tar.zst")
    linked_result = OllamaRuntime().install(
        state, linked, _recipe(linked.read_bytes()), safe_bytes=SAFE_BYTES
    )
    assert isinstance(linked_result, PrefixRefusal)
    assert linked_result.reason == "archive links are refused"
    bounded = OllamaRuntime().install(
        tmp_path / "bounded",
        compressed,
        recipe,
        safe_bytes=1,
    )
    assert isinstance(bounded, PrefixRefusal)
    assert bounded.failure is FailureCode.INSUFFICIENT_CAPACITY
    assert not (state / "foundation" / "staging").exists()
    assert not (tmp_path / "bounded" / "foundation" / "staging").exists()
    assert marker.read_bytes() == b"keep-me"
    assert not any((tmp_path / "bounded").rglob("bin/ollama"))


def test_missing_safe_bytes_refuses(tmp_path: Path) -> None:
    archive = _archive()
    refused = OllamaRuntime().install(
        tmp_path / "state",
        _file(tmp_path, archive),
        _recipe(archive),
    )
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.INSUFFICIENT_CAPACITY
    assert not (tmp_path / "state" / "foundation" / "environments").exists()


def test_two_pass_zstd_and_transaction_faults(tmp_path: Path) -> None:
    compressed = _zst(tmp_path, _archive(), "twice.tar.zst")
    recipe = _recipe(compressed.read_bytes())

    class Counting(SystemZstdDecompressor):
        def __init__(self) -> None:
            super().__init__()
            self.opens = 0

        def open_stream(self, source: Path):
            self.opens += 1
            return super().open_stream(source)

    counter = Counting()
    installed = OllamaRuntime().install(
        tmp_path / "state",
        compressed,
        recipe,
        safe_bytes=SAFE_BYTES,
        decompressor=counter,
    )
    assert isinstance(installed, InstalledPrefix)
    assert counter.opens == 2
    archive_source = Path("src/machi/adapters/foundation/ollama_archive.py")
    assert "payload.tar" not in archive_source.read_text(encoding="utf-8")
    kept = (installed.prefix / "lib" / "ollama" / "cuda_v12.keep").read_bytes()
    other = _zst(
        tmp_path,
        _archive(("lib/ollama/extra.keep", b"x")),
        "other.tar.zst",
    )
    promoted = OllamaRuntime().install(
        tmp_path / "state",
        other,
        _recipe(other.read_bytes()),
        safe_bytes=SAFE_BYTES,
        faults=InstallFaults(registry_fault="replace"),
    )
    assert isinstance(promoted, PrefixRefusal)
    assert promoted.failure is FailureCode.PROMOTED_UNREGISTERED
    assert promoted.support is SupportState.RECONCILE_REQUIRED
    assert promoted.environment_id in unregistered_owned_generations(tmp_path / "state")
    assert kept == (installed.prefix / "lib" / "ollama" / "cuda_v12.keep").read_bytes()
    blocked = OllamaRuntime().install(
        tmp_path / "promote",
        compressed,
        recipe,
        safe_bytes=SAFE_BYTES,
        faults=InstallFaults(fail_promote=True),
    )
    assert isinstance(blocked, PrefixRefusal)
    assert blocked.failure is FailureCode.PACKAGE_INSTALL_FAILED
    assert not (tmp_path / "promote" / "foundation" / "environments").exists()


def test_runtime_closure_identity_changes_with_bytes(tmp_path: Path) -> None:
    from machi.adapters.foundation.ollama_archive import observe_runtime_identity

    root = tmp_path / "runtime"
    binary = root / "bin" / "ollama"
    library = root / "lib" / "ollama" / "runner"
    library.parent.mkdir(parents=True)
    binary.parent.mkdir()
    binary.write_bytes(b"executable-v1")
    library.write_bytes(b"library-v1")
    first, strength = observe_runtime_identity(binary)
    assert strength == "runtime_closure"
    library.write_bytes(b"library-v2")
    second, _again = observe_runtime_identity(binary)
    assert first != second
    lone = tmp_path / "only-exe" / "ollama"
    lone.parent.mkdir()
    lone.write_bytes(b"exe")
    _digest, partial = observe_runtime_identity(lone)
    assert partial == "partial_executable"


def test_same_runtime_on_two_ports_keeps_qualification_identity() -> None:
    shared = {
        "runtime_identity_sha256": "ab" * 32,
        "identity_strength": "runtime_closure",
    }
    first = _assess(endpoint="http://127.0.0.1:11434", **shared)
    second = _assess(endpoint="http://127.0.0.1:11435", **shared)
    assert first.substrate is not None
    assert second.substrate is not None
    assert (
        first.substrate.generation.generation_id
        == second.substrate.generation.generation_id
    )
    assert first.substrate.generation.qualification_reusable is True
    assert first.substrate.generation.endpoint != second.substrate.generation.endpoint


def test_missing_zstd_is_a_prerequisite_refusal(tmp_path: Path) -> None:
    compressed = _zst(tmp_path, _archive(), "needs-zstd.tar.zst")
    recipe = _recipe(compressed.read_bytes())

    class Missing(SystemZstdDecompressor):
        def preflight(self):
            return PrefixRefusal(
                FailureCode.PREREQUISITE_BLOCKED,
                SupportState.BLOCKED_BY_PREREQUISITE,
                "zstd decompressor is not available",
            )

    refused = OllamaRuntime().install(
        tmp_path / "state",
        compressed,
        recipe,
        safe_bytes=SAFE_BYTES,
        decompressor=Missing(),
    )
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.PREREQUISITE_BLOCKED


def test_registry_faults_leave_the_generation_for_reconciliation(
    tmp_path: Path,
) -> None:
    raw = _archive(("lib/ollama/marker", b"m"))
    for fault in ("temp", "write", "fsync"):
        root = tmp_path / fault
        compressed = _zst(root, raw, "fault.tar.zst")
        recipe = _recipe(compressed.read_bytes())
        result = OllamaRuntime().install(
            root / "state",
            compressed,
            recipe,
            safe_bytes=SAFE_BYTES,
            faults=InstallFaults(registry_fault=fault),
        )
        assert isinstance(result, PrefixRefusal)
        assert result.failure is FailureCode.PROMOTED_UNREGISTERED
        assert result.environment_id in unregistered_owned_generations(root / "state")


def test_aggregate_size_is_not_the_per_member_ceiling() -> None:
    from machi.adapters.foundation.ollama_archive import (
        _MAX_MEMBER,
        generated_metadata_budget,
        individual_member_refusal,
        provisioning_peak,
    )

    half = _MAX_MEMBER // 2 + 1
    assert half <= _MAX_MEMBER
    assert half + half > _MAX_MEMBER
    assert individual_member_refusal(half) is None
    assert individual_member_refusal(_MAX_MEMBER + 1) is not None
    peak = provisioning_peak(
        staged_bytes=32,
        declared_bytes=half + half,
        metadata_bytes=generated_metadata_budget(),
        registry_temp_bytes=64,
    )
    assert peak > 1_000
    small_peak = provisioning_peak(
        staged_bytes=32,
        declared_bytes=100,
        metadata_bytes=generated_metadata_budget(),
        registry_temp_bytes=64,
    )
    assert small_peak < SAFE_BYTES


def test_registry_temp_bytes_are_part_of_the_safe_peak(tmp_path: Path) -> None:
    from machi.adapters.foundation.ollama_archive import (
        generated_metadata_budget,
        projected_registry_temp_bytes,
        provisioning_peak,
    )

    archive = _archive()
    path = _file(tmp_path, archive, "small.tar")
    recipe = _recipe(archive)
    environment_id = runtime_environment_id(recipe)
    identifiers = [f"renv_{index:05d}_{'x' * 40}" for index in range(1500)]
    registry_temp = projected_registry_temp_bytes(identifiers, environment_id)
    assert registry_temp > 65_536
    with tarfile.open(path, "r:") as handle:
        declared = sum(member.size for member in handle.getmembers() if member.isfile())
    metadata = generated_metadata_budget()
    staged = path.stat().st_size
    peak = provisioning_peak(
        staged_bytes=staged,
        declared_bytes=declared,
        metadata_bytes=metadata,
        registry_temp_bytes=registry_temp,
    )
    state = tmp_path / "state"
    directory = state / "foundation" / "environments"
    directory.mkdir(parents=True)
    registry = directory / "registry.json"
    registry.write_text(
        json.dumps(identifiers, indent=2) + "\n",
        encoding="utf-8",
    )
    original = registry.read_bytes()
    short = OllamaRuntime().install(
        state,
        path,
        recipe,
        safe_bytes=peak - 1,
    )
    assert isinstance(short, PrefixRefusal)
    assert short.failure is FailureCode.INSUFFICIENT_CAPACITY
    assert registry.read_bytes() == original
    installed = OllamaRuntime().install(
        state,
        path,
        recipe,
        safe_bytes=peak,
    )
    assert isinstance(installed, InstalledPrefix)


def test_nonzero_decompressor_exit_fails_provisioning(tmp_path: Path) -> None:
    from machi.adapters.foundation.ollama_archive import DecompressorEvidence

    tar_bytes = _archive()
    tar_path = _file(tmp_path, tar_bytes, "layout.tar")
    staged = _file(tmp_path, b"\x28\xb5\x2f\xfdnot-zstd", "fake.tar.zst")
    recipe = _recipe(staged.read_bytes())

    class FailingDecode(SystemZstdDecompressor):
        def preflight(self) -> DecompressorEvidence:
            return DecompressorEvidence("zstd", "fake")

        def open_stream(self, source: Path) -> subprocess.Popen[bytes]:
            del source
            code = (
                "import sys\n"
                "sys.stdout.buffer.write(open(sys.argv[1], 'rb').read())\n"
                "sys.stderr.buffer.write(b'decompressor failed\\n')\n"
                "raise SystemExit(1)\n"
            )
            return subprocess.Popen(
                [sys.executable, "-c", code, str(tar_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

    refused = OllamaRuntime().install(
        tmp_path / "state",
        staged,
        recipe,
        safe_bytes=SAFE_BYTES,
        decompressor=FailingDecode(),
    )
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.PACKAGE_INSTALL_FAILED
    assert "exited without success" in refused.reason
    assert "decompressor failed" in refused.reason
    assert not (tmp_path / "state" / "foundation" / "environments").exists()


def test_corrupt_registry_is_a_typed_refusal(tmp_path: Path) -> None:
    from machi.adapters.foundation.ollama_archive import inspect_environment_index

    archive = _archive()
    path = _file(tmp_path, archive, "next.tar")
    recipe = _recipe(archive)
    state = tmp_path / "state"
    kept = state / "foundation" / "environments" / "renv_kept"
    kept.mkdir(parents=True)
    marker = kept / "manifest.json"
    marker.write_text(
        '{"owned": true, "environment_id": "renv_kept"}\n',
        encoding="utf-8",
    )
    registry = state / "foundation" / "environments" / "registry.json"
    registry.write_text("{not-json", encoding="utf-8")
    original_registry = registry.read_bytes()
    original_marker = marker.read_bytes()
    refused = OllamaRuntime().install(state, path, recipe, safe_bytes=SAFE_BYTES)
    assert isinstance(refused, PrefixRefusal)
    assert refused.failure is FailureCode.VERIFICATION_FAILED
    assert refused.support is SupportState.RECONCILE_REQUIRED
    assert refused.reason == "environment index is corrupt"
    assert registry.read_bytes() == original_registry
    assert marker.read_bytes() == original_marker
    inspection = inspect_environment_index(state)
    assert inspection.corrupt is True
    assert inspection.reason == "environment index is corrupt"
    registry.write_text('{"ids": []}\n', encoding="utf-8")
    shaped = OllamaRuntime().install(state, path, recipe, safe_bytes=SAFE_BYTES)
    assert isinstance(shaped, PrefixRefusal)
    assert shaped.reason == "environment index is corrupt"
    assert registry.read_text(encoding="utf-8") == '{"ids": []}\n'
    assert marker.read_bytes() == original_marker
