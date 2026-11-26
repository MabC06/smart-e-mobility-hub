"""apply_sensor_event: each event type, repeated events, and a bad feed (NFR-10)."""

import math
import random
from datetime import datetime, timedelta

import pytest

from core.domain.entities import StateChangeRecord
from core.domain.enums import (
    ChargingPointStatus,
    HolderKind,
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
from core.sensors import SensorEvent, SensorEventType
from core.services.commands import TransitionCtx

B = SensorEventType


def send(world, kind, entity_id, value=None, event_id="E1", actor=None, **kw):
    event = SensorEvent(
        kw.get("event_id", event_id),
        kw.get("source", "sim-1"),
        kind.value if isinstance(kind, SensorEventType) else kind,
        entity_id,
        kw.get("at", world.clock.now()),
        value,
    )
    return world.core.commands.apply_sensor_event(event, actor or world.iot)


def types(world):
    return [e.type for e in world.events]


def private_ev(world):
    result = world.core.commands.register_vehicle(
        Ownership.PRIVATE,
        "EV-1",
        VehicleType.E_SCOOTER,
        1.0,
        60.0,
        world.operator,
        owner_user_id="U1",
        connector_type="TYPE2",
    )
    assert isinstance(result, Ok)
    world.events.clear()
    return result.value.vehicle_id


# ------------------------------------------------------------------------------------ battery


def test_battery_level_updates_the_vehicle_and_announces_it(world):
    world.park("V001", "S02", battery_pct=80.0)

    result = send(world, B.BATTERY_LEVEL, "V001", 14.5)

    assert isinstance(result, Ok) and result.value.changed
    assert world.vehicle("V001").battery_pct == 14.5
    assert world.vehicle("V001").version == 2
    event = world.events[0]
    assert event.type == EventType.VEHICLE_BATTERY_CHANGED.value
    assert event.payload["previous"] == 80.0 and event.payload["new"] == 14.5
    assert event.payload["low"] is True


@pytest.mark.parametrize(("level", "low"), [(15.01, False), (15.0, True), (14.99, True)])
def test_the_low_flag_follows_the_threshold_at_or_below(world, level, low):
    world.park("V001", "S02", battery_pct=80.0)

    send(world, B.BATTERY_LEVEL, "V001", level)

    assert world.events[0].payload["low"] is low


def test_the_same_battery_level_twice_changes_nothing_the_second_time(world):
    world.park("V001", "S02")

    first = send(world, B.BATTERY_LEVEL, "V001", 50.0)
    version = world.vehicle("V001").version
    second = send(world, B.BATTERY_LEVEL, "V001", 50.0)

    assert isinstance(first, Ok) and first.value.changed
    assert isinstance(second, Ok) and not second.value.changed
    assert world.vehicle("V001").version == version
    assert types(world) == [EventType.VEHICLE_BATTERY_CHANGED.value]


def test_battery_changes_are_not_state_changes_and_are_not_logged(world):
    world.park("V001", "S02")

    send(world, B.BATTERY_LEVEL, "V001", 50.0)

    assert world.repo.query(StateChangeRecord) == []


# ----------------------------------------------------------------------------------- occupancy


def test_a_sensor_confirming_the_recorded_occupancy_changes_nothing(world):
    world.park("V001", "S02")
    version = world.space("S02").version

    result = send(world, B.SPACE_OCCUPIED, "S02", "V001")

    assert isinstance(result, Ok) and not result.value.changed
    assert world.space("S02").version == version


def test_a_private_ev_arrives_by_sensor_and_leaves_by_sensor(world):
    ev = private_ev(world)

    arrived = send(world, B.SPACE_OCCUPIED, "S02", ev)
    assert isinstance(arrived, Ok) and arrived.value.changed
    assert world.vehicle(ev).parking_space_id == "S02"
    assert world.space("S02").status is SpaceStatus.OCCUPIED
    assert world.core.check_invariants() == []

    left = send(world, B.SPACE_FREED, "S02", event_id="E2")
    assert isinstance(left, Ok) and left.value.changed
    assert world.vehicle(ev).parking_space_id is None
    assert world.space("S02").status is SpaceStatus.AVAILABLE
    assert world.core.check_invariants() == []


def test_freeing_a_free_space_is_a_confirmation(world):
    result = send(world, B.SPACE_FREED, "S02")

    assert isinstance(result, Ok) and not result.value.changed


def test_a_sensor_cannot_move_a_fleet_vehicle(world):
    world.park("V001", "S02")
    world.park("V002", "S03")
    before = world.repo.export_state()

    elsewhere = send(world, B.SPACE_OCCUPIED, "S01", "V001")  # V001 is recorded in S02
    freed = send(
        world, B.SPACE_FREED, "S02", event_id="E2"
    )  # a fleet vehicle only leaves by pickup
    swapped = send(world, B.SPACE_OCCUPIED, "S02", "V002", event_id="E3")

    for result in (elsewhere, freed, swapped):
        assert isinstance(result, Err)
        assert result.code is ErrorCode.INVALID_TRANSITION
    assert world.repo.export_state() == before


def test_a_sensor_cannot_put_a_vehicle_on_a_trip_into_a_space(world):
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")
    commands = world.core.commands
    commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    commands.transition_vehicle(
        "V001", VehicleEvent.PICKUP, 2, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    before = world.repo.export_state()

    result = send(world, B.SPACE_OCCUPIED, "S03", "V001")

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_TRANSITION
    assert "records" in result.message
    assert world.repo.export_state() == before
    assert world.vehicle("V001").state is VehicleState.IN_USE


def test_a_private_ev_cannot_arrive_in_an_occupied_or_held_space(world):
    ev = private_ev(world)
    world.park("V001", "S02")

    occupied = send(world, B.SPACE_OCCUPIED, "S02", ev)
    assert isinstance(occupied, Err)

    world.core.commands.place_claim(
        ResourceType.SPACE,
        "S03",
        HolderKind.RESERVATION,
        "R9",
        world.clock.now(),
        world.clock.now() + timedelta(minutes=10),
        world.reservation,
    )
    held = send(world, B.SPACE_OCCUPIED, "S03", ev, event_id="E2")
    assert isinstance(held, Err)
    assert held.code is ErrorCode.SPACE_NOT_FREE
    assert world.vehicle(ev).parking_space_id is None


# ------------------------------------------------------------------------------------ faults


def test_a_charger_fault_takes_the_point_out_of_service_and_a_clear_brings_it_back(world):
    fault = send(world, B.CHARGER_FAULT, "CP01")
    assert isinstance(fault, Ok) and fault.value.changed
    point = world.core.queries.list_charging_points("H01")[0]
    assert point.status is ChargingPointStatus.OUT_OF_SERVICE
    assert world.events[0].type == EventType.CHARGING_POINT_STATUS_CHANGED.value

    again = send(world, B.CHARGER_FAULT, "CP01", event_id="E2")
    assert isinstance(again, Ok) and not again.value.changed

    cleared = send(world, B.CHARGER_FAULT, "CP01", False, event_id="E3")
    assert isinstance(cleared, Ok) and cleared.value.changed
    assert world.core.queries.list_charging_points("H01")[0].status is ChargingPointStatus.AVAILABLE

    nothing_to_clear = send(world, B.CHARGER_FAULT, "CP01", False, event_id="E4")
    assert isinstance(nothing_to_clear, Ok) and not nothing_to_clear.value.changed


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (VehicleState.AVAILABLE, VehicleState.MAINTENANCE),
        (VehicleState.RETURNED, VehicleState.MAINTENANCE),
        (VehicleState.CHARGING, VehicleState.MAINTENANCE),
    ],
)
def test_a_vehicle_fault_moves_a_parked_vehicle_to_maintenance(world, state, expected):
    world.park("V001", "S01", state=state)

    result = send(world, B.VEHICLE_FAULT, "V001")

    assert isinstance(result, Ok) and result.value.changed
    assert world.vehicle("V001").state is expected
    assert world.log_of("V001")[0].trigger == "report_fault"
    assert world.log_of("V001")[0].actor == "iot_sim/SIM"


