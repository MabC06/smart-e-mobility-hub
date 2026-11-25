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


_CORE_ERROR_MAP: dict[ErrorCode, ChargingErrorCode] = {
    ErrorCode.INVALID_INPUT: ChargingErrorCode.INVALID_INPUT,
    ErrorCode.FORBIDDEN: ChargingErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND: ChargingErrorCode.NOT_FOUND,
    ErrorCode.RESOURCE_UNAVAILABLE: ChargingErrorCode.RESOURCE_UNAVAILABLE,
    ErrorCode.CLAIM_CONFLICT: ChargingErrorCode.CONFLICT,
    ErrorCode.VERSION_CONFLICT: ChargingErrorCode.CONFLICT,
    ErrorCode.INVALID_TRANSITION: ChargingErrorCode.INVALID_STATE,
    ErrorCode.HUB_FULL: ChargingErrorCode.INVALID_STATE,
    ErrorCode.SPACE_NOT_FREE: ChargingErrorCode.INVALID_STATE,
    ErrorCode.BATTERY_TOO_LOW: ChargingErrorCode.INVALID_INPUT,
}


def from_core_error(err: Err) -> ChargingError:
    """Translate a refused Core command into a charging error (FR-07)."""
    return ChargingError(
        _CORE_ERROR_MAP.get(err.code, ChargingErrorCode.INTERNAL_ERROR), err.message
    )


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
