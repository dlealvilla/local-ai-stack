"""How much Kultrun actually knows about a host shape.

`docs/PRODUCT_VISION.md` §89 defines five support tiers so the product can
support broad hardware "without pretending every environment has identical
guarantees". This module is the only place Kultrun makes such a claim.

A tier is **earned from the acceptance level reached on that shape**, never
declared. `L4` certifies, `L3` supports, `L2` qualifies as compatible, a
captured observation alone is experimental, and a known incompatibility is
unsupported. Written this way a tier cannot get ahead of its evidence.

The matrix is data rather than logic, so a support claim cannot scatter into
branches. A shape absent from it is experimental — the honest answer for
hardware nobody has run.
"""

from __future__ import annotations

from dataclasses import dataclass

from kultrun.host.contracts import (
    AcceleratorVendor,
    Architecture,
    DeploymentProfile,
    HostCapabilities,
)


@dataclass(frozen=True, slots=True)
class ShapeKey:
    """The hardware, software and environment shape a claim applies to.

    Deliberately coarse. One validated NVIDIA system does not certify every
    NVIDIA system, but a claim keyed to an exact GPU model would never match
    anything twice and would make the ladder useless.
    """

    os_name: str
    architecture: Architecture
    accelerator_vendor: AcceleratorVendor

    def describe(self) -> str:
        return (
            f"{self.os_name}/{self.architecture.value}/"
            f"{self.accelerator_vendor.value}"
        )


#: The support matrix. Every entry is a claim backed by acceptance evidence
#: recorded in a stage package; nothing is listed on expectation.
SUPPORT_MATRIX: dict[ShapeKey, DeploymentProfile] = {
    # Stage 1.1, L2: real discovery proven on the reference host. Inference
    # is not proven, so this is Compatible and not Supported.
    ShapeKey("linux", Architecture.X86_64, AcceleratorVendor.NVIDIA): (
        DeploymentProfile.COMPATIBLE
    ),
}


def shape_of(capabilities: HostCapabilities) -> ShapeKey:
    """The shape this host belongs to."""
    vendors = {accelerator.vendor for accelerator in capabilities.accelerators}
    if not vendors:
        vendor = AcceleratorVendor.UNKNOWN
    elif len(vendors) == 1:
        vendor = next(iter(vendors))
    else:
        # A heterogeneous host is its own shape and nothing has validated one.
        vendor = AcceleratorVendor.UNKNOWN
    return ShapeKey(
        os_name=capabilities.operating_environment.os_name.lower(),
        architecture=capabilities.operating_environment.architecture,
        accelerator_vendor=vendor,
    )


def classify(capabilities: HostCapabilities) -> DeploymentProfile:
    """The profile this host's shape has earned.

    Never raises and never refuses. An unrecognised shape is experimental,
    because a platform that will not describe unusual hardware cannot tell
    its administrator why — and fail-closed governs mutations, not existence.
    """
    return SUPPORT_MATRIX.get(shape_of(capabilities), DeploymentProfile.EXPERIMENTAL)
