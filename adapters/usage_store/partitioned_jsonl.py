import json
import threading

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path


_WRITE_LOCK = threading.Lock()


def _parse_time(value):
    if not value:
        return None

    if value.endswith("Z"):
        value = (
            value[:-1]
            + "+00:00"
        )

    parsed = datetime.fromisoformat(
        value
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def resolve_dir(config):
    configured = Path(
        config["analytics"][
            "usage_events_dir"
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


def _partition_date(event):
    started_at = event.get(
        "started_at"
    )

    try:
        parsed = _parse_time(
            started_at
        )
    except Exception:
        parsed = None

    if parsed is None:
        parsed = datetime.now(
            timezone.utc
        )

    return parsed.date().isoformat()


def _partition_path(
    event,
    config,
):
    return (
        resolve_dir(config)
        / (
            _partition_date(event)
            + ".jsonl"
        )
    )


def append_event(
    event,
    config,
):
    """
    Append one UsageEvent to its UTC daily partition.

    WORKING implementation.

    The UsageStore interface remains independent of JSONL.
    """

    path = _partition_path(
        event,
        config,
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


def list_events(config):
    """
    Return events across all local daily partitions.

    PROVISIONAL:
    Full scanning is acceptable for the MVP data volume.
    """

    root = resolve_dir(
        config
    )

    if not root.exists():
        return []

    events = []

    for path in sorted(
        root.glob("*.jsonl")
    ):
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


def find_event(
    event_id,
    config,
):
    """
    Find an event by ID.

    Search newest partitions first.

    PROVISIONAL:
    Future database stores should provide indexed lookup.
    """

    root = resolve_dir(
        config
    )

    if not root.exists():
        return None

    paths = sorted(
        root.glob("*.jsonl"),
        reverse=True,
    )

    for path in paths:
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


def prune_before(
    cutoff,
    config,
):
    """
    Remove events older than cutoff.

    Whole daily partitions older than the cutoff date are deleted.

    The cutoff-day partition is rewritten only when necessary.

    Future storage engines may implement this using TTL,
    partitions or database lifecycle policies.
    """

    cutoff_time = _parse_time(
        cutoff
    )

    if cutoff_time is None:
        return {
            "removed_events": 0,
            "removed_partitions": 0,
        }

    root = resolve_dir(
        config
    )

    if not root.exists():
        return {
            "removed_events": 0,
            "removed_partitions": 0,
        }

    removed_events = 0
    removed_partitions = 0

    cutoff_date = (
        cutoff_time.date()
    )

    with _WRITE_LOCK:

        for path in sorted(
            root.glob("*.jsonl")
        ):
            try:
                partition_date = (
                    datetime.strptime(
                        path.stem,
                        "%Y-%m-%d",
                    ).date()
                )
            except ValueError:
                continue

            if partition_date < cutoff_date:
                with path.open(
                    encoding="utf-8",
                ) as handle:
                    removed_events += sum(
                        1
                        for line in handle
                        if line.strip()
                    )

                path.unlink()
                removed_partitions += 1
                continue

            if partition_date > cutoff_date:
                continue

            kept = []

            with path.open(
                encoding="utf-8",
            ) as handle:

                for raw_line in handle:
                    line = raw_line.strip()

                    if not line:
                        continue

                    try:
                        event = json.loads(
                            line
                        )

                        event_time = (
                            _parse_time(
                                event.get(
                                    "started_at"
                                )
                            )
                        )

                    except Exception:
                        kept.append(
                            line
                        )
                        continue

                    if (
                        event_time is not None
                        and event_time < cutoff_time
                    ):
                        removed_events += 1
                    else:
                        kept.append(
                            line
                        )

            temporary = path.with_suffix(
                ".jsonl.tmp"
            )

            with temporary.open(
                "w",
                encoding="utf-8",
            ) as handle:

                for line in kept:
                    handle.write(
                        line + "\n"
                    )

            temporary.replace(
                path
            )

    return {
        "removed_events": (
            removed_events
        ),
        "removed_partitions": (
            removed_partitions
        ),
    }
