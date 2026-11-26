"""The UI (src/ui) in Phase 3: real login, and pages that read ``core``.

The network below is loaded into a real ``core`` behind the real application (``main.build_app``),
so the pages show what ``core`` holds, and the pages of M2 to M6 call those modules' routes.
Each test names its TC, the technique (M7 uses EP, DT, SEC,
UX, INT), what it verifies and the expected result.
"""

import re
from datetime import UTC, datetime, timedelta
from html import unescape as html_unescape

import pytest
from fastapi.testclient import TestClient

import main
from core.actor import Actor
from core.auth import AuthConfig, hash_password
from core.config import CoreConfig
from core.domain.enums import HubStatus, Role, VehicleType
from core.repository.memory import InMemoryRepository
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec
from ui import routes
from ui.api import explain

KEY = "test-secret-key-0123456789"  # test data, not a real secret
COST = 1000  # a cheap password-hash cost so the tests are fast
STUDENT = ("2452001", "pw-student")  # test accounts made below
OPERATOR = ("OP-1", "pw-operator")
SYSTEM = Actor("SIM", Role.OPERATOR, "iot_sim")

STUDENT_PAGES = [
    "/ui/student/hubs",
    "/ui/student/hubs/H01/vehicles",
    "/ui/student/reserve?hub_id=H01&vehicle_id=V1",
    "/ui/student/bookings",
    "/ui/student/parking",
    "/ui/student/vehicle",
    "/ui/student/charging",
]
OPERATOR_PAGES = [
    "/ui/operator/overview",
    "/ui/operator/hubs/H02",
    "/ui/operator/charging",
    "/ui/operator/dispatch",
    "/ui/operator/incidents",
    "/ui/operator/simulation",
]


@pytest.fixture
def app():
    """The application with ``ui`` and a small network: H01 (3 fleet, 1 private EV) and H02."""
    settings = main.Settings(
        core=CoreConfig(),
        auth=AuthConfig(KEY, token_minutes=30, hash_iterations=COST),
        log_level="WARNING",
    )
    modules = ("reservation", "charging", "allocation", "monitoring", "simulation", "ui")
    app = main.build_app(settings, InMemoryRepository(), module_names=modules)
    fleet = tuple(
        VehicleSpec(f"V{n}", f"RENT-{n}", VehicleType.E_BIKE, battery)
        for n, battery in ((1, 90.0), (2, 40.0), (3, 12.0))
    )
    private = (
        VehicleSpec(
            "P1", "EV-1", VehicleType.E_SCOOTER, 70.0, 1.0, owner_user_id="U1", connector_type="T2"
        ),
    )
    spec = NetworkSpec(
        hubs=(
            HubSpec("H01", "Metro", "METRO", 6, 2, vehicles=fleet),
            HubSpec("H02", "Dorm A", "DORM", 3, 0),
        ),
        users=(
            UserSpec("U1", STUDENT[0], Role.STUDENT, hash_password(STUDENT[1], COST)),
            UserSpec("OP1", OPERATOR[0], Role.OPERATOR, hash_password(OPERATOR[1], COST)),
        ),
        private_vehicles=private,
    )
    core = app.state.core
    assert isinstance(core.commands.load_network(spec, SYSTEM), Ok)
    assert isinstance(core.commands.occupy_space("P1", "H01-S002", 1, SYSTEM), Ok)
    return app


def sign_in(app, account) -> TestClient:
    """A browser (own cookie jar) signed in with the account."""
    browser = TestClient(app)
    data = {"code": account[0], "password": account[1]}
    assert browser.post("/ui/login", data=data, follow_redirects=False).status_code == 303
    return browser


@pytest.fixture
def student(app):
    return sign_in(app, STUDENT)


@pytest.fixture
def operator(app):
    return sign_in(app, OPERATOR)


def set_hub_status(app, hub_id: str, status: HubStatus) -> None:
    """What M5 does: store the status of a Hub."""
    core = app.state.core
    hub = core.queries.get_hub(hub_id).value
    actor = Actor("OP1", Role.OPERATOR, "monitoring")
    assert isinstance(core.commands.set_hub_status(hub_id, status, hub.version, actor), Ok)


def links(html: str) -> list[str]:
    """The targets of the links on a page (anchors inside the page left out)."""
    return re.findall(r'href="([^"#]+)"', html)


def form_action(html: str) -> str:
    """The target of the first form on a page; fails the test if the page has no form."""
    match = re.search(r'<form action="([^"]+)"', html)
    assert match is not None, "the page has no form"
    return match.group(1)


# ------------------------------------------------------------------------------------ login


@pytest.mark.parametrize(
    ("account", "home"),
    [(STUDENT, "/ui/student/hubs"), (OPERATOR, "/ui/operator/overview")],
)
def test_login_leads_each_role_to_its_home_screen(app, account, home):
    """TC-M7-001 · EP · A right code and password open the home screen of the account's role.

    Verifies: FR-01, NFR-16
    Expected: 303 to S2 (student) or O1 (operator), and a cookie that page scripts cannot read.
    """
    browser = TestClient(app)
    data = {"code": account[0], "password": account[1]}

    response = browser.post("/ui/login", data=data, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].endswith(home)
    assert "httponly" in response.headers["set-cookie"].lower()
    assert browser.get(home).status_code == 200


@pytest.mark.parametrize(
    ("code", "password"), [(STUDENT[0], "wrong"), ("nobody", STUDENT[1]), ("", "")]
)
def test_wrong_login_is_refused_with_one_message(app, code, password):
    """TC-M7-012 · EP · A wrong password, an unknown code or an empty form gives no token.

    Verifies: NFR-16, NFR-21
    Expected: 401, the same plain message for each case, no cookie, no stack trace.
    """
    response = TestClient(app).post("/ui/login", data={"code": code, "password": password})

    assert response.status_code == 401
    assert "The code or the password is wrong" in response.text
    assert "ui_token" not in response.headers.get("set-cookie", "")
    assert "Traceback" not in response.text


