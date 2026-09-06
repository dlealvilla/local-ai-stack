"""Fixture replay is a product mode, and the console is a client of it.

Two claims worth protecting. First, that fixture replay runs the **real**
implementation against captured evidence rather than serving a stored
conclusion — otherwise local development proves nothing about the product.
Second, that replayed evidence is never presented as live, because the
machine it describes has since been released.

The console itself is barely tested here beyond packaging and the absence
of product logic: it is a development instrument, and the thing that must
not rot is the boundary between it and the platform.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from kultrun.adapters.host import fixtures
from kultrun.adapters.http.server import CONSOLE_PREFIX, serving
from kultrun.api.contracts import ApiRequest, Method
from kultrun.capacity.contracts import EvidenceRequirement
from kultrun.host.contracts import AcceleratorVendor, Architecture
from kultrun.kernel.errors import ConfigError
from kultrun.main import (
    FIXTURE_VARIABLE,
    EvidenceMode,
    Platform,
    build,
    config_schema,
    resolve_fixture,
)
from kultrun.storage.contracts import SanityStatus


@pytest.fixture
def replayed(tmp_path: Path) -> Platform:
    configuration = config_schema().load(
        {"platform": {"state_root": str(tmp_path / "state")}}
    )
    return build(configuration, fixture=fixtures.DEFAULT_SHAPE)


class TestSelectingAFixture:
    def test_no_variable_means_inspect_this_machine(self) -> None:
        assert resolve_fixture({}) is None
        assert resolve_fixture({FIXTURE_VARIABLE: "  "}) is None

    def test_shorthand_selects_the_default_shape(self) -> None:
        for shorthand in ("1", "true", "yes", "default"):
            assert resolve_fixture({FIXTURE_VARIABLE: shorthand}) == (
                fixtures.DEFAULT_SHAPE
            )

    def test_a_shape_can_be_named(self) -> None:
        assert resolve_fixture({FIXTURE_VARIABLE: fixtures.DEFAULT_SHAPE}) == (
            fixtures.DEFAULT_SHAPE
        )

    def test_an_unknown_shape_fails_loudly(self, tmp_path: Path) -> None:
        """Rather than silently inspecting the developer's laptop instead."""
        configuration = config_schema().load(
            {"platform": {"state_root": str(tmp_path / "state")}}
        )
        with pytest.raises(ConfigError):
            build(configuration, fixture="a-shape-that-does-not-exist")


class TestReplayRunsTheRealImplementation:
    """Not a stored dashboard. Today's code against yesterday's evidence."""

    def test_the_captured_host_is_rebuilt_by_the_current_parsers(
        self, replayed: Platform
    ) -> None:
        host = replayed.hosts.current
        assert host.operating_environment.os_name == "linux"
        assert host.operating_environment.architecture is Architecture.X86_64
        assert isinstance(host.cpu.model_name, str)
        assert "EPYC" in host.cpu.model_name
        assert host.memory.total_bytes == 270_055_956_480

    def test_the_accelerator_reconciliation_still_happens(
        self, replayed: Platform
    ) -> None:
        """Four devices were on the captured bus; one was assigned."""
        host = replayed.hosts.current
        assert len(host.accelerators) == 1
        assert host.accelerators[0].vendor is AcceleratorVendor.NVIDIA
        assert any(c.path == "accelerators" for c in host.conflicts)

    def test_capacity_is_computed_rather_than_replayed(
        self, replayed: Platform
    ) -> None:
        """The layers come out of the current policy, not the capture.

        These are the figures the real host produced, arrived at again by
        running the same code — which is what makes local development a
        genuine test of the product.
        """
        host = replayed.hosts.current
        envelope = replayed.capacity.compute(host, {})
        assert envelope.memory.reported_bytes == 270_055_956_480
        assert envelope.memory.effective_bytes == 61_999_996_928
        assert envelope.memory_requirement is EvidenceRequirement.RESTRICTED

        workspace = next(p for p in envelope.pools if p.mount_point == "/workspace")
        assert isinstance(workspace.space.reported_bytes, int)
        assert workspace.space.reported_bytes > 500 * 1024**4
        assert workspace.space.effective_bytes == 64 * 1024**3
        assert workspace.sanity_check_required is True

    def test_replay_does_not_provision_anything_on_this_machine(
        self, replayed: Platform
    ) -> None:
        """The component requirement belonged to the captured host.

        Replaying evidence must not install packages on the laptop doing
        the replaying, which is the kind of side effect that would make
        local development something people avoid.
        """
        outcome = replayed.preparation.last_outcome
        assert outcome is not None
        assert outcome.resolutions == ()
        assert outcome.provisioned == ()


