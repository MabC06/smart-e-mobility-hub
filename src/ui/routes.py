"""Pages of the UI prototype (Phase 2): one route for each screen of the wireframes.

Screens S1 to S9 are in ``docs/design/ui/wireframes-student.md``, O1 to O6 in
``wireframes-operator.md``, and the moves between them in ``ui-flow-diagrams.md``. The data comes
from ``ui.sample_data``; nothing is read from or written to ``core`` yet (Phase 3).

Phase 2 has no real login: S1 has one button for each role. Buttons that would change data
(Confirm reservation, Approve, Resolve...) only lead to the next screen of the flow.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.domain.enums import HubStatus, Ownership, VehicleState, VehicleType
from core.views import HubView, VehicleView
from ui import sample_data

TEMPLATES_DIR = Path(__file__).parent / "templates"
ICT = timezone(timedelta(hours=7), "ICT")  # D-005: times are shown in ICT (UTC+7)
ALERT_STATUSES = (HubStatus.CRITICAL, HubStatus.WARNING)  # alert strip, most severe first
ACTIVE_INCIDENT_STATUSES = ("OPEN", "IN_PROGRESS", "ESCALATED")  # M5 statuses before RESOLVED
SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")  # M5 IncidentSeverity, most severe first
STATUS_SYMBOLS = {  # O1 notes: severity is a symbol and a word, not only a colour
    HubStatus.CRITICAL: "■",
    HubStatus.WARNING: "▲",
    HubStatus.ACTIVE: "●",
    HubStatus.MAINTENANCE: "✖",
}
VEHICLE_TYPE_LABELS = {  # the words of the S3 wireframe
    VehicleType.E_BIKE: "E-bike",
    VehicleType.E_SCOOTER: "E-scooter",
    VehicleType.E_MOTORCYCLE: "E-motorcycle",
}

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def to_ict(moment: datetime) -> str:
    """A UTC time as the screens show it, in ICT (D-005), e.g. ``10:42:05``."""
    return moment.astimezone(ICT).strftime("%H:%M:%S")


def type_label(vehicle_type: VehicleType) -> str:
    """The word a screen shows for a vehicle type, e.g. ``E-scooter``."""
    return VEHICLE_TYPE_LABELS[vehicle_type]


def status_symbol(status: HubStatus) -> str:
    """The symbol shown before a Hub status on operator screens, e.g. ``▲`` for WARNING."""
    return STATUS_SYMBOLS[status]


templates.env.filters["ict"] = to_ict
templates.env.filters["type_label"] = type_label
templates.env.filters["status_symbol"] = status_symbol

router = APIRouter(prefix="/ui", include_in_schema=False)
root_router = APIRouter(include_in_schema=False)


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    """What the error block S9 shows (NFR-21): what failed, the cause, up to two ways on
    as (label, URL), and the code under "Details"."""

    title: str
    cause: str
    code: str
    alternatives: tuple[tuple[str, str], ...] = ()


# ------------------------------------------------------------------------------------ helpers


def _find_hub(hub_id: str | None) -> HubView | None:
    return next((hub for hub in sample_data.HUBS if hub.hub_id == hub_id), None)


def _find_vehicle(vehicle_id: str | None) -> VehicleView | None:
    return next((v for v in sample_data.VEHICLES if v.vehicle_id == vehicle_id), None)


def _by_severity(hubs: list[HubView]) -> list[HubView]:
    """O1 order: by severity (the order of ``STATUS_SYMBOLS``), then the fullest Hub first."""
    order = list(STATUS_SYMBOLS)

    def key(hub: HubView) -> tuple[int, float]:
        use = hub.occupied / hub.parking_capacity if hub.parking_capacity else 0.0
        return order.index(hub.status), -use

    return sorted(hubs, key=key)


def _student_page(
    request: Request, template: str, status_code: int = 200, **context: Any
) -> HTMLResponse:
    """A student screen: the header shows the student's ``user_id``, the footer the data time."""
    context.update(actor="student", user_id=sample_data.STUDENT_ID, as_of=sample_data.AS_OF)
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def _operator_page(
    request: Request, template: str, status_code: int = 200, **context: Any
) -> HTMLResponse:
    """An operator screen: header, tab bar, alert strip and the data time.

    The alert strip lists the Hubs in ``WARNING`` or ``CRITICAL`` and the number of active
    incidents (operator rule 2, NFR-20).
    """
    alert_hubs = [
        hub for status in ALERT_STATUSES for hub in sample_data.HUBS if hub.status is status
    ]
    active_incidents = sum(1 for i in sample_data.INCIDENTS if i.status in ACTIVE_INCIDENT_STATUSES)
    context.update(
        actor="operator",
        user_id=sample_data.OPERATOR_ID,
        as_of=sample_data.AS_OF,
        alert_hubs=alert_hubs,
        active_incidents=active_incidents,
    )
    return templates.TemplateResponse(request, template, context, status_code=status_code)


# ---------------------------------------------------------------------------- entry and login


@root_router.get("/")
def home(request: Request) -> RedirectResponse:
    """Opening the site shows the login screen."""
    return RedirectResponse(request.url_for("login_page"))


@router.get("/login")
def login_page(request: Request) -> HTMLResponse:
    """S1. Login. A student goes to S2, an operator to O1 (ui-flow-diagrams.md)."""
    return templates.TemplateResponse(request, "login.html", {})


# ------------------------------------------------------------------------------------ student


@router.get("/student/hubs")
def student_hubs(request: Request) -> HTMLResponse:
    """S2. Find a Hub: the student's home screen."""
    return _student_page(request, "student/hubs.html", hubs=sample_data.HUBS)


