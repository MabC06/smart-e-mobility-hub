"""Command interface ``StateCommands`` (docs/design/architecture/core-api-spec.md, section 5).

Every command returns a ``Result``. A command checks everything first and writes afterwards, and
the runtime undoes its changes when it returns an error, so a failed command leaves no trace.
"""

from dataclasses import dataclass, field
from datetime import datetime

from core import permissions
from core.actor import Actor
from core.domain.claims import ClaimPolicy
from core.domain.entities import (
    ChargingPoint,
    Hub,
    ParkingSpace,
    ResourceClaim,
    UserAccount,
    Vehicle,
)
from core.domain.enums import (
    ChargingPointStatus,
    ClaimStatus,
    HolderKind,
    HubStatus,
    Ownership,
    ResourceType,
    SpaceStatus,
    VehicleEvent,
    VehicleState,
    VehicleType,
)
from core.domain.state_machine import TransitionContext
from core.errors import ErrorCode
from core.events import EventType
from core.result import Err, Ok, Result
from core.seed import NetworkSpec, NetworkSummary
from core.sensors import SensorEvent, SensorResult
from core.services.network_loader import NetworkLoader
from core.services.runtime import Runtime
from core.services.sensor_intake import SensorIntake
from core.services.transition_ctx import TransitionCtx
from core.views import ChargingPointView, ClaimView, HubStatusView, SpaceView, VehicleView


@dataclass(slots=True)
class _Effects:
    spaces: list[tuple[ParkingSpace, SpaceStatus]] = field(default_factory=list)
    claims: list[ResourceClaim] = field(default_factory=list)


# Events of the rental trip. A private EV does not rent: it arrives, parks, charges and departs.
# While it is away from every Hub it is IN_USE (vehicle-state-machine.md, section 7, point 1).
_RENTAL_EVENTS = frozenset(
    {
        VehicleEvent.RESERVE,
        VehicleEvent.RELEASE_RESERVATION,
        VehicleEvent.PICKUP,
        VehicleEvent.RETURN,
        VehicleEvent.RETURN_FAULTY,
    }
)
_PRIVATE_EVENTS = frozenset({VehicleEvent.ARRIVE, VehicleEvent.DEPART})


def _forbidden(actor: Actor, action: str) -> Err:
    return Err(ErrorCode.FORBIDDEN, f"{actor.label()} may not {action}")


def _not_found(kind: str, entity_id: str) -> Err:
    return Err(ErrorCode.NOT_FOUND, f"unknown {kind} {entity_id!r}")


def _version_conflict(kind: str, entity_id: str, expected: int, current: int) -> Err:
    return Err(
        ErrorCode.VERSION_CONFLICT,
        f"{kind} {entity_id!r} changed: expected version {expected}, current {current}",
        {"expected_version": expected, "current_version": current},
    )


