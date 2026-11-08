"""Unit tests for the monitoring module (M5).

Traceability:
- FR-08, FR-09
- BR-M5-01, BR-M5-02, BR-M5-03, BR-M5-04, BR-M5-05
- NFR-01, NFR-06, NFR-10, NFR-20, NFR-25
"""

import pytest

from core.actor import Actor
from core.clock import SystemClock
from core.domain.entities import ChargingPoint, DomainEvent, Hub, ParkingSpace
from core.domain.enums import ChargingPointStatus, HubStatus, Role, SpaceStatus
from core.events import EventType
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.repository.schema import check_spec
from monitoring.domain import (
    IncidentSeverity,
    IncidentStatus,
    IncidentTicket,
    IncidentType,
)
from monitoring.schema import AUDIT_SPEC, INCIDENT_SPEC
from monitoring.service import (
    IncidentNotFoundError,
    InvalidStatusTransitionError,
    MonitoringService,
)

OPERATOR_ACTOR = Actor(user_id="op_viet", role=Role.OPERATOR, module="monitoring")


@pytest.fixture
def core() -> CoreFacade:
    repo = InMemoryRepository()
    clock = SystemClock()
    facade = CoreFacade(repository=repo, clock=clock)
    # Register M5 tables
    facade.register_entity(INCIDENT_SPEC)
    facade.register_entity(AUDIT_SPEC)
    return facade


@pytest.fixture
def service(core: CoreFacade) -> MonitoringService:
    return MonitoringService(core)


def _seed_sample_hub(
    core: CoreFacade, hub_id: str = "H01", capacity: int = 10, occupied: int = 0
) -> Hub:
    hub = Hub(
        hub_id=hub_id,
        name="Test Hub",
        zone_code="ZONE_A",
        parking_capacity=capacity,
        charging_point_count=4,
        status=HubStatus.ACTIVE,
        version=1,
    )
    with core.unit_of_work() as uow:
        uow.repository.add(hub)
        for i in range(capacity):
            sp_status = SpaceStatus.OCCUPIED if i < occupied else SpaceStatus.AVAILABLE
            space = ParkingSpace(
                parking_space_id=f"SP_{hub_id}_{i + 1}",
                hub_id=hub_id,
                label=f"P{i + 1}",
                status=sp_status,
                occupant_vehicle_id=f"V{i + 1}" if i < occupied else None,
                version=1,
            )
            uow.repository.add(space)
            if i < 4:
                cp_status = ChargingPointStatus.CHARGING if i < 2 else ChargingPointStatus.AVAILABLE
                cp = ChargingPoint(
                    charging_point_id=f"CP_{hub_id}_{i + 1}",
                    hub_id=hub_id,
                    parking_space_id=space.parking_space_id,
                    power_rate_kw=22.0,
                    status=cp_status,
                    version=1,
                )
                uow.repository.add(cp)
        uow.commit()
    return hub


def test_schema_spec_compliance():
    """Verify TableSpecs strictly adhere to core requirements (check_spec)."""
    check_spec(INCIDENT_SPEC)
    check_spec(AUDIT_SPEC)


def test_hub_metrics_aggregation(core: CoreFacade, service: MonitoringService):
    """Test FR-08.1, FR-08.2: compute accurate utilization percentages."""
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=3)

    metrics = service.get_hub_metrics("H01")
    assert metrics is not None
    assert metrics.hub_id == "H01"
    assert metrics.parking_capacity == 10
    assert metrics.occupied_parking_spaces == 3
    assert metrics.free_parking_spaces == 7
    assert metrics.parking_occupancy_pct == 30.0
    assert metrics.charging_point_count == 4
    assert metrics.charging_points_in_use == 2
    assert metrics.charging_utilization_pct == 50.0

    network = service.get_network_metrics()
    assert len(network) == 1
    assert network[0].hub_id == "H01"


def test_capacity_alert_warning_threshold(core: CoreFacade, service: MonitoringService):
    """Test BR-M5-01: occupancy >= 90% triggers WARNING status."""
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=9)

    res = service.evaluate_hub_capacity("H01")
    assert res is not None

    hub = core.queries.get_hub("H01")
    assert not isinstance(hub, type(None))
    assert hub.value.status is HubStatus.WARNING


def test_capacity_alert_critical_overflow_creates_incident(
    core: CoreFacade, service: MonitoringService
):
    """Test BR-M5-02: occupancy == 100% triggers CRITICAL status and INC-CAP-01 ticket."""
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=10)

    res = service.evaluate_hub_capacity("H01")
    assert res is not None

    hub = core.queries.get_hub("H01")
    assert not isinstance(hub, type(None))
    assert hub.value.status is HubStatus.CRITICAL

    incidents = service.list_incidents(hub_id="H01", status=IncidentStatus.OPEN)
    assert len(incidents) == 1
    assert incidents[0].incident_type == IncidentType.HUB_CAPACITY_FULL
    assert incidents[0].severity == IncidentSeverity.HIGH


