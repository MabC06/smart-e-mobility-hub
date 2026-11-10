"""Allocation and Vehicle Dispatching Service (FR-10, FR-11.M4, D-016, D-017, D-018).

Coordinates redistribution planning, operator approval, task execution (pickup/return),
cancellation and claim management through Core's unit of work.
"""

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Protocol, cast

from core.actor import Actor
from core.domain.entities import Entity, ResourceClaim
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
from core.repository.base import Repository
from core.result import Err, Ok, Result
from core.services.transition_ctx import TransitionCtx
from core.views import SpaceView, VehicleFilter

from .config import AllocationConfig, default_config
from .models import DispatchTask, DispatchTaskStatus
from .planner import HubDemandInfo, HubStateView, HubVehicleInfo, plan_redistribution


class _BookingRow(Protocol):
    @property
    def reservation_id(self) -> str: ...
    @property
    def kind(self) -> str: ...
    @property
    def hub_id(self) -> str: ...


class _UpcomingBookingsData(Protocol):
    @property
    def bookings(self) -> Sequence[_BookingRow]: ...


class _OpenTripRow(Protocol):
    @property
    def trip_id(self) -> str: ...
    @property
    def reservation_id(self) -> str: ...
    @property
    def destination_hub_id(self) -> str | None: ...
    @property
    def expected_return_at(self) -> datetime: ...


class _OpenTripsData(Protocol):
    @property
    def as_of(self) -> datetime: ...
    @property
    def trips(self) -> Sequence[_OpenTripRow]: ...


class _ReservationDemandPort(Protocol):
    def upcoming_bookings(
        self, hub_id: str, horizon: timedelta
    ) -> Result[_UpcomingBookingsData]: ...
    def open_trips(self, hub_id: str) -> Result[_OpenTripsData]: ...


def _get_task(core: CoreFacade, task_id: str) -> DispatchTask | None:
    return cast(
        DispatchTask | None,
        core.get_entity(cast(type[Entity], DispatchTask), task_id),
    )


def _query_tasks(
    core: CoreFacade, predicate: Callable[[DispatchTask], bool] | None = None
) -> list[DispatchTask]:
    return cast(
        list[DispatchTask],
        core.query_entities(
            cast(type[Entity], DispatchTask),
            cast(Callable[[Entity], bool] | None, predicate),
        ),
    )


def _repo_get_task(repo: Repository, task_id: str) -> DispatchTask | None:
    return cast(DispatchTask | None, repo.get(cast(type[Entity], DispatchTask), task_id))


def _repo_add_task(repo: Repository, task: DispatchTask) -> None:
    repo.add(cast(Entity, task))


def _repo_update_task(repo: Repository, task: DispatchTask, expected_version: int) -> None:
    repo.update(cast(Entity, task), expected_version=expected_version)


def _call_upcoming_bookings(
    provider: _ReservationDemandPort, hub_id: str, horizon: timedelta
) -> Result[_UpcomingBookingsData]:
    return provider.upcoming_bookings(hub_id, horizon)