def test_a_vehicle_fault_during_a_trip_only_sets_the_flag(world):
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")
    commands = world.core.commands
    commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    commands.transition_vehicle(
        "V001", VehicleEvent.PICKUP, 2, world.reservation, TransitionCtx(claim_id=claim_id)
    )

    result = send(world, B.VEHICLE_FAULT, "V001")

    assert isinstance(result, Ok) and result.value.changed
    assert world.vehicle("V001").state is VehicleState.IN_USE
    assert world.vehicle("V001").fault_flag is True
    repeat = send(world, B.VEHICLE_FAULT, "V001", event_id="E2")
    assert isinstance(repeat, Ok) and not repeat.value.changed


def test_a_repeated_vehicle_fault_is_a_confirmation(world):
    world.park("V001", "S02")
    send(world, B.VEHICLE_FAULT, "V001")
    logged = len(world.log_of("V001"))

    again = send(world, B.VEHICLE_FAULT, "V001", event_id="E2")

    assert isinstance(again, Ok) and not again.value.changed
    assert len(world.log_of("V001")) == logged


def test_a_heartbeat_changes_nothing_and_is_announced(world):
    before = world.repo.export_state()

    result = send(world, B.HEARTBEAT, "H01")

    assert isinstance(result, Ok) and not result.value.changed
    assert world.repo.export_state() == before
    assert types(world) == [EventType.SENSOR_HEARTBEAT.value]
    assert world.events[0].payload["entity_id"] == "H01"


