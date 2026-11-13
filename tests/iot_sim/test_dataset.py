"""DS-STD generation tests — TC-M8-001 to TC-M8-006."""

from collections import Counter

from core.domain.enums import VehicleType
from core.seed import validate_network
from iot_sim import build_network_spec


def test_ds_std_totals_and_hub_profiles() -> None:
    spec = build_network_spec(42)
    assert len(spec.hubs) == 10
    assert sum(h.space_count for h in spec.hubs) == 400
    assert sum(h.charging_point_count for h in spec.hubs) == 61
    assert sum(len(h.vehicles) for h in spec.hubs) == 250
    assert len(spec.users) == 1005
    assert len(spec.private_vehicles) == 100
    assert validate_network(spec) is None


def test_rental_vehicle_battery_bands_match_reference_dataset() -> None:
    fleet = [v for hub in build_network_spec(42).hubs for v in hub.vehicles]
    high = sum(v.battery_pct > 70 for v in fleet)
    medium = sum(30 <= v.battery_pct <= 70 for v in fleet)
    low = sum(v.battery_pct < 30 for v in fleet)
    assert (high, medium, low) == (150, 62, 38)


def test_rental_vehicle_type_distribution_matches_reference_dataset() -> None:
    fleet = [v for hub in build_network_spec(42).hubs for v in hub.vehicles]
    counts = Counter(v.vehicle_type for v in fleet)
    assert counts == {
        VehicleType.E_BIKE: 125,
        VehicleType.E_SCOOTER: 75,
        VehicleType.E_MOTORCYCLE: 50,
    }


def test_same_seed_produces_equal_network_spec() -> None:
    assert build_network_spec(7) == build_network_spec(7)


def test_different_seed_changes_battery_values_but_not_network_shape() -> None:
    first = build_network_spec(7)
    second = build_network_spec(8)
    assert first != second
    assert [h.hub_id for h in first.hubs] == [h.hub_id for h in second.hubs]


def test_negative_seed_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="non-negative"):
        build_network_spec(-1)
