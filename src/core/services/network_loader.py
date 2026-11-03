"""Load a ``NetworkSpec`` into an empty store, all or nothing (see core/seed.py).

Loading the first data is not a state change of an existing entity, so it writes no log entries.
It refuses a store that already holds Hubs or users, so it can never overwrite real state.
"""

from core import permissions
from core.actor import Actor
from core.domain.entities import (
    ChargingPoint,
    Entity,
    Hub,
    ParkingSpace,
    UserAccount,
    Vehicle,
)
from core.domain.enums import Ownership, SpaceStatus, VehicleState
from core.errors import ErrorCode
from core.result import Err, Ok, Result
from core.seed import (
    HubSpec,
    NetworkSpec,
    NetworkSummary,
    VehicleSpec,
    charging_point_id,
    space_id,
    validate_network,
)
from core.services.runtime import Runtime


class NetworkLoader:
    def __init__(self, runtime: Runtime) -> None:
        self._rt = runtime

    def load(self, spec: NetworkSpec, actor: Actor) -> Result[NetworkSummary]:
        repo = self._rt.repo
        if not permissions.may_load_network(actor):
            return Err(ErrorCode.FORBIDDEN, f"{actor.label()} may not load a network")
        has_hubs = bool(repo.query(Hub))
        has_users = bool(repo.query(UserAccount))
        if has_hubs or has_users:
            return Err(ErrorCode.INVALID_INPUT, "the network is already loaded")
        invalid = validate_network(spec)
        if invalid is not None:
            return invalid
        try:
            entities = self._build(spec)
        except ValueError as exc:
            return Err(ErrorCode.INVALID_INPUT, str(exc))
        for entity in entities:
            repo.add(entity)
        return Ok(
            NetworkSummary(
                hubs=len(spec.hubs),
                parking_spaces=sum(h.space_count for h in spec.hubs),
                charging_points=sum(h.charging_point_count for h in spec.hubs),
                vehicles=sum(len(h.vehicles) for h in spec.hubs) + len(spec.private_vehicles),
                users=len(spec.users),
            )
        )

    def _build(self, spec: NetworkSpec) -> list[Entity]:
        """Entities in an order that respects the foreign keys."""
        users: list[Entity] = [
            UserAccount(u.user_id, u.code, u.role, password_hash=u.password_hash)
            for u in spec.users
        ]
        hubs: list[Entity] = []
        spaces: list[Entity] = []
        points: list[Entity] = []
        vehicles: list[Entity] = []
        for hub in spec.hubs:
            hubs.append(
                Hub(
                    hub.hub_id,
                    hub.name,
                    hub.zone_code,
                    hub.space_count,
                    hub.charging_point_count,
                )
            )
            placed = self._placement(hub)
            for number in range(1, hub.space_count + 1):
                occupant = placed.get(number)
                spaces.append(
                    ParkingSpace(
                        space_id(hub.hub_id, number),
                        hub.hub_id,
                        f"S{number:03d}",
                        status=SpaceStatus.OCCUPIED if occupant else SpaceStatus.AVAILABLE,
                        occupant_vehicle_id=occupant.vehicle_id if occupant else None,
                    )
                )
            for number in range(1, hub.charging_point_count + 1):
                points.append(
                    ChargingPoint(
                        charging_point_id(hub.hub_id, number),
                        hub.hub_id,
                        space_id(hub.hub_id, number),
                        hub.power_rate_kw,
                    )
                )
            for number, vehicle in sorted(placed.items()):
                vehicles.append(self._vehicle(vehicle, hub.hub_id, space_id(hub.hub_id, number)))
        vehicles.extend(self._vehicle(v, None, None) for v in spec.private_vehicles)
        return [*users, *hubs, *spaces, *points, *vehicles]

    @staticmethod
    def _placement(hub: HubSpec) -> dict[int, VehicleSpec]:
        """Space number for each fleet vehicle: free spaces first, charging bays last."""
        bays = range(1, hub.charging_point_count + 1)
        free = range(hub.charging_point_count + 1, hub.space_count + 1)
        order = [*free, *bays]
        return {order[index]: vehicle for index, vehicle in enumerate(hub.vehicles)}

    @staticmethod
    def _vehicle(spec: VehicleSpec, hub_id: str | None, parking_space_id: str | None) -> Vehicle:
        return Vehicle(
            vehicle_id=spec.vehicle_id,
            plate_or_code=spec.plate_or_code,
            ownership=Ownership.PRIVATE if spec.owner_user_id else Ownership.FLEET,
            vehicle_type=spec.vehicle_type,
            battery_pct=spec.battery_pct,
            battery_capacity_kwh=spec.battery_capacity_kwh,
            state=VehicleState.IN_USE if spec.owner_user_id else VehicleState.AVAILABLE,
            hub_id=hub_id,
            parking_space_id=parking_space_id,
            owner_user_id=spec.owner_user_id,
            connector_type=spec.connector_type,
        )
