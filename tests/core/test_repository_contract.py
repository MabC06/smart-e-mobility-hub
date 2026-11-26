"""The contract every Repository follows (see core/repository/base.py), run on both of them."""

import pytest

from core.domain.entities import Hub, ResourceClaim, Vehicle
from core.domain.enums import ClaimStatus, VehicleState
from core.repository.base import (
    DuplicateEntityError,
    EntityNotFoundError,
    VersionConflictError,
)
from core.repository.memory import InMemoryRepository
from core.repository.sql import SqlRepository


@pytest.fixture(params=["memory", "sql"])
def repo(request):
    repository = (
        InMemoryRepository() if request.param == "memory" else SqlRepository.open("sqlite://")
    )
    # the SQL schema has foreign keys: the hub every test vehicle may refer to
    repository.add(Hub("H01", "Metro", "METRO", 10, 0))
    yield repository
    if isinstance(repository, SqlRepository):
        repository.close()


def test_get_returns_none_for_an_unknown_id(repo):
    assert repo.get(Vehicle, "nope") is None


def test_add_then_get_returns_an_equal_copy(repo, make_vehicle):
    vehicle = make_vehicle("V001")
    repo.add(vehicle)

    loaded = repo.get(Vehicle, "V001")

    assert loaded == vehicle
    assert loaded is not vehicle


def test_changing_a_loaded_object_does_not_change_the_store(repo, make_vehicle):
    repo.add(make_vehicle("V001"))
    loaded = repo.get(Vehicle, "V001")
    loaded.state = VehicleState.MAINTENANCE

    assert repo.get(Vehicle, "V001").state is VehicleState.AVAILABLE


def test_changing_the_added_object_does_not_change_the_store(repo, make_vehicle):
    vehicle = make_vehicle("V001")
    repo.add(vehicle)
    vehicle.battery_pct = 1.0

    assert repo.get(Vehicle, "V001").battery_pct == 80.0


def test_add_rejects_a_duplicate_id(repo, make_vehicle):
    repo.add(make_vehicle("V001"))

    with pytest.raises(DuplicateEntityError):
        repo.add(make_vehicle("V001"))


def test_update_bumps_the_version_and_writes_it_back(repo, make_vehicle):
    repo.add(make_vehicle("V001"))
    vehicle = repo.get(Vehicle, "V001")
    vehicle.state = VehicleState.RESERVED

    repo.update(vehicle, expected_version=1)

    assert vehicle.version == 2
    stored = repo.get(Vehicle, "V001")
    assert (stored.version, stored.state) == (2, VehicleState.RESERVED)


def test_a_stale_update_fails_and_changes_nothing(repo, make_vehicle):
    repo.add(make_vehicle("V001"))
    first = repo.get(Vehicle, "V001")
    second = repo.get(Vehicle, "V001")
    first.state = VehicleState.RESERVED
    repo.update(first, expected_version=1)

    second.state = VehicleState.MAINTENANCE
    with pytest.raises(VersionConflictError):
        repo.update(second, expected_version=1)

    stored = repo.get(Vehicle, "V001")
    assert (stored.state, stored.version) == (VehicleState.RESERVED, 2)


def test_update_of_an_unknown_entity_fails(repo, make_vehicle):
    with pytest.raises(EntityNotFoundError):
        repo.update(make_vehicle("V404"), expected_version=1)


def test_versioned_update_needs_a_version_and_unversioned_must_not_have_one(
    repo, make_vehicle, make_claim
):
    repo.add(make_vehicle("V001"))
    repo.add(make_claim("C1", "V001"))

    with pytest.raises(ValueError):
        repo.update(make_vehicle("V001"))
    with pytest.raises(ValueError):
        repo.update(make_claim("C1", "V001"), expected_version=1)


def test_claims_can_change_status_without_a_version(repo, make_vehicle, make_claim):
    repo.add(make_vehicle("V001"))
    repo.add(make_claim("C1", "V001"))
    claim = repo.get(ResourceClaim, "C1")
    claim.status = ClaimStatus.RELEASED

    repo.update(claim)

    assert repo.get(ResourceClaim, "C1").status is ClaimStatus.RELEASED


def test_query_is_sorted_by_id_and_can_filter(repo, make_vehicle):
    for vehicle_id, battery in [("V003", 90.0), ("V001", 20.0), ("V002", 60.0)]:
        repo.add(make_vehicle(vehicle_id, battery_pct=battery))

    assert [v.vehicle_id for v in repo.query(Vehicle)] == ["V001", "V002", "V003"]
    assert [v.vehicle_id for v in repo.query(Vehicle, lambda v: v.battery_pct >= 50.0)] == [
        "V002",
        "V003",
    ]