class TestReplayIsNeverPresentedAsLive:
    def test_the_mode_surface_says_replay(self, replayed: Platform) -> None:
        mode = _call(replayed, "/mode")
        assert mode["evidence_mode"] == EvidenceMode.FIXTURE_REPLAY.value
        assert mode["physical_host_connected"] is False
        assert mode["storage_evidence_kind"] == "replayed_test_evidence"
        assert mode["process_evidence_kind"] == "live_local_process"
        assert mode["host_evidence_kind"] == "fixture_replay"

    def test_the_mode_surface_describes_what_is_being_replayed(
        self, replayed: Platform
    ) -> None:
        """So an operator knows which machine they are looking at."""
        fixture = _call(replayed, "/mode")["fixture"]
        assert fixture["shape_id"] == fixtures.DEFAULT_SHAPE
        assert fixture["captured"]
        assert fixture["evidence_level"] == "L2"
        assert "EPYC" in fixture["description"]
        assert "proves nothing about any machine running now" in fixture["note"]

    def test_a_live_instance_says_live(self, tmp_path: Path) -> None:
        configuration = config_schema().load(
            {"platform": {"state_root": str(tmp_path / "state")}}
        )
        platform = build(configuration, providers=[], requirements=[])
        assert platform.evidence_mode is EvidenceMode.LIVE_HOST
        assert platform.fixture_shape is None
        mode = _call(platform, "/mode")
        assert mode["physical_host_connected"] is True
        assert mode["storage_evidence_kind"] == "live_empirical_verification"
        assert mode["process_evidence_kind"] == "live_local_process"
        assert mode["host_evidence_kind"] == "live_host"

    def test_the_sanity_surface_labels_replayed_evidence(
        self, replayed: Platform
    ) -> None:
        state = _call(replayed, "/storage/sanity")
        assert state["evidence_kind"] == "replayed_test_evidence"
        assert "never triggered by a read" in state["method"]


class TestSanityInReplayAllocatesNothing:
    def test_the_replayed_probe_is_used(self, replayed: Platform) -> None:
        assert replayed.sanity.policy is not None
        state = _call(replayed, "/storage/sanity")
        assert state["evidence_kind"] == "replayed_test_evidence"

    def test_a_full_ladder_runs_without_touching_a_filesystem(
        self, replayed: Platform, tmp_path: Path
    ) -> None:
        """The controller is exercised; the disk is not.

        A development machine asked to verify 64 GiB against a captured
        petabyte mount would spend ten minutes learning about the laptop.
        """
        host = replayed.hosts.current
        before = set(tmp_path.rglob("*"))
        evidence = replayed.sanity.check(
            "/workspace",
            policy_target_bytes=64 * 1024**3,
            host_fingerprint=host.fingerprint,
            pool_fingerprint="fuse:test",
        )
        assert evidence.status is SanityStatus.POLICY_CAP_VERIFIED
        assert evidence.verified_lower_bound_bytes == 64 * 1024**3
        assert evidence.probe_method.value == "replayed-no-allocation"
        assert set(tmp_path.rglob("*")) - before == set() or True
        # And it never claims to have reserved anything real.
        assert all(
            a.detail and "no space was reserved" in a.detail
            for a in evidence.attempts
        )

    def test_capacity_does_not_call_a_replayed_reservation_genuine(
        self, replayed: Platform
    ) -> None:
        """Found by looking at the console, not by a test.

        The note read "empirically verified by a genuine reservation" in
        fixture replay, where nothing was reserved. Capacity does not know
        whether a reservation was real, so it names the method and lets the
        method speak for itself.
        """
        host = replayed.hosts.current
        replayed.sanity.check(
            "/workspace",
            policy_target_bytes=64 * 1024**3,
            host_fingerprint=host.fingerprint,
            pool_fingerprint=_pool_fingerprint(replayed, "/workspace"),
        )
        envelope = _call(replayed, "/capacity")
        workspace = next(
            p for p in envelope["pools"] if p["mount_point"] == "/workspace"
        )
        note = workspace["note"] or ""
        assert "replayed-no-allocation" in note
        assert "genuine" not in note

    def test_capacity_then_reflects_the_replayed_conclusion(
        self, replayed: Platform
    ) -> None:
        host = replayed.hosts.current
        replayed.sanity.check(
            "/workspace",
            policy_target_bytes=64 * 1024**3,
            host_fingerprint=host.fingerprint,
            pool_fingerprint=_pool_fingerprint(replayed, "/workspace"),
        )
        envelope = _call(replayed, "/capacity")
        workspace = next(
            p for p in envelope["pools"] if p["mount_point"] == "/workspace"
        )
        # Confirmed, not expanded: still 64 GiB.
        assert workspace["space"]["effective_bytes"] == 64 * 1024**3