# ---------------------------------------------------------------------------- a bad feed


BAD_EVENTS = [
    ("no event id", dict(event_id="")),
    ("blank source", dict(source="   ")),
    ("unknown type", dict(kind="EXPLODE")),
    ("no type", dict(kind="")),
    ("no entity", dict(entity_id="")),
    ("naive time", dict(at=datetime(2026, 11, 2, 8, 0))),
    ("not a time", dict(at="yesterday")),
    ("battery above 100", dict(kind=B.BATTERY_LEVEL, entity_id="V001", value=100.1)),
    ("battery below 0", dict(kind=B.BATTERY_LEVEL, entity_id="V001", value=-0.1)),
    ("battery not a number", dict(kind=B.BATTERY_LEVEL, entity_id="V001", value="full")),
    ("battery is a bool", dict(kind=B.BATTERY_LEVEL, entity_id="V001", value=True)),
    ("battery is NaN", dict(kind=B.BATTERY_LEVEL, entity_id="V001", value=math.nan)),
    ("battery is infinite", dict(kind=B.BATTERY_LEVEL, entity_id="V001", value=math.inf)),
    ("battery missing", dict(kind=B.BATTERY_LEVEL, entity_id="V001", value=None)),
    ("occupied without vehicle", dict(kind=B.SPACE_OCCUPIED, entity_id="S02", value=None)),
    ("occupied by a number", dict(kind=B.SPACE_OCCUPIED, entity_id="S02", value=7)),
    ("charger fault with a string", dict(kind=B.CHARGER_FAULT, entity_id="CP01", value="yes")),
    ("unknown vehicle", dict(kind=B.BATTERY_LEVEL, entity_id="V404", value=50.0)),
    ("unknown space", dict(kind=B.SPACE_FREED, entity_id="S404")),
    ("unknown charging point", dict(kind=B.CHARGER_FAULT, entity_id="CP404")),
    ("unknown vehicle for a fault", dict(kind=B.VEHICLE_FAULT, entity_id="V404")),
    ("occupied by an unknown vehicle", dict(kind=B.SPACE_OCCUPIED, entity_id="S02", value="V404")),
]