def test_capacity_alert_recovery(core: CoreFacade, service: MonitoringService):
    """Test recovery from WARNING to ACTIVE when occupancy drops below 90%."""
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=9)
    service.evaluate_hub_capacity("H01")

    # Free up spaces in core
    with core.unit_of_work() as uow:
        for i in range(5):
            sp = uow.repository.get(ParkingSpace, f"SP_H01_{i + 1}")
            assert sp is not None
            sp.status = SpaceStatus.AVAILABLE
            sp.occupant_vehicle_id = None
            uow.repository.update(sp, sp.version)
        uow.commit()

    service.evaluate_hub_capacity("H01")
    hub = core.queries.get_hub("H01")
    assert not isinstance(hub, type(None))
    assert hub.value.status is HubStatus.ACTIVE


def test_incident_full_lifecycle(core: CoreFacade, service: MonitoringService):
    """Test FR-09.2, FR-09.4, NFR-25: ticket creation, acknowledge,
    resolve, close with audit trail.
    """
    ticket = service.create_incident(
        incident_type=IncidentType.PARKING_SENSOR_FAULT,
        severity=IncidentSeverity.MEDIUM,
        hub_id="H01",
        entity_type="Sensor",
        entity_id="SENSOR_01",
        description="Sensor heartbeat missed",
        reported_by="SYSTEM",
    )
    assert ticket.status == IncidentStatus.OPEN
    assert ticket.version == 1

    # Audit log check
    logs = service.list_audit_logs(ticket.incident_id)
    assert len(logs) == 1
    assert logs[0].action == "CREATE"

    # Acknowledge
    ack_ticket = service.acknowledge_incident(ticket.incident_id, "op_viet")
    assert ack_ticket.status == IncidentStatus.IN_PROGRESS
    assert ack_ticket.assigned_operator_id == "op_viet"
    assert ack_ticket.acknowledged_at is not None

    # Resolve
    res_ticket = service.resolve_incident(ticket.incident_id, "Replaced battery", "op_viet")
    assert res_ticket.status == IncidentStatus.RESOLVED
    assert res_ticket.resolution_notes == "Replaced battery"
    assert res_ticket.resolved_at is not None

    # Close
    closed_ticket = service.close_incident(ticket.incident_id, "op_viet")
    assert closed_ticket.status == IncidentStatus.CLOSED
    assert closed_ticket.closed_at is not None

    # All logs (sort by timestamp to check chronological sequence)
    all_logs = service.list_audit_logs(ticket.incident_id)
    assert len(all_logs) == 4
    all_logs.sort(key=lambda log: log.timestamp)
    assert [log.action for log in all_logs] == ["CREATE", "ACKNOWLEDGE", "RESOLVE", "CLOSE"]


def test_incident_escalation(core: CoreFacade, service: MonitoringService):
    """Test BR-M5-04: unacknowledged escalation (OPEN -> ESCALATED -> IN_PROGRESS)."""
    ticket = service.create_incident(
        incident_type=IncidentType.CHARGING_POINT_FAILURE,
        severity=IncidentSeverity.CRITICAL,
        hub_id="H01",
        entity_type="ChargingPoint",
        entity_id="CP_01",
        description="Power failure",
        reported_by="SYSTEM",
    )

    esc_ticket = service.escalate_incident(ticket.incident_id)
    assert esc_ticket.status == IncidentStatus.ESCALATED
    assert esc_ticket.escalated_at is not None

    # Escalated ticket can still be claimed by an operator
    ack_ticket = service.acknowledge_incident(ticket.incident_id, "op_viet")
    assert ack_ticket.status == IncidentStatus.IN_PROGRESS


def test_invalid_incident_transitions(core: CoreFacade, service: MonitoringService):
    """Test error handling for illegal lifecycle transitions."""
    ticket = service.create_incident(
        incident_type=IncidentType.OVERDUE_VEHICLE,
        severity=IncidentSeverity.LOW,
        hub_id="H01",
        entity_type="Vehicle",
        entity_id="V01",
        description="Rental overdue",
        reported_by="SYSTEM",
    )

    # Cannot close directly from OPEN
    with pytest.raises(InvalidStatusTransitionError):
        service.close_incident(ticket.incident_id, "op_viet")

    # Cannot resolve without notes
    with pytest.raises(ValueError):
        service.resolve_incident(ticket.incident_id, "   ", "op_viet")

    # Not found check
    with pytest.raises(IncidentNotFoundError):
        service.acknowledge_incident("NON_EXISTENT", "op_viet")


