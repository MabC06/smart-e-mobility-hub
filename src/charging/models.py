"""Domain models and error types for Module M3 Charging Request & Priority Queue v1."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from core.errors import ErrorCode
from core.result import Err, Ok


class ChargingErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    INVALID_STATE = "INVALID_STATE"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class ChargingError:
    code: ChargingErrorCode
    message: str


type ChargingResult[T] = Ok[T] | ChargingError


def from_core_error(err: Err) -> ChargingError:
    mapping = {
        ErrorCode.INVALID_INPUT: ChargingErrorCode.INVALID_INPUT,
        ErrorCode.FORBIDDEN: ChargingErrorCode.FORBIDDEN,
        ErrorCode.NOT_FOUND: ChargingErrorCode.NOT_FOUND,
        ErrorCode.INVALID_STATE: ChargingErrorCode.INVALID_STATE,
        ErrorCode.RESOURCE_UNAVAILABLE: ChargingErrorCode.RESOURCE_UNAVAILABLE,
        getattr(ErrorCode, "CLAIM_CONFLICT", None): ChargingErrorCode.CONFLICT,
        getattr(ErrorCode, "VERSION_CONFLICT", None): ChargingErrorCode.CONFLICT,
        getattr(ErrorCode, "INVALID_TRANSITION", None): ChargingErrorCode.INVALID_STATE,
        getattr(ErrorCode, "HUB_FULL", None): ChargingErrorCode.INVALID_STATE,
        getattr(ErrorCode, "SPACE_NOT_FREE", None): ChargingErrorCode.INVALID_STATE,
        getattr(ErrorCode, "BATTERY_TOO_LOW", None): ChargingErrorCode.INVALID_INPUT,
    }
    clean_mapping = {k: v for k, v in mapping.items() if k is not None}
    return ChargingError(clean_mapping.get(err.code, ChargingErrorCode.INTERNAL_ERROR), err.message)


class ChargingSessionStatus(StrEnum):
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    CHARGING = "CHARGING"
    COMPLETED = "COMPLETED"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class ChargingRequest:
    """Persisted charging request & session entity (D-017, D-018)."""

    ID_FIELD: ClassVar[str] = "request_id"
    VERSIONED: ClassVar[bool] = True

    request_id: str
    vehicle_id: str
    station_id: str
    current_soc: float
    target_soc: float
    requested_at: datetime
    is_emergency: bool = False
    energy_kwh: float = 0.0
    charger_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    point_claim_id: str | None = None
    vehicle_claim_id: str | None = None
    status: ChargingSessionStatus = ChargingSessionStatus.QUEUED
    user_id: str | None = None
    version: int = 1
