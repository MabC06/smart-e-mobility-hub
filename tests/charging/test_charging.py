from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from charging import ChargingDemandProvider
from charging.models import ChargingRequest
from charging.service import ChargingQueueService
from core.config import CoreConfig
from core.providers import ScheduledChargingSessionRow
from core.result import Ok


def test_battery_boundary_below_threshold():
    # Test SOC <= 15% triggers emergency mode when created via service or configured
    config = CoreConfig()
    mock_core = MagicMock()
    mock_core.queries.get_config.return_value = config

    service = ChargingQueueService(core=mock_core)

    req_below = ChargingRequest(
        request_id="REQ-001", vehicle_id="EV-101", station_id="ST-01", current_soc=14.9
    )
    service.add_request(req_below)
    assert req_below.is_emergency is True

    req_exact = ChargingRequest(
        request_id="REQ-002", vehicle_id="EV-102", station_id="ST-01", current_soc=15.0
    )
    service.add_request(req_exact)
    assert req_exact.is_emergency is True


def test_battery_boundary_above_threshold():
    # Test SOC > 15% does not trigger emergency mode
    config = CoreConfig()
    mock_core = MagicMock()
    mock_core.queries.get_config.return_value = config

    service = ChargingQueueService(core=mock_core)

    req_above = ChargingRequest(
        request_id="REQ-003", vehicle_id="EV-103", station_id="ST-01", current_soc=15.1
    )
    service.add_request(req_above)
    assert req_above.is_emergency is False


def test_priority_queue_sorting_order():
    mock_core = MagicMock()
    mock_core.queries.get_config.return_value = CoreConfig()
    service = ChargingQueueService(core=mock_core)

    req1 = ChargingRequest(
        request_id="R1", vehicle_id="V1", station_id="S1", current_soc=50.0
    )
    req2 = ChargingRequest(
        request_id="R2", vehicle_id="V2", station_id="S1", current_soc=30.0
    )
    req3 = ChargingRequest(
        request_id="R3", vehicle_id="V3", station_id="S1", current_soc=60.0
    )

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
    mock_core = MagicMock()
    mock_core.queries.get_config.return_value = CoreConfig()
    service = ChargingQueueService(core=mock_core)

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


def test_charging_demand_provider_scheduled_sessions():
    mock_config = MagicMock()
    mock_config.as_of = datetime.now(UTC)
    mock_config.low_battery_threshold = 15.0

    mock_core = MagicMock()
    mock_core.queries.get_config.return_value = mock_config
    service = ChargingQueueService(core=mock_core)

    req = ChargingRequest(
        request_id="REQ-100",
        vehicle_id="EV-200",
        station_id="ST-01",
        current_soc=20.0,
        target_soc=80.0,
    )
    service.add_request(req)

    provider = ChargingDemandProvider(service)
    horizon = datetime.now(UTC) + timedelta(hours=2)
    result = provider.scheduled_sessions("hub-01", horizon)

    assert isinstance(result, Ok)
    sessions = result.value
    assert len(sessions) == 1
    assert isinstance(sessions[0], ScheduledChargingSessionRow)
    assert sessions[0].session_id == "REQ-100"
    assert sessions[0].vehicle_id == "EV-200"
