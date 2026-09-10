"""vLLM native-process provisioner. Installs a pin; does not run the engine."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import RuntimeProvisioningPlan
from kultrun.runtime.pins import PIP_INSTALLER, VLLM_PACKAGE, VLLM_VERSION
from kultrun.runtime.ports import InstallerOutcome

IDENTITY = Name("vllm-native")
METADATA_PROBE = "import importlib.metadata as m; print(m.version('vllm'))"


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured subprocess outcome. Not a domain contract."""

    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """Structured argv execution. Implementations must not use a shell."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: float | None = None,
    ) -> CommandResult: ...


class SubprocessRunner:
    """stdlib subprocess, argv list only."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        import subprocess

        if not argv:
            raise PreconditionFailedError("installer argv must not be empty")
        finished = subprocess.run(
            list(argv),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            shell=False,
        )
        return CommandResult(finished.returncode, finished.stdout, finished.stderr)


class VllmNativeProvisioner:
    """Create a venv and pip-install exact vllm==0.28.0 into staging."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def installer_mechanism(self) -> str:
        return "python-venv-pip"

    @property
    def requires_host_python(self) -> bool:
        return True

    def install(
        self,
        plan: RuntimeProvisioningPlan,
        staging_dir: Path,
        *,
        python_executable: str | None,
    ) -> InstallerOutcome:
        if plan.runtime_version != VLLM_VERSION:
            return InstallerOutcome(
                succeeded=False,
                failure_code="version_mismatch",
                failure_message="plan is not the Stage 1.6C vLLM pin",
            )
        if python_executable is None:
            return InstallerOutcome(
                succeeded=False,
                failure_code="prerequisite_missing",
                failure_message="python 3.12 is not available",
            )
        venv_root = staging_dir / "venv"
        created = self._runner.run([python_executable, "-m", "venv", str(venv_root)])
        if created.returncode != 0:
            return InstallerOutcome(
                succeeded=False,
                failure_code="installer_failed",
                failure_message=created.stderr.strip() or "venv creation failed",
            )
        venv_python = _venv_python(venv_root)
        if venv_python is None:
            return InstallerOutcome(
                succeeded=False,
                failure_code="installer_failed",
                failure_message="venv python is missing",
            )
        report = staging_dir / "manifest" / "installer-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        # pip is the Stage 1.6C installer. uv is K-67; lockfiles are K-69.
        package = f"{VLLM_PACKAGE}=={VLLM_VERSION}"
        installed = self._runner.run(
            [
                str(venv_python),
                "-m",
                PIP_INSTALLER,
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--report",
                str(report),
                package,
            ]
        )
        if installed.returncode != 0:
            return InstallerOutcome(
                succeeded=False,
                failure_code="installer_failed",
                failure_message=installed.stderr.strip() or "pip install failed",
            )
        probed = self._runner.run([str(venv_python), "-c", METADATA_PROBE])
        if probed.returncode != 0:
            return InstallerOutcome(
                succeeded=False,
                failure_code="installer_failed",
                failure_message=probed.stderr.strip() or "metadata probe failed",
            )
        version = probed.stdout.strip()
        pip_version = self._pip_version(venv_python)
        _summarize_report(report)
        return InstallerOutcome(
            succeeded=True,
            python_executable=str(venv_python),
            python_version=plan.python_version,
            installer_version=pip_version,
            resolved_runtime_version=version,
            report_relative_path="manifest/installer-report.json",
            provenance=(
                "python-venv-pip",
                package,
                f"report={report.name}",
            ),
        )

    def _pip_version(self, venv_python: Path) -> str | None:
        result = self._runner.run([str(venv_python), "-m", PIP_INSTALLER, "--version"])
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None


def _venv_python(root: Path) -> Path | None:
    unix = root / "bin" / "python"
    if unix.exists():
        return unix
    windows = root / "Scripts" / "python.exe"
    if windows.exists():
        return windows
    return None


def _summarize_report(report: Path) -> None:
    """Best-effort parse. Missing hashes are not fabricated."""
    if not report.is_file():
        return
    try:
        json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
