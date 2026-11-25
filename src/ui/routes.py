"""Pages of the UI: one route for each screen of the wireframes (``docs/design/ui``).

S2, O1 and O2 read ``core``; O2's actions call ``core.commands`` with the operator's Actor
(operator rule 10). S3 to S8 and O3 to O6 call the routes of M2 to M6 through ``ui.api`` (D-026).
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from core.actor import Actor
from core.api.security import Principal
from core.domain.entities import UserAccount
from core.domain.enums import (
    ChargingPointStatus,
    HubStatus,
    Ownership,
    Role,
    VehicleEvent,
    VehicleState,
    VehicleType,
)
from core.facade import CoreFacade
from core.result import Err
from core.views import HubView, VehicleFilter, VehicleView
from ui.api import call, explain, read_form, read_form_list
from ui.auth import TOKEN_COOKIE, current_user, get_auth, get_core

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


def to_ict_day(moment: datetime) -> str:
    """A UTC time with its day, in ICT (D-005), e.g. ``Wed 26/11 19:51``."""
    return moment.astimezone(ICT).strftime("%a %d/%m %H:%M")


def to_ict_hm(moment: datetime) -> str:
    """A UTC time as hours and minutes in ICT (D-005), e.g. ``20:51``."""
    return moment.astimezone(ICT).strftime("%H:%M")


def to_ict_until(end: datetime, start: datetime) -> str:
    """The end of a period: hours and minutes on the start's day, else with its own day."""
    same_day = end.astimezone(ICT).date() == start.astimezone(ICT).date()
    return to_ict_hm(end) if same_day else to_ict_day(end)


def type_label(vehicle_type: VehicleType) -> str:
    """The word a screen shows for a vehicle type, e.g. ``E-scooter``."""
    return VEHICLE_TYPE_LABELS[vehicle_type]


def status_symbol(status: HubStatus) -> str:
    """The symbol shown before a Hub status on operator screens, e.g. ``▲`` for WARNING."""
    return STATUS_SYMBOLS[status]


templates.env.filters["ict"] = to_ict
templates.env.filters["ict_day"] = to_ict_day
templates.env.filters["ict_hm"] = to_ict_hm
templates.env.filters["ict_until"] = to_ict_until
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
    **context: Any,
) -> HTMLResponse:
    """Render a screen. An operator page also gets the alert strip (NFR-20)."""
    core = get_core(request)
    account = core.get_entity(UserAccount, who.user_id)
    context["user_id"] = account.code if account is not None else who.user_id  # the login code
    context["as_of"] = core.queries.get_config().as_of
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


def _go(request: Request, name: str, **params: str) -> RedirectResponse:
    """After a form: back to a screen (303, so a refresh does not send the form again)."""
    return RedirectResponse(str(request.url_for(name, **params)), status_code=303)


def _whole_number(text: str) -> int | str:
    """A typed whole number as an int; anything else is sent as it is and the module refuses it."""
    return int(text) if text.isdigit() else text


def _from_ict(text: str) -> str:
    """A ``datetime-local`` value typed in ICT as an ISO time; anything else is sent as it is."""
    try:
        return datetime.fromisoformat(text).replace(tzinfo=ICT).isoformat()
    except ValueError:
        return text


def _plates(core: CoreFacade, vehicle_ids: set[str]) -> dict[str, str]:
    """Vehicle ID -> the code a screen shows (FLEET-0001, PRIVATE-001)."""
    plates: dict[str, str] = {}
    for vehicle_id in vehicle_ids:
        found = core.queries.get_vehicle(vehicle_id)
        plates[vehicle_id] = vehicle_id if isinstance(found, Err) else found.value.plate_or_code
    return plates


def _times(record: dict[str, Any], *fields: str) -> dict[str, Any]:
    """Turn the ISO times of an answer into datetimes, so the page can show them in ICT."""
    for name in fields:
        if record.get(name):
            record[name] = datetime.fromisoformat(record[name])
    return record


# ------------------------------------------------------------------------------------ student


@router.get("/student/hubs")
def student_hubs(request: Request) -> Response:
    """S2. Find a Hub: the student's home screen."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    return _page(request, "student/hubs.html", who, hubs=get_core(request).queries.list_hubs())


@router.get("/student/hubs/{hub_id}/vehicles")
def student_vehicles(
    request: Request, hub_id: str, type: str = "", min_battery: str = "20"
) -> Response:
    """S3. Vehicles a student can rent now at one Hub: M2's search (FR-02), best battery first."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    core = get_core(request)
    hub = _find_hub(core, hub_id)
    if hub is None:
        return _hub_not_found(request, who, "student_hubs", "Back to Hubs")
    params: dict[str, str] = {"hub_id": hub_id, "min_battery": min_battery or "20"}
    if type:
        params["type"] = type
    status, found = call(request, "GET", "/reservations/vehicles", params=params)
    if status != 200:
        return _refused(request, who, "search vehicles", status, found, "student_hubs", "Back")
    return _page(
        request,
        "student/vehicles.html",
        who,
        hub=hub,
        vehicles=found["vehicles"],
        hubs=core.queries.list_hubs(),
        vehicle_types=list(VehicleType),
        chosen_type=type,
        min_battery=params["min_battery"],
    )