@pytest.mark.parametrize("path", [*STUDENT_PAGES, *OPERATOR_PAGES])
def test_every_page_needs_a_login(app, path):
    """TC-M7-013 · SEC · Without a token a page sends the browser to S1.

    Verifies: NFR-16
    Expected: 303 to ``/ui/login`` for each page of both roles.
    """
    response = TestClient(app).get(path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/login")


@pytest.mark.parametrize(
    ("who", "path", "message"),
    [
        ("student", "/ui/operator/overview", "This page is for operators."),
        ("operator", "/ui/student/hubs", "This page is for students."),
    ],
)
def test_a_role_cannot_open_the_pages_of_the_other_role(student, operator, who, path, message):
    """TC-M7-014 · SEC · A student cannot open operator pages and an operator not student pages.

    Verifies: NFR-16, NFR-21
    Expected: 403 with the error block (the cause and a link to the user's own home page).
    """
    browser = student if who == "student" else operator

    response = browser.get(path)

    assert response.status_code == 403
    assert message in response.text
    assert "Details: FORBIDDEN" in response.text
    assert "Go to your home page" in response.text


def test_logout_removes_the_token(student):
    """TC-M7-015 · SEC · After Logout the pages need a login again.

    Verifies: NFR-16
    Expected: the next page request is sent to S1.
    """
    student.get("/ui/logout", follow_redirects=False)

    after = student.get("/ui/student/hubs", follow_redirects=False)

    assert after.status_code == 303 and after.headers["location"].endswith("/ui/login")


# ------------------------------------------------------------------------------- screens


@pytest.mark.parametrize("path", STUDENT_PAGES)
def test_every_student_screen_opens(student, path):
    """TC-M7-002 · UX · Every student screen opens as an HTML page.

    Verifies: FR-01, FR-02, FR-03, NFR-21
    Expected: 200, HTML, the student's code in the header, no stack trace.
    """
    response = student.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert STUDENT[0] in response.text and "Traceback" not in response.text


@pytest.mark.parametrize("path", OPERATOR_PAGES)
def test_every_operator_screen_opens(operator, path):
    """TC-M7-016 · UX · Every operator screen opens as an HTML page.

    Verifies: FR-08, FR-09, FR-10, FR-12, NFR-21
    Expected: 200, HTML, the operator's code in the header, no stack trace.
    """
    response = operator.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert OPERATOR[0] in response.text and "Traceback" not in response.text


def test_hub_list_shows_the_hubs_of_core(student, app):
    """TC-M7-003 · INT · S2 lists every Hub that core holds, with its numbers.

    Verifies: FR-01
    Expected: one row per Hub with "free of capacity"; the footer shows the data time in ICT.
    """
    html = student.get("/ui/student/hubs").text

    for hub in app.state.core.queries.list_hubs():
        assert f"{hub.hub_id} {hub.name}" in html
        assert f"{hub.free_spaces} of {hub.parking_capacity}" in html
    assert re.search(r'Data as of <span id="as-of">\d\d:\d\d:\d\d</span>', html)


@pytest.mark.parametrize(
    ("hub_id", "shown", "hidden"),
    [("H01", ["RENT-1", "RENT-2"], ["EV-1", "RENT-3"]), ("H02", [], [])],
)
def test_student_sees_only_fleet_vehicles(student, hub_id, shown, hidden):
    """TC-M7-004 · EP · S3 lists M2's search: fleet vehicles a student can rent now.

    Verifies: FR-02
    Expected: fleet vehicles at 20% or more are listed; a private EV and RENT-3 (12%) are not;
    an empty Hub says so.
    """
    html = student.get(f"/ui/student/hubs/{hub_id}/vehicles").text

    assert all(code in html for code in shown)
    assert not any(code in html for code in hidden)
    if not shown:
        assert "No vehicle matches at this Hub now" in html


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/ui/student/hubs/H99/vehicles", 404, "NOT_FOUND"),
        ("/ui/student/reserve", 400, "INVALID_INPUT"),
        ("/ui/student/reserve?hub_id=H01&vehicle_id=V99", 400, "INVALID_INPUT"),
        ("/ui/student/reserve?hub_id=H01&vehicle_id=P1", 400, "INVALID_INPUT"),
    ],
)
def test_wrong_input_gives_the_error_block(student, path, status, code):
    """TC-M7-005 · EP · Unknown IDs, a missing choice and a private EV show the error block S9.

    Verifies: NFR-18, NFR-21
    Expected: the 4xx status, a cause, a link to go on, the code under "Details", no stack trace.
    A private vehicle is answered like an unknown one, so a student cannot find out it exists.
    """
    response = student.get(path)

    assert response.status_code == status
    assert 'class="error-block"' in response.text
    assert f"Details: {code}" in response.text
    assert 'class="button" href="http://testserver/ui/' in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize("path", OPERATOR_PAGES)
def test_alert_strip_shows_hubs_at_risk_on_every_operator_screen(operator, app, path):
    """TC-M7-006 · DT · The alert strip lists Hubs in CRITICAL or WARNING, most severe first.

    Verifies: UC-M7-07, NFR-20
    Expected: "■ H02 CRITICAL" before "▲ H01 WARNING", then "Incidents: 0 active".
    """
    set_hub_status(app, "H01", HubStatus.WARNING)
    set_hub_status(app, "H02", HubStatus.CRITICAL)

    html = operator.get(path).text
    strip = html[html.index('class="alert-strip"') : html.index("</p>", html.index("alert-strip"))]

    assert strip.index("■ H02 CRITICAL") < strip.index("▲ H01 WARNING")
    assert "Incidents: 0 active" in strip


def test_hub_detail_shows_every_vehicle_to_an_operator(operator):
    """TC-M7-017 · INT · O2 lists the vehicles, spaces and charging points of the Hub from core.

    Verifies: FR-01, FR-08, UC-M7-01
    Expected: fleet and private vehicles (operators see both), a space and a charging point of H01.
    """
    html = operator.get("/ui/operator/hubs/H01").text

    assert "RENT-1" in html and "EV-1" in html
    assert "H01-S002" in html and "H01-CP01" in html


