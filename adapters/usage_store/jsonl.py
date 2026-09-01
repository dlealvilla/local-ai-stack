import json
import threading
from pathlib import Path


_WRITE_LOCK = threading.Lock()


def resolve_path(config):
    configured = Path(
        config["analytics"][
            "usage_events_path"
        ]
    )

    if configured.is_absolute():
        return configured

    return (
        Path(
            config["platform"]["data_root"]
        )
        / configured
    )


def append_event(event, config):
    """
    PROVISIONAL single-node JSONL event storage.

    This implementation is replaceable.

    The lock protects concurrent gateway threads inside
    the current gateway process.
    """

    path = resolve_path(
        config
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    line = json.dumps(
        event,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    with _WRITE_LOCK:
        with path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                line + "\n"
            )

    return path


def find_event(event_id, config):
    """
    Find one usage event by its platform request/event ID.

    PROVISIONAL:
    Linear JSONL scan is acceptable for the bootstrap store.
    A database-backed implementation will provide indexed lookup.
    """

    path = resolve_path(
        config
    )

    if not path.exists():
        return None

    with path.open(
        encoding="utf-8",
    ) as handle:

        for line in handle:
            line = line.strip()

            if not line:
                continue

            try:
                event = json.loads(
                    line
                )
            except Exception:
                continue

            if (
                event.get("event_id")
                == event_id
            ):
                return event

    return None



def list_events(config):
    """
    Return all stored UsageEvents.

    PROVISIONAL:
    Full-file scanning is acceptable for the current bootstrap store.
    """

    path = resolve_path(
        config
    )

    if not path.exists():
        return []

    events = []

    with path.open(
        encoding="utf-8",
    ) as handle:

        for line in handle:
            line = line.strip()

            if not line:
                continue

            try:
                events.append(
                    json.loads(line)
                )
            except Exception:
                continue

    return events
