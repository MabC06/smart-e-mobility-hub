"""A module's own records join core's transactions (core-api-spec.md, 5.2).

``DemoBooking`` stands in for a record of M2 or M4. The same tests run on both repositories.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table

from core.domain.enums import HubStatus
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.repository.base import (
    DuplicateEntityError,
    IntegrityViolationError,
    UnknownEntityError,
    VersionConflictError,
)
from core.repository.schema import TableSpec, metadata
from core.repository.sql import SqlRepository
from core.result import Err, Ok


class BookingStatus(StrEnum):
    HELD = "HELD"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class DemoBooking:
    ID_FIELD: ClassVar[str] = "booking_id"
    VERSIONED: ClassVar[bool] = True

    booking_id: str
    vehicle_id: str
    status: BookingStatus = BookingStatus.HELD
    version: int = 1


demo_bookings = Table(
    "demo_bookings",
    metadata,  # core's metadata, so the foreign key to vehicles resolves
    Column("booking_id", String, primary_key=True),
    Column("vehicle_id", String, ForeignKey("vehicles.vehicle_id"), nullable=False),
    Column("status", String, nullable=False),
    Column("version", Integer, nullable=False),
)
BOOKING = TableSpec(DemoBooking, demo_bookings, "booking_id", {"status": BookingStatus}, True)


@pytest.fixture
def booked(world):
    world.core.register_entity(BOOKING)
    world.park("V001", "S02")
    return world


def hub_version(world) -> int:
    hub = world.core.queries.get_hub("H01")
    assert isinstance(hub, Ok)
    return hub.value.version


def hub_status(world) -> HubStatus:
    hub = world.core.queries.get_hub("H01")
    assert isinstance(hub, Ok)
    return hub.value.status


def add_booking(world, booking_id="B1") -> None:
    with world.core.unit_of_work() as uow:
        uow.repository.add(DemoBooking(booking_id, "V001"))
        assert isinstance(uow.commit(), Ok)


# ------------------------------------------------------------------ one transaction


def test_a_module_record_and_a_core_change_commit_together(booked):
    with booked.core.unit_of_work() as uow:
        uow.repository.add(DemoBooking("B1", "V001"))
        changed = uow.commands.set_hub_status(
            "H01", HubStatus.WARNING, hub_version(booked), booked.operator
        )
        assert isinstance(changed, Ok)
        assert isinstance(uow.commit(), Ok)

    assert booked.core.get_entity(DemoBooking, "B1") == DemoBooking("B1", "V001")
    assert hub_status(booked) is HubStatus.WARNING


def test_leaving_the_unit_without_commit_undoes_both(booked):
    with booked.core.unit_of_work() as uow:
        uow.repository.add(DemoBooking("B1", "V001"))
        uow.commands.set_hub_status("H01", HubStatus.WARNING, hub_version(booked), booked.operator)

    assert booked.core.get_entity(DemoBooking, "B1") is None
    assert hub_status(booked) is HubStatus.ACTIVE


def test_an_exception_undoes_both(booked):
    with pytest.raises(RuntimeError), booked.core.unit_of_work() as uow:
        uow.commands.set_hub_status("H01", HubStatus.WARNING, hub_version(booked), booked.operator)
        uow.repository.add(DemoBooking("B1", "V001"))
        raise RuntimeError("the module failed after writing")

    assert booked.core.query_entities(DemoBooking) == []
    assert hub_status(booked) is HubStatus.ACTIVE


def test_a_rejected_core_command_followed_by_rollback_leaves_nothing(booked):
    with booked.core.unit_of_work() as uow:
        uow.repository.add(DemoBooking("B1", "V001"))
        refused = uow.commands.set_hub_status("H01", HubStatus.WARNING, 99, booked.operator)
        assert isinstance(refused, Err) and refused.code is ErrorCode.VERSION_CONFLICT
        uow.rollback()

    assert booked.core.get_entity(DemoBooking, "B1") is None
    assert hub_status(booked) is HubStatus.ACTIVE


def test_a_duplicate_id_fails_and_the_unit_leaves_no_trace(booked):
    add_booking(booked)

    with booked.core.unit_of_work() as uow:
        uow.repository.add(DemoBooking("B2", "V001"))
        with pytest.raises(DuplicateEntityError):
            uow.repository.add(DemoBooking("B1", "V001"))

    assert [b.booking_id for b in booked.core.query_entities(DemoBooking)] == ["B1"]


def test_module_records_are_versioned_and_locked(booked):
    add_booking(booked)
    first = booked.core.get_entity(DemoBooking, "B1")
    second = booked.core.get_entity(DemoBooking, "B1")

    with booked.core.unit_of_work() as uow:
        first.status = BookingStatus.CANCELLED
        uow.repository.update(first, 1)
        uow.commit()
    with booked.core.unit_of_work() as uow, pytest.raises(VersionConflictError):
        uow.repository.update(second, 1)

    stored = booked.core.get_entity(DemoBooking, "B1")
    assert (stored.status, stored.version) == (BookingStatus.CANCELLED, 2)


def test_a_snapshot_plan_conflicts_with_a_later_change_to_a_module_record(booked):
    add_booking(booked)
    snapshot_version = booked.repo.version()
    later = booked.core.get_entity(DemoBooking, "B1")
    with booked.core.unit_of_work() as uow:
        later.status = BookingStatus.CANCELLED
        uow.repository.update(later, 1)
        uow.commit()

    with booked.core.unit_of_work(snapshot_version=snapshot_version) as uow:
        plan = booked.core.get_entity(DemoBooking, "B1")
        uow.repository.update(plan, plan.version)
        result = uow.commit()

    assert isinstance(result, Err) and result.code is ErrorCode.VERSION_CONFLICT
    assert result.details["changed"] == [("DemoBooking", "B1")]


def test_module_records_do_not_disturb_the_core_rules(booked):
    add_booking(booked)

    assert booked.core.check_invariants() == []
    assert booked.repo.export_state()[DemoBooking]["B1"].vehicle_id == "V001"


# ------------------------------------------------------------------ registration


def test_a_type_must_be_registered_before_use(world):
    with pytest.raises(UnknownEntityError):
        world.core.get_entity(DemoBooking, "B1")
    with world.core.unit_of_work() as uow, pytest.raises(UnknownEntityError):
        uow.repository.add(DemoBooking("B1", "V001"))


def test_registering_twice_is_harmless_and_keeps_the_data(booked):
    add_booking(booked)

    booked.core.register_entity(BOOKING)

    assert [b.booking_id for b in booked.core.query_entities(DemoBooking)] == ["B1"]


def item_table(name="late_items"):
    return Table(
        name,
        MetaData(),
        Column("item_id", String, primary_key=True),
        Column("label", String, nullable=False),
    )


@dataclass(slots=True)
class LateItem:
    ID_FIELD: ClassVar[str] = "item_id"

    item_id: str
    label: str


def test_a_table_registered_after_start_up_is_created(world):
    world.core.register_entity(TableSpec(LateItem, item_table(), "item_id", {}, False))

    with world.core.unit_of_work() as uow:
        uow.repository.add(LateItem("I1", "first"))
        uow.commit()

    assert world.core.get_entity(LateItem, "I1") == LateItem("I1", "first")


@dataclass(slots=True)
class WithExtraField:
    ID_FIELD: ClassVar[str] = "item_id"
    item_id: str
    label: str
    extra: str = ""


@dataclass(slots=True)
class Vehicle:  # the name of a core entity
    ID_FIELD: ClassVar[str] = "item_id"
    item_id: str
    label: str


class PlainClass:
    ID_FIELD = "item_id"


@dataclass(slots=True)
class WrongId:
    ID_FIELD: ClassVar[str] = "label"
    item_id: str
    label: str


@dataclass(slots=True)
class FlagButNoVersion:
    ID_FIELD: ClassVar[str] = "item_id"
    VERSIONED: ClassVar[bool] = True
    item_id: str
    label: str


@dataclass(slots=True)
class UsesTakenTable:
    ID_FIELD: ClassVar[str] = "booking_id"
    booking_id: str
    vehicle_id: str
    status: str
    version: int


BAD_SPECS = {
    "not a dataclass": lambda: TableSpec(PlainClass, item_table(), "item_id", {}, False),
    "core class name": lambda: TableSpec(Vehicle, item_table(), "item_id", {}, False),
    "id field differs": lambda: TableSpec(WrongId, item_table(), "item_id", {}, False),
    "field without a column": lambda: TableSpec(WithExtraField, item_table(), "item_id", {}, False),
    "versioned flag differs": lambda: TableSpec(LateItem, item_table(), "item_id", {}, True),
    "versioned without version field": lambda: TableSpec(
        FlagButNoVersion, item_table(), "item_id", {}, True
    ),
    "table name already used": lambda: TableSpec(
        UsesTakenTable, demo_bookings, "booking_id", {}, False
    ),
    "enum column missing": lambda: TableSpec(
        LateItem, item_table(), "item_id", {"nope": BookingStatus}, False
    ),
}


@pytest.mark.parametrize("label", sorted(BAD_SPECS))
def test_a_bad_spec_is_refused_and_nothing_is_registered(booked, label):
    with pytest.raises(ValueError):
        booked.core.register_entity(BAD_SPECS[label]())

    assert booked.core.check_invariants() == []


def test_another_table_for_a_registered_class_is_refused(booked):
    clash = TableSpec(
        DemoBooking,
        Table(
            "other_bookings",
            MetaData(),
            Column("booking_id", String, primary_key=True),
            Column("vehicle_id", String, nullable=False),
            Column("status", String, nullable=False),
            Column("version", Integer, nullable=False),
        ),
        "booking_id",
        {"status": BookingStatus},
        True,
    )

    with pytest.raises(ValueError, match="another table"):
        booked.core.register_entity(clash)


# ------------------------------------------------------------------ the SQL database


def test_the_sql_database_refuses_a_record_of_an_unknown_vehicle(world):
    if world.repo_kind != "sql":
        pytest.skip("only the database has foreign keys")
    world.core.register_entity(BOOKING)

    with world.core.unit_of_work() as uow, pytest.raises(IntegrityViolationError):
        uow.repository.add(DemoBooking("B1", "NO-SUCH-VEHICLE"))


def test_module_records_survive_a_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    spec = TableSpec(LateItem, item_table(), "item_id", {}, False)
    first = SqlRepository.open(url)
    core = CoreFacade(first)
    core.register_entity(spec)
    with core.unit_of_work() as uow:
        uow.repository.add(LateItem("I1", "kept"))
        uow.commit()
    first.close()

    second = SqlRepository.open(url)
    reopened = CoreFacade(second)
    reopened.register_entity(TableSpec(LateItem, item_table(), "item_id", {}, False))

    assert reopened.get_entity(LateItem, "I1") == LateItem("I1", "kept")
    second.close()
