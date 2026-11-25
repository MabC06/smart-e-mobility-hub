"""Pages of the UI: one route for each screen of the wireframes (``docs/design/ui``).

S2 to S4, O1 and O2 read ``core``. S7, S8 and O3 to O5 call the routes of M3, M4 and M5 through
``ui.api``. S5 and O6 still show ``ui.sample_data`` and say so on the page.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from core.api.security import Principal
from core.domain.enums import (
    ChargingPointStatus,
    HubStatus,
    Ownership,
    Role,
    VehicleState,
    VehicleType,
)
from core.facade import CoreFacade
from core.result import Err
from core.views import HubView, VehicleFilter, VehicleView
from ui import sample_data
from ui.api import call, explain, read_form
from ui.auth import TOKEN_COOKIE, current_user, get_auth, get_core

TEMPLATES_DIR = Path(__file__).parent / "templates"
ICT = timezone(timedelta(hours=7), "ICT")  # D-005: times are shown in ICT (UTC+7)
SAMPLE_NOTE = "Sample data: this screen is not connected to its module yet."
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


def _page(
    request: Request,
    template: str,
    who: Principal,
    status_code: int = 200,
    sample: bool = False,
    **context: Any,
) -> HTMLResponse:
    """Render a screen. An operator page also gets the alert strip (NFR-20)."""
    core = get_core(request)
    context["user_id"] = who.user_id
    # A sample screen uses the time of its sample data, so ages and deadlines on it stay right.
    context["as_of"] = sample_data.AS_OF if sample else core.queries.get_config().as_of
    context["sample_note"] = SAMPLE_NOTE if sample else None
    if who.role is Role.OPERATOR:
        hubs = core.queries.list_hubs()
        context["actor"] = "operator"
        context["alert_hubs"] = [h for s in ALERT_STATUSES for h in hubs if h.status is s]
        status, incidents = call(request, "GET", "/api/v1/monitoring/incidents")
        # "?" if M5 does not answer: better than a wrong number on the alert strip (NFR-20)
        context["active_incidents"] = (
            sum(1 for i in incidents if i["status"] in ACTIVE_INCIDENT_STATUSES)
            if status == 200
            else "?"
        )
    else:
        context["actor"] = "student"
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def _check_login(request: Request, role: Role) -> Principal | Response:
    """The signed-in user if it has the role, else the response to send: S1 or a 403 (NFR-16)."""
    who = current_user(request)
    if who is None:
        return RedirectResponse(str(request.url_for("login_page")), status_code=303)
    if who.role is not role:
        is_student = who.role is Role.STUDENT
        home = request.url_for("student_hubs" if is_student else "operator_overview")
        error = ErrorInfo(
            "You cannot open this page",
            "This page is for operators." if is_student else "This page is for students.",
            "FORBIDDEN",
            (("Go to your home page", str(home)),),
        )
        return _page(request, "error.html", who, 403, error=error)
    return who


def _refused(
    request: Request, who: Principal, what: str, status: int, data: Any, back: str, label: str
) -> HTMLResponse:
    """The error block S9 for a call that a module refused: its own cause and code (NFR-21)."""
    code, cause = explain(status, data)
    error = ErrorInfo(f"We could not {what}", cause, code, ((label, str(request.url_for(back))),))
    return _page(request, "error.html", who, 400 if status < 500 else 502, error=error)


def _hub_not_found(request: Request, who: Principal, back: str, label: str) -> HTMLResponse:
    """The error block for a Hub ID that does not exist, with a link back to ``back``."""
    error = ErrorInfo(
        "We could not open this Hub",
        "This item no longer exists.",
        "NOT_FOUND",
        ((label, str(request.url_for(back))),),
    )
    return _page(request, "error.html", who, 404, error=error)


def _find_hub(core: CoreFacade, hub_id: str | None) -> HubView | None:
    result = core.queries.get_hub(hub_id) if hub_id else None
    return None if result is None or isinstance(result, Err) else result.value


def _find_fleet_vehicle(core: CoreFacade, vehicle_id: str | None) -> VehicleView | None:
    """A private vehicle counts as unknown: a student never sees it."""
    result = core.queries.get_vehicle(vehicle_id) if vehicle_id else None
    if result is None or isinstance(result, Err) or result.value.ownership is not Ownership.FLEET:
        return None
    return result.value


def _by_severity(hubs: list[HubView]) -> list[HubView]:
    """O1 order: by severity (the order of ``STATUS_SYMBOLS``), then the fullest Hub first."""
    order = list(STATUS_SYMBOLS)

    def key(hub: HubView) -> tuple[int, float]:
        use = hub.occupied / hub.parking_capacity if hub.parking_capacity else 0.0
        return order.index(hub.status), -use

    return sorted(hubs, key=key)


# ---------------------------------------------------------------------------- entry and login


@root_router.get("/")
def home(request: Request) -> RedirectResponse:
    """Opening the site shows the login screen."""
    return RedirectResponse(request.url_for("login_page"))


@router.get("/login")
def login_page(request: Request) -> HTMLResponse:
    """S1. Login form."""
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login_submit(request: Request) -> Response:
    """S1. Ask ``core`` if the code and password are right; then S2 (student) or O1 (operator)."""
    form = read_form(request)
    code = form.get("code", "").strip()
    result = get_auth(request).login(code, form.get("password", ""))
    if isinstance(result, Err):
        # One message for a wrong code and a wrong password, like core (NFR-16).
        message = "The code or the password is wrong. Check both and try again."
        context = {"error": message, "code": code}
        return templates.TemplateResponse(request, "login.html", context, status_code=401)
    login = result.value
    home_page = "student_hubs" if login.role is Role.STUDENT else "operator_overview"
    response = RedirectResponse(str(request.url_for(home_page)), status_code=303)
    response.set_cookie(
        TOKEN_COOKIE, login.access_token, expires=login.expires_at, httponly=True, samesite="lax"
    )
    return response


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    """Forget the token and go back to S1."""
    response = RedirectResponse(str(request.url_for("login_page")), status_code=303)
    response.delete_cookie(TOKEN_COOKIE)
    return response


# ------------------------------------------------------------------------------------ student


@router.get("/student/hubs")
def student_hubs(request: Request) -> Response:
    """S2. Find a Hub: the student's home screen."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    return _page(request, "student/hubs.html", who, hubs=get_core(request).queries.list_hubs())


