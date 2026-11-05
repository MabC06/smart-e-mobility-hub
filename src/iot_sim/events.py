"""Deterministic minimal sensor-event feed: battery drain and private parking occupancy."""
from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from core.seed import NetworkSpec, space_id
from core.sensors import SensorEvent
from iot_sim.config import SimulatorConfig


def iter_minimal_events(
    spec: NetworkSpec,
    start_at: datetime,
    config: SimulatorConfig,
) -> Iterator[SensorEvent]:
    """Yield reproducible events in timestamp order.

    Battery events cover the fleet; private EV occupancy is emitted as a paired arrival/departure
    for a deterministic subset. The paired events leave the seeded network structurally balanced.
    """
    if start_at.tzinfo is None or start_at.utcoffset() is None:
        raise ValueError("start_at must be timezone-aware")
    rng = random.Random(config.seed)
    fleet = sorted((v for hub in spec.hubs for v in hub.vehicles), key=lambda v: v.vehicle_id)
    cursor = start_at.astimezone(UTC)
    sequence = 0

    for vehicle in fleet:
        drain = rng.uniform(
            config.battery_drain_min_pct, config.battery_drain_max_pct
        )
        value = round(max(0.0, vehicle.battery_pct - drain), 1)
        sequence += 1
        yield SensorEvent(
            event_id=f"IOT-{config.seed:08d}-{sequence:06d}",
            source="iot_sim:battery",
            type="BATTERY_LEVEL",
            entity_id=vehicle.vehicle_id,
            at=cursor + timedelta(seconds=sequence),
            value=value,
        )

    private = sorted(spec.private_vehicles, key=lambda v: v.vehicle_id)
    available_spaces = [
        space_id(hub.hub_id, number)
        for hub in spec.hubs
        for number in range(
            hub.charging_point_count + len(hub.vehicles) + 1, hub.space_count + 1
        )
    ]
    count = min(config.private_arrival_count, len(private), len(available_spaces))
    for index in range(count):
        vehicle = private[index]
        parking_space = available_spaces[index]
        sequence += 1
        yield SensorEvent(
            event_id=f"IOT-{config.seed:08d}-{sequence:06d}",
            source="iot_sim:parking",
            type="SPACE_OCCUPIED",
            entity_id=parking_space,
            at=cursor + timedelta(seconds=sequence),
            value=vehicle.vehicle_id,
        )
        sequence += 1
        yield SensorEvent(
            event_id=f"IOT-{config.seed:08d}-{sequence:06d}",
            source="iot_sim:parking",
            type="SPACE_FREED",
            entity_id=parking_space,
            at=cursor + timedelta(seconds=sequence),
        )
