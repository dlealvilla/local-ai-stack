def get_lock_adapter(
    provider="flock_file",
):
    """
    Resolve the current host-local locking implementation.

    Core owns the storage-operation locking concept.
    The adapter owns the platform-specific lock mechanism.
    """

    if provider == "flock_file":
        from adapters.locking import (
            flock_file,
        )

        return flock_file

    raise ValueError(
        "Unknown lock adapter provider: "
        + str(
            provider
        )
    )
