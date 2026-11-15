"""Tests for AllocationService lifecycle and transactions (BR-M4-08, D-016, D-017, D-018, D-020)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from allocation.config import AllocationConfig
from allocation.models import DISPATCH_TASK_SPEC, DispatchTask, DispatchTaskStatus
from allocation.service import AllocationService
from core.actor import Actor
from core.clock import FixedClock
from core.domain.entities import ResourceClaim, Vehicle
from core.domain.enums import (
    ClaimStatus,
    HolderKind,
    ResourceType,
    Role,
    VehicleState,
    VehicleType,
)
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.providers import ProviderPort
from core.repository.memory import InMemoryRepository
from core.result import Err, Ok, Result
from core.seed import HubSpec, NetworkSpec, VehicleSpec, space_id


@dataclass(frozen=True, slots=True)
class StubBookingDemand:
    reservation_id: str
    kind: str
    hub_id: str
    vehicle_id: str
    resource_id: str
    claim_id: str
    start_at: datetime
    end_at: datetime
    hold_expires_at: datetime


@dataclass(frozen=True, slots=True)
class StubUpcomingBookings:
    as_of: datetime
    horizon_end: datetime
    bookings: tuple[StubBookingDemand, ...]


@dataclass(frozen=True, slots=True)
class StubOpenTripDemand:
    trip_id: str
    reservation_id: str
    vehicle_id: str
    origin_hub_id: str
    destination_hub_id: str | None
    picked_up_at: datetime
    expected_return_at: datetime
    is_overdue: bool


@dataclass(frozen=True, slots=True)
class StubOpenTrips:
    as_of: datetime
    trips: tuple[StubOpenTripDemand, ...]


class StubReservationDemand:
    """Stub implementing M2's D-020 ReservationDemand signature (upcoming_bookings & open_trips)."""

    def __init__(
        self,
        as_of: datetime,
        bookings_by_hub: dict[str, tuple[StubBookingDemand, ...]] | None = None,
        trips_by_hub: dict[str, tuple[StubOpenTripDemand, ...]] | None = None,
    ) -> None:
        self._as_of = as_of
        self._bookings = bookings_by_hub or {}
        self._trips = trips_by_hub or {}
        self.seen_horizons: list[timedelta] = []

    def upcoming_bookings(self, hub_id: str, horizon: timedelta) -> Result[StubUpcomingBookings]:
        if horizon <= timedelta(0):
            return Err(ErrorCode.INVALID_INPUT, "horizon must be positive")
        self.seen_horizons.append(horizon)
        return Ok(
            StubUpcomingBookings(
                as_of=self._as_of,
                horizon_end=self._as_of + horizon,
                bookings=self._bookings.get(hub_id, ()),
            )
        )

    def open_trips(self, hub_id: str) -> Result[StubOpenTrips]:
        return Ok(StubOpenTrips(as_of=self._as_of, trips=self._trips.get(hub_id, ())))


@pytest.fixture
def allocation_world() -> tuple[CoreFacade, AllocationService, Actor]:
    """Create a test environment with DispatchTask table, seeded hubs and ReservationDemand."""
    fixed_now = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    core = CoreFacade(InMemoryRepository(), clock=FixedClock(fixed_now))
    core.register_entity(DISPATCH_TASK_SPEC)
    core.register_provider(ProviderPort.RESERVATION_DEMAND, StubReservationDemand(fixed_now))
    operator = Actor("OP01", Role.OPERATOR, "allocation")

    # Hub H01: surplus of 4 vehicles (total 4 vehicles, 10 spaces)
    # Hub H02: deficit (0 vehicles, 10 spaces)
    spec = NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Hub 1",
                "Z1",
                10,
                0,
                vehicles=tuple(
                    VehicleSpec(f"V00{i}", f"PLATE-{i}", VehicleType.E_BIKE, 80.0) for i in range(4)
                ),
            ),
            HubSpec("H02", "Hub 2", "Z2", 10, 0),
        )
    )
    load_res = core.commands.load_network(spec, operator)
    assert isinstance(load_res, Ok)

    cfg = AllocationConfig(safety_stock=1, parking_buffer=2, min_dispatch_battery=30.0)
    service = AllocationService(core, cfg)
    return core, service, operator


