"""SQLAlchemy table schema and TableSpec registrations for the monitoring module (D-018).

Traceability:
- FR-09 (Operational Incident Handling)
- D-018 (Module tables register with core)
- docs/design/structural/incident-data-model.md
"""

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text

from core.repository.schema import TableSpec, UtcDateTime, metadata
from monitoring.domain import (
    IncidentSeverity,
    IncidentStatus,
    IncidentTicket,
    IncidentType,
    TicketAuditLog,
)

monitoring_incidents = Table(
    "monitoring_incidents",
    metadata,
    Column("incident_id", String, primary_key=True),
    Column("incident_type", String, nullable=False),
    Column("severity", String, nullable=False),
    Column("status", String, nullable=False),
    Column("hub_id", String, ForeignKey("hubs.hub_id"), nullable=False),
    Column("entity_type", String, nullable=False),
    Column("entity_id", String, nullable=False),
    Column("error_code", String, nullable=True),
    Column("description", Text, nullable=False),
    Column("reported_by", String, nullable=False),
    Column("assigned_operator_id", String, nullable=True),
    Column("resolution_notes", Text, nullable=True),
    Column("created_at", UtcDateTime, nullable=False),
    Column("acknowledged_at", UtcDateTime, nullable=True),
    Column("escalated_at", UtcDateTime, nullable=True),
    Column("resolved_at", UtcDateTime, nullable=True),
    Column("closed_at", UtcDateTime, nullable=True),
    Column("version", Integer, nullable=False),
)

monitoring_incident_audit_logs = Table(
    "monitoring_incident_audit_logs",
    metadata,
    Column("log_id", String, primary_key=True),
    Column("incident_id", String, ForeignKey("monitoring_incidents.incident_id"), nullable=False),
    Column("previous_status", String, nullable=False),
    Column("new_status", String, nullable=False),
    Column("changed_by", String, nullable=False),
    Column("action", String, nullable=False),
    Column("reason", Text, nullable=True),
    Column("timestamp", UtcDateTime, nullable=False),
)

INCIDENT_SPEC = TableSpec(
    entity=IncidentTicket,
    table=monitoring_incidents,
    id_column="incident_id",
    enums={
        "incident_type": IncidentType,
        "severity": IncidentSeverity,
        "status": IncidentStatus,
    },
    versioned=True,
)

AUDIT_SPEC = TableSpec(
    entity=TicketAuditLog,
    table=monitoring_incident_audit_logs,
    id_column="log_id",
    enums={
        "previous_status": IncidentStatus,
        "new_status": IncidentStatus,
    },
    versioned=False,
)
