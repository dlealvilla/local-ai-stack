"""Native vLLM foundation resolution and provisioning seams."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from pathlib import Path

from machi.adapters.foundation.process import ProcessResult
from machi.adapters.foundation.provision import ManagedVllmProvisioner
from machi.capacity.compose import compose_envelope
from machi.capacity.contracts import CapacityEnvelope
from machi.discover.contracts import (
    AcceleratorDevice,
    AcceleratorDeviceType,
    AcceleratorMemoryTopology,
    AcceleratorObservation,
    AcceleratorProviderReport,
    AcceleratorSource,
    AcceleratorVendor,
    CpuArchitecture,
    MemoryObservation,
    MemorySource,
    ObservationStatus,
    OSArchitectureObservation,
    OSFamily,
    ProviderInspectionStatus,
)
from machi.foundation.contracts import (
    AcceleratorBackend,
    FailureCode,
    ProvisionMode,
    SupportState,
)
from machi.foundation.policy import default_foundation_settings
from machi.foundation.resolve import resolve_candidate
from machi.kernel.clock import FixedClock
from machi.kernel.unresolved import NOT_MEASURED, is_resolved

FIXED = dt.datetime(2026, 9, 22, 5, 0, tzinfo=dt.UTC)
GIB = 1024 * 1024 * 1024


def _os(family: OSFamily) -> OSArchitectureObservation:
    return OSArchitectureObservation(
        os_family=family,
        architecture=CpuArchitecture.X86_64,
        os_status=ObservationStatus.NORMALIZED,
        architecture_status=ObservationStatus.NORMALIZED,
        raw_os=family.value,
        raw_architecture="x86_64",
        observed_at=FIXED,
        observer="native",
    )


def _gpu(vendor: AcceleratorVendor, identity: str) -> AcceleratorObservation:
    device = AcceleratorDevice(
        ordinal=0,
        vendor=vendor,
        vendor_status=ObservationStatus.NORMALIZED,
        model_name="GPU",
        model_status=ObservationStatus.NORMALIZED,
        device_type=AcceleratorDeviceType.DISCRETE_GPU,
        device_type_status=ObservationStatus.NORMALIZED,
        memory_topology=AcceleratorMemoryTopology.DISCRETE,
        memory_topology_status=ObservationStatus.NORMALIZED,
        memory_total_bytes=48 * GIB,
        memory_total_status=ObservationStatus.NORMALIZED,
        identity=identity,
        source=(
            AcceleratorSource.NVIDIA_SMI
            if vendor is AcceleratorVendor.NVIDIA
            else AcceleratorSource.AMD_SMI
        ),
        raw="index=0",
    )
    return AcceleratorObservation(
        devices=(device,),
        providers=(
            AcceleratorProviderReport(
                provider=vendor.value,
                status=ProviderInspectionStatus.OBSERVED,
                detail="",
                device_count=1,
            ),
        ),
        status=ObservationStatus.NORMALIZED,
        observed_at=FIXED,
        observer="native",
    )


def _capacity(storage: int, memory: int) -> CapacityEnvelope:
    observed = MemoryObservation(
        physical_total_bytes=memory,
        physical_total_status=ObservationStatus.NORMALIZED,
        source=MemorySource.LINUX_PROC,
        raw_total=f"MemTotal:{memory}",
        observed_at=FIXED,
        observer="native",
    )
    from machi.adapters.discover.linux_mount import LinuxMountProvider
    from machi.discover.mounts import default_mount_settings

    class _VFS:
        def __init__(self) -> None:
            self.f_frsize = 1
            self.f_bsize = 1
            self.f_blocks = storage
            self.f_bfree = storage
            self.f_bavail = storage

    provider = LinuxMountProvider(
        mountinfo_text="22 1 8:1 / /data rw - ext4 /dev/sda1 rw\n",
        statvfs=lambda _path: _VFS(),
        clock=FixedClock(FIXED),
    )
    mounts = provider.observe(default_mount_settings(), FIXED)
    return compose_envelope(
        evidence_id="cap_foundation",
        memory=observed,
        execution_limit_bytes=NOT_MEASURED,
        mounts=mounts,
        settings=__import__(
            "machi.capacity.policy", fromlist=["default_capacity_settings"]
        ).default_capacity_settings(
            memory_reserve_bytes=0,
            storage_reserve_bytes=0,
            accelerator_reserve_bytes=0,
        ),
        observed_at=FIXED,
        provider="native",
        input_parts=("cap",),
    )


def test_nvidia_candidate_is_cuda() -> None:
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="auto",
        prerequisite_ready=None,
    )
    assert candidate.backend is AcceleratorBackend.CUDA
    assert candidate.support is SupportState.SUPPORTED
    assert candidate.package_spec == "vllm==0.18.0"
    assert candidate.failure is FailureCode.NONE


def test_amd_candidate_is_rocm() -> None:
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.AMD, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="auto",
        prerequisite_ready=None,
    )
    assert candidate.backend is AcceleratorBackend.ROCM
    assert "rocm700" in candidate.package_spec
    assert candidate.package_source.startswith("https://wheels.vllm.ai/rocm/")


def test_macos_is_unsupported_without_ollama_substitution() -> None:
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.MACOS),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="auto",
        prerequisite_ready=None,
    )
    assert candidate.failure is FailureCode.HOST_UNSUPPORTED
    assert candidate.support is SupportState.UNSUPPORTED
    assert not is_resolved(candidate.backend)
    assert "ollama" not in candidate.reason


def test_insufficient_storage_blocks() -> None:
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(1 * GIB, 16 * GIB),
        backend="cuda",
        prerequisite_ready=True,
    )
    assert candidate.failure is FailureCode.INSUFFICIENT_CAPACITY


def test_prerequisite_block_is_distinct() -> None:
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.AMD, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="rocm",
        prerequisite_ready=False,
    )
    assert candidate.failure is FailureCode.PREREQUISITE_BLOCKED
    assert candidate.support is SupportState.BLOCKED_BY_PREREQUISITE


def test_explicit_cuda_without_nvidia_fails_closed() -> None:
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.AMD, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="cuda",
        prerequisite_ready=None,
    )
    assert candidate.failure is FailureCode.ACCELERATOR_UNSUPPORTED


class _Runner:
    def __init__(self, version: str = "0.18.0") -> None:
        self.version = version
        self.calls: list[list[str]] = []

    def run(
        self,
        argv: list[str],
        *,
        cwd: str,
        timeout: int,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        self.calls.append(argv)
        if argv[:2] == ["uv", "venv"]:
            python = Path(argv[4]) / "bin" / "python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("", encoding="utf-8")
            return ProcessResult(0, "", False)
        if "-c" in argv:
            if self.version != "0.18.0":
                return ProcessResult(1, self.version, False)
            return ProcessResult(0, f"{self.version}\n", False)
        return ProcessResult(0, "", False)


def test_provision_creates_owned_generation_and_reuses_it(tmp_path: Path) -> None:
    runner = _Runner()
    tool = ManagedVllmProvisioner(runner, clock=FixedClock(FIXED))
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="cuda",
        prerequisite_ready=None,
    )
    settings = default_foundation_settings(mode=ProvisionMode.PROVISION, backend="cuda")
    first = tool.apply(
        state_root=tmp_path,
        candidate=candidate,
        settings=settings,
        capacity_evidence_id="cap_foundation",
    )
    assert first.selection.support is SupportState.READY
    assert is_resolved(first.verification)
    assert first.verification.passed is True
    generations = tmp_path / "foundation" / "generations"
    manifest = next(generations.rglob(".machi-foundation.json"))
    assert "managed_vllm_foundation" in manifest.read_text(encoding="utf-8")
    calls_after_first = len(runner.calls)
    second = tool.apply(
        state_root=tmp_path,
        candidate=candidate,
        settings=settings,
        capacity_evidence_id="cap_foundation",
    )
    assert second.selection.support is SupportState.READY
    assert len(runner.calls) == calls_after_first + 1
    assert runner.calls[-1][0].endswith("python")


def test_version_mismatch_is_verification_failure(tmp_path: Path) -> None:
    runner = _Runner(version="9.9.9")
    tool = ManagedVllmProvisioner(runner, clock=FixedClock(FIXED))
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="cuda",
        prerequisite_ready=None,
    )
    result = tool.apply(
        state_root=tmp_path,
        candidate=candidate,
        settings=default_foundation_settings(mode=ProvisionMode.PROVISION),
        capacity_evidence_id="cap_foundation",
    )
    assert result.selection.support is SupportState.VERIFICATION_FAILED
    assert result.selection.failure is FailureCode.VERIFICATION_FAILED


def test_inspect_does_not_call_the_process_runner(tmp_path: Path) -> None:
    runner = _Runner()
    tool = ManagedVllmProvisioner(runner, clock=FixedClock(FIXED))
    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="auto",
        prerequisite_ready=None,
    )
    result = tool.apply(
        state_root=tmp_path,
        candidate=candidate,
        settings=default_foundation_settings(mode=ProvisionMode.INSPECT_ONLY),
        capacity_evidence_id="cap_foundation",
    )
    assert result.selection.support is SupportState.SUPPORTED
    assert runner.calls == []
    assert not (tmp_path / "foundation").exists()


def test_settings_name_python_and_vllm_pins() -> None:
    settings = default_foundation_settings()
    names = {row.name for row in settings.settings}
    assert "python.version" in names
    assert "vllm.version" in names
    assert "provision.mode" in names
    assert settings.executor.value == "native_process"


def test_missing_os_is_unresolved_input() -> None:
    candidate = resolve_candidate(
        os_observation=None,
        accelerators=None,
        capacity=None,
        backend="auto",
        prerequisite_ready=None,
    )
    assert candidate.failure is FailureCode.HOST_UNSUPPORTED


def test_timeout_is_distinct(tmp_path: Path) -> None:
    class _Timeout:
        def run(
            self,
            argv: list[str],
            *,
            cwd: str,
            timeout: int,
            env: Mapping[str, str] | None = None,
        ) -> ProcessResult:
            return ProcessResult(124, "", True)

    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="cuda",
        prerequisite_ready=None,
    )
    result = ManagedVllmProvisioner(_Timeout(), clock=FixedClock(FIXED)).apply(
        state_root=tmp_path,
        candidate=candidate,
        settings=default_foundation_settings(mode=ProvisionMode.PROVISION),
        capacity_evidence_id="cap_foundation",
    )
    assert result.selection.failure is FailureCode.TIMEOUT


def test_backend_mismatch_is_distinct(tmp_path: Path) -> None:
    class _Mismatch:
        def run(
            self,
            argv: list[str],
            *,
            cwd: str,
            timeout: int,
            env: Mapping[str, str] | None = None,
        ) -> ProcessResult:
            if argv[:2] == ["uv", "venv"]:
                python = Path(argv[4]) / "bin" / "python"
                python.parent.mkdir(parents=True, exist_ok=True)
                python.write_text("", encoding="utf-8")
                return ProcessResult(0, "", False)
            if "-c" in argv:
                return ProcessResult(2, "MACHI_BACKEND_MISMATCH\n", False)
            return ProcessResult(0, "", False)

    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="cuda",
        prerequisite_ready=None,
    )
    result = ManagedVllmProvisioner(_Mismatch(), clock=FixedClock(FIXED)).apply(
        state_root=tmp_path,
        candidate=candidate,
        settings=default_foundation_settings(mode=ProvisionMode.PROVISION),
        capacity_evidence_id="cap_foundation",
    )
    assert result.selection.failure is FailureCode.DRIVER_OR_BACKEND_INCOMPATIBLE


def test_invalid_generation_is_not_treated_as_healthy(tmp_path: Path) -> None:
    planted = tmp_path / "foundation" / "generations" / "fgen_old"
    planted.mkdir(parents=True)
    (planted / ".machi-foundation.json").write_text(
        '{"candidate_id":"vllm-0.18.0-cuda","generation_id":"fgen_old",'
        f'"python_path":"{planted / "missing"}"}}\n'.replace("}}", "}"),
        encoding="utf-8",
    )

    class _RejectThenInstall(_Runner):
        def __init__(self) -> None:
            super().__init__()
            self.rejected = False

        def run(
            self,
            argv: list[str],
            *,
            cwd: str,
            timeout: int,
            env: Mapping[str, str] | None = None,
        ) -> ProcessResult:
            if "-c" in argv and not self.rejected:
                self.rejected = True
                return ProcessResult(1, "", False)
            return super().run(argv, cwd=cwd, timeout=timeout, env=env)

    candidate = resolve_candidate(
        os_observation=_os(OSFamily.LINUX),
        accelerators=_gpu(AcceleratorVendor.NVIDIA, "gpu0"),
        capacity=_capacity(40 * GIB, 16 * GIB),
        backend="cuda",
        prerequisite_ready=None,
    )
    result = ManagedVllmProvisioner(
        _RejectThenInstall(),
        clock=FixedClock(FIXED),
    ).apply(
        state_root=tmp_path,
        candidate=candidate,
        settings=default_foundation_settings(mode=ProvisionMode.PROVISION),
        capacity_evidence_id="cap_foundation",
    )
    assert result.selection.support is SupportState.READY
    generations = list((tmp_path / "foundation" / "generations").iterdir())
    assert len(generations) == 2