def test_automated_hardware_and_battery_event_handlers(
    core: CoreFacade, service: MonitoringService
):
    """Test BR-M5-03, BR-M5-05: automated incident creation on domain events."""
    now = core._clock.now()

    # 1. Charger out of service event
    charger_event = DomainEvent(
        event_id="EVT_1",
        type=EventType.CHARGING_POINT_STATUS_CHANGED,
        at=now,
        payload={
            "charging_point_id": "CP_01",
            "hub_id": "H01",
            "new": ChargingPointStatus.OUT_OF_SERVICE.value,
        },
    )
    service.on_charging_point_status_changed(charger_event)

    incidents = service.list_incidents(hub_id="H01")
    assert len(incidents) == 1
    assert incidents[0].incident_type == IncidentType.CHARGING_POINT_FAILURE
    assert incidents[0].severity == IncidentSeverity.CRITICAL

    # 2. Battery critical event
    battery_event = DomainEvent(
        event_id="EVT_2",
        type=EventType.VEHICLE_BATTERY_CHANGED,
        at=now,
        payload={"vehicle_id": "V_LOW", "hub_id": "H01", "low": True, "new": 12.0},
    )
    service.on_vehicle_battery_changed(battery_event)

    all_incidents = service.list_incidents(hub_id="H01")
    assert len(all_incidents) == 2
    types = {i.incident_type for i in all_incidents}
    assert IncidentType.BATTERY_CRITICAL_FAULT in types


def test_api_endpoints(core: CoreFacade, service: MonitoringService):
    """Test router endpoints for monitoring module directly."""
    from fastapi import HTTPException

    from monitoring.router import (
        AcknowledgeRequest,
        CloseRequest,
        CreateIncidentRequest,
        EscalateRequest,
        ResolveRequest,
        acknowledge_incident,
        close_incident,
        create_incident,
        escalate_incident,
        evaluate_hub_capacity,
        get_hub_metrics,
        get_incident,
        get_incident_audit_logs,
        list_hub_metrics,
        list_incidents,
        resolve_incident,
        set_service,
    )

    set_service(service)
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=5)

    # 1. GET /metrics/hubs
    metrics_list = list_hub_metrics()
    assert len(metrics_list) == 1
    assert metrics_list[0].hub_id == "H01"
    assert metrics_list[0].parking_occupancy_pct == 50.0

    # 2. GET /metrics/hubs/{id}
    h_metric = get_hub_metrics("H01")
    assert h_metric.hub_id == "H01"
    with pytest.raises(HTTPException) as exc_info:
        get_hub_metrics("UNKNOWN")
    assert exc_info.value.status_code == 404

    # 3. POST /hubs/{id}/evaluate-capacity
    eval_res = evaluate_hub_capacity("H01")
    assert "status" in eval_res

    # 4. POST /incidents
    create_body = CreateIncidentRequest(
        incident_type=IncidentType.HUB_VEHICLE_DEFICIT,
        severity=IncidentSeverity.MEDIUM,
        hub_id="H01",
        entity_type="Hub",
        entity_id="H01",
        description="Deficit warning",
        reported_by="OPERATOR",
    )
    ticket = create_incident(create_body)
    inc_id = ticket.incident_id
    assert ticket.status == IncidentStatus.OPEN

    # 5. GET /incidents & GET /incidents/{id}
    inc_list = list_incidents(hub_id="H01", status_filter=IncidentStatus.OPEN, severity_filter=None)
    assert len(inc_list) == 1
    fetched = get_incident(inc_id)
    assert fetched.incident_id == inc_id
    with pytest.raises(HTTPException):
        get_incident("NON_EXISTENT")

    # 6. POST /incidents/{id}/acknowledge
    ack_res = acknowledge_incident(inc_id, AcknowledgeRequest(operator_id="op_test"))
    assert ack_res.status == IncidentStatus.IN_PROGRESS

    # 7. POST /incidents/{id}/escalate (from IN_PROGRESS invalid transition test)
    with pytest.raises(HTTPException) as exc_esc:
        escalate_incident(inc_id, EscalateRequest(reason="late"))
    assert exc_esc.value.status_code == 400

    # 8. POST /incidents/{id}/resolve
    res_ticket = resolve_incident(
        inc_id,
        ResolveRequest(resolution_notes="Dispatched fleet", operator_id="op_test"),
    )
    assert res_ticket.status == IncidentStatus.RESOLVED

    # 9. POST /incidents/{id}/close
    closed_ticket = close_incident(inc_id, CloseRequest(operator_id="op_test"))
    assert closed_ticket.status == IncidentStatus.CLOSED

    # 10. GET /incidents/{id}/logs
    logs = get_incident_audit_logs(inc_id)
    assert len(logs) == 4


def test_module_install():
    """Test module lifecycle installation (D-013, D-018)."""
    from fastapi import FastAPI

    from core.clock import SystemClock
    from core.facade import CoreFacade
    from core.repository.memory import InMemoryRepository
    from monitoring import install

    fresh_core = CoreFacade(InMemoryRepository(), clock=SystemClock())
    app = FastAPI()
    install(fresh_core, app)

    # Check tables registered and queryable
    assert fresh_core.query_entities(IncidentTicket) == []

    # Check routes included
    assert any(getattr(r, "original_router", None) is not None for r in app.routes)
