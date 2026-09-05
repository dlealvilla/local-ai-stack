"""Regression against a real machine, forever, without renting one.

These fixtures were captured from the Stage 1.1 reference host — Ubuntu
24.04 on an AMD EPYC 7763 with an NVIDIA RTX PRO 4500 Blackwell — at both
boundaries the brief requires:

*Provider fixtures* are the raw output of each provider. They catch a
parsing regression, and they catch a change in what a tool reports.

*The normalized fixture* is what Kultrun concluded from exactly that input.
It catches a change in what the platform *decides* from unchanged
observations, which a provider fixture alone cannot see.

Capturing only one boundary would leave half the pipeline untested. And a
hand-written fixture would only encode what someone assumed a Blackwell
device reports; this one encodes what it did.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from kultrun.adapters.host import hwloc, native_linux, nvidia
from kultrun.host.contracts import AcceleratorVendor, Architecture, DeploymentProfile
from kultrun.host.discovery import HostDiscoveryService
from kultrun.host.fingerprint import compute
from kultrun.host.profile import classify
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.schema import from_dict, to_dict
from kultrun.kernel.unresolved import Unresolved, is_resolved

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hosts"
REFERENCE = FIXTURES / "linux-x86_64-nvidia"
INSTANT = dt.datetime(2026, 9, 5, 12, 0, tzinfo=dt.UTC)


@pytest.fixture(scope="module")
def replayed() -> object:
    """The reference host, rebuilt from its captured provider output."""
    service = HostDiscoveryService(
        [
            hwloc.replay((REFERENCE / "provider-hwloc.xml").read_text()),
            nvidia.replay((REFERENCE / "provider-nvidia.csv").read_text()),
            native_linux.replay(
                json.loads((REFERENCE / "provider-native-linux.json").read_text())
            ),
        ],
        clock=FixedClock(INSTANT),
    )
    return service.discover()


@pytest.fixture(scope="module")
def captured() -> dict[str, object]:
    """What Kultrun concluded on the day of acceptance."""
    loaded: dict[str, object] = json.loads(
        (REFERENCE / "normalized-host-capabilities.json").read_text()
    )
    return loaded


class TestTheReferenceHostReplays:
    def test_the_cpu_is_recognised(self, replayed) -> None:  # type: ignore[no-untyped-def]
        assert replayed.cpu.physical_cores == 64
        assert replayed.cpu.logical_cores == 128
        assert isinstance(replayed.cpu.model_name, str)
        assert "EPYC" in replayed.cpu.model_name

    def test_the_memory_total_is_recognised(self, replayed) -> None:  # type: ignore[no-untyped-def]
        assert replayed.memory.total_bytes == 270_055_956_480

    def test_two_providers_independently_agree_on_memory(self, replayed) -> None:  # type: ignore[no-untyped-def]
        """A topology tool and /proc/meminfo concurring is itself evidence."""
        (entry,) = [
            p for p in replayed.provenance if p.path == "memory.total_bytes"
        ]
        assert {name.value for name in entry.providers} == {"hwloc", "native-linux"}

    def test_exactly_one_accelerator_is_usable(self, replayed) -> None:  # type: ignore[no-untyped-def]
        """The finding this whole reconciliation design exists for.

        The bus carried four NVIDIA devices; one was assigned to this
        container. Believing the enumeration would have claimed roughly
        128 GiB of accelerator memory where 32 GiB exists.
        """
        assert len(replayed.accelerators) == 1
        accelerator = replayed.accelerators[0]
        assert accelerator.vendor is AcceleratorVendor.NVIDIA
        assert accelerator.memory_total_bytes == 34_207_694_848
        assert accelerator.unified_memory is False

    def test_the_unassigned_devices_remain_visible_as_evidence(self, replayed) -> None:  # type: ignore[no-untyped-def]
        (conflict,) = replayed.conflicts
        assert conflict.path == "accelerators"
        assert len(conflict.observations) == 3
        assert conflict.resolution is not None

    def test_the_management_vga_is_not_counted(self, replayed) -> None:  # type: ignore[no-untyped-def]
        """The host's ASPEED display controller is not an accelerator."""
        recorded = {o.path for c in replayed.conflicts for o in c.observations}
        assert not any("45:00.0" in path for path in recorded)
        assert all(a.vendor is AcceleratorVendor.NVIDIA for a in replayed.accelerators)

    def test_the_distribution_and_family_stay_separate(self, replayed) -> None:  # type: ignore[no-untyped-def]
        assert replayed.operating_environment.os_name == "linux"
        assert replayed.operating_environment.distribution == "ubuntu"
        assert replayed.operating_environment.architecture is Architecture.X86_64

    def test_mounts_are_reported_including_the_absurd_one(self, replayed) -> None:  # type: ignore[no-untyped-def]
        """A 2.15 PB network mount, reported and never authorizing.

        This is the previous attempt's "239 TB free" trap in a new costume.
        Reporting it is correct; Stage 1.2 decides what may be believed and
        Milestone 2 decides what may be relied on.
        """
        by_point = {m.mount_point: m for m in replayed.mounts}
        workspace = by_point["/workspace"]
        assert is_resolved(workspace.total_bytes)
        assert workspace.total_bytes > 2 * 10**15
        assert workspace.filesystem_type == "fuse"

    def test_only_candidate_storage_is_reported(self, replayed) -> None:  # type: ignore[no-untyped-def]
        """Container plumbing is not storage, and must not enter identity.

        The host mounted a tmpfs at `/run/nvidia-ctk-hook<uuid>` whose name
        changes on every container start. A mount point is a fingerprint
        input, so reporting it would have made host identity unstable across
        restarts and left Milestone 2 unable to reuse any cached evidence.
        """
        assert [m.mount_point for m in replayed.mounts] == ["/", "/workspace"]

    def test_what_the_host_could_not_answer_stays_unresolved(self, replayed) -> None:  # type: ignore[no-untyped-def]
        """Discrete-GPU hosts do not report unified memory; that is unknown."""
        assert isinstance(replayed.memory.unified_with_accelerator, Unresolved)
        assert isinstance(replayed.execution.docker, Unresolved)
        assert replayed.execution.native_process is True

    def test_the_shape_earns_compatible_and_no_more(self, replayed) -> None:  # type: ignore[no-untyped-def]
        assert classify(replayed) is DeploymentProfile.COMPATIBLE


