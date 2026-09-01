def export_event(
    event,
    config,
):
    """
    No-op UsageExporter.

    FUTURE:
    Replaceable exporters may asynchronously send structured,
    non-content UsageEvents to vendor or customer systems.
    """

    return {
        "exported": False,
        "provider": "disabled",
    }