def test_no_screen_shows_sample_data(student, operator):
    """TC-M7-018 · UX · No screen shows sample data or a Planned mark: every screen is connected.

    Verifies: NFR-21
    Expected: neither "Sample data" nor a Planned mark on any student or operator screen.
    """
    for path in STUDENT_PAGES:
        html = student.get(path).text
        assert "Sample data" not in html and 'class="planned"' not in html, path
    for path in OPERATOR_PAGES:
        html = operator.get(path).text
        assert "Sample data" not in html and 'class="planned"' not in html, path


# ------------------------------------------- screens that call the routes of M3, M4 and M5


def fake_call(monkeypatch, answers):
    """Make the pages see these answers from the other modules: ``{path: (status, json)}``.
    A path that is not listed answers 200 with an empty list."""

    def call(request, method, path, **options):
        return answers.get(path, (200, []))

    monkeypatch.setattr(routes, "call", call)


def a_task(status):
    """A dispatch task as M4's route answers it."""
    return {
        "task_id": "TASK-slot1-001",
        "source_hub_id": "H01",
        "target_hub_id": "H02",
        "vehicle_type": "E_BIKE",
        "quantity": 1,
        "assigned_vehicles": ["V1"],
        "status": status,
        "priority": 1,
        "reason": "Deficit at H02",
    }


def a_ticket(incident_id, severity="HIGH", status="OPEN", minutes_old=5):
    """An incident ticket as M5's route answers it."""
    created = datetime.now(UTC) - timedelta(minutes=minutes_old)
    return {
        "incident_id": incident_id,
        "incident_type": "INC-HW-01",
        "severity": severity,
        "status": status,
        "hub_id": "H02",
        "description": "Charging point H02-CP01 failed",
        "reported_by": "SYSTEM_HARDWARE_MONITOR",
        "assigned_operator_id": None,
        "resolution_notes": None,
        "created_at": created.isoformat(),
    }


def create_incident(operator) -> str:
    """Make a real ticket through M5's route, as the signed-in operator."""
    headers = {"Authorization": f"Bearer {operator.cookies['ui_token']}"}
    body = {
        "incident_type": "INC-HW-01",
        "severity": "CRITICAL",
        "hub_id": "H02",
        "entity_type": "CHARGING_POINT",
        "entity_id": "H02-CP01",
        "description": "Charging point H02-CP01 failed",
    }
    response = operator.post("/api/v1/monitoring/incidents", headers=headers, json=body)
    assert response.status_code == 201
    return response.json()["incident_id"]


@pytest.mark.parametrize(
    ("status", "buttons"),
    [
        ("RECOMMENDED", ["Approve"]),
        ("APPROVED", ["Confirm pick-up", "Cancel"]),
        ("IN_PROGRESS", ["Confirm delivery", "Cancel"]),
        ("COMPLETED", []),
        ("FAILED", []),
    ],
)
def test_dispatch_offers_the_actions_the_task_status_allows(operator, monkeypatch, status, buttons):
    """TC-M7-007 · DT · O4 shows on a task only the actions its status allows.

    Verifies: FR-10, UC-M7-06
    Expected: the listed buttons and no other of the four task actions.
    """
    fake_call(monkeypatch, {"/allocation/tasks": (200, [a_task(status)])})

    html = operator.get("/ui/operator/dispatch").text

    for action in ("Approve", "Confirm pick-up", "Confirm delivery", "Cancel"):
        assert (f">{action}</button>" in html) is (action in buttons)


@pytest.mark.parametrize(
    ("status", "buttons"),
    [
        ("OPEN", ["Acknowledge"]),
        ("ESCALATED", ["Acknowledge", "Resolve"]),
        ("IN_PROGRESS", ["Resolve"]),
        ("RESOLVED", ["Close"]),
        ("CLOSED", []),
    ],
)
def test_incidents_offer_the_actions_the_ticket_status_allows(
    operator, monkeypatch, status, buttons
):
    """TC-M7-008 · DT · O5 shows on a ticket only the actions its status allows.

    Verifies: FR-09, UC-M7-08
    Expected: the listed buttons and no other of Acknowledge, Resolve, Close.
    """
    answers = {"/api/v1/monitoring/incidents": (200, [a_ticket("INC-1", status=status)])}
    fake_call(monkeypatch, answers)

    html = operator.get("/ui/operator/incidents").text

    for action in ("Acknowledge", "Resolve", "Close"):
        assert (f">{action}</button>" in html) is (action in buttons)


def test_incidents_are_listed_most_severe_first_then_oldest(operator, monkeypatch):
    """TC-M7-011 · UX · O5 lists tickets by severity, then by age (oldest first).

    Verifies: FR-09, UC-M7-08
    Expected: CRITICAL before HIGH before LOW; of two HIGH tickets the older one first.
    """
    tickets = [
        a_ticket("INC-LOW", "LOW"),
        a_ticket("INC-HIGH-NEW", "HIGH"),
        a_ticket("INC-CRIT", "CRITICAL"),
        a_ticket("INC-HIGH-OLD", "HIGH", minutes_old=30),
    ]
    fake_call(monkeypatch, {"/api/v1/monitoring/incidents": (200, tickets)})

    html = operator.get("/ui/operator/incidents").text

    order = ["INC-CRIT", "INC-HIGH-OLD", "INC-HIGH-NEW", "INC-LOW"]
    positions = [html.index(f'href="#{ticket}"') for ticket in order]
    assert positions == sorted(positions)


def test_incident_goes_through_its_life_in_the_screen(operator):
    """TC-M7-019 · INT · An operator acknowledges, resolves and closes a ticket of M5 in O5.

    Verifies: FR-09, UC-M7-08
    Expected: after each button the ticket shows the next status; Resolve without notes is
    refused with M5's cause.
    """
    incident_id = create_incident(operator)
    acknowledge = f"/ui/operator/incidents/{incident_id}/acknowledge"
    resolve = f"/ui/operator/incidents/{incident_id}/resolve"
    close = f"/ui/operator/incidents/{incident_id}/close"

    assert "OPEN" in operator.get("/ui/operator/incidents").text
    assert operator.post(acknowledge).status_code == 200
    assert "IN_PROGRESS" in operator.get("/ui/operator/incidents").text
    refused = operator.post(resolve, data={"notes": ""})
    assert refused.status_code == 400 and 'class="error-block"' in refused.text
    assert operator.post(resolve, data={"notes": "Replaced the cable"}).status_code == 200
    assert "RESOLVED" in operator.get("/ui/operator/incidents").text
    assert operator.post(close).status_code == 200
    assert "CLOSED" in operator.get("/ui/operator/incidents").text


