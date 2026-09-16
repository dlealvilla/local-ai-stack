"""Import the completed RunPod read-only control-plane preflight.

Facts are those recorded at STATUS=RUNPOD_CONTROL_PLANE_READY.
No credentials are stored. No hardware selection is implied.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from tools.acceptance_lab.ids import stable_id
from tools.acceptance_lab.jsonutil import sha256_canonical
from tools.acceptance_lab.policy import CURRENT_POLICY
from tools.acceptance_lab.recording import record_campaign, record_policy
from tools.acceptance_lab.store import insert_or_ignore
from tools.acceptance_lab.timeutil import UTC, format_utc

PREFLIGHT_AT = dt.datetime(2026, 9, 16, 10, 20, 0, tzinfo=UTC)
SSH_FINGERPRINT = "SHA256:nJGORrvycr8VeY1UN52YiSh2H89/tAcbUdiUvic7blk"
RUNPODCTL_VERSION = "2.14.0-dd55bcf"
SPEND_USD = 1.085648168809712
GPU_SPEND_USD = 0.0

PROVIDER_SCOPE = {
    "nvidia": "ACTIVE",
    "amd": "ACTIVE",
    "intel": "OUT",
    "apple": "CODE_RETAINED_NOT_ACCEPTED_PHYSICAL_DEFERRED",
}

# Eligible NVIDIA 1x GPU at or under $1.50/hour with stock not NONE.
SECURE_NVIDIA_ELIGIBLE = (
    ("NVIDIA RTX 2000 Ada Generation", 0.24, "LOW", "EUR-IS-1"),
    ("NVIDIA RTX 4000 Ada Generation", 0.28, "LOW", "EUR-IS-1"),
    ("NVIDIA A40", 0.49, "LOW", "CA-MTL-1"),
    ("NVIDIA L4", 0.49, "LOW", "EU-RO-1"),
    ("NVIDIA RTX A6000", 0.53, "LOW", "EU-SE-1"),
    ("NVIDIA RTX PRO 4000 Blackwell", 0.57, "LOW", "EU-RO-1"),
    (
        "NVIDIA RTX PRO 6000 Blackwell Server Edition MIG 1g.24gb",
        0.59,
        "LOW",
        "US-NE-1",
    ),
    ("NVIDIA RTX PRO 4500 Blackwell", 0.72, "LOW", "EU-RO-1"),
    ("NVIDIA RTX PRO 4500 Blackwell Server Edition", 0.72, "LOW", "US-KS-2"),
    ("NVIDIA GeForce RTX 4090", 0.74, "MEDIUM", "EU-RO-1"),
    ("NVIDIA RTX 6000 Ada Generation", 0.84, "LOW", "US-CA-2"),
    ("NVIDIA GeForce RTX 5090", 0.99, "LOW", "EU-RO-1"),
    ("NVIDIA L40S", 1.09, "LOW", "OC-AU-1"),
    (
        "NVIDIA RTX PRO 6000 Blackwell Server Edition MIG 2g.48gb",
        1.09,
        "LOW",
        "EUR-IS-2",
    ),
)

COMMUNITY_NVIDIA_ELIGIBLE = (
    ("NVIDIA RTX 4000 SFF Ada Generation", 0.18, "LOW"),
    ("NVIDIA RTX A4500", 0.19, "LOW"),
    ("NVIDIA GeForce RTX 4070 Ti", 0.19, "LOW"),
    ("Tesla V100-PCIE-16GB", 0.19, "LOW"),
    ("NVIDIA RTX 4000 Ada Generation", 0.20, "LOW"),
    ("NVIDIA GeForce RTX 3090", 0.22, "LOW"),
    ("Tesla V100-SXM2-16GB", 0.23, "LOW"),
    ("NVIDIA GeForce RTX 4090", 0.34, "LOW"),
    ("NVIDIA GeForce RTX 5080", 0.39, "LOW"),
    ("NVIDIA RTX 5000 Ada Generation", 0.49, "LOW"),
    ("NVIDIA GeForce RTX 5090", 0.69, "LOW"),
    ("NVIDIA L40", 0.69, "LOW"),
    ("NVIDIA RTX 6000 Ada Generation", 0.74, "LOW"),
    ("NVIDIA L40S", 0.79, "LOW"),
    ("NVIDIA RTX PRO 5000 Blackwell", 0.82, "LOW"),
    ("NVIDIA A100-SXM4-40GB", 1.00, "LOW"),
    ("NVIDIA A100 80GB PCIe", 1.19, "LOW"),
    ("NVIDIA A100-SXM4-80GB", 1.39, "LOW"),
)

EXCLUDED_OVER_CAP = (
    ("NVIDIA H100 80GB HBM3", "SECURE", 3.49, "policy_h100_and_over_cap"),
    ("NVIDIA H100 NVL", "SECURE", 3.19, "policy_h100_and_over_cap"),
    ("NVIDIA H100 PCIe", "SECURE", 2.89, "policy_h100_and_over_cap"),
    ("NVIDIA H200", "SECURE", 4.59, "policy_h200_and_over_cap"),
    ("NVIDIA B200", "SECURE", 6.79, "policy_b200_and_over_cap"),
    ("NVIDIA A100 80GB PCIe", "SECURE", 1.59, "over_nvidia_hourly_cap"),
    ("NVIDIA A100-SXM4-80GB", "SECURE", 1.59, "over_nvidia_hourly_cap"),
    (
        "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition",
        "COMMUNITY",
        1.64,
        "over_nvidia_hourly_cap",
    ),
    (
        "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
        "COMMUNITY",
        1.69,
        "over_nvidia_hourly_cap",
    ),
)


def import_control_plane_preflight(connection: sqlite3.Connection) -> dict[str, str]:
    campaign_id = stable_id("camp", "runpod-control-plane-preflight", "2026-09-16")
    cps_id = stable_id("cps", campaign_id, format_utc(PREFLIGHT_AT))
    evid_id = stable_id("evid", "preflight-2026-09-16")
    record_campaign(
        connection,
        campaign_id=campaign_id,
        name="runpod-control-plane-preflight-2026-09-16",
        purpose="Read-only RunPod control-plane validation before AMD work",
        status="completed",
        when=PREFLIGHT_AT,
        started=PREFLIGHT_AT,
        finished=PREFLIGHT_AT,
        provider_scope=PROVIDER_SCOPE,
        notes=(
            "STATUS=RUNPOD_CONTROL_PLANE_READY. MCP OAuth connected. "
            "runpodctl installed but no_credentials. No Pod created or mutated. "
            "Current account balance was not exposed."
        ),
        historical_import=True,
    )
    record_policy(
        connection,
        campaign_id=campaign_id,
        policy=CURRENT_POLICY,
        when=PREFLIGHT_AT,
        historical_import=True,
    )
    insert_or_ignore(
        connection,
        "evidence_artifact",
        {
            "evidence_artifact_id": evid_id,
            "artifact_type": "runpod_response",
            "path": "docs/machi/acceptance_lab/PREFLIGHT-2026-09-16.json",
            "sha256": sha256_canonical(
                {
                    "existing_pod_count": 23,
                    "running_pod_count": 0,
                    "ssh": SSH_FINGERPRINT,
                    "mi300x_secure_usd": 2.39,
                }
            ),
            "size_bytes": None,
            "captured_at_utc": format_utc(PREFLIGHT_AT),
            "sanitized": 1,
            "committed": 1,
            "notes": "Sanitized preflight summary; no tokens or private keys.",
            "historical_import": 1,
        },
    )
    insert_or_ignore(
        connection,
        "control_plane_snapshot",
        {
            "control_plane_snapshot_id": cps_id,
            "campaign_id": campaign_id,
            "captured_at_utc": format_utc(PREFLIGHT_AT),
            "provider": "runpod",
            "authentication_mode": "mcp_oauth",
            "runpodctl_version": RUNPODCTL_VERSION,
            "mcp_connected": 1,
            "cli_authenticated": 0,
            "balance_exposed": 0,
            "balance_usd": None,
            "existing_pod_count": 23,
            "running_pod_count": 0,
            "ssh_public_key_fingerprint": SSH_FINGERPRINT,
            "observed_spend_usd": SPEND_USD,
            "observed_gpu_spend_usd": GPU_SPEND_USD,
            "raw_evidence_artifact_id": evid_id,
            "notes": (
                "23 pre-existing EXITED Pods observed and not modified. "
                "None named machi-acceptance-. Official skills installed user-level. "
                "Hosted MCP URL configured without API key."
            ),
            "historical_import": 1,
        },
    )
    for gpu, price, availability, datacenter in SECURE_NVIDIA_ELIGIBLE:
        insert_or_ignore(
            connection,
            "gpu_inventory_observation",
            {
                "gpu_inventory_observation_id": stable_id(
                    "gpin", cps_id, "SECURE", gpu
                ),
                "control_plane_snapshot_id": cps_id,
                "gpu_type": gpu,
                "manufacturer": "NVIDIA",
                "cloud_type": "SECURE",
                "datacenter": datacenter,
                "hourly_price_usd": price,
                "availability_state": availability,
                "max_gpu_count": 1,
                "eligible": 1,
                "exclusion_reason": None,
                "notes": "Preflight eligible pool; not a selection decision.",
            },
        )
    for gpu, price, availability in COMMUNITY_NVIDIA_ELIGIBLE:
        insert_or_ignore(
            connection,
            "gpu_inventory_observation",
            {
                "gpu_inventory_observation_id": stable_id(
                    "gpin", cps_id, "COMMUNITY", gpu
                ),
                "control_plane_snapshot_id": cps_id,
                "gpu_type": gpu,
                "manufacturer": "NVIDIA",
                "cloud_type": "COMMUNITY",
                "datacenter": None,
                "hourly_price_usd": price,
                "availability_state": availability,
                "max_gpu_count": 1,
                "eligible": 1,
                "exclusion_reason": None,
                "notes": "Preflight eligible pool; not a selection decision.",
            },
        )
    for gpu, cloud, price, reason in EXCLUDED_OVER_CAP:
        insert_or_ignore(
            connection,
            "gpu_inventory_observation",
            {
                "gpu_inventory_observation_id": stable_id(
                    "gpin", cps_id, "excl", cloud, gpu
                ),
                "control_plane_snapshot_id": cps_id,
                "gpu_type": gpu,
                "manufacturer": "NVIDIA",
                "cloud_type": cloud,
                "datacenter": None,
                "hourly_price_usd": price,
                "availability_state": "LOW",
                "max_gpu_count": 1,
                "eligible": 0,
                "exclusion_reason": reason,
                "notes": "Recorded so the exclusion is auditable.",
            },
        )
    insert_or_ignore(
        connection,
        "gpu_inventory_observation",
        {
            "gpu_inventory_observation_id": stable_id("gpin", cps_id, "MI300X"),
            "control_plane_snapshot_id": cps_id,
            "gpu_type": "AMD Instinct MI300X OAM",
            "manufacturer": "AMD",
            "cloud_type": "SECURE",
            "datacenter": "EU-RO-1",
            "hourly_price_usd": 2.39,
            "availability_state": "LOW",
            "max_gpu_count": 8,
            "eligible": 1,
            "exclusion_reason": None,
            "notes": (
                "First AMD gate target. Community stock NONE. "
                "Community price 0.5 on the catalog row is not a usable offer."
            ),
        },
    )
    connection.commit()
    return {"campaign_id": campaign_id, "control_plane_snapshot_id": cps_id}
