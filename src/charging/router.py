from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from charging import schema
from charging.models import (
    ChargingError,
    ChargingErrorCode,
    ChargingRequest,
    from_core_error,
)
from charging.service import ChargingQueueService
from core.api.security import Principal, acting_as, current_principal, require_operator
from core.domain.enums import Ownership, Role, VehicleType
from core.facade import CoreFacade
from core.result import Err

CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
OperatorPrincipal = Annotated[Principal, Depends(require_operator)]


class ImmediateChargingIn(BaseModel):
    request_id: str
    vehicle_id: str
    hub_id: str
    target_soc: float = Field(default=100.0, gt=0.0, le=100.0)
    duration_minutes: int | None = Field(default=None, gt=0)
    queue_if_full: bool = True


class ScheduleChargingIn(BaseModel):
    request_id: str
    vehicle_id: str
    hub_id: str
    start_at: datetime
    duration_minutes: int = Field(gt=0)
    target_soc: float = Field(default=100.0, gt=0.0, le=100.0)


class ModifyScheduleIn(BaseModel):
    start_at: datetime
    duration_minutes: int = Field(gt=0)


class FinishChargingIn(BaseModel):
    final_soc: float | None = Field(default=None, ge=0.0, le=100.0)


class InterruptChargingIn(BaseModel):
    current_soc: float | None = Field(default=None, ge=0.0, le=100.0)


class RegisterPrivateEvIn(BaseModel):
    plate_or_code: str
    vehicle_type: VehicleType
    battery_capacity_kwh: float = Field(gt=0.0)
    current_soc: float = Field(ge=0.0, le=100.0)
    connector_type: str
    vehicle_id: str | None = None


