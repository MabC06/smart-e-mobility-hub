"""Redistribution Planning Engine (FR-10.1 - FR-10.3, BR-M4-03 - BR-M4-06, UC-M4-01).

Implements Algorithm A (Greedy matching with threshold rules) designed in
docs/design/architecture/allocation-algorithm-design.md §4.

The planner is a pure function:
    plan_redistribution(hub_snapshots, demand, active_tasks, config) -> list[DispatchTask]
It produces deterministic outputs without reading external clocks (NFR-13, D-003).
"""

from dataclasses import dataclass

from core.domain.enums import Ownership, VehicleState, VehicleType

from .config import AllocationConfig, default_config
from .models import DispatchTask, DispatchTaskStatus


@dataclass(frozen=True, slots=True)
class HubVehicleInfo:
    """Summary of a vehicle located at a hub for planning evaluation."""

    vehicle_id: str
    vehicle_type: VehicleType
    battery_level: float
    state: VehicleState
    ownership: Ownership
    is_reserved_soon: bool = False


@dataclass(frozen=True, slots=True)
class HubDemandInfo:
    """Forecasted pickups and returns for a hub over the horizon."""

    expected_pickups: int = 0
    expected_returns: int = 0


@dataclass(frozen=True, slots=True)
class HubStateView:
    """State view of one hub used by the planner."""

    hub_id: str
    free_spaces: int
    vehicles: list[HubVehicleInfo]
    demand: HubDemandInfo = HubDemandInfo()


