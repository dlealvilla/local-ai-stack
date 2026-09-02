import errno
import os
import tempfile
import time

from pathlib import Path

from core.config import load_config


STORAGE_PROBE_SCHEMA_VERSION = 1


#
# Sentinel for "resolve the ceiling from configuration", which is what
# every existing caller wants and gets by not passing the argument.
#
# An explicit `max_probe_bytes=None` means no ceiling at all. Host
# characterization uses that; its bound is an iteration budget rather
# than a probe size.
#
USE_CONFIGURED_PROBE_CEILING = object()


def _resolve_probe_directory(
    config,
):
    settings = config.get(
        "storage_capacity",
        {},
    )

    configured = Path(
        settings.get(
            "probe_directory",
            "data/capacity-probes",
        )
    )

    if configured.is_absolute():
        return configured

    return (
        Path(
            config[
                "platform"
            ][
                "data_root"
            ]
        )
        / configured
    )


def probe_required_capacity(
    requested_bytes,
    *,
    config=None,
    max_probe_bytes=USE_CONFIGURED_PROBE_CEILING,
):
    """
    Empirically test whether the filesystem can reserve
    requested_bytes right now.

    The temporary reservation is deleted immediately.

    This answers:

        "Can this filesystem reserve X bytes?"

    It does NOT answer:

        "What is the absolute remaining quota?"

    A bounded discovery algorithm can be layered on top later.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    if not settings.get(
        "probe_enabled",
        False,
    ):
        return {
            "schema_version": (
                STORAGE_PROBE_SCHEMA_VERSION
            ),
            "supported": True,
            "success": False,
            "reason": "probe_disabled",
        }

    try:
        requested_bytes = int(
            requested_bytes
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "requested_bytes must be an integer."
        ) from exc

    if requested_bytes <= 0:
        raise ValueError(
            "requested_bytes must be positive."
        )

    #
    # Ceiling resolution, in order of specificity:
    #
    #   argument omitted  -> configured `probe_max_gb`, unchanged
    #   explicit None     -> no ceiling
    #   explicit integer  -> that ceiling
    #
    if max_probe_bytes is USE_CONFIGURED_PROBE_CEILING:
        max_probe_bytes = int(
            float(
                settings.get(
                    "probe_max_gb",
                    64.0,
                )
            )
            * (1024 ** 3)
        )

    elif max_probe_bytes is not None:
        max_probe_bytes = int(
            max_probe_bytes
        )

        if max_probe_bytes <= 0:
            raise ValueError(
                "max_probe_bytes must be positive "
                "or None"
            )

    if (
        max_probe_bytes is not None
        and requested_bytes > max_probe_bytes
    ):
        return {
            "schema_version": (
                STORAGE_PROBE_SCHEMA_VERSION
            ),
            "supported": True,
            "success": False,
            "reason": "probe_limit_exceeded",
            "requested_bytes": (
                requested_bytes
            ),
            "max_probe_bytes": (
                max_probe_bytes
            ),
        }

    directory = (
        _resolve_probe_directory(
            config
        )
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd = None
    path = None

    started = time.monotonic()

    try:
        fd, raw_path = tempfile.mkstemp(
            prefix="capacity-probe-",
            suffix=".tmp",
            dir=directory,
        )

        path = Path(
            raw_path
        )

        if hasattr(
            os,
            "posix_fallocate",
        ):
            method = "posix_fallocate"

            os.posix_fallocate(
                fd,
                0,
                requested_bytes,
            )

        else:
            return {
                "schema_version": (
                    STORAGE_PROBE_SCHEMA_VERSION
                ),
                "supported": False,
                "success": False,
                "reason": (
                    "posix_fallocate_unavailable"
                ),
                "requested_bytes": (
                    requested_bytes
                ),
            }

        stat = os.fstat(
            fd
        )

        # Some FUSE/network filesystems report st_blocks=0
        # even after a successful reservation.
        #
        # Keep this as an observation only.
        reported_allocated_bytes = int(
            stat.st_blocks
            * 512
        )

        elapsed = (
            time.monotonic()
            - started
        )

        return {
            "schema_version": (
                STORAGE_PROBE_SCHEMA_VERSION
            ),

            "supported": True,
            "success": True,

            "method": method,

            "requested_bytes": (
                requested_bytes
            ),

            # POSIX success means the reservation call was
            # accepted. This is the useful empirical result.
            "reservation_accepted": True,

            # This field is diagnostic only and may be zero on
            # FUSE/network filesystems.
            "reported_allocated_bytes": (
                reported_allocated_bytes
            ),

            "allocation_visibility": (
                "observable"
                if reported_allocated_bytes > 0
                else "not_reported"
            ),

            "duration_seconds": (
                round(
                    elapsed,
                    6,
                )
            ),

            "reason": None,
        }

    except OSError as exc:
        elapsed = (
            time.monotonic()
            - started
        )

        known = {
            errno.ENOSPC: (
                "no_space"
            ),
            errno.EDQUOT: (
                "quota_exceeded"
            ),
            errno.EFBIG: (
                "file_too_large"
            ),
            errno.EOPNOTSUPP: (
                "operation_not_supported"
            ),
        }

        reason = known.get(
            exc.errno,
            (
                "os_error_"
                + str(
                    exc.errno
                )
            ),
        )

        return {
            "schema_version": (
                STORAGE_PROBE_SCHEMA_VERSION
            ),

            "supported": (
                exc.errno
                != errno.EOPNOTSUPP
            ),

            "success": False,

            "method": (
                "posix_fallocate"
            ),

            "requested_bytes": (
                requested_bytes
            ),

            "duration_seconds": (
                round(
                    elapsed,
                    6,
                )
            ),

            "reason": reason,

            "errno": exc.errno,

            "detail": str(
                exc
            ),
        }

    finally:
        if fd is not None:
            try:
                os.close(
                    fd
                )
            except OSError:
                pass

        if path is not None:
            try:
                path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass
