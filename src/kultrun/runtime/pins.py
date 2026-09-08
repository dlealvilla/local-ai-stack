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
TARGET_SEMANTICS = "runtimes/{runtime}/{version}"