def test_full_dispatch_task_lifecycle(
    allocation_world: tuple[CoreFacade, AllocationService, Actor],
) -> None:
    """Verify task lifecycle: RECOMMENDED -> APPROVED -> IN_PROGRESS -> COMPLETED (BR-M4-08)."""
    core, service, operator = allocation_world
    expected_now = core.queries.get_config().as_of

    task = DispatchTask(
        task_id="TASK-T1-001",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=2,
        vehicle_ids="V000,V001",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
        reason="Manual test task",
    )
    with core.unit_of_work() as uow:
        uow.repository.add(task)
        assert isinstance(uow.commit(), Ok)

    # 1. Approve places claims on vehicles and destination spaces using queries.get_config().as_of
    approve_res = service.approve_task(task.task_id, operator)
    assert isinstance(approve_res, Ok)
    approved_task = approve_res.value
    assert approved_task.status is DispatchTaskStatus.APPROVED

    claims = core.query_entities(
        ResourceClaim,
        lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
    )
    assert len(claims) == 4
    assert all(c.status is ClaimStatus.ACTIVE for c in claims)
    assert all(c.start_at == expected_now for c in claims)

    # 2. Carry out pickup: moves vehicles to IN_USE and task to IN_PROGRESS
    pickup_res = service.carry_out_pickup(task.task_id, operator)
    assert isinstance(pickup_res, Ok)
    in_prog_task = pickup_res.value
    assert in_prog_task.status is DispatchTaskStatus.IN_PROGRESS

    for vid in in_prog_task.assigned_vehicles:
        v_view = core.queries.get_vehicle(vid)
        assert isinstance(v_view, Ok)
        assert v_view.value.state is VehicleState.IN_USE

    # 3. Carry out return: delivers vehicles to H02, releases claims
    return_res = service.carry_out_return(task.task_id, operator)
    assert isinstance(return_res, Ok)
    completed_task = return_res.value
    assert completed_task.status is DispatchTaskStatus.COMPLETED

    for vid in completed_task.assigned_vehicles:
        v_view = core.queries.get_vehicle(vid)
        assert isinstance(v_view, Ok)
        assert v_view.value.hub_id == "H02"
        assert v_view.value.state is VehicleState.AVAILABLE

    claims_after = core.query_entities(
        ResourceClaim,
        lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
    )
    assert all(c.status is ClaimStatus.RELEASED for c in claims_after)
    assert core.check_invariants() == []


def test_carry_out_return_uses_held_destination_space_when_others_claimed(
    allocation_world: tuple[CoreFacade, AllocationService, Actor],
) -> None:
    """BR-M4-04, D-017: Return succeeds into held space when all other hub spaces are claimed."""
    core, service, operator = allocation_world
    now = core.queries.get_config().as_of

    task = DispatchTask(
        task_id="TASK-FULL-DEST",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=1,
        vehicle_ids="V000",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
    )
    with core.unit_of_work() as uow:
        uow.repository.add(task)
        assert isinstance(uow.commit(), Ok)

    assert isinstance(service.approve_task(task.task_id, operator), Ok)
    assert isinstance(service.carry_out_pickup(task.task_id, operator), Ok)

    # Claim all remaining 9 spaces at H02 so ONLY the task's held H02-S001 remains free for it
    res_actor = Actor("RES", Role.OPERATOR, "reservation")
    for idx in range(2, 11):
        claim_r = core.commands.place_claim(
            ResourceType.SPACE,
            space_id("H02", idx),
            HolderKind.RESERVATION,
            f"R-FILL-{idx}",
            now,
            now + timedelta(minutes=30),
            res_actor,
        )
        assert isinstance(claim_r, Ok)

    ret_res = service.carry_out_return(task.task_id, operator, battery_pct=78.0)
    assert isinstance(ret_res, Ok)
    assert ret_res.value.status is DispatchTaskStatus.COMPLETED

    v0 = core.queries.get_vehicle("V000")
    assert isinstance(v0, Ok)
    assert v0.value.parking_space_id == space_id("H02", 1)
    assert v0.value.battery_pct == 78.0
    assert core.check_invariants() == []


