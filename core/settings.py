def normalize_setting(
    name,
    requested,
    effective,
    recommendation=None,
):
    """
    Normalize one configurable platform setting.

    This separates:
    - requested administrator/config value
    - recommendation from platform intelligence
    - effective value actually used

    PROVISIONAL:
    Only some settings currently have real automatic recommendation logic.
    The structure is intended to remain stable while the intelligence improves.
    """

    mode = (
        "auto"
        if requested == "auto"
        else "manual"
    )

    recommended = None
    reason = None
    confidence = None

    if recommendation:
        recommended = recommendation.get(
            "value"
        )

        reason = recommendation.get(
            "reason"
        )

        confidence = recommendation.get(
            "confidence"
        )

    if mode == "manual":
        reason = (
            reason
            or
            "Explicit value supplied by configuration."
        )

        confidence = (
            confidence
            or
            "explicit"
        )

    elif effective == "auto":
        reason = (
            reason
            or
            "Automatic resolution is not implemented "
            "for this setting yet."
        )

        confidence = (
            confidence
            or
            "unresolved"
        )

    else:
        recommended = (
            recommended
            if recommended is not None
            else effective
        )

        reason = (
            reason
            or
            "Automatically resolved by the planner."
        )

        confidence = (
            confidence
            or
            "provisional"
        )

    return {
        "name": name,
        "mode": mode,
        "requested": (
            None
            if requested == "auto"
            else requested
        ),
        "recommended": recommended,
        "effective": effective,
        "reason": reason,
        "confidence": confidence,
    }


def build_performance_settings(
    requested,
    effective,
    recommendations,
):
    settings = {}

    for name in (
        "context_length",
        "gpu_memory_utilization",
        "concurrency",
    ):
        settings[name] = normalize_setting(
            name=name,
            requested=requested.get(name),
            effective=effective.get(name),
            recommendation=(
                recommendations.get(name)
            ),
        )

    return settings
