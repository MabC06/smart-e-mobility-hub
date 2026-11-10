"""FastAPI router for Allocation & Vehicle Dispatching (M4).

Implements REST API endpoints following D-002 (plain def handlers, Pydantic v2 schemas).
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from core.actor import Actor
from core.domain.enums import Role, VehicleType
from core.errors import ErrorCode
from core.providers import (
    AlternativeChargingProvider,
    AlternativeHubProvider,
    AlternativeHubRequest,
    DisplacedChargingRequest,
)
from core.result import Ok, Result

from .arbitration import ContenderRequest, RequestClass, settle_competing_requests
from .config import AllocationConfig
from .models import DispatchTaskStatus
from .service import AllocationService


class PlanRequestIn(BaseModel):
    slot_id: str = "slot1"


class ApproveTaskIn(BaseModel):
    adjusted_quantity: int | None = Field(default=None, ge=1)


class ReturnTaskIn(BaseModel):
    battery_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class CancelTaskIn(BaseModel):
    reason: str = ""


class DisplacedRequestIn(BaseModel):
    request_id: str
    details: str = ""


class FindAlternativeChargingIn(BaseModel):
    displaced_requests: list[DisplacedRequestIn]
    failed_hub_id: str


class ContenderIn(BaseModel):
    request_id: str
    request_class: int = Field(..., ge=1, le=8)
    requested_at: datetime
    requester_id: str
    target_resource_id: str
    details: str = ""


class ArbitrateIn(BaseModel):
    requests: list[ContenderIn]


class ConfigUpdateIn(BaseModel):
    horizon_minutes: int | None = Field(default=None, ge=1)
    safety_stock: int | None = Field(default=None, ge=0)
    parking_buffer: int | None = Field(default=None, ge=0)
    min_dispatch_battery: float | None = Field(default=None, ge=0.0, le=100.0)
    max_tasks_per_hub: int | None = Field(default=None, ge=1)
    max_vehicles_per_task: int | None = Field(default=None, ge=1)
    task_timeout_minutes: int | None = Field(default=None, ge=1)
    staleness_limit_minutes: int | None = Field(default=None, ge=1)
    reservation_lookahead_minutes: int | None = Field(default=None, ge=1)


def _handle_result[T](result: Result[T]) -> T:
    if isinstance(result, Ok):
        return result.value
    code_map = {
        ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
        ErrorCode.INVALID_INPUT: status.HTTP_400_BAD_REQUEST,
        ErrorCode.INVALID_TRANSITION: status.HTTP_409_CONFLICT,
        ErrorCode.CLAIM_CONFLICT: status.HTTP_409_CONFLICT,
        ErrorCode.VERSION_CONFLICT: status.HTTP_409_CONFLICT,
        ErrorCode.RESOURCE_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCode.FORBIDDEN: status.HTTP_403_FORBIDDEN,
        ErrorCode.HUB_FULL: status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorCode.BATTERY_TOO_LOW: status.HTTP_422_UNPROCESSABLE_CONTENT,
    }
    status_code = code_map.get(result.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(
        status_code=status_code, detail={"code": result.code.name, "message": result.message}
    )


def create_allocation_router(
    service: AllocationService,
    hub_provider: AlternativeHubProvider,
    charging_provider: AlternativeChargingProvider,
) -> APIRouter:
    router = APIRouter()
    operator_actor = Actor(user_id="OP01", role=Role.OPERATOR, module="allocation")

    @router.post("/tasks/plan")
    def plan_tasks(body: PlanRequestIn) -> list[dict[str, Any]]:
        """Generate and save redistribution recommendations (UC-M4-01)."""
        tasks = _handle_result(service.plan(operator_actor, body.slot_id))
        return [
            {
                "task_id": t.task_id,
                "source_hub_id": t.source_hub_id,
                "target_hub_id": t.target_hub_id,
                "vehicle_type": t.vehicle_type.value,
                "quantity": t.quantity,
                "assigned_vehicles": t.assigned_vehicles,
                "status": t.status.value,
                "priority": t.priority,
                "reason": t.reason,
            }
            for t in tasks
        ]

    @router.get("/tasks")
    def list_tasks(task_status: DispatchTaskStatus | None = None) -> list[dict[str, Any]]:
        """List current allocation tasks with optional status filter."""
        tasks = service.list_tasks(task_status)
        return [
            {
                "task_id": t.task_id,
                "source_hub_id": t.source_hub_id,
                "target_hub_id": t.target_hub_id,
                "vehicle_type": t.vehicle_type.value,
                "quantity": t.quantity,
                "assigned_vehicles": t.assigned_vehicles,
                "status": t.status.value,
                "priority": t.priority,
                "reason": t.reason,
            }
            for t in tasks
        ]

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        """Get details of one dispatch task."""
        t = _handle_result(service.get_task(task_id))
        return {
            "task_id": t.task_id,
            "source_hub_id": t.source_hub_id,
            "target_hub_id": t.target_hub_id,
            "vehicle_type": t.vehicle_type.value,
            "quantity": t.quantity,
            "assigned_vehicles": t.assigned_vehicles,
            "status": t.status.value,
            "priority": t.priority,
            "reason": t.reason,
        }

    @router.post("/tasks/{task_id}/approve")
    def approve_task(task_id: str, body: ApproveTaskIn | None = None) -> dict[str, Any]:
        """Approve task and place claims on vehicles and target spaces (UC-M4-02)."""
        qty = body.adjusted_quantity if body else None
        t = _handle_result(service.approve_task(task_id, operator_actor, qty))
        return {"task_id": t.task_id, "status": t.status.value, "quantity": t.quantity}

    @router.post("/tasks/{task_id}/pickup")
    def carry_out_pickup(task_id: str) -> dict[str, Any]:
        """Confirm vehicle pick-up at origin hub, setting task to IN_PROGRESS (UC-M4-03)."""
        t = _handle_result(service.carry_out_pickup(task_id, operator_actor))
        return {"task_id": t.task_id, "status": t.status.value}

    @router.post("/tasks/{task_id}/return")
    def carry_out_return(task_id: str, body: ReturnTaskIn | None = None) -> dict[str, Any]:
        """Confirm delivery at destination, releasing claims and completing task (UC-M4-03)."""
        pct = body.battery_pct if body else None
        t = _handle_result(service.carry_out_return(task_id, operator_actor, pct))
        return {"task_id": t.task_id, "status": t.status.value}

    @router.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: str, body: CancelTaskIn | None = None) -> dict[str, Any]:
        """Cancel task and release held claims (UC-M4-04)."""
        reason = body.reason if body else ""
        t = _handle_result(service.cancel_task(task_id, operator_actor, reason))
        return {"task_id": t.task_id, "status": t.status.value, "reason": t.reason}

    @router.get("/alternatives/hubs")
    def suggest_alternative_hubs(
        requested_hub_id: str,
        vehicle_type: VehicleType | None = None,
        require_vehicle: bool = True,
        require_parking: bool = False,
        limit: int = 3,
    ) -> dict[str, Any]:
        """Suggest nearest suitable alternative hubs (UC-M4-05, BR-M4-10)."""
        req = AlternativeHubRequest(
            requested_hub_id=requested_hub_id,
            vehicle_type=vehicle_type,
            require_vehicle=require_vehicle,
            require_parking=require_parking,
            limit=limit,
        )
        res = _handle_result(hub_provider.suggest_alternative_hubs(req))
        return {
            "candidates": [
                {
                    "hub_id": c.hub_id,
                    "hub_name": c.hub_name,
                    "closeness": c.closeness,
                    "available_vehicles": c.available_vehicles,
                    "free_spaces": c.free_spaces,
                    "best_battery_level": c.best_battery_level,
                }
                for c in res.candidates
            ],
            "as_of": res.as_of.isoformat(),
            "reason_code": res.reason_code,
        }

    @router.post("/alternatives/charging")
    def find_alternative_charging(body: FindAlternativeChargingIn) -> list[dict[str, Any]]:
        """Suggest nearest suitable alternative charging hubs (UC-M4-07, BR-M4-10, BR-M3-02)."""
        reqs = [
            DisplacedChargingRequest(request_id=r.request_id, details=r.details)
            for r in body.displaced_requests
        ]
        res = _handle_result(charging_provider.find_alternative_charging(reqs, body.failed_hub_id))
        return [
            {
                "request_id": alt.request_id,
                "alternative_hub_id": alt.alternative_hub_id,
                "charging_point_id": alt.charging_point_id,
                "closeness": alt.closeness,
                "status": alt.status,
            }
            for alt in res.alternatives
        ]

    @router.post("/arbitrate")
    def arbitrate_competing_requests(body: ArbitrateIn) -> dict[str, Any]:
        """Arbitrate competing requests for a shared resource (UC-M4-06, BR-M4-01)."""
        contenders = [
            ContenderRequest(
                request_id=c.request_id,
                request_class=RequestClass(c.request_class),
                requested_at=c.requested_at,
                requester_id=c.requester_id,
                target_resource_id=c.target_resource_id,
                details=c.details,
            )
            for c in body.requests
        ]
        outcome = settle_competing_requests(contenders)
        if outcome is None:
            return {"outcome": None}
        return {
            "winner_request_id": outcome.winner.request_id,
            "displaced_request_ids": [d.request_id for d in outcome.displaced],
            "reason": outcome.reason,
        }

    @router.get("/config")
    def get_config() -> dict[str, Any]:
        """Get current allocation configuration (UC-M4-09)."""
        cfg = service.get_config()
        return {
            "horizon_minutes": cfg.horizon_minutes,
            "safety_stock": cfg.safety_stock,
            "parking_buffer": cfg.parking_buffer,
            "min_dispatch_battery": cfg.min_dispatch_battery,
            "max_tasks_per_hub": cfg.max_tasks_per_hub,
            "max_vehicles_per_task": cfg.max_vehicles_per_task,
            "task_timeout_minutes": cfg.task_timeout_minutes,
            "staleness_limit_minutes": cfg.staleness_limit_minutes,
            "reservation_lookahead_minutes": cfg.reservation_lookahead_minutes,
        }

    @router.put("/config")
    def update_config(body: ConfigUpdateIn) -> dict[str, Any]:
        """Update allocation configuration settings (UC-M4-09)."""
        cur = service.get_config()
        new_cfg = AllocationConfig(
            horizon_minutes=body.horizon_minutes
            if body.horizon_minutes is not None
            else cur.horizon_minutes,
            safety_stock=body.safety_stock if body.safety_stock is not None else cur.safety_stock,
            parking_buffer=body.parking_buffer
            if body.parking_buffer is not None
            else cur.parking_buffer,
            min_dispatch_battery=body.min_dispatch_battery
            if body.min_dispatch_battery is not None
            else cur.min_dispatch_battery,
            max_tasks_per_hub=body.max_tasks_per_hub
            if body.max_tasks_per_hub is not None
            else cur.max_tasks_per_hub,
            max_vehicles_per_task=body.max_vehicles_per_task
            if body.max_vehicles_per_task is not None
            else cur.max_vehicles_per_task,
            task_timeout_minutes=body.task_timeout_minutes
            if body.task_timeout_minutes is not None
            else cur.task_timeout_minutes,
            staleness_limit_minutes=body.staleness_limit_minutes
            if body.staleness_limit_minutes is not None
            else cur.staleness_limit_minutes,
            reservation_lookahead_minutes=body.reservation_lookahead_minutes
            if body.reservation_lookahead_minutes is not None
            else cur.reservation_lookahead_minutes,
            closeness_matrix=cur.closeness_matrix,
        )
        service.set_config(new_cfg)
        return {
            "status": "updated",
            "config": {
                "horizon_minutes": new_cfg.horizon_minutes,
                "safety_stock": new_cfg.safety_stock,
                "parking_buffer": new_cfg.parking_buffer,
                "min_dispatch_battery": new_cfg.min_dispatch_battery,
                "max_tasks_per_hub": new_cfg.max_tasks_per_hub,
                "max_vehicles_per_task": new_cfg.max_vehicles_per_task,
                "task_timeout_minutes": new_cfg.task_timeout_minutes,
                "staleness_limit_minutes": new_cfg.staleness_limit_minutes,
                "reservation_lookahead_minutes": new_cfg.reservation_lookahead_minutes,
            },
        }

    return router
