"""Unit tests for the monitoring and incident handling module (M5).

Traceability:
- FR-08 (System Monitoring), FR-09 (Incident Handling)
- BR-M5-01 (Capacity Warning Threshold >= 90%)
- BR-M5-02 (Critical Capacity Overflow == 100%)
- BR-M5-03 (Charger Fault Isolation)
- BR-M5-04 (Unacknowledged Escalation > 5 min)
- BR-M5-05 (Low Battery Lockout <= 15%)
- NFR-01, NFR-06, NFR-10, NFR-20, NFR-25
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.actor import Actor
from core.clock import FixedClock
from core.domain.entities import (
    ChargingPoint,
    DomainEvent,
    Hub,
    ParkingSpace,
)
from core.domain.enums import (
    ChargingPointStatus,
    HubStatus,
    Role,
    SpaceStatus,
)
from core.events import EventType
from core.facade import CoreFacade
from core.providers import OpenTripDemand, OpenTrips, ProviderPort, UpcomingBookings
from core.repository.memory import InMemoryRepository
from core.repository.schema import check_spec
from core.result import Ok, Result
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


class StubReservationDemand:
    def __init__(self, trips: tuple[OpenTripDemand, ...] = ()) -> None:
        self._trips = trips

    def upcoming_bookings(self, hub_id: str, horizon: timedelta) -> Result[UpcomingBookings]:
        return Ok(
            UpcomingBookings(
                as_of=datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
                horizon_end=datetime(2026, 11, 8, 12, 0, tzinfo=UTC) + horizon,
                bookings=(),
            )
        )

    def open_trips(self, hub_id: str) -> Result[OpenTrips]:
        return Ok(
            OpenTrips(
                as_of=datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
                trips=self._trips,
            )
        )


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 11, 8, 12, 0, tzinfo=UTC))


@pytest.fixture
def core(clock: FixedClock) -> CoreFacade:
    repo = InMemoryRepository()
    facade = CoreFacade(repository=repo, clock=clock)
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


# ====================================================================================
# TC-M5-001 to TC-M5-007: Incident Taxonomy Verification (All 7 Incident Types)
# ====================================================================================


def test_tc_m5_001_charging_point_failure_incident(core: CoreFacade, service: MonitoringService):
    """TC-M5-001 · ST · Charger failure triggers INC-HW-01 with CRITICAL severity.

    Verifies: FR-09.1, FR-09.2, BR-M5-03, NFR-10.
    """
    _seed_sample_hub(core, hub_id="H01")
    now = core.queries.get_config().as_of

    event = DomainEvent(
        event_id="EVT_CP_FAIL",
        type=EventType.CHARGING_POINT_STATUS_CHANGED,
        at=now,
        payload={
            "charging_point_id": "CP_H01_1",
            "hub_id": "H01",
            "new": ChargingPointStatus.OUT_OF_SERVICE.value,
        },
    )
    service.on_charging_point_status_changed(event)

    incidents = service.list_incidents(hub_id="H01", status=IncidentStatus.OPEN)
    assert len(incidents) == 1
    ticket = incidents[0]
    assert ticket.incident_type == IncidentType.CHARGING_POINT_FAILURE
    assert ticket.severity == IncidentSeverity.CRITICAL
    assert ticket.entity_type == "ChargingPoint"
    assert ticket.entity_id == "CP_H01_1"
    assert ticket.error_code == "ERR_CHARGER_OUT_OF_SERVICE"


def test_tc_m5_002_parking_sensor_fault_incident(core: CoreFacade, service: MonitoringService):
    """TC-M5-002 · ST · Core SensorEventRejected triggers INC-HW-02 with MEDIUM severity.

    Verifies: FR-09.1, FR-09.2, NFR-10.
    """
    _seed_sample_hub(core, hub_id="H01")
    now = core.queries.get_config().as_of

    event = DomainEvent(
        event_id="EVT_REJECT",
        type=EventType.SENSOR_EVENT_REJECTED,
        at=now,
        payload={
            "event_id": "RAW_SENS_99",
            "source": "iot_sim",
            "type": "SPACE_OCCUPIED",
            "entity_id": "SP_H01_1",
            "code": "INVALID_TRANSITION",
            "reason": "sensor sees vehicle in occupied space",
        },
    )
    service.on_sensor_event_rejected(event)

    incidents = service.list_incidents(hub_id="H01", status=IncidentStatus.OPEN)
    assert len(incidents) == 1
    ticket = incidents[0]
    assert ticket.incident_type == IncidentType.PARKING_SENSOR_FAULT
    assert ticket.severity == IncidentSeverity.MEDIUM
    assert ticket.entity_type == "ParkingSpace"
    assert ticket.entity_id == "SP_H01_1"
    assert ticket.error_code == "INVALID_TRANSITION"


def test_tc_m5_003_hub_capacity_full_incident(core: CoreFacade, service: MonitoringService):
    """TC-M5-003 · BVA · Hub reaching 100% capacity triggers INC-CAP-01 with HIGH severity.

    Verifies: FR-08.3, FR-09.1, BR-M5-02, NFR-01.
    """
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=10)

    res = service.evaluate_hub_capacity("H01")
    assert res is not None

    hub = core.queries.get_hub("H01")
    assert hub.value.status is HubStatus.CRITICAL

    incidents = service.list_incidents(hub_id="H01", status=IncidentStatus.OPEN)
    assert len(incidents) == 1
    ticket = incidents[0]
    assert ticket.incident_type == IncidentType.HUB_CAPACITY_FULL
    assert ticket.severity == IncidentSeverity.HIGH
    assert ticket.entity_id == "H01"


def test_tc_m5_004_hub_vehicle_deficit_incident(core: CoreFacade, service: MonitoringService):
    """TC-M5-004 · BVA · Hub rental fleet falling < 2 units triggers INC-CAP-02.

    Verifies: FR-08.2, FR-09.1, NFR-01.
    """
    _seed_sample_hub(core, hub_id="H01")

    # Available vehicles count is 0 (< 2 threshold)
    created = service.check_vehicle_deficits(min_vehicles=2)
    assert len(created) == 1
    ticket = created[0]
    assert ticket.incident_type == IncidentType.HUB_VEHICLE_DEFICIT
    assert ticket.severity == IncidentSeverity.MEDIUM
    assert ticket.entity_id == "H01"
    assert ticket.error_code == "WARN_VEHICLE_DEFICIT"


def test_tc_m5_005_battery_critical_fault_incident(core: CoreFacade, service: MonitoringService):
    """TC-M5-005 · BVA · Battery level <= 15% triggers INC-BAT-01 with HIGH severity.

    Verifies: FR-09.1, FR-09.3, BR-M5-05, NFR-10.
    """
    _seed_sample_hub(core, hub_id="H01")
    now = core.queries.get_config().as_of

    event = DomainEvent(
        event_id="EVT_BAT_LOW",
        type=EventType.VEHICLE_BATTERY_CHANGED,
        at=now,
        payload={
            "vehicle_id": "V_FLEET_01",
            "hub_id": "H01",
            "previous": 18.0,
            "new": 14.5,
            "low": True,
        },
    )
    service.on_vehicle_battery_changed(event)

    incidents = service.list_incidents(hub_id="H01", status=IncidentStatus.OPEN)
    assert len(incidents) == 1
    ticket = incidents[0]
    assert ticket.incident_type == IncidentType.BATTERY_CRITICAL_FAULT
    assert ticket.severity == IncidentSeverity.HIGH
    assert ticket.entity_id == "V_FLEET_01"
    assert ticket.error_code == "ERR_BATTERY_CRITICAL"


def test_tc_m5_006_telemetry_connection_loss_incident(
    core: CoreFacade, service: MonitoringService, clock: FixedClock
):
    """TC-M5-006 · TIM · Loss of heartbeat > 30s triggers INC-COMM-01 with CRITICAL severity.

    Verifies: FR-09.1, FR-09.2, NFR-10, NFR-25.
    """
    _seed_sample_hub(core, hub_id="H01")
    t0 = clock.now()

    # Receive initial heartbeat for H01
    service.on_sensor_heartbeat(
        DomainEvent(
            event_id="EVT_HB_1",
            type=EventType.SENSOR_HEARTBEAT,
            at=t0,
            payload={
                "source": "gateway_h01",
                "entity_id": "H01",
                "sent_at": t0.isoformat(),
                "received_at": t0.isoformat(),
            },
        )
    )

    # Within 20s: no timeout incident
    clock.advance(timedelta(seconds=20))
    timed_out = service.check_heartbeat_timeouts(timeout_seconds=30.0)
    assert len(timed_out) == 0

    # Advance clock past 30s threshold (to 35s total)
    clock.advance(timedelta(seconds=15))

    # A subsequent heartbeat from another device runs periodic checks and catches H01 timeout
    service.on_sensor_heartbeat(
        DomainEvent(
            event_id="EVT_HB_2",
            type=EventType.SENSOR_HEARTBEAT,
            at=clock.now(),
            payload={
                "source": "gateway_sp1",
                "entity_id": "SP_H01_1",
                "sent_at": clock.now().isoformat(),
                "received_at": clock.now().isoformat(),
            },
        )
    )

    incidents = service.list_incidents(hub_id="H01", status=IncidentStatus.OPEN)
    comm_tickets = [
        i for i in incidents if i.incident_type == IncidentType.TELEMETRY_CONNECTION_LOSS
    ]
    assert len(comm_tickets) == 1
    ticket = comm_tickets[0]
    assert ticket.severity == IncidentSeverity.CRITICAL
    assert ticket.entity_id == "H01"
    assert ticket.error_code == "ERR_TELEMETRY_TIMEOUT"


def test_tc_m5_007_overdue_vehicle_incident(
    core: CoreFacade, service: MonitoringService, clock: FixedClock
):
    """TC-M5-007 · TIM · Overdue trip read via ReservationDemand port triggers INC-USR-01.

    Verifies: FR-09.1, FR-09.2.
    """
    _seed_sample_hub(core, hub_id="H01")
    t0 = clock.now()

    # 1. When ReservationDemand is not registered, returns empty list without error
    assert service.check_overdue_vehicles() == []

    # 2. Register mock provider with an overdue trip
    trip = OpenTripDemand(
        trip_id="TRIP_OVERDUE_1",
        reservation_id="RES_001",
        vehicle_id="V_OVERDUE",
        origin_hub_id="H01",
        destination_hub_id="H01",
        picked_up_at=t0 - timedelta(hours=3),
        expected_return_at=t0 - timedelta(hours=2),
        is_overdue=True,
    )
    core.register_provider(
        ProviderPort.RESERVATION_DEMAND,
        StubReservationDemand(trips=(trip,)),
    )

    overdue_tickets = service.check_overdue_vehicles()
    assert len(overdue_tickets) == 1
    ticket = overdue_tickets[0]
    assert ticket.incident_type == IncidentType.OVERDUE_VEHICLE
    assert ticket.severity == IncidentSeverity.LOW
    assert ticket.entity_id == "V_OVERDUE"
    assert ticket.hub_id == "H01"
    assert ticket.error_code == "WARN_RENTAL_OVERDUE"


# ====================================================================================
# TC-M5-008 to TC-M5-011: Escalation Rules, Deduplication and Lifecycle
# ====================================================================================


def test_tc_m5_008_unacknowledged_escalation_rule(
    core: CoreFacade, service: MonitoringService, clock: FixedClock
):
    """TC-M5-008 · TIM · Unacknowledged HIGH/CRITICAL ticket auto-escalates after 5 minutes.

    Verifies: BR-M5-04, FR-09.4, NFR-25.
    """
    _seed_sample_hub(core, hub_id="H01")

    # 1. Create a CRITICAL ticket and a LOW ticket
    critical_ticket = service.create_incident(
        incident_type=IncidentType.CHARGING_POINT_FAILURE,
        severity=IncidentSeverity.CRITICAL,
        hub_id="H01",
        entity_type="ChargingPoint",
        entity_id="CP_01",
        description="High voltage relay fault",
        reported_by="SYSTEM",
    )
    low_ticket = service.create_incident(
        incident_type=IncidentType.OVERDUE_VEHICLE,
        severity=IncidentSeverity.LOW,
        hub_id="H01",
        entity_type="Vehicle",
        entity_id="V_01",
        description="Overdue vehicle notice",
        reported_by="SYSTEM",
    )

    # Within 4 minutes: neither escalates
    clock.advance(timedelta(minutes=4))
    escalated = service.check_and_escalate_unacknowledged(timeout_seconds=300.0)
    assert len(escalated) == 0

    # Past 5 minutes (advance 2 more minutes): CRITICAL escalates, LOW does not
    clock.advance(timedelta(minutes=2))
    escalated = service.check_and_escalate_unacknowledged(timeout_seconds=300.0)
    assert len(escalated) == 1
    assert escalated[0].incident_id == critical_ticket.incident_id
    assert escalated[0].status == IncidentStatus.ESCALATED

    # Verify LOW ticket remains OPEN
    re_low = service.get_incident(low_ticket.incident_id)
    assert re_low is not None and re_low.status == IncidentStatus.OPEN

    # Verify audit log recorded escalation
    logs = service.list_audit_logs(critical_ticket.incident_id)
    assert any(log.action == "ESCALATE" for log in logs)


def test_tc_m5_009_incident_deduplication(core: CoreFacade, service: MonitoringService):
    """TC-M5-009 · ISO · Duplicate events in OPEN, IN_PROGRESS or ESCALATED do not duplicate.

    Verifies: FR-09.1, NFR-10.
    """
    _seed_sample_hub(core, hub_id="H01")
    now = core.queries.get_config().as_of

    evt = DomainEvent(
        event_id="EVT_1",
        type=EventType.CHARGING_POINT_STATUS_CHANGED,
        at=now,
        payload={
            "charging_point_id": "CP_H01_1",
            "hub_id": "H01",
            "new": ChargingPointStatus.OUT_OF_SERVICE.value,
        },
    )

    # 1. Dedup on OPEN status
    service.on_charging_point_status_changed(evt)
    service.on_charging_point_status_changed(evt)
    incidents = service.list_incidents(hub_id="H01")
    assert len(incidents) == 1
    t = incidents[0]
    assert t.status == IncidentStatus.OPEN

    # 2. Dedup on IN_PROGRESS status
    service.acknowledge_incident(t.incident_id, "op_viet")
    service.on_charging_point_status_changed(evt)
    assert len(service.list_incidents(hub_id="H01")) == 1

    # 3. Dedup on ESCALATED status
    t2 = service.create_incident(
        incident_type=IncidentType.BATTERY_CRITICAL_FAULT,
        severity=IncidentSeverity.HIGH,
        hub_id="H01",
        entity_type="Vehicle",
        entity_id="V_BAT_ESC",
        description="Low battery",
        reported_by="SYSTEM",
    )
    service.escalate_incident(t2.incident_id, reason="Unacknowledged")
    bat_evt = DomainEvent(
        event_id="EVT_BAT_ESC",
        type=EventType.VEHICLE_BATTERY_CHANGED,
        at=now,
        payload={
            "vehicle_id": "V_BAT_ESC",
            "hub_id": "H01",
            "new": 10.0,
            "low": True,
        },
    )
    service.on_vehicle_battery_changed(bat_evt)
    assert len(service.list_incidents(hub_id="H01")) == 2


def test_tc_m5_010_incident_full_lifecycle(core: CoreFacade, service: MonitoringService):
    """TC-M5-010 · ST · Complete lifecycle: OPEN -> IN_PROGRESS -> RESOLVED -> CLOSED.

    Verifies: FR-09.4, NFR-25.
    """
    _seed_sample_hub(core, hub_id="H01")

    ticket = service.create_incident(
        incident_type=IncidentType.CHARGING_POINT_FAILURE,
        severity=IncidentSeverity.CRITICAL,
        hub_id="H01",
        entity_type="ChargingPoint",
        entity_id="CP_01",
        description="Power failure",
        reported_by="SYSTEM",
    )
    assert ticket.status == IncidentStatus.OPEN

    # Acknowledge
    ack = service.acknowledge_incident(ticket.incident_id, "op_viet")
    assert ack.status == IncidentStatus.IN_PROGRESS
    assert ack.assigned_operator_id == "op_viet"

    # Resolve
    res = service.resolve_incident(ticket.incident_id, "Replaced fuse", "op_viet")
    assert res.status == IncidentStatus.RESOLVED

    # Close
    closed = service.close_incident(ticket.incident_id, "op_viet")
    assert closed.status == IncidentStatus.CLOSED

    # Verify audit logs
    logs = service.list_audit_logs(ticket.incident_id)
    assert len(logs) == 4
    assert [log.action for log in logs] == ["CREATE", "ACKNOWLEDGE", "RESOLVE", "CLOSE"]


def test_tc_m5_011_invalid_incident_transitions(core: CoreFacade, service: MonitoringService):
    """TC-M5-011 · NEG · Illegal lifecycle transitions and empty resolution notes are rejected.

    Verifies: FR-09.4, NFR-18.
    """
    _seed_sample_hub(core, hub_id="H01")

    ticket = service.create_incident(
        incident_type=IncidentType.OVERDUE_VEHICLE,
        severity=IncidentSeverity.LOW,
        hub_id="H01",
        entity_type="Vehicle",
        entity_id="V_01",
        description="Rental overdue",
        reported_by="SYSTEM",
    )

    # Cannot close directly from OPEN
    with pytest.raises(InvalidStatusTransitionError):
        service.close_incident(ticket.incident_id, "op_viet")

    # Cannot resolve with empty notes
    with pytest.raises(ValueError):
        service.resolve_incident(ticket.incident_id, "   ", "op_viet")

    # Unknown incident raises IncidentNotFoundError
    with pytest.raises(IncidentNotFoundError):
        service.acknowledge_incident("NON_EXISTENT_ID", "op_viet")


# ====================================================================================
# TC-M5-012 to TC-M5-020: Metrics, Capacity Alerting, API, Installation, Fallback
# ====================================================================================


def test_tc_m5_012_hub_metrics_aggregation(core: CoreFacade, service: MonitoringService):
    """TC-M5-012 · CALC · Utilization percentages are calculated correctly.

    Verifies: FR-08.1, FR-08.2.
    """
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


def test_tc_m5_013_capacity_warning_threshold(core: CoreFacade, service: MonitoringService):
    """TC-M5-013 · BVA · Hub occupancy >= 90% sets Hub status to WARNING.

    Verifies: FR-08.3, FR-08.4, BR-M5-01, NFR-01.
    """
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=9)

    res = service.evaluate_hub_capacity("H01")
    assert res is not None

    hub = core.queries.get_hub("H01")
    assert hub.value.status is HubStatus.WARNING


def test_tc_m5_014_capacity_alert_recovery(core: CoreFacade, service: MonitoringService):
    """TC-M5-014 · ST · Hub drops below 90% occupancy returns Hub status to ACTIVE.

    Verifies: FR-08.4, BR-M5-01.
    """
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=9)

    # Set to WARNING
    service.evaluate_hub_capacity("H01")
    assert core.queries.get_hub("H01").value.status is HubStatus.WARNING

    # Space freed: update space in repo
    with core.unit_of_work() as uow:
        sp = uow.repository.get(ParkingSpace, "SP_H01_9")
        assert sp is not None
        sp.status = SpaceStatus.AVAILABLE
        sp.occupant_vehicle_id = None
        uow.repository.update(sp, sp.version)
        uow.commit()

    service.evaluate_hub_capacity("H01")
    assert core.queries.get_hub("H01").value.status is HubStatus.ACTIVE


def test_tc_m5_015_router_endpoints_crud(core: CoreFacade, service: MonitoringService):
    """TC-M5-015 · API · Direct router endpoints invocation and CRUD lifecycle.

    Verifies: FR-08, FR-09, D-014.
    """
    from fastapi import HTTPException

    from core.auth import Principal
    from monitoring.router import (
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

    who = Principal(user_id="op_test", role=Role.OPERATOR, module="ui")
    set_service(service)
    _seed_sample_hub(core, hub_id="H01", capacity=10, occupied=5)

    # 1. Metrics
    metrics_list = list_hub_metrics(who=who)
    assert len(metrics_list) == 1
    assert metrics_list[0].hub_id == "H01"

    h_metric = get_hub_metrics(hub_id="H01", who=who)
    assert h_metric.hub_id == "H01"
    with pytest.raises(HTTPException):
        get_hub_metrics(hub_id="UNKNOWN", who=who)

    # 2. Evaluate capacity
    eval_res = evaluate_hub_capacity(hub_id="H01", who=who)
    assert "status" in eval_res

    # 3. Create incident
    body = CreateIncidentRequest(
        incident_type=IncidentType.HUB_VEHICLE_DEFICIT,
        severity=IncidentSeverity.MEDIUM,
        hub_id="H01",
        entity_type="Hub",
        entity_id="H01",
        description="Vehicle deficit alert",
    )
    ticket = create_incident(body=body, who=who)
    inc_id = ticket.incident_id
    assert ticket.status == IncidentStatus.OPEN

    # 4. List and get incident
    inc_list = list_incidents(who=who, hub_id="H01", status_filter=IncidentStatus.OPEN)
    assert len(inc_list) == 1
    fetched = get_incident(incident_id=inc_id, who=who)
    assert fetched.incident_id == inc_id

    # 5. Acknowledge
    ack = acknowledge_incident(incident_id=inc_id, who=who)
    assert ack.status == IncidentStatus.IN_PROGRESS

    # 6. Escalate from IN_PROGRESS is invalid
    with pytest.raises(HTTPException):
        escalate_incident(incident_id=inc_id, body=EscalateRequest(reason="late"), who=who)

    # 7. Resolve & Close
    resolved = resolve_incident(
        incident_id=inc_id, body=ResolveRequest(resolution_notes="Dispatched fleet"), who=who
    )
    assert resolved.status == IncidentStatus.RESOLVED

    closed = close_incident(incident_id=inc_id, who=who)
    assert closed.status == IncidentStatus.CLOSED

    # 8. Audit logs
    logs = get_incident_audit_logs(incident_id=inc_id, who=who)
    assert len(logs) == 4


def test_tc_m5_016_module_install():
    """TC-M5-016 · INT · Module installation registers schemas, event listeners and routes.

    Verifies: D-013, D-018.
    """
    from fastapi import FastAPI

    from core.clock import SystemClock
    from core.facade import CoreFacade
    from core.repository.memory import InMemoryRepository
    from monitoring import install

    fresh_core = CoreFacade(InMemoryRepository(), clock=SystemClock())
    app = FastAPI()
    install(fresh_core, app)

    check_spec(INCIDENT_SPEC)
    check_spec(AUDIT_SPEC)
    assert fresh_core.query_entities(IncidentTicket) == []
    assert any(getattr(r, "original_router", None) is not None for r in app.routes)


def test_tc_m5_020_unmapped_entity_skips_incident_creation(
    core: CoreFacade, service: MonitoringService
):
    """TC-M5-020 · NEG · Sensor event for unresolvable Hub entity logs warning and skips ticket.

    Verifies: FR-09.1, NFR-18.
    """
    _seed_sample_hub(core, hub_id="H01")
    now = core.queries.get_config().as_of

    event = DomainEvent(
        event_id="EVT_GHOST",
        type=EventType.SENSOR_EVENT_REJECTED,
        at=now,
        payload={
            "event_id": "RAW_GHOST_1",
            "source": "iot_sim",
            "type": "UNKNOWN_SIGNAL",
            "entity_id": "NON_EXISTENT_DEVICE_999",
            "code": "INVALID_INPUT",
            "reason": "Ghost sensor signal",
        },
    )
    service.on_sensor_event_rejected(event)
    assert len(service.list_incidents()) == 0