@router.get("/student/reserve")
def student_confirm(
    request: Request,
    hub_id: str | None = None,
    vehicle_id: str | None = None,
    return_hub_id: str | None = None,
) -> Response:
    """S4. Confirm the vehicle chosen in S3."""
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
        hub=hub,
        vehicle=vehicle,
        return_hub=_find_hub(core, return_hub_id),
    )


@router.post("/student/reserve")
def student_reserve(request: Request) -> Response:
    """S4. Send the reservation to M2; then S5, where the booking is listed."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    body: dict[str, Any] = {
        "reservation_id": f"RES-{uuid4().hex[:12]}",  # the screen makes the ID, one for each click
        "vehicle_id": form.get("vehicle_id", ""),
        "origin_hub_id": form.get("hub_id", ""),
        "expected_version": _whole_number(form.get("version", "")),  # the version S4 showed
        "planned_duration_minutes": _whole_number(form.get("planned_minutes", "")),
    }
    if form.get("return_hub_id"):
        body["destination_hub_id"] = form["return_hub_id"]
    status, data = call(request, "POST", "/reservations", json=body)
    if status != 200:
        return _refused(
            request, who, "reserve this vehicle", status, data, "student_hubs", "Choose a vehicle"
        )
    return _go(request, "student_bookings")


def _my_rentals(request: Request, who: Principal) -> dict[str, Any] | Response:
    """M2's answer for the signed-in student, with times as datetimes and vehicle codes."""
    status, mine = call(request, "GET", "/reservations/mine")
    if status != 200:
        return _refused(request, who, "show your bookings", status, mine, "student_hubs", "Back")
    for booking in mine["bookings"]:
        _times(booking, "hold_expires_at", "confirmed_at")
    for trip in mine["open_trips"]:
        _times(trip, "picked_up_at", "expected_return_at")
    for stay in mine["parking"]:
        _times(stay, "start_at", "hold_expires_at", "planned_end_at", "arrived_at", "departed_at")
    ids = {b["vehicle_id"] for b in mine["bookings"]} | {p["vehicle_id"] for p in mine["parking"]}
    mine["plates"] = _plates(get_core(request), ids)
    return dict(mine)


@router.get("/student/bookings")
def student_bookings(request: Request) -> Response:
    """S5. My bookings from M2, newest first, with the actions each booking allows."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    mine = _my_rentals(request, who)
    if isinstance(mine, Response):
        return mine
    trips = {trip["reservation_id"]: trip for trip in mine["open_trips"]}
    holds = {
        p["trip_id"]: p
        for p in mine["parking"]
        if p["purpose"] == "RENTAL_RETURN" and p["status"] == "CONFIRMED"
    }
    for booking in mine["bookings"]:
        booking["version"] = mine["vehicle_versions"].get(booking["vehicle_id"])
        booking["plate"] = mine["plates"][booking["vehicle_id"]]
        booking["trip"] = trips.get(booking["reservation_id"])
        booking["hold"] = holds.get(f"TRIP:{booking['reservation_id']}")
    bookings = sorted(mine["bookings"], key=lambda b: b["confirmed_at"], reverse=True)
    # open: reserved, or picked up and not returned yet; the others are only listed
    current = [b for b in bookings if b["status"] == "CONFIRMED" or b["trip"] is not None]
    earlier = [b for b in bookings if b["status"] != "CONFIRMED" and b["trip"] is None]
    hubs = get_core(request).queries.list_hubs()
    return _page(request, "student/bookings.html", who, current=current, earlier=earlier, hubs=hubs)


BOOKING_ACTIONS = {  # S5 action -> what the error block says could not be done
    "pickup": "pick up this vehicle",
    "cancel": "cancel this booking",
    "return": "return this vehicle",
    "hold": "hold a return space",
}


@router.post("/student/bookings/{reservation_id}/{action}")
def booking_action(request: Request, reservation_id: str, action: str) -> Response:
    """S5. Pick up, cancel, return or hold a return space for one booking (M2); back to S5."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    if action not in BOOKING_ACTIONS:
        return _refused(
            request, who, "do this", 404, {"detail": "Unknown action."}, "student_bookings", "Back"
        )
    form = read_form(request)
    version = _whole_number(form.get("version", ""))  # the vehicle version S5 showed
    path = f"/reservations/{reservation_id}/{action}"
    options: dict[str, Any] = {}
    if action == "pickup":
        options["json"] = {
            "origin_hub_id": form.get("origin_hub_id", ""),
            "expected_version": version,
        }
    elif action == "return":
        hub_id = form.get("destination_hub_id", "")
        options["json"] = {"destination_hub_id": hub_id, "expected_version": version}
    elif action == "hold":
        path = f"/reservations/{reservation_id}/return-hold"
        options["json"] = {
            "parking_id": f"PK-{uuid4().hex[:12]}",
            "destination_hub_id": form.get("destination_hub_id", ""),
        }
    status, data = call(request, "POST", path, **options)
    if status != 200:
        return _refused(
            request, who, BOOKING_ACTIONS[action], status, data, "student_bookings", "Back"
        )
    return _go(request, "student_bookings")