@router.get("/student/hubs/{hub_id}/vehicles")
def student_vehicles(request: Request, hub_id: str) -> HTMLResponse:
    """S3. Vehicles at one Hub. A student sees fleet vehicles only (student rule 3)."""
    hub = _find_hub(hub_id)
    if hub is None:
        error = ErrorInfo(
            "We could not open this Hub",
            "This item no longer exists.",
            "NOT_FOUND",
            (("Back to Hubs", str(request.url_for("student_hubs"))),),
        )
        return _student_page(request, "error.html", 404, error=error)
    vehicles = [
        v
        for v in sample_data.VEHICLES
        if v.hub_id == hub_id
        and v.ownership is Ownership.FLEET
        and v.state is VehicleState.AVAILABLE
    ]
    return _student_page(
        request, "student/vehicles.html", hub=hub, vehicles=vehicles, hubs=sample_data.HUBS
    )


@router.get("/student/reserve")
def student_confirm(
    request: Request,
    hub_id: str | None = None,
    vehicle_id: str | None = None,
    return_hub_id: str | None = None,
) -> HTMLResponse:
    """S4. Confirm the reservation of the vehicle chosen in S3 (sent as query parameters)."""
    hub = _find_hub(hub_id)
    vehicle = _find_vehicle(vehicle_id)
    if hub is None or vehicle is None:
        back = (
            str(request.url_for("student_vehicles", hub_id=hub.hub_id))
            if hub is not None
            else str(request.url_for("student_hubs"))
        )
        error = ErrorInfo(
            "We could not reserve this vehicle",
            "Choose a vehicle in the list first.",
            "INVALID_INPUT",
            (("Choose a vehicle", back),),
        )
        return _student_page(request, "error.html", 400, error=error)
    return _student_page(
        request,
        "student/confirm.html",
        hub=hub,
        vehicle=vehicle,
        return_hub=_find_hub(return_hub_id),
    )


@router.get("/student/bookings")
def student_bookings(request: Request) -> HTMLResponse:
    """S5. My bookings: pick up, cancel, return. ``hubs`` fills the "Return to" list."""
    return _student_page(
        request, "student/bookings.html", bookings=sample_data.BOOKINGS, hubs=sample_data.HUBS
    )


@router.get("/student/parking")
def student_parking(request: Request) -> HTMLResponse:
    """S6. Parking booking (Planned)."""
    return _student_page(
        request,
        "planned.html",
        screen="S6. Parking booking",
        reason="Not in M2's code yet (M2's Phase 3).",
    )


@router.get("/student/vehicle")
def student_private_ev(request: Request) -> HTMLResponse:
    """S7. Register a private EV (Planned screen)."""
    return _student_page(
        request,
        "planned.html",
        screen="S7. My vehicle",
        reason="The form goes to an M3 route, which does not exist yet.",
    )


@router.get("/student/charging")
def student_charging(request: Request) -> HTMLResponse:
    """S8. Request or schedule charging (Planned)."""
    return _student_page(
        request,
        "planned.html",
        screen="S8. Charging",
        reason="M3's code keeps only an in-memory queue, with no status and no route.",
    )


# ----------------------------------------------------------------------------------- operator


@router.get("/operator/overview")
def operator_overview(request: Request) -> HTMLResponse:
    """O1. Network overview: the operator's home screen, Hub cards ordered by severity."""
    return _operator_page(request, "operator/overview.html", hubs=_by_severity(sample_data.HUBS))


@router.get("/operator/hubs/{hub_id}")
def operator_hub(request: Request, hub_id: str) -> HTMLResponse:
    """O2. Hub detail. Not a tab: it opens from a Hub card or the alert strip."""
    hub = _find_hub(hub_id)
    if hub is None:
        error = ErrorInfo(
            "We could not open this Hub",
            "This item no longer exists.",
            "NOT_FOUND",
            (("Back to Overview", str(request.url_for("operator_overview"))),),
        )
        return _operator_page(request, "error.html", 404, error=error)
    return _operator_page(
        request,
        "operator/hub.html",
        hub=hub,
        vehicles=[v for v in sample_data.VEHICLES if v.hub_id == hub_id],
        spaces=[s for s in sample_data.SPACES if s.hub_id == hub_id],
        charging_points=[p for p in sample_data.CHARGING_POINTS if p.hub_id == hub_id],
    )


@router.get("/operator/charging")
def operator_charging(request: Request) -> HTMLResponse:
    """O3. Charging coordination (Planned)."""
    return _operator_page(
        request,
        "planned.html",
        screen="O3. Charging",
        reason="M3's code keeps only an in-memory queue, with no status and no route.",
    )


@router.get("/operator/dispatch")
def operator_dispatch(request: Request) -> HTMLResponse:
    """O4. Dispatch tasks of M4."""
    return _operator_page(request, "operator/dispatch.html", tasks=sample_data.DISPATCH_TASKS)


@router.get("/operator/incidents")
def operator_incidents(request: Request) -> HTMLResponse:
    """O5. Incident management (tickets of M5): most severe first, then oldest."""
    incidents = sorted(
        sample_data.INCIDENTS, key=lambda i: (SEVERITY_ORDER.index(i.severity), i.created_at)
    )
    return _operator_page(request, "operator/incidents.html", incidents=incidents)


@router.get("/operator/simulation")
def operator_simulation(request: Request) -> HTMLResponse:
    """O6. What-if Simulation Lab (M6). ``hubs`` fills "Target Hubs"; ``seed`` is the run's."""
    return _operator_page(
        request,
        "operator/simulation.html",
        result=sample_data.SIMULATION_RESULT,
        seed=sample_data.SIMULATION_SEED,
        hubs=sample_data.HUBS,
    )
