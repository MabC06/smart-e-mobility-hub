from datetime import UTC, datetime, timedelta

import pytest
from src.charging.models import ChargingRequest
from src.charging.service import ChargingQueueService


def test_battery_boundary_below_threshold():
    """Verify that battery levels at or below the 15% threshold (14.9% and 15.0%) trigger emergency mode."""
    req_below = ChargingRequest(
        request_id="REQ-001", vehicle_id="EV-101", station_id="ST-01", current_soc=14.9
    )
    req_at_edge = ChargingRequest(
        request_id="REQ-002", vehicle_id="EV-102", station_id="ST-01", current_soc=15.0
    )

    assert req_below.is_emergency is True
    assert req_at_edge.is_emergency is True


def test_battery_boundary_above_threshold():
    """Verify that battery levels above the 15% threshold (e.g., 15.1%) do not trigger emergency mode by default."""
    req_above = ChargingRequest(
        request_id="REQ-003", vehicle_id="EV-103", station_id="ST-01", current_soc=15.1
    )
    assert req_above.is_emergency is False


def test_priority_queue_sorting_order():
    """
    Verify the priority sorting order in the queue
    (prioritizing emergencies and lower battery levels).
    """

    service = ChargingQueueService()

    # High battery vehicle (80%)
    service.add_request(ChargingRequest("REQ-A", "EV-1", "ST-1", current_soc=80.0))
    # Emergency low battery vehicle (10%)
    service.add_request(ChargingRequest("REQ-B", "EV-2", "ST-1", current_soc=10.0))
    # Medium battery vehicle (30%)
    service.add_request(ChargingRequest("REQ-C", "EV-3", "ST-1", current_soc=30.0))

    # First popped item must be the emergency vehicle (REQ-B, 10%)
    first = service.pop_next_request()
    assert first is not None
    assert first.request_id == "REQ-B"

    # Next popped item must be the next lowest battery vehicle (REQ-C, 30%)
    second = service.pop_next_request()
    assert second is not None
    assert second.request_id == "REQ-C"

    # Finally, the high battery vehicle (REQ-A, 80%)
    third = service.pop_next_request()
    assert third is not None
    assert third.request_id == "REQ-A"


def test_invalid_soc_values_raise_error():
    """Verify that invalid SoC values (< 0 or > 100) raise a ValueError."""
    with pytest.raises(ValueError):
        ChargingRequest("ERR-1", "EV-99", "ST-1", current_soc=-1.0)

    with pytest.raises(ValueError):
        ChargingRequest("ERR-2", "EV-99", "ST-1", current_soc=105.0)


def test_duplicate_request_id_raises_error():
    """Verify that adding a duplicate request_id to the queue raises an error."""
    service = ChargingQueueService()
    req1 = ChargingRequest("REQ-DUP", "EV-1", "ST-1", current_soc=50.0)
    req2 = ChargingRequest("REQ-DUP", "EV-2", "ST-1", current_soc=60.0)

    service.add_request(req1)
    with pytest.raises(ValueError):
        service.add_request(req2)


def test_priority_queue_fifo_tie_breaker():
    """
    Verify the FIFO (First-In, First-Out) tie-breaker
    mechanism when vehicles share the same SoC level.
    """

    service = ChargingQueueService()

    t1 = datetime.now(UTC)
    t2 = t1 + timedelta(seconds=10)

    # Early request
    req_early = ChargingRequest("REQ-1", "EV-1", "ST-1", current_soc=40.0, requested_at=t1)
    # Late request with the same 40% battery level
    req_late = ChargingRequest("REQ-2", "EV-2", "ST-1", current_soc=40.0, requested_at=t2)

    # Add the later request first to test sorting order
    service.add_request(req_late)
    service.add_request(req_early)

    # The earlier request must be popped out first
    first = service.pop_next_request()
    assert first is not None
    assert first.request_id == "REQ-1"

    second = service.pop_next_request()
    assert second is not None
    assert second.request_id == "REQ-2"


def test_empty_queue_pop():
    """Verify that popping from an empty queue returns None without raising an error."""
    service = ChargingQueueService()
    assert service.pop_next_request() is None


def test_invalid_target_soc_raises_error():
    """Verify that invalid target_soc values (< 0 or > 100) raise a ValueError."""
    with pytest.raises(ValueError):
        ChargingRequest("ERR-3", "EV-99", "ST-1", current_soc=50.0, target_soc=-1.0)

    with pytest.raises(ValueError):
        ChargingRequest("ERR-4", "EV-99", "ST-1", current_soc=50.0, target_soc=101.0)
