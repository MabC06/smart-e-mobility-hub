"""load_network: a whole network, all or nothing, and the reference dataset DS-STD (A-11)."""

import random
from collections import Counter

import pytest

from core.actor import Actor
from core.clock import FixedClock
from core.domain.entities import (
    ChargingPoint,
    Hub,
    ParkingSpace,
    StateChangeRecord,
    UserAccount,
    Vehicle,
)
from core.domain.enums import Ownership, Role, SpaceStatus, VehicleState, VehicleType
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.repository.sql import SqlRepository
from core.result import Err, Ok
from core.seed import (
    HubSpec,
    NetworkSpec,
    UserSpec,
    VehicleSpec,
    charging_point_id,
    space_id,
)


def bike(vehicle_id, battery=80.0, **kw):
    return VehicleSpec(vehicle_id, f"PLATE-{vehicle_id}", VehicleType.E_BIKE, battery, **kw)


@pytest.fixture(params=["memory", "sql"])
def fresh(request, t0):
    """An empty core on each repository, with the actors that may load a network."""
    repo = InMemoryRepository() if request.param == "memory" else SqlRepository.open("sqlite://")
    core = CoreFacade(repo, FixedClock(t0))
    yield core, repo
    if isinstance(repo, SqlRepository):
        repo.close()


LOADER = Actor("SIM", Role.OPERATOR, "iot_sim")


def small_spec(**changes):
    hubs = (
        HubSpec(
            "H01",
            "Metro",
            "METRO",
            space_count=5,
            charging_point_count=2,
            vehicles=(bike("V001"), bike("V002"), bike("V003")),
        ),
        HubSpec("H02", "Dorm A", "DORM", space_count=3, charging_point_count=0),
    )
    users = (UserSpec("U1", "2452001", Role.STUDENT), UserSpec("OP1", "OP-1", Role.OPERATOR))
    private = (
        VehicleSpec(
            "P1",
            "PRIV-1",
            VehicleType.E_SCOOTER,
            55.0,
            1.0,
            owner_user_id="U1",
            connector_type="TYPE2",
        ),
    )
    fields = {"hubs": hubs, "users": users, "private_vehicles": private}
    fields.update(changes)
    return NetworkSpec(**fields)


def test_a_network_is_loaded_with_deterministic_ids_and_summary(fresh):
    core, repo = fresh

    result = core.commands.load_network(small_spec(), LOADER)

    assert isinstance(result, Ok)
    summary = result.value
    assert (summary.hubs, summary.parking_spaces, summary.charging_points) == (2, 8, 2)
    assert (summary.vehicles, summary.users) == (4, 2)
    assert [s.parking_space_id for s in repo.query(ParkingSpace, lambda s: s.hub_id == "H02")] == [
        "H02-S001",
        "H02-S002",
        "H02-S003",
    ]
    assert [p.charging_point_id for p in repo.query(ChargingPoint)] == ["H01-CP01", "H01-CP02"]
    assert space_id("H01", 3) == "H01-S003" and charging_point_id("H01", 2) == "H01-CP02"
    assert core.check_invariants() == []


def test_fleet_vehicles_fill_the_free_spaces_before_the_charging_bays(fresh):
    core, repo = fresh
    core.commands.load_network(small_spec(), LOADER)

    parked = {v.vehicle_id: v.parking_space_id for v in repo.query(Vehicle)}

    # H01 has bays in spaces 1 and 2, free spaces 3, 4, 5
    assert parked["V001"] == "H01-S003"
    assert parked["V002"] == "H01-S004"
    assert parked["V003"] == "H01-S005"
    bays = {p.parking_space_id for p in repo.query(ChargingPoint)}
    assert all(
        repo.get(ParkingSpace, bay).status is SpaceStatus.AVAILABLE for bay in bays
    )  # every bay is still free


def test_when_the_hub_is_nearly_full_vehicles_use_the_bays_last(fresh):
    core, repo = fresh
    spec = NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Metro",
                "METRO",
                3,
                1,
                vehicles=(bike("V1"), bike("V2"), bike("V3")),
            ),
        )
    )

    assert isinstance(core.commands.load_network(spec, LOADER), Ok)

    assert repo.get(Vehicle, "V3").parking_space_id == "H01-S001"  # the bay, used last
    assert core.check_invariants() == []


def test_private_vehicles_start_away_from_every_hub(fresh):
    core, repo = fresh
    core.commands.load_network(small_spec(), LOADER)

    private = repo.get(Vehicle, "P1")

    assert private.ownership is Ownership.PRIVATE
    assert (private.hub_id, private.parking_space_id) == (None, None)
    assert private.state is VehicleState.IN_USE
    assert private.owner_user_id == "U1" and private.connector_type == "TYPE2"
    assert repo.get(UserAccount, "OP1").role is Role.OPERATOR


