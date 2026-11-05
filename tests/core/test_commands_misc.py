"""register_vehicle, occupy_space, free_space, set_hub_status, set_charging_point_status."""

from datetime import timedelta

from core.domain.entities import ChargingPoint, ParkingSpace, Vehicle
from core.domain.enums import (
    ChargingPointStatus,
    ClaimStatus,
    HolderKind,
    HubStatus,
    Ownership,
    ResourceType,
    SpaceStatus,
    VehicleEvent,
    VehicleState,
    VehicleType,
)
from core.errors import ErrorCode
from core.events import EventType
from core.result import Err, Ok
from core.services.transition_ctx import TransitionCtx


def register_fleet(world, plate="BIKE-1", space="S02", **kw):
    return world.core.commands.register_vehicle(
        Ownership.FLEET,
        plate,
        VehicleType.E_BIKE,
        0.5,
        kw.pop("battery_pct", 90.0),
        kw.pop("actor", world.iot),
        parking_space_id=space,
        **kw,
    )


def register_private(world, plate="EV-1", **kw):
    return world.core.commands.register_vehicle(
        Ownership.PRIVATE,
        plate,
        VehicleType.E_SCOOTER,
        1.2,
        kw.pop("battery_pct", 50.0),
        kw.pop("actor", world.charging),
        owner_user_id=kw.pop("owner_user_id", "U1"),
        connector_type=kw.pop("connector_type", "TYPE2"),
        **kw,
    )


# ------------------------------------------------------------------------- register_vehicle


def test_register_a_fleet_vehicle_occupies_its_space(world):
    result = register_fleet(world)

    assert isinstance(result, Ok)
    assert result.value.state is VehicleState.AVAILABLE
    assert (result.value.hub_id, result.value.parking_space_id) == ("H01", "S02")
    assert world.space("S02").status is SpaceStatus.OCCUPIED
    assert world.space("S02").occupant_vehicle_id == result.value.vehicle_id
    assert world.log_of(result.value.vehicle_id)[0].trigger == "register"


def test_register_a_private_vehicle_starts_away_from_every_hub(world):
    result = register_private(world)

    assert isinstance(result, Ok)
    assert result.value.state is VehicleState.IN_USE
    assert result.value.hub_id is None
    assert result.value.parking_space_id is None
    assert result.value.owner_user_id == "U1"
    assert result.value.connector_type == "TYPE2"


def test_register_rules(world):
    cases = [
        (register_fleet(world, plate=" "), ErrorCode.INVALID_INPUT),
        (register_fleet(world, space=None), ErrorCode.INVALID_INPUT),
        (register_fleet(world, owner_user_id="U1"), ErrorCode.INVALID_INPUT),
        (register_fleet(world, space="NOPE"), ErrorCode.NOT_FOUND),
        (register_fleet(world, battery_pct=101.0), ErrorCode.INVALID_INPUT),
        (register_private(world, connector_type=""), ErrorCode.INVALID_INPUT),
        (register_private(world, owner_user_id="NOPE"), ErrorCode.NOT_FOUND),
        (register_private(world, owner_user_id="U2"), ErrorCode.INVALID_INPUT),
        (register_private(world, parking_space_id="S02"), ErrorCode.INVALID_INPUT),
        (register_fleet(world, actor=world.student), ErrorCode.FORBIDDEN),
    ]
    for result, expected in cases:
        assert isinstance(result, Err)
        assert result.code is expected
    assert world.repo.query(Vehicle) == []


def test_register_rejects_duplicates_and_occupied_spaces(world):
    assert isinstance(register_fleet(world, plate="A"), Ok)

    same_plate = register_fleet(world, plate="A", space="S03")
    occupied = register_fleet(world, plate="B", space="S02")

    assert isinstance(same_plate, Err) and same_plate.code is ErrorCode.INVALID_INPUT
    assert isinstance(occupied, Err) and occupied.code is ErrorCode.SPACE_NOT_FREE


def test_register_respects_the_hub_capacity(world):
    for index, space in enumerate(["S01", "S02", "S03"]):
        assert isinstance(register_fleet(world, plate=f"B{index}", space=space), Ok)
    hub = world.core.queries.get_hub("H01")
    assert isinstance(hub, Ok)
    assert hub.value.occupied == 3 and hub.value.free_spaces == 0


