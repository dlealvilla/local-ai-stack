"""StateRootBinder (MACHI 1.2.1).

Resolve, normalize, establish, and return the filesystem root under
which this Machi installation's managed state will subsequently live.

This Component does not prove ownership, mint an InstallRun, scan
siblings, reclaim storage, or measure capacity.
"""

from __future__ import annotations

import os
from pathlib import Path

from machi.install.contracts import SelectionSource, StateRootBinding
from machi.install.defaults import (
    KULTRUN_OWNER_FILENAME,
    KULTRUN_SYSTEM_ROOT,
    platform_default_state_root,
)
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import PersistenceError, ValidationError


class StateRootBinder:
    """Bind one state root for this process.

    Precedence, applied by this object and not by Kernel:

    1. explicit invocation path
    2. ``MACHI_STATE_ROOT`` value supplied by the composition root
    3. platform default

    The binder does not read ``os.environ``. Blank or whitespace
    environment values are not a configuration.
    """

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        default_root: Path | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._default_root = Path(default_root) if default_root is not None else None

    def bind(
        self,
        *,
        explicit: str | Path | None = None,
        environment: str | None = None,
    ) -> StateRootBinding:
        """Resolve and establish one state root. May create the directory."""
        source, raw = self._select(explicit=explicit, environment=environment)
        path = self._normalize(raw)
        self._refuse_reserved(path)
        existed = path.exists()
        if existed:
            if not path.is_dir():
                raise ValidationError(
                    "state root exists and is not a directory",
                    path=str(path),
                )
            self._refuse_kultrun_marker(path)
            created = False
        else:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise PersistenceError(
                    "failed to create the state root",
                    path=str(path),
                ) from exc
            if not path.is_dir():
                raise PersistenceError(
                    "state root was not a directory after creation",
                    path=str(path),
                )
            created = True
        self._require_writable(path)
        return StateRootBinding(
            root=str(path),
            selection_source=source,
            existed=existed,
            created=created,
            bound_at=self._clock.now(),
        )

    def _select(
        self,
        *,
        explicit: str | Path | None,
        environment: str | None,
    ) -> tuple[SelectionSource, str]:
        if explicit is not None:
            text = _require_text(explicit, what="explicit state root")
            return SelectionSource.EXPLICIT, text
        if environment is not None:
            text = str(environment).strip()
            if text:
                return SelectionSource.ENVIRONMENT, text
        default = self._default_root or platform_default_state_root()
        return SelectionSource.PLATFORM_DEFAULT, str(default)

    def _normalize(self, raw: str) -> Path:
        if "\x00" in raw:
            raise ValidationError("state root path must not contain a NUL byte")
        text = raw.strip()
        if not text:
            raise ValidationError("state root path must not be empty")
        try:
            path = Path(text).expanduser().resolve()
        except (OSError, RuntimeError) as exc:
            raise ValidationError(
                "state root path could not be normalized",
                path=text,
            ) from exc
        if not path.is_absolute():
            raise ValidationError(
                "state root must resolve to an absolute path",
                path=str(path),
            )
        return path

    def _refuse_reserved(self, path: Path) -> None:
        if path.parent == path:
            raise ValidationError(
                "refusing to bind the filesystem root as a Machi state root",
                path=str(path),
            )
        try:
            if path == KULTRUN_SYSTEM_ROOT.resolve():
                raise ValidationError(
                    "refusing to bind the Kultrun system state root; "
                    "Machi and Kultrun must remain distinguishable",
                    path=str(path),
                )
        except OSError:
            if path == KULTRUN_SYSTEM_ROOT:
                raise ValidationError(
                    "refusing to bind the Kultrun system state root; "
                    "Machi and Kultrun must remain distinguishable",
                    path=str(path),
                ) from None

    def _refuse_kultrun_marker(self, path: Path) -> None:
        marker = path / KULTRUN_OWNER_FILENAME
        if marker.is_file():
            raise ValidationError(
                "refusing to bind a tree that already carries Kultrun "
                "ownership evidence; Steward may reason about it later",
                path=str(path),
            )

    def _require_writable(self, path: Path) -> None:
        if not os.access(path, os.W_OK):
            raise PersistenceError(
                "state root is not writable",
                path=str(path),
            )


def _require_text(value: str | Path, *, what: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValidationError(f"{what} must not be empty")
    return text