def test_loading_writes_no_log_and_a_second_load_is_refused(fresh):
    core, repo = fresh
    assert isinstance(core.commands.load_network(small_spec(), LOADER), Ok)
    assert repo.query(StateChangeRecord) == []
    before = repo.export_state()

    again = core.commands.load_network(small_spec(), LOADER)

    assert isinstance(again, Err)
    assert again.code is ErrorCode.INVALID_INPUT
    assert repo.export_state() == before


def test_a_different_network_is_not_merged_into_a_loaded_one(fresh):
    core, repo = fresh
    assert isinstance(core.commands.load_network(small_spec(), LOADER), Ok)
    before = repo.export_state()
    other = NetworkSpec(hubs=(HubSpec("H09", "Library", "SERVICE", 4, 1),))

    result = core.commands.load_network(other, LOADER)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_INPUT
    assert "already loaded" in result.message
    assert repo.export_state() == before


def test_only_the_simulator_or_an_operator_may_load(fresh):
    core, repo = fresh

    by_student = core.commands.load_network(small_spec(), Actor("U1", Role.STUDENT, "reservation"))
    assert isinstance(by_student, Err) and by_student.code is ErrorCode.FORBIDDEN
    assert repo.query(Hub) == []

    by_operator = core.commands.load_network(small_spec(), Actor("OP1", Role.OPERATOR, "ui"))
    assert isinstance(by_operator, Ok)


BAD_SPECS = {
    "no hubs": dict(hubs=()),
    "duplicate hub ids": dict(
        hubs=(HubSpec("H01", "A", "Z", 2, 0), HubSpec("H01", "B", "Z", 2, 0))
    ),
    "duplicate hub names": dict(
        hubs=(HubSpec("H01", "A", "Z", 2, 0), HubSpec("H02", "A", "Z", 2, 0))
    ),
    "no spaces": dict(hubs=(HubSpec("H01", "A", "Z", 0, 0),)),
    "more charging points than spaces": dict(hubs=(HubSpec("H01", "A", "Z", 2, 3),)),
    "more vehicles than spaces": dict(
        hubs=(HubSpec("H01", "A", "Z", 1, 0, vehicles=(bike("V1"), bike("V2"))),)
    ),
    "duplicate vehicle ids": dict(
        hubs=(
            HubSpec("H01", "A", "Z", 3, 0, vehicles=(bike("V1"),)),
            HubSpec("H02", "B", "Z", 3, 0, vehicles=(bike("V1"),)),
        )
    ),
    "duplicate plates": dict(
        hubs=(
            HubSpec(
                "H01",
                "A",
                "Z",
                3,
                0,
                vehicles=(bike("V1"), VehicleSpec("V2", "PLATE-V1", VehicleType.E_BIKE, 50.0)),
            ),
        )
    ),
    "a parked vehicle with an owner": dict(
        hubs=(HubSpec("H01", "A", "Z", 3, 0, vehicles=(bike("V1", owner_user_id="U1"),)),)
    ),
    "battery out of range": dict(
        hubs=(HubSpec("H01", "A", "Z", 3, 0, vehicles=(bike("V1", battery=120.0),)),)
    ),
    "private vehicle without an owner": dict(
        private_vehicles=(VehicleSpec("P1", "PRIV", VehicleType.E_BIKE, 50.0, connector_type="T2"),)
    ),
    "private vehicle with an unknown owner": dict(
        private_vehicles=(
            VehicleSpec(
                "P1", "PRIV", VehicleType.E_BIKE, 50.0, owner_user_id="NOBODY", connector_type="T2"
            ),
        )
    ),
    "private vehicle without a connector": dict(
        private_vehicles=(VehicleSpec("P1", "PRIV", VehicleType.E_BIKE, 50.0, owner_user_id="U1"),)
    ),
    "duplicate users": dict(
        users=(UserSpec("U1", "A", Role.STUDENT), UserSpec("U1", "B", Role.STUDENT))
    ),
}


@pytest.mark.parametrize("label", sorted(BAD_SPECS))
def test_an_invalid_description_loads_nothing(fresh, label):
    core, repo = fresh

    result = core.commands.load_network(small_spec(**BAD_SPECS[label]), LOADER)

    assert isinstance(result, Err), label
    assert result.code is ErrorCode.INVALID_INPUT
    assert repo.query(Hub) == [] and repo.query(Vehicle) == [] and repo.query(UserAccount) == []


def test_a_failure_in_the_middle_of_the_load_leaves_an_empty_store(fresh, monkeypatch):
    core, repo = fresh
    original = repo.add
    calls = []

    def failing_add(entity):
        calls.append(type(entity).__name__)
        if type(entity).__name__ == "Vehicle":
            raise RuntimeError("disk full")
        original(entity)

    monkeypatch.setattr(repo, "add", failing_add)

    result = core.commands.load_network(small_spec(), LOADER)

    assert isinstance(result, Err) and result.code is ErrorCode.INTERNAL_ERROR
    assert "Hub" in calls  # hubs, spaces and users were added before the failure
    monkeypatch.undo()
    assert (
        repo.query(Hub) == [] and repo.query(ParkingSpace) == [] and repo.query(UserAccount) == []
    )


