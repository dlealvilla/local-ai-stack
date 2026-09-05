"""Provisioning through the host distribution's package manager.

The mechanism approved for the Linux reference environment. It is an
implementation detail behind `install`: no distribution name and no package
manager appears in a core contract, and `docs/DEBT.md` DC-07 records the
verified-release-artifact mechanism as deferred.

Deliberately narrow. It supports exactly the environment it was validated
on, and `supports()` returns False elsewhere rather than guessing — a
provisioner that claims a host it has never run on is worse than no
provisioner, because the failure arrives later and further from the cause.

Nothing here is generic. There is no second package manager, no mirror, no
offline path and no download. One mechanism, one validated environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Final

from kultrun.components.contracts import ComponentRequirement
from kultrun.kernel.ids import Name

MECHANISM: Final = Name("apt")

#: Which requirement maps to which package. A map rather than an assumption
#: that the component and the package share a name, because they frequently
#: do not, and guessing produces a confusing failure.
_PACKAGES: Final = {"hwloc": ("hwloc",)}

#: Long enough for a package index refresh on a cold container.
_TIMEOUT_SECONDS: Final = 300.0


class AptProvisioner:
    """Installs a component with the system package manager."""

    mechanism = MECHANISM

    def __init__(self, *, root: Path | None = None) -> None:
        self._root = root or Path("/")

    def supports(self, requirement: ComponentRequirement) -> bool:
        """Only a Debian-family host, and only a component we have mapped."""
        if requirement.component.value not in _PACKAGES:
            return False
        if shutil.which("apt-get") is None:
            return False
        return (self._root / "etc" / "debian_version").exists()

    def provision(self, requirement: ComponentRequirement) -> tuple[bool, str]:
        """Refresh the index once, then install. Reports rather than raises."""
        packages = _PACKAGES.get(requirement.component.value)
        if packages is None:
            return False, f"no package mapping for {requirement.component}"

        environment = {
            **os.environ,
            "DEBIAN_FRONTEND": "noninteractive",
        }
        for argv in (
            ["apt-get", "update", "-qq"],
            ["apt-get", "install", "-y", "-qq", *packages],
        ):
            try:
                finished = subprocess.run(  # fixed argv, never a shell
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=_TIMEOUT_SECONDS,
                    check=False,
                    env=environment,
                )
            except subprocess.TimeoutExpired:
                return False, f"{argv[0]} {argv[1]} exceeded {_TIMEOUT_SECONDS:g}s"
            except OSError as error:
                return False, f"{argv[0]}: {error}"
            if finished.returncode != 0:
                return False, (
                    f"{' '.join(argv[:2])} exited {finished.returncode}: "
                    f"{finished.stderr.strip()[:200]}"
                )
        return True, f"installed {' '.join(packages)} with {MECHANISM}"


def build(root: Path | None = None) -> AptProvisioner:
    """Factory for the adapter registry."""
    return AptProvisioner(root=root)
