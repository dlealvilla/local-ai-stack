from adapters.model_manifest import (
    get_model_manifest_adapter,
)


MODEL_REMOTE_STORAGE_PREFLIGHT_SCHEMA_VERSION = 1


def resolve_huggingface_repository_manifest(
    repo_id,
    *,
    revision="main",
):
    """
    Resolve the full repository footprint for one exact Hugging Face
    revision without downloading the model.

    HIGH confidence is granted only when:

        a concrete revision resolves
        at least one repository file exists
        every repository file has a byte size
        total_bytes is positive

    The current Hugging Face transfer worker downloads the complete
    unfiltered snapshot, so this manifest represents its artifact
    transfer scope.
    """

    adapter = (
        get_model_manifest_adapter(
            "huggingface"
        )
    )


    payload = (
        adapter.inspect_repository(
            repo_id=repo_id,

            revision=revision,
        )
    )


    resolved_revision = (
        payload.get(
            "resolved_revision"
        )
    )

    total_bytes = (
        payload.get(
            "total_bytes"
        )
    )

    file_count = int(
        payload.get(
            "file_count"
        )
        or 0
    )

    all_sizes = bool(
        payload.get(
            "all_file_sizes_resolved",
            False,
        )
    )


    if (
        not resolved_revision
        or not all_sizes
        or file_count <= 0
        or total_bytes is None
        or int(
            total_bytes
        )
        <= 0
    ):
        return {
            "schema_version": (
                MODEL_REMOTE_STORAGE_PREFLIGHT_SCHEMA_VERSION
            ),

            "resolved": False,

            "provider": (
                "huggingface"
            ),

            "repo_id": (
                repo_id
            ),

            "requested_revision": (
                revision
            ),

            "resolved_revision": (
                resolved_revision
            ),

            "bytes": None,

            "file_count": (
                file_count
            ),

            "confidence": (
                "unknown"
            ),

            "exactness": (
                "repository_manifest_incomplete"
            ),

            "missing_size_files": (
                payload.get(
                    "missing_size_files"
                )
                or []
            ),
        }


    return {
        "schema_version": (
            MODEL_REMOTE_STORAGE_PREFLIGHT_SCHEMA_VERSION
        ),

        "resolved": True,

        "provider": (
            "huggingface"
        ),

        "repo_id": (
            repo_id
        ),

        "requested_revision": (
            revision
        ),

        "resolved_revision": (
            resolved_revision
        ),

        "bytes": int(
            total_bytes
        ),

        "file_count": (
            file_count
        ),

        "confidence": (
            "high"
        ),

        "exactness": (
            "full_repository_manifest_at_resolved_revision"
        ),

        "missing_size_files": [],
    }


def build_huggingface_storage_candidate(
    repo_id,
    *,
    revision="main",
):
    """
    Produce a normal model-shaped candidate that existing storage
    requirement estimators can consume.
    """

    manifest = (
        resolve_huggingface_repository_manifest(
            repo_id,

            revision=revision,
        )
    )


    if not manifest[
        "resolved"
    ]:
        return {
            "model_id": repo_id,

            "source": {
                "provider": (
                    "huggingface"
                ),

                "source_model_id": (
                    repo_id
                ),

                "revision": (
                    revision
                ),
            },

            "size": {},

            "remote_manifest": (
                manifest
            ),
        }


    return {
        "model_id": repo_id,

        "source": {
            "provider": (
                "huggingface"
            ),

            "source_model_id": (
                repo_id
            ),

            #
            # Hard-commit sizing must be tied to the immutable
            # revision resolved by the manifest.
            #
            "revision": (
                manifest[
                    "resolved_revision"
                ]
            ),
        },

        "size": {
            "manifest_bytes": (
                manifest[
                    "bytes"
                ]
            ),
        },

        "remote_manifest": (
            manifest
        ),
    }
