"""Host discovery: providers observe, Kultrun decides.

The tests that matter here are not "it parsed the file". They are the ones
that pin behaviour discovered on real hardware — above all that PCI
enumeration overcounts accelerators in a container, which would have claimed
four times the accelerator memory that exists.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from kultrun.adapters.host import hwloc, native_linux, nvidia
from kultrun.evidence.contracts import Confidence, Derivation
from kultrun.host.contracts import (
    AcceleratorVendor,
    Architecture,
    DeploymentProfile,
    HostCapabilities,
    HostId,
    Observation,
    ProviderReport,
    ProviderStatus,
)
from kultrun.host.discovery import HostDiscoveryService
from kultrun.host.fingerprint import compute
from kultrun.host.ports import HostDiscoveryProvider
from kultrun.host.profile import ShapeKey, classify, shape_of
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import from_dict, to_dict
from kultrun.kernel.unresolved import Unresolved, is_resolved

INSTANT = dt.datetime(2026, 9, 5, 12, 0, tzinfo=dt.UTC)


class FakeProvider:
    """A provider that returns exactly what a test hands it."""

    def __init__(
        self,
        name: str,
        observations: tuple[Observation, ...] = (),
        *,
        assignment_aware: bool = False,
        status: ProviderStatus = ProviderStatus.PARTIAL,
        raises: bool = False,
    ) -> None:
        self.provider = Name(name)
        self.reports_accelerator_assignment = assignment_aware
        self._observations = observations
        self._status = status
        self._raises = raises

    def observe(self) -> ProviderReport:
        if self._raises:
            raise RuntimeError("provider exploded")
        return ProviderReport(
            provider=self.provider,
            status=self._status,
            observed_at=INSTANT,
            observations=self._observations,
        )


def seen(path: str, value: object) -> Observation:
    return Observation(
        path=path,
        value=value,  # type: ignore[arg-type]
        derivation=Derivation.MEASURED,
        confidence=Confidence.HIGH,
    )


def service(*providers: HostDiscoveryProvider) -> HostDiscoveryService:
    return HostDiscoveryService(list(providers), clock=FixedClock(INSTANT))


class TestProvidersSatisfyThePort:
    @pytest.mark.parametrize(
        "provider", [hwloc.build(), nvidia.build(), native_linux.build()]
    )
    def test_each_shipped_provider(self, provider: HostDiscoveryProvider) -> None:
        assert isinstance(provider, HostDiscoveryProvider)

    def test_only_the_vendor_provider_reports_assignment(self) -> None:
        """The one declared capability that carries a reconciliation rule."""
        assert nvidia.build().reports_accelerator_assignment is True
        assert hwloc.build().reports_accelerator_assignment is False
        assert native_linux.build().reports_accelerator_assignment is False

    def test_an_absent_tool_is_a_fact_and_not_an_exception(self) -> None:
        """A missing vendor tool must not turn into a failed startup."""
        report = nvidia.NvidiaProvider(FixedClock(INSTANT)).observe()
        assert isinstance(report, ProviderReport)
        assert report.status in (
            ProviderStatus.UNAVAILABLE,
            ProviderStatus.PARTIAL,
            ProviderStatus.AVAILABLE,
        )

    def test_a_provider_that_raises_does_not_break_discovery(self) -> None:
        capabilities = service(FakeProvider("broken", raises=True)).discover()
        (report,) = capabilities.provider_reports
        assert report.status is ProviderStatus.FAILED
        assert report.detail is not None
        assert "exploded" in report.detail


class TestTheAcceleratorAssignmentRule:
    """The finding that justifies the one field-specific reconciliation rule.

    Measured on the Stage 1.1 reference host: PCI enumeration reported four
    NVIDIA display devices where the vendor interface reported one. The other
    three are physically present and not assigned to this container.
    """

    def enumeration(self) -> FakeProvider:
        return FakeProvider(
            "enumerator",
            tuple(
                seen(f"accelerator.0000:{bus}:00.0.vendor", "nvidia")
                for bus in ("81", "82", "c1", "c2")
            ),
        )

    def vendor(self) -> FakeProvider:
        return FakeProvider(
            "vendor",
            (
                seen("accelerator.0000:82:00.0.vendor", "nvidia"),
                seen("accelerator.0000:82:00.0.memory_total_bytes", 34_205_204_480),
                seen("accelerator.0000:82:00.0.model_name", "Test Accelerator"),
            ),
            assignment_aware=True,
        )

    def test_only_assigned_devices_become_accelerators(self) -> None:
        capabilities = service(self.enumeration(), self.vendor()).discover()
        assert len(capabilities.accelerators) == 1
        assert capabilities.accelerators[0].memory_total_bytes == 34_205_204_480

    def test_the_unassigned_devices_are_kept_as_evidence(self) -> None:
        """An operator asking "why only one GPU" needs to see the other three."""
        capabilities = service(self.enumeration(), self.vendor()).discover()
        (conflict,) = capabilities.conflicts
        assert conflict.path == "accelerators"
        assert conflict.resolution is not None
        assert "assignment" in conflict.resolution
        assert len(conflict.observations) == 3

    def test_without_an_assignment_aware_provider_everything_is_reported(self) -> None:
        """Enumeration alone is all we have, so it is what we report."""
        capabilities = service(self.enumeration()).discover()
        assert len(capabilities.accelerators) == 4
        assert capabilities.conflicts == ()

    def test_the_rule_is_not_a_global_vendor_precedence(self) -> None:
        """A disagreement about anything else still surfaces as a conflict."""
        capabilities = service(
            FakeProvider("enumerator", (seen("cpu.physical_cores", 64),)),
            FakeProvider(
                "vendor", (seen("cpu.physical_cores", 32),), assignment_aware=True
            ),
        ).discover()
        assert not is_resolved(capabilities.cpu.physical_cores)
        (conflict,) = capabilities.conflicts
        assert conflict.path == "cpu.physical_cores"
        assert conflict.resolution is None


class TestNormalization:
    def test_agreement_records_every_contributing_provider(self) -> None:
        """Two independent sources concurring is itself evidence."""
        capabilities = service(
            FakeProvider("a", (seen("memory.total_bytes", 1024),)),
            FakeProvider("b", (seen("memory.total_bytes", 1024),)),
        ).discover()
        assert capabilities.memory.total_bytes == 1024
        (entry,) = [
            p for p in capabilities.provenance if p.path == "memory.total_bytes"
        ]
        assert [name.value for name in entry.providers] == ["a", "b"]

    def test_what_nobody_reported_is_unresolved_and_not_zero(self) -> None:
        capabilities = service(FakeProvider("a", ())).discover()
        assert isinstance(capabilities.memory.total_bytes, Unresolved)
        assert isinstance(capabilities.cpu.physical_cores, Unresolved)
        assert capabilities.accelerators == ()

    def test_a_cpu_only_host_has_no_accelerators_and_no_false_zero(self) -> None:
        """The branch most likely to be broken by code written on a GPU box."""
        capabilities = service(
            FakeProvider("a", (seen("cpu.logical_cores", 8),))
        ).discover()
        assert capabilities.accelerators == ()
        assert capabilities.cpu.logical_cores == 8

    def test_an_unknown_vendor_normalizes_to_unknown_rather_than_failing(self) -> None:
        """A host Kultrun has never seen must still be describable."""
        capabilities = service(
            FakeProvider("a", (seen("accelerator.0000:01:00.0.vendor", "sirius"),))
        ).discover()
        assert capabilities.accelerators[0].vendor is AcceleratorVendor.UNKNOWN

    def test_an_unknown_architecture_normalizes_to_unknown(self) -> None:
        capabilities = service(
            FakeProvider("a", (seen("operating_environment.architecture", "sparc"),))
        ).discover()
        assert capabilities.operating_environment.architecture is Architecture.UNKNOWN

    def test_several_accelerators_are_ordered_and_indexed(self) -> None:
        """Plural from v1, on hosts that have one."""
        capabilities = service(
            FakeProvider(
                "a",
                (
                    seen("accelerator.0000:82:00.0.vendor", "nvidia"),
                    seen("accelerator.0000:03:00.0.vendor", "amd"),
                ),
            )
        ).discover()
        assert [a.index for a in capabilities.accelerators] == [0, 1]
        assert capabilities.accelerators[0].vendor is AcceleratorVendor.AMD

    def test_an_unrecognised_path_is_ignored_not_absorbed(self) -> None:
        """A provider cannot introduce a concept by reporting it."""
        capabilities = service(
            FakeProvider("a", (seen("vendor.secret_sauce", "yes"),))
        ).discover()
        assert from_dict(to_dict(capabilities)) == capabilities

    def test_capabilities_survive_the_wire(self) -> None:
        capabilities = service(
            FakeProvider("a", (seen("memory.total_bytes", 8),))
        ).discover()
        assert from_dict(to_dict(capabilities)) == capabilities


class TestFingerprint:
    def stable(self, **kwargs: object) -> HostCapabilities:
        return service(
            FakeProvider(
                "a",
                (
                    seen("cpu.model_name", "Test CPU"),
                    seen("cpu.physical_cores", 64),
                    seen("memory.total_bytes", 270_055_956_480),
                    seen("operating_environment.architecture", "x86_64"),
                    *(kwargs.get("extra") or ()),  # type: ignore[misc]
                ),
            )
        ).discover(host_id=HostId.generate())

    def test_the_same_host_fingerprints_the_same(self) -> None:
        assert compute(self.stable()) == compute(self.stable())

    def test_volatile_values_do_not_change_it(self) -> None:
        """Otherwise every cached probe is invalidated on every restart."""
        baseline = compute(self.stable())
        moved = compute(
            self.stable(extra=(seen("memory.available_bytes", 1_000),))
        )
        assert baseline == moved

    def test_free_space_does_not_change_it(self) -> None:
        with_free = self.stable(
            extra=(
                seen("mount./.mount_point", "/"),
                seen("mount./.total_bytes", 1_000),
                seen("mount./.free_bytes", 500),
            )
        )
        other_free = self.stable(
            extra=(
                seen("mount./.mount_point", "/"),
                seen("mount./.total_bytes", 1_000),
                seen("mount./.free_bytes", 900),
            )
        )
        assert compute(with_free) == compute(other_free)

    def test_a_changed_accelerator_does_change_it(self) -> None:
        """Because cached evidence keyed on the old shape is no longer valid."""
        baseline = compute(self.stable())
        added = compute(
            self.stable(extra=(seen("accelerator.0000:82:00.0.vendor", "nvidia"),))
        )
        assert baseline != added

    def test_an_unresolved_input_is_distinct_from_a_known_one(self) -> None:
        known = compute(self.stable())
        unknown = compute(
            service(
                FakeProvider(
                    "a",
                    (
                        seen("cpu.model_name", "Test CPU"),
                        seen("memory.total_bytes", 270_055_956_480),
                        seen("operating_environment.architecture", "x86_64"),
                    ),
                )
            ).discover()
        )
        assert known != unknown


class TestDeploymentProfile:
    def host(self, os_name: str, arch: str, vendor: str | None) -> HostCapabilities:
        accelerator = (
            (seen("accelerator.0000:82:00.0.vendor", vendor),) if vendor else ()
        )
        return service(
            FakeProvider(
                "a",
                (
                    seen("operating_environment.os_name", os_name),
                    seen("operating_environment.architecture", arch),
                    *accelerator,
                ),
                assignment_aware=bool(vendor),
            )
        ).discover()

    def test_the_reference_shape_is_compatible_and_not_supported(self) -> None:
        """L2 earns Compatible. Supported needs proven live inference."""
        profile = classify(self.host("linux", "x86_64", "nvidia"))
        assert profile is DeploymentProfile.COMPATIBLE

    def test_an_unvalidated_shape_is_experimental(self) -> None:
        assert classify(self.host("darwin", "arm64", "apple")) is (
            DeploymentProfile.EXPERIMENTAL
        )
        assert classify(self.host("linux", "x86_64", "amd")) is (
            DeploymentProfile.EXPERIMENTAL
        )
        assert classify(self.host("linux", "x86_64", None)) is (
            DeploymentProfile.EXPERIMENTAL
        )

    def test_a_heterogeneous_host_is_its_own_unvalidated_shape(self) -> None:
        capabilities = service(
            FakeProvider(
                "a",
                (
                    seen("operating_environment.os_name", "linux"),
                    seen("operating_environment.architecture", "x86_64"),
                    seen("accelerator.0000:82:00.0.vendor", "nvidia"),
                    seen("accelerator.0000:03:00.0.vendor", "amd"),
                ),
            )
        ).discover()
        assert shape_of(capabilities).accelerator_vendor is AcceleratorVendor.UNKNOWN
        assert classify(capabilities) is DeploymentProfile.EXPERIMENTAL

    def test_the_shape_is_coarse_enough_to_match_twice(self) -> None:
        """A claim keyed to an exact GPU model would never match anything."""
        key = shape_of(self.host("linux", "x86_64", "nvidia"))
        assert key == ShapeKey("linux", Architecture.X86_64, AcceleratorVendor.NVIDIA)


class TestNoProviderSchemaLeaks:
    def test_no_core_contract_field_names_a_vendor_or_tool(self) -> None:
        """The literal test from `docs/ARCHITECTURE.md` Part IX §0."""
        import dataclasses

        from kultrun.kernel.schema import registered_contracts

        banned = ("nvidia", "nvml", "cuda", "hwloc", "lstopo", "amdsmi", "apt")
        offenders = [
            f"{cls.kind}.{field.name}"
            for cls in registered_contracts().values()
            if cls.__module__.startswith("kultrun.")
            for field in dataclasses.fields(cls)  # type: ignore[arg-type]
            if any(word in field.name.lower() for word in banned)
        ]
        assert offenders == []

    def test_the_vendor_bus_spelling_is_normalized_in_the_adapter(self) -> None:
        """Two tools spell one address differently; the platform sees one."""
        assert nvidia._normalize_bus("00000000:82:00.0") == "0000:82:00.0"
        assert nvidia._normalize_bus("0000:82:00.0") == "0000:82:00.0"


class TestHwlocDoesNotInventAccelerators:
    """Measured on the reference host: not every display device is an accelerator.

    The host carries an ASPEED management VGA (PCI vendor 1a03) alongside its
    NVIDIA devices, as most servers do. Asserting every display controller as
    an accelerator would give a CPU-only host one phantom accelerator with an
    unknown vendor and unknown memory — precisely the shape where a false
    accelerator would go unnoticed.
    """

    def topology(self, *devices: tuple[str, str]) -> str:
        entries = "".join(
            f'<object type="PCIDev" pci_busid="{bus}" '
            f'pci_type="0300 [{vendor}:0001] [0000:0000] a1"/>'
            for bus, vendor in devices
        )
        return (
            '<?xml version="1.0"?><topology><object type="Machine">'
            f"{entries}</object></topology>"
        )

    def observed(self, xml: str) -> set[str]:
        report = hwloc.replay(xml, FixedClock(INSTANT)).observe()
        return {
            o.path for o in report.observations if o.path.startswith("accelerator")
        }

    def test_a_management_vga_is_not_an_accelerator(self) -> None:
        assert self.observed(self.topology(("0000:45:00.0", "1a03"))) == set()

    def test_a_known_accelerator_vendor_is_reported(self) -> None:
        assert self.observed(self.topology(("0000:82:00.0", "10de"))) == {
            "accelerator.0000:82:00.0.vendor"
        }

    def test_a_cpu_only_host_with_onboard_video_has_no_accelerators(self) -> None:
        capabilities = HostDiscoveryService(
            [hwloc.replay(self.topology(("0000:45:00.0", "1a03")))],
            clock=FixedClock(INSTANT),
        ).discover()
        assert capabilities.accelerators == ()

    def test_the_mixed_case_reports_only_the_accelerator(self) -> None:
        xml = self.topology(("0000:45:00.0", "1a03"), ("0000:82:00.0", "10de"))
        capabilities = HostDiscoveryService(
            [hwloc.replay(xml)], clock=FixedClock(INSTANT)
        ).discover()
        assert len(capabilities.accelerators) == 1
        assert capabilities.accelerators[0].vendor is AcceleratorVendor.NVIDIA


def test_native_provider_declines_a_non_linux_host(tmp_path: Path) -> None:
    """On a host with no /proc it reports unavailable rather than guessing."""
    report = native_linux.NativeLinuxProvider(
        FixedClock(INSTANT), root=tmp_path
    ).observe()
    assert report.status is ProviderStatus.UNAVAILABLE