# ------------------------------------------------------------------ occupy_space / free_space


def private_ev(world):
    result = register_private(world)
    assert isinstance(result, Ok)
    return result.value


def test_a_private_ev_arrives_and_leaves(world):
    ev = private_ev(world)
    world.events.clear()

    arrived = world.core.commands.occupy_space(ev.vehicle_id, "S02", 1, world.reservation)

    assert isinstance(arrived, Ok)
    assert arrived.value.status is SpaceStatus.OCCUPIED
    assert world.vehicle(ev.vehicle_id).parking_space_id == "S02"
    assert world.vehicle(ev.vehicle_id).hub_id == "H01"
    assert world.vehicle(ev.vehicle_id).state is VehicleState.AVAILABLE
    assert [e.type for e in world.events] == [
        EventType.VEHICLE_STATE_CHANGED.value,
        EventType.SPACE_OCCUPANCY_CHANGED.value,
    ]

    left = world.core.commands.free_space("S02", arrived.value.version, world.reservation)

    assert isinstance(left, Ok)
    assert left.value.status is SpaceStatus.AVAILABLE
    assert world.vehicle(ev.vehicle_id).parking_space_id is None
    assert world.vehicle(ev.vehicle_id).state is VehicleState.IN_USE


def test_a_private_ev_arrives_and_departs_with_the_state_events(world):
    ev = private_ev(world)
    commands = world.core.commands

    arrived = commands.transition_vehicle(
        ev.vehicle_id,
        VehicleEvent.ARRIVE,
        ev.version,
        world.reservation,
        TransitionCtx(hub_id="H01"),
    )

    assert isinstance(arrived, Ok)
    assert arrived.value.state is VehicleState.AVAILABLE
    assert (arrived.value.hub_id, arrived.value.parking_space_id) == ("H01", "S01")
    assert world.log_of(ev.vehicle_id)[0].trigger == "arrive"

    departed = commands.transition_vehicle(
        ev.vehicle_id, VehicleEvent.DEPART, arrived.value.version, world.reservation
    )

    assert isinstance(departed, Ok)
    assert departed.value.state is VehicleState.IN_USE
    assert departed.value.parking_space_id is None
    assert world.repo.get(ParkingSpace, "S01").status is SpaceStatus.AVAILABLE


def test_a_private_ev_cannot_depart_while_charging(world):
    ev = private_ev(world)
    world.core.commands.occupy_space(ev.vehicle_id, "S01", 1, world.reservation)
    parked = world.vehicle(ev.vehicle_id)
    claim = world.core.commands.place_claim(
        ResourceType.CHARGING_POINT,
        "CP01",
        HolderKind.CHARGING_SESSION,
        "CS1",
        world.clock.now(),
        world.clock.now() + timedelta(minutes=30),
        world.charging,
    )
    assert isinstance(claim, Ok)
    charging = world.core.commands.transition_vehicle(
        ev.vehicle_id,
        VehicleEvent.START_CHARGING,
        parked.version,
        world.charging,
        TransitionCtx(claim_id=claim.value.claim_id, charging_point_id="CP01"),
    )
    assert isinstance(charging, Ok)

    result = world.core.commands.transition_vehicle(
        ev.vehicle_id, VehicleEvent.DEPART, charging.value.version, world.reservation
    )

    assert isinstance(result, Err) and result.code is ErrorCode.INVALID_TRANSITION
    assert world.vehicle(ev.vehicle_id).state is VehicleState.CHARGING


def test_arrive_and_depart_are_for_private_vehicles_only(world):
    fleet = register_fleet(world)
    assert isinstance(fleet, Ok)

    for event in (VehicleEvent.ARRIVE, VehicleEvent.DEPART):
        result = world.core.commands.transition_vehicle(
            fleet.value.vehicle_id, event, fleet.value.version, world.reservation
        )
        assert isinstance(result, Err) and result.code is ErrorCode.INVALID_TRANSITION


def test_a_student_cannot_move_a_vehicle_in_or_out_of_a_hub(world):
    ev = private_ev(world)

    result = world.core.commands.transition_vehicle(
        ev.vehicle_id, VehicleEvent.ARRIVE, ev.version, world.student, TransitionCtx(hub_id="H01")
    )

    assert isinstance(result, Err) and result.code is ErrorCode.FORBIDDEN


