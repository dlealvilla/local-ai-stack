import time

from contextlib import (
    contextmanager,
)

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path


from adapters.locking import (
    get_lock_adapter,
)

from core.config import (
    load_config,
)


STORAGE_OPERATION_LOCK_SCHEMA_VERSION = 1


class StorageOperationBusyError(
    RuntimeError
):
    pass


def _utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def resolve_storage_operation_lock_path(
    config=None,
):
    """
    Resolve the shared host-local storage-operation lock.

    WORKING compatibility rule:

    storage_operation_lock_path and maintenance_lock_path must
    resolve to the same file while maintenance calibration still
    uses the legacy maintenance-specific configuration key.

    This prevents an administrator from accidentally configuring
    model mutations and maintenance sonar to use independent locks.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    operation_value = settings.get(
        "storage_operation_lock_path"
    )

    maintenance_value = settings.get(
        "maintenance_lock_path"
    )


    if (
        operation_value
        and maintenance_value
    ):
        operation_path = Path(
            operation_value
        ).expanduser()

        maintenance_path = Path(
            maintenance_value
        ).expanduser()


        if (
            operation_path.resolve()
            != maintenance_path.resolve()
        ):
            raise ValueError(
                "storage_operation_lock_path and "
                "maintenance_lock_path must currently "
                "reference the same lock file."
            )


    selected = (
        operation_value
        or maintenance_value
    )


    if not selected:
        selected = (
            "/opt/ai-stack/runtime/locks/"
            "storage-capacity.lock"
        )


    path = Path(
        selected
    ).expanduser()


    if not path.is_absolute():
        raise ValueError(
            "Storage operation lock path must be absolute "
            "so the current flock adapter remains host-local."
        )


    return path


@contextmanager
def storage_operation_lock(
    operation,
    *,
    config=None,
    wait_seconds=None,
    poll_seconds=0.05,
    provider="flock_file",
):
    """
    Serialize one platform-managed storage operation.

    Intended future critical section:

        acquire lock
            ->
        rebuild current storage plan
            ->
        calculate/resolve operation requirement
            ->
        commit-time verification
            ->
        execute mutation
            ->
        advance generation / invalidate cache
            ->
        release lock

    Maintenance calibration uses the same underlying lock path,
    preventing it from overlapping future model mutations.

    Current behavior is fail-fast by default.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )


    if wait_seconds is None:
        wait_seconds = float(
            settings.get(
                "storage_operation_lock_wait_seconds",
                0.0,
            )
        )

    else:
        wait_seconds = float(
            wait_seconds
        )


    poll_seconds = float(
        poll_seconds
    )


    if wait_seconds < 0:
        raise ValueError(
            "wait_seconds cannot be negative"
        )


    if poll_seconds <= 0:
        raise ValueError(
            "poll_seconds must be positive"
        )


    path = (
        resolve_storage_operation_lock_path(
            config
        )
    )


    adapter = get_lock_adapter(
        provider
    )


    started = time.monotonic()

    handle = None


    while handle is None:

        handle = adapter.try_acquire(
            path,

            owner={
                "schema_version": (
                    STORAGE_OPERATION_LOCK_SCHEMA_VERSION
                ),

                "operation": str(
                    operation
                ),

                "acquired_at": (
                    _utc_now()
                ),

                "provider": (
                    provider
                ),
            },
        )


        if handle is not None:
            break


        elapsed = (
            time.monotonic()
            - started
        )


        if (
            wait_seconds <= 0
            or elapsed >= wait_seconds
        ):
            raise StorageOperationBusyError(
                "Another platform storage operation "
                "currently owns the shared storage lock."
            )


        remaining = (
            wait_seconds
            - elapsed
        )

        time.sleep(
            min(
                poll_seconds,
                max(
                    0.0,
                    remaining
                ),
            )
        )


    session = {
        "schema_version": (
            STORAGE_OPERATION_LOCK_SCHEMA_VERSION
        ),

        "operation": str(
            operation
        ),

        "provider": (
            provider
        ),

        "lock_path": str(
            path
        ),

        "acquired": True,

        "acquired_at": (
            _utc_now()
        ),

        "wait_seconds": (
            wait_seconds
        ),
    }


    try:
        yield session

    finally:
        adapter.release(
            handle
        )
