"""Persistence schema registration for Module M3 (D-018)."""

from typing import cast

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Table

from charging.models import ChargingRequest, ChargingSessionStatus
from core.domain.entities import Entity
from core.facade import CoreFacade
from core.repository.base import Repository
from core.repository.schema import TableSpec, UtcDateTime, metadata

charging_requests_table = Table(
    "charging_requests",
    metadata,
    Column("request_id", String(128), primary_key=True),
    Column("vehicle_id", String(128), ForeignKey("vehicles.vehicle_id"), nullable=False),
    Column("station_id", String(128), ForeignKey("hubs.hub_id"), nullable=False),
    Column("current_soc", Float, nullable=False),
    Column("target_soc", Float, nullable=False),
    Column("requested_at", UtcDateTime, nullable=False),
    Column("is_emergency", Boolean, nullable=False),
    Column("energy_kwh", Float, nullable=False),
    Column("charger_id", String(128), ForeignKey("charging_points.charging_point_id")),
    Column("start_time", UtcDateTime),
    Column("end_time", UtcDateTime),
    Column("point_claim_id", String(128), ForeignKey("resource_claims.claim_id")),
    Column("vehicle_claim_id", String(128), ForeignKey("resource_claims.claim_id")),
    Column("status", String(32), nullable=False),
    Column("user_id", String(128), ForeignKey("user_accounts.user_id")),
    Column("version", Integer, nullable=False),
)

SPEC = TableSpec(
    ChargingRequest,
    charging_requests_table,
    "request_id",
    {"status": ChargingSessionStatus},
    True,
)


def register_tables(core: CoreFacade) -> None:
    core.register_entity(SPEC)


def read(core: CoreFacade, request_id: str) -> ChargingRequest | None:
    return cast(
        ChargingRequest | None,
        core.get_entity(cast(type[Entity], ChargingRequest), request_id),
    )


def all_requests(core: CoreFacade) -> list[ChargingRequest]:
    return cast(
        list[ChargingRequest],
        core.query_entities(cast(type[Entity], ChargingRequest)),
    )


def add(repo: Repository, req: ChargingRequest) -> None:
    repo.add(cast(Entity, req))


def update(repo: Repository, req: ChargingRequest) -> None:
    repo.update(cast(Entity, req), req.version)