def _my_private_evs(request: Request, who: Principal) -> list[VehicleView]:
    """The private EVs that the signed-in student owns (read from core)."""
    found = get_core(request).queries.find_vehicles(VehicleFilter(ownership=Ownership.PRIVATE))
    return [v for v in found if v.owner_user_id == who.user_id]


@router.get("/student/parking")
def student_parking(request: Request) -> Response:
    """S6. Parking for the student's own EV (M2): book a space, arrive, leave, cancel."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    mine = _my_rentals(request, who)
    if isinstance(mine, Response):
        return mine
    stays = [p for p in mine["parking"] if p["purpose"] == "PRIVATE_STAY"]
    for stay in stays:
        stay["plate"] = mine["plates"][stay["vehicle_id"]]
        stay["version"] = mine["vehicle_versions"].get(stay["vehicle_id"])
    current = [s for s in stays if s["status"] in ("CONFIRMED", "ACTIVE")]
    booked = {s["vehicle_id"] for s in current}
    evs = _my_private_evs(request, who)
    return _page(
        request,
        "student/parking.html",
        who,
        # an EV away from every Hub and not booked yet can be booked
        vehicles=[v for v in evs if v.hub_id is None and v.vehicle_id not in booked],
        parked=[v for v in evs if v.hub_id is not None],
        hubs=get_core(request).queries.list_hubs(),
        current=current,
        earlier=[s for s in stays if s["status"] not in ("CONFIRMED", "ACTIVE")],
    )


@router.post("/student/parking")
def student_book_parking(request: Request) -> Response:
    """S6. Book a space for a private EV, now or later (the time is typed in ICT)."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    body: dict[str, Any] = {
        "parking_id": f"PK-{uuid4().hex[:12]}",
        "vehicle_id": form.get("vehicle_id", ""),
        "hub_id": form.get("hub_id", ""),
        "duration_minutes": _whole_number(form.get("duration_minutes", "")),
    }
    if form.get("when") == "later":
        body["start_at"] = _from_ict(form.get("start_at", ""))
    status, data = call(request, "POST", "/reservations/parking", json=body)
    if status != 200:
        return _refused(request, who, "book parking", status, data, "student_parking", "Back")
    return _go(request, "student_parking")


PARKING_ACTIONS = {
    "arrive": "record your arrival",
    "depart": "record your departure",
    "cancel": "cancel this parking",
}


