import json
import threading

from pathlib import Path


_LOCK = threading.Lock()


def resolve_path(config):
    configured = Path(
        config["model_inventory"]["state_path"]
    )

    if configured.is_absolute():
        return configured

    return (
        Path(config["platform"]["data_root"])
        / configured
    )


def _load_unlocked(config):
    path = resolve_path(config)

    if not path.exists():
        return {
            "schema_version": 1,
            "records": [],
        }

    try:
        with path.open(
            encoding="utf-8",
        ) as handle:
            payload = json.load(handle)

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {
            "schema_version": 1,
            "records": [],
        }

    if not isinstance(
        payload.get("records"),
        list,
    ):
        payload["records"] = []

    return payload


def list_records(config):
    with _LOCK:
        return list(
            _load_unlocked(
                config
            )["records"]
        )


def get_record(
    inventory_id,
    config,
):
    for record in list_records(
        config
    ):
        if (
            record.get("inventory_id")
            == inventory_id
        ):
            return record

    return None


def upsert_record(
    record,
    config,
):
    """
    Persist normalized inventory metadata atomically.

    Model files themselves remain separate artifacts.
    """

    path = resolve_path(config)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _LOCK:
        payload = _load_unlocked(
            config
        )

        records = payload[
            "records"
        ]

        inventory_id = record[
            "inventory_id"
        ]

        replaced = False

        for index, existing in enumerate(
            records
        ):
            if (
                existing.get(
                    "inventory_id"
                )
                == inventory_id
            ):
                records[index] = record
                replaced = True
                break

        if not replaced:
            records.append(
                record
            )

        temporary = path.with_suffix(
            ".json.tmp"
        )

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                ensure_ascii=False,
            )

            handle.write("\n")

        temporary.replace(
            path
        )

    return record


def remove_record(
    inventory_id,
    config,
):
    """
    Remove one persistent Inventory metadata record.

    PROVISIONAL:
    The current JSON-file store performs an atomic whole-file
    rewrite. Future storage adapters can implement deletion
    according to their own persistence model.
    """

    import json

    path = resolve_path(
        config
    )

    if not path.exists():
        return False

    try:
        payload = json.loads(
            path.read_text()
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(
            "Could not read model inventory store."
        ) from exc

    removed = False

    # Current/canonical object form.
    if (
        isinstance(payload, dict)
        and isinstance(
            payload.get("records"),
            list,
        )
    ):
        original = payload["records"]

        filtered = [
            record
            for record in original
            if record.get(
                "inventory_id"
            ) != inventory_id
        ]

        removed = (
            len(filtered)
            != len(original)
        )

        payload["records"] = filtered

    # Backward-compatible list form.
    elif isinstance(
        payload,
        list,
    ):
        original = payload

        filtered = [
            record
            for record in original
            if record.get(
                "inventory_id"
            ) != inventory_id
        ]

        removed = (
            len(filtered)
            != len(original)
        )

        payload = filtered

    else:
        raise RuntimeError(
            "Unsupported model inventory "
            "store structure."
        )

    if not removed:
        return False

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(
        path.name + ".delete.tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
        )
        + "\n"
    )

    temporary.replace(
        path
    )

    return True
