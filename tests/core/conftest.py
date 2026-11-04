from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from core.actor import Actor
from core.clock import FixedClock
from core.domain.entities import (
    ChargingPoint,
    DomainEvent,
    Hub,
    ParkingSpace,
    ResourceClaim,
    StateChangeRecord,
    UserAccount,
    Vehicle,
)
from core.domain.enums import (
    HolderKind,
    Ownership,
    ResourceType,
    Role,
    SpaceStatus,
    VehicleState,
    VehicleType,
)
from core.events import EventType
from core.facade import CoreFacade
from core.repository.base import Repository
from core.repository.memory import InMemoryRepository
from core.repository.sql import SqlRepository
from core.result import Ok

T0 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


@pytest.fixture
def t0() -> datetime:
    return T0


@pytest.fixture
def make_vehicle() -> Callable[..., Vehicle]:
    def factory(
        vehicle_id: str = "V001",
        state: VehicleState = VehicleState.AVAILABLE,
        battery_pct: float = 80.0,
        fault_flag: bool = False,
        **extra: object,
    ) -> Vehicle:
        return Vehicle(
            vehicle_id=vehicle_id,
            plate_or_code=f"CODE-{vehicle_id}",
            ownership=Ownership.FLEET,
            vehicle_type=VehicleType.E_BIKE,
            battery_pct=battery_pct,
            battery_capacity_kwh=0.5,
            state=state,
            fault_flag=fault_flag,
            **extra,  # type: ignore[arg-type]
        )

    return factory


@pytest.fixture
def make_claim() -> Callable[..., ResourceClaim]:
    def factory(
        claim_id: str = "C001",
        resource_id: str = "V001",
        start_min: int = 0,
        end_min: int = 10,
        resource_type: ResourceType = ResourceType.VEHICLE,
        holder_kind: HolderKind = HolderKind.RESERVATION,
        holder_ref: str = "R001",
        **extra: object,
    ) -> ResourceClaim:
        return ResourceClaim(
            claim_id=claim_id,
            resource_type=resource_type,
            resource_id=resource_id,
            holder_kind=holder_kind,
            holder_ref=holder_ref,
            start_at=T0 + timedelta(minutes=start_min),
            end_at=T0 + timedelta(minutes=end_min),
            **extra,  # type: ignore[arg-type]
        )

    return factory


@dataclass
class World:
    """A small network: H01 (3 spaces, bay S01 with CP01) and H02 (2 spaces)."""

    core: CoreFacade
    repo: Repository
    clock: FixedClock
    events: list[DomainEvent]
    repo_kind: str = "memory"
    reservation: Actor = Actor("U1", Role.STUDENT, "reservation")
    charging: Actor = Actor("U1", Role.STUDENT, "charging")
    allocation: Actor = Actor("U1", Role.STUDENT, "allocation")
    monitoring: Actor = Actor("SYS", Role.OPERATOR, "monitoring")
    iot: Actor = Actor("SIM", Role.OPERATOR, "iot_sim")
    operator: Actor = Actor("OP1", Role.OPERATOR, "ui")
    student: Actor = Actor("U1", Role.STUDENT, "ui")

    def park(
        self,
        vehicle_id: str,
        space_id: str,
        state: VehicleState = VehicleState.AVAILABLE,
        battery_pct: float = 80.0,
    ) -> Vehicle:
        space = self.repo.get(ParkingSpace, space_id)
        assert space is not None
        vehicle = Vehicle(
            vehicle_id=vehicle_id,
            plate_or_code=f"CODE-{vehicle_id}",
            ownership=Ownership.FLEET,
            vehicle_type=VehicleType.E_BIKE,
            battery_pct=battery_pct,
            battery_capacity_kwh=0.5,
            state=state,
            hub_id=space.hub_id,
            parking_space_id=space_id,
        )
        space.status = SpaceStatus.OCCUPIED
        space.occupant_vehicle_id = vehicle_id
        self.repo.add(vehicle)
        self.repo.update(space, space.version)
        return vehicle

    def vehicle(self, vehicle_id: str) -> Vehicle:
        found = self.repo.get(Vehicle, vehicle_id)
        assert found is not None
        return found

    def space(self, space_id: str) -> ParkingSpace:
        found = self.repo.get(ParkingSpace, space_id)
        assert found is not None
        return found

    def claim_vehicle(self, vehicle_id: str, minutes: int = 10, ref: str = "R1") -> str:
        result = self.core.commands.place_claim(
            ResourceType.VEHICLE,
            vehicle_id,
            HolderKind.RESERVATION,
            ref,
            self.clock.now(),
            self.clock.now() + timedelta(minutes=minutes),
            self.reservation,
        )
        assert isinstance(result, Ok)
        return result.value.claim_id

    def log_of(self, entity_id: str) -> list[StateChangeRecord]:
        return self.core.queries.get_state_log(entity_id)


@pytest.fixture(params=["memory", "sql"])
def world(request: pytest.FixtureRequest) -> Iterator[World]:
    """The same small network on both repositories: every test using it runs twice."""
    kind = str(request.param)
    repo: Repository = InMemoryRepository() if kind == "memory" else SqlRepository.open("sqlite://")
    clock = FixedClock(T0)
    core = CoreFacade(repo, clock)
    events: list[DomainEvent] = []
    for event_type in EventType:
        core.events.subscribe(event_type, events.append)
    repo.add(Hub("H01", "Metro", "METRO", 3, 1))
    repo.add(Hub("H02", "Dorm A", "DORM", 2, 0))
    for space_id, hub_id in [
        ("S01", "H01"),
        ("S02", "H01"),
        ("S03", "H01"),
        ("S11", "H02"),
        ("S12", "H02"),
    ]:
        repo.add(ParkingSpace(space_id, hub_id, space_id))
    repo.add(ChargingPoint("CP01", "H01", "S01", 11.0))
    repo.add(UserAccount("U1", "2452001", Role.STUDENT))
    repo.add(UserAccount("U2", "2452002", Role.STUDENT, is_active=False))
    yield World(core, repo, clock, events, repo_kind=kind)
    if isinstance(repo, SqlRepository):
        repo.close()