@router.post("/student/parking/{parking_id}/{action}")
def parking_action(request: Request, parking_id: str, action: str) -> Response:
    """S6. Arrive at, leave or cancel one parking booking (M2); back to S6."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    if action not in PARKING_ACTIONS:
        return _refused(
            request, who, "do this", 404, {"detail": "Unknown action."}, "student_parking", "Back"
        )
    options: dict[str, Any] = {}
    if action in ("arrive", "depart"):
        version = _whole_number(read_form(request).get("version", ""))
        options["json"] = {"expected_version": version}
    status, data = call(request, "POST", f"/reservations/parking/{parking_id}/{action}", **options)
    if status != 200:
        return _refused(
            request, who, PARKING_ACTIONS[action], status, data, "student_parking", "Back"
        )
    return _go(request, "student_parking")


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
    return _go(request, "student_private_ev")


@router.get("/student/charging")
def student_charging(request: Request) -> Response:
    """S8. Request or schedule charging for a private EV; change or cancel a request (M3)."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    status, sessions = call(request, "GET", "/charging/sessions")
    if status != 200:
        return _refused(
            request, who, "show your charging", status, sessions, "student_hubs", "Back"
        )
    core = get_core(request)
    plates = _plates(core, {s["vehicle_id"] for s in sessions})
    for session in sessions:
        _times(session, "start_time", "end_time", "requested_at")
        session["plate"] = plates[session["vehicle_id"]]
    sessions.sort(key=lambda s: str(s["requested_at"]), reverse=True)
    open_statuses = ("QUEUED", "SCHEDULED", "CHARGING")
    return _page(
        request,
        "student/charging.html",
        who,
        vehicles=_my_private_evs(request, who),
        hubs=core.queries.list_hubs(),
        sessions=[s for s in sessions if s["status"] in open_statuses],
        earlier=[s for s in sessions if s["status"] not in open_statuses],
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
        body["start_at"] = _from_ict(form.get("start_at", ""))
    status, data = call(request, "POST", path, json=body)
    if status != 200:
        return _refused(request, who, "request charging", status, data, "student_charging", "Back")
    return _go(request, "student_charging")


@router.post("/student/charging/{request_id}/{action}")
def charging_change(request: Request, request_id: str, action: str) -> Response:
    """S8. Change the time of (M3 PATCH), cancel (M3 DELETE) or start one charging request."""
    who = _check_login(request, Role.STUDENT)
    if isinstance(who, Response):
        return who
    if action == "change":
        form = read_form(request)
        body = {
            "start_at": _from_ict(form.get("start_at", "")),
            "duration_minutes": _whole_number(form.get("duration_minutes", "")),
        }
        status, data = call(request, "PATCH", f"/charging/requests/{request_id}", json=body)
        what = "change this charging time"
    elif action == "cancel":
        status, data = call(request, "DELETE", f"/charging/requests/{request_id}")
        what = "cancel this charging"
    elif action == "start":
        status, data = call(request, "POST", f"/charging/sessions/{request_id}/start")
        what = "start charging"
    else:
        status, data, what = 404, {"detail": "Unknown action."}, "do this"
    if status != 200:
        return _refused(request, who, what, status, data, "student_charging", "Back")
    return _go(request, "student_charging")


# ----------------------------------------------------------------------------------- operator


def _operator_actor(who: Principal) -> Actor:
    """The operator as core's Actor for O2's commands (operator rule 10, NFR-16)."""
    return Actor(who.user_id, Role.OPERATOR, "ui")


@router.get("/operator/overview")
def operator_overview(request: Request, zone: str = "", status: str = "") -> Response:
    """O1. Network overview: the operator's home screen, Hub cards ordered by severity."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    all_hubs = get_core(request).queries.list_hubs()
    hubs = [
        h
        for h in _by_severity(all_hubs)
        if (not zone or h.zone_code == zone) and (not status or h.status == status)
    ]
    return _page(
        request,
        "operator/overview.html",
        who,
        hubs=hubs,
        zones=sorted({h.zone_code for h in all_hubs}),
        statuses=list(HubStatus),
        zone=zone,
        status=status,
    )


@router.get("/operator/hubs/{hub_id}")
def operator_hub(
    request: Request,
    hub_id: str,
    type: str = "",
    state: str = "",
    owner: str = "",
    vehicle: str = "",
) -> Response:
    """O2. Hub detail and resource control. Opens from a Hub card or the alert strip."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    core = get_core(request)
    hub = _find_hub(core, hub_id)
    if hub is None:
        return _hub_not_found(request, who, "operator_overview", "Back to Overview")
    at_hub = core.queries.find_vehicles(VehicleFilter(hub_id=hub_id))
    vehicles = [
        v
        for v in at_hub
        if (not type or v.vehicle_type == type)
        and (not state or v.state == state)
        and (not owner or v.ownership == owner)
    ]
    history = core.queries.get_state_log(vehicle, limit=10) if vehicle else []
    return _page(
        request,
        "operator/hub.html",
        who,
        hub=hub,
        vehicles=vehicles,
        spaces=core.queries.list_spaces(hub_id),
        plates={v.vehicle_id: v.plate_or_code for v in at_hub},
        charging_points=core.queries.list_charging_points(hub_id),
        vehicle_types=list(VehicleType),
        vehicle_states=list(VehicleState),
        filters={"type": type, "state": state, "owner": owner},
        shown_vehicle=vehicle,
        history=history,
        point_statuses=(
            ChargingPointStatus.AVAILABLE,
            ChargingPointStatus.OUT_OF_SERVICE,
            ChargingPointStatus.MAINTENANCE,
        ),
    )


VEHICLE_EVENTS = {  # O2 action -> core event and what the error block says
    "report_fault": (VehicleEvent.REPORT_FAULT, "report a fault"),
    "repair": (VehicleEvent.REPAIR, "record the repair"),
    "mark_ready": (VehicleEvent.MARK_READY, "make the vehicle available"),
}


@router.post("/operator/hubs/{hub_id}/vehicles/{vehicle_id}/{action}")
def vehicle_action(request: Request, hub_id: str, vehicle_id: str, action: str) -> Response:
    """O2. Report a fault, record a repair or make a vehicle available (core T11, T12, T6)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    if action not in VEHICLE_EVENTS:
        return _refused(
            request, who, "do this", 404, {"detail": "Unknown action."}, "operator_overview", "Back"
        )
    event, what = VEHICLE_EVENTS[action]
    version = _whole_number(read_form(request).get("version", ""))
    result = get_core(request).commands.transition_vehicle(
        vehicle_id, event, version if isinstance(version, int) else -1, _operator_actor(who)
    )
    if isinstance(result, Err):
        return _core_refused(request, who, what, result, hub_id)
    return _go(request, "operator_hub", hub_id=hub_id)


def _core_refused(
    request: Request, who: Principal, what: str, error: Err, hub_id: str
) -> HTMLResponse:
    """The error block for a core command that was refused, with a link back to O2."""
    info = ErrorInfo(
        f"We could not {what}",
        error.message,
        error.code.value,
        (("Back to the Hub", str(request.url_for("operator_hub", hub_id=hub_id))),),
    )
    return _page(request, "error.html", who, 400, error=info)


@router.post("/operator/hubs/{hub_id}/points/{point_id}")
def point_status(request: Request, hub_id: str, point_id: str) -> Response:
    """O2. Set a charging point AVAILABLE, OUT_OF_SERVICE or MAINTENANCE (M3 reacts)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    try:
        new_status = ChargingPointStatus(form.get("status", ""))
    except ValueError:
        new_status = ChargingPointStatus.AVAILABLE
    version = _whole_number(form.get("version", ""))
    result = get_core(request).commands.set_charging_point_status(
        point_id, new_status, version if isinstance(version, int) else -1, _operator_actor(who)
    )
    if isinstance(result, Err):
        return _core_refused(request, who, "change the charging point", result, hub_id)
    return _go(request, "operator_hub", hub_id=hub_id)


@router.post("/operator/hubs/{hub_id}/status")
def hub_status(request: Request, hub_id: str) -> Response:
    """O2. Close a Hub for maintenance or open it again (ACTIVE); M5 sets WARNING and CRITICAL."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    new_status = HubStatus.MAINTENANCE if form.get("status") == "MAINTENANCE" else HubStatus.ACTIVE
    version = _whole_number(form.get("version", ""))
    result = get_core(request).commands.set_hub_status(
        hub_id, new_status, version if isinstance(version, int) else -1, _operator_actor(who)
    )
    if isinstance(result, Err):
        return _core_refused(request, who, "change the Hub status", result, hub_id)
    return _go(request, "operator_hub", hub_id=hub_id)


@router.get("/operator/charging")
def operator_charging(request: Request, hub_id: str | None = None, owner: str = "") -> Response:
    """O3. Charging coordination: points (core), queue, sessions and moved sessions (M3)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    core = get_core(request)
    hubs = core.queries.list_hubs()
    hub = _find_hub(core, hub_id) or (hubs[0] if hubs else None)
    if hub is None:
        return _hub_not_found(request, who, "operator_overview", "Back to Overview")
    params = {"hub_id": hub.hub_id}
    answers = [
        call(request, "GET", "/charging/queue", params=params),
        call(request, "GET", "/charging/sessions", params=params),
        call(request, "GET", "/charging/moved", params=params),
    ]
    for status, data in answers:
        if status != 200:
            return _refused(
                request, who, "show charging", status, data, "operator_overview", "Back"
            )
    queue, sessions, moved = (data for _, data in answers)
    queue = [q for q in queue if not owner or q["ownership"] == owner]
    plates = _plates(core, {s["vehicle_id"] for s in [*queue, *sessions, *moved]})
    for row in [*queue, *sessions, *moved]:
        row["plate"] = plates[row["vehicle_id"]]
        _times(row, "start_time", "end_time", "interrupted_at", "to_start_time", "requested_at")
    active = [s for s in sessions if s["status"] in ("SCHEDULED", "CHARGING")]
    active.sort(key=lambda s: s["start_time"] or datetime.max.replace(tzinfo=ICT))
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
        sessions=active,
        moved=moved,
        owner=owner,
    )