@router.get("/student/hubs/{hub_id}/vehicles")
def student_vehicles(request: Request, hub_id: str) -> Response:
    """S3. Vehicles at one Hub: fleet vehicles that are AVAILABLE only (student rule 3)."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    core = get_core(request)
    hub = _find_hub(core, hub_id)
    if hub is None:
        return _hub_not_found(request, who, "student_hubs", "Back to Hubs")
    vehicles = core.queries.find_vehicles(
        VehicleFilter(hub_id=hub_id, state=VehicleState.AVAILABLE, ownership=Ownership.FLEET)
    )
    hubs = core.queries.list_hubs()
    return _page(request, "student/vehicles.html", who, hub=hub, vehicles=vehicles, hubs=hubs)


@router.get("/student/reserve")
def student_confirm(
    request: Request,
    hub_id: str | None = None,
    vehicle_id: str | None = None,
    return_hub_id: str | None = None,
) -> Response:
    """S4. Confirm the vehicle chosen in S3 (the reservation itself needs a route of M2)."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    core = get_core(request)
    hub = _find_hub(core, hub_id)
    vehicle = _find_fleet_vehicle(core, vehicle_id)
    if hub is None or vehicle is None:
        back = "student_vehicles" if hub is not None else "student_hubs"
        link = (
            request.url_for(back, hub_id=hub.hub_id) if hub is not None else request.url_for(back)
        )
        error = ErrorInfo(
            "We could not reserve this vehicle",
            "Choose a vehicle in the list first.",
            "INVALID_INPUT",
            (("Choose a vehicle", str(link)),),
        )
        return _page(request, "error.html", who, 400, error=error)
    return _page(
        request,
        "student/confirm.html",
        who,
        sample=True,
        hub=hub,
        vehicle=vehicle,
        return_hub=_find_hub(core, return_hub_id),
    )


@router.get("/student/bookings")
def student_bookings(request: Request) -> Response:
    """S5. My bookings: pick up, cancel, return. Sample data until M2 has a route for it."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    hubs = get_core(request).queries.list_hubs()
    return _page(
        request,
        "student/bookings.html",
        who,
        sample=True,
        bookings=sample_data.BOOKINGS,
        hubs=hubs,
    )


@router.get("/student/parking")
def student_parking(request: Request) -> Response:
    """S6. Parking booking (Planned)."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    reason = "Not in M2's code yet (M2's Phase 3)."
    return _page(request, "planned.html", who, screen="S6. Parking booking", reason=reason)