class StateCommands:
    def __init__(self, runtime: Runtime) -> None:
        self._rt = runtime

    # ------------------------------------------------------------------ iot_sim

    def apply_sensor_event(self, event: SensorEvent, actor: Actor) -> Result[SensorResult]:
        """Apply an event of the IoT simulator, or reject it without any change (NFR-10)."""
        return SensorIntake(self._rt, self).apply(event, actor)

    def load_network(self, spec: NetworkSpec, actor: Actor) -> Result[NetworkSummary]:
        """Load a whole network into an empty store, all or nothing (see ``core.seed``)."""
        return self._rt.run(lambda: NetworkLoader(self._rt).load(spec, actor))

    # ------------------------------------------------------------------ transition_vehicle

    def transition_vehicle(
        self,
        vehicle_id: str,
        event: VehicleEvent,
        expected_version: int,
        actor: Actor,
        ctx: TransitionCtx | None = None,
    ) -> Result[VehicleView]:
        """Apply one event of the Vehicle state machine (T1 to T12) with all its side effects."""
        return self._rt.run(
            lambda: self._transition(
                vehicle_id, event, expected_version, actor, ctx or TransitionCtx()
            )
        )

    def _transition(
        self,
        vehicle_id: str,
        event: VehicleEvent,
        expected_version: int,
        actor: Actor,
        ctx: TransitionCtx,
    ) -> Result[VehicleView]:
        rt = self._rt
        if not permissions.may_transition(actor, event):
            return _forbidden(actor, f"run {event.value!r}")
        vehicle = rt.repo.get(Vehicle, vehicle_id)
        if vehicle is None:
            return _not_found("vehicle", vehicle_id)
        if vehicle.version != expected_version:
            return _version_conflict("vehicle", vehicle_id, expected_version, vehicle.version)
        if vehicle.ownership is Ownership.PRIVATE and event in _RENTAL_EVENTS:
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"a private vehicle does not use the rental event {event.value!r}",
                {"vehicle_id": vehicle_id, "event": event},
            )
        if vehicle.ownership is Ownership.FLEET and event in _PRIVATE_EVENTS:
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"a fleet vehicle moves with pickup and return, not {event.value!r}",
                {"vehicle_id": vehicle_id, "event": event},
            )
        if (
            vehicle.ownership is Ownership.PRIVATE
            and vehicle.state is VehicleState.IN_USE
            and event is VehicleEvent.REPORT_FAULT
        ):
            return Err(
                ErrorCode.INVALID_TRANSITION,
                "a private vehicle away from every Hub cannot report a fault",
                {"vehicle_id": vehicle_id, "event": event},
            )
        if ctx.battery_pct is not None:
            if not 0.0 <= ctx.battery_pct <= 100.0:
                return Err(ErrorCode.INVALID_INPUT, "battery_pct must be between 0 and 100")
            vehicle.battery_pct = ctx.battery_pct

        checked = rt.machine.check(vehicle, event, TransitionContext(min_battery=ctx.min_battery))
        if isinstance(checked, Err):
            return checked

        now = rt.now()
        effects = _Effects()
        failure = self._prepare(vehicle, event, ctx, now, effects)
        if failure is not None:
            return failure

        previous = vehicle.state
        applied = rt.machine.apply(vehicle, event, TransitionContext(min_battery=ctx.min_battery))
        if isinstance(applied, Err):
            return applied

        label = actor.label()
        rt.repo.update(vehicle, expected_version)
        rt.log_change(
            "Vehicle", vehicle.vehicle_id, previous.value, vehicle.state.value, event.value, label
        )
        rt.emit(
            EventType.VEHICLE_STATE_CHANGED,
            {
                "vehicle_id": vehicle.vehicle_id,
                "previous": previous.value,
                "new": vehicle.state.value,
                "event": event.value,
                "hub_id": vehicle.hub_id,
                "at": now.isoformat(),
                "actor": label,
            },
        )
        self._write_space_effects(effects, event.value, label, now)
        if event is VehicleEvent.REPAIR and isinstance(
            rt.machine.check(vehicle, VehicleEvent.MARK_READY), Ok
        ):
            # An operator repairs once: if the readiness check (T6) passes, the vehicle goes on to
            # Available in the same unit of work. Both steps are logged.
            ready = self._transition(
                vehicle_id, VehicleEvent.MARK_READY, vehicle.version, actor, TransitionCtx()
            )
            if isinstance(ready, Ok):
                return ready
        return Ok(VehicleView.of(vehicle))

    def _prepare(
        self,
        vehicle: Vehicle,
        event: VehicleEvent,
        ctx: TransitionCtx,
        now: datetime,
        effects: _Effects,
    ) -> Err | None:
        """Checks and changes that need data besides the vehicle. Nothing is saved here."""
        match event:
            case VehicleEvent.RESERVE:
                claim = self._need_claim(
                    ctx.claim_id, ResourceType.VEHICLE, vehicle.vehicle_id, now
                )
                return claim if isinstance(claim, Err) else None
            case VehicleEvent.PICKUP:
                return self._prepare_pickup(vehicle, ctx, now, effects)
            case VehicleEvent.RETURN | VehicleEvent.RETURN_FAULTY | VehicleEvent.ARRIVE:
                return self._prepare_return(vehicle, ctx, now, effects)
            case VehicleEvent.DEPART:
                return self._leave_origin(vehicle, effects)
            case VehicleEvent.START_CHARGING:
                return self._prepare_start_charging(vehicle, ctx, now)
            case _:
                return None

    def _need_claim(
        self,
        claim_id: str | None,
        resource_type: ResourceType,
        resource_id: str,
        now: datetime,
        holder_kind: HolderKind | None = None,
    ) -> ResourceClaim | Err:
        if claim_id is None:
            return Err(ErrorCode.INVALID_INPUT, "claim_id is required for this event")
        claim = self._rt.repo.get(ResourceClaim, claim_id)
        if claim is None:
            return _not_found("claim", claim_id)
        active_now = (
            claim.status is ClaimStatus.ACTIVE
            and claim.resource_type is resource_type
            and claim.resource_id == resource_id
            and claim.start_at <= now < claim.end_at
        )
        if not active_now:
            return Err(
                ErrorCode.INVALID_TRANSITION,
                "the claim is not an active claim on this resource at this time",
                {"claim_id": claim_id, "resource_id": resource_id},
            )
        if holder_kind is not None and claim.holder_kind is not holder_kind:
            return Err(ErrorCode.INVALID_INPUT, f"the claim must be held by {holder_kind.value}")
        return claim

    def _prepare_pickup(
        self, vehicle: Vehicle, ctx: TransitionCtx, now: datetime, effects: _Effects
    ) -> Err | None:
        claim = self._need_claim(ctx.claim_id, ResourceType.VEHICLE, vehicle.vehicle_id, now)
        if isinstance(claim, Err):
            return claim
        return self._leave_origin(vehicle, effects)

    def _leave_origin(self, vehicle: Vehicle, effects: _Effects) -> Err | None:
        """The vehicle leaves its space: the space is freed and the vehicle has no location."""
        if vehicle.parking_space_id is None:
            return Err(ErrorCode.RESOURCE_UNAVAILABLE, "the vehicle has no origin space")
        origin = self._rt.repo.get(ParkingSpace, vehicle.parking_space_id)
        if origin is None:
            return _not_found("parking space", vehicle.parking_space_id)
        effects.spaces.append((origin, origin.status))
        origin.status = SpaceStatus.AVAILABLE
        origin.occupant_vehicle_id = None
        vehicle.hub_id = None
        vehicle.parking_space_id = None
        return None

    def _prepare_return(
        self, vehicle: Vehicle, ctx: TransitionCtx, now: datetime, effects: _Effects
    ) -> Err | None:
        rt = self._rt
        space = self._destination_space(ctx, now)
        if isinstance(space, Err):
            return space
        hub = rt.repo.get(Hub, space.hub_id)
        if hub is None:
            return _not_found("hub", space.hub_id)
        if hub.status is HubStatus.MAINTENANCE:
            return Err(ErrorCode.RESOURCE_UNAVAILABLE, f"hub {hub.hub_id!r} is in maintenance")
        if space.status is not SpaceStatus.AVAILABLE:
            return Err(
                ErrorCode.SPACE_NOT_FREE,
                f"space {space.parking_space_id!r} is {space.status.value}",
            )
        if rt.occupied_count(hub.hub_id) >= hub.parking_capacity:
            return Err(ErrorCode.HUB_FULL, f"hub {hub.hub_id!r} has no free space")
        hold = None
        if ctx.claim_id is not None:
            claim = self._need_claim(ctx.claim_id, ResourceType.SPACE, space.parking_space_id, now)
            if isinstance(claim, Err):
                return claim
            hold = claim
        blocking = self._claims_on(
            ResourceType.SPACE, space.parking_space_id, now, skip=ctx.claim_id
        )
        if blocking:
            return Err(
                ErrorCode.SPACE_NOT_FREE,
                f"space {space.parking_space_id!r} is held by another claim",
                {"claim_id": blocking[0].claim_id},
            )
        effects.spaces.append((space, space.status))
        space.status = SpaceStatus.OCCUPIED
        space.occupant_vehicle_id = vehicle.vehicle_id
        vehicle.hub_id = space.hub_id
        vehicle.parking_space_id = space.parking_space_id
        if hold is not None:
            hold.status = ClaimStatus.RELEASED
            effects.claims.append(hold)
        return None

    def _destination_space(self, ctx: TransitionCtx, now: datetime) -> ParkingSpace | Err:
        repo = self._rt.repo
        if ctx.parking_space_id is not None:
            space = repo.get(ParkingSpace, ctx.parking_space_id)
            if space is None:
                return _not_found("parking space", ctx.parking_space_id)
            if ctx.hub_id is not None and ctx.hub_id != space.hub_id:
                return Err(ErrorCode.INVALID_INPUT, "parking_space_id is not in hub_id")
            return space
        if ctx.hub_id is None:
            return Err(ErrorCode.INVALID_INPUT, "hub_id or parking_space_id is required")
        hub_id = ctx.hub_id
        if repo.get(Hub, hub_id) is None:
            return _not_found("hub", hub_id)
        for candidate in repo.query(
            ParkingSpace, lambda s: s.hub_id == hub_id and s.status is SpaceStatus.AVAILABLE
        ):
            if not self._claims_on(
                ResourceType.SPACE, candidate.parking_space_id, now, skip=ctx.claim_id
            ):
                return candidate
        return Err(ErrorCode.HUB_FULL, f"hub {hub_id!r} has no free space")

    def _claims_on(
        self, resource_type: ResourceType, resource_id: str, now: datetime, skip: str | None
    ) -> list[ResourceClaim]:
        """ACTIVE claims on a resource that are running now or start later."""
        return self._rt.repo.query(
            ResourceClaim,
            lambda c: (
                c.status is ClaimStatus.ACTIVE
                and c.resource_type is resource_type
                and c.resource_id == resource_id
                and c.end_at > now
                and c.claim_id != skip
            ),
        )

    def _prepare_start_charging(
        self, vehicle: Vehicle, ctx: TransitionCtx, now: datetime
    ) -> Err | None:
        if ctx.charging_point_id is None:
            return Err(ErrorCode.INVALID_INPUT, "charging_point_id is required")
        point = self._rt.repo.get(ChargingPoint, ctx.charging_point_id)
        if point is None:
            return _not_found("charging point", ctx.charging_point_id)
        if point.status is not ChargingPointStatus.AVAILABLE:
            return Err(ErrorCode.RESOURCE_UNAVAILABLE, f"charging point is {point.status.value}")
        if vehicle.hub_id != point.hub_id or vehicle.parking_space_id != point.parking_space_id:
            return Err(
                ErrorCode.INVALID_INPUT, "the vehicle is not in the bay of this charging point"
            )
        claim = self._need_claim(
            ctx.claim_id,
            ResourceType.CHARGING_POINT,
            point.charging_point_id,
            now,
            HolderKind.CHARGING_SESSION,
        )
        return claim if isinstance(claim, Err) else None

    def _write_space_effects(
        self, effects: _Effects, trigger: str, label: str, now: datetime
    ) -> None:
        rt = self._rt
        for space, previous in effects.spaces:
            rt.repo.update(space, space.version)
            rt.log_change(
                "ParkingSpace",
                space.parking_space_id,
                previous.value,
                space.status.value,
                trigger,
                label,
            )
            self._emit_occupancy(space, now)
        for claim in effects.claims:
            rt.repo.update(claim)
            self._emit_claim_released(claim)

    def _emit_occupancy(self, space: ParkingSpace, now: datetime) -> None:
        self._rt.emit(
            EventType.SPACE_OCCUPANCY_CHANGED,
            {
                "hub_id": space.hub_id,
                "parking_space_id": space.parking_space_id,
                "occupied": space.status is SpaceStatus.OCCUPIED,
                "occupied_count": self._rt.occupied_count(space.hub_id),
                "at": now.isoformat(),
            },
        )

    def _emit_claim_released(self, claim: ResourceClaim) -> None:
        self._rt.emit(
            EventType.CLAIM_RELEASED,
            {
                "claim_id": claim.claim_id,
                "resource_type": claim.resource_type.value,
                "resource_id": claim.resource_id,
                "holder_kind": claim.holder_kind.value,
                "holder_ref": claim.holder_ref,
            },
        )

    # ------------------------------------------------------------------ claims

    def place_claim(
        self,
        resource_type: ResourceType,
        resource_id: str,
        holder_kind: HolderKind,
        holder_ref: str,
        start_at: datetime,
        end_at: datetime,
        actor: Actor,
    ) -> Result[ClaimView]:
        """Claim a resource for [start_at, end_at). A retry by the same holder returns the claim."""
        return self._rt.run(
            lambda: self._place_claim(
                resource_type, resource_id, holder_kind, holder_ref, start_at, end_at, actor
            )
        )

    def _place_claim(
        self,
        resource_type: ResourceType,
        resource_id: str,
        holder_kind: HolderKind,
        holder_ref: str,
        start_at: datetime,
        end_at: datetime,
        actor: Actor,
    ) -> Result[ClaimView]:
        rt = self._rt
        if not permissions.may_manage_claim(actor, holder_kind):
            return _forbidden(actor, f"place a {holder_kind.value} claim")
        if not holder_ref.strip():
            return Err(ErrorCode.INVALID_INPUT, "holder_ref is required")
        invalid = ClaimPolicy.validate_interval(start_at, end_at)
        if invalid is not None:
            return invalid
        unavailable = self._claimable(resource_type, resource_id)
        if unavailable is not None:
            return unavailable

        existing = rt.repo.query(
            ResourceClaim,
            lambda c: c.resource_type is resource_type and c.resource_id == resource_id,
        )
        same = ClaimPolicy.find_same_request(
            existing, resource_type, resource_id, holder_kind, holder_ref, start_at, end_at
        )
        if same is not None:
            return Ok(ClaimView.of(same))
        conflict = ClaimPolicy.find_conflict(existing, resource_type, resource_id, start_at, end_at)
        if conflict is not None:
            return Err(
                ErrorCode.CLAIM_CONFLICT,
                f"{resource_type.value} {resource_id!r} is already claimed in this interval",
                {"conflicting_claim_id": conflict.claim_id},
            )

        claim = ResourceClaim(
            claim_id=rt.ids.next_id("CLM"),
            resource_type=resource_type,
            resource_id=resource_id,
            holder_kind=holder_kind,
            holder_ref=holder_ref,
            start_at=start_at,
            end_at=end_at,
        )
        rt.repo.add(claim)
        rt.emit(
            EventType.CLAIM_PLACED,
            {
                "claim_id": claim.claim_id,
                "resource_type": resource_type.value,
                "resource_id": resource_id,
                "holder_kind": holder_kind.value,
                "holder_ref": holder_ref,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            },
        )
        return Ok(ClaimView.of(claim))

    def _claimable(self, resource_type: ResourceType, resource_id: str) -> Err | None:
        repo = self._rt.repo
        match resource_type:
            case ResourceType.VEHICLE:
                vehicle = repo.get(Vehicle, resource_id)
                if vehicle is None:
                    return _not_found("vehicle", resource_id)
                if vehicle.state is VehicleState.MAINTENANCE or vehicle.fault_flag:
                    return Err(
                        ErrorCode.RESOURCE_UNAVAILABLE, "the vehicle is faulty or in maintenance"
                    )
            case ResourceType.SPACE:
                space = repo.get(ParkingSpace, resource_id)
                if space is None:
                    return _not_found("parking space", resource_id)
                if space.status is SpaceStatus.MAINTENANCE:
                    return Err(
                        ErrorCode.RESOURCE_UNAVAILABLE, "the parking space is in maintenance"
                    )
            case ResourceType.CHARGING_POINT:
                point = repo.get(ChargingPoint, resource_id)
                if point is None:
                    return _not_found("charging point", resource_id)
                if point.status in {
                    ChargingPointStatus.OUT_OF_SERVICE,
                    ChargingPointStatus.MAINTENANCE,
                }:
                    return Err(
                        ErrorCode.RESOURCE_UNAVAILABLE,
                        f"the charging point is {point.status.value}",
                    )
        return None

    def release_claim(self, claim_id: str, actor: Actor) -> Result[ClaimView]:
        """Release a claim. Releasing twice returns the same claim, without an error."""
        return self._rt.run(lambda: self._release_claim(claim_id, actor))

    def _release_claim(self, claim_id: str, actor: Actor) -> Result[ClaimView]:
        rt = self._rt
        claim = rt.repo.get(ResourceClaim, claim_id)
        if claim is None:
            return _not_found("claim", claim_id)
        if not permissions.may_manage_claim(actor, claim.holder_kind):
            return _forbidden(actor, f"release a {claim.holder_kind.value} claim")
        if claim.status is ClaimStatus.ACTIVE:
            claim.status = ClaimStatus.RELEASED
            rt.repo.update(claim)
            self._emit_claim_released(claim)
        return Ok(ClaimView.of(claim))

    # ------------------------------------------------------------------ vehicles and spaces

    def register_vehicle(
        self,
        ownership: Ownership,
        plate_or_code: str,
        vehicle_type: VehicleType,
        battery_capacity_kwh: float,
        battery_pct: float,
        actor: Actor,
        *,
        vehicle_id: str | None = None,
        owner_user_id: str | None = None,
        connector_type: str | None = None,
        parking_space_id: str | None = None,
    ) -> Result[VehicleView]:
        """Create a vehicle.

        A FLEET vehicle needs a free ``parking_space_id``, has no owner and starts AVAILABLE. A
        PRIVATE vehicle needs an active owner and a connector type, and starts IN_USE: away from
        every Hub, as a vehicle on the road. It gets a space and becomes AVAILABLE when it arrives
        (event ``arrive``, or ``occupy_space``).
        """
        return self._rt.run(
            lambda: self._register_vehicle(
                ownership,
                plate_or_code,
                vehicle_type,
                battery_capacity_kwh,
                battery_pct,
                actor,
                vehicle_id,
                owner_user_id,
                connector_type,
                parking_space_id,
            )
        )

    def _register_vehicle(
        self,
        ownership: Ownership,
        plate_or_code: str,
        vehicle_type: VehicleType,
        battery_capacity_kwh: float,
        battery_pct: float,
        actor: Actor,
        vehicle_id: str | None,
        owner_user_id: str | None,
        connector_type: str | None,
        parking_space_id: str | None,
    ) -> Result[VehicleView]:
        rt = self._rt
        if not permissions.may_register_vehicle(actor):
            return _forbidden(actor, "register a vehicle")
        if not plate_or_code.strip():
            return Err(ErrorCode.INVALID_INPUT, "plate_or_code is required")
        if rt.repo.query(Vehicle, lambda v: v.plate_or_code == plate_or_code):
            return Err(ErrorCode.INVALID_INPUT, f"plate_or_code {plate_or_code!r} is already used")
        new_id = vehicle_id or rt.ids.next_id("VEH")
        if rt.repo.get(Vehicle, new_id) is not None:
            return Err(ErrorCode.INVALID_INPUT, f"vehicle {new_id!r} already exists")

        space: ParkingSpace | None = None
        if ownership is Ownership.PRIVATE:
            if owner_user_id is None or not connector_type:
                return Err(
                    ErrorCode.INVALID_INPUT,
                    "a private vehicle needs owner_user_id and connector_type",
                )
            owner = rt.repo.get(UserAccount, owner_user_id)
            if owner is None:
                return _not_found("user", owner_user_id)
            if not owner.is_active:
                return Err(ErrorCode.INVALID_INPUT, "the owner account is not active")
            if parking_space_id is not None:
                return Err(
                    ErrorCode.INVALID_INPUT, "a private vehicle gets a space when it arrives"
                )
        else:
            if owner_user_id is not None:
                return Err(ErrorCode.INVALID_INPUT, "a fleet vehicle has no owner")
            if parking_space_id is None:
                return Err(ErrorCode.INVALID_INPUT, "a fleet vehicle needs parking_space_id")
            space = rt.repo.get(ParkingSpace, parking_space_id)
            if space is None:
                return _not_found("parking space", parking_space_id)
            if space.status is not SpaceStatus.AVAILABLE:
                return Err(
                    ErrorCode.SPACE_NOT_FREE, f"space {parking_space_id!r} is {space.status.value}"
                )
            hub = rt.repo.get(Hub, space.hub_id)
            if hub is None:
                return _not_found("hub", space.hub_id)
            if rt.occupied_count(hub.hub_id) >= hub.parking_capacity:
                return Err(ErrorCode.HUB_FULL, f"hub {hub.hub_id!r} has no free space")

        try:
            vehicle = Vehicle(
                vehicle_id=new_id,
                plate_or_code=plate_or_code,
                ownership=ownership,
                vehicle_type=vehicle_type,
                battery_pct=battery_pct,
                battery_capacity_kwh=battery_capacity_kwh,
                state=VehicleState.IN_USE
                if ownership is Ownership.PRIVATE
                else VehicleState.AVAILABLE,
                owner_user_id=owner_user_id,
                connector_type=connector_type,
                hub_id=None if space is None else space.hub_id,
                parking_space_id=None if space is None else space.parking_space_id,
            )
        except ValueError as exc:
            return Err(ErrorCode.INVALID_INPUT, str(exc))
        rt.repo.add(vehicle)
        label = actor.label()
        rt.log_change("Vehicle", new_id, "NONE", vehicle.state.value, "register", label)
        if space is not None:
            previous = space.status
            space.status = SpaceStatus.OCCUPIED
            space.occupant_vehicle_id = new_id
            rt.repo.update(space, space.version)
            rt.log_change(
                "ParkingSpace",
                space.parking_space_id,
                previous.value,
                space.status.value,
                "register",
                label,
            )
            self._emit_occupancy(space, rt.now())
        return Ok(VehicleView.of(vehicle))

    def occupy_space(
        self,
        vehicle_id: str,
        parking_space_id: str,
        expected_version: int,
        actor: Actor,
        claim_id: str | None = None,
    ) -> Result[SpaceView]:
        """A private EV arrives. With ``claim_id`` its claim on the space becomes the occupancy."""
        return self._rt.run(
            lambda: self._occupy_space(
                vehicle_id, parking_space_id, expected_version, actor, claim_id
            )
        )

    def _occupy_space(
        self,
        vehicle_id: str,
        parking_space_id: str,
        expected_version: int,
        actor: Actor,
        claim_id: str | None,
    ) -> Result[SpaceView]:
        rt = self._rt
        if not permissions.may_change_occupancy(actor):
            return _forbidden(actor, "change the occupancy of a space")
        vehicle = rt.repo.get(Vehicle, vehicle_id)
        if vehicle is None:
            return _not_found("vehicle", vehicle_id)
        space = rt.repo.get(ParkingSpace, parking_space_id)
        if space is None:
            return _not_found("parking space", parking_space_id)
        if space.version != expected_version:
            return _version_conflict(
                "parking space", parking_space_id, expected_version, space.version
            )
        if vehicle.ownership is not Ownership.PRIVATE:
            return Err(
                ErrorCode.INVALID_INPUT, "a fleet vehicle is placed by return, not by occupy_space"
            )
        arrived = self._transition(
            vehicle_id,
            VehicleEvent.ARRIVE,
            vehicle.version,
            actor,
            TransitionCtx(parking_space_id=parking_space_id, claim_id=claim_id),
        )
        if isinstance(arrived, Err):
            return arrived
        parked = rt.repo.get(ParkingSpace, parking_space_id)
        return Ok(SpaceView.of(parked if parked is not None else space))

    def free_space(
        self, parking_space_id: str, expected_version: int, actor: Actor
    ) -> Result[SpaceView]:
        """A private EV leaves. A fleet vehicle leaves a space only through ``pickup``."""
        return self._rt.run(lambda: self._free_space(parking_space_id, expected_version, actor))

    def _free_space(
        self, parking_space_id: str, expected_version: int, actor: Actor
    ) -> Result[SpaceView]:
        rt = self._rt
        if not permissions.may_change_occupancy(actor):
            return _forbidden(actor, "change the occupancy of a space")
        space = rt.repo.get(ParkingSpace, parking_space_id)
        if space is None:
            return _not_found("parking space", parking_space_id)
        if space.version != expected_version:
            return _version_conflict(
                "parking space", parking_space_id, expected_version, space.version
            )
        if space.status is not SpaceStatus.OCCUPIED or space.occupant_vehicle_id is None:
            return Err(ErrorCode.INVALID_TRANSITION, f"space {parking_space_id!r} is not occupied")
        vehicle = rt.repo.get(Vehicle, space.occupant_vehicle_id)
        if vehicle is None:
            return _not_found("vehicle", space.occupant_vehicle_id)
        if vehicle.ownership is not Ownership.PRIVATE:
            return Err(ErrorCode.INVALID_INPUT, "a fleet vehicle leaves a space through pickup")
        left = self._transition(
            vehicle.vehicle_id, VehicleEvent.DEPART, vehicle.version, actor, TransitionCtx()
        )
        if isinstance(left, Err):
            return left
        freed = rt.repo.get(ParkingSpace, parking_space_id)
        return Ok(SpaceView.of(freed if freed is not None else space))

    # ------------------------------------------------------------------ statuses

    def set_charging_point_status(
        self,
        charging_point_id: str,
        status: ChargingPointStatus,
        expected_version: int,
        actor: Actor,
    ) -> Result[ChargingPointView]:
        """Change a charging point.

        ``OUT_OF_SERVICE`` does not end sessions by itself; the event lets M3 interrupt them.
        """
        return self._rt.run(
            lambda: self._set_charging_point_status(
                charging_point_id, status, expected_version, actor
            )
        )

    def _set_charging_point_status(
        self,
        charging_point_id: str,
        status: ChargingPointStatus,
        expected_version: int,
        actor: Actor,
    ) -> Result[ChargingPointView]:
        rt = self._rt
        if not permissions.may_set_charging_point_status(actor):
            return _forbidden(actor, "set a charging point status")
        point = rt.repo.get(ChargingPoint, charging_point_id)
        if point is None:
            return _not_found("charging point", charging_point_id)
        if point.version != expected_version:
            return _version_conflict(
                "charging point", charging_point_id, expected_version, point.version
            )
        if point.status is status:
            return Ok(ChargingPointView.of(point))
        previous = point.status
        point.status = status
        rt.repo.update(point, expected_version)
        rt.log_change(
            "ChargingPoint",
            charging_point_id,
            previous.value,
            status.value,
            "set_status",
            actor.label(),
        )
        rt.emit(
            EventType.CHARGING_POINT_STATUS_CHANGED,
            {
                "charging_point_id": charging_point_id,
                "hub_id": point.hub_id,
                "previous": previous.value,
                "new": status.value,
                "at": rt.now().isoformat(),
            },
        )
        return Ok(ChargingPointView.of(point))

    def set_hub_status(
        self, hub_id: str, status: HubStatus, expected_version: int, actor: Actor
    ) -> Result[HubStatusView]:
        """Store the Hub status decided by M5 (BR-M5-01, BR-M5-02)."""
        return self._rt.run(lambda: self._set_hub_status(hub_id, status, expected_version, actor))

    def _set_hub_status(
        self, hub_id: str, status: HubStatus, expected_version: int, actor: Actor
    ) -> Result[HubStatusView]:
        rt = self._rt
        if not permissions.may_set_hub_status(actor):
            return _forbidden(actor, "set a hub status")
        hub = rt.repo.get(Hub, hub_id)
        if hub is None:
            return _not_found("hub", hub_id)
        if hub.version != expected_version:
            return _version_conflict("hub", hub_id, expected_version, hub.version)
        if hub.status is status:
            return Ok(HubStatusView.of(hub))
        previous = hub.status
        hub.status = status
        rt.repo.update(hub, expected_version)
        rt.log_change("Hub", hub_id, previous.value, status.value, "set_status", actor.label())
        rt.emit(
            EventType.HUB_STATUS_CHANGED,
            {
                "hub_id": hub_id,
                "previous": previous.value,
                "new": status.value,
                "at": rt.now().isoformat(),
            },
        )
        return Ok(HubStatusView.of(hub))
