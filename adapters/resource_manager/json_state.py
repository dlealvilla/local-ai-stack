"""Atomic JSON workload-state adapter.

AI_DEPLOYMENT_PHASE9_RESOURCE_MANAGER_V1
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from core.resource_manager import (
    WorkloadRecord,
)


class JsonFileWorkloadStateStore:
    FORMAT_VERSION = 1

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)

    def load(self) -> list[WorkloadRecord]:
        if not self.path.exists():
            return []

        with self.path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            payload = json.load(handle)

        if payload.get(
            "format_version"
        ) != self.FORMAT_VERSION:
            raise ValueError(
                "unsupported workload-state format"
            )

        workloads = payload.get(
            "workloads"
        )

        if not isinstance(workloads, list):
            raise ValueError(
                "workload-state workloads must be a list"
            )

        return [
            WorkloadRecord.from_dict(
                value
            )
            for value in workloads
        ]

    def save(
        self,
        workloads: Iterable[WorkloadRecord],
    ) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "format_version":
                self.FORMAT_VERSION,
            "workloads": [
                workload.to_dict()
                for workload in workloads
            ],
        }

        temporary = self.path.with_name(
            f".{self.path.name}.tmp-{os.getpid()}"
        )

        try:
            with temporary.open(
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    payload,
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                temporary,
                self.path,
            )

            try:
                directory_fd = os.open(
                    self.path.parent,
                    os.O_RDONLY,
                )
            except OSError:
                return

            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        finally:
            if temporary.exists():
                temporary.unlink()
