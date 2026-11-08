from datetime import UTC, datetime, timedelta

from src.charging.models import ChargingRequest
from src.charging.service import ChargingQueueService


def test_battery_boundary_below_threshold():
    # Test SOC <= 15% triggers emergency mode
    req_below = ChargingRequest(
        request_id="REQ-001", vehicle_id="EV-101", station_id="ST-01", current_soc=14.9
    )
    assert req_below.is_emergency is True

    req_exact = ChargingRequest(
        request_id="REQ-002", vehicle_id="EV-102", station_id="ST-01", current_soc=15.0
    )
    assert req_exact.is_emergency is True


def test_battery_boundary_above_threshold():
    # Test SOC > 15% does not trigger emergency mode
    req_above = ChargingRequest(
        request_id="REQ-003", vehicle_id="EV-103", station_id="ST-01", current_soc=15.1
    )
    assert req_above.is_emergency is False


def test_priority_queue_sorting_order():
    # Verify priority queue sorting order (emergencies and lower SoC first)
    service = ChargingQueueService()

    req1 = ChargingRequest(request_id="R1", vehicle_id="V1", station_id="S1", current_soc=50.0)
    req2 = ChargingRequest(request_id="R2", vehicle_id="V2", station_id="S1", current_soc=30.0)
    req3 = ChargingRequest(request_id="R3", vehicle_id="V3", station_id="S1", current_soc=60.0)

    service.add_request(req1)
    service.add_request(req2)
    service.add_request(req3)

    first = service.pop_next_request()
    second = service.pop_next_request()
    third = service.pop_next_request()

    assert first is not None and first.request_id == "R2"
    assert second is not None and second.request_id == "R1"
    assert third is not None and third.request_id == "R3"


def test_priority_queue_fifo_tie_breaker():
    # Verify FIFO tie-breaker mechanism for identical SoC levels
    service = ChargingQueueService()

    t1 = datetime.now(UTC)
    t2 = t1 + timedelta(seconds=10)

    req1 = ChargingRequest(
        request_id="R1",
        vehicle_id="V1",
        station_id="S1",
        current_soc=40.0,
        requested_at=t1,
    )
    req2 = ChargingRequest(
        request_id="R2",
        vehicle_id="V2",
        station_id="S1",
        current_soc=40.0,
        requested_at=t2,
    )

    service.add_request(req2)
    service.add_request(req1)

    first = service.pop_next_request()
    second = service.pop_next_request()

    assert first is not None and first.request_id == "R1"
    assert second is not None and second.request_id == "R2"