def test_active_incidents_are_counted_on_the_alert_strip(operator):
    """TC-M7-020 · DT · The alert strip counts the tickets that are not RESOLVED or CLOSED.

    Verifies: UC-M7-07, NFR-20
    Expected: "Incidents: 0 active" with no ticket, "Incidents: 1 active" after one is created.
    """
    assert "Incidents: 0 active" in operator.get("/ui/operator/overview").text

    create_incident(operator)

    assert "Incidents: 1 active" in operator.get("/ui/operator/overview").text


def test_a_refused_task_action_shows_the_cause_of_m4(operator):
    """TC-M7-021 · EP · A task that does not exist: the error block shows M4's code and cause.

    Verifies: FR-10, UC-M7-06, NFR-21
    Expected: an error block with "NOT_FOUND" and a link back, no stack trace.
    """
    response = operator.post("/ui/operator/dispatch/TASK-none/approve")

    assert response.status_code == 400
    assert "Details: NOT_FOUND" in response.text
    assert "Traceback" not in response.text


def test_dispatch_screen_asks_m4_for_new_tasks(operator):
    """TC-M7-022 · INT · O4 opens, and "Update recommendations" asks M4 to plan.

    M2 is installed, so M4 can read the demand and plan.
    Verifies: FR-10, UC-M7-05
    Expected: O4 opens (200); after the button O4 opens again with no error block.
    """
    assert operator.get("/ui/operator/dispatch").status_code == 200

    response = operator.post("/ui/operator/dispatch/plan")

    assert response.status_code == 200
    assert "Dispatch" in response.text and 'class="error-block"' not in response.text


def test_operator_sees_the_charging_queue_of_a_hub(operator):
    """TC-M7-023 · INT · O3 shows the charging points of core and the queue of M3.

    Verifies: FR-06, UC-M7-03
    Expected: H01 has 2 charging points, none in use; the empty queue is said in words.
    """
    html = operator.get("/ui/operator/charging?hub_id=H01").text

    assert "Charging points 2: in use 0" in html
    assert "No vehicle is waiting to charge at this Hub." in html


def test_student_saves_a_private_ev_and_a_duplicate_is_explained(student):
    """TC-M7-024 · EP · S7 saves a private EV through M3 and shows it; the same plate twice is
    refused with a cause.

    Verifies: FR-07, NFR-21
    Expected: the plate is listed after saving; the second save shows an error block.
    """
    form = {
        "plate_or_code": "59A-12345",
        "vehicle_type": "E_SCOOTER",
        "battery_capacity_kwh": "3.2",
        "current_soc": "70",
        "connector_type": "T2",
    }

    first = student.post("/ui/student/vehicle", data=form)
    second = student.post("/ui/student/vehicle", data=form)

    assert first.status_code == 200 and "59A-12345" in first.text
    # M3 answers a refused core command with a 500 today (src/charging/models.py maps an error
    # code that core does not have); the page must show the error block either way.
    assert second.status_code in (400, 502) and 'class="error-block"' in second.text
    assert "Traceback" not in second.text


def test_student_requests_charging_for_a_private_ev(student):
    """TC-M7-025 · INT · S8 sends "charge now" to M3 and lists the request.

    Verifies: FR-07
    Expected: after the request S8 opens again and lists the EV by its code (EV-1).
    """
    form = {"vehicle_id": "P1", "hub_id": "H01", "when": "now", "duration_minutes": "60"}

    response = student.post("/ui/student/charging", data=form)

    assert response.status_code == 200
    assert 'class="error-block"' not in response.text
    assert "<strong>EV-1 at H01</strong>" in response.text


def a_booking_on_a_trip(trip_status: str, minutes_left: int) -> dict:
    """M2's answer to GET /reservations/mine: one booking that is on a trip."""
    now = datetime.now(UTC)
    return {
        "bookings": [
            {
                "reservation_id": "RES-1",
                "vehicle_id": "V1",
                "origin_hub_id": "H01",
                "destination_hub_id": None,
                "confirmed_at": (now - timedelta(minutes=40)).isoformat(),
                "hold_expires_at": (now - timedelta(minutes=30)).isoformat(),
                "status": "ACTIVE",
            }
        ],
        "open_trips": [
            {
                "trip_id": "TRIP:RES-1",
                "reservation_id": "RES-1",
                "vehicle_id": "V1",
                "origin_hub_id": "H01",
                "picked_up_at": (now - timedelta(minutes=35)).isoformat(),
                "expected_return_at": (now + timedelta(minutes=minutes_left)).isoformat(),
                "status": trip_status,
            }
        ],
        "vehicle_versions": {"V1": 3},
        "parking": [],
    }


def test_a_student_cannot_use_the_operator_actions(student):
    """TC-M7-026 · SEC · The action routes of O4 and O5 are for operators only.

    Verifies: NFR-16
    Expected: 403 for a student on an incident action and on a dispatch action.
    """
    for path in ("/ui/operator/incidents/INC-1/acknowledge", "/ui/operator/dispatch/plan"):
        assert student.post(path).status_code == 403


def test_bookings_warn_when_the_trip_is_overdue(student, monkeypatch):
    """TC-M7-010 · EP · S5 warns a student whose trip is past the expected return time.

    Verifies: FR-04
    Expected: the warning, with the minutes late, only for the OVERDUE trip.
    """
    on_time = a_booking_on_a_trip("IN_PROGRESS", minutes_left=8)
    late = a_booking_on_a_trip("OVERDUE", minutes_left=-20)

    fake_call(monkeypatch, {"/reservations/mine": (200, on_time)})
    assert "past the expected return time" not in student.get("/ui/student/bookings").text
    fake_call(monkeypatch, {"/reservations/mine": (200, late)})
    html = student.get("/ui/student/bookings").text

    assert "You are 20 minutes past the expected return time" in html


