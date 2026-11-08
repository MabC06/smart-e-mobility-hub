"""MonitoringService: core business logic for monitoring, capacity alerts and incident management.

Traceability:
- FR-08.1, FR-08.2 (Telemetry & Metrics Aggregation)
- FR-08.3, FR-08.4 (Capacity Alert & State Synchronization via set_hub_status)
- FR-09.1, FR-09.2, FR-09.3, FR-09.4 (Incident Detection, Ticket Creation, Lifecycle Tracking)
- BR-M5-01 (Capacity Warning Threshold >= 90%)
- BR-M5-02 (Critical Capacity Overflow == 100%)
- BR-M5-03 (Charger Fault Isolation)
- BR-M5-04 (Unacknowledged Escalation)
- BR-M5-05 (Low Battery Lockout)
"""

import logging
from uuid import uuid4

from core.actor import Actor
from core.domain.entities import DomainEvent
from core.domain.enums import ChargingPointStatus, HubStatus, Role
from core.facade import CoreFacade
from core.result import Err, Ok, Result
from core.views import HubStatusView, HubView
from monitoring.domain import (
    HubMetricsView,
    IncidentSeverity,
    IncidentStatus,
    IncidentTicket,
    IncidentType,
    TicketAuditLog,
)

logger = logging.getLogger("monitoring.service")

MONITORING_SYSTEM_ACTOR = Actor(
    user_id="MONITORING_DAEMON", role=Role.OPERATOR, module="monitoring"
)


class IncidentNotFoundError(Exception):
    """Raised when an incident ticket is not found."""


class InvalidStatusTransitionError(Exception):
    """Raised when an illegal lifecycle transition is attempted."""


