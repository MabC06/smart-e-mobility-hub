"""The Phase 2 UI prototype (src/ui): every screen opens and the flows can be clicked through.

The pages show ``ui.sample_data``, so these tests check what the prototype must show, not data
read from ``core`` (Phase 3). Each test names its TC, the technique (M8's
``test-technique-assignment.md``: M7 uses EP, DT, SEC, UX, INT), what it verifies and the
expected result. Role checks (SEC, NFR-16) need the real login of Phase 3.
"""

import dataclasses
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import main
from core.auth import AuthConfig
from core.config import CoreConfig
from core.repository.memory import InMemoryRepository
from ui import sample_data

KEY = "test-secret-key-0123456789"  # test data, not a real secret

STUDENT_PAGES = [
    "/ui/student/hubs",
    "/ui/student/hubs/H01/vehicles",
    "/ui/student/reserve?hub_id=H01&vehicle_id=F-0001",
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
def client():
    settings = main.Settings(core=CoreConfig(), auth=AuthConfig(KEY), log_level="WARNING")
    app = main.build_app(settings, InMemoryRepository(), module_names=("ui",))
    return TestClient(app)


def links(html: str) -> list[str]:
    """The targets of the links on a page (anchors inside the page left out)."""
    return re.findall(r'href="([^"#]+)"', html)


def form_action(html: str) -> str:
    """The target of the first form on a page; fails the test if the page has no form."""
    match = re.search(r'<form action="([^"]+)"', html)
    assert match is not None, "the page has no form"
    return match.group(1)


def test_site_opens_on_login_and_login_leads_to_each_home(client):
    """TC-M7-001 · INT · ``/`` opens S1; S1 leads the student to S2 and the operator to O1.

    Verifies: FR-01, FR-08
    Expected: ``/`` redirects to ``/ui/login``; S1 links to both home screens (ui-flow-diagrams).
    """
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/ui/login")
    targets = links(client.get("/ui/login").text)
    assert any(t.endswith("/ui/student/hubs") for t in targets)
    assert any(t.endswith("/ui/operator/overview") for t in targets)


@pytest.mark.parametrize("path", ["/ui/login", *STUDENT_PAGES, *OPERATOR_PAGES])
def test_every_screen_opens_as_a_page(client, path):
    """TC-M7-002 · UX · Every screen of the prototype opens as an HTML page.

    Verifies: FR-01, FR-02, FR-03, FR-08, FR-09, FR-10, FR-12, NFR-21
    Expected: 200, HTML, the "sample data" note on top, no stack trace.
    """
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Prototype (Phase 2)" in response.text
    assert "Traceback" not in response.text


def test_hub_list_shows_every_hub_with_its_free_spaces(client):
    """TC-M7-003 · INT · S2 lists every Hub with its numbers, the data time shown in ICT.

    Verifies: FR-01
    Expected: one row per Hub with "free of capacity"; 03:42:05 UTC is shown as 10:42:05.
    """
    html = client.get("/ui/student/hubs").text

    for hub in sample_data.HUBS:
        assert f"{hub.hub_id} {hub.name}" in html
        assert f"{hub.free_spaces} of {hub.parking_capacity}" in html
    assert 'Data as of <span id="as-of">10:42:05</span>' in html


@pytest.mark.parametrize(
    ("hub_id", "shown", "hidden"),
    [
        ("H01", ["FLEET-0001", "FLEET-0004"], ["FLEET-0005", "FLEET-0006"]),
        ("H02", ["FLEET-0051", "FLEET-0054"], ["FLEET-0052", "FLEET-0053", "PRIVATE-001"]),
        ("H03", [], []),
    ],
)
def test_student_sees_only_fleet_vehicles_that_can_be_rented(client, hub_id, shown, hidden):
    """TC-M7-004 · EP · S3 shows a student only fleet vehicles that are AVAILABLE.

    Classes: fleet AVAILABLE (shown); fleet CHARGING, RESERVED or MAINTENANCE (hidden);
    private (hidden); a Hub with none (empty state).
    Verifies: FR-02
    Expected: only the first class is listed; an empty Hub says so and offers another Hub.
    """
    html = client.get(f"/ui/student/hubs/{hub_id}/vehicles").text

    assert all(code in html for code in shown)
    assert not any(code in html for code in hidden)
    if not shown:
        assert "No vehicle can be rented at this Hub now" in html


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/ui/student/hubs/H99/vehicles", 404, "NOT_FOUND"),
        ("/ui/student/reserve", 400, "INVALID_INPUT"),
        ("/ui/student/reserve?hub_id=H01", 400, "INVALID_INPUT"),
        ("/ui/student/reserve?hub_id=H01&vehicle_id=F-9999", 400, "INVALID_INPUT"),
        ("/ui/operator/hubs/H99", 404, "NOT_FOUND"),
    ],
)
def test_wrong_input_gives_the_error_block(client, path, status, code):
    """TC-M7-005 · EP · Unknown IDs and missing choices show the error block S9 with a 4xx.

    Verifies: NFR-18, NFR-21
    Expected: the 4xx status, a cause, a link to go on, the code under "Details", no stack trace.
    """
    response = client.get(path)

    assert response.status_code == status
    assert 'class="error-block"' in response.text
    assert f"Details: {code}" in response.text
    assert 'class="button" href="http://testserver/ui/' in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize("path", OPERATOR_PAGES)
