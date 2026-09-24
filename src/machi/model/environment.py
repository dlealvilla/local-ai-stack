"""Material execution environment. Not a device name and not a class label."""

from __future__ import annotations

from machi.model.identity import input_token


def execution_environment_fingerprint(
    *,
    vendor: str,
    accelerator_model: str,
    capability: str,
    runtime_capability: str,
    generation_id: str,
) -> str:
    """Hash the facts that make one accelerator environment different.

    ``capability`` is a compute capability or gfx token. ``accelerator_model``
    is the normalized model, so two devices in one capability class stay
    distinct. No vendor driver number is named here.
    """
    parts = (
        "execution-environment",
        vendor.strip().lower(),
        accelerator_model.strip().lower(),
        capability.strip().lower(),
        runtime_capability.strip().lower(),
        generation_id.strip(),
    )
    if any(not part for part in parts[1:]):
        raise ValueError("execution environment fact is empty")
    return "exe_" + input_token(*parts)


def runtime_bound_execution_fingerprint(
    *,
    vendor: str,
    accelerator_model: str,
    capability: str,
    runtime_capability: str,
    runtime_environment_id: str,
) -> str:
    """Environment hash that cites an renv_ artifact, not an fgen_ generation.

    Provider foundation generations are derived from this fingerprint, so the
    fingerprint cannot also contain the generation it creates.
    """
    if not runtime_environment_id.startswith("renv_"):
        raise ValueError("runtime environment id must be an renv identity")
    return execution_environment_fingerprint(
        vendor=vendor,
        accelerator_model=accelerator_model,
        capability=capability,
        runtime_capability=runtime_capability,
        generation_id=runtime_environment_id,
    )
