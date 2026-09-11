"""Exact provisioning pins. Not floating ranges and not verification truth."""

from __future__ import annotations

VLLM_VERSION = "0.28.0"
PYTHON_VERSION = "3.12"
VLLM_PACKAGE = "vllm"
PYPI_SOURCE = "pypi"
PIP_INSTALLER = "pip"
NATIVE_EXECUTOR = "native-process"
PLAN_SCHEMA = "runtime.provisioning_plan@1"
INSTALLATION_SCHEMA = "runtime.installation@1"
PROFILE_SCHEMA = "runtime.capability_profile@1"
BASIS_SCHEMA = "runtime.verification_basis@1"
SELECTION_SCHEMA = "runtime.foundation_selection@1"
ELIGIBILITY_SCHEMA = "runtime.eligible_model_view@1"
PREFERENCE_POLICY_VERSION = "1.6R0.0-runtime-breadth"
#: Ranking preference only. Not feasibility, not admission, not 32 GiB Sonar.
COMFORTABLE_STORAGE_BYTES = 64 * 1024**3
TARGET_SEMANTICS = "runtimes/{runtime}/{version}"
PROBE_TIMEOUT_SECONDS = 180.0
PROBE_OUTPUT_LIMIT_BYTES = 32 * 1024
