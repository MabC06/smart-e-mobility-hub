"""Operational snapshot for the What-if simulation and for allocation plans (NFR-12, NFR-13).

A snapshot is a read-only copy of the core entities taken in one read, under the lock, so it
matches a single commit point. It holds copies only: no reference to live objects or to the store.
``version`` grows with every commit; ``snapshot_id`` is a hash of the content, so the same state
gives the same ID whatever the number of commits behind it.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum

from core.domain.entities import (
    ChargingPoint,
    Entity,
    Hub,
    ParkingSpace,
    ResourceClaim,
    Vehicle,
)
from core.domain.enums import ClaimStatus
from core.repository.memory import InMemoryRepository
from core.services.runtime import Runtime


def _plain(value: object) -> object:
    """Turn entities into plain JSON-compatible data."""
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class OperationalSnapshot:
    snapshot_id: str
    taken_at: datetime
    version: int
    hubs: tuple[Hub, ...]
    parking_spaces: tuple[ParkingSpace, ...]
    charging_points: tuple[ChargingPoint, ...]
    vehicles: tuple[Vehicle, ...]
    claims: tuple[ResourceClaim, ...]

    def content(self) -> dict[str, object]:
        """The state itself, without ``snapshot_id``, ``taken_at`` and ``version``."""
        return {
            "hubs": _plain(self.hubs),
            "parking_spaces": _plain(self.parking_spaces),
            "charging_points": _plain(self.charging_points),
            "vehicles": _plain(self.vehicles),
            "claims": _plain(self.claims),
        }

    def to_dict(self) -> dict[str, object]:
        """A plain dictionary that can be written as JSON."""
        return {
            "snapshot_id": self.snapshot_id,
            "taken_at": self.taken_at.isoformat(),
            "version": self.version,
            **self.content(),
        }

    def to_repository(self) -> InMemoryRepository:
        """Load the snapshot into a new in-memory store; the live store is not involved."""
        repo = InMemoryRepository()
        everything: list[Entity] = [
            *self.hubs,
            *self.parking_spaces,
            *self.charging_points,
            *self.vehicles,
            *self.claims,
        ]
        for entity in everything:
            repo.add(entity)  # the repository stores its own copy
        return repo


def snapshot_id_of(content: dict[str, object]) -> str:
    text = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return "SNAP-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class SnapshotService:
    def __init__(self, runtime: Runtime) -> None:
        self._rt = runtime

    def export_snapshot(self) -> OperationalSnapshot:
        rt = self._rt
        with rt.lock:
            snapshot = OperationalSnapshot(
                snapshot_id="",
                taken_at=rt.now(),
                version=rt.repo.version(),
                hubs=tuple(rt.repo.query(Hub)),
                parking_spaces=tuple(rt.repo.query(ParkingSpace)),
                charging_points=tuple(rt.repo.query(ChargingPoint)),
                vehicles=tuple(rt.repo.query(Vehicle)),
                claims=tuple(
                    rt.repo.query(ResourceClaim, lambda c: c.status is ClaimStatus.ACTIVE)
                ),
            )
        return OperationalSnapshot(
            snapshot_id=snapshot_id_of(snapshot.content()),
            taken_at=snapshot.taken_at,
            version=snapshot.version,
            hubs=snapshot.hubs,
            parking_spaces=snapshot.parking_spaces,
            charging_points=snapshot.charging_points,
            vehicles=snapshot.vehicles,
            claims=snapshot.claims,
        )