def plan_redistribution(
    hubs: list[HubStateView],
    active_tasks: list[DispatchTask],
    config: AllocationConfig | None = None,
    slot_id: str = "slot1",
) -> list[DispatchTask]:
    """Execute Algorithm A to propose vehicle redistribution tasks.

    Follows steps 1-5 in docs/design/architecture/allocation-algorithm-design.md §4.2:
    1. Compute need, surplus and urgency per hub and vehicle type.
    2. Sort destinations by urgency descending, then hub_id.
    3. Greedily match with closest surplus sources.
    4. Propose Recommended DispatchTask instances with deterministic keys.
    """
    cfg = config or default_config()

    # Track already busy vehicles in non-terminal active tasks
    busy_vehicles: set[str] = set()
    hub_active_task_count: dict[str, int] = {}

    for t in active_tasks:
        if not t.is_terminal():
            busy_vehicles.update(t.assigned_vehicles)
            hub_active_task_count[t.source_hub_id] = (
                hub_active_task_count.get(t.source_hub_id, 0) + 1
            )
            hub_active_task_count[t.target_hub_id] = (
                hub_active_task_count.get(t.target_hub_id, 0) + 1
            )

    proposed_tasks: list[DispatchTask] = []
    task_counter = 1

    # Plan for each fleet vehicle type independently (as designed in §4.2)
    vehicle_types = [VehicleType.E_BIKE, VehicleType.E_SCOOTER, VehicleType.E_MOTORCYCLE]

    # Track dynamic hub state across passes
    current_free_spaces: dict[str, int] = {h.hub_id: h.free_spaces for h in hubs}
    current_assigned_vehicles: set[str] = set(busy_vehicles)

    for v_type in vehicle_types:
        # Step 4.1: Compute quantities per Hub
        need: dict[str, int] = {}
        surplus: dict[str, int] = {}
        urgency: dict[str, float] = {}
        available_vehicles_by_hub: dict[str, list[HubVehicleInfo]] = {}

        for h in hubs:
            # A(h): rentable vehicles matching type with sufficient battery
            eligible_v = [
                v
                for v in h.vehicles
                if v.vehicle_type == v_type
                and v.ownership == Ownership.FLEET
                and v.state == VehicleState.AVAILABLE
                and v.battery_level >= cfg.min_dispatch_battery
                and not v.is_reserved_soon
                and v.vehicle_id not in current_assigned_vehicles
            ]
            available_vehicles_by_hub[h.hub_id] = sorted(
                eligible_v, key=lambda v: (-v.battery_level, v.vehicle_id)
            )

            a_count = len(eligible_v)
            f_out = h.demand.expected_pickups
            f_in = h.demand.expected_returns
            p_free = current_free_spaces[h.hub_id]

            # Need formula: need(h) = max(0, F_out(h) + S - A_eff(h))
            h_need = max(0, f_out + cfg.safety_stock - a_count)
            need[h.hub_id] = h_need

            # Surplus formulas
            surplus_v = max(0, a_count - f_out - cfg.safety_stock)
            pressure = max(0, f_in + cfg.parking_buffer - p_free)
            h_surplus = min(a_count, max(surplus_v, pressure))
            surplus[h.hub_id] = h_surplus

            # Urgency formula
            denom = f_out + cfg.safety_stock
            urgency[h.hub_id] = (h_need / denom) if denom > 0 else 0.0

        # Step 4.2.3: Sort destinations by urgency (descending), then hub_id
        deficit_hubs = [hid for hid, n in need.items() if n > 0]
        deficit_hubs.sort(key=lambda hid: (-urgency[hid], hid))

        # Step 4.2.4: Greedily match with sources
        for dest_id in deficit_hubs:
            while need[dest_id] > 0:
                # Find eligible surplus sources for dest_id
                candidate_sources = [
                    hid
                    for hid, s in surplus.items()
                    if hid != dest_id
                    and s > 0
                    and hub_active_task_count.get(hid, 0) < cfg.max_tasks_per_hub
                ]

                if not candidate_sources:
                    break

                if hub_active_task_count.get(dest_id, 0) >= cfg.max_tasks_per_hub:
                    break

                # Sort sources: closest first; ties: larger surplus, then hub_id
                candidate_sources.sort(
                    key=lambda hid: (
                        cfg.get_closeness(hid, dest_id),
                        -surplus[hid],
                        hid,
                    )
                )
                source_id = candidate_sources[0]

                # Destination parking capacity check (BR-M4-04): P_free(d) - B
                avail_parking_for_dispatch = current_free_spaces[dest_id] - cfg.parking_buffer
                if avail_parking_for_dispatch <= 0:
                    # Destination cannot accept any more vehicles without violating parking buffer
                    break

                # Quantity: q = min(need(d), surplus(s), P_free(d) - B, max_per_task)
                q = min(
                    need[dest_id],
                    surplus[source_id],
                    avail_parking_for_dispatch,
                    cfg.max_vehicles_per_task,
                )

                if q <= 0:
                    surplus[source_id] = 0
                    continue

                # Select q vehicles with highest battery at source
                source_vehicles = available_vehicles_by_hub[source_id]
                chosen_v = source_vehicles[:q]
                if not chosen_v:
                    surplus[source_id] = 0
                    continue

                actual_q = len(chosen_v)
                v_ids = [v.vehicle_id for v in chosen_v]
                for vid in v_ids:
                    current_assigned_vehicles.add(vid)
                available_vehicles_by_hub[source_id] = source_vehicles[actual_q:]

                # Create task proposal
                task_id = f"TASK-{slot_id}-{task_counter:03d}"
                task_counter += 1
                dist = cfg.get_closeness(source_id, dest_id)
                reason = (
                    f"Deficit at {dest_id} (need {need[dest_id]}, urgency {urgency[dest_id]:.2f}) "
                    f"served by surplus at {source_id} (dist {dist})"
                )

                task = DispatchTask(
                    task_id=task_id,
                    source_hub_id=source_id,
                    target_hub_id=dest_id,
                    vehicle_type=v_type,
                    quantity=actual_q,
                    vehicle_ids=",".join(v_ids),
                    status=DispatchTaskStatus.RECOMMENDED,
                    priority=1,
                    reason=reason,
                )
                proposed_tasks.append(task)

                # Update states
                need[dest_id] -= actual_q
                surplus[source_id] -= actual_q
                current_free_spaces[dest_id] -= actual_q
                current_free_spaces[source_id] += actual_q
                hub_active_task_count[source_id] = hub_active_task_count.get(source_id, 0) + 1
                hub_active_task_count[dest_id] = hub_active_task_count.get(dest_id, 0) + 1

    # Return sorted by priority, then task_id (Step 4.2.5)
    proposed_tasks.sort(key=lambda t: (t.priority, t.task_id))
    return proposed_tasks
