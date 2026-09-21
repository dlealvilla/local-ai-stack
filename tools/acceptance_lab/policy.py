"""Live NVIDIA+AMD acceptance policy.

``CURRENT_POLICY`` is the policy that runtime checks use now. Historical
``policy_snapshot`` rows are append-only: never rewrite a snapshot that
truthfully recorded an older floor or scope. A policy change is a new
snapshot plus an update of this module.
"""

from __future__ import annotations

from typing import Any

CURRENT_POLICY: dict[str, Any] = {
    "active_providers": ["nvidia", "amd"],
    "deferred_providers": ["apple"],
    "out_of_scope_providers": ["intel"],
    "apple_policy": "code_retained_not_accepted_physical_deferred",
    "intel_policy": "out_of_scope",
    "intel_status": "PARKED_OUT_OF_SCOPE",
    "policy_revision": "physical-poc-2026-09-21-balance-floor-5",
    "max_nvidia_hourly_usd": 1.50,
    "max_amd_hourly_usd": 4.00,
    "max_session_usd": 40.0,
    "max_daily_usd": 80.0,
    "balance_floor_usd": 5.0,
    "max_concurrent_pods": 1,
    "max_pod_lifetime_seconds": 5400,
    "max_provision_retries": 3,
    "max_nvidia_servers": 3,
    "max_amd_servers": 3,
    "first_physical_proof": {"nvidia": 1, "amd": 1},
    "allow_secure_cloud": True,
    "allow_community_cloud": True,
    "allow_network_volume": False,
    "regions": "unrestricted",
    "hang_action": "stop_and_ask",
    "success_teardown_action": "terminate",
    "product_failure_teardown_action": "terminate",
    "selection_strategy": "coverage_driven_random",
    "first_amd_target": "MI300X",
    "stock_vendor_cli_required": True,
    "install_vendor_driver_or_smi": False,
    "pod_name_prefix": "machi-acceptance-",
}

# Policy that governed the 351cee81 NVIDIA physical campaign. RunPod limits
# did not apply; numeric lab ceilings are stored only because the schema
# requires the columns and are flagged as not governing.
HISTORICAL_NVIDIA_PHYSICAL_POLICY: dict[str, Any] = {
    "active_providers": ["nvidia"],
    "implemented_providers": ["nvidia", "apple"],
    "deferred_providers": ["apple"],
    "out_of_scope_providers": ["intel", "amd"],
    "apple_policy": "implemented_physical_pending",
    "intel_policy": "out_of_scope",
    "amd_policy": "not_implemented_on_this_candidate",
    "max_nvidia_hourly_usd": 0.0,
    "max_amd_hourly_usd": 0.0,
    "max_session_usd": 0.0,
    "max_daily_usd": 0.0,
    "balance_floor_usd": 0.0,
    "max_concurrent_pods": 0,
    "max_pod_lifetime_seconds": 0,
    "max_provision_retries": 0,
    "max_nvidia_servers": 1,
    "max_amd_servers": 0,
    "first_physical_proof": {"nvidia": 1, "amd": 0},
    "allow_secure_cloud": False,
    "allow_community_cloud": False,
    "allow_network_volume": False,
    "regions": "not_applicable",
    "hang_action": "not_applicable",
    "success_teardown_action": "not_recorded",
    "product_failure_teardown_action": "not_recorded",
    "selection_strategy": "operator_supplied_historical_host",
    "first_amd_target": "not_applicable",
    "stock_vendor_cli_required": True,
    "install_vendor_driver_or_smi": False,
    "runpod_limits_applied": False,
    "pod_name_prefix": "not_applicable",
}