def _my_private_evs(request: Request, who: Principal) -> list[VehicleView]:
    """The private EVs that the signed-in student owns (read from core)."""
    found = get_core(request).queries.find_vehicles(VehicleFilter(ownership=Ownership.PRIVATE))
    return [v for v in found if v.owner_user_id == who.user_id]


@router.get("/student/vehicle")
def student_private_ev(request: Request) -> Response:
    """S7. Register a private EV: the form and the student's saved vehicles."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    return _page(request, "student/vehicle.html", who, vehicles=_my_private_evs(request, who))


@router.post("/student/vehicle")
def student_register_ev(request: Request) -> Response:
    """S7. Save the vehicle through M3's route; back to S7 when it is saved."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    try:
        body = {
            "plate_or_code": form.get("plate_or_code", "").strip(),
            "vehicle_type": form.get("vehicle_type", ""),
            "battery_capacity_kwh": float(form.get("battery_capacity_kwh", "")),
            "current_soc": float(form.get("current_soc", "")),
            "connector_type": form.get("connector_type", "").strip(),
        }
    except ValueError:
        body = {}  # M3 refuses the empty body and its message is shown
    status, data = call(request, "POST", "/charging/private/vehicles", json=body)
    if status != 200:
        return _refused(
            request, who, "save this vehicle", status, data, "student_private_ev", "Back"
        )
    return RedirectResponse(str(request.url_for("student_private_ev")), status_code=303)


@router.get("/student/charging")
def student_charging(request: Request) -> Response:
    """S8. Request or schedule charging for a private EV, and the student's requests."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    status, sessions = call(request, "GET", "/charging/sessions")
    if status != 200:
        return _refused(
            request, who, "show your charging", status, sessions, "student_hubs", "Back"
        )
    return _page(
        request,
        "student/charging.html",
        who,
        vehicles=_my_private_evs(request, who),
        hubs=get_core(request).queries.list_hubs(),
        sessions=sessions,
    )


@router.post("/student/charging")
def student_request_charging(request: Request) -> Response:
    """S8. Send the request to M3: "now" or at a chosen time (the time is read as ICT)."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    body: dict[str, Any] = {
        "request_id": f"REQ-{uuid4().hex[:12]}",  # the screen makes the ID, one for each click
        "vehicle_id": form.get("vehicle_id", ""),
        "hub_id": form.get("hub_id", ""),
    }
    if form.get("duration_minutes", "").isdigit():
        body["duration_minutes"] = int(form["duration_minutes"])
    path = "/charging/requests/immediate"
    if form.get("when") == "schedule":
        path = "/charging/requests/schedule"
        try:  # the time is typed in ICT
            start = datetime.fromisoformat(form["start_at"]).replace(tzinfo=ICT)
            body["start_at"] = start.isoformat()
        except (KeyError, ValueError):
            body["start_at"] = form.get("start_at", "")  # M3 refuses it and says why
    status, data = call(request, "POST", path, json=body)
    if status != 200:
        return _refused(request, who, "request charging", status, data, "student_charging", "Back")
    return RedirectResponse(str(request.url_for("student_charging")), status_code=303)


# ----------------------------------------------------------------------------------- operator


@router.get("/operator/overview")
def operator_overview(request: Request) -> Response:
    """O1. Network overview: the operator's home screen, Hub cards ordered by severity."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    hubs = _by_severity(get_core(request).queries.list_hubs())
    return _page(request, "operator/overview.html", who, hubs=hubs)


@router.get("/operator/hubs/{hub_id}")
def operator_hub(request: Request, hub_id: str) -> Response:
    """O2. Hub detail. Not a tab: it opens from a Hub card or the alert strip."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    core = get_core(request)
    hub = _find_hub(core, hub_id)
    if hub is None:
        return _hub_not_found(request, who, "operator_overview", "Back to Overview")
    return _page(
        request,
        "operator/hub.html",
        who,
        hub=hub,
        vehicles=core.queries.find_vehicles(VehicleFilter(hub_id=hub_id)),
        spaces=core.queries.list_spaces(hub_id),
        charging_points=core.queries.list_charging_points(hub_id),
    )


