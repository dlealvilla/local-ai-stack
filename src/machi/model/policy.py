"""Default model policy. Inspection does not download weights."""

from __future__ import annotations

from machi.model.contracts import (
    AcquisitionMode,
    ModelSetting,
    ModelSettings,
    SettingProvenance,
)

DEFAULT_TIMEOUT = 600
MAX_RETRIES = 2


def default_model_settings(
    *,
    mode: AcquisitionMode = AcquisitionMode.INSPECT_ONLY,
    provenance: SettingProvenance = SettingProvenance.PRODUCT_DEFAULT,
) -> ModelSettings:
    """Explicit references only. Remote code stays refused."""
    rows = (
        _row(
            "acquisition.mode",
            mode.value,
            provenance,
            "inspect does not fetch weights",
        ),
        _row(
            "remote_code.policy",
            "refuse",
            provenance,
            "repository code is not executed",
        ),
        _row(
            "warehouse.root",
            "state_root_warehouse",
            provenance,
            "owned artifact generations",
        ),
        _row(
            "import.copy",
            "copy_into_warehouse",
            provenance,
            "external paths are not inventory",
        ),
        _row("integrity", "sha256", provenance, "external etags are not the digest"),
        _row(
            "revision.policy",
            "immutable_commit",
            provenance,
            "branch names are not identity",
        ),
        _row(
            "license.policy",
            "surface_unknown",
            provenance,
            "missing license stays unknown",
        ),
        _row("source.hub", "enabled", provenance, "explicit repository references"),
        _row("source.local", "enabled", provenance, "local import needs no network"),
        _row("timeout.seconds", str(DEFAULT_TIMEOUT), provenance, "one source call"),
        _row("retries", str(MAX_RETRIES), provenance, "bounded retries"),
    )
    return ModelSettings(
        acquisition_mode=mode,
        remote_code_policy="refuse",
        warehouse_policy="state_root_warehouse",
        copy_policy="copy_into_warehouse",
        integrity_policy="sha256",
        revision_policy="immutable_commit",
        license_policy="surface_unknown",
        timeout_seconds=DEFAULT_TIMEOUT,
        max_retries=MAX_RETRIES,
        settings=rows,
    )


def _row(
    name: str,
    value: str,
    provenance: SettingProvenance,
    reason: str,
) -> ModelSetting:
    return ModelSetting(
        name=name,
        value=value,
        provenance=provenance,
        reason=reason,
        invalidation="recompute_available_models",
    )
