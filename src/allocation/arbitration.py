"""Arbitration of competing requests for resources (FR-11.M4.1, BR-M4-01, UC-M4-06).

Defines the priority hierarchy between different classes of requests and orders them
deterministically by (class_priority, request_time, request_id).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class RequestClass(IntEnum):
    """Priority levels 1 (highest) to 8 (lowest) defined in BR-M4-01."""

    OPERATOR_EMERGENCY = 1
    CONFIRMED_RESERVATION_SOON = 2
    TRIP_RETURN = 3
    SCHEDULED_CHARGING = 4
    DISPATCH_TASK = 5
    WALK_IN_RENTAL = 6
    AD_HOC_CHARGING = 7
    MAINTENANCE_TRANSFER = 8


@dataclass(frozen=True, slots=True)
class ContenderRequest:
    """A competing request for a shared resource (vehicle, parking space, or charger)."""

    request_id: str
    request_class: RequestClass
    requested_at: datetime
    requester_id: str
    target_resource_id: str
    details: str = ""


@dataclass(frozen=True, slots=True)
class ArbitrationResult:
    """Outcome of settling competing requests for a resource."""

    winner: ContenderRequest
    displaced: list[ContenderRequest]
    reason: str


def settle_competing_requests(requests: list[ContenderRequest]) -> ArbitrationResult | None:
    """Settle competing requests for one resource according to BR-M4-01.

    Ordering rule:
    1. Lower RequestClass value wins (class priority 1 beats 2, etc.)
    2. Earlier requested_at wins (FCFS within the same class)
    3. Lexicographical request_id breaks any remaining ties deterministically (NFR-13).
    """
    if not requests:
        return None

    sorted_requests = sorted(
        requests,
        key=lambda r: (r.request_class, r.requested_at, r.request_id),
    )
    winner = sorted_requests[0]
    displaced = sorted_requests[1:]
    reason = (
        f"Request {winner.request_id} won by class {winner.request_class.name} "
        f"at {winner.requested_at.isoformat()}"
    )
    return ArbitrationResult(winner=winner, displaced=displaced, reason=reason)
