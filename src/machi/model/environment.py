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
