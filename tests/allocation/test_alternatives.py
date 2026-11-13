"""Tests for Alternative Hub and Charging Providers (UC-M4-05, UC-M4-07, BR-M4-10, D-020)."""

from datetime import UTC, datetime, timedelta

import pytest

from allocation.alternatives import AlternativeChargingService, AlternativeHubService
from allocation.config import AllocationConfig
from core.actor import Actor
from core.clock import FixedClock
from core.domain.enums import HolderKind, ResourceType, Role, VehicleType
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.providers import (
    AlternativeChargingProvider,
    AlternativeHubProvider,
    AlternativeHubRequest,
    DisplacedChargingRequest,
    ProviderPort,
)
from core.repository.memory import InMemoryRepository
from core.result import Err, Ok
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec, charging_point_id, space_id


@pytest.fixture
def network_core() -> CoreFacade:
    """Create a minimal core facade seeded with three hubs and a fixed clock."""
    fixed_now = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    core = CoreFacade(InMemoryRepository(), clock=FixedClock(fixed_now))
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
        ),
        users=(UserSpec("U01", "STU-01", Role.STUDENT),),
        private_vehicles=(
            VehicleSpec(
                "PV01",
                "PRIV-01",
                VehicleType.E_BIKE,
                88.0,
                owner_user_id="U01",
                connector_type="TYPE_2",
            ),
        ),
    )
    res = core.commands.load_network(spec, admin)
    assert isinstance(res, Ok)
    return core


def test_alternative_services_implement_core_provider_protocols(network_core: CoreFacade) -> None:
    """D-020, M4-4: M4 services register on ProviderRegistry using Core Protocol types."""
    hub_provider: AlternativeHubProvider = AlternativeHubService(network_core)
    charging_provider: AlternativeChargingProvider = AlternativeChargingService(network_core)

    network_core.register_provider(ProviderPort.ALTERNATIVE_HUB, hub_provider)
    network_core.register_provider(ProviderPort.ALTERNATIVE_CHARGING, charging_provider)

    hub_res = network_core.providers.call(
        ProviderPort.ALTERNATIVE_HUB,
        lambda p: p.suggest_alternative_hubs(AlternativeHubRequest(requested_hub_id="H01")),
    )
    assert isinstance(hub_res, Ok)
    assert hub_res.value.reason_code == "OK"
    assert len(hub_res.value.candidates) >= 1

    chg_res = network_core.providers.call(
        ProviderPort.ALTERNATIVE_CHARGING,
        lambda p: p.find_alternative_charging([DisplacedChargingRequest("REQ-1")], "H01"),
    )
    assert isinstance(chg_res, Ok)
    assert chg_res.value.alternatives[0].status == "FOUND"


def test_suggest_alternative_hubs_ranks_by_closeness_and_battery(network_core: CoreFacade) -> None:
    """UC-M4-05, BR-M4-10: Ranks hubs closer first, then resource count and battery."""
    distances = {
        ("H01", "H02"): 1,
        ("H01", "H03"): 3,
    }
    cfg = AllocationConfig(closeness_matrix=distances)
    service = AlternativeHubService(network_core, cfg)

    result = service.suggest_alternative_hubs(
        AlternativeHubRequest(requested_hub_id="H01", vehicle_type=VehicleType.E_BIKE, limit=2)
    )

    assert isinstance(result, Ok)
    candidates = result.value.candidates
    assert len(candidates) == 2
    assert candidates[0].hub_id == "H02"
    assert candidates[1].hub_id == "H03"
    assert result.value.reason_code == "OK"
    assert result.value.as_of == network_core.queries.get_config().as_of


def test_suggest_alternative_hubs_no_vehicle_found(network_core: CoreFacade) -> None:
    """UC-M4-05, BR-M4-10: Returns NO_VEHICLE when requested type is not available."""
    service = AlternativeHubService(network_core)
    result = service.suggest_alternative_hubs(
        AlternativeHubRequest(requested_hub_id="H01", vehicle_type=VehicleType.E_MOTORCYCLE)
    )

    assert isinstance(result, Ok)
    assert result.value.candidates == ()
    assert result.value.reason_code == "NO_VEHICLE"


