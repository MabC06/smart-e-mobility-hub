import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from math import ceil, isfinite

from charging import schema
from charging.models import (
    ChargingError,
    ChargingErrorCode,
    ChargingRequest,
    ChargingResult,
    ChargingSessionStatus,
    from_core_error,
)
from core.actor import Actor
from core.domain.entities import UserAccount, Vehicle
from core.domain.enums import (
    ChargingPointStatus,
    HolderKind,
    HubStatus,
    ResourceType,
    Role,
    VehicleEvent,
    VehicleState,
)
from core.errors import ErrorCode
from core.events import EventType
from core.facade import CoreFacade
from core.providers import ProviderPort, ScheduledChargingSessionRow
from core.repository.base import RepositoryError, VersionConflictError
from core.result import Err, Ok, Result
from core.services.transition_ctx import TransitionCtx
from core.views import ChargingPointView

logger = logging.getLogger(__name__)

DEFAULT_SESSION_MINUTES = 60


def _id_valid(value: str) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and len(value) <= 128


def _soc_valid(value: float) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(value)
        and 0.0 <= float(value) <= 100.0
    )


def _err(code: ChargingErrorCode, message: str) -> ChargingError:
    return ChargingError(code, message)


def _check_owner_or_operator(req: ChargingRequest, caller: Actor) -> bool:
    """Allow the session owner or an OPERATOR to act on the session (M3-16)."""
    return caller.role is Role.OPERATOR or req.user_id == caller.user_id