def test_main_paths_can_be_clicked_through(student, operator):
    """TC-M7-009 · INT · The main paths of ui-flow-diagrams.md work by following the links.

    Student: S2 → S3 → S4 → S5 → S8. Operator: O1 → O2 → O4.
    Verifies: FR-01, FR-02, FR-03, FR-08, FR-10
    Expected: each link or form found on a page opens the next screen with 200.
    """
    hubs = student.get("/ui/student/hubs").text
    s3 = next(t for t in links(hubs) if t.endswith("/ui/student/hubs/H01/vehicles"))
    vehicles = student.get(s3).text
    confirm = student.get(form_action(vehicles), params={"hub_id": "H01", "vehicle_id": "V1"})
    assert confirm.status_code == 200 and "Confirm your rental" in confirm.text
    form = {"hub_id": "H01", "vehicle_id": "V1", "version": "1", "planned_minutes": "30"}
    bookings = student.post(form_action(confirm.text), data=form)
    assert bookings.status_code == 200 and "My bookings" in bookings.text
    s8 = next(t for t in links(bookings.text) if t.endswith("/ui/student/charging"))
    assert student.get(s8).status_code == 200

    overview = operator.get("/ui/operator/overview").text
    o2 = next(t for t in links(overview) if t.endswith("/ui/operator/hubs/H02"))
    hub = operator.get(o2).text
    o4 = next(t for t in links(hub) if t.endswith("/ui/operator/dispatch"))
    assert operator.get(o4).status_code == 200


@pytest.mark.parametrize(
    ("status", "data", "expected"),
    [
        (
            404,
            {"error": {"code": "NOT_FOUND", "message": "no such Hub"}},
            ("NOT_FOUND", "no such Hub"),
        ),
        (409, {"detail": {"code": "CONFLICT", "message": "taken"}}, ("CONFLICT", "taken")),
        (400, {"detail": "not allowed"}, ("400", "not allowed")),
        (422, {"detail": []}, ("INVALID_INPUT", "Check the values you entered and try again.")),
        (500, None, ("500", "The request was refused.")),
    ],
)
def test_every_answer_shape_of_the_modules_becomes_one_error_block(status, data, expected):
    """TC-M7-027 · EP · ``explain`` turns each shape of a refusal into (code, cause).

    Verifies: NFR-21
    Expected: the pair the error block S9 shows.
    """
    assert explain(status, data) == expected


# ------------------------------------------- screens that call the routes of M2 and M6


def reserve(student, app, vehicle_id="V1"):
    """Send the S4 form for a vehicle at H01, with the version core holds now."""
    version = app.state.core.queries.get_vehicle(vehicle_id).value.version
    form = {"hub_id": "H01", "vehicle_id": vehicle_id, "version": str(version)}
    return student.post("/ui/student/reserve", data={**form, "planned_minutes": "30"})


def test_student_reserves_and_cancels_a_vehicle(student, app):
    """TC-M7-028 · INT · S4 reserves through M2; S5 lists the booking and cancels it.

    Verifies: FR-03, FR-04, UC-M2-02, UC-M2-03
    Expected: after Confirm, S5 shows RENT-1 as Reserved; after Cancel it is listed under
    "Earlier bookings" as CANCELLED.
    """
    response = reserve(student, app)

    assert response.status_code == 200 and 'class="error-block"' not in response.text
    assert "RENT-1 · Reserved" in response.text
    reservation_id = re.search(r"Booking (RES-\w+)", response.text).group(1)

    response = student.post(f"/ui/student/bookings/{reservation_id}/cancel")

    assert "Earlier bookings" in response.text
    assert "RENT-1 · CANCELLED" in response.text and reservation_id in response.text


def test_student_picks_up_and_returns_a_vehicle(student, app):
    """TC-M7-029 · INT · S5 picks up a reserved vehicle and returns it to another Hub (M2).

    Verifies: FR-04, UC-M2-04, UC-M2-05
    Expected: after pick-up the booking is In progress; after the return to H02 it is COMPLETED
    and V1 is parked at H02 in core.
    """
    html = reserve(student, app).text
    reservation_id = re.search(r"Booking (RES-\w+)", html).group(1)
    version = re.search(r'name="version" value="(\d+)"', html).group(1)

    pickup = {"origin_hub_id": "H01", "version": version}
    html = student.post(f"/ui/student/bookings/{reservation_id}/pickup", data=pickup).text
    assert "RENT-1 · In progress" in html and 'class="error-block"' not in html
    version = re.search(r'name="version" value="(\d+)"', html).group(1)

    back = {"destination_hub_id": "H02", "version": version}
    html = student.post(f"/ui/student/bookings/{reservation_id}/return", data=back).text

    assert "RENT-1 · COMPLETED" in html
    assert app.state.core.queries.get_vehicle("V1").value.hub_id == "H02"


def test_a_refused_reservation_shows_the_cause_of_m2(student, app):
    """TC-M7-030 · EP · A second rental while one is open is refused with M2's code and cause.

    Verifies: FR-03, UC-M2-02, NFR-21
    Expected: an error block with "LIMIT_REACHED" and a link back, no stack trace.
    """
    assert "RENT-1 · Reserved" in reserve(student, app, "V1").text

    response = reserve(student, app, "V2")

    assert response.status_code == 400
    assert "Details: LIMIT_REACHED" in response.text
    assert "Traceback" not in response.text


SIMULATION_FORM = {
    "scenario": "SCENARIO_01_DEMAND_SURGE",
    "target_hub_ids": ["H01", "H02"],
    "surge_multiplier": "1.5",
    "duration_minutes": "60",
    "time_horizon_minutes": "120",
    "time_step_minutes": "5",
    "random_seed": "42",
}


def test_operator_runs_the_demand_surge_in_m6(operator):
    """TC-M7-031 · INT · O6 sends the form to M6 and shows its result under the form.

    Verifies: FR-12, UC-M7-09
    Expected: the rate with and without the plan and one row for each target Hub, no error block.
    """
    response = operator.post("/ui/operator/simulation", data=SIMULATION_FORM)

    assert response.status_code == 200 and 'class="error-block"' not in response.text
    assert "Vehicle shortage rate, do nothing" in response.text
    assert "With every recommendation" in response.text
    assert "<td>H01</td>" in response.text and "<td>H02</td>" in response.text