def test_the_same_id_can_exist_in_two_entity_types(repo, make_vehicle):
    repo.add(make_vehicle("X1"))
    repo.add(Hub("X1", "Other", "OTHER", 5, 0))

    assert repo.get(Vehicle, "X1") is not None
    assert repo.get(Hub, "X1") is not None


def test_times_come_back_as_the_same_utc_instant(repo, make_vehicle, make_claim, t0):
    repo.add(make_vehicle("V001"))
    repo.add(make_claim("C1", "V001", 0, 90))

    loaded = repo.get(ResourceClaim, "C1")

    assert loaded.start_at == t0
    assert loaded.start_at.utcoffset().total_seconds() == 0
    assert (loaded.end_at - loaded.start_at).total_seconds() == 90 * 60


# --------------------------------------------------------------- transactions and counters


def test_rollback_undoes_every_write_of_the_transaction(repo, make_vehicle):
    repo.add(make_vehicle("V001"))

    repo.begin()
    repo.add(make_vehicle("V002"))
    vehicle = repo.get(Vehicle, "V001")
    vehicle.state = VehicleState.MAINTENANCE
    repo.update(vehicle, expected_version=1)
    repo.rollback()

    assert [v.vehicle_id for v in repo.query(Vehicle)] == ["V001"]
    assert repo.get(Vehicle, "V001").state is VehicleState.AVAILABLE


def test_commit_keeps_every_write_of_the_transaction(repo, make_vehicle):
    repo.begin()
    repo.add(make_vehicle("V001"))
    repo.add(make_vehicle("V002"))
    repo.commit()

    assert [v.vehicle_id for v in repo.query(Vehicle)] == ["V001", "V002"]


def test_only_one_transaction_can_be_open(repo):
    repo.begin()
    with pytest.raises(RuntimeError):
        repo.begin()
    repo.rollback()


def test_a_savepoint_undoes_only_what_came_after_it(repo, make_vehicle):
    repo.begin()
    repo.add(make_vehicle("V001"))
    savepoint = repo.savepoint()
    repo.add(make_vehicle("V002"))
    repo.rollback_to(savepoint)
    repo.commit()

    assert [v.vehicle_id for v in repo.query(Vehicle)] == ["V001"]


def test_a_released_savepoint_keeps_its_writes(repo, make_vehicle):
    repo.begin()
    savepoint = repo.savepoint()
    repo.add(make_vehicle("V001"))
    repo.release(savepoint)
    repo.commit()

    assert [v.vehicle_id for v in repo.query(Vehicle)] == ["V001"]


def test_the_version_counts_commits_not_writes_reads_or_rollbacks(repo, make_vehicle):
    start = repo.version()

    repo.add(make_vehicle("V001"))  # a write on its own is one commit
    assert repo.version() == start + 1

    repo.query(Vehicle)
    repo.get(Vehicle, "V001")
    assert repo.version() == start + 1

    repo.begin()
    repo.add(make_vehicle("V002"))
    vehicle = repo.get(Vehicle, "V001")
    repo.update(vehicle, expected_version=1)
    repo.commit()  # two writes, one commit
    assert repo.version() == start + 2

    repo.begin()
    repo.add(make_vehicle("V003"))
    repo.rollback()
    assert repo.version() == start + 2


def test_touched_and_changed_since(repo, make_vehicle):
    repo.add(make_vehicle("V001"))
    version = repo.version()

    repo.begin()
    vehicle = repo.get(Vehicle, "V001")
    repo.update(vehicle, expected_version=1)
    assert repo.touched() == frozenset({("Vehicle", "V001")})
    savepoint = repo.savepoint()
    repo.update(repo.get(Vehicle, "V001"), expected_version=2)
    repo.add(make_vehicle("V002"))
    assert ("Vehicle", "V002") in repo.touched()
    repo.rollback_to(savepoint)
    assert repo.touched() == frozenset({("Vehicle", "V001")})
    repo.commit()

    assert repo.touched() == frozenset()
    assert repo.changed_since(frozenset({("Vehicle", "V001")}), version) == [("Vehicle", "V001")]
    assert repo.changed_since(frozenset({("Vehicle", "V001")}), version + 1) == []
    assert repo.changed_since(frozenset({("Vehicle", "NEVER")}), 0) == []
    assert repo.changed_since(frozenset(), 0) == []