def _call_open_trips(provider: _ReservationDemandPort, hub_id: str) -> Result[_OpenTripsData]:
    return provider.open_trips(hub_id)


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
        if not slot_id.strip():
            return Err(ErrorCode.INVALID_INPUT, "slot_id is required")
        if self._config.horizon_minutes <= 0:
            return Err(ErrorCode.INVALID_INPUT, "horizon_minutes must be positive")

        now = self._core.queries.get_config().as_of
        hub_views_res = self._build_hub_views(now)
        if isinstance(hub_views_res, Err):
            return hub_views_res

        active_tasks = _query_tasks(self._core, lambda t: not t.is_terminal())
        proposed = plan_redistribution(hub_views_res.value, active_tasks, self._config, slot_id)
        save_res = self._save_planned_tasks(proposed, slot_id)
        if isinstance(save_res, Err):
            return save_res
        return Ok(proposed)

    def _active_plan_claims(self, now: datetime) -> tuple[set[str], set[str]]:
        horizon_end = now + timedelta(minutes=self._config.horizon_minutes)
        lookahead_end = now + timedelta(minutes=self._config.reservation_lookahead_minutes)
        active_claims = self._core.query_entities(
            ResourceClaim,
            lambda c: c.status == ClaimStatus.ACTIVE and c.end_at > now,
        )
        reserved_vids = {
            c.resource_id
            for c in active_claims
            if c.resource_type == ResourceType.VEHICLE
            and (c.holder_kind is HolderKind.DISPATCH_TASK or c.start_at < lookahead_end)
        }
        claimed_sids = {
            c.resource_id
            for c in active_claims
            if c.resource_type == ResourceType.SPACE and c.start_at < horizon_end
        }
        return reserved_vids, claimed_sids

    def _fetch_hub_demand(
        self, hub_id: str, horizon: timedelta, seen_trip_ids: set[str]
    ) -> Result[HubDemandInfo]:
        bookings_res: Result[_UpcomingBookingsData] = self._core.providers.call(
            ProviderPort.RESERVATION_DEMAND,
            lambda p: _call_upcoming_bookings(p, hub_id, horizon),
        )
        if isinstance(bookings_res, Err):
            return bookings_res

        trips_res: Result[_OpenTripsData] = self._core.providers.call(
            ProviderPort.RESERVATION_DEMAND,
            lambda p: _call_open_trips(p, hub_id),
        )
        if isinstance(trips_res, Err):
            return trips_res

        bookings_data = bookings_res.value
        trips_data = trips_res.value
        pickup_res_ids = {
            b.reservation_id
            for b in bookings_data.bookings
            if b.hub_id == hub_id and b.kind == "RENTAL_PICKUP"
        }
        horizon_end = trips_data.as_of + horizon
        return_res_ids: set[str] = set()
        returns = 0
        for trip in trips_data.trips:
            if (
                trip.destination_hub_id == hub_id
                and trip.expected_return_at <= horizon_end
                and trip.trip_id not in seen_trip_ids
            ):
                seen_trip_ids.add(trip.trip_id)
                return_res_ids.add(trip.reservation_id)
                returns += 1

        extra_return_ids = {
            b.reservation_id
            for b in bookings_data.bookings
            if b.hub_id == hub_id
            and b.kind == "RENTAL_RETURN"
            and b.reservation_id not in return_res_ids
        }
        returns += len(extra_return_ids)
        return Ok(HubDemandInfo(expected_pickups=len(pickup_res_ids), expected_returns=returns))

    def _build_hub_views(self, now: datetime) -> Result[list[HubStateView]]:
        reserved_vids, claimed_sids = self._active_plan_claims(now)
        horizon = timedelta(minutes=self._config.horizon_minutes)
        seen_trip_ids: set[str] = set()
        hub_views: list[HubStateView] = []

        for hub in self._core.queries.list_hubs():
            if hub.status in {HubStatus.MAINTENANCE, HubStatus.CRITICAL}:
                continue
            spaces = self._core.queries.list_spaces(hub.hub_id)
            free_spaces = sum(
                1
                for s in spaces
                if s.status == SpaceStatus.AVAILABLE and s.parking_space_id not in claimed_sids
            )
            vehicles = self._core.queries.find_vehicles(VehicleFilter(hub_id=hub.hub_id))
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
            demand_res = self._fetch_hub_demand(hub.hub_id, horizon, seen_trip_ids)
            if isinstance(demand_res, Err):
                return demand_res

            hub_views.append(
                HubStateView(
                    hub_id=hub.hub_id,
                    free_spaces=free_spaces,
                    vehicles=v_infos,
                    demand=demand_res.value,
                )
            )
        return Ok(hub_views)

    def _save_planned_tasks(self, proposed: list[DispatchTask], slot_id: str) -> Result[None]:
        with self._core.unit_of_work() as uow:
            proposed_ids = {t.task_id for t in proposed}
            old_recommended = _query_tasks(
                self._core,
                lambda t: (
                    t.status == DispatchTaskStatus.RECOMMENDED and t.task_id not in proposed_ids
                ),
            )
            for old_t in old_recommended:
                old_t.status = DispatchTaskStatus.CANCELLED
                old_t.reason = f"Superseded by plan {slot_id}"
                _repo_update_task(uow.repository, old_t, old_t.version)

            for task in proposed:
                existing = _get_task(self._core, task.task_id)
                if existing is None:
                    _repo_add_task(uow.repository, task)
                else:
                    task.version = existing.version
                    _repo_update_task(uow.repository, task, existing.version)
            return uow.commit()

    def _mark_task_failed(self, task_id: str, reason: str) -> None:
        with self._core.unit_of_work() as uow:
            current = _repo_get_task(uow.repository, task_id)
            if current is not None and current.status == DispatchTaskStatus.RECOMMENDED:
                current.status = DispatchTaskStatus.FAILED
                current.reason = reason
                _repo_update_task(uow.repository, current, current.version)
                uow.commit()

    def _select_approval_vehicles(
        self, task: DispatchTask, adjusted_quantity: int | None
    ) -> Result[list[str]]:
        v_ids = task.assigned_vehicles
        if not v_ids:
            return Err(ErrorCode.INVALID_INPUT, "no vehicles selected for approval")
        if adjusted_quantity is not None:
            if adjusted_quantity <= 0 or adjusted_quantity > len(v_ids):
                return Err(
                    ErrorCode.INVALID_INPUT,
                    f"adjusted_quantity must be between 1 and {len(v_ids)}",
                )
            v_ids = v_ids[:adjusted_quantity]
        if len(set(v_ids)) != len(v_ids):
            return Err(ErrorCode.INVALID_INPUT, "duplicate vehicle IDs in dispatch task")
        return Ok(v_ids)

    def _validate_approval_resources(
        self, task: DispatchTask, v_ids: list[str], now: datetime, hold_until: datetime
    ) -> Result[list[SpaceView]]:
        hub_res = self._core.queries.get_hub(task.target_hub_id)
        if isinstance(hub_res, Err):
            return hub_res
        if hub_res.value.status in {HubStatus.MAINTENANCE, HubStatus.CRITICAL}:
            reason = (
                f"Destination {task.target_hub_id} is unavailable ({hub_res.value.status.value})"
            )
            self._mark_task_failed(task.task_id, reason)
            return Err(ErrorCode.RESOURCE_UNAVAILABLE, reason)

        bay_space_ids = {
            cp.parking_space_id
            for cp in self._core.queries.list_charging_points(task.target_hub_id)
        }
        dest_spaces = self._core.queries.list_spaces(task.target_hub_id)
        free_dest_spaces = sorted(
            (
                s
                for s in dest_spaces
                if s.status == SpaceStatus.AVAILABLE
                and not self._core.queries.get_claims(s.parking_space_id, now, hold_until)
            ),
            key=lambda s: (s.parking_space_id in bay_space_ids, s.parking_space_id),
        )
        if len(free_dest_spaces) - len(v_ids) < self._config.parking_buffer:
            reason = (
                f"Destination {task.target_hub_id} violates parking buffer "
                f"({len(free_dest_spaces)} free)"
            )
            self._mark_task_failed(task.task_id, reason)
            return Err(ErrorCode.HUB_FULL, reason)

        for vid in v_ids:
            v_check = self._core.queries.get_vehicle(vid)
            if isinstance(v_check, Err):
                self._mark_task_failed(task.task_id, v_check.message)
                return v_check
            vehicle = v_check.value
            if vehicle.state != VehicleState.AVAILABLE:
                msg = f"Vehicle {vid} is not available (state: {vehicle.state.value})"
                self._mark_task_failed(task.task_id, msg)
                return Err(ErrorCode.RESOURCE_UNAVAILABLE, msg)
            if vehicle.hub_id != task.source_hub_id:
                msg = (
                    f"Vehicle {vid} is not at source hub {task.source_hub_id} "
                    f"(current: {vehicle.hub_id})"
                )
                self._mark_task_failed(task.task_id, msg)
                return Err(ErrorCode.INVALID_TRANSITION, msg)
            if vehicle.battery_pct < self._config.min_dispatch_battery:
                msg = (
                    f"Vehicle {vid} battery ({vehicle.battery_pct}%) "
                    f"below minimum {self._config.min_dispatch_battery}%"
                )
                self._mark_task_failed(task.task_id, msg)
                return Err(ErrorCode.BATTERY_TOO_LOW, msg)

        return Ok(free_dest_spaces[: len(v_ids)])

    def _place_approval_claims(
        self,
        task: DispatchTask,
        v_ids: list[str],
        selected_spaces: list[SpaceView],
        now: datetime,
        hold_until: datetime,
        actor: Actor,
    ) -> Result[DispatchTask]:
        fail_reason: str | None = None
        fail_err: Err | None = None
        with self._core.unit_of_work() as uow:
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
                    uow.rollback()
                    fail_reason = f"Vehicle {vid} claim conflict: {claim_res.message}"
                    fail_err = claim_res
                    break

            if fail_err is None:
                for target_space in selected_spaces:
                    space_res = uow.commands.place_claim(
                        ResourceType.SPACE,
                        target_space.parking_space_id,
                        HolderKind.DISPATCH_TASK,
                        task.task_id,
                        now,
                        hold_until,
                        actor,
                    )
                    if isinstance(space_res, Err):
                        uow.rollback()
                        fail_reason = (
                            f"Space {target_space.parking_space_id} claim conflict: "
                            f"{space_res.message}"
                        )
                        fail_err = space_res
                        break

            if fail_err is None:
                task.status = DispatchTaskStatus.APPROVED
                task.quantity = len(v_ids)
                task.vehicle_ids = ",".join(v_ids)
                _repo_update_task(uow.repository, task, task.version)
                commit_res = uow.commit()
                if isinstance(commit_res, Err):
                    return commit_res
                return Ok(task)

        if fail_reason is not None:
            self._mark_task_failed(task.task_id, fail_reason)
        assert fail_err is not None
        return fail_err

    def approve_task(
        self,
        task_id: str,
        actor: Actor,
        adjusted_quantity: int | None = None,
    ) -> Result[DispatchTask]:
        """Approve a task, placing claims atomically (UC-M4-02, BR-M4-02 - BR-M4-06, BR-M1-01)."""
        task = _get_task(self._core, task_id)
        if task is None:
            return Err(ErrorCode.NOT_FOUND, f"task {task_id} not found")
        if task.status != DispatchTaskStatus.RECOMMENDED:
            return Err(
                ErrorCode.INVALID_TRANSITION, f"task {task_id} is in status {task.status.value}"
            )

        selected_res = self._select_approval_vehicles(task, adjusted_quantity)
        if isinstance(selected_res, Err):
            return selected_res
        v_ids = selected_res.value

        now = self._core.queries.get_config().as_of
        hold_until = now + timedelta(minutes=self._config.task_timeout_minutes)
        spaces_res = self._validate_approval_resources(task, v_ids, now, hold_until)
        if isinstance(spaces_res, Err):
            return spaces_res

        return self._place_approval_claims(task, v_ids, spaces_res.value, now, hold_until, actor)

    def carry_out_pickup(self, task_id: str, actor: Actor) -> Result[DispatchTask]:
        """Confirm pick-up of vehicles at source hub, transitioning to IN_PROGRESS (UC-M4-03)."""
        task = _get_task(self._core, task_id)
        if task is None:
            return Err(ErrorCode.NOT_FOUND, f"task {task_id} not found")
        if task.status != DispatchTaskStatus.APPROVED:
            return Err(
                ErrorCode.INVALID_TRANSITION, f"task {task_id} is in status {task.status.value}"
            )

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
            for vid in task.assigned_vehicles:
                claim_id = vehicle_claims.get(vid)
                if not claim_id:
                    uow.rollback()
                    return Err(
                        ErrorCode.INVALID_TRANSITION, f"missing active claim for vehicle {vid}"
                    )
                err = self._pickup_one_vehicle(vid, claim_id, task, actor)
                if err is not None:
                    uow.rollback()
                    return err

            task.status = DispatchTaskStatus.IN_PROGRESS
            _repo_update_task(uow.repository, task, task.version)
            commit_res = uow.commit()
            if isinstance(commit_res, Err):
                return commit_res

        return Ok(task)

    def _pickup_one_vehicle(
        self, vid: str, claim_id: str, task: DispatchTask, actor: Actor
    ) -> Err | None:
        veh = self._core.queries.get_vehicle(vid)
        if isinstance(veh, Err):
            return veh
        if veh.value.hub_id != task.source_hub_id:
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"vehicle {vid} not at source hub "
                f"(current: {veh.value.hub_id}, expected: {task.source_hub_id})",
            )
        if veh.value.state not in (VehicleState.AVAILABLE, VehicleState.RESERVED):
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"vehicle {vid} in invalid state {veh.value.state.value} for pickup",
            )

        state_cmds = self._core.commands
        if veh.value.state == VehicleState.AVAILABLE:
            res_r = state_cmds.transition_vehicle(
                vid,
                VehicleEvent.RESERVE,
                veh.value.version,
                actor,
                TransitionCtx(claim_id=claim_id, min_battery=self._config.min_dispatch_battery),
            )
            if isinstance(res_r, Err):
                return res_r
            cur_version = res_r.value.version
        else:
            cur_version = veh.value.version

        pickup_r = state_cmds.transition_vehicle(
            vid,
            VehicleEvent.PICKUP,
            cur_version,
            actor,
            TransitionCtx(claim_id=claim_id),
        )
        return pickup_r if isinstance(pickup_r, Err) else None

    def carry_out_return(
        self,
        task_id: str,
        actor: Actor,
        battery_pct: float | None = None,
    ) -> Result[DispatchTask]:
        """Confirm return at destination hub, releasing claims and completing task (UC-M4-03)."""
        task = _get_task(self._core, task_id)
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
        space_claims = sorted(
            (c for c in active_claims if c.resource_type == ResourceType.SPACE),
            key=lambda c: c.resource_id,
        )
        if len(space_claims) < len(v_ids):
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"task {task_id} is missing active destination space claims",
            )

        with self._core.unit_of_work() as uow:
            consumed_claim_ids: set[str] = set()
            for idx, vid in enumerate(v_ids):
                if vid not in vehicle_claims:
                    uow.rollback()
                    return Err(
                        ErrorCode.INVALID_TRANSITION,
                        f"vehicle {vid} has no active claim for task {task_id}",
                    )
                space_claim = space_claims[idx]
                err = self._return_one_vehicle(vid, task, space_claim, battery_pct, actor)
                if err is not None:
                    uow.rollback()
                    return err
                consumed_claim_ids.add(space_claim.claim_id)

            for claim in active_claims:
                if claim.claim_id not in consumed_claim_ids:
                    rel_r = uow.commands.release_claim(claim.claim_id, actor)
                    if isinstance(rel_r, Err):
                        uow.rollback()
                        return rel_r

            task.status = DispatchTaskStatus.COMPLETED
            _repo_update_task(uow.repository, task, task.version)
            commit_res = uow.commit()
            if isinstance(commit_res, Err):
                return commit_res

        return Ok(task)

    def _return_one_vehicle(
        self,
        vid: str,
        task: DispatchTask,
        space_claim: ResourceClaim,
        battery_pct: float | None,
        actor: Actor,
    ) -> Err | None:
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

        ret_r = self._core.commands.transition_vehicle(
            vid,
            VehicleEvent.RETURN,
            veh.value.version,
            actor,
            TransitionCtx(
                hub_id=task.target_hub_id,
                parking_space_id=space_claim.resource_id,
                claim_id=space_claim.claim_id,
                battery_pct=battery_pct,
            ),
        )
        if isinstance(ret_r, Err):
            return ret_r

        ready_r = self._core.commands.transition_vehicle(
            vid,
            VehicleEvent.MARK_READY,
            ret_r.value.version,
            actor,
            TransitionCtx(),
        )
        return ready_r if isinstance(ready_r, Err) else None

    def cancel_task(self, task_id: str, actor: Actor, reason: str = "") -> Result[DispatchTask]:
        """Cancel a dispatch task and release any held claims (UC-M4-04)."""
        task = _get_task(self._core, task_id)
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
                rel_r = uow.commands.release_claim(c.claim_id, actor)
                if isinstance(rel_r, Err):
                    uow.rollback()
                    return rel_r

            task.status = DispatchTaskStatus.CANCELLED
            task.reason = reason or "Cancelled by operator"
            _repo_update_task(uow.repository, task, task.version)
            commit_res = uow.commit()
            if isinstance(commit_res, Err):
                return commit_res

        return Ok(task)

    def get_task(self, task_id: str) -> Result[DispatchTask]:
        task = _get_task(self._core, task_id)
        if task is None:
            return Err(ErrorCode.NOT_FOUND, f"task {task_id} not found")
        return Ok(task)

    def list_tasks(self, status: DispatchTaskStatus | None = None) -> list[DispatchTask]:
        if status is None:
            return _query_tasks(self._core)
        return _query_tasks(self._core, lambda t: t.status == status)
