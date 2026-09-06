"""The control plane: it starts from nothing, and it answers for itself."""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from kultrun.adapters.http.server import serving
from kultrun.api.contracts import ApiRequest, Method
from kultrun.api.router import Router
from kultrun.evidence.contracts import Confidence, Derivation
from kultrun.host.contracts import Observation, ProviderReport, ProviderStatus
from kultrun.identity.contracts import PrincipalKind, SubjectId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.errors import (
    ConflictError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.main import Platform, build, config_schema
from kultrun.platform.contracts import (
    Approval,
    ApprovalDecision,
    ApprovalId,
    ComponentHealth,
    HealthStatus,
    PlatformSettings,
    PlatformState,
)
from kultrun.platform.health import aggregate_status

INSTANT = dt.datetime(2026, 9, 5, 6, 30, tzinfo=dt.UTC)


class StubProvider:
    """A host provider that answers, so control-plane tests stay portable.

    Stage 0.3's tests are about the control plane, not discovery. Without a
    stub they would assert whatever the machine running them happens to
    have — green on the Linux reference host and degraded on a developer's
    Mac — which would make them a test of the laptop rather than of the
    shell.
    """

    provider = Name("stub")
    reports_accelerator_assignment = False

    def observe(self) -> ProviderReport:
        return ProviderReport(
            provider=self.provider,
            status=ProviderStatus.AVAILABLE,
            observed_at=INSTANT,
            observations=(
                Observation(
                    path="operating_environment.os_name",
                    value="linux",
                    derivation=Derivation.MEASURED,
                    confidence=Confidence.HIGH,
                ),
            ),
        )


def build_platform(tmp_path: Path, clock: FixedClock, **overrides: object) -> Platform:
    configuration = config_schema().load(
        {"platform": {"state_root": str(tmp_path / "state")}}
    )
    return build(
        configuration,
        clock=clock,
        providers=[StubProvider()],
        requirements=[],
        provisioners=[],
        **overrides,  # type: ignore[arg-type]
    )


@pytest.fixture
def platform(tmp_path: Path, clock: FixedClock) -> Platform:
    return build_platform(tmp_path, clock)


def call(platform: Platform, path: str, **query: str) -> Any:
    """Invoke an endpoint and return its rendered payload."""
    response = platform.call(
        ApiRequest(method=Method.GET, path=path, query=dict(query))
    )
    assert response.status == 200, response.body
    return response.body["payload"]


class TestStartingFromNothing:
    def test_the_platform_starts_with_nothing_installed(
        self, platform: Platform
    ) -> None:
        """The bootstrap deadlock the previous attempt spent four commits undoing.

        An empty platform is the state a platform starts in, not a problem to
        be solved before starting.
        """
        assert platform.startup_report.completed
        assert platform.startup_report.first_run is True

    def test_a_fresh_platform_reports_healthy(self, platform: Platform) -> None:
        assert platform.plane.health.report().status is HealthStatus.HEALTHY

    def test_first_run_creates_an_administrator(self, platform: Platform) -> None:
        administrator = platform.plane.state.administrator
        assert administrator.principal_kind is PrincipalKind.ADMINISTRATOR

    def test_every_phase_is_recorded_in_order(self, platform: Platform) -> None:
        phases = [phase.phase.value for phase in platform.startup_report.phases]
        assert phases == [
            "record-store",
            "platform-state",
            "component-preparation",
            "host-discovery",
            "execution",
        ]

    def test_the_store_reconciles_before_anything_reads_it(
        self, platform: Platform
    ) -> None:
        """Every other phase reads persisted state, so recovery must precede them."""
        assert platform.startup_report.phases[0].phase == Name("record-store")


class TestRestart:
    def test_a_second_start_reuses_the_installation_identity(
        self, tmp_path: Path, clock: FixedClock
    ) -> None:
        """Minting a new identity would orphan every record referencing the old."""
        first = build_platform(tmp_path, clock)
        second = build_platform(tmp_path, clock)
        assert (
            first.plane.state.current.installation_id
            == second.plane.state.current.installation_id
        )
        assert second.startup_report.first_run is False

    def test_a_second_start_reuses_the_administrator(
        self, tmp_path: Path, clock: FixedClock
    ) -> None:
        first = build_platform(tmp_path, clock)
        second = build_platform(tmp_path, clock)
        assert (
            first.plane.state.administrator.subject_id
            == second.plane.state.administrator.subject_id
        )

    def test_an_unreadable_state_record_refuses_rather_than_recreating(
        self, tmp_path: Path, clock: FixedClock
    ) -> None:
        """Silently minting a new identity is the failure mode worth preventing."""
        root = tmp_path / "state"
        build_platform(tmp_path, clock)
        (root / "platform.state" / "current.json").write_text("{", encoding="utf-8")

        rebuilt = build_platform(tmp_path, clock)
        assert not rebuilt.startup_report.completed
        state_phase = rebuilt.startup_report.phases[1]
        assert not state_phase.succeeded
        assert state_phase.detail is not None
        assert "refusing" in state_phase.detail

    def test_a_missing_administrator_record_refuses(
        self, tmp_path: Path, clock: FixedClock
    ) -> None:
        root = tmp_path / "state"
        first = build_platform(tmp_path, clock)
        subject_file = (
            root
            / "identity.subject"
            / f"{first.plane.state.administrator.subject_id.value}.json"
        )
        subject_file.unlink()

        rebuilt = build_platform(tmp_path, clock)
        assert not rebuilt.startup_report.completed

    def test_a_store_defect_is_surfaced_but_does_not_stop_startup(
        self, tmp_path: Path, clock: FixedClock
    ) -> None:
        """An administrator diagnoses through the API, so it has to keep serving."""
        root = tmp_path / "state"
        build_platform(tmp_path, clock)
        (root / "platform.state" / "stray.json").write_text("{ nope", encoding="utf-8")

        rebuilt = build_platform(tmp_path, clock)
        assert rebuilt.startup_report.completed
        assert rebuilt.startup_report.defects
        assert call(rebuilt, "/health")


class TestTheApiAnswersFromPlatformState:
    """The Milestone 0 gate, endpoint by endpoint."""

    def test_version_identifies_the_running_build(self, platform: Platform) -> None:
        """A result arriving over HTTP must be traceable to a source state.

        These tests run from the repository, so the honest answer here is
        `source` and `acceptable_as_evidence` must be false. A checkout that
        claimed otherwise would let a development run pass as acceptance.
        """
        payload = call(platform, "/version")
        assert payload["origin"] == "source"
        assert payload["acceptable_as_evidence"] is False

    def test_health(self, platform: Platform) -> None:
        body = call(platform, "/health")
        assert body["status"] == "healthy"
        assert isinstance(body["components"], list)

    def test_platform(self, platform: Platform) -> None:
        body = call(platform, "/platform")
        assert body["kind"] == "platform.state"
        assert body["installation_id"] == str(
            platform.plane.state.current.installation_id
        )

    def test_contracts_catalogue_comes_from_the_registry(
        self, platform: Platform
    ) -> None:
        """Derived, so the answer cannot drift from the code."""
        body = call(platform, "/contracts")
        assert isinstance(body, list)
        kinds = {entry["kind"] for entry in body}
        assert {"platform.state", "host.capabilities", "analytics.usage_event"} <= kinds

    def test_config_reports_what_is_in_force(self, platform: Platform) -> None:
        body = call(platform, "/config")
        assert body["platform"]["schema_version"] == 1

    def test_startup_report(self, platform: Platform) -> None:
        body = call(platform, "/startup")
        assert body["completed"] is True

    def test_approvals_is_empty_before_any_decision(
        self, platform: Platform
    ) -> None:
        assert call(platform, "/approvals") == []


class TestErrorsRenderUniformly:
    def test_an_unknown_route_is_a_structured_error(self, platform: Platform) -> None:
        response = platform.call(ApiRequest(method=Method.GET, path="/invented"))
        assert response.status == 404
        assert response.body["payload"] is None
        assert response.body["error"]["code"] == "not_found"  # type: ignore[index]

    def test_a_raising_handler_renders_through_its_stable_code(self) -> None:
        router = Router()

        def explode(_: ApiRequest) -> None:
            raise PreconditionFailedError("not ready", subsystem="storage")

        router.get("/boom", explode)
        response = router.handle(ApiRequest(method=Method.GET, path="/boom"))
        assert response.status == 412
        assert response.body["error"]["code"] == "precondition_failed"  # type: ignore[index]
        assert response.body["error"]["context"]["subsystem"] == "storage"  # type: ignore[index]

    def test_an_unexpected_exception_does_not_leak_its_detail(self) -> None:
        """A subsystem error is as likely to carry a path as anything useful."""
        router = Router()

        def explode(_: ApiRequest) -> None:
            raise RuntimeError("/Users/secret/path/leaked")

        router.get("/boom", explode)
        response = router.handle(ApiRequest(method=Method.GET, path="/boom"))
        assert response.status == 500
        assert "leaked" not in json.dumps(response.body)

    def test_correlation_survives_into_the_response(self, platform: Platform) -> None:
        response = platform.call(
            ApiRequest(method=Method.GET, path="/health", correlation_id="req-9")
        )
        assert response.body["correlation_id"] == "req-9"

    def test_two_handlers_cannot_claim_one_route(self) -> None:
        router = Router()
        router.get("/thing", lambda _: None)
        with pytest.raises(ValidationError):
            router.get("/thing", lambda _: None)

    def test_the_route_table_is_reportable(self, platform: Platform) -> None:
        assert "GET /v1/health" in platform.router.paths()


class TestHealthAggregation:
    def test_the_aggregate_is_the_worst_component_not_an_average(self) -> None:
        components = (
            ComponentHealth(component=Name("a"), status=HealthStatus.HEALTHY),
            ComponentHealth(component=Name("b"), status=HealthStatus.FAILING),
            ComponentHealth(component=Name("c"), status=HealthStatus.HEALTHY),
        )
        assert aggregate_status(components) is HealthStatus.FAILING

    def test_unknown_outranks_healthy(self) -> None:
        """A component nobody has asked has not passed."""
        components = (
            ComponentHealth(component=Name("a"), status=HealthStatus.HEALTHY),
            ComponentHealth(component=Name("b"), status=HealthStatus.UNKNOWN),
        )
        assert aggregate_status(components) is HealthStatus.UNKNOWN

    def test_failing_outranks_unknown(self) -> None:
        """A known failure is more actionable than an unknown."""
        components = (
            ComponentHealth(component=Name("a"), status=HealthStatus.UNKNOWN),
            ComponentHealth(component=Name("b"), status=HealthStatus.FAILING),
        )
        assert aggregate_status(components) is HealthStatus.FAILING

    def test_nothing_registered_is_unknown_not_healthy(self) -> None:
        assert aggregate_status(()) is HealthStatus.UNKNOWN

    def test_a_source_that_raises_is_reported_failing_not_lost(
        self, platform: Platform, clock: FixedClock
    ) -> None:
        class Broken:
            component = Name("broken")

            def check_health(self) -> ComponentHealth:
                raise RuntimeError("cannot tell")

        platform.plane.health.register(Broken())
        report = platform.plane.health.report()
        assert report.status is HealthStatus.FAILING
        assert any(c.component == Name("broken") for c in report.components)


class TestApprovals:
    def approval(self, platform: Platform) -> Approval:
        subject = platform.plane.state.administrator.subject_id
        return Approval(
            approval_id=ApprovalId.generate(),
            action=Name("model.install"),
            target_kind=Name("model"),
            target_id="model_abc",
            requested_by=subject,
            requested_at=INSTANT,
            decision=ApprovalDecision.GRANTED,
            decided_by=subject,
            decided_at=INSTANT,
            reason="capacity verified",
        )

    def test_a_decision_is_recorded_and_readable(self, platform: Platform) -> None:
        recorded = platform.plane.approvals.record(self.approval(platform))
        assert platform.plane.approvals.get(recorded.approval_id.value) == recorded

    def test_a_decision_is_never_overwritten(self, platform: Platform) -> None:
        """A wrong decision is superseded, not edited; the record is the value."""
        recorded = platform.plane.approvals.record(self.approval(platform))
        with pytest.raises(ConflictError):
            platform.plane.approvals.record(recorded)

    def test_decisions_are_visible_through_the_api(self, platform: Platform) -> None:
        recorded = platform.plane.approvals.record(self.approval(platform))
        listed = call(platform, "/approvals")
        assert isinstance(listed, list)
        assert listed[0]["approval_id"] == recorded.approval_id.value

    def test_an_unknown_approval_is_a_structured_not_found(
        self, platform: Platform
    ) -> None:
        response = platform.call(
            ApiRequest(
                method=Method.GET,
                path="/approvals",
                query={"approval_id": ApprovalId.generate().value},
            )
        )
        assert response.status == 404
        assert response.body["error"]["code"] == "not_found"  # type: ignore[index]


class TestPlatformStateAccess:
    def test_reading_state_before_startup_refuses(
        self, tmp_path: Path, clock: FixedClock
    ) -> None:
        from kultrun.adapters.persistence.file_store import FileStore
        from kultrun.platform.state import PlatformStateStore

        store = PlatformStateStore(FileStore(tmp_path), clock, "0.1.0")
        assert not store.is_loaded
        with pytest.raises(PreconditionFailedError):
            _ = store.current

    def test_state_references_the_administrator_by_identifier(
        self, platform: Platform
    ) -> None:
        """Law 2: an entity from another package is referenced, not embedded.

        The reference-by-identifier check caught this as a real violation in
        the first code written after it existed, which is the strongest
        evidence the check is worth having.
        """
        assert isinstance(platform.plane.state.current.administrator_id, SubjectId)
        rendered = call(platform, "/platform")
        assert "administrator_id" in rendered
        assert "administrator" not in rendered


class TestTheHttpAdapter:
    def test_it_serves_the_router_and_releases_its_port(
        self, platform: Platform
    ) -> None:
        """A control plane that leaks a listening socket cannot restart."""
        with serving(platform.router, port=0) as server:
            port = server.port
            with urllib.request.urlopen(
                f"http://{server.address}:{port}/v1/health", timeout=5
            ) as response:
                assert response.status == 200
                body = json.loads(response.read())
        assert body["payload"]["status"] == "healthy"

        # The port is free afterwards, which is the part that matters.
        with serving(platform.router, port=port) as reopened:
            assert reopened.port == port

    def test_it_reports_an_unknown_route_with_the_mapped_status(
        self, platform: Platform
    ) -> None:
        with serving(platform.router, port=0) as server:
            url = f"http://{server.address}:{server.port}/v1/invented"
            with pytest.raises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(url, timeout=5)
            assert raised.value.code == 404


def test_the_settings_section_is_a_contract_like_any_other() -> None:
    """Which is what makes 'no config field may be reinterpreted' enforceable."""
    assert PlatformSettings.kind == "config.platform"
    assert PlatformSettings.schema_version == 1


def test_platform_state_is_not_a_junk_drawer() -> None:
    """Domain state belongs to domains; this is where that rule erodes first."""
    from dataclasses import fields

    names = {field.name for field in fields(PlatformState)}
    assert names == {
        "installation_id",
        "platform_version",
        "initialized_at",
        "administrator_id",
    }