@pytest.mark.parametrize(("label", "fields"), BAD_EVENTS, ids=[b[0] for b in BAD_EVENTS])
def test_a_bad_event_is_rejected_without_any_change_and_is_announced(world, label, fields):
    world.park("V001", "S02")
    before = world.repo.export_state()
    version = world.core.snapshots.export_snapshot().version
    world.events.clear()
    fields = dict(fields)
    kind = fields.pop("kind", B.HEARTBEAT)
    entity_id = fields.pop("entity_id", "H01")
    value = fields.pop("value", None)

    result = send(world, kind, entity_id, value, **fields)

    assert isinstance(result, Err), label
    assert result.code in {ErrorCode.INVALID_INPUT, ErrorCode.NOT_FOUND}
    assert world.repo.export_state() == before
    assert world.core.snapshots.export_snapshot().version == version
    assert types(world) == [EventType.SENSOR_EVENT_REJECTED.value]
    assert world.events[0].payload["code"] == result.code.value
    assert world.events[0].payload["reason"]


def test_only_the_simulator_may_send_events(world):
    world.park("V001", "S02")

    for actor in (world.student, world.operator, world.monitoring, world.reservation):
        result = send(world, B.BATTERY_LEVEL, "V001", 50.0, actor=actor)
        assert isinstance(result, Err)
        assert result.code is ErrorCode.FORBIDDEN
    assert world.vehicle("V001").battery_pct == 80.0


def test_a_rejection_is_logged_as_a_warning(world, caplog):
    with caplog.at_level("WARNING", logger="core.sensors"):
        send(world, B.BATTERY_LEVEL, "V404", 50.0, event_id="E77")

    assert any("E77" in record.message for record in caplog.records)


def test_the_rejection_handler_cannot_break_the_intake(world):
    def broken(_event):
        raise RuntimeError("handler bug")

    world.core.events.subscribe(EventType.SENSOR_EVENT_REJECTED, broken)

    result = send(world, B.BATTERY_LEVEL, "V404", 50.0)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.NOT_FOUND


@pytest.mark.parametrize("seed", range(6))
def test_a_garbage_feed_never_crashes_or_breaks_a_rule(world, seed):
    """Valid and broken events mixed at random: nothing raises, the invariants always hold, and
    every rejected event leaves the whole store exactly as it was."""
    rng = random.Random(seed)
    world.park("V001", "S01")
    world.park("V002", "S03", battery_pct=10.0)
    ev = private_ev(world)
    kinds = [*SensorEventType] * 3 + ["NOPE", "", None, 7]
    entities = ["V001", "V002", ev, "S01", "S02", "S03", "S11", "CP01", "H01", "ghost", "", None, 3]
    values = [None, True, False, 0, 14.99, 15, 50.5, 100, 101, -1, "V001", "V002", ev, "", math.nan]
    times = [world.clock.now()] * 8 + [datetime(2026, 11, 2), "bad", None]

    accepted = rejected = 0
    cheap = world.repo_kind == "sql"  # on SQL the commit counter proves nothing was committed
    for index in range(300):
        before = world.repo.version() if cheap else world.repo.export_state()
        result = send(
            world,
            rng.choice(kinds),
            rng.choice(entities),
            rng.choice(values),
            event_id=rng.choice([f"E{index}"] * 8 + ["", None]),
            source=rng.choice(["sim"] * 8 + ["", None]),
            at=rng.choice(times),
        )
        if isinstance(result, Err):
            rejected += 1
            after = world.repo.version() if cheap else world.repo.export_state()
            assert after == before, f"seed {seed}, event {index}"
        else:
            accepted += 1
        assert world.core.check_invariants() == [], f"seed {seed}, event {index}"
    assert accepted > 10 and rejected > 100