def test_the_same_description_gives_the_same_network(t0):
    ids = []
    for _ in range(2):
        core = CoreFacade(InMemoryRepository(), FixedClock(t0))
        assert isinstance(core.commands.load_network(small_spec(), LOADER), Ok)
        ids.append(core.snapshots.export_snapshot().snapshot_id)

    assert ids[0] == ids[1]


# --------------------------------------------------------------- reference dataset DS-STD

DS_STD_HUBS = [
    ("H01", "Metro", "METRO", 70, 10, 50),
    ("H02", "Dorm A", "DORM", 60, 10, 35),
    ("H03", "Dorm B", "DORM", 50, 8, 30),
    ("H04", "Dorm C", "DORM", 40, 6, 25),
    ("H05", "Campus A", "CAMPUS", 50, 8, 30),
    ("H06", "Campus B", "CAMPUS", 40, 6, 25),
    ("H07", "Campus C", "CAMPUS", 30, 4, 20),
    ("H08", "Library A", "SERVICE", 25, 4, 14),
    ("H09", "Library B", "SERVICE", 20, 3, 12),
    ("H10", "Library C", "SERVICE", 15, 2, 9),
]


def ds_std_spec(seed=0):
    """The reference dataset (reference-dataset.md) from its tables; M8 builds the real one."""
    rng = random.Random(seed)
    batteries = [90.0] * 150 + [50.0] * 63 + [20.0] * 37  # 60 %, 25 %, 15 % (within rounding)
    types = (
        [VehicleType.E_BIKE] * 125 + [VehicleType.E_SCOOTER] * 75 + [VehicleType.E_MOTORCYCLE] * 50
    )
    rng.shuffle(batteries)
    rng.shuffle(types)
    counter = iter(range(250))
    hubs = []
    for hub_id, name, zone, spaces, points, vehicles in DS_STD_HUBS:
        fleet = []
        for _ in range(vehicles):
            n = next(counter)
            fleet.append(VehicleSpec(f"V{n:03d}", f"RENT-{n:03d}", types[n], batteries[n]))
        hubs.append(HubSpec(hub_id, name, zone, spaces, points, vehicles=tuple(fleet)))
    users = tuple(UserSpec(f"S{i:04d}", f"24{i:05d}", Role.STUDENT) for i in range(1000)) + tuple(
        UserSpec(f"O{i}", f"OP-{i}", Role.OPERATOR) for i in range(5)
    )
    private = tuple(
        VehicleSpec(
            f"P{i:03d}",
            f"EV-{i:03d}",
            VehicleType.E_SCOOTER,
            60.0,
            1.2,
            owner_user_id=f"S{i:04d}",
            connector_type="TYPE2",
        )
        for i in range(100)
    )
    return NetworkSpec(tuple(hubs), users, private)


@pytest.mark.parametrize("kind", ["memory", "sql"])
def test_the_reference_dataset_loads_and_passes_its_sanity_checks(kind, t0):
    repo = InMemoryRepository() if kind == "memory" else SqlRepository.open("sqlite://")
    core = CoreFacade(repo, FixedClock(t0))
    try:
        result = core.commands.load_network(ds_std_spec(), LOADER)
        assert isinstance(result, Ok)

        # reference-dataset.md, section 7
        assert (result.value.parking_spaces, result.value.charging_points) == (400, 61)
        fleet = repo.query(Vehicle, lambda v: v.ownership is Ownership.FLEET)
        assert len(fleet) == 250
        for hub in core.queries.list_hubs():
            assert hub.occupied <= hub.parking_capacity
            assert hub.charging_points <= hub.parking_capacity
        high = sum(1 for v in fleet if v.battery_pct > 70)
        mid = sum(1 for v in fleet if 30 <= v.battery_pct <= 70)
        low = sum(1 for v in fleet if v.battery_pct < 30)
        assert high == 150 and abs(mid - 62.5) <= 1 and abs(low - 37.5) <= 1
        by_type = Counter(v.vehicle_type for v in fleet)
        assert by_type[VehicleType.E_BIKE] == 125 and by_type[VehicleType.E_MOTORCYCLE] == 50
        assert len(repo.query(Vehicle, lambda v: v.ownership is Ownership.PRIVATE)) == 100
        assert len(repo.query(UserAccount)) == 1005
        assert core.check_invariants() == []
    finally:
        if isinstance(repo, SqlRepository):
            repo.close()


def test_the_reference_dataset_is_repeatable(t0):
    ids = []
    for _ in range(2):
        core = CoreFacade(InMemoryRepository(), FixedClock(t0))
        assert isinstance(core.commands.load_network(ds_std_spec(seed=7), LOADER), Ok)
        ids.append(core.snapshots.export_snapshot().snapshot_id)

    assert ids[0] == ids[1]