SESSION_ACTIONS = {
    "start": "start this session",
    "finish": "finish this session",
    "interrupt": "stop this session",
}


@router.post("/operator/charging/{hub_id}/optimize")
def charging_optimize(request: Request, hub_id: str) -> Response:
    """O3. Ask M3 to bind the queue of the Hub to free charging slots (UC-M3-07)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    status, data = call(request, "POST", "/charging/schedule/optimize", params={"hub_id": hub_id})
    if status != 200:
        return _refused(
            request, who, "optimize the queue", status, data, "operator_charging", "Back"
        )
    return RedirectResponse(
        str(request.url_for("operator_charging").include_query_params(hub_id=hub_id)),
        status_code=303,
    )


@router.post("/operator/charging/{hub_id}/sessions/{request_id}/{action}")
def session_action(request: Request, hub_id: str, request_id: str, action: str) -> Response:
    """O3. Start a scheduled session, finish or stop a running one (M3)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    if action not in SESSION_ACTIONS:
        return _refused(
            request, who, "do this", 404, {"detail": "Unknown action."}, "operator_charging", "Back"
        )
    options: dict[str, Any] = {} if action == "start" else {"json": {}}
    status, data = call(request, "POST", f"/charging/sessions/{request_id}/{action}", **options)
    if status != 200:
        return _refused(
            request, who, SESSION_ACTIONS[action], status, data, "operator_charging", "Back"
        )
    return RedirectResponse(
        str(request.url_for("operator_charging").include_query_params(hub_id=hub_id)),
        status_code=303,
    )


