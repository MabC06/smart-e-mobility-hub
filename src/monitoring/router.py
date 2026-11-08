"""REST API endpoints for the monitoring and incident handling module (M5).

Traceability:
- FR-08 (System Monitoring)
- FR-09 (Incident Handling)
- UC-M5-01, UC-M5-02
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from monitoring.domain import (
    HubMetricsView,
    IncidentSeverity,
    IncidentStatus,
    IncidentTicket,
    IncidentType,
    TicketAuditLog,
)
from monitoring.service import (
    IncidentNotFoundError,
    InvalidStatusTransitionError,
    MonitoringService,
)

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

# Injected by install()
_service: MonitoringService | None = None


def set_service(service: MonitoringService) -> None:
    global _service
    _service = service


def get_service() -> MonitoringService:
    if _service is None:
        raise RuntimeError("MonitoringService has not been initialized")
    return _service


# ---------------------------------------------------------------------------------- Schemas
class CreateIncidentRequest(BaseModel):
    incident_type: IncidentType
    severity: IncidentSeverity
    hub_id: str
    entity_type: str
    entity_id: str
    description: str
    reported_by: str = "OPERATOR"
    error_code: str | None = None


class AcknowledgeRequest(BaseModel):
    operator_id: str = "operator_1"


class EscalateRequest(BaseModel):
    reason: str = "Unacknowledged > 5 minutes"


class ResolveRequest(BaseModel):
    resolution_notes: str = Field(min_length=1)
    operator_id: str = "operator_1"


class CloseRequest(BaseModel):
    operator_id: str = "operator_1"


# ---------------------------------------------------------------------------- Metrics Routes
@router.get("/metrics/hubs", response_model=list[HubMetricsView])
def list_hub_metrics() -> list[HubMetricsView]:
    """Retrieve real-time utilization metrics for all Hubs (FR-08.1, FR-08.2)."""
    return get_service().get_network_metrics()


@router.get("/metrics/hubs/{hub_id}", response_model=HubMetricsView)
def get_hub_metrics(hub_id: str) -> HubMetricsView:
    """Retrieve real-time utilization metrics for a specific Hub (FR-08.1, FR-08.2)."""
    metrics = get_service().get_hub_metrics(hub_id)
    if metrics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Hub {hub_id} not found")
    return metrics


@router.post("/hubs/{hub_id}/evaluate-capacity")
def evaluate_hub_capacity(hub_id: str) -> dict[str, str | None]:
    """Trigger on-demand capacity evaluation for a Hub (BR-M5-01, BR-M5-02)."""
    res = get_service().evaluate_hub_capacity(hub_id)
    if res is None:
        return {"status": "unchanged"}
    return {"status": "updated"}


# --------------------------------------------------------------------------- Incident Routes
@router.get("/incidents", response_model=list[IncidentTicket])
def list_incidents(
    hub_id: str | None = None,
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    severity_filter: Annotated[IncidentSeverity | None, Query(alias="severity")] = None,
) -> list[IncidentTicket]:
    """List operational incident tickets with optional filters (FR-09.2)."""
    return get_service().list_incidents(
        hub_id=hub_id, status=status_filter, severity=severity_filter
    )


@router.get("/incidents/{incident_id}", response_model=IncidentTicket)
def get_incident(incident_id: str) -> IncidentTicket:
    """Get single incident ticket details by ID."""
    ticket = get_service().get_incident(incident_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {incident_id} not found"
        )
    return ticket


@router.get("/incidents/{incident_id}/logs", response_model=list[TicketAuditLog])
def get_incident_audit_logs(incident_id: str) -> list[TicketAuditLog]:
    """Retrieve complete lifecycle audit trail for an incident ticket (NFR-25)."""
    return get_service().list_audit_logs(incident_id)


@router.post("/incidents", response_model=IncidentTicket, status_code=status.HTTP_201_CREATED)
def create_incident(body: CreateIncidentRequest) -> IncidentTicket:
    """Create a new operational incident ticket (FR-09.2)."""
    return get_service().create_incident(
        incident_type=body.incident_type,
        severity=body.severity,
        hub_id=body.hub_id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        description=body.description,
        reported_by=body.reported_by,
        error_code=body.error_code,
    )


@router.post("/incidents/{incident_id}/acknowledge", response_model=IncidentTicket)
def acknowledge_incident(incident_id: str, body: AcknowledgeRequest) -> IncidentTicket:
    """Acknowledge and claim an incident ticket (OPEN/ESCALATED -> IN_PROGRESS)."""
    try:
        return get_service().acknowledge_incident(incident_id, body.operator_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/escalate", response_model=IncidentTicket)
def escalate_incident(incident_id: str, body: EscalateRequest) -> IncidentTicket:
    """Escalate an unacknowledged incident ticket (BR-M5-04: OPEN -> ESCALATED)."""
    try:
        return get_service().escalate_incident(incident_id, body.reason)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentTicket)
def resolve_incident(incident_id: str, body: ResolveRequest) -> IncidentTicket:
    """Resolve an incident ticket with mandatory notes (IN_PROGRESS/ESCALATED -> RESOLVED)."""
    try:
        return get_service().resolve_incident(incident_id, body.resolution_notes, body.operator_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (InvalidStatusTransitionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/close", response_model=IncidentTicket)
def close_incident(incident_id: str, body: CloseRequest) -> IncidentTicket:
    """Final sign-off and closure of an incident ticket (RESOLVED -> CLOSED)."""
    try:
        return get_service().close_incident(incident_id, body.operator_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
