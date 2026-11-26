"""Tests for Redistribution Planning Engine (FR-10.1 - FR-10.3, BR-M4-03 - BR-M4-06, NFR-13)."""

import pytest

from allocation.config import AllocationConfig
from allocation.planner import HubDemandInfo, HubStateView, HubVehicleInfo, plan_redistribution
from core.domain.enums import Ownership, VehicleState, VehicleType


def _make_vehicle(
    vid: str,
    vtype: VehicleType = VehicleType.E_BIKE,
    battery: float = 80.0,
    state: VehicleState = VehicleState.AVAILABLE,
) -> HubVehicleInfo:
    return HubVehicleInfo(
        vehicle_id=vid,
        vehicle_type=vtype,
        battery_level=battery,
        state=state,
        ownership=Ownership.FLEET,
    )


@pytest.mark.tc_m4_001
def test_planner_worked_example_matches_design_doc():
    """Verify worked example from docs/design/architecture/allocation-algorithm-design.md §4.3.

    Setup:
    - H08: needs 5, urgency 0.29 (F_out=14, S=3, A=12, P_free=11)
    - H01: needs 6, urgency 0.12 (F_out=47, S=3, A=44, P_free=20)
    - H05: surplus 15 (A=26, F_out=8, S=3, P_free=20)
    - H03: surplus 4 (A=27, F_out=20, S=3, P_free=20)
    - Distances: H05-H08=1, H03-H01=1, H05-H01=2, H03-H08=3

    Expected Tasks:
    - Task 1: H05 -> H08, 5 vehicles
    - Task 2: H03 -> H01, 4 vehicles
    - Task 3: H05 -> H01, 2 vehicles
    """
    distances = {
        ("H05", "H08"): 1,
        ("H03", "H01"): 1,
        ("H05", "H01"): 2,
        ("H03", "H08"): 3,
    }
    cfg = AllocationConfig(
        safety_stock=3,
        parking_buffer=3,
        min_dispatch_battery=30.0,
        max_tasks_per_hub=5,
        max_vehicles_per_task=10,
        closeness_matrix=distances,
    )

    h01_v = [_make_vehicle(f"V01_{i}") for i in range(44)]
    h05_v = [_make_vehicle(f"V05_{i}") for i in range(26)]
    h08_v = [_make_vehicle(f"V08_{i}") for i in range(12)]
    h03_v = [_make_vehicle(f"V03_{i}") for i in range(27)]

    hubs = [
        HubStateView(
            "H01", free_spaces=20, vehicles=h01_v, demand=HubDemandInfo(expected_pickups=47)
        ),
        HubStateView(
            "H05", free_spaces=20, vehicles=h05_v, demand=HubDemandInfo(expected_pickups=8)
        ),
        HubStateView(
            "H08", free_spaces=11, vehicles=h08_v, demand=HubDemandInfo(expected_pickups=14)
        ),
        HubStateView(
            "H03", free_spaces=20, vehicles=h03_v, demand=HubDemandInfo(expected_pickups=20)
        ),
    ]

    tasks = plan_redistribution(hubs, active_tasks=[], config=cfg)

    assert len(tasks) == 3

    # Task 1: H05 to H08, 5 vehicles
    assert tasks[0].source_hub_id == "H05"
    assert tasks[0].target_hub_id == "H08"
    assert tasks[0].quantity == 5
    assert len(tasks[0].assigned_vehicles) == 5

    # Task 2: H03 to H01, 4 vehicles
    assert tasks[1].source_hub_id == "H03"
    assert tasks[1].target_hub_id == "H01"
    assert tasks[1].quantity == 4
    assert len(tasks[1].assigned_vehicles) == 4

    # Task 3: H05 to H01, 2 vehicles
    assert tasks[2].source_hub_id == "H05"
    assert tasks[2].target_hub_id == "H01"
    assert tasks[2].quantity == 2
    assert len(tasks[2].assigned_vehicles) == 2


@pytest.mark.tc_m4_002
def test_balanced_network_yields_no_tasks():
    """When demand is covered, no redistribution task is proposed."""
    hubs = [
        HubStateView("H01", free_spaces=10, vehicles=[_make_vehicle(f"V1_{i}") for i in range(10)]),
        HubStateView("H02", free_spaces=10, vehicles=[_make_vehicle(f"V2_{i}") for i in range(10)]),
    ]
    tasks = plan_redistribution(hubs, active_tasks=[])
    assert tasks == []


@pytest.mark.tc_m4_003
def test_source_never_drops_below_safety_stock():
    """BR-M4-05: Source hub must retain safety stock S available vehicles."""
    cfg = AllocationConfig(safety_stock=5)
    # H01 has 6 available, demand 0 -> surplus is 6 - 5 = 1
    # H02 has 0 available, demand 5 -> need is 5 + 5 = 10
    h1 = HubStateView("H01", free_spaces=10, vehicles=[_make_vehicle(f"V1_{i}") for i in range(6)])
    h2 = HubStateView("H02", free_spaces=10, vehicles=[], demand=HubDemandInfo(expected_pickups=5))

    tasks = plan_redistribution([h1, h2], active_tasks=[], config=cfg)
    assert len(tasks) == 1
    assert tasks[0].quantity == 1  # only 1 can be dispatched without violating S=5


