import json
import os
import re
import urllib.error
import urllib.request

from adapters.storage_capacity import (
    generic_filesystem,
)


PROVIDER = "runpod_network_volume"


def _volume_id_from_mount(
    mount,
):
    if not mount:
        return None

    source = str(
        mount.get(
            "source",
            "",
        )
    )

    match = re.search(
        r"/networkvolumes/([^]\s]+)",
        source,
    )

    if not match:
        return None

    return match.group(1)


def _query_runpod_volume(
    volume_id,
):
    """
    Query authoritative RunPod Network Volume metadata when
    an administrator has supplied an account-scoped read-only
    credential.

    The built-in RUNPOD_API_KEY is intentionally NOT used here
    because it may be pod-scoped rather than account-scoped.
    """

    api_key = os.environ.get(
        "RUNPOD_ACCOUNT_API_KEY"
    )

    if not api_key:
        return {
            "available": False,
            "reason": (
                "account_api_key_unavailable"
            ),
            "volume": None,
        }

    url = (
        "https://rest.runpod.io/v1/"
        "networkvolumes/"
        + volume_id
    )

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": (
                "Bearer "
                + api_key
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=15,
        ) as response:
            payload = json.load(
                response
            )

    except urllib.error.HTTPError as exc:
        return {
            "available": False,
            "reason": (
                "provider_api_http_"
                + str(
                    exc.code
                )
            ),
            "volume": None,
        }

    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return {
            "available": False,
            "reason": (
                "provider_api_unavailable"
            ),
            "volume": None,
        }

    return {
        "available": True,
        "reason": None,
        "volume": payload,
    }


def inspect_storage_capacity(
    *,
    path,
    config,
):
    """
    RunPod Network Volume capacity observation.

    Provider allocation is authoritative when the RunPod API
    can be queried.

    The mounted FUSE filesystem observation is retained as
    diagnostic information but is not treated as account quota.
    """

    generic = (
        generic_filesystem
        .inspect_storage_capacity(
            path=path,
            config=config,
        )
    )

    mount = generic.get(
        "mount"
    )

    volume_id = (
        os.environ.get(
            "RUNPOD_VOLUME_ID"
        )
        or _volume_id_from_mount(
            mount
        )
    )

    provider_result = None

    if volume_id:
        provider_result = (
            _query_runpod_volume(
                volume_id
            )
        )

    volume = (
        provider_result.get(
            "volume"
        )
        if provider_result
        else None
    )

    allocated_gb = (
        volume.get(
            "size"
        )
        if isinstance(
            volume,
            dict,
        )
        else None
    )

    quota_total_bytes = None

    if isinstance(
        allocated_gb,
        (int, float),
    ):
        # RunPod API reports volume allocation in decimal GB.
        quota_total_bytes = int(
            float(
                allocated_gb
            )
            * 1_000_000_000
        )

    quota_known = (
        quota_total_bytes
        is not None
    )

    notes = [
        (
            "Detected RunPod Network Volume."
        ),
        (
            "FUSE filesystem totals are retained "
            "for diagnostics but are not treated "
            "as the customer volume quota."
        ),
    ]

    if not quota_known:
        reason = (
            provider_result.get(
                "reason"
            )
            if provider_result
            else (
                "volume_identity_unavailable"
            )
        )

        notes.append(
            (
                "Authoritative RunPod quota is "
                "currently unavailable: "
                + str(
                    reason
                )
                + "."
            )
        )

    return {
        "provider": PROVIDER,

        "path": generic[
            "path"
        ],

        "identity": {
            "volume_id": (
                volume_id
            ),
            "datacenter_id": (
                os.environ.get(
                    "RUNPOD_DC_ID"
                )
                or (
                    volume.get(
                        "dataCenterId"
                    )
                    if isinstance(
                        volume,
                        dict,
                    )
                    else None
                )
            ),
        },

        "mount": mount,

        "filesystem": generic[
            "filesystem"
        ],

        "quota": {
            "known": (
                quota_known
            ),
            "total_bytes": (
                quota_total_bytes
            ),
            "source": (
                "runpod_network_volume_api"
                if quota_known
                else None
            ),
        },

        "provider_api": {
            "queried": (
                bool(
                    os.environ.get(
                        "RUNPOD_ACCOUNT_API_KEY"
                    )
                )
            ),
            "available": (
                provider_result.get(
                    "available"
                )
                if provider_result
                else False
            ),
            "reason": (
                provider_result.get(
                    "reason"
                )
                if provider_result
                else None
            ),
        },

        "confidence": (
            "high"
            if quota_known
            else "medium"
        ),

        "notes": notes,
    }
