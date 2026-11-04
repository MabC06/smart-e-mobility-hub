"""InvariantChecker: it accepts a good store, names each kind of corruption, and a seeded random
sequence of commands never breaks a rule (NFR-06, NFR-07, NFR-08, BR-M1-01 to BR-M1-03)."""

import random
from datetime import timedelta

import pytest

from core.domain.entities import ChargingPoint, Hub, ParkingSpace, ResourceClaim, Vehicle
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
from core.domain.invariants import InvariantChecker, InvariantCode
from core.repository.base import IntegrityViolationError
from core.result import Ok
from core.services.commands import TransitionCtx


def codes(world):
    return sorted(v.code.value for v in InvariantChecker.check(world.repo))


def test_an_empty_and_a_normal_world_have_no_violations(world):
    assert codes(world) == []
    world.park("V001", "S02")
    world.park("V002", "S03", state=VehicleState.MAINTENANCE)
    assert codes(world) == []
    assert world.core.check_invariants() == []


def edit(world, entity_type, entity_id, **changes):
    entity = world.repo.get(entity_type, entity_id)
    assert entity is not None
    for field, value in changes.items():
        setattr(entity, field, value)
    if hasattr(entity, "version"):
        world.repo.update(entity, entity.version)
    else:
        world.repo.update(entity)


def corrupt(world, action, sql_refuses=False):
    """Apply a corruption and say whether the store accepted it.

    The SQL database already refuses some of them with its own constraints (foreign key, unique,
    check). For those, the test asserts the refusal instead of the checker's message.
    """
    if world.repo_kind == "sql" and sql_refuses:
        with pytest.raises(IntegrityViolationError):
            action()
        return False
    action()
    return True


def test_hub_counts_must_match(world):
    edit(world, Hub, "H01", parking_capacity=4)
    edit(world, Hub, "H02", charging_point_count=1)

    assert codes(world) == [InvariantCode.HUB_POINT_COUNT, InvariantCode.HUB_SPACE_COUNT]


def test_a_hub_cannot_hold_more_vehicles_than_its_capacity(world):
    world.park("V001", "S01")
    world.park("V002", "S02")
    world.park("V003", "S03")
    edit(world, Hub, "H01", parking_capacity=2)

    assert InvariantCode.HUB_OVER_CAPACITY in codes(world)


def test_a_charging_point_needs_a_bay_in_its_own_hub(world):
    if corrupt(
        world,
        lambda: edit(world, ChargingPoint, "CP01", parking_space_id="NOPE"),
        sql_refuses=True,
    ):
        assert codes(world) == [InvariantCode.BAY_MISSING]

    edit(world, ChargingPoint, "CP01", parking_space_id="S11")
    assert codes(world) == [InvariantCode.BAY_WRONG_HUB]


def test_two_charging_points_cannot_share_a_bay(world):
    edit(world, Hub, "H01", charging_point_count=2)

    if corrupt(
        world,
        lambda: world.repo.add(ChargingPoint("CP02", "H01", "S01", 11.0)),
        sql_refuses=True,
    ):
        assert codes(world) == [InvariantCode.BAY_SHARED]


def test_space_and_vehicle_must_agree(world):
    world.park("V001", "S02")
    edit(world, ParkingSpace, "S02", occupant_vehicle_id="V999")
    assert InvariantCode.SPACE_OCCUPANT_MISMATCH in codes(world)

    edit(world, ParkingSpace, "S02", occupant_vehicle_id="V001")
    assert codes(world) == []
    edit(world, ParkingSpace, "S03", occupant_vehicle_id="V001")  # free space naming an occupant
    assert InvariantCode.SPACE_OCCUPANT_MISMATCH in codes(world)


def test_two_vehicles_cannot_share_a_space(world):
    world.park("V001", "S02")
    world.park("V002", "S03")

    if corrupt(
        world,
        lambda: edit(world, Vehicle, "V002", parking_space_id="S02"),
        sql_refuses=True,
    ):
        assert InvariantCode.SPACE_OCCUPANT_MISMATCH in codes(world)


def test_vehicle_location_rules(world):
    world.park("V001", "S02")
    if corrupt(
        world,
        lambda: edit(world, Vehicle, "V001", hub_id=None),
        sql_refuses=True,
    ):
        assert InvariantCode.VEHICLE_LOCATION in codes(world)

    # on a trip but at a Hub: a rule across rows and columns, so the database accepts it
    edit(world, Vehicle, "V001", hub_id="H01", state=VehicleState.IN_USE)
    assert InvariantCode.VEHICLE_LOCATION in codes(world)