def test_a_wrong_simulation_value_shows_the_error_block(operator):
    """TC-M7-032 · EP · A surge multiplier below 1 is refused by M6 and explained.

    Verifies: FR-12, UC-M7-09, NFR-21
    Expected: 400 and an error block with INVALID_INPUT, no stack trace.
    """
    form = {**SIMULATION_FORM, "surge_multiplier": "0.5"}

    response = operator.post("/ui/operator/simulation", data=form)

    assert response.status_code == 400
    assert "Details: INVALID_INPUT" in response.text
    assert "Traceback" not in response.text


def test_each_role_can_use_only_its_own_new_actions(student, operator):
    """TC-M7-033 · SEC · Reserving is for students and running a simulation is for operators.

    Verifies: NFR-16
    Expected: 403 for an operator on S4 and S5 actions, and for a student on O6.
    """
    assert operator.post("/ui/student/reserve").status_code == 403
    assert operator.post("/ui/student/bookings/RES-1/cancel").status_code == 403
    assert student.post("/ui/operator/simulation").status_code == 403


# ------------------------------------------- PR 4: every Planned action connected


def private_ev_away(app):
    """P1 leaves H01, so its owner can book parking for it (what iot_sim reports)."""
    core = app.state.core
    space = next(s for s in core.queries.list_spaces("H01") if s.occupant_vehicle_id == "P1")
    assert isinstance(core.commands.free_space(space.parking_space_id, space.version, SYSTEM), Ok)


def test_vehicle_search_filters_by_type_and_battery(student):
    """TC-M7-034 · EP · S3 sends its filters to M2's search.

    Verifies: FR-02, UC-M2-01
    Expected: at least 50% leaves RENT-1 only; an E-scooter filter leaves no vehicle.
    """
    html = student.get("/ui/student/hubs/H01/vehicles", params={"min_battery": "50"}).text
    assert "RENT-1" in html and "RENT-2" not in html

    html = student.get("/ui/student/hubs/H01/vehicles", params={"type": "E_SCOOTER"}).text
    assert "No vehicle matches at this Hub now" in html


def test_student_holds_a_return_space_and_the_return_uses_it(student, app):
    """TC-M7-035 · INT · S5 holds a space at H02 during the trip; the return parks there.

    Verifies: FR-05, UC-M2-05, UC-M2-06, BR-M2-10
    Expected: S5 names the held space; after the return RENT-1 is in that space.
    """
    html = reserve(student, app).text
    reservation_id = re.search(r"Booking (RES-\w+)", html).group(1)
    version = re.search(r'name="version" value="(\d+)"', html).group(1)
    student.post(
        f"/ui/student/bookings/{reservation_id}/pickup",
        data={"origin_hub_id": "H01", "version": version},
    )

    html = student.post(
        f"/ui/student/bookings/{reservation_id}/hold", data={"destination_hub_id": "H02"}
    ).text
    space = re.search(r"Space (\S+) at H02 is held for you", html).group(1)
    version = re.search(r'name="version" value="(\d+)"', html).group(1)
    student.post(
        f"/ui/student/bookings/{reservation_id}/return",
        data={"destination_hub_id": "H02", "version": version},
    )

    assert app.state.core.queries.get_vehicle("V1").value.parking_space_id == space


def test_student_books_parking_arrives_and_leaves(student, app):
    """TC-M7-036 · INT · S6 books a space for the private EV, records arrival and departure.

    Verifies: FR-05, FR-07, UC-M2-06, UC-M2-07, UC-M2-08
    Expected: Booked, then Parked at H02, then listed under "Earlier parking" as COMPLETED; a
    second booking cancelled at once is CANCELLED.
    """
    private_ev_away(app)
    form = {"vehicle_id": "P1", "hub_id": "H02", "when": "now", "duration_minutes": "60"}
    html = student.post("/ui/student/parking", data=form).text
    assert "EV-1 · Space" in html and "· Booked" in html
    parking_id = re.search(r"Booking (PK-\w+)", html).group(1)
    version = re.search(r'name="version" value="(\d+)"', html).group(1)

    html = student.post(f"/ui/student/parking/{parking_id}/arrive", data={"version": version}).text
    assert "· Parked" in html
    assert app.state.core.queries.get_vehicle("P1").value.hub_id == "H02"
    version = re.search(r'name="version" value="(\d+)"', html).group(1)
    html = student.post(f"/ui/student/parking/{parking_id}/depart", data={"version": version}).text

    assert "EV-1 · H02 · COMPLETED" in html
    html = student.post("/ui/student/parking", data=form).text
    second = re.search(r"Booking (PK-\w+)", html).group(1)
    html = student.post(f"/ui/student/parking/{second}/cancel").text
    assert "EV-1 · H02 · CANCELLED" in html


def test_student_changes_and_cancels_a_charging_request(student):
    """TC-M7-037 · INT · S8 changes the time of a scheduled request, then cancels it (M3).

    Verifies: FR-06, FR-07, UC-M3-03
    Expected: the request is listed as Booked with its day and time; after "Change time" the new
    start is listed; after "Cancel" the request is CANCELLED; the Start field is for a later time.
    """
    start = (datetime.now(UTC) + timedelta(hours=3)).astimezone(routes.ICT)
    form = {
        "vehicle_id": "P1",
        "hub_id": "H01",
        "when": "schedule",
        "start_at": start.strftime("%Y-%m-%dT%H:%M"),
        "duration_minutes": "60",
    }
    html = student.post("/ui/student/charging", data=form).text
    request_id = re.search(r"/ui/student/charging/(REQ-\w+)/change", html).group(1)
    assert "● Booked</span> <strong>" + start.strftime("%a %d/%m") in html
    assert 'name="start_at" data-later-only' in html

    later = start + timedelta(hours=1)
    change = {"start_at": later.strftime("%Y-%m-%dT%H:%M"), "duration_minutes": "45"}
    html = student.post(f"/ui/student/charging/{request_id}/change", data=change).text
    assert 'class="error-block"' not in html and later.strftime("%H:%M") in html

    html = student.post(f"/ui/student/charging/{request_id}/cancel").text
    assert "CANCELLED" in html


