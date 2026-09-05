"""The discovery seam.

`docs/ARCHITECTURE.md` Part IX: no concrete hardware-discovery technology is
part of Kultrun's core. hwloc, vendor management interfaces, native OS
sources and anything comparable are implementations of this one port.

A provider **observes**. It does not decide, and — under Law 5 — it has no
import path to `model`, `planning`, `resource`, `runtime` or `inference`, so
the restriction is structural rather than a request.

A provider also **never installs**. It may report that a prerequisite is
missing; acting on that belongs to `install`. A component that both inspects
a machine and modifies it cannot be safely run to find out what is there.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.host.contracts import ProviderReport
from kultrun.kernel.ids import Name


@runtime_checkable
class HostDiscoveryProvider(Protocol):
    """Something that can observe part of a host."""

    @property
    def provider(self) -> Name:
        """Which provider this is, as it appears in provenance."""
        ...

    @property
    def reports_accelerator_assignment(self) -> bool:
        """Whether this provider sees only devices assigned to this context.

        This is the one declared capability that carries a reconciliation
        rule, and it exists because of a measured disagreement rather than a
        guess. On the Stage 1.1 reference host, PCI enumeration found four
        NVIDIA devices while the vendor interface found one: the other three
        are physically present on the machine and not assigned to this
        container. Trusting the enumeration would have claimed four times
        the accelerator memory that exists.

        A provider that answers True is describing what this platform
        instance may actually use. A provider that answers False is
        describing the hardware it can see, which in a container is a
        superset. See `docs/ARCHITECTURE.md` Part IV `host`.
        """
        ...

    def observe(self) -> ProviderReport:
        """Report what this provider can see, honestly and partially.

        Must not raise for an ordinary failure. An absent tool, a timeout or
        unparseable output is a `ProviderReport` with a status and a reason —
        "that source was unavailable" is a fact the platform needs, and it is
        different from "this host has no accelerator".
        """
        ...
