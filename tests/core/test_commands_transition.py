"""transition_vehicle: the Vehicle state machine plus its side effects on spaces and claims.

The ``world`` fixture is defined in conftest.py: H01 has spaces S01 (bay of CP01), S02, S03 and
H02 has S11, S12. Times come from a fixed clock, so every boundary is exact.
"""

from datetime import timedelta

from core.domain.entities import ChargingPoint, ResourceClaim
from core.domain.enums import (
    ChargingPointStatus,
    HolderKind,
    HubStatus,
    ResourceType,
    SpaceStatus,
    VehicleEvent,
    VehicleState,
)
from core.errors import ErrorCode
from core.events import EventType
from core.result import Err, Ok
from core.services.commands import TransitionCtx

E = VehicleEvent
S = VehicleState


def reserve(world, vehicle_id="V001", **kw):
    claim_id = world.claim_vehicle(vehicle_id)
    version = world.vehicle(vehicle_id).version
    return world.core.commands.transition_vehicle(
        vehicle_id, E.RESERVE, version, world.reservation, TransitionCtx(claim_id=claim_id, **kw)
    )


def reserved_vehicle(world, vehicle_id="V001", space_id="S02"):
    world.park(vehicle_id, space_id)
    result = reserve(world, vehicle_id)
    assert isinstance(result, Ok)
    return result.value


def in_use_vehicle(world, vehicle_id="V001", space_id="S02"):
    view = reserved_vehicle(world, vehicle_id, space_id)
    claim = world.repo.query(ResourceClaim)
    result = world.core.commands.transition_vehicle(
        vehicle_id,
        E.PICKUP,
        view.version,
        world.reservation,
        TransitionCtx(claim_id=claim[0].claim_id),
    )
    assert isinstance(result, Ok)
    return result.value


# --------------------------------------------------------------------------------- reserve (T1)


def test_reserve_needs_an_active_claim_and_changes_the_state(world):
    world.park("V001", "S02")

    result = reserve(world)

    assert isinstance(result, Ok)
    assert result.value.state is S.RESERVED
    assert result.value.version == 2
    assert world.vehicle("V001").state is S.RESERVED
    assert world.space("S02").status is SpaceStatus.OCCUPIED  # the space stays occupied


def test_reserve_without_a_claim_is_rejected(world):
    world.park("V001", "S02")

    result = world.core.commands.transition_vehicle("V001", E.RESERVE, 1, world.reservation)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_INPUT
    assert world.vehicle("V001").state is S.AVAILABLE


