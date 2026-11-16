"""Sample data shown by the Phase 2 prototype. Nothing here is read from or written to ``core``.

Core data uses core's own view types (``HubView``, ``VehicleView``, ``SpaceView``,
``ChargingPointView``), so Phase 3 can replace each list with the matching ``core.queries`` call
and keep the templates. IDs follow the formats of ``core.seed`` and ``iot_sim``: Hubs ``H01``,
fleet vehicles ``F-0001``, private vehicles ``P-001``, spaces ``H01-S001``, charging points
``H01-CP01``, students ``U-0001``, operators ``OP-01``. Hub names and sizes are those of
``docs/requirements/reference-dataset.md``, section 3.

The other modules' records cannot be imported (D-019), so they are small dataclasses below. Their
field names and status values are copied from the module code, which is not merged yet:
M2 ``origin/feat/reservation-booking-flow`` (``src/reservation/models.py``), M4
``origin/feat/allocation-phase2`` (``src/allocation/models.py``), M5
``origin/feat/monitoring-incident`` (``src/monitoring/domain.py``), M6
``origin/feat/m6-simulation-impl`` (``src/simulation/models.py``).

Hub totals (``occupied``, ``charging_in_use``) are sample numbers; the lists of vehicles, spaces
and charging points are a few rows only, so they do not add up to those totals.
``available_vehicles`` does match the rentable vehicles listed for each Hub, so S2 and S3 agree.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core.domain.enums import (
    ChargingPointStatus,
    HubStatus,
    Ownership,
    SpaceStatus,
    VehicleState,
    VehicleType,
)
from core.views import ChargingPointView, HubView, SpaceView, VehicleView

AS_OF = datetime(2026, 11, 9, 3, 42, 5, tzinfo=UTC)  # 10:42:05 ICT, the time in the wireframes
STUDENT_ID = "U-0001"
OPERATOR_ID = "OP-01"

# --------------------------------------------------------------------------------------- core


def _hub(
    hub_id: str,
    name: str,
    zone_code: str,
    capacity: int,
    occupied: int,
    points: int,
    points_in_use: int,
    available_vehicles: int,
    status: HubStatus,
) -> HubView:
    return HubView(
        hub_id=hub_id,
        name=name,
        zone_code=zone_code,
        parking_capacity=capacity,
        occupied=occupied,
        free_spaces=capacity - occupied,
        charging_points=points,
        charging_in_use=points_in_use,
        available_vehicles=available_vehicles,
        status=status,
        version=1,
        as_of=AS_OF,
    )


# One Hub for each status word of S2. M5 sets WARNING at 90% and CRITICAL at 100% parking use.
HUBS: list[HubView] = [
    _hub("H01", "Metro", "METRO", 70, 40, 10, 3, 4, HubStatus.ACTIVE),
    _hub("H02", "Dorm A", "DORM", 60, 55, 10, 9, 2, HubStatus.WARNING),
    _hub("H03", "Dorm B", "DORM", 50, 50, 8, 8, 0, HubStatus.CRITICAL),
    _hub("H04", "Dorm C", "DORM", 40, 20, 6, 0, 0, HubStatus.MAINTENANCE),
    _hub("H05", "Campus A", "CAMPUS", 50, 30, 8, 2, 2, HubStatus.ACTIVE),
]


def _fleet(
    number: int,
    vehicle_type: VehicleType,
    battery_pct: float,
    state: VehicleState,
    space_id: str,
    fault_flag: bool = False,
) -> VehicleView:
    return VehicleView(
        vehicle_id=f"F-{number:04d}",
        plate_or_code=f"FLEET-{number:04d}",
        ownership=Ownership.FLEET,
        vehicle_type=vehicle_type,
        battery_pct=battery_pct,
        state=state,
        fault_flag=fault_flag,
        hub_id=space_id.split("-")[0],
        parking_space_id=space_id,
        owner_user_id=None,
        connector_type=None,
        version=1,
    )


VEHICLES: list[VehicleView] = [
    _fleet(1, VehicleType.E_BIKE, 96.0, VehicleState.AVAILABLE, "H01-S011"),
    _fleet(2, VehicleType.E_SCOOTER, 81.0, VehicleState.AVAILABLE, "H01-S012"),
    _fleet(3, VehicleType.E_MOTORCYCLE, 63.0, VehicleState.AVAILABLE, "H01-S013"),
    _fleet(4, VehicleType.E_BIKE, 22.0, VehicleState.AVAILABLE, "H01-S014"),
    _fleet(5, VehicleType.E_SCOOTER, 54.0, VehicleState.CHARGING, "H01-S001"),
    _fleet(6, VehicleType.E_BIKE, 70.0, VehicleState.RESERVED, "H01-S015"),
    _fleet(51, VehicleType.E_BIKE, 88.0, VehicleState.AVAILABLE, "H02-S011"),
    _fleet(52, VehicleType.E_SCOOTER, 54.0, VehicleState.CHARGING, "H02-S001"),
    _fleet(53, VehicleType.E_MOTORCYCLE, 63.0, VehicleState.MAINTENANCE, "H02-S020", True),
    _fleet(54, VehicleType.E_BIKE, 91.0, VehicleState.AVAILABLE, "H02-S012"),
    _fleet(141, VehicleType.E_BIKE, 77.0, VehicleState.AVAILABLE, "H05-S009"),
    _fleet(142, VehicleType.E_SCOOTER, 45.0, VehicleState.AVAILABLE, "H05-S010"),
    # A private EV parked at H02: an operator sees it in O2, a student never does in S3.
    VehicleView(
        vehicle_id="P-001",
        plate_or_code="PRIVATE-001",
        ownership=Ownership.PRIVATE,
        vehicle_type=VehicleType.E_SCOOTER,
        battery_pct=70.0,
        state=VehicleState.AVAILABLE,
        fault_flag=False,
        hub_id="H02",
        parking_space_id="H02-S014",
        owner_user_id="U-0001",
        connector_type="TYPE2",
        version=1,
    ),
]


def _space(space_id: str, occupant_vehicle_id: str | None = None) -> SpaceView:
    hub_id, label = space_id.split("-")
    return SpaceView(
        parking_space_id=space_id,
        hub_id=hub_id,
        label=label,
        status=SpaceStatus.OCCUPIED if occupant_vehicle_id else SpaceStatus.AVAILABLE,
        occupant_vehicle_id=occupant_vehicle_id,
        version=1,
    )


# Spaces 1 to N of a Hub are its charging bays (core.seed); fleet vehicles fill the others first.
SPACES: list[SpaceView] = [
    _space("H01-S001", "F-0005"),
    _space("H01-S002"),
    _space("H01-S011", "F-0001"),
    _space("H01-S012", "F-0002"),
    _space("H01-S016"),
    _space("H02-S001", "F-0052"),
    _space("H02-S002"),
    _space("H02-S011", "F-0051"),
    _space("H02-S014", "P-001"),
    _space("H02-S020", "F-0053"),
]


def _point(point_id: str, status: ChargingPointStatus) -> ChargingPointView:
    hub_id, number = point_id.split("-CP")
    return ChargingPointView(
        charging_point_id=point_id,
        hub_id=hub_id,
        parking_space_id=f"{hub_id}-S{int(number):03d}",
        power_rate_kw=11.0,
        status=status,
        version=1,
    )


CHARGING_POINTS: list[ChargingPointView] = [
    _point("H01-CP01", ChargingPointStatus.CHARGING),
    _point("H01-CP02", ChargingPointStatus.AVAILABLE),
    _point("H02-CP01", ChargingPointStatus.CHARGING),
    _point("H02-CP02", ChargingPointStatus.OUT_OF_SERVICE),
]

# -------------------------------------------------------------------------------- M2 bookings


@dataclass(frozen=True, slots=True)
class SampleBooking:
    """A rental reservation and its trip, if started (M2 ``RentalReservation``, ``RentalTrip``).

    ``status`` is a ``ReservationStatus`` value, ``trip_status`` a ``TripStatus`` value.
    """

    reservation_id: str
    vehicle_id: str
    origin_hub_id: str
    destination_hub_id: str | None
    status: str
    hold_expires_at: datetime
    trip_id: str | None = None
    trip_status: str | None = None
    picked_up_at: datetime | None = None
    expected_return_at: datetime | None = None


# Two bookings so that S5 shows both of its card layouts. A real student holds one rental at a
# time (LIMIT_REACHED). The screen makes the reservation ID; M2 fixes no format for it. M2 names
# a trip ``TRIP:<reservation_id>``. F-0006 is RESERVED at H01 in ``VEHICLES``; F-0007 is on a
# trip, so it is at no Hub and not in that list.
BOOKINGS: list[SampleBooking] = [
    SampleBooking(
        reservation_id="RES-0002",
        vehicle_id="F-0006",
        origin_hub_id="H01",
        destination_hub_id="H05",
        status="CONFIRMED",
        hold_expires_at=AS_OF + timedelta(minutes=10),
    ),
    SampleBooking(
        reservation_id="RES-0001",
        vehicle_id="F-0007",
        origin_hub_id="H01",
        destination_hub_id="H05",
        status="ACTIVE",
        hold_expires_at=AS_OF - timedelta(minutes=25),
        trip_id="TRIP:RES-0001",
        trip_status="IN_PROGRESS",
        picked_up_at=AS_OF - timedelta(minutes=22),
        expected_return_at=AS_OF + timedelta(minutes=8),
    ),
]

# -------------------------------------------------------------------------- M4 dispatch tasks


@dataclass(frozen=True, slots=True)
class SampleDispatchTask:
    """A dispatch task (M4 ``DispatchTask``). ``status`` is a ``DispatchTaskStatus`` value.

    M4 stores ``vehicle_ids`` as one comma-separated string; here it is already split.
    """

    task_id: str
    source_hub_id: str
    target_hub_id: str
    vehicle_type: VehicleType
    quantity: int
    vehicle_ids: tuple[str, ...]
    status: str
    priority: int
    reason: str


# Task IDs follow M4's planner: ``TASK-<slot_id>-<counter>``, default slot ``slot1``. The reason
# texts follow the planner (RECOMMENDED) and the parking-buffer check of ``approve`` (FAILED).
DISPATCH_TASKS: list[SampleDispatchTask] = [
    SampleDispatchTask(
        task_id="TASK-slot1-003",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=1,
        vehicle_ids=("F-0001",),
        status="RECOMMENDED",
        priority=1,
        reason="Deficit at H02 (need 1, urgency 0.80) served by surplus at H01 (dist 2)",
    ),
    SampleDispatchTask(
        task_id="TASK-slot1-002",
        source_hub_id="H05",
        target_hub_id="H01",
        vehicle_type=VehicleType.E_BIKE,
        quantity=1,
        vehicle_ids=("F-0150",),
        status="IN_PROGRESS",
        priority=2,
        reason="Deficit at H01 (need 1, urgency 0.50) served by surplus at H05 (dist 3)",
    ),
    SampleDispatchTask(
        task_id="TASK-slot1-001",
        source_hub_id="H02",
        target_hub_id="H03",
        vehicle_type=VehicleType.E_BIKE,
        quantity=1,
        vehicle_ids=("F-0054",),
        status="FAILED",
        priority=3,
        reason="Destination H03 violates parking buffer (0 free)",
    ),
]

# ------------------------------------------------------------------------------- M5 incidents


@dataclass(frozen=True, slots=True)
class SampleIncident:
    """An incident ticket (M5 ``IncidentTicket``).

    ``incident_type`` is an ``IncidentType`` value (the code, such as ``INC-HW-01``),
    ``severity`` an ``IncidentSeverity`` value, ``status`` an ``IncidentStatus`` value.
    """

    incident_id: str
    incident_type: str
    severity: str
    status: str
    hub_id: str
    description: str
    reported_by: str
    assigned_operator_id: str | None
    created_at: datetime


# Two of the tickets M5's service creates by itself, with its description texts and reporters.
INCIDENTS: list[SampleIncident] = [
    SampleIncident(
        incident_id="INC-3F9A0C21",
        incident_type="INC-HW-01",
        severity="CRITICAL",
        status="OPEN",
        hub_id="H02",
        description="Charging point H02-CP02 at hub H02 entered OUT_OF_SERVICE state",
        reported_by="SYSTEM_HARDWARE_MONITOR",
        assigned_operator_id=None,
        created_at=AS_OF - timedelta(minutes=2),
    ),
    SampleIncident(
        incident_id="INC-7B12E4D8",
        incident_type="INC-CAP-01",
        severity="HIGH",
        status="IN_PROGRESS",
        hub_id="H03",
        description="Hub Dorm B reached 100% parking capacity (50/50)",
        reported_by="SYSTEM_CAPACITY_EVALUATOR",
        assigned_operator_id="OP-01",
        created_at=AS_OF - timedelta(minutes=12),
    ),
]

# ------------------------------------------------------------------------------ M6 simulation


@dataclass(frozen=True, slots=True)
class SampleHubImpact:
    """Result for one Hub (M6 ``HubImpactMetrics``)."""

    hub_id: str
    total_requests: int
    unmet_requests: int
    shortage_rate_pct: float


@dataclass(frozen=True, slots=True)
class SampleRecommendation:
    """One recommendation of a run. M6 returns it as a dict with these keys."""

    recommendation_type: str
    target_module: str
    source_hub_id: str
    destination_hub_id: str
    batch_size: int
    trigger_reason: str
    status: str


@dataclass(frozen=True, slots=True)
class SampleSimulationReport:
    """The result of a demand-surge run (M6 ``SimulationReport``)."""

    simulation_id: str
    scenario_id: str
    snapshot_id: str
    executed_at: datetime
    baseline_shortage_rate_pct: float
    hub_metrics: tuple[SampleHubImpact, ...]
    recommendations: tuple[SampleRecommendation, ...]


def _move(destination_hub_id: str, unmet: int) -> SampleRecommendation:
    """One vehicle from H01, the only Hub with a surplus (4 rentable vehicles - 3 kept)."""
    return SampleRecommendation(
        recommendation_type="VEHICLE_REDISTRIBUTION",
        target_module="M4",
        source_hub_id="H01",
        destination_hub_id=destination_hub_id,
        batch_size=1,
        trigger_reason=f"Shortage of {unmet} vehicles at {destination_hub_id} during peak surge",
        status="PENDING_OPERATOR_APPROVAL",
    )


# The run M6's engine would make on the sample network above, with the form's defaults (targets
# H01 and H02, multiplier 1.5). Per Hub: rentable = AVAILABLE with battery >= 20% (M6 counts the
# private P-001 too); requests = ceil(max(5, rentable) x 1.5 on a target, x 1 elsewhere);
# unmet = requests - rentable. Baseline = all unmet / all requests = 22 / 31.
SIMULATION_SEED = 42  # SimulationConfig.random_seed of the run; the report has no seed
SIMULATION_RESULT = SampleSimulationReport(
    simulation_id="SIM-0001",
    scenario_id="SCENARIO_01_DEMAND_SURGE",
    snapshot_id="SNAP-4e1f0a9c2b7d6e35",
    executed_at=AS_OF,
    baseline_shortage_rate_pct=70.97,
    hub_metrics=(
        SampleHubImpact("H01", total_requests=8, unmet_requests=4, shortage_rate_pct=50.0),
        SampleHubImpact("H02", total_requests=8, unmet_requests=5, shortage_rate_pct=62.5),
        SampleHubImpact("H03", total_requests=5, unmet_requests=5, shortage_rate_pct=100.0),
        SampleHubImpact("H04", total_requests=5, unmet_requests=5, shortage_rate_pct=100.0),
        SampleHubImpact("H05", total_requests=5, unmet_requests=3, shortage_rate_pct=60.0),
    ),
    recommendations=(_move("H02", 5), _move("H03", 5), _move("H04", 5), _move("H05", 3)),
)