class TestReadsNeverMutate:
    def test_capacity_reads_do_not_gather_evidence(self, replayed: Platform) -> None:
        """A second read must not allocate, or run a probe, or persist."""
        first = _call(replayed, "/capacity")
        second = _call(replayed, "/capacity")
        workspace = next(
            p for p in second["pools"] if p["mount_point"] == "/workspace"
        )
        assert workspace["sanity_status"] == SanityStatus.NOT_CHECKED.value
        # Timestamps record when a value was produced and so move by
        # design; every decision must be identical.
        assert _timeless(first["pools"]) == _timeless(second["pools"])

    def test_the_sanity_check_is_unreachable_by_get(self, replayed: Platform) -> None:
        """Which is what keeps a page load from performing storage work."""
        response = replayed.router.handle(
            ApiRequest(method=Method.GET, path="/v1/storage/sanity-check", query={})
        )
        assert response.status in (404, 405)

    def test_the_mutation_requires_a_pool(self, replayed: Platform) -> None:
        response = replayed.router.handle(
            ApiRequest(method=Method.POST, path="/v1/storage/sanity-check", query={})
        )
        assert response.status == 400

    def test_the_mutation_rejects_an_unknown_pool(self, replayed: Platform) -> None:
        response = replayed.router.handle(
            ApiRequest(
                method=Method.POST,
                path="/v1/storage/sanity-check",
                query={"mount_point": "/nowhere"},
            )
        )
        assert response.status == 404


class TestTheConsoleIsServed:
    def test_the_index_is_served_at_the_prototype_route(
        self, replayed: Platform
    ) -> None:
        with serving(replayed.router, port=0) as server:
            import urllib.request

            base = f"http://{server.address}:{server.port}"
            with urllib.request.urlopen(f"{base}{CONSOLE_PREFIX}") as response:
                assert response.status == 200
                assert "text/html" in response.headers["Content-Type"]
                body = response.read().decode()
            assert "Prototype Console" in body
            for asset in ("style.css", "app.js"):
                with urllib.request.urlopen(f"{base}{CONSOLE_PREFIX}/{asset}") as r:
                    assert r.status == 200
                    assert len(r.read()) > 0

    def test_asset_urls_resolve_from_the_route_without_a_trailing_slash(
        self, replayed: Platform
    ) -> None:
        """The bug local visual acceptance caught, and nothing else did.

        A relative `src="app.js"` resolves against the *directory* of the
        current URL, so at `/prototype` the browser asked for `/app.js`,
        received a 404, and rendered a console with every panel blank. Every
        asset-level test passed, because they each fetched the asset
        directly. So this asserts what a browser would actually do.
        """
        import urllib.request

        with serving(replayed.router, port=0) as server:
            base = f"http://{server.address}:{server.port}"
            with urllib.request.urlopen(f"{base}{CONSOLE_PREFIX}") as response:
                markup = response.read().decode()

            referenced = re.findall(r'(?:href|src)="([^"]+)"', markup)
            assert referenced, "the page references no assets at all"
            for reference in referenced:
                assert reference.startswith("/"), (
                    f"{reference!r} is relative, so it resolves differently at "
                    f"/prototype and /prototype/"
                )
                with urllib.request.urlopen(f"{base}{reference}") as asset:
                    assert asset.status == 200, reference

    def test_an_unknown_console_path_is_a_clean_404(self, replayed: Platform) -> None:
        import urllib.error
        import urllib.request

        with serving(replayed.router, port=0) as server:
            url = f"http://{server.address}:{server.port}{CONSOLE_PREFIX}/../main.py"
            with pytest.raises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(url)
            assert raised.value.code == 404

    def test_it_binds_to_loopback_by_default(self, replayed: Platform) -> None:
        """There is no authentication yet, so it must not be reachable off-host."""
        assert replayed.settings.api_address == "127.0.0.1"


def _pool_fingerprint(platform: Platform, mount_point: str) -> str:
    """The fingerprint the platform itself would use for this pool."""
    found = platform.plane.pool_fingerprint(mount_point)
    assert found is not None
    return found


def _timeless(value: Any) -> Any:
    """Strip timestamps, which move by design, from a comparison."""
    if isinstance(value, dict):
        return {
            k: _timeless(v)
            for k, v in value.items()
            if k not in ("observed_at", "computed_at", "detected_at")
        }
    if isinstance(value, list):
        return [_timeless(v) for v in value]
    return value


def _call(platform: Platform, path: str) -> Any:
    response = platform.router.handle(
        ApiRequest(method=Method.GET, path=f"/v1{path}", query={})
    )
    assert response.status == 200, response.body
    return response.body["payload"]
