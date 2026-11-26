"""Request and response models of the REST interface. Their JSON schema (``/openapi.json``) is the
interface document for the user interface (M7)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.domain.enums import (
    ChargingPointStatus,
    HubStatus,
    Ownership,
    Role,
    SpaceStatus,
    VehicleState,
    VehicleType,
)
from core.sensors import SensorEventType


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorOut(BaseModel):
    error: ErrorBody


class LoginIn(BaseModel):
    code: str = Field(min_length=1, max_length=64, description="Student or operator code")
    password: str = Field(min_length=1, max_length=256)


class LoginOut(_Out):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user_id: str
    role: Role


class MeOut(_Out):
    user_id: str
    role: Role
    module: str


class HubOut(_Out):
    hub_id: str
    name: str
    zone_code: str
    parking_capacity: int
    occupied: int
    free_spaces: int
    charging_points: int
    charging_in_use: int
    available_vehicles: int
    status: HubStatus
    version: int
    as_of: datetime


class VehicleOut(_Out):
    vehicle_id: str
    plate_or_code: str
    ownership: Ownership
    vehicle_type: VehicleType
    battery_pct: float
    state: VehicleState
    fault_flag: bool
    hub_id: str | None
    parking_space_id: str | None
    version: int


class SpaceOut(_Out):
    parking_space_id: str
    hub_id: str
    label: str
    status: SpaceStatus
    occupant_vehicle_id: str | None
    version: int


class ChargingPointOut(_Out):
    charging_point_id: str
    hub_id: str
    parking_space_id: str
    power_rate_kw: float
    status: ChargingPointStatus
    version: int


class StateLogOut(_Out):
    record_id: str
    at: datetime
    entity_type: str
    entity_id: str
    previous_state: str
    new_state: str
    trigger: str
    actor: str


class SensorResultOut(_Out):
    event_id: str
    type: SensorEventType
    changed: bool
    detail: str
