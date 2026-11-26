"""Invariant checker: the rules that must hold after every commit (NFR-07, BR-M1-01 to BR-M1-03).

It reads the whole store and returns what is wrong; it never changes anything. Tests run it after
every operation, and the What-if simulation can run it on a loaded snapshot.

A vehicle is at a Hub (hub and space both set) exactly when it is not IN_USE. This holds for
fleet and private vehicles alike: a private EV away from every Hub is IN_USE
(docs/design/behavioral/vehicle-state-machine.md, section 7, point 1).
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from core.domain.claims import ClaimPolicy
from core.domain.entities import (
    ChargingPoint,
    Hub,
    ParkingSpace,
    ResourceClaim,
    Vehicle,
)
from core.domain.enums import (
    ClaimStatus,
    Ownership,
    ResourceType,
    SpaceStatus,
    VehicleState,
)
from core.repository.base import Repository


class InvariantCode(StrEnum):
    HUB_SPACE_COUNT = "HUB_SPACE_COUNT"
    HUB_POINT_COUNT = "HUB_POINT_COUNT"
    HUB_OVER_CAPACITY = "HUB_OVER_CAPACITY"
    BAY_MISSING = "BAY_MISSING"
    BAY_WRONG_HUB = "BAY_WRONG_HUB"
    BAY_SHARED = "BAY_SHARED"
    SPACE_OCCUPANT_MISMATCH = "SPACE_OCCUPANT_MISMATCH"
    VEHICLE_LOCATION = "VEHICLE_LOCATION"
    VEHICLE_OWNERSHIP = "VEHICLE_OWNERSHIP"
    VEHICLE_BATTERY = "VEHICLE_BATTERY"
    CHARGING_OUTSIDE_BAY = "CHARGING_OUTSIDE_BAY"
    CLAIM_OVERLAP = "CLAIM_OVERLAP"
    CLAIM_RESOURCE_MISSING = "CLAIM_RESOURCE_MISSING"


@dataclass(frozen=True, slots=True)
class Violation:
    code: InvariantCode
    entity_id: str
    message: str


class InvariantChecker:
    @staticmethod
    def check(repo: Repository) -> list[Violation]:
        hubs = repo.query(Hub)
        spaces = repo.query(ParkingSpace)
        points = repo.query(ChargingPoint)
        vehicles = repo.query(Vehicle)
        claims = repo.query(ResourceClaim, lambda c: c.status is ClaimStatus.ACTIVE)
        found: list[Violation] = []
        found += _check_hubs(hubs, spaces, points)
        found += _check_bays(hubs, spaces, points)
        found += _check_occupancy(spaces, vehicles)
        found += _check_vehicles(vehicles, points)
        found += _check_claims(claims, spaces, points, vehicles)
        return found


def _check_hubs(
    hubs: list[Hub], spaces: list[ParkingSpace], points: list[ChargingPoint]
) -> list[Violation]:
    found: list[Violation] = []
    for hub in hubs:
        hub_spaces = [s for s in spaces if s.hub_id == hub.hub_id]
        hub_points = [p for p in points if p.hub_id == hub.hub_id]
        occupied = sum(1 for s in hub_spaces if s.status is SpaceStatus.OCCUPIED)
        if len(hub_spaces) != hub.parking_capacity:
            found.append(
                Violation(
                    InvariantCode.HUB_SPACE_COUNT,
                    hub.hub_id,
                    f"{len(hub_spaces)} spaces, capacity {hub.parking_capacity}",
                )
            )
        if len(hub_points) != hub.charging_point_count:
            found.append(
                Violation(
                    InvariantCode.HUB_POINT_COUNT,
                    hub.hub_id,
                    f"{len(hub_points)} charging points, expected {hub.charging_point_count}",
                )
            )
        if occupied > hub.parking_capacity:
            found.append(
                Violation(
                    InvariantCode.HUB_OVER_CAPACITY,
                    hub.hub_id,
                    f"{occupied} occupied, capacity {hub.parking_capacity}",
                )
            )
    return found


def _check_bays(
    hubs: list[Hub], spaces: list[ParkingSpace], points: list[ChargingPoint]
) -> list[Violation]:
    """A charging point is attached to exactly one space of its own Hub (D-007)."""
    found: list[Violation] = []
    space_by_id = {s.parking_space_id: s for s in spaces}
    points_of_space: dict[str, list[str]] = defaultdict(list)
    for point in points:
        points_of_space[point.parking_space_id].append(point.charging_point_id)
        space = space_by_id.get(point.parking_space_id)
        if space is None:
            found.append(
                Violation(
                    InvariantCode.BAY_MISSING, point.charging_point_id, "its bay does not exist"
                )
            )
        elif space.hub_id != point.hub_id:
            found.append(
                Violation(
                    InvariantCode.BAY_WRONG_HUB,
                    point.charging_point_id,
                    f"bay {space.parking_space_id!r} belongs to hub {space.hub_id!r}",
                )
            )
    for space_id, ids in sorted(points_of_space.items()):
        if len(ids) > 1:
            found.append(
                Violation(InvariantCode.BAY_SHARED, space_id, f"charging points {sorted(ids)}")
            )
    return found


def _check_occupancy(spaces: list[ParkingSpace], vehicles: list[Vehicle]) -> list[Violation]:
    """Space and vehicle agree on who is parked where, and nobody shares a space."""
    found: list[Violation] = []
    vehicle_by_id = {v.vehicle_id: v for v in vehicles}
    for space in spaces:
        if space.status is SpaceStatus.OCCUPIED:
            occupant = vehicle_by_id.get(space.occupant_vehicle_id or "")
            if (
                occupant is None
                or occupant.parking_space_id != space.parking_space_id
                or occupant.hub_id != space.hub_id
            ):
                found.append(
                    Violation(
                        InvariantCode.SPACE_OCCUPANT_MISMATCH,
                        space.parking_space_id,
                        f"occupant {space.occupant_vehicle_id!r} does not match",
                    )
                )
        elif space.occupant_vehicle_id is not None:
            found.append(
                Violation(
                    InvariantCode.SPACE_OCCUPANT_MISMATCH,
                    space.parking_space_id,
                    f"space is {space.status.value} but names {space.occupant_vehicle_id!r}",
                )
            )
    seen: dict[str, str] = {}
    for vehicle in vehicles:
        if vehicle.parking_space_id is None:
            continue
        if vehicle.parking_space_id in seen:
            found.append(
                Violation(
                    InvariantCode.SPACE_OCCUPANT_MISMATCH,
                    vehicle.parking_space_id,
                    f"{seen[vehicle.parking_space_id]!r} and {vehicle.vehicle_id!r} share it",
                )
            )
        seen[vehicle.parking_space_id] = vehicle.vehicle_id
        parked_in = next(
            (s for s in spaces if s.parking_space_id == vehicle.parking_space_id), None
        )
        if parked_in is None or parked_in.occupant_vehicle_id != vehicle.vehicle_id:
            found.append(
                Violation(
                    InvariantCode.SPACE_OCCUPANT_MISMATCH,
                    vehicle.vehicle_id,
                    f"parked in {vehicle.parking_space_id!r}, which does not name it",
                )
            )
    return found


def _check_vehicles(vehicles: list[Vehicle], points: list[ChargingPoint]) -> list[Violation]:
    found: list[Violation] = []
    bays = {p.parking_space_id for p in points}
    for vehicle in vehicles:
        located = vehicle.hub_id is not None and vehicle.parking_space_id is not None
        absent = vehicle.hub_id is None and vehicle.parking_space_id is None
        if not (located or absent):
            found.append(
                Violation(
                    InvariantCode.VEHICLE_LOCATION, vehicle.vehicle_id, "hub and space disagree"
                )
            )
        else:
            if vehicle.state is VehicleState.IN_USE and not absent:
                found.append(
                    Violation(
                        InvariantCode.VEHICLE_LOCATION,
                        vehicle.vehicle_id,
                        "a vehicle on a trip is at a Hub",
                    )
                )
            if vehicle.state is not VehicleState.IN_USE and not located:
                found.append(
                    Violation(
                        InvariantCode.VEHICLE_LOCATION,
                        vehicle.vehicle_id,
                        f"a {vehicle.state.value} vehicle has no parking space",
                    )
                )
        if (vehicle.ownership is Ownership.PRIVATE) != (vehicle.owner_user_id is not None):
            found.append(
                Violation(
                    InvariantCode.VEHICLE_OWNERSHIP,
                    vehicle.vehicle_id,
                    "owner_user_id is set exactly for private vehicles",
                )
            )
        if not 0.0 <= vehicle.battery_pct <= 100.0:
            found.append(
                Violation(
                    InvariantCode.VEHICLE_BATTERY,
                    vehicle.vehicle_id,
                    f"battery {vehicle.battery_pct} is outside 0..100",
                )
            )
        if vehicle.state is VehicleState.CHARGING and vehicle.parking_space_id not in bays:
            found.append(
                Violation(
                    InvariantCode.CHARGING_OUTSIDE_BAY,
                    vehicle.vehicle_id,
                    "a charging vehicle is not in a charging bay",
                )
            )
    return found


def _check_claims(
    claims: list[ResourceClaim],
    spaces: list[ParkingSpace],
    points: list[ChargingPoint],
    vehicles: list[Vehicle],
) -> list[Violation]:
    """No two ACTIVE claims overlap on one resource (BR-M1-01), and the resource exists."""
    found: list[Violation] = []
    existing: dict[ResourceType, set[str]] = {
        ResourceType.VEHICLE: {v.vehicle_id for v in vehicles},
        ResourceType.SPACE: {s.parking_space_id for s in spaces},
        ResourceType.CHARGING_POINT: {p.charging_point_id for p in points},
    }
    by_resource: dict[tuple[ResourceType, str], list[ResourceClaim]] = defaultdict(list)
    for claim in claims:
        if claim.resource_id not in existing[claim.resource_type]:
            found.append(
                Violation(
                    InvariantCode.CLAIM_RESOURCE_MISSING,
                    claim.claim_id,
                    f"{claim.resource_type.value} {claim.resource_id!r} does not exist",
                )
            )
        by_resource[(claim.resource_type, claim.resource_id)].append(claim)
    for group in by_resource.values():
        for index, first in enumerate(group):
            for second in group[index + 1 :]:
                if ClaimPolicy.overlaps(
                    first.start_at, first.end_at, second.start_at, second.end_at
                ):
                    found.append(
                        Violation(
                            InvariantCode.CLAIM_OVERLAP,
                            first.claim_id,
                            f"overlaps {second.claim_id!r} on {first.resource_id!r}",
                        )
                    )
    return found