class ChargingQueueService:
    """Phase 2 v2: charging requests, battery-threshold priority queue, and D-020 provider."""

    def __init__(self, core: CoreFacade) -> None:
        self.core = core
        schema.register_tables(core)
        core.events.subscribe(
            EventType.CHARGING_POINT_STATUS_CHANGED,
            self._on_point_status_changed,
        )

    def _run[T](
        self, fn: Callable[..., ChargingResult[T]], actor: Actor | None
    ) -> ChargingResult[T]:
        caller = (
            Actor("SYSTEM_M3", Role.OPERATOR, "charging")
            if actor is None
            else Actor(actor.user_id, actor.role, "charging")
        )
        if not _id_valid(caller.user_id):
            return _err(ChargingErrorCode.FORBIDDEN, "Invalid actor user_id.")
        try:
            with self.core.unit_of_work() as uow:
                return fn(uow, caller)
        except VersionConflictError:
            return _err(ChargingErrorCode.CONFLICT, "Resource version changed; retry.")
        except RepositoryError:
            logger.exception("Charging persistence failed; transaction rolled back")
            return _err(
                ChargingErrorCode.INTERNAL_ERROR,
                "Charging operation could not be saved.",
            )

    def _on_point_status_changed(self, event: object) -> None:
        """React to a charging point failing or becoming free (UC-M3-08, BR-M3-02)."""
        payload = getattr(event, "payload", None) or {}
        point_id = payload.get("charging_point_id")
        new_status = payload.get("new")
        hub_id = payload.get("hub_id")
        if not point_id or not new_status:
            return

        system = Actor("SYSTEM_EVENT", Role.OPERATOR, "charging")
        if new_status in (
            ChargingPointStatus.OUT_OF_SERVICE,
            ChargingPointStatus.MAINTENANCE,
        ):
            now = self.core.queries.get_config().as_of
            hubs: set[str] = set()
            for req in schema.all_requests(self.core):
                if req.charger_id != point_id:
                    continue
                if req.status is ChargingSessionStatus.CHARGING:
                    interrupted = self.interrupt_charging(req.request_id, system)
                    if isinstance(interrupted, Ok):
                        self._resubmit_after_failure(interrupted.value)
                elif req.status is ChargingSessionStatus.SCHEDULED:
                    minutes = (
                        round((req.end_time - req.start_time).total_seconds() / 60)
                        if req.end_time and req.start_time
                        else DEFAULT_SESSION_MINUTES
                    )
                    self.modify_charging_schedule(
                        req.request_id, now + timedelta(minutes=15), minutes, system
                    )
                else:
                    continue
                hubs.add(req.station_id)
            for affected_hub in sorted(hubs):
                self.optimize_queue(affected_hub, system)
        elif new_status == ChargingPointStatus.AVAILABLE and hub_id:
            self.optimize_queue(hub_id, system)

    def _resubmit_after_failure(self, failed: ChargingRequest) -> None:
        """Submit a new request for the same vehicle and owner (UC-M3-08)."""
        n = 1
        while schema.read(self.core, f"{failed.request_id}-R{n}") is not None:
            n += 1
        owner = (
            self.core.get_entity(UserAccount, failed.user_id)
            if failed.user_id is not None
            else None
        )
        actor = (
            Actor(owner.user_id, owner.role, "charging")
            if owner is not None
            else Actor("SYSTEM_EVENT", Role.OPERATOR, "charging")
        )
        self.submit_charging_request(
            f"{failed.request_id}-R{n}",
            failed.vehicle_id,
            failed.station_id,
            actor,
            target_soc=failed.target_soc,
        )

    def _find_free_bay(
        self,
        uow,
        hub_id: str,
        start_at: datetime,
        end_at: datetime,
        required_space_id: str | None = None,
        *,
        immediate: bool = False,
    ) -> ChargingPointView | None:
        candidates = [
            pt
            for pt in uow.queries.list_charging_points(hub_id)
            if pt.status
            not in (ChargingPointStatus.OUT_OF_SERVICE, ChargingPointStatus.MAINTENANCE)
            and (
                not immediate
                or (
                    required_space_id is not None
                    and pt.status is ChargingPointStatus.AVAILABLE
                    and pt.parking_space_id == required_space_id
                )
            )
            and (required_space_id is None or pt.parking_space_id == required_space_id)
            and not uow.queries.get_claims(pt.charging_point_id, start_at, end_at)
        ]
        candidates.sort(key=lambda p: p.charging_point_id)
        return candidates[0] if candidates else None

    def _earliest_slot(
        self, uow, hub_id: str, start_at: datetime, minutes: int
    ) -> tuple[ChargingPointView | None, datetime | None]:
        """Try a free bay every 15 minutes over the next 2 hours (BR-M3-02, step 2)."""
        current_start = start_at
        max_horizon = start_at + timedelta(hours=2)
        while current_start <= max_horizon:
            current_end = current_start + timedelta(minutes=minutes)
            bay = self._find_free_bay(uow, hub_id, current_start, current_end)
            if bay is not None:
                return bay, current_start
            current_start += timedelta(minutes=15)
        return None, None

    def optimize_queue(self, hub_id: str, actor: Actor) -> ChargingResult[list[ChargingRequest]]:
        """Bind QUEUED requests to the earliest free slot by priority (UC-M3-07)."""
        if not _id_valid(hub_id):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid hub_id.")

        def _bind_one(
            request_id: str,
        ) -> Callable[..., ChargingResult[ChargingRequest | None]]:
            def _op(uow, caller: Actor) -> ChargingResult[ChargingRequest | None]:
                req = schema.read(self.core, request_id)
                if req is None or req.status is not ChargingSessionStatus.QUEUED:
                    return Ok(None)
                duration = (
                    round((req.end_time - req.start_time).total_seconds() / 60)
                    if req.end_time and req.start_time
                    else DEFAULT_SESSION_MINUTES
                )
                now = uow.queries.get_config().as_of
                bay, slot_start = self._earliest_slot(uow, hub_id, now, duration)
                if bay is None or slot_start is None:
                    return Ok(None)
                return self._bind_bay(
                    uow,
                    req,
                    bay,
                    slot_start,
                    slot_start + timedelta(minutes=duration),
                    caller,
                    start_now=False,
                    is_new=False,
                )

            return _op

        bound: list[ChargingRequest] = []
        for queued in self.compute_priority_queue(hub_id):
            res = self._run(_bind_one(queued.request_id), actor)
            if isinstance(res, ChargingError):
                if res.code is ChargingErrorCode.FORBIDDEN:
                    return res
                continue
            if res.value is not None:
                bound.append(res.value)
        return Ok(bound)

    def _bind_bay(
        self,
        uow,
        req: ChargingRequest,
        bay: ChargingPointView,
        start_at: datetime,
        end_at: datetime,
        caller: Actor,
        *,
        start_now: bool,
        is_new: bool,
    ) -> ChargingResult[ChargingRequest]:
        pt_claim = uow.commands.place_claim(
            ResourceType.CHARGING_POINT,
            bay.charging_point_id,
            HolderKind.CHARGING_SESSION,
            req.request_id,
            start_at,
            end_at,
            caller,
        )
        if isinstance(pt_claim, Err):
            return from_core_error(pt_claim)
        veh_claim = uow.commands.place_claim(
            ResourceType.VEHICLE,
            req.vehicle_id,
            HolderKind.CHARGING_SESSION,
            req.request_id,
            start_at,
            end_at,
            caller,
        )
        if isinstance(veh_claim, Err):
            return from_core_error(veh_claim)

        if start_now:
            veh = uow.queries.get_vehicle(req.vehicle_id)
            if isinstance(veh, Err):
                return from_core_error(veh)
            trans = uow.commands.transition_vehicle(
                req.vehicle_id,
                VehicleEvent.START_CHARGING,
                veh.value.version,
                caller,
                TransitionCtx(
                    charging_point_id=bay.charging_point_id,
                    claim_id=pt_claim.value.claim_id,
                ),
            )
            if isinstance(trans, Err):
                return from_core_error(trans)
            pt_res = uow.commands.set_charging_point_status(
                bay.charging_point_id, ChargingPointStatus.CHARGING, bay.version, caller
            )
            if isinstance(pt_res, Err):
                return from_core_error(pt_res)

        req.charger_id = bay.charging_point_id
        req.start_time = start_at
        req.end_time = end_at
        req.point_claim_id = pt_claim.value.claim_id
        req.vehicle_claim_id = veh_claim.value.claim_id
        req.status = (
            ChargingSessionStatus.CHARGING if start_now else ChargingSessionStatus.SCHEDULED
        )
        (schema.add if is_new else schema.update)(uow.repository, req)
        committed = uow.commit()
        return from_core_error(committed) if isinstance(committed, Err) else Ok(req)

    def submit_charging_request(
        self,
        request_id: str,
        vehicle_id: str,
        hub_id: str,
        actor: Actor,
        *,
        target_soc: float = 100.0,
        start_at: datetime | None = None,
        duration_minutes: int | None = None,
        queue_if_full: bool = True,
    ) -> ChargingResult[ChargingRequest]:
        """Submit an immediate or scheduled charging request (UC-M3-01, UC-M3-02)."""
        if not all(_id_valid(v) for v in (request_id, vehicle_id, hub_id)):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid IDs for charging request.")
        if not _soc_valid(target_soc) or target_soc <= 0.0:
            return _err(ChargingErrorCode.INVALID_INPUT, "target_soc must be in (0, 100].")

        def _op(uow, caller: Actor) -> ChargingResult[ChargingRequest]:
            if (existing := schema.read(self.core, request_id)) is not None:
                return Ok(existing)

            hub_res = uow.queries.get_hub(hub_id)
            if isinstance(hub_res, Err):
                return from_core_error(hub_res)
            if hub_res.value.status is HubStatus.MAINTENANCE:
                return _err(ChargingErrorCode.INVALID_STATE, "Hub is in maintenance.")

            veh_res = uow.queries.get_vehicle(vehicle_id)
            if isinstance(veh_res, Err):
                return from_core_error(veh_res)
            veh = veh_res.value
            if veh.fault_flag or veh.state is VehicleState.MAINTENANCE:
                return _err(ChargingErrorCode.INVALID_STATE, "Vehicle is unavailable.")
            if target_soc <= veh.battery_pct:
                return _err(
                    ChargingErrorCode.INVALID_INPUT,
                    "target_soc must exceed battery_pct.",
                )

            config = uow.queries.get_config()
            now = config.as_of
            immediate = start_at is None
            session_start = now if immediate else start_at
            if not immediate and session_start < now:
                return _err(ChargingErrorCode.INVALID_INPUT, "start_at cannot be in the past.")

            veh_entity = uow.repository.get(Vehicle, vehicle_id)
            if veh_entity is None:
                return _err(ChargingErrorCode.NOT_FOUND, "Vehicle entity not found.")

            energy_kwh = round(
                veh_entity.battery_capacity_kwh * (target_soc - veh.battery_pct) / 100.0,
                4,
            )
            session_end = session_start + timedelta(
                minutes=duration_minutes or DEFAULT_SESSION_MINUTES
            )
            req = ChargingRequest(
                request_id=request_id,
                vehicle_id=vehicle_id,
                station_id=hub_id,
                current_soc=veh.battery_pct,
                target_soc=target_soc,
                requested_at=now,
                is_emergency=veh.battery_pct <= config.low_battery_threshold,
                energy_kwh=energy_kwh,
                user_id=caller.user_id,
            )

            bay = self._find_free_bay(
                uow,
                hub_id,
                session_start,
                session_end,
                required_space_id=veh.parking_space_id if immediate else None,
                immediate=immediate,
            )
            if bay is None:
                if not queue_if_full:
                    return _err(
                        ChargingErrorCode.CONFLICT,
                        f"No free charging bay at hub {hub_id!r}.",
                    )
                req.status = ChargingSessionStatus.QUEUED
                schema.add(uow.repository, req)
                committed = uow.commit()
                return from_core_error(committed) if isinstance(committed, Err) else Ok(req)

            if duration_minutes is None:
                session_end = session_start + timedelta(
                    minutes=max(1, ceil((energy_kwh / bay.power_rate_kw) * 60.0))
                )
            return self._bind_bay(
                uow,
                req,
                bay,
                session_start,
                session_end,
                caller,
                start_now=immediate,
                is_new=True,
            )

        return self._run(_op, actor)

    def start_scheduled_session(
        self, request_id: str, actor: Actor
    ) -> ChargingResult[ChargingRequest]:
        """Start a SCHEDULED session once its start_time has come (M3-15)."""
        if not _id_valid(request_id):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid request_id.")

        def _op(uow, caller: Actor) -> ChargingResult[ChargingRequest]:
            req = schema.read(self.core, request_id)
            if req is None or not _check_owner_or_operator(req, caller):
                return _err(ChargingErrorCode.NOT_FOUND, "Charging session not found.")
            if req.status is not ChargingSessionStatus.SCHEDULED:
                return _err(ChargingErrorCode.INVALID_STATE, "Session is not SCHEDULED.")
            now = uow.queries.get_config().as_of
            if req.start_time is None or req.start_time > now:
                return _err(
                    ChargingErrorCode.INVALID_STATE,
                    "Scheduled start time has not come yet.",
                )

            veh = uow.queries.get_vehicle(req.vehicle_id)
            if isinstance(veh, Err):
                return from_core_error(veh)
            trans = uow.commands.transition_vehicle(
                req.vehicle_id,
                VehicleEvent.START_CHARGING,
                veh.value.version,
                caller,
                TransitionCtx(
                    charging_point_id=req.charger_id,
                    claim_id=req.point_claim_id,
                ),
            )
            if isinstance(trans, Err):
                return from_core_error(trans)

            bay = next(
                (
                    p
                    for p in uow.queries.list_charging_points(req.station_id)
                    if p.charging_point_id == req.charger_id
                ),
                None,
            )
            if bay is None:
                return _err(ChargingErrorCode.NOT_FOUND, "Assigned charging point not found.")
            pt_res = uow.commands.set_charging_point_status(
                bay.charging_point_id, ChargingPointStatus.CHARGING, bay.version, caller
            )
            if isinstance(pt_res, Err):
                return from_core_error(pt_res)

            req.status = ChargingSessionStatus.CHARGING
            schema.update(uow.repository, req)
            committed = uow.commit()
            return from_core_error(committed) if isinstance(committed, Err) else Ok(req)

        return self._run(_op, actor)

    def finish_charging(
        self, request_id: str, actor: Actor, *, final_soc: float | None = None
    ) -> ChargingResult[ChargingRequest]:
        """Finish a CHARGING session and release the bay and claims (UC-M3-01)."""
        if not _id_valid(request_id):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid request_id.")
        if final_soc is not None and not _soc_valid(final_soc):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid final_soc.")

        def _op(uow, caller: Actor) -> ChargingResult[ChargingRequest]:
            req = schema.read(self.core, request_id)
            if req is None or not _check_owner_or_operator(req, caller):
                return _err(ChargingErrorCode.NOT_FOUND, "Charging session not found.")
            if req.status is not ChargingSessionStatus.CHARGING:
                return _err(ChargingErrorCode.INVALID_STATE, "Session is not CHARGING.")

            veh = uow.queries.get_vehicle(req.vehicle_id)
            if isinstance(veh, Err):
                return from_core_error(veh)
            soc = req.target_soc if final_soc is None else final_soc
            trans = uow.commands.transition_vehicle(
                req.vehicle_id,
                VehicleEvent.FINISH_CHARGING,
                veh.value.version,
                caller,
                TransitionCtx(battery_pct=soc),
            )
            if isinstance(trans, Err):
                return from_core_error(trans)

            bay = next(
                (
                    p
                    for p in uow.queries.list_charging_points(req.station_id)
                    if p.charging_point_id == req.charger_id
                ),
                None,
            )
            if bay is not None and bay.status is ChargingPointStatus.CHARGING:
                pt_res = uow.commands.set_charging_point_status(
                    bay.charging_point_id,
                    ChargingPointStatus.AVAILABLE,
                    bay.version,
                    caller,
                )
                if isinstance(pt_res, Err):
                    return from_core_error(pt_res)

            for cid in (req.point_claim_id, req.vehicle_claim_id):
                if cid is not None and isinstance(
                    (rel := uow.commands.release_claim(cid, caller)), Err
                ):
                    return from_core_error(rel)

            req.current_soc = soc
            req.end_time = uow.queries.get_config().as_of
            req.status = ChargingSessionStatus.COMPLETED
            schema.update(uow.repository, req)
            committed = uow.commit()
            return from_core_error(committed) if isinstance(committed, Err) else Ok(req)

        return self._run(_op, actor)

    def modify_charging_schedule(
        self,
        request_id: str,
        new_start_at: datetime,
        new_duration_minutes: int,
        actor: Actor,
    ) -> ChargingResult[ChargingRequest]:
        """Move a SCHEDULED session to a new time slot (UC-M3-03)."""
        if not _id_valid(request_id):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid request_id.")
        if not isinstance(new_duration_minutes, int) or new_duration_minutes <= 0:
            return _err(
                ChargingErrorCode.INVALID_INPUT,
                "duration_minutes must be a positive integer.",
            )

        def _op(uow, caller: Actor) -> ChargingResult[ChargingRequest]:
            req = schema.read(self.core, request_id)
            if req is None or not _check_owner_or_operator(req, caller):
                return _err(ChargingErrorCode.NOT_FOUND, "Charging session not found.")
            if req.status is not ChargingSessionStatus.SCHEDULED:
                return _err(
                    ChargingErrorCode.INVALID_STATE,
                    "Only SCHEDULED requests can be modified.",
                )

            config = uow.queries.get_config()
            if new_start_at < config.as_of:
                return _err(
                    ChargingErrorCode.INVALID_INPUT,
                    "New start time cannot be in the past.",
                )

            for cid in (req.point_claim_id, req.vehicle_claim_id):
                if cid is not None:
                    rel = uow.commands.release_claim(cid, caller)
                    if isinstance(rel, Err):
                        return from_core_error(rel)

            new_end_at = new_start_at + timedelta(minutes=new_duration_minutes)
            bay = self._find_free_bay(uow, req.station_id, new_start_at, new_end_at)
            if bay is None:
                return _err(
                    ChargingErrorCode.CONFLICT,
                    "No free bay for the new schedule slot.",
                )

            pt_claim = uow.commands.place_claim(
                ResourceType.CHARGING_POINT,
                bay.charging_point_id,
                HolderKind.CHARGING_SESSION,
                req.request_id,
                new_start_at,
                new_end_at,
                caller,
            )
            if isinstance(pt_claim, Err):
                return from_core_error(pt_claim)

            veh_claim = uow.commands.place_claim(
                ResourceType.VEHICLE,
                req.vehicle_id,
                HolderKind.CHARGING_SESSION,
                req.request_id,
                new_start_at,
                new_end_at,
                caller,
            )
            if isinstance(veh_claim, Err):
                return from_core_error(veh_claim)

            req.charger_id = bay.charging_point_id
            req.start_time = new_start_at
            req.end_time = new_end_at
            req.point_claim_id = pt_claim.value.claim_id
            req.vehicle_claim_id = veh_claim.value.claim_id
            schema.update(uow.repository, req)
            committed = uow.commit()
            return from_core_error(committed) if isinstance(committed, Err) else Ok(req)

        return self._run(_op, actor)

    def cancel_charging_schedule(
        self, request_id: str, actor: Actor
    ) -> ChargingResult[ChargingRequest]:
        """Cancel a QUEUED or SCHEDULED request and free its claims (UC-M3-03)."""
        if not _id_valid(request_id):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid request_id.")

        def _op(uow, caller: Actor) -> ChargingResult[ChargingRequest]:
            req = schema.read(self.core, request_id)
            if req is None or not _check_owner_or_operator(req, caller):
                return _err(ChargingErrorCode.NOT_FOUND, "Charging session not found.")
            if req.status not in (
                ChargingSessionStatus.QUEUED,
                ChargingSessionStatus.SCHEDULED,
            ):
                return _err(
                    ChargingErrorCode.INVALID_STATE,
                    "Only QUEUED or SCHEDULED requests can be cancelled.",
                )

            for cid in (req.point_claim_id, req.vehicle_claim_id):
                if cid is not None:
                    rel = uow.commands.release_claim(cid, caller)
                    if isinstance(rel, Err):
                        return from_core_error(rel)

            if req.charger_id is not None:
                bay = next(
                    (
                        p
                        for p in uow.queries.list_charging_points(req.station_id)
                        if p.charging_point_id == req.charger_id
                    ),
                    None,
                )
                if bay is not None and bay.status is ChargingPointStatus.CHARGING:
                    uow.commands.set_charging_point_status(
                        bay.charging_point_id,
                        ChargingPointStatus.AVAILABLE,
                        bay.version,
                        caller,
                    )

            req.status = ChargingSessionStatus.CANCELLED
            schema.update(uow.repository, req)
            committed = uow.commit()
            return from_core_error(committed) if isinstance(committed, Err) else Ok(req)

        return self._run(_op, actor)

    def interrupt_charging(
        self, request_id: str, actor: Actor, *, current_soc: float | None = None
    ) -> ChargingResult[ChargingRequest]:
        """Interrupt a CHARGING session and release the bay and claims (UC-M3-08)."""
        if not _id_valid(request_id):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid request_id.")
        if current_soc is not None and not _soc_valid(current_soc):
            return _err(ChargingErrorCode.INVALID_INPUT, "Invalid current_soc.")

        def _op(uow, caller: Actor) -> ChargingResult[ChargingRequest]:
            req = schema.read(self.core, request_id)
            if req is None or not _check_owner_or_operator(req, caller):
                return _err(ChargingErrorCode.NOT_FOUND, "Charging session not found.")
            if req.status is not ChargingSessionStatus.CHARGING:
                return _err(
                    ChargingErrorCode.INVALID_STATE,
                    "Session is not currently CHARGING.",
                )

            veh = uow.queries.get_vehicle(req.vehicle_id)
            if isinstance(veh, Err):
                return from_core_error(veh)

            soc = req.current_soc if current_soc is None else current_soc
            trans = uow.commands.transition_vehicle(
                req.vehicle_id,
                VehicleEvent.INTERRUPT_CHARGING,
                veh.value.version,
                caller,
                TransitionCtx(battery_pct=soc),
            )
            if isinstance(trans, Err):
                return from_core_error(trans)

            bay = next(
                (
                    p
                    for p in uow.queries.list_charging_points(req.station_id)
                    if p.charging_point_id == req.charger_id
                ),
                None,
            )
            if bay is not None and bay.status is ChargingPointStatus.CHARGING:
                pt_res = uow.commands.set_charging_point_status(
                    bay.charging_point_id,
                    ChargingPointStatus.AVAILABLE,
                    bay.version,
                    caller,
                )
                if isinstance(pt_res, Err):
                    return from_core_error(pt_res)

            for cid in (req.point_claim_id, req.vehicle_claim_id):
                if cid is not None:
                    rel = uow.commands.release_claim(cid, caller)
                    if isinstance(rel, Err):
                        return from_core_error(rel)

            req.current_soc = soc
            req.end_time = uow.queries.get_config().as_of
            req.status = ChargingSessionStatus.INTERRUPTED
            schema.update(uow.repository, req)
            committed = uow.commit()
            return from_core_error(committed) if isinstance(committed, Err) else Ok(req)

        return self._run(_op, actor)

    def compute_priority_queue(self, hub_id: str | None = None) -> list[ChargingRequest]:
        """Rank QUEUED requests: 15% override, booked, lowest SoC (BR-M3-03)."""
        threshold = self.core.queries.get_config().low_battery_threshold
        queued = [
            r
            for r in schema.all_requests(self.core)
            if r.status is ChargingSessionStatus.QUEUED
            and (hub_id is None or r.station_id == hub_id)
        ]

        # Booking factor per Hub; on Err (e.g. RESOURCE_UNAVAILABLE) use battery only.
        booked: dict[str, set[str]] = {}
        for queued_hub in {r.station_id for r in queued}:
            demand = self.core.providers.call(
                ProviderPort.RESERVATION_DEMAND,
                lambda p, h=queued_hub: p.upcoming_bookings(h, timedelta(hours=1)),
            )
            if isinstance(demand, Ok):
                booked[queued_hub] = {b.vehicle_id for b in demand.value.bookings}

        for req in queued:
            req.is_emergency = req.current_soc <= threshold

        queued.sort(
            key=lambda r: (
                not (r.current_soc <= threshold),
                r.vehicle_id not in booked.get(r.station_id, set()),
                r.current_soc,
                r.requested_at,
            )
        )
        return queued

    def get_scheduled_sessions(
        self, hub_id: str, horizon: timedelta
    ) -> Result[list[ScheduledChargingSessionRow]]:
        """Return scheduled charging demand for the D-020 provider port."""
        if not _id_valid(hub_id):
            return Err(ErrorCode.INVALID_INPUT, "hub_id must be a non-empty string")
        if horizon <= timedelta(0):
            return Err(ErrorCode.INVALID_INPUT, "horizon must be positive")
        if isinstance((hub_res := self.core.queries.get_hub(hub_id)), Err):
            return hub_res

        as_of = self.core.queries.get_config().as_of
        horizon_end = as_of + horizon
        rows = [
            ScheduledChargingSessionRow(
                session_id=r.request_id,
                vehicle_id=r.vehicle_id,
                charger_id=r.charger_id,
                energy_kwh=r.energy_kwh,
                start_time=r.start_time,
                end_time=r.end_time,
            )
            for r in schema.all_requests(self.core)
            if r.station_id == hub_id
            and r.status in (ChargingSessionStatus.SCHEDULED, ChargingSessionStatus.CHARGING)
            and r.charger_id is not None
            and r.start_time is not None
            and r.end_time is not None
            and r.start_time < horizon_end
            and r.end_time > as_of
        ]
        rows.sort(key=lambda r: (r.start_time, r.session_id))
        return Ok(rows)