def test_cancel_approved_task_releases_claims(
    allocation_world: tuple[CoreFacade, AllocationService, Actor],
) -> None:
    """UC-M4-04: Cancelling an approved task releases holds."""
    core, service, operator = allocation_world

    task = DispatchTask(
        task_id="TASK-T2-001",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=1,
        vehicle_ids="V000",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
        reason="Cancel test task",
    )
    with core.unit_of_work() as uow:
        uow.repository.add(task)
        assert isinstance(uow.commit(), Ok)

    service.approve_task(task.task_id, operator)
    cancel_res = service.cancel_task(task.task_id, operator, reason="Operator changed mind")
    assert isinstance(cancel_res, Ok)
    assert cancel_res.value.status is DispatchTaskStatus.CANCELLED

    claims = core.query_entities(
        ResourceClaim,
        lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
    )
    assert all(c.status is ClaimStatus.RELEASED for c in claims)
    assert core.check_invariants() == []


def test_service_plan_and_queries(
    allocation_world: tuple[CoreFacade, AllocationService, Actor],
) -> None:
    """Test service.plan() generates tasks and list_tasks / get_task work."""
    core, service, operator = allocation_world

    plan_res = service.plan(operator, slot_id="SLOT-1")
    assert isinstance(plan_res, Ok)
    tasks = plan_res.value
    assert len(tasks) >= 1

    all_tasks = service.list_tasks()
    assert len(all_tasks) >= 1

    first_task = all_tasks[0]
    fetched = service.get_task(first_task.task_id)
    assert isinstance(fetched, Ok)
    assert fetched.value.task_id == first_task.task_id

    missing = service.get_task("NON-EXISTENT")
    assert missing.is_err


def test_plan_requires_reservation_demand_provider_and_complete_methods() -> None:
    """D-020, M4-2: Missing or incomplete ReservationDemand returns RESOURCE_UNAVAILABLE."""
    now = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    operator = Actor("OP01", Role.OPERATOR, "allocation")
    spec = NetworkSpec(hubs=(HubSpec("H01", "Hub 1", "Z1", 5, 0),))

    # Case 1: Unregistered ReservationDemand
    core_missing = CoreFacade(InMemoryRepository(), clock=FixedClock(now))
    core_missing.register_entity(DISPATCH_TASK_SPEC)
    assert isinstance(core_missing.commands.load_network(spec, operator), Ok)
    res_missing = AllocationService(core_missing).plan(operator)
    assert isinstance(res_missing, Err)
    assert res_missing.code is ErrorCode.RESOURCE_UNAVAILABLE

    # Case 2: Incomplete provider (missing open_trips) -> no silent zero-demand fallback
    class PartialDemand:
        def upcoming_bookings(
            self, hub_id: str, horizon: timedelta
        ) -> Result[StubUpcomingBookings]:
            return Ok(StubUpcomingBookings(now, now + horizon, ()))

    core_partial = CoreFacade(InMemoryRepository(), clock=FixedClock(now))
    core_partial.register_entity(DISPATCH_TASK_SPEC)
    assert isinstance(core_partial.commands.load_network(spec, operator), Ok)
    core_partial.register_provider(ProviderPort.RESERVATION_DEMAND, PartialDemand())
    res_partial = AllocationService(core_partial).plan(operator)
    assert isinstance(res_partial, Err)
    assert res_partial.code is ErrorCode.RESOURCE_UNAVAILABLE


