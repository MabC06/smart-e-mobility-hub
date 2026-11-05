"""Tests for AllocationService lifecycle and transactions (BR-M4-08, D-016, D-017, D-018)."""

import pytest

from allocation.config import AllocationConfig
from allocation.models import DISPATCH_TASK_SPEC, DispatchTask, DispatchTaskStatus
from allocation.service import AllocationService
from core.actor import Actor
from core.domain.entities import ResourceClaim
from core.domain.enums import ClaimStatus, HolderKind, Role, VehicleState, VehicleType
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, VehicleSpec


@pytest.fixture
def allocation_world():
    """Create a test environment with registered DispatchTask table and seeded hubs."""
    core = CoreFacade(InMemoryRepository())
    core.register_entity(DISPATCH_TASK_SPEC)
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


def test_full_dispatch_task_lifecycle(allocation_world):
    """Verify task lifecycle: RECOMMENDED -> APPROVED -> IN_PROGRESS -> COMPLETED (BR-M4-08)."""
    core, service, operator = allocation_world

    # Manually create a recommended task: H01 -> H02 for 2 vehicles
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

    # 1. Approve places claims on vehicles and destination spaces
    approve_res = service.approve_task(task.task_id, operator)
    assert isinstance(approve_res, Ok)
    approved_task = approve_res.value
    assert approved_task.status is DispatchTaskStatus.APPROVED

    # Check claims placed
    claims = core.query_entities(
        ResourceClaim,
        lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
    )
    assert len(claims) > 0
    assert all(c.status is ClaimStatus.ACTIVE for c in claims)

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

    # Check vehicles are now at H02 and AVAILABLE
    for vid in completed_task.assigned_vehicles:
        v_view = core.queries.get_vehicle(vid)
        assert isinstance(v_view, Ok)
        assert v_view.value.hub_id == "H02"
        assert v_view.value.state is VehicleState.AVAILABLE

    # Check claims released
    claims_after = core.query_entities(
        ResourceClaim,
        lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
    )
    assert all(c.status is ClaimStatus.RELEASED for c in claims_after)

    # 4. Check core invariants hold (no violations!)
    violations = core.check_invariants()
    assert violations == []


def test_cancel_approved_task_releases_claims(allocation_world):
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


def test_service_plan_and_queries(allocation_world):
    """Test service.plan() generates tasks and list_tasks / get_task work."""
    core, service, operator = allocation_world

    # Plan with default world (H01 has 4 vehicles, H02 has 0)
    plan_res = service.plan(operator, slot_id="SLOT-1")
    assert isinstance(plan_res, Ok)
    tasks = plan_res.value
    assert len(tasks) >= 1

    # Check list_tasks
    all_tasks = service.list_tasks()
    assert len(all_tasks) >= 1

    # Check get_task
    first_task = all_tasks[0]
    fetched = service.get_task(first_task.task_id)
    assert isinstance(fetched, Ok)
    assert fetched.value.task_id == first_task.task_id

    # Non-existent get
    missing = service.get_task("NON-EXISTENT")
    assert missing.is_err


def test_approve_task_errors(allocation_world):
    """Verify error branches when approving tasks."""
    core, service, operator = allocation_world

    # Task not found
    err_not_found = service.approve_task("MISSING-TASK", operator)
    assert err_not_found.is_err

    # Create task with no vehicles
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
    with core.unit_of_work() as uow:
        uow.repository.add(empty_task)
        uow.commit()

    err_no_v = service.approve_task(empty_task.task_id, operator)
    assert err_no_v.is_err


def test_invalid_lifecycle_transitions(allocation_world):
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

    # Cannot pickup RECOMMENDED task before approving
    pickup_err = service.carry_out_pickup(task.task_id, operator)
    assert pickup_err.is_err

    # Cannot return RECOMMENDED task
    return_err = service.carry_out_return(task.task_id, operator)
    assert return_err.is_err