def test_a_private_ev_on_the_road_cannot_report_a_fault(world):
    ev = private_ev(world)

    result = world.core.commands.transition_vehicle(
        ev.vehicle_id, VehicleEvent.REPORT_FAULT, ev.version, world.operator
    )

    assert isinstance(result, Err) and result.code is ErrorCode.INVALID_TRANSITION
    assert world.vehicle(ev.vehicle_id).fault_flag is False


def test_arrival_is_refused_when_the_hub_is_full(world):
    ev = private_ev(world)
    for index, space in enumerate(["S01", "S02"]):
        assert isinstance(register_fleet(world, plate=f"F{index}", space=space), Ok)

    result = world.core.commands.transition_vehicle(
        ev.vehicle_id,
        VehicleEvent.ARRIVE,
        ev.version,
        world.reservation,
        TransitionCtx(hub_id="H01"),
    )

    assert isinstance(result, Ok)  # the third space of the small test Hub is still free
    second = register_private(world, plate="EV-2")
    assert isinstance(second, Ok)
    full = world.core.commands.transition_vehicle(
        second.value.vehicle_id,
        VehicleEvent.ARRIVE,
        second.value.version,
        world.reservation,
        TransitionCtx(hub_id="H01"),
    )
    assert isinstance(full, Err) and full.code is ErrorCode.HUB_FULL


def test_arrival_turns_the_claim_into_the_occupancy(world):
    ev = private_ev(world)
    claim = world.core.commands.place_claim(
        ResourceType.SPACE,
        "S02",
        HolderKind.RESERVATION,
        "R9",
        world.clock.now(),
        world.clock.now() + timedelta(minutes=10),
        world.reservation,
    )
    assert isinstance(claim, Ok)

    result = world.core.commands.occupy_space(
        ev.vehicle_id, "S02", 1, world.reservation, claim.value.claim_id
    )

    assert isinstance(result, Ok)
    assert (
        world.core.queries.get_claims(
            "S02", world.clock.now(), world.clock.now() + timedelta(hours=1)
        )
        == []
    )


def test_arrival_is_rejected_when_the_space_is_held_by_someone_else(world):
    ev = private_ev(world)
    world.core.commands.place_claim(
        ResourceType.SPACE,
        "S02",
        HolderKind.RESERVATION,
        "R-OTHER",
        world.clock.now(),
        world.clock.now() + timedelta(minutes=10),
        world.reservation,
    )

    result = world.core.commands.occupy_space(ev.vehicle_id, "S02", 1, world.reservation)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.SPACE_NOT_FREE
    assert world.space("S02").status is SpaceStatus.AVAILABLE


def test_arrival_rules(world):
    ev = private_ev(world)
    world.park("V101", "S03")
    commands = world.core.commands

    fleet = commands.occupy_space("V101", "S02", 1, world.reservation)
    taken = commands.occupy_space(
        ev.vehicle_id, "S03", world.space("S03").version, world.reservation
    )
    stale = commands.occupy_space(ev.vehicle_id, "S02", 9, world.reservation)
    unknown_space = commands.occupy_space(ev.vehicle_id, "NOPE", 1, world.reservation)
    unknown_vehicle = commands.occupy_space("NOPE", "S02", 1, world.reservation)
    forbidden = commands.occupy_space(ev.vehicle_id, "S02", 1, world.charging)

    assert fleet.code is ErrorCode.INVALID_INPUT  # type: ignore[union-attr]
    assert taken.code is ErrorCode.SPACE_NOT_FREE  # type: ignore[union-attr]
    assert stale.code is ErrorCode.VERSION_CONFLICT  # type: ignore[union-attr]
    assert unknown_space.code is ErrorCode.NOT_FOUND  # type: ignore[union-attr]
    assert unknown_vehicle.code is ErrorCode.NOT_FOUND  # type: ignore[union-attr]
    assert forbidden.code is ErrorCode.FORBIDDEN  # type: ignore[union-attr]


def test_a_parked_vehicle_cannot_arrive_twice(world):
    ev = private_ev(world)
    world.core.commands.occupy_space(ev.vehicle_id, "S02", 1, world.reservation)

    again = world.core.commands.occupy_space(ev.vehicle_id, "S03", 1, world.reservation)

    assert isinstance(again, Err)
    assert again.code is ErrorCode.INVALID_TRANSITION


