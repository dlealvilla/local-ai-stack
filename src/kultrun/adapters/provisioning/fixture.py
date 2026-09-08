"""Deterministic fixture provisioner. Not real vLLM and never uses the network."""

from __future__ import annotations

import json
from pathlib import Path

from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import RuntimeProvisioningPlan
from kultrun.runtime.pins import VLLM_VERSION
from kultrun.runtime.ports import InstallerOutcome

IDENTITY = Name("fixture")


class FixtureRuntimeProvisioner:
    """Simulates isolated install, manifest, and failure. Offline only."""

    def __init__(
        self, *, fail: bool = False, installed_version: str = VLLM_VERSION
    ) -> None:
        self._fail = fail
        self._installed_version = installed_version
        self.install_calls = 0

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def installer_mechanism(self) -> str:
        return "fixture-marker"

    @property
    def requires_host_python(self) -> bool:
        return False

    def install(
        self,
        plan: RuntimeProvisioningPlan,
        staging_dir: Path,
        *,
        python_executable: str | None,
    ) -> InstallerOutcome:
        del python_executable
        self.install_calls += 1
        if self._fail:
            return InstallerOutcome(
                succeeded=False,
                failure_code="installer_failed",
                failure_message="fixture installer failed",
            )
        venv = staging_dir / "venv" / "bin"
        venv.mkdir(parents=True, exist_ok=True)
        python = venv / "python"
        python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        manifest = staging_dir / "manifest"
        manifest.mkdir(parents=True, exist_ok=True)
        report = {
            "version": "1",
            "requested": f"{plan.runtime.value}=={plan.runtime_version}",
            "install": [
                {
                    "metadata": {
                        "name": plan.runtime.value,
                        "version": self._installed_version,
                    }
                }
            ],
            "environment": {"installer": "fixture-marker"},
        }
        (manifest / "installer-report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        return InstallerOutcome(
            succeeded=True,
            python_executable=str(python),
            python_version=plan.python_version,
            installer_version="fixture",
            resolved_runtime_version=self._installed_version,
            report_relative_path="manifest/installer-report.json",
            provenance=(
                "fixture-marker",
                f"{plan.runtime.value}=={self._installed_version}",
            ),
        )