def test_a_parked_fleet_vehicle_must_have_a_space(world):
    world.park("V001", "S02")
    space = world.space("S02")
    space.status = SpaceStatus.AVAILABLE
    space.occupant_vehicle_id = None
    world.repo.update(space, space.version)
    edit(world, Vehicle, "V001", hub_id=None, parking_space_id=None)

    assert codes(world) == [InvariantCode.VEHICLE_LOCATION]


def test_ownership_and_battery_rules(world):
    world.park("V001", "S02")
    if corrupt(
        world,
        lambda: edit(world, Vehicle, "V001", owner_user_id="U1"),
        sql_refuses=True,
    ):
        assert InvariantCode.VEHICLE_OWNERSHIP in codes(world)

    if corrupt(
        world,
        lambda: edit(world, Vehicle, "V001", owner_user_id=None, battery_pct=140.0),
        sql_refuses=True,
    ):
        assert codes(world) == [InvariantCode.VEHICLE_BATTERY]


def test_a_charging_vehicle_must_be_in_a_bay(world):
    world.park("V001", "S02", state=VehicleState.CHARGING)
    assert codes(world) == [InvariantCode.CHARGING_OUTSIDE_BAY]

    world2 = world
    world2.park("V002", "S01", state=VehicleState.CHARGING)  # S01 is the bay of CP01
    assert codes(world2) == [InvariantCode.CHARGING_OUTSIDE_BAY]  # only V001 is wrong


def test_active_claims_must_not_overlap_and_must_point_to_something(world, make_claim):
    world.park("V001", "S02")
    world.repo.add(make_claim("C1", "V001", 0, 10))
    world.repo.add(make_claim("C2", "V001", 5, 15, holder_ref="R2"))
    assert codes(world) == [InvariantCode.CLAIM_OVERLAP]

    edit(world, ResourceClaim, "C2", status=ClaimStatus.RELEASED)  # a released claim does not count
    assert codes(world) == []

    world.repo.add(make_claim("C3", "GHOST", 0, 10, holder_ref="R3"))
    assert codes(world) == [InvariantCode.CLAIM_RESOURCE_MISSING]


def private_ev(state, **kw):
    return Vehicle(
        "P1",
        "EV-1",
        Ownership.PRIVATE,
        VehicleType.E_SCOOTER,
        50.0,
        1.0,
        state=state,
        owner_user_id="U1",
        connector_type="TYPE2",
        **kw,
    )


def test_a_private_vehicle_away_from_every_hub_is_in_use(world):
    world.repo.add(private_ev(VehicleState.IN_USE))

    assert codes(world) == []


def test_a_private_vehicle_that_is_not_in_use_must_be_parked(world):
    world.repo.add(private_ev(VehicleState.AVAILABLE))

    assert codes(world) == [InvariantCode.VEHICLE_LOCATION]


# ------------------------------------------------------------------ seeded random sequences


VALID_EVENTS = {
    VehicleState.AVAILABLE: [
        VehicleEvent.RESERVE,
        VehicleEvent.START_CHARGING,
    ],
    VehicleState.RESERVED: [
        VehicleEvent.PICKUP,
        VehicleEvent.PICKUP,
        VehicleEvent.RELEASE_RESERVATION,
    ],
    VehicleState.IN_USE: [
        VehicleEvent.RETURN,
        VehicleEvent.RETURN_FAULTY,
    ],
    VehicleState.RETURNED: [
        VehicleEvent.MARK_READY,
        VehicleEvent.START_CHARGING,
    ],
    VehicleState.CHARGING: [
        VehicleEvent.FINISH_CHARGING,
        VehicleEvent.INTERRUPT_CHARGING,
    ],
    VehicleState.MAINTENANCE: [VehicleEvent.REPAIR],
}


