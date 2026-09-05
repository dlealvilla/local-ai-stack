"""Clock, results, events, config and the adapter registry."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from kultrun.kernel.clock import Clock, FixedClock, SystemClock, now_utc, require_utc
from kultrun.kernel.config import ConfigSchema
from kultrun.kernel.errors import (
    ConfigError,
    DuplicateRegistrationError,
    KultrunError,
    NotFoundError,
    UnknownAdapterError,
    ValidationError,
)
from kultrun.kernel.events import Event
from kultrun.kernel.ids import EventId, Name
from kultrun.kernel.registry import AdapterRegistry
from kultrun.kernel.results import ErrorDetail, Result
from kultrun.kernel.schema import from_dict, to_dict
from tests.fixtures.contracts import Leaf, RequiredSettings, Settings


class TestClock:
    def test_platform_time_is_timezone_aware_utc(self) -> None:
        assert now_utc().tzinfo is dt.UTC

    def test_a_naive_timestamp_is_refused_rather_than_assumed(self) -> None:
        with pytest.raises(ValidationError):
            require_utc(dt.datetime(2026, 9, 5))

    def test_both_clocks_satisfy_the_port(self, clock: FixedClock) -> None:
        assert isinstance(SystemClock(), Clock)
        assert isinstance(clock, Clock)

    def test_a_fixed_clock_does_not_move_unless_told(self, clock: FixedClock) -> None:
        first = clock.now()
        assert clock.now() == first
        clock.advance(90)
        assert (clock.now() - first).total_seconds() == 90


class TestResults:
    def test_a_success_carries_a_payload_and_no_error(self) -> None:
        result = Result.success(Leaf(label="pool-0"), correlation_id="req-1")
        assert result.ok
        assert result.error is None
        assert result.payload == {
            "kind": "test.leaf",
            "schema_version": 1,
            "label": "pool-0",
        }

    def test_a_failure_carries_a_stable_code_and_context(self) -> None:
        result = Result.failure(NotFoundError("no such pool", pool_id="pool-9"))
        assert not result.ok
        assert result.error is not None
        assert result.error.code == "not_found"
        assert result.error.context["pool_id"] == "pool-9"

    def test_a_retryable_failure_says_so(self) -> None:
        detail = ErrorDetail.from_error(KultrunError("transient"))
        assert detail.retryable is False

    def test_a_result_cannot_carry_both_a_payload_and_an_error(self) -> None:
        with pytest.raises(KultrunError):
            Result(payload={"a": 1}, error=ErrorDetail.from_error(KultrunError("x")))

    def test_a_result_survives_the_wire(self) -> None:
        result = Result.failure(
            ValidationError("bad pool", pool_id="pool-9"), correlation_id="req-2"
        )
        assert from_dict(to_dict(result)) == result

    def test_error_context_that_is_not_json_safe_does_not_cause_a_second_failure(
        self,
    ) -> None:
        """Context is assembled at raise sites everywhere; it cannot be trusted."""
        detail = ErrorDetail.from_error(KultrunError("odd", path=Path("/tmp/x")))
        assert detail.context["path"] == repr(Path("/tmp/x"))

    def test_unwrap_returns_a_payload_and_raises_a_failure(self) -> None:
        assert Result.success(Leaf(label="x")).unwrap() is not None
        with pytest.raises(KultrunError, match="denied"):
            Result.failure(NotFoundError("denied")).unwrap()


class TestEvents:
    def test_an_event_records_when_it_happened_from_the_injected_clock(
        self, clock: FixedClock
    ) -> None:
        event = Event.create(
            event_type="workload.admitted", source="resource", clock=clock
        )
        assert event.occurred_at == clock.now()

    def test_correlation_is_carried_from_the_first_event(
        self, clock: FixedClock
    ) -> None:
        """Threading this through a finished serving path later is expensive."""
        event = Event.create(
            event_type="gateway.request",
            source="gateway",
            correlation_id="req-1",
            clock=clock,
        )
        assert event.correlation_id == "req-1"

    def test_a_domain_payload_keeps_its_own_kind_and_version(
        self, clock: FixedClock
    ) -> None:
        """Payloads version independently of the envelope that carries them."""
        event = Event.create(
            event_type="probe.completed",
            source="storage",
            payload=Leaf(label="pool-0"),
            clock=clock,
        )
        restored = from_dict(to_dict(event))
        assert restored == event
        assert isinstance(restored, Event)
        assert isinstance(restored.payload, Leaf)

    def test_an_event_type_must_be_a_stable_name(self, clock: FixedClock) -> None:
        with pytest.raises(ValidationError):
            Event.create(event_type="Workload Admitted!", source="x", clock=clock)

    def test_a_naive_timestamp_cannot_be_stored_on_an_event(self) -> None:
        with pytest.raises(ValidationError):
            Event(
                event_id=EventId.generate(),
                event_type=Name("probe.completed"),
                occurred_at=dt.datetime(2026, 9, 5),
                source=Name("storage"),
            )


class TestConfig:
    def test_a_section_absent_from_the_input_uses_its_declared_defaults(self) -> None:
        schema = ConfigSchema()
        schema.register("store", Settings)
        assert schema.load({}).section(Settings).retention_days == 7

    def test_a_supplied_value_overrides_the_default(self) -> None:
        schema = ConfigSchema()
        schema.register("store", Settings)
        loaded = schema.load({"store": {"retention_days": 30}})
        assert loaded.section(Settings).retention_days == 30

    def test_an_unrecognised_section_is_refused(self) -> None:
        schema = ConfigSchema()
        schema.register("store", Settings)
        with pytest.raises(ConfigError, match="sections"):
            schema.load({"stoer": {}})

    def test_a_misspelled_key_is_refused_rather_than_ignored(self) -> None:
        """A silently ignored setting looks exactly like one that was applied."""
        schema = ConfigSchema()
        schema.register("store", Settings)
        with pytest.raises(ConfigError):
            schema.load({"store": {"retention_dayz": 30}})

    def test_a_value_of_the_wrong_type_is_refused(self) -> None:
        schema = ConfigSchema()
        schema.register("store", Settings)
        with pytest.raises(ConfigError):
            schema.load({"store": {"retention_days": "thirty"}})

    def test_a_section_with_no_defaults_must_be_supplied(self) -> None:
        schema = ConfigSchema()
        schema.register("service", RequiredSettings)
        with pytest.raises(ConfigError):
            schema.load({})

    def test_two_subsystems_cannot_claim_one_section_name(self) -> None:
        schema = ConfigSchema()
        schema.register("store", Settings)
        with pytest.raises(DuplicateRegistrationError):
            schema.register("store", RequiredSettings)

    def test_effective_configuration_is_reportable(self) -> None:
        """This is what the Platform API shows an administrator from Stage 0.3."""
        schema = ConfigSchema()
        schema.register("store", Settings)
        effective = schema.load({"store": {"root": "/srv/kultrun"}}).effective()
        assert effective["store"]["root"] == "/srv/kultrun"
        assert effective["store"]["schema_version"] == 1

    def test_a_missing_file_means_all_defaults(self, tmp_path: Path) -> None:
        schema = ConfigSchema()
        schema.register("store", Settings)
        loaded = schema.load_file(tmp_path / "absent.toml")
        assert loaded.section(Settings).root == "/var/lib/kultrun"

    def test_a_toml_file_is_loaded(self, tmp_path: Path) -> None:
        path = tmp_path / "kultrun.toml"
        path.write_text('[store]\nretention_days = 14\n', encoding="utf-8")
        schema = ConfigSchema()
        schema.register("store", Settings)
        assert schema.load_file(path).section(Settings).retention_days == 14

    def test_invalid_toml_is_reported_as_a_configuration_error(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "kultrun.toml"
        path.write_text("[store\n", encoding="utf-8")
        schema = ConfigSchema()
        schema.register("store", Settings)
        with pytest.raises(ConfigError, match="TOML"):
            schema.load_file(path)


class TestAdapterRegistry:
    def test_a_registered_adapter_can_be_built(self) -> None:
        registry: AdapterRegistry[str] = AdapterRegistry("test.Port")
        registry.register("upper", lambda text: text.upper())
        assert registry.create("upper", "vllm") == "VLLM"

    def test_an_unregistered_name_fails_closed_with_no_default(self) -> None:
        registry: AdapterRegistry[str] = AdapterRegistry("test.Port")
        registry.register("native", lambda: "native")
        with pytest.raises(UnknownAdapterError) as raised:
            registry.create("docker")
        assert raised.value.context["registered"] == ["native"]

    def test_two_adapters_cannot_claim_one_name(self) -> None:
        registry: AdapterRegistry[str] = AdapterRegistry("test.Port")
        registry.register("native", lambda: "a")
        with pytest.raises(DuplicateRegistrationError):
            registry.register("native", lambda: "b")

    def test_an_adapter_name_must_be_a_stable_name(self) -> None:
        registry: AdapterRegistry[str] = AdapterRegistry("test.Port")
        with pytest.raises(ValidationError):
            registry.register("Native Process!", lambda: "a")

    def test_registered_names_are_reportable(self) -> None:
        registry: AdapterRegistry[str] = AdapterRegistry("test.Port")
        registry.register("vllm", lambda: "a")
        registry.register("llama-cpp", lambda: "b")
        assert registry.names() == ("llama-cpp", "vllm")
        assert "vllm" in registry
