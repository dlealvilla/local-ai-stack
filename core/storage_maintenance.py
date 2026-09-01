import fcntl
import os
import tempfile

from contextlib import (
    contextmanager,
)

from pathlib import Path

from adapters.maintenance import (
    get_maintenance_lifecycle_adapter,
)

from core.config import (
    load_config,
)


STORAGE_MAINTENANCE_SCHEMA_VERSION = 1


def _resolve_data_path(
    value,
    *,
    data_root,
):
    path = Path(
        value
    )

    if path.is_absolute():
        return path

    return (
        data_root
        / path
    )


def _create_emergency_reserve(
    *,
    directory,
    reserve_bytes,
):
    """
    Reserve recoverable emergency headroom on the target storage.

    A successful posix_fallocate call is treated as reservation
    acceptance.

    As observed on the current RunPod FUSE volume, st_blocks may
    remain zero, so physical block visibility is diagnostic only.
    """

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd = None
    path = None

    try:
        fd, raw_path = tempfile.mkstemp(
            prefix=(
                "emergency-reserve-"
            ),

            suffix=".tmp",

            dir=directory,
        )

        path = Path(
            raw_path
        )

        if not hasattr(
            os,
            "posix_fallocate",
        ):
            raise RuntimeError(
                "posix_fallocate is unavailable"
            )

        os.posix_fallocate(
            fd,
            0,
            int(
                reserve_bytes
            ),
        )

        info = os.fstat(
            fd
        )

        return {
            "accepted": True,

            "path": str(
                path
            ),

            "requested_bytes": int(
                reserve_bytes
            ),

            "logical_size_bytes": int(
                info.st_size
            ),

            "reported_allocated_bytes": int(
                getattr(
                    info,
                    "st_blocks",
                    0,
                )
                * 512
            ),

            "method": (
                "posix_fallocate"
            ),
        }

    except Exception:
        if path is not None:
            try:
                path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

        raise

    finally:
        if fd is not None:
            try:
                os.close(
                    fd
                )
            except OSError:
                pass


def _release_emergency_reserve(
    reserve,
):
    if not reserve:
        return {
            "released": False,
            "reason": "no_reserve",
        }

    path_value = reserve.get(
        "path"
    )

    if not path_value:
        return {
            "released": False,
            "reason": "reserve_path_missing",
        }

    path = Path(
        path_value
    )

    existed = path.exists()

    path.unlink(
        missing_ok=True
    )

    return {
        "released": True,

        "previously_existed": (
            existed
        ),

        "path": str(
            path
        ),
    }


@contextmanager
def storage_maintenance_session(
    *,
    config=None,
    emergency_reserve_bytes=None,
    lifecycle_provider="current_cli",
):
    """
    Enter a controlled storage-maintenance session.

    Sequence:

        acquire host-local maintenance lock
        capture workload state
        refuse unsafe partial state
        quiesce platform workload
        create emergency storage reserve
        yield control to diagnostic/calibration operation
        release emergency reserve
        restore original workload state
        release maintenance lock

    Restoration occurs in finally even when the diagnostic body
    raises an exception.

    IMPORTANT:
    This does NOT run Capacity Sonar itself.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    data_root = Path(
        config[
            "platform"
        ][
            "data_root"
        ]
    ).resolve()

    lock_path = Path(
        settings.get(
            "maintenance_lock_path",
            (
                "/opt/ai-stack/runtime/"
                "locks/storage-capacity.lock"
            ),
        )
    )

    reserve_directory = (
        _resolve_data_path(
            settings.get(
                "maintenance_reserve_directory",
                "data/capacity-reserve",
            ),

            data_root=data_root,
        )
    )

    if emergency_reserve_bytes is None:
        emergency_reserve_bytes = int(
            float(
                settings.get(
                    "maintenance_emergency_reserve_gb",
                    2.0,
                )
            )
            * 1024
            * 1024
            * 1024
        )

    emergency_reserve_bytes = int(
        emergency_reserve_bytes
    )

    if emergency_reserve_bytes <= 0:
        raise ValueError(
            "Emergency reserve must be positive"
        )

    timeout_seconds = int(
        settings.get(
            "maintenance_lifecycle_timeout_seconds",
            600,
        )
    )

    lifecycle = (
        get_maintenance_lifecycle_adapter(
            lifecycle_provider
        )
    )

    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lock_handle = lock_path.open(
        "a+"
    )

    lock_acquired = False
    prior_state = None
    stop_result = None
    reserve = None
    release_result = None
    restore_result = None

    try:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                (
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB
                ),
            )

        except BlockingIOError as exc:
            raise RuntimeError(
                "Another storage maintenance session "
                "already holds the maintenance lock."
            ) from exc

        lock_acquired = True

        prior_state = (
            lifecycle.capture_workload_state()
        )

        lifecycle.validate_restorable_state(
            prior_state
        )

        stop_result = (
            lifecycle.stop_for_maintenance(
                prior_state,

                timeout_seconds=(
                    timeout_seconds
                ),
            )
        )

        quiesced_state = (
            lifecycle.capture_workload_state()
        )

        if quiesced_state[
            "mode"
        ] not in {
            "all_stopped",
            "no_enabled_services",
        }:
            raise RuntimeError(
                "Workload did not enter a safe "
                "quiesced maintenance state."
            )

        reserve = (
            _create_emergency_reserve(
                directory=(
                    reserve_directory
                ),

                reserve_bytes=(
                    emergency_reserve_bytes
                ),
            )
        )

        session = {
            "schema_version": (
                STORAGE_MAINTENANCE_SCHEMA_VERSION
            ),

            "lock": {
                "path": str(
                    lock_path
                ),

                "acquired": True,
            },

            "prior_state": (
                prior_state
            ),

            "stop_result": (
                stop_result
            ),

            "quiesced_state": (
                quiesced_state
            ),

            "emergency_reserve": (
                reserve
            ),

            "maintenance_sonar_enabled": bool(
                settings.get(
                    "maintenance_sonar_enabled",
                    False,
                )
            ),

            "boundary_search_enabled": bool(
                settings.get(
                    "boundary_search_enabled",
                    False,
                )
            ),
        }

        yield session

    finally:
        #
        # Release storage headroom BEFORE restarting workloads.
        #

        if reserve is not None:
            try:
                release_result = (
                    _release_emergency_reserve(
                        reserve
                    )
                )

            except Exception as exc:
                release_result = {
                    "released": False,

                    "reason": (
                        "reserve_release_failed"
                    ),

                    "detail": str(
                        exc
                    ),
                }

        #
        # Restore the state captured before maintenance.
        #

        if prior_state is not None:
            try:
                restore_result = (
                    lifecycle.restore_after_maintenance(
                        prior_state,

                        timeout_seconds=(
                            timeout_seconds
                        ),
                    )
                )

            except Exception as exc:
                #
                # Restoration failure is critical.
                #
                # Raise after releasing the lock below.
                #

                restore_result = {
                    "performed": True,

                    "restored": False,

                    "error": str(
                        exc
                    ),
                }

        if lock_acquired:
            try:
                fcntl.flock(
                    lock_handle.fileno(),
                    fcntl.LOCK_UN,
                )

            except OSError:
                pass

        lock_handle.close()

        if (
            restore_result is not None
            and restore_result.get(
                "restored"
            )
            is False
        ):
            raise RuntimeError(
                "Maintenance workload restoration failed: "
                + str(
                    restore_result.get(
                        "error"
                    )
                )
            )
