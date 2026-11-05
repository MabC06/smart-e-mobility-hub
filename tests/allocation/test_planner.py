"""Tests for Redistribution Planning Engine (FR-10.1 - FR-10.3, BR-M4-03 - BR-M4-06, NFR-13)."""

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


def test_balanced_network_yields_no_tasks():
    """When demand is covered, no redistribution task is proposed."""
    hubs = [
        HubStateView("H01", free_spaces=10, vehicles=[_make_vehicle(f"V1_{i}") for i in range(10)]),
        HubStateView("H02", free_spaces=10, vehicles=[_make_vehicle(f"V2_{i}") for i in range(10)]),
    ]
    tasks = plan_redistribution(hubs, active_tasks=[])
    assert tasks == []


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


def test_destination_parking_buffer_respected():
    """BR-M4-04: Destination free spaces after dispatch cannot drop below buffer B."""
    cfg = AllocationConfig(safety_stock=0, parking_buffer=3)
    # H02 has only 4 free parking spaces. With buffer 3, it can at most receive 4 - 3 = 1 vehicle.
    h1 = HubStateView("H01", free_spaces=10, vehicles=[_make_vehicle(f"V1_{i}") for i in range(10)])
    h2 = HubStateView("H02", free_spaces=4, vehicles=[], demand=HubDemandInfo(expected_pickups=5))

    tasks = plan_redistribution([h1, h2], active_tasks=[], config=cfg)
    assert len(tasks) == 1
    assert tasks[0].quantity == 1


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


def test_plan_is_deterministic():
    """NFR-13: Pure planning function produces identical output on repeated runs."""
    h1 = HubStateView("H01", free_spaces=10, vehicles=[_make_vehicle(f"V1_{i}") for i in range(8)])
    h2 = HubStateView("H02", free_spaces=10, vehicles=[], demand=HubDemandInfo(expected_pickups=4))

    plan1 = plan_redistribution([h1, h2], active_tasks=[])
    plan2 = plan_redistribution([h1, h2], active_tasks=[])

    assert [(t.task_id, t.quantity, t.assigned_vehicles) for t in plan1] == [
        (t.task_id, t.quantity, t.assigned_vehicles) for t in plan2
    ]
