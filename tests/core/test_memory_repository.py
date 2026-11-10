"""In-memory repository: copies, duplicates, optimistic locking, sorted queries."""

from collections.abc import Callable

import pytest

from core.domain.entities import Hub, ResourceClaim, Vehicle
from core.domain.enums import ClaimStatus, VehicleState
from core.repository.base import (
    DuplicateEntityError,
    EntityNotFoundError,
    VersionConflictError,
)
from core.repository.memory import InMemoryRepository


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


def test_get_returns_none_for_unknown_id(repo: InMemoryRepository) -> None:
    assert repo.get(Vehicle, "nope") is None


def test_add_then_get_returns_an_equal_copy(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    vehicle = make_vehicle("V001")
    repo.add(vehicle)

    loaded = repo.get(Vehicle, "V001")

    assert loaded == vehicle
    assert loaded is not vehicle


def test_changing_a_loaded_object_does_not_change_the_store(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    repo.add(make_vehicle("V001"))
    loaded = repo.get(Vehicle, "V001")
    assert loaded is not None

    loaded.state = VehicleState.MAINTENANCE

    again = repo.get(Vehicle, "V001")
    assert again is not None
    assert again.state is VehicleState.AVAILABLE


def test_changing_the_added_object_does_not_change_the_store(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    vehicle = make_vehicle("V001")
    repo.add(vehicle)

    vehicle.battery_pct = 1.0

    stored = repo.get(Vehicle, "V001")
    assert stored is not None
    assert stored.battery_pct == 80.0


def test_add_rejects_a_duplicate_id(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    repo.add(make_vehicle("V001"))

    with pytest.raises(DuplicateEntityError):
        repo.add(make_vehicle("V001"))


def test_update_bumps_the_version_and_writes_it_back(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    repo.add(make_vehicle("V001"))
    vehicle = repo.get(Vehicle, "V001")
    assert vehicle is not None
    vehicle.state = VehicleState.RESERVED

    repo.update(vehicle, expected_version=1)

    assert vehicle.version == 2
    stored = repo.get(Vehicle, "V001")
    assert stored is not None
    assert stored.version == 2
    assert stored.state is VehicleState.RESERVED


def test_stale_update_fails_and_changes_nothing(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    repo.add(make_vehicle("V001"))
    first = repo.get(Vehicle, "V001")
    second = repo.get(Vehicle, "V001")
    assert first is not None
    assert second is not None
    first.state = VehicleState.RESERVED
    repo.update(first, expected_version=1)

    second.state = VehicleState.MAINTENANCE
    with pytest.raises(VersionConflictError):
        repo.update(second, expected_version=1)

    stored = repo.get(Vehicle, "V001")
    assert stored is not None
    assert stored.state is VehicleState.RESERVED
    assert stored.version == 2


def test_update_of_an_unknown_entity_fails(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    with pytest.raises(EntityNotFoundError):
        repo.update(make_vehicle("V404"), expected_version=1)


def test_versioned_update_requires_an_expected_version(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    repo.add(make_vehicle("V001"))

    with pytest.raises(ValueError):
        repo.update(make_vehicle("V001"))


def test_claims_have_no_version_and_can_change_status(
    repo: InMemoryRepository, make_claim: Callable[..., ResourceClaim]
) -> None:
    repo.add(make_claim("C001"))
    claim = repo.get(ResourceClaim, "C001")
    assert claim is not None
    claim.status = ClaimStatus.RELEASED

    repo.update(claim)

    stored = repo.get(ResourceClaim, "C001")
    assert stored is not None
    assert stored.status is ClaimStatus.RELEASED


def test_unversioned_update_rejects_an_expected_version(
    repo: InMemoryRepository, make_claim: Callable[..., ResourceClaim]
) -> None:
    repo.add(make_claim("C001"))

    with pytest.raises(ValueError):
        repo.update(make_claim("C001"), expected_version=1)


def test_query_is_sorted_by_id_and_can_filter(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    for vehicle_id, battery in [("V003", 90.0), ("V001", 20.0), ("V002", 60.0)]:
        repo.add(make_vehicle(vehicle_id, battery_pct=battery))

    everything = repo.query(Vehicle)
    charged = repo.query(Vehicle, lambda v: v.battery_pct >= 50.0)

    assert [v.vehicle_id for v in everything] == ["V001", "V002", "V003"]
    assert [v.vehicle_id for v in charged] == ["V002", "V003"]


def test_tables_are_separate_per_entity_type(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    repo.add(make_vehicle("X1"))
    repo.add(Hub("X1", "Metro", "METRO", 70, 10))

    assert repo.get(Vehicle, "X1") is not None
    assert repo.get(Hub, "X1") is not None
    assert len(repo.query(Hub)) == 1


def test_export_and_import_state_restore_an_earlier_point(
    repo: InMemoryRepository, make_vehicle: Callable[..., Vehicle]
) -> None:
    repo.add(make_vehicle("V001"))
    saved = repo.export_state()

    repo.add(make_vehicle("V002"))
    vehicle = repo.get(Vehicle, "V001")
    assert vehicle is not None
    vehicle.state = VehicleState.MAINTENANCE
    repo.update(vehicle, expected_version=1)

    repo.import_state(saved)

    assert [v.vehicle_id for v in repo.query(Vehicle)] == ["V001"]
    restored = repo.get(Vehicle, "V001")
    assert restored is not None
    assert restored.state is VehicleState.AVAILABLE
    assert restored.version == 1
