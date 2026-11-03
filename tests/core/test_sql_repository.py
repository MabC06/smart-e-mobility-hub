"""What is specific to the SQLite repository: constraints, files, restarts, two connections."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError as SqlIntegrityError
from sqlalchemy.exc import OperationalError

from core.clock import FixedClock
from core.domain.entities import (
    ChargingPoint,
    Hub,
    ParkingSpace,
    ResourceClaim,
    UserAccount,
    Vehicle,
)
from core.domain.enums import (
    HolderKind,
    Ownership,
    ResourceType,
    Role,
    VehicleEvent,
    VehicleState,
    VehicleType,
)
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.repository.base import IntegrityViolationError, VersionConflictError
from core.repository.sql import SqlRepository
from core.result import Err, Ok
from core.services.commands import TransitionCtx

T0 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


@pytest.fixture
def db():
    repository = SqlRepository.open("sqlite://")
    repository.add(Hub("H01", "Metro", "METRO", 3, 1))
    repository.add(ParkingSpace("S01", "H01", "S01"))
    repository.add(ParkingSpace("S02", "H01", "S02"))
    repository.add(UserAccount("U1", "2452001", Role.STUDENT))
    yield repository
    repository.close()


def vehicle(vehicle_id="V001", **kw):
    fields = {
        "plate_or_code": f"CODE-{vehicle_id}",
        "ownership": Ownership.FLEET,
        "vehicle_type": VehicleType.E_BIKE,
        "battery_pct": 80.0,
        "battery_capacity_kwh": 0.5,
    }
    fields.update(kw)
    return Vehicle(vehicle_id, **fields)


def scalar(repo, sql):
    with repo._scope(write=False):
        return repo._conn.execute(text(sql)).scalar_one()


# ----------------------------------------------------------------------- the database's own rules


def test_foreign_keys_are_switched_on(db):
    assert scalar(db, "PRAGMA foreign_keys") == 1


def test_a_vehicle_cannot_refer_to_a_hub_or_space_that_does_not_exist(db):
    with pytest.raises(IntegrityViolationError):
        db.add(vehicle(hub_id="H99", parking_space_id="S01"))
    with pytest.raises(IntegrityViolationError):
        db.add(vehicle(hub_id="H01", parking_space_id="S99"))
    with pytest.raises(IntegrityViolationError):
        db.add(ParkingSpace("S90", "H99", "S90"))
    assert db.query(Vehicle) == []


def test_plate_space_and_bay_are_unique(db):
    db.add(vehicle("V001", hub_id="H01", parking_space_id="S01"))

    with pytest.raises(IntegrityViolationError):
        db.add(vehicle("V002", plate_or_code="CODE-V001"))
    with pytest.raises(IntegrityViolationError):
        db.add(vehicle("V003", hub_id="H01", parking_space_id="S01"))
    db.add(ChargingPoint("CP01", "H01", "S02", 11.0))
    with pytest.raises(IntegrityViolationError):
        db.add(ChargingPoint("CP02", "H01", "S02", 22.0))  # one charging point per bay (D-007)


def test_location_and_owner_must_be_paired(db):
    with pytest.raises(IntegrityViolationError):
        db.add(vehicle(hub_id="H01", parking_space_id=None))
    with pytest.raises(IntegrityViolationError):
        db.add(vehicle(owner_user_id="U1"))  # a fleet vehicle has no owner
    with pytest.raises(IntegrityViolationError):
        db.add(vehicle(ownership=Ownership.PRIVATE))  # a private vehicle has one
    db.add(vehicle("P1", ownership=Ownership.PRIVATE, owner_user_id="U1", connector_type="T2"))


def test_ranges_and_enumerations_are_checked(db):
    db.add(vehicle("V001"))
    loaded = db.get(Vehicle, "V001")
    loaded.battery_pct = 101.0
    with pytest.raises(IntegrityViolationError):
        db.update(loaded, expected_version=1)

    with (
        pytest.raises(SqlIntegrityError),
        db._scope(write=True),
    ):  # raw SQL, not through the repository
        db._conn.execute(text("UPDATE vehicles SET state = 'FLYING' WHERE vehicle_id = 'V001'"))
    hub = db.get(Hub, "H01")
    hub.parking_capacity = 0
    with pytest.raises(IntegrityViolationError):
        db.update(hub, expected_version=1)


def test_a_refused_write_changes_nothing_and_leaves_the_repository_usable(db):
    before = db.version()
    with pytest.raises(IntegrityViolationError):
        db.add(vehicle(hub_id="H99", parking_space_id="S01"))

    assert db.version() == before
    db.add(vehicle("V001"))
    assert db.get(Vehicle, "V001") is not None


def test_a_refusal_by_the_database_becomes_an_input_error_and_a_rollback(db):
    repo = db
    repo.add(Hub("H02", "Dorm", "DORM", 2, 0))
    repo.add(ParkingSpace("S11", "H02", "S11"))
    clock = FixedClock(T0)
    core = CoreFacade(repo, clock)
    original = repo.update

    def refusing(entity, expected_version=None):
        original(entity, expected_version)
        if isinstance(entity, ParkingSpace):
            raise IntegrityViolationError("injected")

    repo.update = refusing  # type: ignore[method-assign]
    registered = core.commands.register_vehicle(
        Ownership.FLEET,
        "BIKE-1",
        VehicleType.E_BIKE,
        0.5,
        80.0,
        _operator(),
        parking_space_id="S11",
    )

    assert isinstance(registered, Err)
    assert registered.code is ErrorCode.INVALID_INPUT
    assert repo.query(Vehicle) == []  # the vehicle that was added first was rolled back


def _operator():
    from core.actor import Actor

    return Actor("OP1", Role.OPERATOR, "ui")


# ------------------------------------------------------------------------------------- times


def test_a_time_with_an_offset_is_stored_as_the_same_utc_instant(db):
    db.add(vehicle("V001"))
    plus7 = timezone(timedelta(hours=7))
    start = datetime(2026, 11, 2, 15, 0, tzinfo=plus7)  # 08:00 UTC
    db.add(
        ResourceClaim(
            "C1",
            ResourceType.VEHICLE,
            "V001",
            HolderKind.RESERVATION,
            "R1",
            start,
            start + timedelta(minutes=10),
        )
    )

    loaded = db.get(ResourceClaim, "C1")

    assert loaded.start_at == T0
    assert loaded.start_at.tzinfo is not None
    assert loaded.start_at.utcoffset() == timedelta(0)
    assert scalar(db, "SELECT start_at FROM resource_claims").startswith("2026-11-02 08:00:00")


# ---------------------------------------------------------------- files, restarts, connections


def test_a_database_file_is_created_with_its_folder_and_uses_the_write_ahead_log(tmp_path):
    url = f"sqlite:///{tmp_path / 'data' / 'hub.db'}"

    repo = SqlRepository.open(url)
    try:
        assert (tmp_path / "data" / "hub.db").exists()
        assert scalar(repo, "PRAGMA journal_mode").lower() == "wal"
        assert scalar(repo, "PRAGMA foreign_keys") == 1
    finally:
        repo.close()


def test_opening_an_existing_database_twice_keeps_its_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    first = SqlRepository.open(url)
    first.add(Hub("H01", "Metro", "METRO", 3, 0))
    first.close()

    second = SqlRepository.open(url)  # create_schema must not wipe or fail
    try:
        assert second.get(Hub, "H01") is not None
        assert second.version() == 1
    finally:
        second.close()


def build_network(core_repo):
    core_repo.add(Hub("H01", "Metro", "METRO", 3, 0))
    for space in ("S01", "S02", "S03"):
        core_repo.add(ParkingSpace(space, "H01", space))


def test_state_survives_a_restart_and_the_rules_still_hold(tmp_path):
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    clock = FixedClock(T0)
    repo = SqlRepository.open(url)
    build_network(repo)
    core = CoreFacade(repo, clock)
    operator = _operator()
    registered = core.commands.register_vehicle(
        Ownership.FLEET, "BIKE-1", VehicleType.E_BIKE, 0.5, 90.0, operator, parking_space_id="S02"
    )
    assert isinstance(registered, Ok)
    claim = core.commands.place_claim(
        ResourceType.VEHICLE,
        registered.value.vehicle_id,
        HolderKind.RESERVATION,
        "R1",
        T0,
        T0 + timedelta(minutes=10),
        operator,
    )
    assert isinstance(claim, Ok)
    reserved = core.commands.transition_vehicle(
        registered.value.vehicle_id,
        VehicleEvent.RESERVE,
        1,
        operator,
        TransitionCtx(claim_id=claim.value.claim_id),
    )
    assert isinstance(reserved, Ok)
    version_before = repo.version()
    snapshot_before = core.snapshots.export_snapshot()
    repo.close()

    reopened = SqlRepository.open(url)
    try:
        again = CoreFacade(reopened, clock)
        view = again.queries.get_vehicle(registered.value.vehicle_id)
        assert isinstance(view, Ok)
        assert view.value.state is VehicleState.RESERVED
        assert view.value.version == 2
        assert reopened.version() == version_before
        assert again.snapshots.export_snapshot().snapshot_id == snapshot_before.snapshot_id
        assert again.check_invariants() == []
        assert len(again.queries.get_state_log(registered.value.vehicle_id)) == 2
    finally:
        reopened.close()


def test_two_connections_cannot_both_win_an_optimistic_update(tmp_path):
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    first = SqlRepository.open(url)
    first.add(Hub("H01", "Metro", "METRO", 3, 0))
    first.add(ParkingSpace("S01", "H01", "S01"))
    first.add(vehicle("V001", hub_id="H01", parking_space_id="S01"))
    second = SqlRepository.open(url)
    try:
        mine = first.get(Vehicle, "V001")
        theirs = second.get(Vehicle, "V001")
        mine.state = VehicleState.RESERVED
        first.update(mine, expected_version=1)

        theirs.state = VehicleState.MAINTENANCE
        with pytest.raises(VersionConflictError):
            second.update(theirs, expected_version=1)

        assert (
            second.get(Vehicle, "V001").state is VehicleState.RESERVED
        )  # sees the committed change
    finally:
        first.close()
        second.close()


def test_a_second_writer_waits_and_then_reports_a_locked_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    first = SqlRepository.open(url)
    second = SqlRepository.open(url, busy_timeout_ms=100)
    try:
        first.begin()  # takes the write lock
        with pytest.raises(OperationalError):
            second.begin()
        first.rollback()

        second.begin()  # free again
        second.rollback()
    finally:
        first.close()
        second.close()


def test_export_state_lists_every_entity_type(db):
    db.add(vehicle("V001"))

    state = db.export_state()

    assert set(state[Vehicle]) == {"V001"}
    assert set(state[Hub]) == {"H01"}
    assert state[ResourceClaim] == {}