@pytest.mark.tc_m4_004
def test_destination_parking_buffer_respected():
    """BR-M4-04: Destination free spaces after dispatch cannot drop below buffer B."""
    cfg = AllocationConfig(safety_stock=0, parking_buffer=3)
    # H02 has only 4 free parking spaces. With buffer 3, it can at most receive 4 - 3 = 1 vehicle.
    h1 = HubStateView("H01", free_spaces=10, vehicles=[_make_vehicle(f"V1_{i}") for i in range(10)])
    h2 = HubStateView("H02", free_spaces=4, vehicles=[], demand=HubDemandInfo(expected_pickups=5))

    tasks = plan_redistribution([h1, h2], active_tasks=[], config=cfg)
    assert len(tasks) == 1
    assert tasks[0].quantity == 1


@pytest.mark.tc_m4_005
def test_low_battery_vehicles_excluded():
    """BR-M4-03: Vehicles with battery below min_dispatch_battery are not dispatched."""
    cfg = AllocationConfig(safety_stock=0, min_dispatch_battery=40.0)
    # V_low has 25% battery; V_high has 85%
    h1 = HubStateView(
        "H01",
        free_spaces=10,
        vehicles=[
            _make_vehicle("V_LOW", battery=25.0),
            _make_vehicle("V_HIGH", battery=85.0),
        ],
    )
    h2 = HubStateView("H02", free_spaces=10, vehicles=[], demand=HubDemandInfo(expected_pickups=2))

    tasks = plan_redistribution([h1, h2], active_tasks=[], config=cfg)
    assert len(tasks) == 1
    assert tasks[0].quantity == 1
    assert tasks[0].assigned_vehicles == ["V_HIGH"]


@pytest.mark.tc_m4_006
def test_plan_is_deterministic():
    """NFR-13: Pure planning function produces identical output on repeated runs."""
    h1 = HubStateView("H01", free_spaces=10, vehicles=[_make_vehicle(f"V1_{i}") for i in range(8)])
    h2 = HubStateView("H02", free_spaces=10, vehicles=[], demand=HubDemandInfo(expected_pickups=4))

    plan1 = plan_redistribution([h1, h2], active_tasks=[])
    plan2 = plan_redistribution([h1, h2], active_tasks=[])

    assert [(t.task_id, t.quantity, t.assigned_vehicles) for t in plan1] == [
        (t.task_id, t.quantity, t.assigned_vehicles) for t in plan2
    ]


def _hub(
    hub_id: str, capacity: int, free: int, vehicles: int, *, accepts: bool = True
) -> HubStateView:
    return HubStateView(
        hub_id=hub_id,
        free_spaces=free,
        vehicles=[_make_vehicle(f"{hub_id}_V{i:02d}") for i in range(vehicles)],
        capacity=capacity,
        accepts_vehicles=accepts,
    )


@pytest.mark.tc_m4_035
def test_a_near_full_hub_is_relieved_when_no_hub_is_short():
    """TC-M4-035 · DT · Verifies: FR-10.2, FR-10.3, FR-10.7, BR-M4-04, BR-M4-05, BR-M5-01.

    Expected: no Hub is short, so the deficit step plans nothing. H01 holds 19 of 20 spaces
    (95 %, at or above 90 %): one relief task moves 5 vehicles to H02, bringing H01 to
    parking_buffer spaces below the threshold, with priority 2 and a reason. At 85 % nothing
    is planned.
    """
    cfg = AllocationConfig(safety_stock=3, parking_buffer=3, max_vehicles_per_task=10)
    hubs = [_hub("H01", 20, 1, 15), _hub("H02", 20, 15, 5)]

    tasks = plan_redistribution(hubs, [], cfg, "relief", near_capacity_pct=90.0)

    assert [(t.source_hub_id, t.target_hub_id, t.quantity, t.priority) for t in tasks] == [
        ("H01", "H02", 5, 2)
    ]
    assert tasks[0].reason.startswith("Relieve parking at H01: 1 free of 20")
    assert len(set(tasks[0].assigned_vehicles)) == 5

    calm = [_hub("H01", 20, 3, 15), _hub("H02", 20, 15, 5)]  # 17 of 20 = 85 %
    assert plan_redistribution(calm, [], cfg, "calm", near_capacity_pct=90.0) == []


@pytest.mark.tc_m4_036
def test_a_full_hub_sends_vehicles_but_never_receives_them():
    """TC-M4-036 · DT · Verifies: FR-10.2, FR-10.7, BR-M4-04, BR-M1-02.

    Expected: H01 is full (CRITICAL, accepts no vehicle) and sends vehicles; H03 is also full
    and short of vehicles, yet no task targets it; every destination keeps its buffer and
    stays below the threshold.
    """
    cfg = AllocationConfig(safety_stock=3, parking_buffer=3, max_vehicles_per_task=10)
    hubs = [
        _hub("H01", 20, 0, 20, accepts=False),
        _hub("H02", 20, 18, 1),
        _hub("H03", 10, 0, 0, accepts=False),
        _hub("H04", 30, 25, 5),
    ]

    tasks = plan_redistribution(hubs, [], cfg, "full", near_capacity_pct=90.0)

    assert tasks and all(t.target_hub_id not in ("H01", "H03") for t in tasks)
    assert any(t.source_hub_id == "H01" for t in tasks)
    received = {"H02": 0, "H04": 0}
    for t in tasks:
        received[t.target_hub_id] += t.quantity
    for hub in hubs[1::2]:
        free_after = hub.free_spaces - received[hub.hub_id]
        assert free_after >= cfg.parking_buffer
        assert hub.capacity - free_after < hub.capacity * 0.9