def test_suggest_alternative_hubs_ignores_private_evs_and_expired_claims(
    network_core: CoreFacade,
) -> None:
    """BR-M4-03, D-017: Private EVs are not rentable; expired ACTIVE claims do not block."""
    actor = Actor("RES", Role.OPERATOR, "reservation")
    now = network_core.queries.get_config().as_of

    # Park private EV at H03 free space H03-S003 -> should NOT count as rentable E_BIKE at H03
    space_h03 = next(
        s for s in network_core.queries.list_spaces("H03") if s.parking_space_id == "H03-S003"
    )
    arr_res = network_core.commands.occupy_space("PV01", "H03-S003", space_h03.version, actor)
    assert isinstance(arr_res, Ok)

    # Claim H03's fleet vehicle V003 actively so only PV01 remains un-claimed there
    active_res = network_core.commands.place_claim(
        ResourceType.VEHICLE,
        "V003",
        HolderKind.RESERVATION,
        "R-ACT",
        now - timedelta(minutes=5),
        now + timedelta(minutes=15),
        actor,
    )
    assert isinstance(active_res, Ok)

    # Place an ALREADY-EXPIRED ACTIVE claim on V002 at H02 (end_at <= now): must NOT block V002
    expired_res = network_core.commands.place_claim(
        ResourceType.VEHICLE,
        "V002",
        HolderKind.RESERVATION,
        "R-EXP",
        now - timedelta(minutes=30),
        now - timedelta(minutes=1),
        actor,
    )
    assert isinstance(expired_res, Ok)

    service = AlternativeHubService(network_core)
    res = service.suggest_alternative_hubs(
        AlternativeHubRequest(requested_hub_id="H01", vehicle_type=VehicleType.E_BIKE)
    )
    assert isinstance(res, Ok)
    hub_ids = [c.hub_id for c in res.value.candidates]
    assert "H02" in hub_ids
    assert "H03" not in hub_ids


def test_suggest_alternative_hubs_validates_input(network_core: CoreFacade) -> None:
    """Rejects blank hub_id and non-positive limit."""
    service = AlternativeHubService(network_core)

    blank = service.suggest_alternative_hubs(AlternativeHubRequest(requested_hub_id="  "))
    assert isinstance(blank, Err)
    assert blank.code is ErrorCode.INVALID_INPUT

    bad_limit = service.suggest_alternative_hubs(
        AlternativeHubRequest(requested_hub_id="H01", limit=0)
    )
    assert isinstance(bad_limit, Err)
    assert bad_limit.code is ErrorCode.INVALID_INPUT


def test_find_alternative_charging_allocates_chargers(network_core: CoreFacade) -> None:
    """UC-M4-07, BR-M4-10: Displaced charging requests find free chargers at nearest hubs."""
    distances = {
        ("H01", "H02"): 1,
        ("H01", "H03"): 2,
    }
    cfg = AllocationConfig(closeness_matrix=distances)
    service = AlternativeChargingService(network_core, cfg)

    displaced = [
        DisplacedChargingRequest("REQ-1"),
        DisplacedChargingRequest("REQ-2"),
        DisplacedChargingRequest("REQ-3"),
    ]
    result = service.find_alternative_charging(displaced, hub_id="H01")

    assert isinstance(result, Ok)
    assert result.value.as_of == network_core.queries.get_config().as_of
    allocated = result.value.alternatives
    assert len(allocated) == 3

    assert allocated[0].request_id == "REQ-1"
    assert allocated[0].alternative_hub_id == "H02"
    assert allocated[0].charging_point_id == charging_point_id("H02", 1)
    assert allocated[0].status == "FOUND"

    assert allocated[1].request_id == "REQ-2"
    assert allocated[1].alternative_hub_id == "H03"
    assert allocated[1].charging_point_id == charging_point_id("H03", 1)
    assert allocated[1].status == "FOUND"

    assert allocated[2].request_id == "REQ-3"
    assert allocated[2].alternative_hub_id is None
    assert allocated[2].charging_point_id is None
    assert allocated[2].status == "NO_CHARGER"


def test_find_alternative_charging_skips_occupied_or_claimed_bays(
    network_core: CoreFacade,
) -> None:
    """D-007: Excludes charging points whose bay space is occupied or actively claimed."""
    actor = Actor("OP01", Role.OPERATOR, "core")
    now = network_core.queries.get_config().as_of

    # Occupy H02 bay space H02-S001 (1-1 with H02-CP01) with private EV PV01
    bay_h02 = next(
        s
        for s in network_core.queries.list_spaces("H02")
        if s.parking_space_id == space_id("H02", 1)
    )
    assert isinstance(
        network_core.commands.occupy_space(
            "PV01", bay_h02.parking_space_id, bay_h02.version, actor
        ),
        Ok,
    )

    # Also place an active claim on H03-CP01 -> no bay left free at H02 or H03
    assert isinstance(
        network_core.commands.place_claim(
            ResourceType.CHARGING_POINT,
            charging_point_id("H03", 1),
            HolderKind.CHARGING_SESSION,
            "CHG-1",
            now,
            now + timedelta(minutes=20),
            actor,
        ),
        Ok,
    )

    service = AlternativeChargingService(
        network_core, AllocationConfig(closeness_matrix={("H01", "H02"): 1, ("H01", "H03"): 2})
    )
    res = service.find_alternative_charging([DisplacedChargingRequest("REQ-1")], "H01")
    assert isinstance(res, Ok)
    assert res.value.alternatives[0].status == "NO_CHARGER"

    bad_hub = service.find_alternative_charging([DisplacedChargingRequest("REQ-1")], " ")
    assert isinstance(bad_hub, Err)
    assert bad_hub.code is ErrorCode.INVALID_INPUT