class MonitoringService:
    def __init__(self, core: CoreFacade) -> None:
        self._core = core

    # ---------------------------------------------------------------------------------- Metrics
    def get_hub_metrics(self, hub_id: str) -> HubMetricsView | None:
        """Aggregate real-time utilization metrics for an individual Hub (FR-08.1, FR-08.2)."""
        res = self._core.queries.get_hub(hub_id)
        if isinstance(res, Err):
            return None
        return self._build_metrics_view(res.value)

    def get_network_metrics(self) -> list[HubMetricsView]:
        """Aggregate metrics across all Hubs in the network (FR-08.2)."""
        hubs = self._core.queries.list_hubs()
        return [self._build_metrics_view(h) for h in hubs]

    def _build_metrics_view(self, hub: HubView) -> HubMetricsView:
        cap = hub.parking_capacity
        occupied = hub.occupied
        occ_pct = round((occupied / cap) * 100.0, 2) if cap > 0 else 0.0

        cp_total = hub.charging_points
        cp_in_use = hub.charging_in_use
        chg_pct = round((cp_in_use / cp_total) * 100.0, 2) if cp_total > 0 else 0.0

        return HubMetricsView(
            hub_id=hub.hub_id,
            name=hub.name,
            zone_code=hub.zone_code,
            parking_capacity=cap,
            occupied_parking_spaces=occupied,
            free_parking_spaces=hub.free_spaces,
            parking_occupancy_pct=occ_pct,
            charging_point_count=cp_total,
            charging_points_in_use=cp_in_use,
            charging_utilization_pct=chg_pct,
            available_rental_vehicles=hub.available_vehicles,
            status=hub.status,
            version=hub.version,
            as_of=hub.as_of,
        )

    # ----------------------------------------------------------------- Capacity Alerts & Status
    def evaluate_hub_capacity(self, hub_id: str) -> Result[HubStatusView] | None:
        """Evaluate parking capacity thresholds and transition status via core.set_hub_status().

        Implements BR-M5-01 (>= 90% -> WARNING) and BR-M5-02 (100% -> CRITICAL).
        """
        res = self._core.queries.get_hub(hub_id)
        if isinstance(res, Err):
            return None
        hub = res.value

        # Do not override maintenance status set manually by operators
        if hub.status is HubStatus.MAINTENANCE:
            return None

        cap = hub.parking_capacity
        occupied = hub.occupied
        ratio = occupied / cap if cap > 0 else 0.0

        target_status: HubStatus
        if ratio >= 1.0:
            target_status = HubStatus.CRITICAL
        elif ratio >= 0.90:
            target_status = HubStatus.WARNING
        else:
            target_status = HubStatus.ACTIVE

        if hub.status is target_status:
            return None

        logger.info(
            "Hub %s capacity changed: ratio=%.2f, transitioning from %s to %s",
            hub_id,
            ratio,
            hub.status.value,
            target_status.value,
        )

        update_res = self._core.commands.set_hub_status(
            hub_id, target_status, hub.version, MONITORING_SYSTEM_ACTOR
        )

        if isinstance(update_res, Ok) and target_status is HubStatus.CRITICAL:
            # Check if an open capacity incident already exists
            existing = self.list_incidents(
                hub_id=hub_id,
                status=IncidentStatus.OPEN,
            )
            if not any(i.incident_type == IncidentType.HUB_CAPACITY_FULL for i in existing):
                self.create_incident(
                    incident_type=IncidentType.HUB_CAPACITY_FULL,
                    severity=IncidentSeverity.HIGH,
                    hub_id=hub_id,
                    entity_type="Hub",
                    entity_id=hub_id,
                    description=f"Hub {hub.name} reached 100% parking capacity ({occupied}/{cap})",
                    reported_by="SYSTEM_CAPACITY_EVALUATOR",
                )

        return update_res

    def on_space_occupancy_changed(self, event: DomainEvent) -> None:
        """Event handler reacting to SpaceOccupancyChanged to evaluate capacity."""
        hub_id = event.payload.get("hub_id")
        if isinstance(hub_id, str):
            try:
                self.evaluate_hub_capacity(hub_id)
            except Exception:
                logger.exception(
                    "Failed to evaluate hub capacity on space occupancy change: %s", hub_id
                )

    # ------------------------------------------------------------- Automated Incident Listeners
    def on_charging_point_status_changed(self, event: DomainEvent) -> None:
        """Automatically create INC-HW-01 on charger failure (BR-M5-03, FR-09.1)."""
        new_status = event.payload.get("new")
        if new_status == ChargingPointStatus.OUT_OF_SERVICE.value:
            cp_id = str(event.payload.get("charging_point_id", ""))
            hub_id = str(event.payload.get("hub_id", ""))
            self.create_incident(
                incident_type=IncidentType.CHARGING_POINT_FAILURE,
                severity=IncidentSeverity.CRITICAL,
                hub_id=hub_id,
                entity_type="ChargingPoint",
                entity_id=cp_id,
                error_code="ERR_CHARGER_OUT_OF_SERVICE",
                description=f"Charging point {cp_id} at hub {hub_id} entered OUT_OF_SERVICE state",
                reported_by="SYSTEM_HARDWARE_MONITOR",
            )

    def on_vehicle_battery_changed(self, event: DomainEvent) -> None:
        """Automatically create INC-BAT-01 on critical low battery (BR-M5-05, FR-09.3)."""
        if event.payload.get("low") is True:
            v_id = str(event.payload.get("vehicle_id", ""))
            hub_id = str(event.payload.get("hub_id") or "UNKNOWN")
            battery = event.payload.get("new", 0.0)
            self.create_incident(
                incident_type=IncidentType.BATTERY_CRITICAL_FAULT,
                severity=IncidentSeverity.HIGH,
                hub_id=hub_id,
                entity_type="Vehicle",
                entity_id=v_id,
                error_code="ERR_BATTERY_CRITICAL",
                description=f"Vehicle {v_id} dropped to {battery}% battery SoC (<= 15% threshold)",
                reported_by="SYSTEM_TELEMETRY_MONITOR",
            )

    # ----------------------------------------------------------------- Incident CRUD & Lifecycle
    def create_incident(
        self,
        incident_type: IncidentType,
        severity: IncidentSeverity,
        hub_id: str,
        entity_type: str,
        entity_id: str,
        description: str,
        reported_by: str,
        error_code: str | None = None,
    ) -> IncidentTicket:
        """Create and persist a new incident ticket with audit trail (FR-09.2, NFR-25)."""
        incident_id = f"INC-{uuid4().hex[:8].upper()}"
        now = self._core._clock.now()

        ticket = IncidentTicket(
            incident_id=incident_id,
            incident_type=incident_type,
            severity=severity,
            status=IncidentStatus.OPEN,
            hub_id=hub_id,
            entity_type=entity_type,
            entity_id=entity_id,
            error_code=error_code,
            description=description,
            reported_by=reported_by,
            assigned_operator_id=None,
            resolution_notes=None,
            created_at=now,
            acknowledged_at=None,
            escalated_at=None,
            resolved_at=None,
            closed_at=None,
            version=1,
        )

        log = TicketAuditLog(
            log_id=f"LOG-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            previous_status=IncidentStatus.OPEN,
            new_status=IncidentStatus.OPEN,
            changed_by=reported_by,
            action="CREATE",
            reason="Initial ticket detection",
            timestamp=now,
        )

        with self._core.unit_of_work() as uow:
            uow.repository.add(ticket)
            uow.repository.add(log)
            res = uow.commit()
            if isinstance(res, Err):
                raise RuntimeError(f"Failed to persist incident ticket: {res.message}")

        logger.info(
            "Created incident %s (type=%s, severity=%s)", incident_id, incident_type, severity
        )
        return ticket

    def acknowledge_incident(self, incident_id: str, operator_id: str) -> IncidentTicket:
        """Operator acknowledges and claims an incident ticket (OPEN/ESCALATED -> IN_PROGRESS)."""
        ticket = self._core.get_entity(IncidentTicket, incident_id)
        if ticket is None:
            raise IncidentNotFoundError(f"Incident {incident_id} not found")

        if ticket.status not in (IncidentStatus.OPEN, IncidentStatus.ESCALATED):
            raise InvalidStatusTransitionError(
                f"Cannot acknowledge ticket in status {ticket.status.value}"
            )

        now = self._core._clock.now()
        previous_status = ticket.status
        expected_version = ticket.version

        ticket.status = IncidentStatus.IN_PROGRESS
        ticket.assigned_operator_id = operator_id
        ticket.acknowledged_at = now

        log = TicketAuditLog(
            log_id=f"LOG-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            previous_status=previous_status,
            new_status=IncidentStatus.IN_PROGRESS,
            changed_by=operator_id,
            action="ACKNOWLEDGE",
            reason=f"Claimed by operator {operator_id}",
            timestamp=now,
        )

        with self._core.unit_of_work() as uow:
            uow.repository.update(ticket, expected_version)
            uow.repository.add(log)
            res = uow.commit()
            if isinstance(res, Err):
                raise RuntimeError(f"Failed to update incident: {res.message}")

        return ticket

    def escalate_incident(
        self, incident_id: str, reason: str = "Unacknowledged > 5 minutes"
    ) -> IncidentTicket:
        """Escalate an unacknowledged incident ticket (BR-M5-04: OPEN -> ESCALATED)."""
        ticket = self._core.get_entity(IncidentTicket, incident_id)
        if ticket is None:
            raise IncidentNotFoundError(f"Incident {incident_id} not found")

        if ticket.status is not IncidentStatus.OPEN:
            raise InvalidStatusTransitionError(
                f"Cannot escalate ticket in status {ticket.status.value}"
            )

        now = self._core._clock.now()
        expected_version = ticket.version

        ticket.status = IncidentStatus.ESCALATED
        ticket.escalated_at = now

        log = TicketAuditLog(
            log_id=f"LOG-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            previous_status=IncidentStatus.OPEN,
            new_status=IncidentStatus.ESCALATED,
            changed_by="SYSTEM_ESCALATION_TIMER",
            action="ESCALATE",
            reason=reason,
            timestamp=now,
        )

        with self._core.unit_of_work() as uow:
            uow.repository.update(ticket, expected_version)
            uow.repository.add(log)
            res = uow.commit()
            if isinstance(res, Err):
                raise RuntimeError(f"Failed to escalate incident: {res.message}")

        return ticket

    def resolve_incident(
        self, incident_id: str, resolution_notes: str, operator_id: str
    ) -> IncidentTicket:
        """Mark an incident as resolved with mandatory notes (IN_PROGRESS/ESCALATED -> RESOLVED)."""
        if not resolution_notes.strip():
            raise ValueError("Resolution notes are mandatory to resolve an incident")

        ticket = self._core.get_entity(IncidentTicket, incident_id)
        if ticket is None:
            raise IncidentNotFoundError(f"Incident {incident_id} not found")

        if ticket.status not in (IncidentStatus.IN_PROGRESS, IncidentStatus.ESCALATED):
            raise InvalidStatusTransitionError(
                f"Cannot resolve ticket in status {ticket.status.value}"
            )

        now = self._core._clock.now()
        previous_status = ticket.status
        expected_version = ticket.version

        ticket.status = IncidentStatus.RESOLVED
        ticket.resolution_notes = resolution_notes
        ticket.resolved_at = now

        log = TicketAuditLog(
            log_id=f"LOG-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            previous_status=previous_status,
            new_status=IncidentStatus.RESOLVED,
            changed_by=operator_id,
            action="RESOLVE",
            reason=resolution_notes,
            timestamp=now,
        )

        with self._core.unit_of_work() as uow:
            uow.repository.update(ticket, expected_version)
            uow.repository.add(log)
            res = uow.commit()
            if isinstance(res, Err):
                raise RuntimeError(f"Failed to resolve incident: {res.message}")

        return ticket

    def close_incident(self, incident_id: str, operator_id: str) -> IncidentTicket:
        """Final sign-off and closure of an incident ticket (RESOLVED -> CLOSED)."""
        ticket = self._core.get_entity(IncidentTicket, incident_id)
        if ticket is None:
            raise IncidentNotFoundError(f"Incident {incident_id} not found")

        if ticket.status is not IncidentStatus.RESOLVED:
            raise InvalidStatusTransitionError(
                f"Cannot close ticket in status {ticket.status.value}; "
                "ticket must be RESOLVED first"
            )

        now = self._core._clock.now()
        expected_version = ticket.version

        ticket.status = IncidentStatus.CLOSED
        ticket.closed_at = now

        log = TicketAuditLog(
            log_id=f"LOG-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            previous_status=IncidentStatus.RESOLVED,
            new_status=IncidentStatus.CLOSED,
            changed_by=operator_id,
            action="CLOSE",
            reason="Final operator verification and sign-off",
            timestamp=now,
        )

        with self._core.unit_of_work() as uow:
            uow.repository.update(ticket, expected_version)
            uow.repository.add(log)
            res = uow.commit()
            if isinstance(res, Err):
                raise RuntimeError(f"Failed to close incident: {res.message}")

        return ticket

    def get_incident(self, incident_id: str) -> IncidentTicket | None:
        """Read a single incident ticket by ID."""
        return self._core.get_entity(IncidentTicket, incident_id)

    def list_incidents(
        self,
        hub_id: str | None = None,
        status: IncidentStatus | None = None,
        severity: IncidentSeverity | None = None,
    ) -> list[IncidentTicket]:
        """Query incident tickets filtered by hub, status, or severity."""

        def predicate(t: IncidentTicket) -> bool:
            if hub_id is not None and t.hub_id != hub_id:
                return False
            if status is not None and t.status is not status:
                return False
            return severity is None or t.severity is severity

        return self._core.query_entities(IncidentTicket, predicate)

    def list_audit_logs(self, incident_id: str) -> list[TicketAuditLog]:
        """Read all lifecycle audit log records for an incident (NFR-25)."""
        return self._core.query_entities(
            TicketAuditLog, predicate=lambda log: log.incident_id == incident_id
        )
