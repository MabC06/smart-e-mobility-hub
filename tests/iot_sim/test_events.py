"""Deterministic event generation tests — TC-M8-007 to TC-M8-011."""
from datetime import UTC, datetime

import pytest

from iot_sim import SimulatorConfig, build_network_spec, iter_minimal_events


def test_event_ids_and_order_are_deterministic() -> None:
    spec = build_network_spec(11)
    start = datetime(2026, 11, 6, tzinfo=UTC)
    config = SimulatorConfig(seed=11, private_arrival_count=3)
    first = list(iter_minimal_events(spec, start, config))
    second = list(iter_minimal_events(spec, start, config))
    assert first == second
    assert len({event.event_id for event in first}) == len(first)
    assert [event.at for event in first] == sorted(event.at for event in first)


def test_minimal_feed_contains_battery_and_paired_parking_events() -> None:
    spec = build_network_spec(11)
    events = list(
        iter_minimal_events(
            spec,
            datetime(2026, 11, 6, tzinfo=UTC),
            SimulatorConfig(seed=11, private_arrival_count=4),
        )
    )
    assert sum(event.type == "BATTERY_LEVEL" for event in events) == 250
    assert sum(event.type == "SPACE_OCCUPIED" for event in events) == 4
    assert sum(event.type == "SPACE_FREED" for event in events) == 4


def test_event_time_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        list(
            iter_minimal_events(
                build_network_spec(1),
                datetime(2026, 11, 6),
                SimulatorConfig(seed=1),
            )
        )


def test_invalid_simulator_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        SimulatorConfig(seed=-1)
    with pytest.raises(ValueError):
        SimulatorConfig(battery_drain_min_pct=3, battery_drain_max_pct=2)