def test_free_space_rules(world):
    world.park("V101", "S03")
    commands = world.core.commands

    empty = commands.free_space("S02", 1, world.reservation)
    fleet = commands.free_space("S03", world.space("S03").version, world.reservation)
    stale = commands.free_space("S03", 99, world.reservation)

    assert empty.code is ErrorCode.INVALID_TRANSITION  # type: ignore[union-attr]
    assert fleet.code is ErrorCode.INVALID_INPUT  # type: ignore[union-attr]
    assert stale.code is ErrorCode.VERSION_CONFLICT  # type: ignore[union-attr]
    assert world.space("S03").status is SpaceStatus.OCCUPIED


# ---------------------------------------------------------------------------------- statuses


def test_set_hub_status_stores_it_logs_it_and_announces_it(world):
    hub = world.core.queries.get_hub("H01")
    assert isinstance(hub, Ok)

    result = world.core.commands.set_hub_status(
        "H01", HubStatus.WARNING, hub.value.version, world.monitoring
    )

    assert isinstance(result, Ok)
    assert result.value.status is HubStatus.WARNING
    assert result.value.version == hub.value.version + 1
    assert world.log_of("H01")[0].new_state == "WARNING"
    assert [e.type for e in world.events] == [EventType.HUB_STATUS_CHANGED.value]


def test_setting_the_same_hub_status_changes_nothing(world):
    hub = world.core.queries.get_hub("H01")
    assert isinstance(hub, Ok)

    result = world.core.commands.set_hub_status(
        "H01", HubStatus.ACTIVE, hub.value.version, world.monitoring
    )

    assert isinstance(result, Ok)
    assert result.value.version == hub.value.version
    assert world.events == []


def test_hub_status_rules(world):
    commands = world.core.commands
    student = commands.set_hub_status("H01", HubStatus.CRITICAL, 1, world.student)
    stale = commands.set_hub_status("H01", HubStatus.CRITICAL, 5, world.monitoring)
    unknown = commands.set_hub_status("NOPE", HubStatus.CRITICAL, 1, world.monitoring)

    assert student.code is ErrorCode.FORBIDDEN  # type: ignore[union-attr]
    assert stale.code is ErrorCode.VERSION_CONFLICT  # type: ignore[union-attr]
    assert unknown.code is ErrorCode.NOT_FOUND  # type: ignore[union-attr]


def test_set_charging_point_status(world):
    result = world.core.commands.set_charging_point_status(
        "CP01", ChargingPointStatus.OUT_OF_SERVICE, 1, world.charging
    )

    assert isinstance(result, Ok)
    assert result.value.status is ChargingPointStatus.OUT_OF_SERVICE
    assert world.repo.get(ChargingPoint, "CP01").version == 2  # type: ignore[union-attr]
    assert world.events[0].payload["new"] == "OUT_OF_SERVICE"
    assert world.events[0].payload["hub_id"] == "H01"


def test_charging_point_status_rules(world):
    commands = world.core.commands
    student = commands.set_charging_point_status(
        "CP01", ChargingPointStatus.CHARGING, 1, world.student
    )
    stale = commands.set_charging_point_status(
        "CP01", ChargingPointStatus.CHARGING, 4, world.charging
    )
    unknown = commands.set_charging_point_status(
        "NOPE", ChargingPointStatus.CHARGING, 1, world.charging
    )

    assert student.code is ErrorCode.FORBIDDEN  # type: ignore[union-attr]
    assert stale.code is ErrorCode.VERSION_CONFLICT  # type: ignore[union-attr]
    assert unknown.code is ErrorCode.NOT_FOUND  # type: ignore[union-attr]


def test_claim_status_after_arrival_is_released(world):
    ev = private_ev(world)
    claim = world.core.commands.place_claim(
        ResourceType.SPACE,
        "S02",
        HolderKind.RESERVATION,
        "R9",
        world.clock.now(),
        world.clock.now() + timedelta(minutes=10),
        world.reservation,
    )
    assert isinstance(claim, Ok)
    world.core.commands.occupy_space(
        ev.vehicle_id, "S02", 1, world.reservation, claim.value.claim_id
    )

    from core.domain.entities import ResourceClaim

    stored = world.repo.get(ResourceClaim, claim.value.claim_id)
    assert stored is not None
    assert stored.status is ClaimStatus.RELEASED