def guided_transition(world, rng, vehicle):
    """An event that fits the vehicle's state, with the claim and destination it needs."""
    commands = world.core.commands
    now = world.clock.now()
    away = vehicle.state is VehicleState.IN_USE
    parked = vehicle.state in (VehicleState.AVAILABLE, VehicleState.RETURNED)
    if vehicle.ownership is Ownership.PRIVATE and (away or (parked and rng.random() < 0.4)):
        event = VehicleEvent.ARRIVE if away else VehicleEvent.DEPART
        ctx = TransitionCtx(hub_id=rng.choice(["H01", "H02"]) if away else None)
        return commands.transition_vehicle(
            vehicle.vehicle_id, event, vehicle.version, world.operator, ctx
        )
    event = rng.choice(VALID_EVENTS[vehicle.state])
    if vehicle.state is not VehicleState.MAINTENANCE and rng.random() < 0.05:
        event = VehicleEvent.REPORT_FAULT
    ctx = TransitionCtx(
        min_battery=rng.choice([0.0, 20.0]), battery_pct=rng.choice([None, 30.0, 95.0])
    )
    claim_id = None
    if event in (VehicleEvent.RESERVE, VehicleEvent.PICKUP):
        mine = world.repo.query(
            ResourceClaim,
            lambda c: (
                c.resource_id == vehicle.vehicle_id
                and c.status is ClaimStatus.ACTIVE
                and c.start_at <= now < c.end_at
            ),
        )
        if mine:
            claim_id = mine[0].claim_id
        elif event is VehicleEvent.RESERVE:
            placed = commands.place_claim(
                ResourceType.VEHICLE,
                vehicle.vehicle_id,
                HolderKind.RESERVATION,
                f"G{rng.randint(1, 99)}",
                now,
                now + timedelta(minutes=rng.randint(5, 30)),
                world.operator,
            )
            claim_id = placed.value.claim_id if isinstance(placed, Ok) else None
    elif event is VehicleEvent.START_CHARGING:
        placed = commands.place_claim(
            ResourceType.CHARGING_POINT,
            "CP01",
            HolderKind.CHARGING_SESSION,
            f"CS{rng.randint(1, 99)}",
            now,
            now + timedelta(minutes=rng.randint(5, 30)),
            world.operator,
        )
        claim_id = placed.value.claim_id if isinstance(placed, Ok) else None
        ctx = TransitionCtx(claim_id=claim_id, charging_point_id="CP01")
        claim_id = None
    elif event in (VehicleEvent.RETURN, VehicleEvent.RETURN_FAULTY):
        ctx = TransitionCtx(hub_id=rng.choice(["H01", "H02"]), battery_pct=ctx.battery_pct)
    if claim_id is not None:
        ctx = TransitionCtx(
            min_battery=ctx.min_battery, claim_id=claim_id, battery_pct=ctx.battery_pct
        )
    return commands.transition_vehicle(
        vehicle.vehicle_id, event, vehicle.version, world.operator, ctx
    )


def random_operation(world, rng):
    """One random command, mostly with plausible inputs so that many of them succeed."""
    commands = world.core.commands
    queries = world.core.queries
    vehicles = queries.find_vehicles()
    vehicle = rng.choice(vehicles) if vehicles else None
    claims = world.repo.query(ResourceClaim, lambda c: c.status is ClaimStatus.ACTIVE)
    kind = rng.choice(
        ["claim", "claim", "release", "transition", "transition", "transition", "transition"]
        + ["occupy", "free", "hub_status", "point_status", "register", "clock"]
    )
    now = world.clock.now()
    if kind == "clock":
        world.clock.advance(timedelta(minutes=rng.randint(1, 20)))
    elif kind == "claim":
        resource_type = rng.choice(list(ResourceType))
        pool = {
            ResourceType.VEHICLE: [v.vehicle_id for v in vehicles],
            ResourceType.SPACE: [s.parking_space_id for s in world.repo.query(ParkingSpace)],
            ResourceType.CHARGING_POINT: ["CP01"],
        }[resource_type]
        if pool:
            start = now + timedelta(minutes=rng.randint(-3, 30))
            commands.place_claim(
                resource_type,
                rng.choice(pool),
                rng.choice(list(HolderKind)),
                f"H{rng.randint(1, 6)}",
                start,
                start + timedelta(minutes=rng.randint(1, 30)),
                world.operator,
            )
    elif kind == "release" and claims:
        commands.release_claim(rng.choice(claims).claim_id, world.operator)
    elif kind == "transition" and vehicle is not None and rng.random() < 0.75:
        guided_transition(world, rng, vehicle)
    elif kind == "transition" and vehicle is not None:
        event = rng.choice(list(VehicleEvent))
        own = [c for c in claims if c.resource_id == vehicle.vehicle_id]
        space_claims = [c for c in claims if c.resource_type is ResourceType.SPACE]
        claim = (
            rng.choice(own + space_claims) if (own or space_claims) and rng.random() < 0.8 else None
        )
        ctx = TransitionCtx(
            min_battery=rng.choice([0.0, 20.0, 50.0]),
            claim_id=claim.claim_id if claim else None,
            hub_id=rng.choice([None, "H01", "H02"]),
            parking_space_id=rng.choice([None, "S01", "S02", "S03", "S11", "S12"]),
            charging_point_id=rng.choice([None, "CP01"]),
            battery_pct=rng.choice([None, None, 5.0, 40.0, 90.0]),
        )
        version = vehicle.version if rng.random() < 0.9 else vehicle.version + 1
        commands.transition_vehicle(vehicle.vehicle_id, event, version, world.operator, ctx)
    elif kind == "occupy":
        private = [v for v in vehicles if v.ownership is Ownership.PRIVATE]
        spaces = world.repo.query(ParkingSpace)
        if private and spaces:
            space = rng.choice(spaces)
            claim = next(
                (c.claim_id for c in claims if c.resource_id == space.parking_space_id), None
            )
            commands.occupy_space(
                rng.choice(private).vehicle_id,
                space.parking_space_id,
                space.version,
                world.operator,
                claim if rng.random() < 0.5 else None,
            )
    elif kind == "free":
        spaces = world.repo.query(ParkingSpace)
        space = rng.choice(spaces)
        commands.free_space(space.parking_space_id, space.version, world.operator)
    elif kind == "hub_status":
        hub = rng.choice(world.repo.query(Hub))
        commands.set_hub_status(
            hub.hub_id, rng.choice(list(HubStatus)), hub.version, world.operator
        )
    elif kind == "point_status":
        point = world.repo.query(ChargingPoint)[0]
        commands.set_charging_point_status(
            point.charging_point_id,
            rng.choice(list(ChargingPointStatus)),
            point.version,
            world.operator,
        )
    elif kind == "register":
        if rng.random() < 0.5:
            commands.register_vehicle(
                Ownership.PRIVATE,
                f"EV-{rng.randint(1, 4)}",
                VehicleType.E_BIKE,
                1.0,
                rng.choice([10.0, 60.0]),
                world.operator,
                owner_user_id="U1",
                connector_type="TYPE2",
            )
        else:
            spaces = world.repo.query(ParkingSpace, lambda s: s.status is SpaceStatus.AVAILABLE)
            if spaces:
                commands.register_vehicle(
                    Ownership.FLEET,
                    f"FL-{rng.randint(1, 8)}",
                    VehicleType.E_SCOOTER,
                    0.5,
                    rng.choice([10.0, 60.0, 95.0]),
                    world.operator,
                    parking_space_id=rng.choice(spaces).parking_space_id,
                )