def _raise_charging_error(err: ChargingError) -> None:
    code_map = {
        ChargingErrorCode.INVALID_INPUT: status.HTTP_400_BAD_REQUEST,
        ChargingErrorCode.FORBIDDEN: status.HTTP_403_FORBIDDEN,
        ChargingErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
        ChargingErrorCode.CONFLICT: status.HTTP_409_CONFLICT,
        ChargingErrorCode.INVALID_STATE: status.HTTP_409_CONFLICT,
        ChargingErrorCode.RESOURCE_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
        ChargingErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    raise HTTPException(
        status_code=code_map.get(err.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        detail={"code": err.code.value, "message": err.message},
    )


def _serialize_session(req: ChargingRequest) -> dict[str, Any]:
    return {
        "request_id": req.request_id,
        "vehicle_id": req.vehicle_id,
        "hub_id": req.station_id,
        "current_soc": req.current_soc,
        "target_soc": req.target_soc,
        "requested_at": req.requested_at.isoformat() if req.requested_at else None,
        "is_emergency": req.is_emergency,
        "status": req.status.value,
        "charger_id": req.charger_id,
        "energy_kwh": req.energy_kwh,
        "start_time": req.start_time.isoformat() if req.start_time else None,
        "end_time": req.end_time.isoformat() if req.end_time else None,
    }


def create_charging_router(service: ChargingQueueService, core: CoreFacade) -> APIRouter:
    router = APIRouter(prefix="/charging", tags=["charging"])

    @router.post("/requests/immediate")
    def request_immediate(body: ImmediateChargingIn, principal: CurrentPrincipal) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        res = service.submit_charging_request(
            body.request_id,
            body.vehicle_id,
            body.hub_id,
            actor,
            target_soc=body.target_soc,
            start_at=None,
            duration_minutes=body.duration_minutes,
            queue_if_full=body.queue_if_full,
        )
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return _serialize_session(res.value)

    @router.post("/requests/schedule")
    def schedule_future(body: ScheduleChargingIn, principal: CurrentPrincipal) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        res = service.submit_charging_request(
            body.request_id,
            body.vehicle_id,
            body.hub_id,
            actor,
            target_soc=body.target_soc,
            start_at=body.start_at,
            duration_minutes=body.duration_minutes,
        )
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return _serialize_session(res.value)

    @router.post("/sessions/{request_id}/start")
    def start_session(request_id: str, principal: CurrentPrincipal) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        res = service.start_scheduled_session(request_id, actor)
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return _serialize_session(res.value)

    @router.post("/sessions/{request_id}/finish")
    def finish_session(
        request_id: str,
        body: FinishChargingIn,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        res = service.finish_charging(request_id, actor, final_soc=body.final_soc)
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return _serialize_session(res.value)

    @router.post("/sessions/{request_id}/interrupt")
    def interrupt_session(
        request_id: str,
        body: InterruptChargingIn,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        res = service.interrupt_charging(request_id, actor, current_soc=body.current_soc)
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return _serialize_session(res.value)

    @router.patch("/requests/{request_id}")
    def modify_schedule(
        request_id: str,
        body: ModifyScheduleIn,
        principal: CurrentPrincipal,
    ) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        res = service.modify_charging_schedule(
            request_id, body.start_at, body.duration_minutes, actor
        )
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return _serialize_session(res.value)

    @router.delete("/requests/{request_id}")
    def cancel_schedule(request_id: str, principal: CurrentPrincipal) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        res = service.cancel_charging_schedule(request_id, actor)
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return _serialize_session(res.value)

    @router.post("/private/vehicles")
    def register_private_ev(
        body: RegisterPrivateEvIn, principal: CurrentPrincipal
    ) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        reg_res = core.commands.register_vehicle(
            vehicle_id=body.vehicle_id or f"V-PRIV-{body.plate_or_code}",
            plate_or_code=body.plate_or_code,
            vehicle_type=body.vehicle_type,
            battery_capacity_kwh=body.battery_capacity_kwh,
            connector_type=body.connector_type,
            ownership=Ownership.PRIVATE,
            owner_user_id=principal.user_id,
            battery_pct=body.current_soc,
            actor=actor,
        )
        if isinstance(reg_res, Err):
            _raise_charging_error(from_core_error(reg_res))
        return {"vehicle_id": reg_res.value.vehicle_id}

    @router.post("/private/slots")
    def reserve_private_slot(
        body: ScheduleChargingIn, principal: CurrentPrincipal
    ) -> dict[str, Any]:
        actor = acting_as(principal, "charging")
        res = service.submit_charging_request(
            body.request_id,
            body.vehicle_id,
            body.hub_id,
            actor,
            target_soc=body.target_soc,
            start_at=body.start_at,
            duration_minutes=body.duration_minutes,
        )
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return _serialize_session(res.value)

    @router.get("/queue")
    def get_priority_queue(
        principal: OperatorPrincipal, hub_id: str | None = None
    ) -> list[dict[str, Any]]:
        return [_serialize_session(r) for r in service.compute_priority_queue(hub_id)]

    @router.post("/schedule/optimize")
    def optimize_schedule(hub_id: str, principal: OperatorPrincipal) -> list[dict[str, Any]]:
        actor = acting_as(principal, "charging")
        res = service.optimize_queue(hub_id, actor)
        if isinstance(res, ChargingError):
            _raise_charging_error(res)
        return [_serialize_session(r) for r in res.value]

    @router.get("/sessions")
    def list_sessions(
        principal: CurrentPrincipal, hub_id: str | None = None
    ) -> list[dict[str, Any]]:
        requests = schema.all_requests(core)
        if hub_id is not None:
            requests = [r for r in requests if r.station_id == hub_id]
        if principal.role is not Role.OPERATOR:
            requests = [r for r in requests if r.user_id == principal.user_id]
        return [_serialize_session(r) for r in requests]

    @router.get("/demand")
    def get_charging_demand(
        hub_id: str,
        principal: OperatorPrincipal,
        horizon_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        res = service.get_scheduled_sessions(hub_id, timedelta(minutes=horizon_minutes))
        if isinstance(res, Err):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": res.code.value, "message": res.message},
            )
        return [
            {
                "session_id": row.session_id,
                "vehicle_id": row.vehicle_id,
                "charger_id": row.charger_id,
                "energy_kwh": row.energy_kwh,
                "start_time": row.start_time.isoformat(),
                "end_time": row.end_time.isoformat(),
            }
            for row in res.value
        ]

    return router
