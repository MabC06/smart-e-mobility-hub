"""Domain entities, enums and views for the monitoring and incident handling module (M5).

Traceability:
- FR-08 (System Monitoring)
- FR-09 (Incident Handling)
- BR-M5-01 to BR-M5-05
- docs/design/structural/incident-data-model.md
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from core.domain.enums import HubStatus


class IncidentType(StrEnum):
    CHARGING_POINT_FAILURE = "INC-HW-01"
    PARKING_SENSOR_FAULT = "INC-HW-02"
    HUB_CAPACITY_FULL = "INC-CAP-01"
    HUB_VEHICLE_DEFICIT = "INC-CAP-02"
    BATTERY_CRITICAL_FAULT = "INC-BAT-01"
    TELEMETRY_CONNECTION_LOSS = "INC-COMM-01"
    OVERDUE_VEHICLE = "INC-USR-01"


class IncidentSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


@dataclass(slots=True)
class IncidentTicket:
    """An operational incident ticket tracking faults, capacity overruns, or vehicle defects.

    Registered with core via TableSpec (D-018).
    """

    ID_FIELD: ClassVar[str] = "incident_id"
    VERSIONED: ClassVar[bool] = True

    incident_id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus
    hub_id: str
    entity_type: str
    entity_id: str
    error_code: str | None
    description: str
    reported_by: str
    assigned_operator_id: str | None
    resolution_notes: str | None
    created_at: datetime
    acknowledged_at: datetime | None
    escalated_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    version: int


@dataclass(slots=True)
class TicketAuditLog:
    """Audit trail record for an incident ticket state transition (NFR-25)."""

    ID_FIELD: ClassVar[str] = "log_id"
    VERSIONED: ClassVar[bool] = False

    log_id: str
    incident_id: str
    previous_status: IncidentStatus
    new_status: IncidentStatus
    changed_by: str
    action: str
    reason: str | None
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class HubMetricsView:
    """Computed utilization metrics for a Mobility Hub (FR-08.1, FR-08.2)."""

    hub_id: str
    name: str
    zone_code: str
    parking_capacity: int
    occupied_parking_spaces: int
    free_parking_spaces: int
    parking_occupancy_pct: float
    charging_point_count: int
    charging_points_in_use: int
    charging_utilization_pct: float
    available_rental_vehicles: int
    status: HubStatus
    version: int
    as_of: datetime
