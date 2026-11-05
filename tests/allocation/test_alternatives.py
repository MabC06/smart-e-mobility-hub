"""Tests for Alternative Hub and Charging Providers (UC-M4-05, UC-M4-07, BR-M4-10, D-020)."""

import pytest

from allocation.alternatives import AlternativeChargingService, AlternativeHubService
from allocation.config import AllocationConfig
from core.actor import Actor
from core.domain.enums import Role, VehicleType
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, VehicleSpec, charging_point_id


@pytest.fixture
def network_core():
    """Create a minimal core facade seeded with three hubs for alternative testing."""
    core = CoreFacade(InMemoryRepository())
    admin = Actor("OP01", Role.OPERATOR, "core")

    spec = NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Hub 1",
                "Z1",
                5,
                2,
                vehicles=(VehicleSpec("V001", "P-V001", VehicleType.E_BIKE, 90.0),),
            ),
            HubSpec(
                "H02",
                "Hub 2",
                "Z2",
                5,
                1,
                vehicles=(VehicleSpec("V002", "P-V002", VehicleType.E_BIKE, 75.0),),
            ),
            HubSpec(
                "H03",
                "Hub 3",
                "Z3",
                5,
                1,
                vehicles=(VehicleSpec("V003", "P-V003", VehicleType.E_BIKE, 85.0),),
            ),
        )
    )
    res = core.commands.load_network(spec, admin)
    assert isinstance(res, Ok)
    return core


def test_suggest_alternative_hubs_ranks_by_closeness_and_battery(network_core):
    """UC-M4-05, BR-M4-10: Ranks hubs closer first, then battery."""
    distances = {
        ("H01", "H02"): 1,
        ("H01", "H03"): 3,
    }
    cfg = AllocationConfig(closeness_matrix=distances)
    service = AlternativeHubService(network_core, cfg)

    result = service.suggest_alternative_hubs(
        requested_hub_id="H01", vehicle_type=VehicleType.E_BIKE, limit=2
    )

    assert isinstance(result, Ok)
    candidates = result.value["candidates"]
    assert len(candidates) == 2
    # H02 is closer (distance 1) than H03 (distance 3)
    assert candidates[0]["hub_id"] == "H02"
    assert candidates[1]["hub_id"] == "H03"
    assert result.value["reason_code"] == "OK"


def test_suggest_alternative_hubs_no_vehicle_found(network_core):
    """UC-M4-05: Returns NO_VEHICLE when requested type is not available."""
    service = AlternativeHubService(network_core)
    result = service.suggest_alternative_hubs(
        requested_hub_id="H01", vehicle_type=VehicleType.E_MOTORCYCLE
    )

    assert isinstance(result, Ok)
    assert result.value["candidates"] == []
    assert result.value["reason_code"] == "NO_VEHICLE"


def test_find_alternative_charging_allocates_chargers(network_core):
    """UC-M4-07, BR-M4-10: Displaced charging requests find free chargers at nearest hubs."""
    distances = {
        ("H01", "H02"): 1,
        ("H01", "H03"): 2,
    }
    cfg = AllocationConfig(closeness_matrix=distances)
    service = AlternativeChargingService(network_core, cfg)

    displaced = [
        {"request_id": "REQ-1"},
        {"request_id": "REQ-2"},
    ]
    result = service.find_alternative_charging(displaced, failed_hub_id="H01")

    assert isinstance(result, Ok)
    allocated = result.value
    assert len(allocated) == 2
    # First request gets H02 charger (closer)
    assert allocated[0]["request_id"] == "REQ-1"
    assert allocated[0]["alternative_hub_id"] == "H02"
    assert allocated[0]["charging_point_id"] == charging_point_id("H02", 1)
    assert allocated[0]["status"] == "FOUND"

    # Second request gets H03 charger
    assert allocated[1]["request_id"] == "REQ-2"
    assert allocated[1]["alternative_hub_id"] == "H03"
    assert allocated[1]["charging_point_id"] == charging_point_id("H03", 1)
    assert allocated[1]["status"] == "FOUND"
