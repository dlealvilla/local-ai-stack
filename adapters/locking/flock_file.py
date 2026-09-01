import fcntl
import json
import os

from pathlib import Path


def try_acquire(
    path,
    *,
    owner=None,
):
    """
    Attempt one non-blocking exclusive flock.

    Returns an open file handle when acquired.
    Returns None when another process owns the lock.

    The kernel flock is authoritative.
    Owner metadata is diagnostic only.
    """

    path = Path(
        path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    handle = path.open(
        "a+",
        encoding="utf-8",
    )

    try:
        fcntl.flock(
            handle.fileno(),
            (
                fcntl.LOCK_EX
                | fcntl.LOCK_NB
            ),
        )

    except BlockingIOError:
        handle.close()
        return None

    #
    # Diagnostic owner information.
    #
    # A crashed process automatically loses flock ownership.
    # Therefore this text must NEVER be treated as authoritative
    # lock state.
    #

    payload = owner or {}

    payload = {
        **payload,
        "pid": int(
            os.getpid()
        ),
    }

    handle.seek(
        0
    )

    handle.truncate()

    json.dump(
        payload,
        handle,
        sort_keys=True,
    )

    handle.write(
        "\n"
    )

    handle.flush()

    return handle


def release(
    handle,
):
    if handle is None:
        return

    try:
        handle.seek(
            0
        )

        handle.truncate()

        handle.flush()

    finally:
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_UN,
            )

        finally:
            handle.close()


def read_owner(
    path,
):
    """
    Read diagnostic owner metadata.

    This does NOT prove whether the lock is currently held.
    """

    path = Path(
        path
    )

    if not path.exists():
        return None

    try:
        raw = (
            path.read_text()
            .strip()
        )

    except OSError:
        return None

    if not raw:
        return None

    try:
        return json.loads(
            raw
        )

    except json.JSONDecodeError:
        return {
            "unparsed": raw,
        }