def test_plan_counts_m2_bookings_and_open_trips_with_horizon_and_expired_claims() -> None:
    """M4-1, D-017: Reads M2 demand types, skips None destinations and expired claims."""
    now = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    operator = Actor("OP01", Role.OPERATOR, "allocation")
    core = CoreFacade(InMemoryRepository(), clock=FixedClock(now))
    core.register_entity(DISPATCH_TASK_SPEC)

    spec = NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Hub 1",
                "Z1",
                10,
                0,
                vehicles=tuple(
                    VehicleSpec(f"V1_{i}", f"P1-{i}", VehicleType.E_BIKE, 85.0) for i in range(4)
                ),
            ),
            HubSpec("H02", "Hub 2", "Z2", 10, 0),
        )
    )
    assert isinstance(core.commands.load_network(spec, operator), Ok)

    # Expired ACTIVE claim on V1_0 must NOT stop V1_0 from being planned for dispatch
    assert isinstance(
        core.commands.place_claim(
            ResourceType.VEHICLE,
            "V1_0",
            HolderKind.RESERVATION,
            "OLD-RES",
            now - timedelta(minutes=40),
            now - timedelta(minutes=1),
            operator,
        ),
        Ok,
    )

    bookings = {
        "H02": (
            StubBookingDemand(
                "RES-1",
                "RENTAL_PICKUP",
                "H02",
                "V1_1",
                "V1_1",
                "C1",
                now + timedelta(minutes=5),
                now + timedelta(minutes=25),
                now + timedelta(minutes=15),
            ),
            StubBookingDemand(
                "RES-2",
                "PRIVATE_PARKING",
                "H02",
                "PV1",
                "H02-S001",
                "C2",
                now + timedelta(minutes=5),
                now + timedelta(minutes=25),
                now + timedelta(minutes=15),
            ),
        )
    }
    trips = {
        "H01": (
            # destination None at origin H01: must NOT be counted as promised return at H01
            StubOpenTripDemand(
                "TRP-NONE", "R10", "V90", "H01", None, now, now + timedelta(minutes=5), False
            ),
            # destined for H02 within 30-min horizon: counted only at H02
            StubOpenTripDemand(
                "TRP-IN", "R11", "V91", "H01", "H02", now, now + timedelta(minutes=10), False
            ),
        ),
        "H02": (
            StubOpenTripDemand(
                "TRP-IN", "R11", "V91", "H01", "H02", now, now + timedelta(minutes=10), False
            ),
            # beyond 30-min horizon: must NOT count in F_in
            StubOpenTripDemand(
                "TRP-LATE", "R12", "V92", "H01", "H02", now, now + timedelta(minutes=90), False
            ),
        ),
    }
    stub = StubReservationDemand(now, bookings_by_hub=bookings, trips_by_hub=trips)
    core.register_provider(ProviderPort.RESERVATION_DEMAND, stub)

    cfg = AllocationConfig(horizon_minutes=30, safety_stock=1, parking_buffer=2)
    service = AllocationService(core, cfg)
    res = service.plan(operator, slot_id="SLOT-M2")

    assert isinstance(res, Ok)
    assert all(isinstance(h, timedelta) and h == timedelta(minutes=30) for h in stub.seen_horizons)
    # H02: 1 RENTAL_PICKUP + safety_stock=1 => need 2 (PRIVATE_PARKING ignored for pickup need);
    # H01 has 4 available (including V1_0 with expired claim) -> surplus 3 -> moves 2 vehicles
    assert len(res.value) == 1
    assert res.value[0].quantity == 2


def test_approve_task_claim_conflict_marks_failed_cleanly(
    allocation_world: tuple[CoreFacade, AllocationService, Actor],
) -> None:
    """UC-M4-02: Conflict rolls back partial claims and marks FAILED without UoW nesting."""
    core, service, operator = allocation_world
    now = core.queries.get_config().as_of
    res_actor = Actor("RES", Role.OPERATOR, "reservation")

    task = DispatchTask(
        task_id="TASK-CONFLICT",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=2,
        vehicle_ids="V000,V001",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
    )
    with core.unit_of_work() as uow:
        uow.repository.add(task)
        assert isinstance(uow.commit(), Ok)

    # Pre-claim V001 so claiming V000 succeeds inside UoW and V001 triggers CLAIM_CONFLICT
    assert isinstance(
        core.commands.place_claim(
            ResourceType.VEHICLE,
            "V001",
            HolderKind.RESERVATION,
            "RES-99",
            now,
            now + timedelta(minutes=30),
            res_actor,
        ),
        Ok,
    )

    err = service.approve_task(task.task_id, operator)
    assert isinstance(err, Err)
    assert err.code is ErrorCode.CLAIM_CONFLICT

    failed_task = core.get_entity(DispatchTask, task.task_id)
    assert failed_task is not None
    assert failed_task.status is DispatchTaskStatus.FAILED

    leaked = core.query_entities(
        ResourceClaim,
        lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
    )
    assert leaked == []
    assert core.check_invariants() == []


