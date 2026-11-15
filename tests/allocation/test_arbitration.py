"""Tests for Arbitration of Competing Requests (FR-11.M4.1, BR-M4-01, UC-M4-06)."""

from datetime import UTC, datetime

from allocation.arbitration import ContenderRequest, RequestClass, settle_competing_requests


def test_higher_priority_class_always_wins():
    """BR-M4-01: Class priority 1 (operator emergency) beats class 2, which beats class 4, etc."""
    now = datetime(2026, 11, 5, 10, 0, 0, tzinfo=UTC)

    # Class 4 (scheduled charging) arrived earlier
    early_charging = ContenderRequest(
        request_id="REQ-01",
        request_class=RequestClass.SCHEDULED_CHARGING,
        requested_at=datetime(2026, 11, 5, 9, 50, 0, tzinfo=UTC),
        requester_id="U001",
        target_resource_id="BAY-01",
    )
    # Class 2 (confirmed reservation) arrived later
    late_reservation = ContenderRequest(
        request_id="REQ-02",
        request_class=RequestClass.CONFIRMED_RESERVATION_SOON,
        requested_at=now,
        requester_id="U002",
        target_resource_id="BAY-01",
    )

    result = settle_competing_requests([early_charging, late_reservation])

    assert result is not None
    assert result.winner.request_id == "REQ-02"
    assert len(result.displaced) == 1
    assert result.displaced[0].request_id == "REQ-01"


def test_same_class_resolved_by_first_come_first_served():
    """BR-M4-01: When classes are identical, earlier requested_at wins."""
    req_earlier = ContenderRequest(
        request_id="REQ-EARLY",
        request_class=RequestClass.WALK_IN_RENTAL,
        requested_at=datetime(2026, 11, 5, 10, 0, 0, tzinfo=UTC),
        requester_id="U001",
        target_resource_id="V001",
    )
    req_later = ContenderRequest(
        request_id="REQ-LATE",
        request_class=RequestClass.WALK_IN_RENTAL,
        requested_at=datetime(2026, 11, 5, 10, 5, 0, tzinfo=UTC),
        requester_id="U002",
        target_resource_id="V001",
    )

    result = settle_competing_requests([req_later, req_earlier])

    assert result is not None
    assert result.winner.request_id == "REQ-EARLY"
    assert result.displaced[0].request_id == "REQ-LATE"


def test_identical_class_and_time_tie_break_by_id():
    """NFR-13: Identical class and timestamp are deterministically broken by request_id."""
    same_time = datetime(2026, 11, 5, 10, 0, 0, tzinfo=UTC)
    req_b = ContenderRequest(
        request_id="REQ-B",
        request_class=RequestClass.AD_HOC_CHARGING,
        requested_at=same_time,
        requester_id="U002",
        target_resource_id="CP01",
    )
    req_a = ContenderRequest(
        request_id="REQ-A",
        request_class=RequestClass.AD_HOC_CHARGING,
        requested_at=same_time,
        requester_id="U001",
        target_resource_id="CP01",
    )

    result = settle_competing_requests([req_b, req_a])

    assert result is not None
    assert result.winner.request_id == "REQ-A"
    assert result.displaced[0].request_id == "REQ-B"


def test_empty_requests_returns_none():
    assert settle_competing_requests([]) is None
