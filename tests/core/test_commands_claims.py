"""place_claim and release_claim (BR-M1-01, NFR-06)."""

from datetime import UTC, datetime, timedelta

from core.domain.entities import ChargingPoint, ResourceClaim, Vehicle
from core.domain.enums import (
    ChargingPointStatus,
    ClaimStatus,
    HolderKind,
    ResourceType,
    SpaceStatus,
    VehicleState,
)
from core.errors import ErrorCode
from core.events import EventType
from core.result import Err, Ok


def place(world, start_min=0, end_min=10, ref="R1", resource="V001", actor=None, **kw):
    base = world.clock.now()
    return world.core.commands.place_claim(
        kw.get("resource_type", ResourceType.VEHICLE),
        resource,
        kw.get("holder_kind", HolderKind.RESERVATION),
        ref,
        base + timedelta(minutes=start_min),
        base + timedelta(minutes=end_min),
        actor or world.reservation,
    )


def test_a_claim_is_created_active_and_announced(world):
    world.park("V001", "S02")

    result = place(world)

    assert isinstance(result, Ok)
    assert result.value.status is ClaimStatus.ACTIVE
    assert result.value.claim_id == "CLM-000001"
    assert [e.type for e in world.events] == [EventType.CLAIM_PLACED.value]


def test_overlapping_claim_by_another_holder_conflicts(world):
    world.park("V001", "S02")
    place(world, 0, 10, "R1")

    result = place(world, 5, 15, "R2")

    assert isinstance(result, Err)
    assert result.code is ErrorCode.CLAIM_CONFLICT
    assert result.details["conflicting_claim_id"] == "CLM-000001"
    assert len(world.repo.query(ResourceClaim)) == 1


def test_a_claim_that_starts_when_the_other_ends_is_accepted(world):
    world.park("V001", "S02")
    place(world, 0, 10, "R1")

    assert isinstance(place(world, 10, 20, "R2"), Ok)


def test_a_retry_by_the_same_holder_returns_the_same_claim(world):
    world.park("V001", "S02")
    first = place(world)
    second = place(world)

    assert isinstance(first, Ok) and isinstance(second, Ok)
    assert first.value.claim_id == second.value.claim_id
    assert len(world.repo.query(ResourceClaim)) == 1
    assert len([e for e in world.events if e.type == EventType.CLAIM_PLACED.value]) == 1


def test_a_released_claim_frees_the_interval(world):
    world.park("V001", "S02")
    first = place(world, 0, 10, "R1")
    assert isinstance(first, Ok)
    world.core.commands.release_claim(first.value.claim_id, world.reservation)

    assert isinstance(place(world, 0, 10, "R2"), Ok)


def test_release_twice_returns_the_same_claim_without_error(world):
    world.park("V001", "S02")
    placed = place(world)
    assert isinstance(placed, Ok)

    first = world.core.commands.release_claim(placed.value.claim_id, world.reservation)
    second = world.core.commands.release_claim(placed.value.claim_id, world.reservation)

    assert isinstance(first, Ok) and isinstance(second, Ok)
    assert second.value.status is ClaimStatus.RELEASED
    released = [e for e in world.events if e.type == EventType.CLAIM_RELEASED.value]
    assert len(released) == 1


def test_release_of_an_unknown_claim_is_not_found(world):
    result = world.core.commands.release_claim("CLM-999999", world.reservation)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.NOT_FOUND


def test_only_the_owning_module_or_an_operator_may_place_or_release(world):
    world.park("V001", "S02")

    wrong_module = place(world, actor=world.charging)
    by_operator = place(world, actor=world.operator)

    assert isinstance(wrong_module, Err)
    assert wrong_module.code is ErrorCode.FORBIDDEN
    assert isinstance(by_operator, Ok)
    release_wrong = world.core.commands.release_claim(by_operator.value.claim_id, world.charging)
    assert isinstance(release_wrong, Err)
    assert release_wrong.code is ErrorCode.FORBIDDEN


def test_unknown_resources_are_not_found(world):
    for resource_type in ResourceType:
        result = place(world, resource="NOPE", resource_type=resource_type)
        assert isinstance(result, Err)
        assert result.code is ErrorCode.NOT_FOUND


def test_resources_in_maintenance_cannot_be_claimed(world):
    vehicle = world.park("V001", "S02", state=VehicleState.MAINTENANCE)
    assert vehicle.state is VehicleState.MAINTENANCE
    space = world.space("S03")
    space.status = SpaceStatus.MAINTENANCE
    world.repo.update(space, space.version)
    point = world.repo.get(ChargingPoint, "CP01")
    point.status = ChargingPointStatus.OUT_OF_SERVICE
    world.repo.update(point, point.version)

    for resource_type, resource in [
        (ResourceType.VEHICLE, "V001"),
        (ResourceType.SPACE, "S03"),
        (ResourceType.CHARGING_POINT, "CP01"),
    ]:
        result = place(world, resource=resource, resource_type=resource_type)
        assert isinstance(result, Err)
        assert result.code is ErrorCode.RESOURCE_UNAVAILABLE


def test_a_faulty_vehicle_cannot_be_claimed(world):
    vehicle = world.park("V001", "S02")
    vehicle.fault_flag = True
    world.repo.update(vehicle, vehicle.version)

    result = place(world)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.RESOURCE_UNAVAILABLE


def test_bad_input_is_rejected(world):
    world.park("V001", "S02")
    base = world.clock.now()
    commands = world.core.commands

    backwards = commands.place_claim(
        ResourceType.VEHICLE, "V001", HolderKind.RESERVATION, "R1", base, base, world.reservation
    )
    naive = commands.place_claim(
        ResourceType.VEHICLE,
        "V001",
        HolderKind.RESERVATION,
        "R1",
        datetime(2026, 11, 2, 8, 0),
        base + timedelta(hours=1),
        world.reservation,
    )
    no_holder = place(world, ref="  ")

    for result in (backwards, naive, no_holder):
        assert isinstance(result, Err)
        assert result.code is ErrorCode.INVALID_INPUT
    assert world.repo.query(ResourceClaim) == []


def test_claims_on_different_resources_do_not_interfere(world):
    world.park("V001", "S02")
    world.park("V002", "S03")

    assert isinstance(place(world, resource="V001"), Ok)
    assert isinstance(place(world, resource="V002", ref="R2"), Ok)
    other_type = place(
        world,
        resource="S11",
        resource_type=ResourceType.SPACE,
        ref="R3",
    )
    assert isinstance(other_type, Ok)


def test_claim_times_are_kept_in_utc(world):
    world.park("V001", "S02")

    result = place(world)

    assert isinstance(result, Ok)
    assert result.value.start_at.tzinfo is UTC or result.value.start_at.utcoffset() == timedelta(0)


def test_vehicle_object_is_untouched_by_claiming(world):
    world.park("V001", "S02")
    before = world.vehicle("V001")

    place(world)

    assert world.vehicle("V001") == before
    assert isinstance(world.repo.get(Vehicle, "V001"), Vehicle)
