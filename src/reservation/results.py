"""M2 service outcomes; no changes to the Core ErrorCode contract."""

from dataclasses import dataclass
from enum import StrEnum

from core.errors import ErrorCode
from core.result import Err, Ok


class BookingErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND_OR_NOT_OWNED = "NOT_FOUND_OR_NOT_OWNED"
    LIMIT_REACHED = "LIMIT_REACHED"
    CONFLICT = "CONFLICT"
    INVALID_STATE = "INVALID_STATE"
    EXPIRED = "EXPIRED"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    NO_PARKING = "NO_PARKING"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class BookingError:
    code: BookingErrorCode
    message: str


type BookingResult[T] = Ok[T] | BookingError


def from_core(error: Err) -> BookingError:
    """Map shared failures without exposing another holder's IDs or Core details."""
    codes = {
        ErrorCode.INVALID_INPUT: BookingErrorCode.INVALID_INPUT,
        ErrorCode.UNAUTHENTICATED: BookingErrorCode.FORBIDDEN,
        ErrorCode.FORBIDDEN: BookingErrorCode.FORBIDDEN,
        ErrorCode.NOT_FOUND: BookingErrorCode.NOT_FOUND_OR_NOT_OWNED,
        ErrorCode.VERSION_CONFLICT: BookingErrorCode.CONFLICT,
        ErrorCode.CLAIM_CONFLICT: BookingErrorCode.CONFLICT,
        ErrorCode.INVALID_TRANSITION: BookingErrorCode.INVALID_STATE,
        ErrorCode.HUB_FULL: BookingErrorCode.NO_PARKING,
        ErrorCode.SPACE_NOT_FREE: BookingErrorCode.NO_PARKING,
        ErrorCode.BATTERY_TOO_LOW: BookingErrorCode.RESOURCE_UNAVAILABLE,
        ErrorCode.RESOURCE_UNAVAILABLE: BookingErrorCode.RESOURCE_UNAVAILABLE,
        ErrorCode.INTERNAL_ERROR: BookingErrorCode.INTERNAL_ERROR,
    }
    code = codes[error.code]
    return BookingError(code, f"Booking operation failed: {code.value}.")