def test_approve_task_errors_and_skips_claimed_dest_spaces(
    allocation_world: tuple[CoreFacade, AllocationService, Actor],
) -> None:
    """Verify error branches and skipping claimed destination spaces on approval."""
    core, service, operator = allocation_world
    now = core.queries.get_config().as_of

    assert service.approve_task("MISSING-TASK", operator).is_err

    empty_task = DispatchTask(
        task_id="TASK-EMPTY",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=0,
        vehicle_ids="",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
    )
    task = DispatchTask(
        task_id="TASK-ADJ",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=2,
        vehicle_ids="V000,V001",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
    )
    with core.unit_of_work() as uow:
        uow.repository.add(empty_task)
        uow.repository.add(task)
        assert isinstance(uow.commit(), Ok)

    assert service.approve_task(empty_task.task_id, operator).is_err

    bad_qty_zero = service.approve_task(task.task_id, operator, adjusted_quantity=0)
    assert isinstance(bad_qty_zero, Err)
    assert bad_qty_zero.code is ErrorCode.INVALID_INPUT

    bad_qty_high = service.approve_task(task.task_id, operator, adjusted_quantity=5)
    assert isinstance(bad_qty_high, Err)
    assert bad_qty_high.code is ErrorCode.INVALID_INPUT

    # External claim on H02-S001 -> approve_task(adjusted_quantity=1) skips it to H02-S002
    res_actor = Actor("RES", Role.OPERATOR, "reservation")
    assert isinstance(
        core.commands.place_claim(
            ResourceType.SPACE,
            space_id("H02", 1),
            HolderKind.RESERVATION,
            "RES-SPC",
            now,
            now + timedelta(minutes=20),
            res_actor,
        ),
        Ok,
    )
    ok_res = service.approve_task(task.task_id, operator, adjusted_quantity=1)
    assert isinstance(ok_res, Ok)
    assert ok_res.value.quantity == 1
    held_spaces = core.query_entities(
        ResourceClaim,
        lambda c: (
            c.holder_kind is HolderKind.DISPATCH_TASK
            and c.holder_ref == task.task_id
            and c.resource_type == ResourceType.SPACE
        ),
    )
    assert [c.resource_id for c in held_spaces] == [space_id("H02", 2)]


def test_invalid_lifecycle_transitions(
    allocation_world: tuple[CoreFacade, AllocationService, Actor],
) -> None:
    """Verify error handling on invalid state transitions."""
    core, service, operator = allocation_world

    task = DispatchTask(
        task_id="TASK-T3-001",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=1,
        vehicle_ids="V000",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
    )
    with core.unit_of_work() as uow:
        uow.repository.add(task)
        uow.commit()

    assert service.carry_out_pickup(task.task_id, operator).is_err
    assert service.carry_out_return(task.task_id, operator).is_err


def test_pickup_validates_vehicle_location(
    allocation_world: tuple[CoreFacade, AllocationService, Actor],
) -> None:
    """Verify pickup fails if vehicle is not at source hub."""
    core, service, operator = allocation_world

    task = DispatchTask(
        task_id="TASK-LOC-001",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=1,
        vehicle_ids="V000",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
    )
    with core.unit_of_work() as uow:
        uow.repository.add(task)
        uow.commit()

    assert isinstance(service.approve_task(task.task_id, operator), Ok)

    with core.unit_of_work() as uow:
        v = uow.repository.get(Vehicle, "V000")
        if v:
            v.hub_id = "H02"
            uow.repository.update(v, expected_version=v.version)
            uow.commit()

    pickup_err = service.carry_out_pickup(task.task_id, operator)
    assert pickup_err.is_err
    assert "not at source hub" in pickup_err.message
