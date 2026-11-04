"""Verify business retry recovery after closing and reopening the SQLite database."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI

from core.actor import Actor
from core.clock import FixedClock
from core.domain.entities import Hub, ParkingSpace, UserAccount, Vehicle
from core.domain.enums import Ownership, Role, SpaceStatus, VehicleType
from core.facade import CoreFacade
from core.repository.sql import SqlRepository
from core.result import Ok
from reservation import install
from reservation.models import ReserveRequest


@pytest.mark.tc_m2_021
def test_retry_survives_database_reopen(tmp_path):
    """Verifies: D-015/018, NFR-09; retry state is durable M2 data, not process memory."""
    url = f"sqlite:///{tmp_path / 'rental.db'}"
    clock = FixedClock(datetime(2026, 11, 4, 8, tzinfo=UTC))
    actor = Actor("U1", Role.STUDENT, "ui")
    request = ReserveRequest("R1", "V1", "H1", 1)
    with_repo = SqlRepository.open(url)
    try:
        with_repo.add(Hub("H1", "Hub", "A", 1, 0))
        with_repo.add(UserAccount("U1", "2452620", Role.STUDENT))
        with_repo.add(ParkingSpace("S1", "H1", "S1", SpaceStatus.OCCUPIED, "V1"))
        with_repo.add(
            Vehicle(
                "V1",
                "V1",
                Ownership.FLEET,
                VehicleType.E_BIKE,
                80,
                0.5,
                hub_id="H1",
                parking_space_id="S1",
            )
        )
        core = CoreFacade(with_repo, clock)
        app = FastAPI()
        install(core, app)
        booking = app.state.reservation.reserve(request, actor)
        assert isinstance(booking, Ok)
    finally:
        with_repo.close()

    reopened = SqlRepository.open(url)
    try:
        core = CoreFacade(reopened, clock)
        app = FastAPI()
        install(core, app)
        # Original observed Vehicle version is stale, but the M2 record wins.
        assert app.state.reservation.reserve(request, actor) == booking
        pickup = app.state.reservation.pickup("R1", "H1", 2, actor)
        assert isinstance(pickup, Ok)
        returned = app.state.reservation.return_trip(pickup.value.trip_id, "H1", 3, actor)
        assert isinstance(returned, Ok)
    finally:
        reopened.close()

    reopened = SqlRepository.open(url)
    try:
        core = CoreFacade(reopened, clock)
        app = FastAPI()
        install(core, app)
        assert app.state.reservation.return_trip("TRIP:R1", "H1", 3, actor) == returned
        assert core.check_invariants() == []
    finally:
        reopened.close()
