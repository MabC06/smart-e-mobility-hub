"""Deterministic DS-STD network specification builder."""
from __future__ import annotations

import random

from core.domain.enums import Role, VehicleType
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec

HUBS: tuple[tuple[str, str, str, int, int, int], ...] = (
    ("H01", "Metro", "METRO", 70, 10, 50),
    ("H02", "Dorm A", "DORM", 60, 10, 35),
    ("H03", "Dorm B", "DORM", 50, 8, 30),
    ("H04", "Dorm C", "DORM", 40, 6, 25),
    ("H05", "Campus A", "CAMPUS", 50, 8, 30),
    ("H06", "Campus B", "CAMPUS", 40, 6, 25),
    ("H07", "Campus C", "CAMPUS", 30, 4, 20),
    ("H08", "Library/Service A", "SERVICE", 25, 4, 14),
    ("H09", "Library/Service B", "SERVICE", 20, 3, 12),
    ("H10", "Library/Service C", "SERVICE", 15, 2, 9),
)


def _battery_levels(rng: random.Random, count: int) -> list[float]:
    """Return deterministic 60/25/15 battery bands."""
    high = round(count * 0.60)
    medium = round(count * 0.25)
    low = count - high - medium
    values = (
        [round(rng.uniform(70.1, 100.0), 1) for _ in range(high)]
        + [round(rng.uniform(30.0, 70.0), 1) for _ in range(medium)]
        + [round(rng.uniform(5.0, 29.9), 1) for _ in range(low)]
    )
    rng.shuffle(values)
    return values


def build_network_spec(seed: int = 0) -> NetworkSpec:
    """Build DS-STD: 10 Hubs, 400 spaces, 61 chargers, 250 fleet + 100 private EVs."""
    if seed < 0:
        raise ValueError("seed must be non-negative")
    rng = random.Random(seed)
    fleet_count = sum(row[5] for row in HUBS)
    fleet_batteries = iter(_battery_levels(rng, fleet_count))
    private_batteries = iter(_battery_levels(rng, 100))
    fleet_types = [VehicleType.E_BIKE] * 125 + [VehicleType.E_SCOOTER] * 75 + [
        VehicleType.E_MOTORCYCLE
    ] * 50
    rng.shuffle(fleet_types)
    type_iter = iter(fleet_types)

    hubs: list[HubSpec] = []
    fleet_index = 1
    for hub_id, name, zone, spaces, chargers, vehicles_count in HUBS:
        vehicles = tuple(
            VehicleSpec(
                vehicle_id=f"F-{fleet_index + offset:04d}",
                plate_or_code=f"FLEET-{fleet_index + offset:04d}",
                vehicle_type=next(type_iter),
                battery_pct=next(fleet_batteries),
                battery_capacity_kwh=0.5,
            )
            for offset in range(vehicles_count)
        )
        fleet_index += vehicles_count
        hubs.append(HubSpec(hub_id, name, zone, spaces, chargers, 11.0, vehicles))

    users = tuple(
        UserSpec(f"U-{i:04d}", f"STU-{i:04d}", Role.STUDENT)
        for i in range(1, 1001)
    ) + tuple(
        UserSpec(f"OP-{i:02d}", f"OPS-{i:02d}", Role.OPERATOR)
        for i in range(1, 6)
    )
    private_types = [VehicleType.E_BIKE] * 50 + [VehicleType.E_SCOOTER] * 30 + [
        VehicleType.E_MOTORCYCLE
    ] * 20
    rng.shuffle(private_types)
    private_vehicles = tuple(
        VehicleSpec(
            vehicle_id=f"P-{i:03d}",
            plate_or_code=f"PRIVATE-{i:03d}",
            vehicle_type=private_types[i - 1],
            battery_pct=next(private_batteries),
            battery_capacity_kwh=0.5,
            owner_user_id=f"U-{i:04d}",
            connector_type="TYPE2",
        )
        for i in range(1, 101)
    )
    return NetworkSpec(tuple(hubs), users, private_vehicles)
