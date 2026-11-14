"""Entity validation, configuration and the injectable clock."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import pytest

from core.clock import FixedClock, SystemClock
from core.config import CoreConfig
from core.domain.entities import (
    ChargingPoint,
    DomainEvent,
    Hub,
    StateChangeRecord,
    Vehicle,
    entity_id,
)
from core.errors import ErrorCode
from core.result import Err, Ok


def test_defaults_follow_the_nfr_list() -> None:
    config = CoreConfig()

    assert config.low_battery_threshold == 15.0
    assert config.near_capacity_threshold == 90.0


def test_configuration_can_be_read_from_the_environment() -> None:
    config = CoreConfig.from_env({"LOW_BATTERY_THRESHOLD": "20", "NEAR_CAPACITY_THRESHOLD": "85.5"})

    assert config.low_battery_threshold == 20.0
    assert config.near_capacity_threshold == 85.5


def test_missing_or_empty_environment_values_use_defaults() -> None:
    assert CoreConfig.from_env({}) == CoreConfig()
    assert CoreConfig.from_env({"LOW_BATTERY_THRESHOLD": "  "}) == CoreConfig()


@pytest.mark.parametrize("raw", ["abc", "-1", "100.5"])
def test_bad_configuration_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        CoreConfig.from_env({"LOW_BATTERY_THRESHOLD": raw})


def test_fixed_clock_only_moves_when_told_to(t0: datetime) -> None:
    clock = FixedClock(t0)

    assert clock.now() == t0
    clock.advance(timedelta(minutes=10))
    assert clock.now() == t0 + timedelta(minutes=10)
    clock.set(t0)
    assert clock.now() == t0


def test_clock_converts_to_utc_and_rejects_naive_times() -> None:
    plus7 = timezone(timedelta(hours=7))
    clock = FixedClock(datetime(2026, 11, 2, 15, 0, tzinfo=plus7))

    assert clock.now() == datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    assert clock.now().utcoffset() == timedelta(0)
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 11, 2, 8, 0))


def test_system_clock_is_timezone_aware() -> None:
    assert SystemClock().now().utcoffset() == timedelta(0)


@pytest.mark.parametrize("battery", [-0.1, 100.1])
def test_battery_must_be_a_percentage(make_vehicle: Callable[..., Vehicle], battery: float) -> None:
    with pytest.raises(ValueError):
        make_vehicle(battery_pct=battery)


def test_hub_capacity_rules() -> None:
    assert Hub("H01", "Metro", "METRO", 70, 10).status.value == "ACTIVE"
    with pytest.raises(ValueError):
        Hub("H01", "Metro", "METRO", 0, 0)
    with pytest.raises(ValueError):
        Hub("H01", "Metro", "METRO", 10, 11)  # more charging points than spaces (D-007)


def test_charging_point_needs_a_positive_power_rate() -> None:
    with pytest.raises(ValueError):
        ChargingPoint("CP1", "H01", "S1", 0.0)


def test_log_records_and_events_need_aware_times() -> None:
    naive = datetime(2026, 11, 2, 8, 0)
    with pytest.raises(ValueError):
        StateChangeRecord("R1", naive, "Vehicle", "V1", "A", "B", "reserve", "M2")
    with pytest.raises(ValueError):
        DomainEvent("E1", "VehicleStateChanged", naive)


def test_entity_id_uses_the_id_field(make_vehicle: Callable[..., Vehicle]) -> None:
    assert entity_id(make_vehicle("V007")) == "V007"
    assert entity_id(Hub("H02", "Dorm A", "DORM", 60, 10)) == "H02"


def test_result_types() -> None:
    ok: Ok[int] = Ok(3)
    err = Err(ErrorCode.NOT_FOUND, "missing", {"id": "x"})

    assert ok.is_ok and not ok.is_err
    assert err.is_err and not err.is_ok
    assert err.details["id"] == "x"