def test_reserve_with_an_expired_claim_is_rejected(world):
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001", minutes=10)
    world.clock.advance(timedelta(minutes=10))  # exactly at the end of the hold

    result = world.core.commands.transition_vehicle(
        "V001", E.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_TRANSITION


def test_reserve_with_a_claim_on_another_vehicle_is_rejected(world):
    world.park("V001", "S02")
    world.park("V002", "S03")
    other_claim = world.claim_vehicle("V002")

    result = world.core.commands.transition_vehicle(
        "V001", E.RESERVE, 1, world.reservation, TransitionCtx(claim_id=other_claim)
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_TRANSITION


def test_reserve_with_a_stale_version_conflicts(world):
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")

    result = world.core.commands.transition_vehicle(
        "V001", E.RESERVE, 7, world.reservation, TransitionCtx(claim_id=claim_id)
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.VERSION_CONFLICT
    assert world.vehicle("V001").version == 1


def test_reserve_respects_the_minimum_battery_and_changes_nothing_on_failure(world):
    world.park("V001", "S02", battery_pct=40.0)
    claim_id = world.claim_vehicle("V001")
    events_before = len(world.events)

    result = world.core.commands.transition_vehicle(
        "V001",
        E.RESERVE,
        1,
        world.reservation,
        TransitionCtx(claim_id=claim_id, min_battery=50.0),
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.BATTERY_TOO_LOW
    assert world.vehicle("V001").state is S.AVAILABLE
    assert world.log_of("V001") == []
    assert len(world.events) == events_before


def test_unknown_vehicle_is_not_found(world):
    result = world.core.commands.transition_vehicle("V404", E.RESERVE, 1, world.reservation)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.NOT_FOUND


def test_a_disallowed_pair_is_rejected_and_not_logged(world):
    world.park("V001", "S02")

    result = world.core.commands.transition_vehicle("V001", E.PICKUP, 1, world.reservation)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_TRANSITION
    assert world.log_of("V001") == []


# ---------------------------------------------------------------------------------- pickup (T3)


def test_pickup_frees_the_origin_space_and_leaves_the_hub(world):
    reserved = reserved_vehicle(world)
    claim = world.repo.query(ResourceClaim)[0]
    world.events.clear()

    result = world.core.commands.transition_vehicle(
        "V001",
        E.PICKUP,
        reserved.version,
        world.reservation,
        TransitionCtx(claim_id=claim.claim_id),
    )

    assert isinstance(result, Ok)
    vehicle = world.vehicle("V001")
    assert vehicle.state is S.IN_USE
    assert vehicle.hub_id is None
    assert vehicle.parking_space_id is None
    assert world.space("S02").status is SpaceStatus.AVAILABLE
    assert world.space("S02").occupant_vehicle_id is None
    assert [e.type for e in world.events] == [
        EventType.VEHICLE_STATE_CHANGED.value,
        EventType.SPACE_OCCUPANCY_CHANGED.value,
    ]
    assert world.events[1].payload["occupied_count"] == 0


def test_pickup_one_second_before_the_end_of_the_hold_is_accepted(world):
    reserved = reserved_vehicle(world)
    claim = world.repo.query(ResourceClaim)[0]
    world.clock.advance(timedelta(minutes=10) - timedelta(seconds=1))
    on_time = world.core.commands.transition_vehicle(
        "V001",
        E.PICKUP,
        reserved.version,
        world.reservation,
        TransitionCtx(claim_id=claim.claim_id),
    )
    assert isinstance(on_time, Ok)
    assert world.vehicle("V001").state is S.IN_USE


def test_pickup_exactly_at_expiry_is_rejected(world):
    reserved = reserved_vehicle(world)
    claim = world.repo.query(ResourceClaim)[0]
    world.clock.advance(timedelta(minutes=10))

    result = world.core.commands.transition_vehicle(
        "V001",
        E.PICKUP,
        reserved.version,
        world.reservation,
        TransitionCtx(claim_id=claim.claim_id),
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_TRANSITION
    assert world.vehicle("V001").state is S.RESERVED
    assert world.space("S02").status is SpaceStatus.OCCUPIED


def test_pickup_writes_a_log_entry_for_the_vehicle_and_the_space(world):
    reserved = reserved_vehicle(world)
    claim = world.repo.query(ResourceClaim)[0]

    world.core.commands.transition_vehicle(
        "V001",
        E.PICKUP,
        reserved.version,
        world.reservation,
        TransitionCtx(claim_id=claim.claim_id),
    )

    vehicle_log = world.log_of("V001")
    assert [(r.previous_state, r.new_state, r.trigger) for r in vehicle_log] == [
        ("RESERVED", "IN_USE", "pickup"),
        ("AVAILABLE", "RESERVED", "reserve"),
    ]
    assert vehicle_log[0].actor == "reservation/U1"
    space_log = world.log_of("S02")
    assert (space_log[0].previous_state, space_log[0].new_state) == ("OCCUPIED", "AVAILABLE")


# --------------------------------------------------------------------------------- return (T4, T5)


def trip(world):
    """V001 is on a trip; S11 and S12 of H02 are free, H01 has S02 free."""
    return in_use_vehicle(world)


def test_return_to_a_named_space_occupies_it(world):
    view = trip(world)
    world.events.clear()

    result = world.core.commands.transition_vehicle(
        "V001",
        E.RETURN,
        view.version,
        world.reservation,
        TransitionCtx(parking_space_id="S11", battery_pct=55.0),
    )

    assert isinstance(result, Ok)
    vehicle = world.vehicle("V001")
    assert vehicle.state is S.RETURNED
    assert (vehicle.hub_id, vehicle.parking_space_id) == ("H02", "S11")
    assert vehicle.battery_pct == 55.0
    assert world.space("S11").status is SpaceStatus.OCCUPIED
    assert world.space("S11").occupant_vehicle_id == "V001"
    occupancy = [e for e in world.events if e.type == EventType.SPACE_OCCUPANCY_CHANGED.value]
    assert occupancy[0].payload["occupied_count"] == 1


def test_return_with_only_a_hub_takes_the_lowest_free_space(world):
    view = trip(world)

    result = world.core.commands.transition_vehicle(
        "V001", E.RETURN, view.version, world.reservation, TransitionCtx(hub_id="H02")
    )

    assert isinstance(result, Ok)
    assert world.vehicle("V001").parking_space_id == "S11"


def test_return_to_a_full_hub_fails_and_changes_nothing(world):
    view = trip(world)
    world.park("V101", "S11")
    world.park("V102", "S12")

    result = world.core.commands.transition_vehicle(
        "V001", E.RETURN, view.version, world.reservation, TransitionCtx(hub_id="H02")
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.HUB_FULL
    assert world.vehicle("V001").state is S.IN_USE


def test_return_to_an_occupied_space_fails(world):
    view = trip(world)
    world.park("V101", "S11")

    result = world.core.commands.transition_vehicle(
        "V001",
        E.RETURN,
        view.version,
        world.reservation,
        TransitionCtx(parking_space_id="S11"),
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.SPACE_NOT_FREE


def test_return_to_a_space_held_by_someone_else_fails(world):
    view = trip(world)
    world.core.commands.place_claim(
        ResourceType.SPACE,
        "S11",
        HolderKind.RESERVATION,
        "R-OTHER",
        world.clock.now() + timedelta(hours=1),
        world.clock.now() + timedelta(hours=2),
        world.reservation,
    )

    result = world.core.commands.transition_vehicle(
        "V001",
        E.RETURN,
        view.version,
        world.reservation,
        TransitionCtx(parking_space_id="S11"),
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.SPACE_NOT_FREE


def test_return_with_the_students_own_hold_consumes_it(world):
    view = trip(world)
    hold = world.core.commands.place_claim(
        ResourceType.SPACE,
        "S11",
        HolderKind.RESERVATION,
        "R1",
        world.clock.now(),
        world.clock.now() + timedelta(minutes=10),
        world.reservation,
    )
    assert isinstance(hold, Ok)

    result = world.core.commands.transition_vehicle(
        "V001",
        E.RETURN,
        view.version,
        world.reservation,
        TransitionCtx(parking_space_id="S11", claim_id=hold.value.claim_id),
    )

    assert isinstance(result, Ok)
    claims = world.core.queries.get_claims(
        "S11", world.clock.now(), world.clock.now() + timedelta(hours=1)
    )
    assert claims == []  # the hold is released


def test_return_to_a_hub_in_maintenance_is_unavailable(world):
    view = trip(world)
    hub = world.core.queries.get_hub("H02")
    assert isinstance(hub, Ok)
    world.core.commands.set_hub_status(
        "H02", HubStatus.MAINTENANCE, hub.value.version, world.monitoring
    )

    result = world.core.commands.transition_vehicle(
        "V001", E.RETURN, view.version, world.reservation, TransitionCtx(hub_id="H02")
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.RESOURCE_UNAVAILABLE


def test_return_needs_a_destination_and_a_valid_battery(world):
    view = trip(world)

    no_destination = world.core.commands.transition_vehicle(
        "V001", E.RETURN, view.version, world.reservation
    )
    bad_battery = world.core.commands.transition_vehicle(
        "V001",
        E.RETURN,
        view.version,
        world.reservation,
        TransitionCtx(hub_id="H02", battery_pct=120.0),
    )

    assert isinstance(no_destination, Err)
    assert no_destination.code is ErrorCode.INVALID_INPUT
    assert isinstance(bad_battery, Err)
    assert bad_battery.code is ErrorCode.INVALID_INPUT
    assert world.vehicle("V001").state is S.IN_USE


def test_faulty_trip_ends_in_maintenance_inside_the_space(world):
    view = trip(world)
    flagged = world.core.commands.transition_vehicle(
        "V001", E.REPORT_FAULT, view.version, world.iot
    )
    assert isinstance(flagged, Ok)
    assert flagged.value.state is S.IN_USE
    assert flagged.value.fault_flag is True

    plain_return = world.core.commands.transition_vehicle(
        "V001", E.RETURN, flagged.value.version, world.reservation, TransitionCtx(hub_id="H02")
    )
    assert isinstance(plain_return, Err)
    assert plain_return.code is ErrorCode.RESOURCE_UNAVAILABLE

    faulty = world.core.commands.transition_vehicle(
        "V001",
        E.RETURN_FAULTY,
        flagged.value.version,
        world.reservation,
        TransitionCtx(hub_id="H02"),
    )
    assert isinstance(faulty, Ok)
    assert faulty.value.state is S.MAINTENANCE
    assert world.space("S11").status is SpaceStatus.OCCUPIED  # a faulty vehicle still occupies


# ---------------------------------------------------------------------------- charging (T7, T8)


def charging_setup(world, state=S.RETURNED):
    world.park("V001", "S01", state=state, battery_pct=30.0)
    claim = world.core.commands.place_claim(
        ResourceType.CHARGING_POINT,
        "CP01",
        HolderKind.CHARGING_SESSION,
        "CS1",
        world.clock.now(),
        world.clock.now() + timedelta(hours=1),
        world.charging,
    )
    assert isinstance(claim, Ok)
    return claim.value.claim_id


def test_start_charging_in_the_bay_with_a_claim(world):
    claim_id = charging_setup(world)

    result = world.core.commands.transition_vehicle(
        "V001",
        E.START_CHARGING,
        1,
        world.charging,
        TransitionCtx(claim_id=claim_id, charging_point_id="CP01"),
    )

    assert isinstance(result, Ok)
    assert result.value.state is S.CHARGING


def test_start_charging_works_from_available_too(world):
    claim_id = charging_setup(world, state=S.AVAILABLE)

    result = world.core.commands.transition_vehicle(
        "V001",
        E.START_CHARGING,
        1,
        world.charging,
        TransitionCtx(claim_id=claim_id, charging_point_id="CP01"),
    )

    assert isinstance(result, Ok)


def test_start_charging_outside_the_bay_is_rejected(world):
    claim_id = charging_setup(world)
    world.park("V002", "S02", state=S.RETURNED)

    result = world.core.commands.transition_vehicle(
        "V002",
        E.START_CHARGING,
        1,
        world.charging,
        TransitionCtx(claim_id=claim_id, charging_point_id="CP01"),
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_INPUT


def test_start_charging_needs_a_charging_session_claim(world):
    world.park("V001", "S01", state=S.RETURNED)
    wrong = world.core.commands.place_claim(
        ResourceType.CHARGING_POINT,
        "CP01",
        HolderKind.DISPATCH_TASK,
        "T1",
        world.clock.now(),
        world.clock.now() + timedelta(hours=1),
        world.allocation,
    )
    assert isinstance(wrong, Ok)

    result = world.core.commands.transition_vehicle(
        "V001",
        E.START_CHARGING,
        1,
        world.charging,
        TransitionCtx(claim_id=wrong.value.claim_id, charging_point_id="CP01"),
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_INPUT


def test_start_charging_on_a_point_out_of_service_is_unavailable(world):
    claim_id = charging_setup(world)
    point = world.repo.get(ChargingPoint, "CP01")
    result_status = world.core.commands.set_charging_point_status(
        "CP01", ChargingPointStatus.OUT_OF_SERVICE, point.version, world.monitoring
    )
    assert isinstance(result_status, Ok)

    result = world.core.commands.transition_vehicle(
        "V001",
        E.START_CHARGING,
        1,
        world.charging,
        TransitionCtx(claim_id=claim_id, charging_point_id="CP01"),
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.RESOURCE_UNAVAILABLE


def test_finish_and_interrupt_charging(world):
    claim_id = charging_setup(world)
    started = world.core.commands.transition_vehicle(
        "V001",
        E.START_CHARGING,
        1,
        world.charging,
        TransitionCtx(claim_id=claim_id, charging_point_id="CP01"),
    )
    assert isinstance(started, Ok)

    finished = world.core.commands.transition_vehicle(
        "V001",
        E.FINISH_CHARGING,
        started.value.version,
        world.charging,
        TransitionCtx(battery_pct=100.0),
    )

    assert isinstance(finished, Ok)
    assert finished.value.state is S.AVAILABLE
    assert finished.value.battery_pct == 100.0


# ---------------------------------------------------------------------------------- permissions


def test_only_operator_or_system_may_repair_or_report_a_fault(world):
    world.park("V001", "S02")

    by_student = world.core.commands.transition_vehicle("V001", E.REPORT_FAULT, 1, world.student)
    by_sensor = world.core.commands.transition_vehicle("V001", E.REPORT_FAULT, 1, world.iot)

    assert isinstance(by_student, Err)
    assert by_student.code is ErrorCode.FORBIDDEN
    assert isinstance(by_sensor, Ok)
    assert by_sensor.value.state is S.MAINTENANCE

    repair_by_student = world.core.commands.transition_vehicle(
        "V001", E.REPAIR, by_sensor.value.version, world.student
    )
    repair_by_operator = world.core.commands.transition_vehicle(
        "V001", E.REPAIR, by_sensor.value.version, world.operator
    )

    assert isinstance(repair_by_student, Err)
    assert repair_by_student.code is ErrorCode.FORBIDDEN
    assert isinstance(repair_by_operator, Ok)
    assert repair_by_operator.value.state is S.AVAILABLE
    assert repair_by_operator.value.fault_flag is False


def test_repair_goes_on_to_available_and_logs_both_steps(world):
    world.park("V001", "S02", battery_pct=80.0)
    faulty = world.core.commands.transition_vehicle("V001", E.REPORT_FAULT, 1, world.operator)
    assert isinstance(faulty, Ok)
    world.events.clear()

    repaired = world.core.commands.transition_vehicle(
        "V001", E.REPAIR, faulty.value.version, world.operator
    )

    assert isinstance(repaired, Ok)
    assert repaired.value.state is S.AVAILABLE
    assert [r.trigger for r in world.log_of("V001")[:2]] == ["mark_ready", "repair"]
    changes = [e.payload["new"] for e in world.events if e.type == "VehicleStateChanged"]
    assert changes == ["RETURNED", "AVAILABLE"]


def test_repair_leaves_a_low_battery_vehicle_returned(world):
    world.park("V001", "S02", battery_pct=15.0)
    faulty = world.core.commands.transition_vehicle("V001", E.REPORT_FAULT, 1, world.operator)
    assert isinstance(faulty, Ok)

    repaired = world.core.commands.transition_vehicle(
        "V001", E.REPAIR, faulty.value.version, world.operator
    )

    assert isinstance(repaired, Ok)
    assert repaired.value.state is S.RETURNED  # at or below the threshold: it needs charging first
    assert repaired.value.fault_flag is False
