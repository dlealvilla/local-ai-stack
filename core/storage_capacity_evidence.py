from datetime import (
    datetime,
    timezone,
)


STORAGE_EVIDENCE_SCHEMA_VERSION = 1


VALID_TYPES = {
    "quota_total",
    "remaining_point",
    "remaining_lower_bound",
    "remaining_upper_bound",
    "usage_point",
    "diagnostic",
}


VALID_CONFIDENCE = {
    "authoritative",
    "high",
    "medium",
    "low",
    "rejected",
}


def build_storage_evidence(
    *,
    evidence_id,
    source,
    scope,
    evidence_type,
    value_bytes,
    confidence,
    accepted=True,
    detail=None,
):
    """
    Normalize one storage-capacity observation.

    Different evidence semantics must not be averaged together.

    Examples:

    quota_total
        "This volume is provisioned as 200 GB."

    remaining_point
        "Approximately 117 GB remain."

    remaining_lower_bound
        "At least 100 GB was successfully reservable."

    remaining_upper_bound
        "A 120 GB reservation failed."

    usage_point
        "This mounted namespace currently consumes 83 GB."
    """

    if evidence_type not in VALID_TYPES:
        raise ValueError(
            "Unsupported storage evidence type: "
            + str(evidence_type)
        )

    if confidence not in VALID_CONFIDENCE:
        raise ValueError(
            "Unsupported storage evidence confidence: "
            + str(confidence)
        )

    if value_bytes is not None:
        value_bytes = int(
            value_bytes
        )

        if value_bytes < 0:
            raise ValueError(
                "Storage evidence value cannot be negative."
            )

    return {
        "schema_version": (
            STORAGE_EVIDENCE_SCHEMA_VERSION
        ),

        "evidence_id": evidence_id,

        "observed_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": source,

        "scope": scope,

        "type": evidence_type,

        "value_bytes": value_bytes,

        "confidence": confidence,

        "accepted": bool(
            accepted
        ),

        "detail": detail,
    }