CONFIG_FIELDS = (  # O4 settings: M4 field, label, unit
    ("horizon_minutes", "Planning horizon", "min"),
    ("safety_stock", "Safety stock", "vehicles"),
    ("parking_buffer", "Parking buffer", "spaces"),
    ("min_dispatch_battery", "Minimum dispatch battery", "%"),
    ("max_tasks_per_hub", "Maximum tasks per Hub", "tasks"),
    ("max_vehicles_per_task", "Maximum vehicles per task", "vehicles"),
    ("task_timeout_minutes", "Task timeout", "min"),
    ("staleness_limit_minutes", "Staleness limit", "min"),
    ("reservation_lookahead_minutes", "Reservation lookahead", "min"),
)
TASK_STATUSES = (
    "RECOMMENDED",
    "APPROVED",
    "IN_PROGRESS",
    "COMPLETED",
    "CANCELLED",
    "REJECTED",
    "FAILED",
)


@router.get("/operator/dispatch")
def operator_dispatch(request: Request, status: str = "") -> Response:
    """O4. Dispatch tasks of M4, most urgent first, and M4's settings."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    params = {"task_status": status} if status in TASK_STATUSES else {}
    code, tasks = call(request, "GET", "/allocation/tasks", params=params)
    if code != 200:
        return _refused(request, who, "show the tasks", code, tasks, "operator_overview", "Back")
    code, config = call(request, "GET", "/allocation/config")
    if code != 200:
        return _refused(
            request, who, "show M4's settings", code, config, "operator_overview", "Back"
        )
    plates = _plates(get_core(request), {v for t in tasks for v in t["assigned_vehicles"]})
    for task in tasks:  # the screen's names for two fields of M4's answer
        task["vehicle_type"] = VehicleType(task["vehicle_type"])
        task["vehicle_ids"] = [plates[v] for v in task["assigned_vehicles"]]
    tasks.sort(
        key=lambda t: (t["status"] not in ("RECOMMENDED", "APPROVED", "IN_PROGRESS"), t["priority"])
    )
    return _page(
        request,
        "operator/dispatch.html",
        who,
        tasks=tasks,
        statuses=TASK_STATUSES,
        status=status,
        config=config,
        config_fields=CONFIG_FIELDS,
    )


@router.post("/operator/dispatch/plan")
def dispatch_plan(request: Request) -> Response:
    """O4. "Update recommendations": ask M4 for new tasks."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    status, data = call(request, "POST", "/allocation/tasks/plan", json={})
    if status != 200:
        return _refused(request, who, "update the tasks", status, data, "operator_dispatch", "Back")
    return _go(request, "operator_dispatch")