def test_alert_strip_shows_hubs_at_risk_and_incidents_on_every_operator_screen(client, path):
    """TC-M7-006 · DT · The alert strip lists the Hubs in CRITICAL or WARNING and the incidents.

    Rules: CRITICAL listed first, WARNING next; ACTIVE and MAINTENANCE not listed; the number of
    active incidents always shown.
    Verifies: NFR-20
    Expected: "■ H03 CRITICAL" before "▲ H02 WARNING", no H01/H04/H05, "Incidents: 2 active".
    """
    html = client.get(path).text
    strip = html[html.index('class="alert-strip"') : html.index("</p>", html.index("alert-strip"))]

    assert strip.index("■ H03 CRITICAL") < strip.index("▲ H02 WARNING")
    assert not any(hub_id in strip for hub_id in ("H01", "H04", "H05"))
    assert "Incidents: 2 active" in strip


@pytest.mark.parametrize(
    ("status", "buttons"),
    [
        ("RECOMMENDED", ["Approve"]),
        ("APPROVED", ["Confirm pick-up", "Cancel"]),
        ("IN_PROGRESS", ["Confirm delivery", "Cancel"]),
        ("COMPLETED", []),
        ("CANCELLED", []),
        ("REJECTED", []),
        ("FAILED", []),
    ],
)
def test_dispatch_offers_the_actions_the_task_status_allows(client, monkeypatch, status, buttons):
    """TC-M7-007 · DT · O4 shows on a task only the actions its status allows.

    Verifies: FR-10
    Expected: the listed buttons and no other of the four task actions.
    """
    task = dataclasses.replace(sample_data.DISPATCH_TASKS[0], status=status)
    monkeypatch.setattr(sample_data, "DISPATCH_TASKS", [task])

    html = client.get("/ui/operator/dispatch").text

    for action in ("Approve", "Confirm pick-up", "Confirm delivery", "Cancel"):
        assert (f">{action}</a>" in html) is (action in buttons)


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
def test_incidents_offer_the_actions_the_ticket_status_allows(client, monkeypatch, status, buttons):
    """TC-M7-008 · DT · O5 shows on a ticket only the actions its status allows.

    Verifies: FR-09
    Expected: the listed buttons and no other of Acknowledge, Resolve, Close.
    """
    ticket = dataclasses.replace(sample_data.INCIDENTS[0], status=status)
    monkeypatch.setattr(sample_data, "INCIDENTS", [ticket])

    html = client.get("/ui/operator/incidents").text

    for action in ("Acknowledge", "Resolve", "Close"):
        assert (f">{action}</a>" in html) is (action in buttons)


