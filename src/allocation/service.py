"""Allocation and Vehicle Dispatching Service (FR-10, FR-11.M4, D-016, D-017, D-018).

Coordinates redistribution planning, operator approval, task execution (pickup/return),
cancellation and claim management through Core's unit of work.
"""

from datetime import timedelta

from core.actor import Actor
from core.domain.entities import ResourceClaim
from core.domain.enums import (
    ClaimStatus,
    HolderKind,
    HubStatus,
    ResourceType,
    SpaceStatus,
    VehicleEvent,
    VehicleState,
)
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.providers import ProviderPort
from core.result import Err, Ok, Result
from core.services.transition_ctx import TransitionCtx
from core.views import VehicleFilter

from .config import AllocationConfig, default_config
from .models import DispatchTask, DispatchTaskStatus
from .planner import HubDemandInfo, HubStateView, HubVehicleInfo, plan_redistribution


class AllocationService:
    """Service handling allocation operations for operators and external modules."""

    def __init__(self, core: CoreFacade, config: AllocationConfig | None = None) -> None:
        self._core = core
        self._config = config or default_config()

    def get_config(self) -> AllocationConfig:
        return self._config

    def set_config(self, config: AllocationConfig) -> None:
        self._config = config

    def plan(self, actor: Actor, slot_id: str = "slot1") -> Result[list[DispatchTask]]:
        """Generate redistribution plan based on snapshots and forecasted demand (UC-M4-01)."""
        hub_views: list[HubStateView] = []
        hubs = self._core.queries.list_hubs()

        # Identify vehicles with active claims within horizon (BR-M4-03)
        active_claims = self._core.query_entities(
            ResourceClaim,
            lambda c: c.resource_type == ResourceType.VEHICLE and c.status == ClaimStatus.ACTIVE,
        )
        reserved_vids = {
            c.resource_id
            for c in active_claims
            if c.holder_kind in (HolderKind.RESERVATION, HolderKind.DISPATCH_TASK)
        }

        for h in hubs:
            if h.status in {HubStatus.MAINTENANCE, HubStatus.CRITICAL}:
                continue

            spaces = self._core.queries.list_spaces(h.hub_id)
            free_spaces = sum(1 for s in spaces if s.status == SpaceStatus.AVAILABLE)

            vehicles = self._core.queries.find_vehicles(VehicleFilter(hub_id=h.hub_id))
            v_infos = [
                HubVehicleInfo(
                    vehicle_id=v.vehicle_id,
                    vehicle_type=v.vehicle_type,
                    battery_level=v.battery_pct,
                    state=v.state,
                    ownership=v.ownership,
                    is_reserved_soon=(v.vehicle_id in reserved_vids),
                )
                for v in vehicles
            ]

            # Fetch demand via provider ports if available (D-020)
            pickups = 0
            returns = 0
            if self._core.providers.is_registered(ProviderPort.RESERVATION_DEMAND):
                horizon = self._config.horizon_minutes
                demand_res = self._core.providers.call(
                    ProviderPort.RESERVATION_DEMAND,
                    lambda p, target_hid=h.hub_id, hor=horizon: getattr(
                        p, "upcoming_bookings", lambda *_: Ok([])
                    )(target_hid, hor),
                )
                if isinstance(demand_res, Ok) and isinstance(demand_res.value, list):
                    pickups = len(demand_res.value)

                returns_res = self._core.providers.call(
                    ProviderPort.RESERVATION_DEMAND,
                    lambda p, target_hid=h.hub_id, hor=horizon: getattr(
                        p, "upcoming_returns", lambda *_: Ok([])
                    )(target_hid, hor),
                )
                if isinstance(returns_res, Ok) and isinstance(returns_res.value, list):
                    returns = len(returns_res.value)

            hub_views.append(
                HubStateView(
                    hub_id=h.hub_id,
                    free_spaces=free_spaces,
                    vehicles=v_infos,
                    demand=HubDemandInfo(expected_pickups=pickups, expected_returns=returns),
                )
            )

        active_tasks = self._core.query_entities(DispatchTask, lambda t: not t.is_terminal())
        proposed = plan_redistribution(hub_views, active_tasks, self._config, slot_id)

        # Store recommended tasks in core's transactional repository
        with self._core.unit_of_work() as uow:
            # Supersede stale recommended tasks from prior plans (FR-10.7)
            proposed_ids = {t.task_id for t in proposed}
            old_recommended = self._core.query_entities(
                DispatchTask,
                lambda t: (
                    t.status == DispatchTaskStatus.RECOMMENDED and t.task_id not in proposed_ids
                ),
            )
            for old_t in old_recommended:
                cur_ver = old_t.version
                old_t.version += 1
                old_t.status = DispatchTaskStatus.CANCELLED
                old_t.reason = f"Superseded by plan {slot_id}"
                uow.repository.update(old_t, expected_version=cur_ver)

            for task in proposed:
                existing = self._core.get_entity(DispatchTask, task.task_id)
                if existing is None:
                    uow.repository.add(task)
                else:
                    cur_ver = existing.version
                    task.version = cur_ver + 1
                    uow.repository.update(task, expected_version=cur_ver)
            commit_res = uow.commit()
            if isinstance(commit_res, Err):
                return commit_res

        return Ok(proposed)

    def approve_task(
        self,
        task_id: str,
        actor: Actor,
        adjusted_quantity: int | None = None,
    ) -> Result[DispatchTask]:
        """Approve a task, placing claims atomically (UC-M4-02, BR-M4-02 - BR-M4-06, BR-M1-01)."""
        task = self._core.get_entity(DispatchTask, task_id)
        if task is None:
            return Err(ErrorCode.NOT_FOUND, f"task {task_id} not found")
        if task.status != DispatchTaskStatus.RECOMMENDED:
            return Err(
                ErrorCode.INVALID_TRANSITION, f"task {task_id} is in status {task.status.value}"
            )

        v_ids = task.assigned_vehicles
        if adjusted_quantity is not None and 0 < adjusted_quantity < len(v_ids):
            v_ids = v_ids[:adjusted_quantity]

        if not v_ids:
            return Err(ErrorCode.INVALID_INPUT, "no vehicles selected for approval")

        # Verify destination has free space for parking buffer (BR-M4-04)
        dest_spaces = self._core.queries.list_spaces(task.target_hub_id)
        free_dest_spaces = [s for s in dest_spaces if s.status == SpaceStatus.AVAILABLE]
        if len(free_dest_spaces) - len(v_ids) < self._config.parking_buffer:
            # Mark task failed due to parking buffer breach
            with self._core.unit_of_work() as uow:
                cur_ver = task.version
                task.version += 1
                task.status = DispatchTaskStatus.FAILED
                task.reason = (
                    f"Destination {task.target_hub_id} violates parking buffer "
                    f"({len(free_dest_spaces)} free)"
                )
                uow.repository.update(task, expected_version=cur_ver)
                uow.commit()
            return Err(ErrorCode.HUB_FULL, task.reason)

        # Verify vehicles are available and meet minimum battery threshold (BR-M4-03)
        for vid in v_ids:
            v_check = self._core.queries.get_vehicle(vid)
            if isinstance(v_check, Err):
                return v_check
            if v_check.value.state != VehicleState.AVAILABLE:
                return Err(
                    ErrorCode.RESOURCE_UNAVAILABLE,
                    f"Vehicle {vid} is not available (state: {v_check.value.state.value})",
                )
            if v_check.value.battery_pct < self._config.min_dispatch_battery:
                return Err(
                    ErrorCode.BATTERY_TOO_LOW,
                    f"Vehicle {vid} battery ({v_check.value.battery_pct}%) "
                    f"below minimum {self._config.min_dispatch_battery}%",
                )

        now = self._core._clock.now()
        hold_until = now + timedelta(minutes=self._config.task_timeout_minutes)

        with self._core.unit_of_work() as uow:
            # Place claims on vehicles
            for vid in v_ids:
                claim_res = uow.commands.place_claim(
                    ResourceType.VEHICLE,
                    vid,
                    HolderKind.DISPATCH_TASK,
                    task.task_id,
                    now,
                    hold_until,
                    actor,
                )
                if isinstance(claim_res, Err):
                    # Claim conflict: rollback claims placed so far, then record task failure
                    uow.rollback()
                    with self._core.unit_of_work() as fail_uow:
                        t = fail_uow.repository.get(DispatchTask, task.task_id)
                        if t:
                            cur_ver = t.version
                            t.version += 1
                            t.status = DispatchTaskStatus.FAILED
                            t.reason = f"Vehicle {vid} claim conflict: {claim_res.message}"
                            fail_uow.repository.update(t, expected_version=cur_ver)
                            fail_uow.commit()
                    return claim_res

            # Place claims on destination spaces
            for i, _vid in enumerate(v_ids):
                target_space = free_dest_spaces[i]
                space_claim_res = uow.commands.place_claim(
                    ResourceType.SPACE,
                    target_space.parking_space_id,
                    HolderKind.DISPATCH_TASK,
                    task.task_id,
                    now,
                    hold_until,
                    actor,
                )
                if isinstance(space_claim_res, Err):
                    # Space claim conflict: rollback all claims placed, then record task failure
                    uow.rollback()
                    with self._core.unit_of_work() as fail_uow:
                        t = fail_uow.repository.get(DispatchTask, task.task_id)
                        if t:
                            cur_ver = t.version
                            t.version += 1
                            t.status = DispatchTaskStatus.FAILED
                            t.reason = (
                                f"Space {target_space.parking_space_id} claim conflict: "
                                f"{space_claim_res.message}"
                            )
                            fail_uow.repository.update(t, expected_version=cur_ver)
                            fail_uow.commit()
                    return space_claim_res

            # Update task
            cur_ver = task.version
            task.version += 1
            task.status = DispatchTaskStatus.APPROVED
            task.quantity = len(v_ids)
            task.vehicle_ids = ",".join(v_ids)
            uow.repository.update(task, expected_version=cur_ver)

            commit_res = uow.commit()
            if isinstance(commit_res, Err):
                return commit_res

        return Ok(task)

    def carry_out_pickup(self, task_id: str, actor: Actor) -> Result[DispatchTask]:
        """Confirm pick-up of vehicles at source hub, transitioning to IN_PROGRESS (UC-M4-03)."""
        task = self._core.get_entity(DispatchTask, task_id)
        if task is None:
            return Err(ErrorCode.NOT_FOUND, f"task {task_id} not found")
        if task.status != DispatchTaskStatus.APPROVED:
            return Err(
                ErrorCode.INVALID_TRANSITION, f"task {task_id} is in status {task.status.value}"
            )

        v_ids = task.assigned_vehicles
        # Find active claims for vehicles
        claims = self._core.query_entities(
            ResourceClaim,
            lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
        )
        vehicle_claims = {
            c.resource_id: c.claim_id
            for c in claims
            if c.resource_type == ResourceType.VEHICLE and c.status == ClaimStatus.ACTIVE
        }

        with self._core.unit_of_work() as uow:
            for vid in v_ids:
                veh = self._core.queries.get_vehicle(vid)
                if isinstance(veh, Err):
                    return veh
                claim_id = vehicle_claims.get(vid)
                if not claim_id:
                    return Err(
                        ErrorCode.INVALID_TRANSITION, f"missing active claim for vehicle {vid}"
                    )

                if veh.value.hub_id != task.source_hub_id:
                    return Err(
                        ErrorCode.INVALID_TRANSITION,
                        f"vehicle {vid} not at source hub "
                        f"(current: {veh.value.hub_id}, expected: {task.source_hub_id})",
                    )

                # Transition: Available -> Reserved -> InUse
                # Vehicle must be AVAILABLE or already RESERVED for this task's claim
                if veh.value.state not in (VehicleState.AVAILABLE, VehicleState.RESERVED):
                    return Err(
                        ErrorCode.INVALID_TRANSITION,
                        f"vehicle {vid} in invalid state {veh.value.state.value} for pickup",
                    )

                if veh.value.state == VehicleState.AVAILABLE:
                    res_r = uow.commands.transition_vehicle(
                        vid,
                        VehicleEvent.RESERVE,
                        veh.value.version,
                        actor,
                        TransitionCtx(
                            claim_id=claim_id, min_battery=self._config.min_dispatch_battery
                        ),
                    )
                    if isinstance(res_r, Err):
                        return res_r
                    cur_version = res_r.value.version
                else:
                    cur_version = veh.value.version

                pickup_r = uow.commands.transition_vehicle(
                    vid,
                    VehicleEvent.PICKUP,
                    cur_version,
                    actor,
                    TransitionCtx(claim_id=claim_id),
                )
                if isinstance(pickup_r, Err):
                    return pickup_r

            cur_ver = task.version
            task.version += 1
            task.status = DispatchTaskStatus.IN_PROGRESS
            uow.repository.update(task, expected_version=cur_ver)
            commit_res = uow.commit()
            if isinstance(commit_res, Err):
                return commit_res

        return Ok(task)

    def carry_out_return(
        self,
        task_id: str,
        actor: Actor,
        battery_pct: float | None = None,
    ) -> Result[DispatchTask]:
        """Confirm return at destination hub, releasing claims and completing task (UC-M4-03)."""
        task = self._core.get_entity(DispatchTask, task_id)
        if task is None:
            return Err(ErrorCode.NOT_FOUND, f"task {task_id} not found")
        if task.status != DispatchTaskStatus.IN_PROGRESS:
            return Err(
                ErrorCode.INVALID_TRANSITION, f"task {task_id} is in status {task.status.value}"
            )

        v_ids = task.assigned_vehicles
        claims = self._core.query_entities(
            ResourceClaim,
            lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
        )
        active_claims = [c for c in claims if c.status == ClaimStatus.ACTIVE]
        vehicle_claims = {
            c.resource_id: c for c in active_claims if c.resource_type == ResourceType.VEHICLE
        }

        with self._core.unit_of_work() as uow:
            for vid in v_ids:
                if vid not in vehicle_claims:
                    return Err(
                        ErrorCode.INVALID_TRANSITION,
                        f"vehicle {vid} has no active claim for task {task_id}",
                    )
                veh = self._core.queries.get_vehicle(vid)
                if isinstance(veh, Err):
                    return veh
                if veh.value.state != VehicleState.IN_USE:
                    return Err(
                        ErrorCode.INVALID_TRANSITION,
                        f"vehicle {vid} is not in IN_USE state (current: {veh.value.state.value})",
                    )
                if veh.value.hub_id is not None:
                    return Err(
                        ErrorCode.INVALID_TRANSITION,
                        f"vehicle {vid} not in transit (hub_id={veh.value.hub_id})",
                    )

                # T4: InUse -> return -> Returned
                ret_r = uow.commands.transition_vehicle(
                    vid,
                    VehicleEvent.RETURN,
                    veh.value.version,
                    actor,
                    TransitionCtx(hub_id=task.target_hub_id, battery_pct=battery_pct),
                )
                if isinstance(ret_r, Err):
                    return ret_r

                # T6: Returned -> mark_ready -> Available
                ready_r = uow.commands.transition_vehicle(
                    vid,
                    VehicleEvent.MARK_READY,
                    ret_r.value.version,
                    actor,
                    TransitionCtx(),
                )
                if isinstance(ready_r, Err):
                    return ready_r

            # Release all claims
            for claim in active_claims:
                rel_r = uow.commands.release_claim(claim.claim_id, actor)
                if isinstance(rel_r, Err):
                    return rel_r

            cur_ver = task.version
            task.version += 1
            task.status = DispatchTaskStatus.COMPLETED
            uow.repository.update(task, expected_version=cur_ver)
            commit_res = uow.commit()
            if isinstance(commit_res, Err):
                return commit_res

        return Ok(task)

    def cancel_task(self, task_id: str, actor: Actor, reason: str = "") -> Result[DispatchTask]:
        """Cancel a dispatch task and release any held claims (UC-M4-04)."""
        task = self._core.get_entity(DispatchTask, task_id)
        if task is None:
            return Err(ErrorCode.NOT_FOUND, f"task {task_id} not found")
        if task.is_terminal():
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"task {task_id} is already in terminal state {task.status.value}",
            )

        claims = self._core.query_entities(
            ResourceClaim,
            lambda c: c.holder_kind is HolderKind.DISPATCH_TASK and c.holder_ref == task.task_id,
        )
        active_claims = [c for c in claims if c.status == ClaimStatus.ACTIVE]

        with self._core.unit_of_work() as uow:
            for c in active_claims:
                uow.commands.release_claim(c.claim_id, actor)

            cur_ver = task.version
            task.version += 1
            task.status = DispatchTaskStatus.CANCELLED
            task.reason = reason or "Cancelled by operator"
            uow.repository.update(task, expected_version=cur_ver)
            commit_res = uow.commit()
            if isinstance(commit_res, Err):
                return commit_res

        return Ok(task)

    def get_task(self, task_id: str) -> Result[DispatchTask]:
        task = self._core.get_entity(DispatchTask, task_id)
        if task is None:
            return Err(ErrorCode.NOT_FOUND, f"task {task_id} not found")
        return Ok(task)

    def list_tasks(self, status: DispatchTaskStatus | None = None) -> list[DispatchTask]:
        if status is None:
            return self._core.query_entities(DispatchTask)
        return self._core.query_entities(DispatchTask, lambda t: t.status == status)