@router.post("/operator/dispatch/settings")
def dispatch_settings(request: Request) -> Response:
    """O4. Save M4's settings (UC-M4-09); M4 checks each value."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    body: dict[str, Any] = {}
    for name, _label, _unit in CONFIG_FIELDS:
        text = form.get(name, "").strip()
        if text:
            try:
                body[name] = float(text) if name == "min_dispatch_battery" else int(text)
            except ValueError:
                body[name] = text  # M4 refuses it and says why
    status, data = call(request, "PUT", "/allocation/config", json=body)
    if status != 200:
        return _refused(
            request, who, "save the settings", status, data, "operator_dispatch", "Back"
        )
    return _go(request, "operator_dispatch")


@router.post("/operator/dispatch/{task_id}/{action}")
def dispatch_action(request: Request, task_id: str, action: str) -> Response:
    """O4. Approve, reject, confirm pick-up, confirm delivery ("return") or cancel a task (M4)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    if action not in ("approve", "reject", "pickup", "return", "cancel"):
        return _refused(
            request, who, "do this", 404, {"detail": "Unknown action."}, "operator_dispatch", "Back"
        )
    form = read_form(request)
    options: dict[str, Any] = {}
    quantity = form.get("quantity")
    if action == "approve" and quantity and quantity.isdigit():
        options["json"] = {"adjusted_quantity": int(quantity)}
    if action in ("reject", "cancel"):
        options["json"] = {"reason": form.get("reason", "").strip()}
    status, data = call(request, "POST", f"/allocation/tasks/{task_id}/{action}", **options)
    if status != 200:
        return _refused(
            request, who, f"{action} this task", status, data, "operator_dispatch", "Back"
        )
    return _go(request, "operator_dispatch")


INCIDENT_TYPES = {
    "INC-HW-01": "Charging-point fault",
    "INC-HW-02": "Parking sensor",
    "INC-CAP-01": "Hub full",
    "INC-CAP-02": "Vehicle deficit",
    "INC-BAT-01": "Low battery",
    "INC-COMM-01": "Telemetry loss",
    "INC-USR-01": "Overdue rental",
}
INCIDENT_STATUSES = ("OPEN", "IN_PROGRESS", "ESCALATED", "RESOLVED", "CLOSED")


@router.get("/operator/incidents")
def operator_incidents(
    request: Request,
    severity: str = "",
    status: str = "",
    hub: str = "",
    type: str = "",
    ticket: str = "",
) -> Response:
    """O5. Incidents of M5, most severe first, then oldest; one ticket's history on demand."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    code, incidents = call(request, "GET", "/api/v1/monitoring/incidents")
    if code != 200:
        return _refused(
            request, who, "show the incidents", code, incidents, "operator_overview", "Back"
        )
    hubs = [h.hub_id for h in get_core(request).queries.list_hubs()]
    for incident in incidents:  # the pages show times as datetimes
        incident["created_at"] = datetime.fromisoformat(incident["created_at"])
    incidents = [
        i
        for i in incidents
        if (not severity or i["severity"] == severity)
        and (not status or i["status"] == status)
        and (not hub or i["hub_id"] == hub)
        and (not type or i["incident_type"] == type)
    ]
    incidents.sort(key=lambda i: (SEVERITY_ORDER.index(i["severity"]), i["created_at"]))
    history: list[dict[str, Any]] = []
    if ticket:
        code, logs = call(request, "GET", f"/api/v1/monitoring/incidents/{ticket}/logs")
        history = [_times(log, "timestamp") for log in logs] if code == 200 else []
    return _page(
        request,
        "operator/incidents.html",
        who,
        incidents=incidents,
        type_names=INCIDENT_TYPES,
        severities=SEVERITY_ORDER,
        statuses=INCIDENT_STATUSES,
        hubs=hubs,
        filters={"severity": severity, "status": status, "hub": hub, "type": type},
        ticket=ticket,
        history=history,
    )


@router.post("/operator/incidents/{incident_id}/{action}")
def incident_action(request: Request, incident_id: str, action: str) -> Response:
    """O5. Acknowledge, escalate, resolve (notes required) or close one ticket (M5)."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    if action not in ("acknowledge", "escalate", "resolve", "close"):
        return _refused(
            request,
            who,
            "do this",
            404,
            {"detail": "Unknown action."},
            "operator_incidents",
            "Back",
        )
    form = read_form(request)
    options: dict[str, Any] = {}
    if action == "resolve":
        options["json"] = {"resolution_notes": form.get("notes", "").strip()}
    if action == "escalate":
        options["json"] = {"reason": form.get("reason", "").strip() or "Escalated by operator"}
    path = f"/api/v1/monitoring/incidents/{incident_id}/{action}"
    status, data = call(request, "POST", path, **options)
    if status != 200:
        return _refused(
            request, who, f"{action} this incident", status, data, "operator_incidents", "Back"
        )
    return _go(request, "operator_incidents")