def test_main_paths_can_be_clicked_through(client):
    """TC-M7-009 · INT · The main paths of ui-flow-diagrams.md work by following the links.

    Student: S2 → S3 → S4 → S5 → S8 (after a return). Operator: O1 → O2 → O4.
    Verifies: FR-01, FR-02, FR-03, FR-08, FR-10
    Expected: each link or form found on a page opens the next screen with 200.
    """
    hubs = client.get("/ui/student/hubs").text
    s3 = next(t for t in links(hubs) if t.endswith("/ui/student/hubs/H01/vehicles"))
    vehicles = client.get(s3).text
    confirm = client.get(form_action(vehicles), params={"hub_id": "H01", "vehicle_id": "F-0001"})
    assert confirm.status_code == 200 and "Confirm your rental" in confirm.text
    bookings = client.get(form_action(confirm.text), params={"planned_minutes": "30"})
    assert bookings.status_code == 200 and "My bookings" in bookings.text
    s8 = next(t for t in links(bookings.text) if t.endswith("/ui/student/charging"))
    assert client.get(s8).status_code == 200

    overview = client.get("/ui/operator/overview").text
    o2 = next(t for t in links(overview) if t.endswith("/ui/operator/hubs/H02"))
    hub = client.get(o2).text
    o4 = next(t for t in links(hub) if t.endswith("/ui/operator/dispatch"))
    assert client.get(o4).status_code == 200


@pytest.mark.parametrize(
    ("changes", "shown", "not_shown"),
    [
        ({}, ["In progress", "Return the vehicle"], ["past the expected return time"]),
        (
            {
                "trip_status": "OVERDUE",
                "expected_return_at": sample_data.AS_OF - timedelta(minutes=20),
            },
            ["You are 20 minutes past the expected return time"],
            [],
        ),
    ],
)
def test_bookings_show_the_card_of_each_trip_state(client, monkeypatch, changes, shown, not_shown):
    """TC-M7-010 · EP · S5 shows the card that fits the trip: in progress, or overdue.

    Classes: trip IN_PROGRESS before the expected return; trip OVERDUE (20 minutes late).
    Verifies: FR-04
    Expected: the overdue warning, with the minutes late, only on the OVERDUE trip.
    """
    trip = dataclasses.replace(sample_data.BOOKINGS[1], **changes)
    monkeypatch.setattr(sample_data, "BOOKINGS", [trip])

    html = client.get("/ui/student/bookings").text

    assert all(text in html for text in shown)
    assert not any(text in html for text in not_shown)


def test_incidents_are_listed_most_severe_first_then_oldest(client, monkeypatch):
    """TC-M7-011 · UX · O5 lists tickets by severity, then by age (oldest first).

    Verifies: FR-09
    Expected: CRITICAL before HIGH before LOW; of two HIGH tickets the older one first.
    """
    base = sample_data.INCIDENTS[0]
    tickets = [
        dataclasses.replace(base, incident_id="INC-LOW", severity="LOW"),
        dataclasses.replace(base, incident_id="INC-HIGH-NEW", severity="HIGH"),
        dataclasses.replace(base, incident_id="INC-CRIT", severity="CRITICAL"),
        dataclasses.replace(
            base,
            incident_id="INC-HIGH-OLD",
            severity="HIGH",
            created_at=base.created_at - timedelta(minutes=30),
        ),
    ]
    monkeypatch.setattr(sample_data, "INCIDENTS", tickets)

    html = client.get("/ui/operator/incidents").text

    order = ["INC-CRIT", "INC-HIGH-OLD", "INC-HIGH-NEW", "INC-LOW"]
    positions = [html.index(f'href="#{ticket}"') for ticket in order]
    assert positions == sorted(positions)
