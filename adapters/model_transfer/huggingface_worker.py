import argparse
import json
import os

from huggingface_hub import (
    HfApi,
    snapshot_download,
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

    parser.add_argument(
        "--destination",
        required=True,
    )

    args = parser.parse_args()

    token = os.environ.get(
        "HF_TOKEN"
    )

    api = HfApi()

    info = api.model_info(
        repo_id=args.repo_id,
        revision=args.revision,
        token=token,
    )

    resolved_revision = info.sha

    local_path = snapshot_download(
        repo_id=args.repo_id,
        revision=resolved_revision,
        local_dir=args.destination,
        token=token,
    )

    print(
        json.dumps({
            "repo_id": args.repo_id,
            "requested_revision": (
                args.revision
            ),
            "resolved_revision": (
                resolved_revision
            ),
            "local_path": local_path,
        })
    )


if __name__ == "__main__":
    main()