@pytest.mark.parametrize("seed", range(24))
def test_random_commands_never_break_an_invariant(world, seed):
    rng = random.Random(seed)
    world.park("V001", "S01", battery_pct=80.0)  # S01 is the charging bay
    world.park("V002", "S03", battery_pct=10.0)

    steps = 250 if world.repo_kind == "memory" else 100  # SQL is slower; 24 seeds still run
    for step in range(steps):
        random_operation(world, rng)
        violations = world.core.check_invariants()
        assert violations == [], f"seed {seed}, step {step}: {violations}"


def test_the_random_sequences_actually_exercise_the_rules(world):
    """Guard against a vacuous fuzz test: many commands must succeed, not only fail."""
    rng = random.Random(1)
    world.park("V001", "S01")  # S01 is the charging bay
    world.park("V002", "S03", battery_pct=10.0)
    for _ in range(600):
        random_operation(world, rng)

    from core.domain.entities import StateChangeRecord

    log = world.repo.query(StateChangeRecord)
    assert len({r.trigger for r in log if r.entity_type == "Vehicle"}) >= 9
    assert len(world.repo.query(ResourceClaim)) > 20
    assert isinstance(world.core.queries.get_vehicle("V001"), Ok)


def test_regression_a_private_vehicle_cannot_enter_the_rental_trip(world):
    """Found by the random test (seed 7): a private EV that was picked up could be parked again
    while still IN_USE, so a later return left its old space occupied."""
    registered = world.core.commands.register_vehicle(
        Ownership.PRIVATE,
        "EV-9",
        VehicleType.E_SCOOTER,
        1.0,
        70.0,
        world.operator,
        owner_user_id="U1",
        connector_type="TYPE2",
    )
    assert isinstance(registered, Ok)
    vehicle_id = registered.value.vehicle_id
    arrived = world.core.commands.occupy_space(vehicle_id, "S02", 1, world.operator)
    assert isinstance(arrived, Ok)

    for event in (
        VehicleEvent.RESERVE,
        VehicleEvent.RELEASE_RESERVATION,
        VehicleEvent.PICKUP,
        VehicleEvent.RETURN,
        VehicleEvent.RETURN_FAULTY,
    ):
        result = world.core.commands.transition_vehicle(
            vehicle_id, event, world.vehicle(vehicle_id).version, world.operator
        )
        assert result.code.value == "INVALID_TRANSITION", event  # type: ignore[union-attr]
    assert world.core.check_invariants() == []


def test_a_private_vehicle_on_a_trip_must_not_be_at_a_hub(world):
    world.repo.add(
        Vehicle(
            "P1",
            "EV-1",
            Ownership.PRIVATE,
            VehicleType.E_SCOOTER,
            50.0,
            1.0,
            state=VehicleState.IN_USE,
            hub_id="H01",
            parking_space_id="S02",
            owner_user_id="U1",
            connector_type="TYPE2",
        )
    )
    space = world.space("S02")
    space.status = SpaceStatus.OCCUPIED
    space.occupant_vehicle_id = "P1"
    world.repo.update(space, space.version)

    assert codes(world) == [InvariantCode.VEHICLE_LOCATION]