SCENARIOS = (  # O6: M6 scenario ID, label
    ("SC-01", "Peak-hour demand surge"),
    ("SC-02", "Hub at capacity"),
    ("SC-03", "Charging surge"),
    ("SC-04", "Charging-point failure"),
    ("SC-05", "Vehicle imbalance"),
)
SCENARIO_NAMES = {  # M6's long scenario IDs -> what O6 shows
    "SCENARIO_01_DEMAND_SURGE": "SC-01 Peak-hour demand surge",
    "SCENARIO_02_HUB_AT_CAPACITY": "SC-02 Hub at capacity",
    "SCENARIO_03_CHARGING_SURGE": "SC-03 Charging surge",
    "SCENARIO_04_CHARGER_FAILURE": "SC-04 Charging-point failure",
    "SCENARIO_05_VEHICLE_IMBALANCE": "SC-05 Vehicle imbalance",
}
SIMULATION_NUMBERS = (  # O6 form fields sent to M6 as typed; M6 checks them
    "surge_multiplier",
    "duration_minutes",
    "incoming_return_rate",
    "soc_threshold",
    "extra_drained_per_hub",
    "charge_minutes",
    "failure_offset_minutes",
    "mttr_minutes",
    "batch_size",
    "transit_delay_minutes",
    "time_horizon_minutes",
    "time_step_minutes",
    "random_seed",
)


def _simulation_page(
    request: Request,
    who: Principal,
    result: dict[str, Any] | None,
    form: dict[str, str],
    decisions: dict[str, str] | None = None,
) -> HTMLResponse:
    core = get_core(request)
    hubs = core.queries.list_hubs()
    points = [p for h in hubs for p in core.queries.list_charging_points(h.hub_id)]
    if result is not None:
        result["executed_at"] = datetime.fromisoformat(str(result["executed_at"]))
    return _page(
        request,
        "operator/simulation.html",
        who,
        result=result,
        result_json=json.dumps(result, default=str) if result else "",
        decisions=decisions or {},
        form=form,
        hubs=hubs,
        points=points,
        scenarios=SCENARIOS,
        scenario_names=SCENARIO_NAMES,
    )


@router.get("/operator/simulation")
def operator_simulation(request: Request) -> Response:
    """O6. What-if Simulation Lab of M6: the form, with no result yet ("Discard and reset")."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    return _simulation_page(request, who, None, {})


@router.post("/operator/simulation")
def operator_run_simulation(request: Request) -> Response:
    """O6. Run one of the five scenarios in M6 and show the result under the form."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    body: dict[str, Any] = {
        "simulation_id": f"SIM-{uuid4().hex[:12]}",  # the screen makes the ID, one for each run
        "scenario_id": form.get("scenario", ""),
        "target_hub_ids": read_form_list(request, "target_hub_ids"),
        "source_hub_ids": read_form_list(request, "source_hub_ids"),
        "destination_hub_ids": read_form_list(request, "destination_hub_ids"),
        "failed_charging_point_ids": read_form_list(request, "failed_charging_point_ids"),
    }
    for name in SIMULATION_NUMBERS:  # M6 reads the numbers from the typed text (422 if wrong)
        if form.get(name, "").strip():
            body[name] = form[name].strip()
    status, result = call(request, "POST", "/simulation/runs", json=body)
    if status != 200:
        return _refused(
            request, who, "run the simulation", status, result, "operator_simulation", "Back"
        )
    return _simulation_page(request, who, result, form)


@router.post("/operator/simulation/decide")
def simulation_decide(request: Request) -> Response:
    """O6. Approve a recommendation (M4 makes a RECOMMENDED task for O4) or reject it."""
    who = _check_login(request, Role.OPERATOR)
    if isinstance(who, Response):
        return who
    form = read_form(request)
    try:
        result = json.loads(form.get("result_json", ""))
        decisions = json.loads(form.get("decisions_json", "") or "{}")
        index = int(form.get("index", ""))
        rec = result["recommendations"][index]
    except (ValueError, KeyError, IndexError, TypeError):
        return _refused(
            request,
            who,
            "use this result",
            400,
            {"detail": "Run the simulation again."},
            "operator_simulation",
            "Back",
        )
    if form.get("decision") == "approve":
        body = {
            "task_id": f"TASK-SIM-{result['simulation_id'].removeprefix('SIM-')}-{index + 1}",
            "source_hub_id": rec["source_hub_id"],
            "target_hub_id": rec["destination_hub_id"],
            "quantity": rec["batch_size"],
            "reason": f"{result['simulation_id']}: {rec['reason']}",
        }
        status, data = call(request, "POST", "/allocation/tasks/from-recommendation", json=body)
        if status != 200:
            return _refused(
                request, who, "send this to Dispatch", status, data, "operator_simulation", "Back"
            )
        decisions[str(index)] = (
            f"Sent to Dispatch as {data['task_id']} ({data['quantity']} vehicles)"
        )
    else:
        decisions[str(index)] = "Rejected: nothing was sent"
    return _simulation_page(request, who, result, {}, decisions)
