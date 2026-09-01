import argparse
import json


from huggingface_hub import (
    HfApi,
)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo-id",
        required=True,
    )

    parser.add_argument(
        "--revision",
        default="main",
    )


    args = parser.parse_args()


    info = (
        HfApi()
        .model_info(
            repo_id=(
                args.repo_id
            ),

            revision=(
                args.revision
            ),

            files_metadata=True,
        )
    )


    siblings = (
        info.siblings
        or []
    )


    files = []

    missing_size = []

    total_bytes = 0


    for sibling in siblings:

        filename = str(
            sibling.rfilename
        )

        size = sibling.size


        if size is None:
            missing_size.append(
                filename
            )

            files.append({
                "path": filename,
                "size_bytes": None,
            })

            continue


        size = int(
            size
        )

        total_bytes += size


        files.append({
            "path": filename,
            "size_bytes": size,
        })


    payload = {
        "provider": (
            "huggingface"
        ),

        "repo_id": (
            args.repo_id
        ),

        "requested_revision": (
            args.revision
        ),

        "resolved_revision": (
            getattr(
                info,
                "sha",
                None,
            )
        ),

        "file_count": (
            len(
                files
            )
        ),

        "all_file_sizes_resolved": (
            len(
                missing_size
            )
            == 0
            and len(
                files
            )
            > 0
        ),

        "total_bytes": (
            total_bytes
            if (
                len(
                    missing_size
                )
                == 0
                and len(
                    files
                )
                > 0
            )
            else None
        ),

        "missing_size_files": (
            missing_size
        ),

        #
        # Keep complete file metadata available to the adapter so
        # future filtered-download policies can operate on exactly
        # the same manifest.
        #
        "files": files,
    }


    print(
        json.dumps(
            payload,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