def test_overview_filters_by_zone_and_status(operator):
    """TC-M7-038 · EP · O1 filters the Hub cards by zone and by status.

    Verifies: FR-01, FR-08, UC-M7-01
    Expected: zone DORM shows H02 only; status MAINTENANCE shows no Hub.
    """
    html = operator.get("/ui/operator/overview", params={"zone": "DORM"}).text
    assert "H02 Dorm A" in html and "H01 Metro" not in html

    html = operator.get("/ui/operator/overview", params={"status": "MAINTENANCE"}).text
    assert "No Hub matches" in html


def test_operator_controls_vehicles_points_and_the_hub(operator, app):
    """TC-M7-039 · ST · O2 reports a fault, records the repair, makes the vehicle available,
    sets a charging point out of service and closes and opens the Hub (core commands).

    Verifies: FR-01, FR-09, UC-M7-02, NFR-25
    Expected: RENT-2 goes MAINTENANCE, then back (core may make it AVAILABLE at once) and its
    history lists the changes;
    H01-CP01 is OUT_OF_SERVICE; H01 is MAINTENANCE, then ACTIVE; a stale version is refused.
    """
    core = app.state.core

    def post(path, **data):
        return operator.post(f"/ui/operator/hubs/H01/{path}", data=data)

    for action, states in (
        ("report_fault", {"MAINTENANCE"}),
        ("repair", {"RETURNED", "AVAILABLE"}),
    ):
        version = core.queries.get_vehicle("V2").value.version
        assert 'class="error-block"' not in post(f"vehicles/V2/{action}", version=version).text
        assert core.queries.get_vehicle("V2").value.state in states
    assert not core.queries.get_vehicle("V2").value.fault_flag
    html = operator.get("/ui/operator/hubs/H01", params={"vehicle": "V2"}).text
    assert "Last changes of V2" in html and "AVAILABLE → MAINTENANCE" in html

    def cp01():
        points = core.queries.list_charging_points("H01")
        return next(p for p in points if p.charging_point_id == "H01-CP01")

    post("points/H01-CP01", status="OUT_OF_SERVICE", version=cp01().version)
    assert cp01().status == "OUT_OF_SERVICE"

    post("status", status="MAINTENANCE", version=core.queries.get_hub("H01").value.version)
    assert core.queries.get_hub("H01").value.status == "MAINTENANCE"
    post("status", status="ACTIVE", version=core.queries.get_hub("H01").value.version)
    assert core.queries.get_hub("H01").value.status == "ACTIVE"
    stale = post("vehicles/V1/report_fault", version=0)
    assert stale.status_code == 400 and "Details: VERSION_CONFLICT" in stale.text


def test_operator_runs_the_charging_queue_and_sessions(operator, student):
    """TC-M7-040 · INT · O3 lists sessions with their actions and finishes a running one (M3).

    Verifies: FR-06, FR-11, UC-M7-03, UC-M7-04
    Expected: P1 charging now at H01 appears with Finish; after Finish it leaves the list; the
    rank column, the moved list and Optimize work.
    """
    form = {"vehicle_id": "P1", "hub_id": "H01", "when": "now", "duration_minutes": "60"}
    student.post("/ui/student/charging", data=form)

    html = operator.get("/ui/operator/charging", params={"hub_id": "H01"}).text
    assert "<th>Rank</th>" in html and "Moved after a charging-point failure" in html
    request_id = re.search(r"/sessions/(REQ-\w+)/finish", html).group(1)

    html = operator.post(f"/ui/operator/charging/H01/sessions/{request_id}/finish").text
    assert 'class="error-block"' not in html and f"/sessions/{request_id}/" not in html
    assert operator.post("/ui/operator/charging/H01/optimize").status_code == 200


def test_simulation_recommendation_goes_to_dispatch_and_can_be_rejected(operator, monkeypatch):
    """TC-M7-041 · INT · O6 runs SC-05; "Approve" makes a task in O4, where it is rejected.

    Verifies: FR-10, FR-12, UC-M7-06, UC-M7-09, UC-M7-10
    Expected: the result shows both rates and an export link; after Approve the recommendation
    says "Sent to Dispatch as TASK-SIM-..."; in O4 Reject makes that task REJECTED.
    """
    report = {  # M6's answer for SC-05; the small test network has too few vehicles to donate
        "simulation_id": "SIM-T",
        "scenario_id": "SCENARIO_05_VEHICLE_IMBALANCE",
        "snapshot_id": "SNAP-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "metric_name": "Vehicle shortage rate",
        "baseline_shortage_rate_pct": 80.0,
        "mitigated_shortage_rate_pct": 60.0,
        "hub_metrics": [
            {"hub_id": "H02", "total_requests": 10, "unmet_requests": 8, "shortage_rate_pct": 80.0}
        ],
        "mitigated_hub_metrics": [
            {"hub_id": "H02", "total_requests": 10, "unmet_requests": 6, "shortage_rate_pct": 60.0}
        ],
        "recommendations": [
            {
                "recommendation_type": "VEHICLE_REDISTRIBUTION",
                "source_hub_id": "H01",
                "destination_hub_id": "H02",
                "batch_size": 2,
                "reason": "Imbalance",
            }
        ],
    }
    real_call = routes.call

    def call(request, method, path, **options):
        if path == "/simulation/runs":
            return 200, dict(report)
        return real_call(request, method, path, **options)

    monkeypatch.setattr(routes, "call", call)
    html = operator.post("/ui/operator/simulation", data={"scenario": "SC-05"}).text
    assert "With every recommendation" in html and "Export report (JSON)" in html
    fields = re.findall(r'name="(result_json|decisions_json|index)" value="([^"]*)"', html)
    decide = {name: html_unescape(value) for name, value in fields}

    html = operator.post("/ui/operator/simulation/decide", data={**decide, "decision": "approve"})
    task_id = re.search(r"Sent to Dispatch as (TASK-SIM-[\w-]+)", html.text).group(1)
    html = operator.post(f"/ui/operator/dispatch/{task_id}/reject", data={"reason": "test"}).text

    assert f"{task_id} · H01 → H02 · REJECTED" in html


