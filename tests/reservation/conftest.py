"""Small deterministic network on both real repositories; no mocked Core."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI

from core.actor import Actor
from core.clock import FixedClock
from core.domain.entities import DomainEvent, Hub, ParkingSpace, UserAccount, Vehicle
from core.domain.enums import Ownership, Role, SpaceStatus, VehicleType
from core.events import EventType
from core.facade import CoreFacade
from core.repository.base import Repository
from core.repository.memory import InMemoryRepository
from core.repository.sql import SqlRepository
from reservation import install
from reservation.models import ReserveRequest
from reservation.service import BookingService

T0 = datetime(2026, 11, 4, 8, tzinfo=UTC)
STUDENT = Actor("U1", Role.STUDENT, "ui")


@dataclass
class RentalWorld:
    core: CoreFacade
    repo: Repository
    clock: FixedClock
    service: BookingService
    events: list[DomainEvent]
    app: FastAPI
    actor: Actor = STUDENT

    def vehicle(self, vehicle_id: str = "V1") -> Vehicle:
        result = self.repo.get(Vehicle, vehicle_id)
        assert result is not None
        return result

    def request(self, **fields) -> ReserveRequest:
        values = dict(
            reservation_id="R1",
            vehicle_id="V1",
            origin_hub_id="H1",
            destination_hub_id="H2",
            expected_version=self.vehicle().version,
        )
        values.update(fields)
        return ReserveRequest(**values)


def seed(repo: Repository) -> None:
    """Direct setup is test-only; all actions under test go through BookingService."""
    repo.add(Hub("H1", "Origin", "A", 2, 0))
    repo.add(Hub("H2", "Destination", "B", 1, 0))
    repo.add(UserAccount("U1", "2452620", Role.STUDENT))
    repo.add(UserAccount("U2", "2452002", Role.STUDENT))
    repo.add(UserAccount("OFF", "2452003", Role.STUDENT, is_active=False))
    repo.add(UserAccount("OP", "operator", Role.OPERATOR))
    for space_id, vehicle_id in [("S1", "V1"), ("S2", "V2")]:
        repo.add(ParkingSpace(space_id, "H1", space_id, SpaceStatus.OCCUPIED, vehicle_id))
        repo.add(
            Vehicle(
                vehicle_id,
                vehicle_id,
                Ownership.FLEET,
                VehicleType.E_BIKE,
                80,
                0.5,
                hub_id="H1",
                parking_space_id=space_id,
            )
        )
    repo.add(ParkingSpace("S3", "H2", "S3"))


@pytest.fixture(params=["memory", "sqlite"])
def rental(request) -> Iterator[RentalWorld]:
    repo = InMemoryRepository() if request.param == "memory" else SqlRepository.open("sqlite://")
    seed(repo)
    clock = FixedClock(T0)
    core = CoreFacade(repo, clock)
    events: list[DomainEvent] = []
    for event_type in EventType:
        core.events.subscribe(event_type, events.append)
    app = FastAPI()
    install(core, app)
    yield RentalWorld(core, repo, clock, app.state.reservation, events, app)
    if isinstance(repo, SqlRepository):
        repo.close()