@router.get("/operator/charging")
def operator_charging(request: Request, hub_id: str | None = None) -> Response:
    """O3. Charging coordination: the Hub's points (core) and its priority queue (M3)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    core = get_core(request)
    hubs = core.queries.list_hubs()
    hub = _find_hub(core, hub_id) or (hubs[0] if hubs else None)
    if hub is None:
        return _hub_not_found(request, who, "operator_overview", "Back to Overview")
    status, queue = call(request, "GET", "/charging/queue", params={"hub_id": hub.hub_id})
    if status != 200:
        return _refused(request, who, "show the queue", status, queue, "operator_overview", "Back")
    points = core.queries.list_charging_points(hub.hub_id)
    return _page(
        request,
        "operator/charging.html",
        who,
        hubs=hubs,
        hub=hub,
        points=points,
        in_use=sum(1 for p in points if p.status is ChargingPointStatus.CHARGING),
        out_of_service=sum(1 for p in points if p.status is ChargingPointStatus.OUT_OF_SERVICE),
        queue=queue,
    )


@router.get("/operator/dispatch")
def operator_dispatch(request: Request) -> Response:
    """O4. Dispatch tasks of M4, most urgent first."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    status, tasks = call(request, "GET", "/allocation/tasks")
    if status != 200:
        return _refused(request, who, "show the tasks", status, tasks, "operator_overview", "Back")
    for task in tasks:  # the screen's names for two fields of M4's answer
        task["vehicle_type"] = VehicleType(task["vehicle_type"])
        task["vehicle_ids"] = task["assigned_vehicles"]
    tasks.sort(key=lambda t: t["priority"])
    return _page(request, "operator/dispatch.html", who, tasks=tasks)


@router.post("/operator/dispatch/plan")
def dispatch_plan(request: Request) -> Response:
    """O4. "Update recommendations": ask M4 for new tasks."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    status, data = call(request, "POST", "/allocation/tasks/plan", json={})
    if status != 200:
        return _refused(request, who, "update the tasks", status, data, "operator_dispatch", "Back")
    return RedirectResponse(str(request.url_for("operator_dispatch")), status_code=303)


@router.post("/operator/dispatch/{task_id}/{action}")
def dispatch_action(request: Request, task_id: str, action: str) -> Response:
    """O4. Approve, confirm pick-up, confirm delivery ("return") or cancel one task (M4)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    if action not in ("approve", "pickup", "return", "cancel"):
        return _refused(
            request, who, "do this", 404, {"detail": "Unknown action."}, "operator_dispatch", "Back"
        )
    options: dict[str, Any] = {}
    quantity = read_form(request).get("quantity")
    if action == "approve" and quantity and quantity.isdigit():
        options["json"] = {"adjusted_quantity": int(quantity)}
    status, data = call(request, "POST", f"/allocation/tasks/{task_id}/{action}", **options)
    if status != 200:
        return _refused(
            request, who, f"{action} this task", status, data, "operator_dispatch", "Back"
        )
    return RedirectResponse(str(request.url_for("operator_dispatch")), status_code=303)


@router.get("/operator/incidents")
def operator_incidents(request: Request) -> Response:
    """O5. Incidents of M5, most severe first, then oldest."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    status, incidents = call(request, "GET", "/api/v1/monitoring/incidents")
    if status != 200:
        return _refused(
            request, who, "show the incidents", status, incidents, "operator_overview", "Back"
        )
    for incident in incidents:  # the pages show times as datetimes
        incident["created_at"] = datetime.fromisoformat(incident["created_at"])
    incidents.sort(key=lambda i: (SEVERITY_ORDER.index(i["severity"]), i["created_at"]))
    return _page(request, "operator/incidents.html", who, incidents=incidents)


@router.post("/operator/incidents/{incident_id}/{action}")
def incident_action(request: Request, incident_id: str, action: str) -> Response:
    """O5. Acknowledge, resolve (notes required) or close one ticket (M5)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    if action not in ("acknowledge", "resolve", "close"):
        return _refused(
            request,
            who,
            "do this",
            404,
            {"detail": "Unknown action."},
            "operator_incidents",
            "Back",
        )
    options: dict[str, Any] = {}
    if action == "resolve":
        options["json"] = {"resolution_notes": read_form(request).get("notes", "").strip()}
    path = f"/api/v1/monitoring/incidents/{incident_id}/{action}"
    status, data = call(request, "POST", path, **options)
    if status != 200:
        return _refused(
            request, who, f"{action} this incident", status, data, "operator_incidents", "Back"
        )
    return RedirectResponse(str(request.url_for("operator_incidents")), status_code=303)


@router.get("/operator/simulation")
def operator_simulation(request: Request) -> Response:
    """O6. What-if Simulation Lab of M6 (sample data until connected)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    return _page(
        request,
        "operator/simulation.html",
        who,
        sample=True,
        result=sample_data.SIMULATION_RESULT,
        seed=sample_data.SIMULATION_SEED,
        hubs=get_core(request).queries.list_hubs(),
    )