@pytest.mark.parametrize("scenario", ["SC-02", "SC-03", "SC-04"])
def test_every_other_scenario_runs_from_the_lab(operator, scenario):
    """TC-M7-042 · INT · O6 runs SC-02, SC-03 and SC-04 from the form.

    Verifies: FR-12, UC-M7-09
    Expected: 200 with the result block and no error block.
    """
    form = {
        "scenario": scenario,
        "target_hub_ids": ["H01"],
        "failed_charging_point_ids": ["H01-CP01"],
        "incoming_return_rate": "6",
        "extra_drained_per_hub": "5",
    }
    html = operator.post("/ui/operator/simulation", data=form).text
    assert 'class="error-block"' not in html and "Result · " in html


def test_dispatch_settings_and_incident_escalation_and_history(operator, monkeypatch):
    """TC-M7-043 · INT · O4 saves M4's settings; O5 escalates a ticket and shows its history.

    Verifies: FR-09, FR-10, UC-M7-08, NFR-25
    Expected: the minimum dispatch battery reads 35 after saving; Escalate sends the typed reason
    to M5's escalate route; the history lists the audit entry.
    """
    operator.post("/ui/operator/dispatch/settings", data={"min_dispatch_battery": "35"})
    assert 'name="min_dispatch_battery" value="35.0"' in operator.get("/ui/operator/dispatch").text

    sent = []
    log = {
        "previous_status": "OPEN",
        "new_status": "ESCALATED",
        "changed_by": "OP1",
        "action": "ESCALATE",
        "reason": "busy",
        "timestamp": datetime.now(UTC).isoformat(),
    }

    def call(request, method, path, **options):
        sent.append((method, path, options.get("json")))
        if path.endswith("/logs"):
            return 200, [log]
        if path == "/api/v1/monitoring/incidents":
            return 200, [a_ticket("INC-9")]
        return 200, []

    monkeypatch.setattr(routes, "call", call)
    operator.post("/ui/operator/incidents/INC-9/escalate", data={"reason": "busy"})
    html = operator.get("/ui/operator/incidents", params={"ticket": "INC-9"}).text

    assert ("POST", "/api/v1/monitoring/incidents/INC-9/escalate", {"reason": "busy"}) in sent
    assert "OPEN → ESCALATED · ESCALATE by OP1 · busy" in html


def test_new_actions_keep_to_their_role(student, operator):
    """TC-M7-044 · SEC · New student actions are for students, new operator actions for operators.

    Verifies: NFR-16
    Expected: 403 for an operator on S6 and S8 actions, and for a student on O2, O3, O4 and O6
    actions.
    """
    for path in ("/ui/student/parking", "/ui/student/charging/REQ-1/cancel"):
        assert operator.post(path).status_code == 403
    for path in (
        "/ui/operator/hubs/H01/vehicles/V1/report_fault",
        "/ui/operator/charging/H01/optimize",
        "/ui/operator/dispatch/settings",
        "/ui/operator/simulation/decide",
    ):
        assert student.post(path).status_code == 403


def test_student_screens_carry_the_phone_layout(student):
    """TC-M7-045 · UX · The student screens carry the phone rules of D-027.

    Verifies: NFR-21
    Expected: every student screen sets the viewport and links the versioned stylesheet; the
    stylesheet has the phone block (max-width 640 px) with 44 px targets and 16 px fields; S2
    lists Hubs as a stacked table with a label on each value.
    """
    for path in STUDENT_PAGES:
        html = student.get(path).text
        assert 'name="viewport" content="width=device-width, initial-scale=1"' in html, path
        assert re.search(r"/app\.css\?v=\d+", html), path
    css = student.get("/ui/static/app.css").text
    phone = css[css.index("@media (max-width: 640px)") :]
    assert "min-height: 44px" in phone and "font-size: 16px" in phone
    hubs = student.get("/ui/student/hubs").text
    assert '<table class="stack">' in hubs and 'data-label="Free spaces"' in hubs


def test_student_charges_now_and_finishes_on_s8(student, app):
    """TC-M7-046 · INT · S8 charges the parked EV now and finishes it; "now" is refused when away.

    Verifies: FR-06, FR-07, UC-M3-01, NFR-21
    Expected: with P1 parked in the bay of H01-CP02, "Now" starts charging and S8 offers
    "Finish charging", which completes the session. A "now" request at H02, where P1 is not
    parked, shows a refusal that says to book a space and record the arrival.
    """
    away = {"vehicle_id": "P1", "hub_id": "H02", "when": "now"}
    html = student.post("/ui/student/charging", data=away).text
    assert 'class="error-block"' in html and "record your arrival" in html

    html = student.post("/ui/student/charging", data={**away, "hub_id": "H01"}).text
    request_id = re.search(r"/ui/student/charging/(REQ-\w+)/finish", html).group(1)
    assert "● Charging</span> at point <strong>H01-CP02" in html

    html = student.post(f"/ui/student/charging/{request_id}/finish").text
    assert 'class="error-block"' not in html and "COMPLETED" in html
    assert app.state.core.queries.get_vehicle("P1").value.state.value == "AVAILABLE"


def test_s3_says_one_rental_at_a_time(student, app):
    """TC-M7-047 · UX · S3 tells a student with a live rental to finish it first.

    Verifies: BR-M2-03, NFR-21
    Expected: before a rental S3 offers "Reserve selected vehicle"; after reserving V1 it shows
    the one-rental notice with a link to My bookings and the button is disabled.
    """
    html = student.get("/ui/student/hubs/H01/vehicles").text
    assert "You already have a rental" not in html
    assert 'type="submit">Reserve selected vehicle' in html

    assert 'class="error-block"' not in reserve(student, app).text
    html = student.get("/ui/student/hubs/H01/vehicles").text
    assert "You already have a rental" in html and "/ui/student/bookings" in html
    assert 'type="submit" disabled>Reserve selected vehicle' in html