class TestNormalizationHasNotDrifted:
    """The second boundary: same input, same conclusions."""

    def test_the_fingerprint_is_unchanged(self, replayed, captured) -> None:  # type: ignore[no-untyped-def]
        assert compute(replayed) == captured["fingerprint"]

    def test_the_accelerator_conclusion_is_unchanged(self, replayed, captured) -> None:  # type: ignore[no-untyped-def]
        assert [
            (a.vendor.value, a.memory_total_bytes) for a in replayed.accelerators
        ] == [
            (a["vendor"], a["memory_total_bytes"]) for a in captured["accelerators"]
        ]

    def test_every_normalized_value_is_unchanged(self, replayed, captured) -> None:  # type: ignore[no-untyped-def]
        """Compares the whole conclusion, minus what is expected to move.

        Identity and timestamps differ per run by design; everything the
        platform *decided* must not.
        """
        volatile = {"host_id", "detected_at", "provider_reports", "provenance"}
        rebuilt = to_dict(replayed)
        rebuilt["fingerprint"] = compute(replayed)
        assert {k: v for k, v in rebuilt.items() if k not in volatile} == {
            k: v for k, v in captured.items() if k not in volatile
        }

    def test_the_captured_conclusion_still_deserializes(self, captured) -> None:  # type: ignore[no-untyped-def]
        """A contract change that broke old records would fail here."""
        assert from_dict(captured) is not None


class TestTheFixturesAreSanitized:
    @pytest.mark.parametrize(
        "name",
        [
            "provider-hwloc.xml",
            "provider-nvidia.csv",
            "provider-native-linux.json",
            "normalized-host-capabilities.json",
        ],
    )
    def test_nothing_identifying_or_secret_survives(self, name: str) -> None:
        text = (REFERENCE / name).read_text().lower()
        for banned in ("runpod", "usyd", "password", "secret", "api_key", "token"):
            assert banned not in text, f"{name} contains {banned!r}"
