# ASSUMPTIONS:
# 1. Private vehicles (Ownership.PRIVATE) are created in NetworkSpec.private_vehicles; when parked
#    at a hub, they do not participate in fleet redistribution in plan() and are excluded from
#    available_vehicles in AlternativeHubService.
# 2. The ReservationDemand port is registered once on a fresh CoreFacade via
#    core.register_provider(ProviderPort.RESERVATION_DEMAND, stub). When no provider is registered
#    or the provider returns Err / raises an exception, plan() returns Err(RESOURCE_UNAVAILABLE).
# 3. When approve_task() encounters a resource conflict or precondition violation, the task
#    transitions to FAILED and returns the corresponding error code.
# 4. Every allocation endpoint requires require_operator, returning 401 when no bearer token is
#    supplied and 403 when a student (STUDENT) token from POST /auth/login is used.

import dataclasses
import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import get_type_hints

import pytest
from fastapi.testclient import TestClient

from allocation.alternatives import AlternativeChargingService, AlternativeHubService
from allocation.config import AllocationConfig
from allocation.models import DISPATCH_TASK_SPEC, DispatchTask, DispatchTaskStatus
from allocation.service import AllocationService
from core.actor import Actor
from core.auth import AuthConfig, hash_password
from core.clock import FixedClock
from core.config import CoreConfig
from core.domain.entities import ResourceClaim, Vehicle
from core.domain.enums import ClaimStatus, HolderKind, ResourceType, Role, VehicleState, VehicleType
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.providers import (
    AlternativeChargingResult,
    AlternativeHubRequest,
    AlternativeHubResult,
    BookingDemand,
    BookingDemandKind,
    ChargingAlternative,
    DisplacedChargingRequest,
    HubAlternative,
    OpenTripDemand,
    OpenTrips,
    ProviderPort,
    UpcomingBookings,
)
from core.repository.memory import InMemoryRepository
from core.result import Err, Ok, Result
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec
from main import Settings, build_app


class StubReservationDemand:
    def __init__(
        self,
        as_of: datetime,
        bookings_by_hub: dict[str, tuple[BookingDemand, ...]] | None = None,
        trips_by_hub: dict[str, tuple[OpenTripDemand, ...]] | None = None,
        raise_on_bookings: bool = False,
        raise_on_trips: bool = False,
        err_on_bookings: bool = False,
        err_on_trips: bool = False,
    ) -> None:
        self.as_of = as_of
        self.bookings_by_hub = bookings_by_hub or {}
        self.trips_by_hub = trips_by_hub or {}
        self.raise_on_bookings = raise_on_bookings
        self.raise_on_trips = raise_on_trips
        self.err_on_bookings = err_on_bookings
        self.err_on_trips = err_on_trips

    def upcoming_bookings(self, hub_id: str, horizon: timedelta) -> Result[UpcomingBookings]:
        if self.raise_on_bookings:
            raise RuntimeError("upcoming_bookings crash")
        if self.err_on_bookings:
            return Err(ErrorCode.RESOURCE_UNAVAILABLE, "demand bookings unavailable")
        return Ok(
            UpcomingBookings(self.as_of, self.as_of + horizon, self.bookings_by_hub.get(hub_id, ()))
        )

    def open_trips(self, hub_id: str) -> Result[OpenTrips]:
        if self.raise_on_trips:
            raise RuntimeError("open_trips crash")
        if self.err_on_trips:
            return Err(ErrorCode.RESOURCE_UNAVAILABLE, "demand trips unavailable")
        return Ok(OpenTrips(self.as_of, self.trips_by_hub.get(hub_id, ())))


@pytest.fixture
def base_now() -> datetime:
    return datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
def operator_actor() -> Actor:
    return Actor("OP01", Role.OPERATOR, "allocation")


@dataclasses.dataclass(frozen=True, slots=True)
class AllocationEnv:
    core: CoreFacade
    service: AllocationService
    alt_hub: AlternativeHubService
    alt_charge: AlternativeChargingService
    clock: FixedClock


_DEFAULT_DEMAND: object = object()
EnvFactory = Callable[..., AllocationEnv]


@pytest.fixture
def make_env(base_now: datetime, operator_actor: Actor) -> EnvFactory:
    def _build(
        demand_provider: StubReservationDemand | None | object = _DEFAULT_DEMAND,
    ) -> AllocationEnv:
        clock = FixedClock(base_now)
        core = CoreFacade(InMemoryRepository(), clock=clock, config=CoreConfig())
        core.register_entity(DISPATCH_TASK_SPEC)

        spec = NetworkSpec(
            hubs=(
                HubSpec(
                    "H01",
                    "Hub 1",
                    "Z1",
                    10,
                    1,
                    vehicles=(
                        VehicleSpec("V000", "PLATE-0", VehicleType.E_BIKE, 80.0),
                        VehicleSpec("V001", "PLATE-1", VehicleType.E_BIKE, 85.0),
                        VehicleSpec("V002", "PLATE-2", VehicleType.E_BIKE, 90.0),
                        VehicleSpec("V003", "PLATE-3", VehicleType.E_BIKE, 75.0),
                    ),
                ),
                HubSpec("H02", "Hub 2", "Z2", 10, 1),
                HubSpec("H03", "Hub 3", "Z3", 10, 1),
            ),
            users=(
                UserSpec("OP01", "OP-01", Role.OPERATOR, hash_password("pw-op", 1000)),
                UserSpec("STU01", "STU-01", Role.STUDENT, hash_password("pw-stu", 1000)),
            ),
            private_vehicles=(
                VehicleSpec(
                    "V_PRIV",
                    "PLATE-PRIV",
                    VehicleType.E_BIKE,
                    80.0,
                    owner_user_id="STU01",
                    connector_type="TYPE2",
                ),
            ),
        )
        assert isinstance(core.commands.load_network(spec, operator_actor), Ok)

        cfg = AllocationConfig(
            safety_stock=1,
            parking_buffer=2,
            min_dispatch_battery=30.0,
            horizon_minutes=30,
            reservation_lookahead_minutes=60,
        )
        service = AllocationService(core, cfg)
        alt_hub_svc = AlternativeHubService(core, cfg)
        alt_charge_svc = AlternativeChargingService(core, cfg)

        core.register_provider(ProviderPort.ALTERNATIVE_HUB, alt_hub_svc)
        core.register_provider(ProviderPort.ALTERNATIVE_CHARGING, alt_charge_svc)
        if demand_provider is _DEFAULT_DEMAND:
            core.register_provider(ProviderPort.RESERVATION_DEMAND, StubReservationDemand(base_now))
        elif isinstance(demand_provider, StubReservationDemand):
            core.register_provider(ProviderPort.RESERVATION_DEMAND, demand_provider)
        return AllocationEnv(core, service, alt_hub_svc, alt_charge_svc, clock)

    return _build


@pytest.fixture
def test_env(make_env: EnvFactory) -> AllocationEnv:
    return make_env()


# M4-4: Dataclass Frozen & Protocol Compliance
@pytest.mark.tc_m4_011
def test_m4_4_dataclasses_are_frozen() -> None:
    """M4-4: Provider dataclasses must be frozen."""
    req = AlternativeHubRequest(requested_hub_id="H01")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        req.requested_hub_id = "H02"  # type: ignore[misc]

    alt = HubAlternative("H02", "Hub 2", 1, 3, 5, 80.0)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        alt.closeness = 2  # type: ignore[misc]

    res = AlternativeHubResult(candidates=(alt,), as_of=datetime.now(UTC), reason_code="OK")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        res.reason_code = "NO_VEHICLE"  # type: ignore[misc]

    disp = DisplacedChargingRequest(request_id="REQ-1")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        disp.request_id = "REQ-2"  # type: ignore[misc]

    chg_alt = ChargingAlternative("REQ-1", "H02", "H02-CP01", 1, "FOUND")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        chg_alt.status = "NO_CHARGER"  # type: ignore[misc]

    chg_res = AlternativeChargingResult(alternatives=(chg_alt,), as_of=datetime.now(UTC))
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        chg_res.alternatives = ()  # type: ignore[misc]


@pytest.mark.tc_m4_011
def test_m4_4_no_dict_any_in_provider_dataclass_annotations() -> None:
    """M4-4: Provider dataclasses must use strict typed fields and never dict[str, Any]."""
    for cls in [
        AlternativeHubRequest,
        HubAlternative,
        AlternativeHubResult,
        DisplacedChargingRequest,
        ChargingAlternative,
        AlternativeChargingResult,
    ]:
        for f_name, f_type in get_type_hints(cls).items():
            assert "dict" not in str(f_type).lower(), f"{cls.__name__}.{f_name} uses dict"


@pytest.mark.tc_m4_011
def test_m4_4_services_implement_provider_protocols(test_env: AllocationEnv) -> None:
    """M4-4: Alternative services implement Protocol methods and register with Core."""
    core, alt_hub_svc, alt_charge_svc = test_env.core, test_env.alt_hub, test_env.alt_charge
    assert hasattr(alt_hub_svc, "suggest_alternative_hubs") and callable(
        alt_hub_svc.suggest_alternative_hubs
    )
    assert hasattr(alt_charge_svc, "find_alternative_charging") and callable(
        alt_charge_svc.find_alternative_charging
    )

    req = AlternativeHubRequest(requested_hub_id="H02", require_vehicle=True)
    hub_res = core.providers.call(
        ProviderPort.ALTERNATIVE_HUB, lambda p: p.suggest_alternative_hubs(req)
    )
    assert isinstance(hub_res, Ok) and isinstance(hub_res.value, AlternativeHubResult)

    disp = [DisplacedChargingRequest(request_id="R-1")]
    chg_res = core.providers.call(
        ProviderPort.ALTERNATIVE_CHARGING, lambda p: p.find_alternative_charging(disp, "H01")
    )
    assert isinstance(chg_res, Ok) and isinstance(chg_res.value, AlternativeChargingResult)


# M4-3: Time Source via core.queries.get_config().as_of
@pytest.mark.tc_m4_027
def test_m4_3_services_never_access_core_clock_attribute() -> None:
    """M4-3: Allocation and alternatives modules must not read core._clock."""
    import allocation.alternatives as alt_module
    import allocation.service as svc_module

    assert "._clock" not in inspect.getsource(svc_module)
    assert "._clock" not in inspect.getsource(alt_module)


@pytest.mark.tc_m4_027
def test_m4_3_services_use_as_of_from_queries_config(
    test_env: AllocationEnv,
    base_now: datetime,
) -> None:
    """M4-3: Services reflect simulated time updates from core.queries.get_config().as_of."""
    core, alt_hub_svc, alt_charge_svc = test_env.core, test_env.alt_hub, test_env.alt_charge
    assert core.queries.get_config().as_of == base_now

    advanced_now = base_now + timedelta(hours=3)
    test_env.clock.set(advanced_now)
    assert core.queries.get_config().as_of == advanced_now

    hub_res = alt_hub_svc.suggest_alternative_hubs(AlternativeHubRequest(requested_hub_id="H02"))
    assert isinstance(hub_res, Ok) and hub_res.value.as_of == advanced_now

    chg_res = alt_charge_svc.find_alternative_charging([DisplacedChargingRequest("R1")], "H01")
    assert isinstance(chg_res, Ok) and chg_res.value.as_of == advanced_now


# M4-1 & M4-2: ReservationDemand upcoming_bookings & open_trips & No Fallbacks
@pytest.mark.tc_m4_023
def test_m4_1_upcoming_bookings_counts_only_rental_pickup(
    make_env: EnvFactory,
    base_now: datetime,
    operator_actor: Actor,
) -> None:
    """M4-1: plan() must count only RENTAL_PICKUP kind from upcoming_bookings."""
    bookings = (
        BookingDemand(
            "RES-1",
            BookingDemandKind.RENTAL_PICKUP,
            "H01",
            "V000",
            "S1",
            "C1",
            base_now,
            base_now,
            base_now,
        ),
        BookingDemand(
            "RES-2",
            BookingDemandKind.PRIVATE_PARKING,
            "H01",
            "V_PRIV",
            "S2",
            "C2",
            base_now,
            base_now,
            base_now,
        ),
        BookingDemand(
            "RES-3",
            BookingDemandKind.RENTAL_RETURN,
            "H01",
            "V001",
            "S3",
            "C3",
            base_now,
            base_now,
            base_now,
        ),
    )
    env = make_env(StubReservationDemand(base_now, bookings_by_hub={"H01": bookings}))
    plan_res = env.service.plan(operator_actor, "slot_test_m4_1")
    assert isinstance(plan_res, Ok)
    assert sum(t.quantity for t in plan_res.value if t.source_hub_id == "H01") == 2


@pytest.mark.tc_m4_023
def test_m4_2_open_trips_filtering_destination_and_horizon_and_deduplicates(
    make_env: EnvFactory,
    base_now: datetime,
    operator_actor: Actor,
) -> None:
    """M4-2: plan() filters trips by destination == hub_id, horizon, and deduplicates trip_id."""
    trips = (
        OpenTripDemand(
            "TRIP-1",
            "RES-1",
            "V000",
            "H01",
            "H02",
            base_now,
            base_now + timedelta(minutes=15),
            False,
        ),
        OpenTripDemand(
            "TRIP-2",
            "RES-2",
            "V001",
            "H01",
            None,
            base_now,
            base_now + timedelta(minutes=15),
            False,
        ),
        OpenTripDemand(
            "TRIP-3",
            "RES-3",
            "V002",
            "H02",
            "H01",
            base_now,
            base_now + timedelta(minutes=15),
            False,
        ),
        OpenTripDemand(
            "TRIP-4",
            "RES-4",
            "V003",
            "H01",
            "H02",
            base_now,
            base_now + timedelta(minutes=45),
            False,
        ),
        OpenTripDemand(
            "TRIP-1",
            "RES-1",
            "V000",
            "H01",
            "H02",
            base_now,
            base_now + timedelta(minutes=15),
            False,
        ),
    )
    env = make_env(StubReservationDemand(base_now, trips_by_hub={"H02": trips}))
    assert isinstance(env.service.plan(operator_actor, "slot_test_m4_2"), Ok)


@pytest.mark.tc_m4_022
def test_m4_1_m4_2_plan_fails_when_reservation_demand_missing(
    make_env: EnvFactory,
    operator_actor: Actor,
) -> None:
    """M4-1 & M4-2: plan() returns RESOURCE_UNAVAILABLE without fallback
    when provider is missing.
    """
    env = make_env(None)
    res = env.service.plan(operator_actor, "slot_fail")
    assert isinstance(res, Err) and res.code == ErrorCode.RESOURCE_UNAVAILABLE


@pytest.mark.tc_m4_022
def test_m4_1_m4_2_plan_fails_when_upcoming_bookings_errors(
    make_env: EnvFactory,
    base_now: datetime,
    operator_actor: Actor,
) -> None:
    """M4-1: plan() returns RESOURCE_UNAVAILABLE if upcoming_bookings fails or raises."""
    env_err = make_env(StubReservationDemand(base_now, err_on_bookings=True))
    res_err = env_err.service.plan(operator_actor, "slot_err")
    assert isinstance(res_err, Err) and res_err.code == ErrorCode.RESOURCE_UNAVAILABLE

    env_crash = make_env(StubReservationDemand(base_now, raise_on_bookings=True))
    res_crash = env_crash.service.plan(operator_actor, "slot_crash")
    assert isinstance(res_crash, Err) and res_crash.code == ErrorCode.RESOURCE_UNAVAILABLE


@pytest.mark.tc_m4_022
def test_m4_1_m4_2_plan_fails_when_open_trips_errors(
    make_env: EnvFactory,
    base_now: datetime,
    operator_actor: Actor,
) -> None:
    """M4-2: plan() returns RESOURCE_UNAVAILABLE if open_trips fails or raises."""
    env = make_env(StubReservationDemand(base_now, err_on_trips=True))
    res = env.service.plan(operator_actor, "slot_err_trips")
    assert isinstance(res, Err) and res.code == ErrorCode.RESOURCE_UNAVAILABLE


# Lifecycle & Resource Claims
@pytest.mark.tc_m4_018
def test_carry_out_return_passes_parking_space_and_claim_id_to_transition_ctx(
    test_env: AllocationEnv,
    operator_actor: Actor,
) -> None:
    """Lifecycle: carry_out_return() passes space and claim_id from SPACE claim
    into TransitionCtx and completes task.
    """
    core, service = test_env.core, test_env.service
    task = service.plan(operator_actor, "slot_return_test").value[0]
    service.approve_task(task.task_id, operator_actor)
    service.carry_out_pickup(task.task_id, operator_actor)

    claims_before = core.query_entities(
        ResourceClaim, lambda c: c.holder_ref == task.task_id and c.status == ClaimStatus.ACTIVE
    )
    space_claims = [c for c in claims_before if c.resource_type == ResourceType.SPACE]
    expected_space_ids = {c.resource_id for c in space_claims}

    ret_res = service.carry_out_return(task.task_id, operator_actor, battery_pct=70.0)
    assert isinstance(ret_res, Ok) and ret_res.value.status == DispatchTaskStatus.COMPLETED

    for vid in task.assigned_vehicles:
        veh_r = core.queries.get_vehicle(vid)
        assert isinstance(veh_r, Ok)
        assert veh_r.value.hub_id == task.target_hub_id
        assert veh_r.value.parking_space_id in expected_space_ids
        assert veh_r.value.state in (VehicleState.AVAILABLE, VehicleState.RETURNED)


@pytest.mark.tc_m4_018
def test_carry_out_return_releases_all_remaining_dispatch_claims(
    test_env: AllocationEnv,
    operator_actor: Actor,
) -> None:
    """Lifecycle: carry_out_return() must release all remaining claims associated with the task."""
    core, service = test_env.core, test_env.service
    task = service.plan(operator_actor, "slot_rel_test").value[0]
    service.approve_task(task.task_id, operator_actor)
    service.carry_out_pickup(task.task_id, operator_actor)
    service.carry_out_return(task.task_id, operator_actor)

    active_claims = core.query_entities(
        ResourceClaim, lambda c: c.holder_ref == task.task_id and c.status == ClaimStatus.ACTIVE
    )
    assert len(active_claims) == 0


@pytest.mark.tc_m4_025
@pytest.mark.parametrize("invalid_qty", [0, -1, 5, 99])
def test_approve_task_validates_adjusted_quantity_boundaries(
    test_env: AllocationEnv,
    operator_actor: Actor,
    invalid_qty: int,
) -> None:
    """approve_task: rejects adjusted_quantity <= 0 or > len(assigned_vehicles)
    with INVALID_INPUT.
    """
    service = test_env.service
    task = service.plan(operator_actor, "slot_adj_test").value[0]
    res = service.approve_task(task.task_id, operator_actor, adjusted_quantity=invalid_qty)
    assert isinstance(res, Err) and res.code == ErrorCode.INVALID_INPUT


@pytest.mark.tc_m4_025
def test_approve_task_with_valid_adjusted_quantity(
    make_env: EnvFactory,
    base_now: datetime,
    operator_actor: Actor,
) -> None:
    """approve_task: adjusted_quantity limits claimed vehicles and destination spaces."""
    demand = StubReservationDemand(
        base_now,
        bookings_by_hub={
            "H02": (
                BookingDemand(
                    "R1",
                    BookingDemandKind.RENTAL_PICKUP,
                    "H02",
                    "V1",
                    "S1",
                    "C1",
                    base_now,
                    base_now,
                    base_now,
                ),
                BookingDemand(
                    "R2",
                    BookingDemandKind.RENTAL_PICKUP,
                    "H02",
                    "V2",
                    "S2",
                    "C2",
                    base_now,
                    base_now,
                    base_now,
                ),
            )
        },
    )
    env = make_env(demand)
    core, service = env.core, env.service
    task = service.plan(operator_actor, "slot_adj_valid").value[0]
    assert task.quantity >= 2

    app_res = service.approve_task(task.task_id, operator_actor, adjusted_quantity=1)
    assert (
        isinstance(app_res, Ok)
        and app_res.value.quantity == 1
        and len(app_res.value.assigned_vehicles) == 1
    )

    claims = core.query_entities(
        ResourceClaim, lambda c: c.holder_ref == task.task_id and c.status == ClaimStatus.ACTIVE
    )
    assert len([c for c in claims if c.resource_type == ResourceType.VEHICLE]) == 1
    assert len([c for c in claims if c.resource_type == ResourceType.SPACE]) == 1


@pytest.mark.tc_m4_025
def test_approve_task_filters_spaces_with_active_claims(
    test_env: AllocationEnv,
    base_now: datetime,
    operator_actor: Actor,
) -> None:
    """approve_task: avoids destination spaces that already have an ACTIVE claim."""
    core, service = test_env.core, test_env.service
    task = service.plan(operator_actor, "slot_claim_conflict").value[0]
    core.commands.place_claim(
        ResourceType.SPACE,
        "H02-S001",
        HolderKind.DISPATCH_TASK,
        "OTHER",
        base_now,
        base_now + timedelta(hours=2),
        operator_actor,
    )

    app_res = service.approve_task(task.task_id, operator_actor)
    assert isinstance(app_res, Ok)

    task_space_claims = core.query_entities(
        ResourceClaim,
        lambda c: (
            c.holder_ref == task.task_id
            and c.resource_type == ResourceType.SPACE
            and c.status == ClaimStatus.ACTIVE
        ),
    )
    assert "H02-S001" not in {c.resource_id for c in task_space_claims}


@pytest.mark.tc_m4_024
def test_approve_task_fails_and_marks_failed_on_invalid_vehicle_state_or_battery(
    test_env: AllocationEnv,
    operator_actor: Actor,
) -> None:
    """approve_task: marks task FAILED without nested UoW error
    when vehicle condition is violated.
    """
    core, service = test_env.core, test_env.service
    task = DispatchTask(
        task_id="TASK-LOW-BATT",
        source_hub_id="H01",
        target_hub_id="H02",
        vehicle_type=VehicleType.E_BIKE,
        quantity=1,
        vehicle_ids="V000",
        status=DispatchTaskStatus.RECOMMENDED,
        priority=1,
    )
    with core.unit_of_work() as uow:
        uow.repository.add(task)
        uow.commit()

    with core.unit_of_work() as uow:
        v = uow.repository.get(Vehicle, "V000")
        assert v is not None
        v.battery_pct = 15.0
        uow.repository.update(v, expected_version=v.version)
        uow.commit()

    res = service.approve_task("TASK-LOW-BATT", operator_actor)
    assert isinstance(res, Err) and res.code == ErrorCode.BATTERY_TOO_LOW
    saved_task = core.get_entity(DispatchTask, "TASK-LOW-BATT")
    assert saved_task is not None and saved_task.status == DispatchTaskStatus.FAILED


@pytest.mark.tc_m4_018
def test_approve_task_does_not_manually_increment_version(
    test_env: AllocationEnv,
    operator_actor: Actor,
) -> None:
    """approve_task: must not manually increment task.version before repository.update."""
    service = test_env.service
    task = service.plan(operator_actor, "slot_ver_check").value[0]
    initial_version = task.version
    app_res = service.approve_task(task.task_id, operator_actor)
    assert isinstance(app_res, Ok) and app_res.value.version == initial_version + 1


# Claims Expiration, Fleet Ownership & Alternatives Filtering
@pytest.mark.tc_m4_014
def test_plan_and_alternatives_filter_expired_active_claims(
    test_env: AllocationEnv,
    base_now: datetime,
    operator_actor: Actor,
) -> None:
    """plan() and alternatives ignore claims where end_at <= now even if status is ACTIVE."""
    core, alt_hub_svc, alt_charge_svc = test_env.core, test_env.alt_hub, test_env.alt_charge
    past_end = base_now - timedelta(minutes=10)
    core.commands.place_claim(
        ResourceType.VEHICLE,
        "V000",
        HolderKind.DISPATCH_TASK,
        "EXP",
        base_now - timedelta(hours=1),
        past_end,
        operator_actor,
    )
    core.commands.place_claim(
        ResourceType.SPACE,
        "H02-S001",
        HolderKind.DISPATCH_TASK,
        "EXP",
        base_now - timedelta(hours=1),
        past_end,
        operator_actor,
    )

    hub_res = alt_hub_svc.suggest_alternative_hubs(
        AlternativeHubRequest(requested_hub_id="H02", require_vehicle=True)
    )
    assert isinstance(hub_res, Ok)
    cand_h01 = next(c for c in hub_res.value.candidates if c.hub_id == "H01")
    assert cand_h01.available_vehicles == 4

    chg_res = alt_charge_svc.find_alternative_charging([DisplacedChargingRequest("R1")], "H01")
    assert isinstance(chg_res, Ok)
    assert (
        chg_res.value.alternatives[0].status == "FOUND"
        and chg_res.value.alternatives[0].alternative_hub_id == "H02"
    )


@pytest.mark.tc_m4_014
def test_plan_and_alternatives_filter_fleet_ownership(
    test_env: AllocationEnv,
    operator_actor: Actor,
) -> None:
    """plan() and suggest_alternative_hubs() only consider Ownership.FLEET vehicles."""
    core, service, alt_hub_svc = test_env.core, test_env.service, test_env.alt_hub
    with core.unit_of_work() as uow:
        priv_v = uow.repository.get(Vehicle, "V_PRIV")
        assert priv_v is not None
        priv_v.hub_id = "H01"
        uow.repository.update(priv_v, expected_version=priv_v.version)
        uow.commit()

    hub_res = alt_hub_svc.suggest_alternative_hubs(
        AlternativeHubRequest(requested_hub_id="H02", require_vehicle=True)
    )
    assert isinstance(hub_res, Ok)
    assert next(c for c in hub_res.value.candidates if c.hub_id == "H01").available_vehicles == 4

    plan_res = service.plan(operator_actor, "slot_fleet_filter")
    assert isinstance(plan_res, Ok)
    for task in plan_res.value:
        assert "V_PRIV" not in task.assigned_vehicles


@pytest.mark.tc_m4_017
def test_find_alternative_charging_checks_space_status_and_claims(
    test_env: AllocationEnv,
    base_now: datetime,
    operator_actor: Actor,
) -> None:
    """find_alternative_charging: only suggests charging points whose
    bay space is AVAILABLE and unclaimed.
    """
    core, alt_charge_svc = test_env.core, test_env.alt_charge
    core.commands.place_claim(
        ResourceType.SPACE,
        "H02-S001",
        HolderKind.DISPATCH_TASK,
        "ACT",
        base_now,
        base_now + timedelta(hours=1),
        operator_actor,
    )

    chg_res = alt_charge_svc.find_alternative_charging([DisplacedChargingRequest("R1")], "H01")
    assert isinstance(chg_res, Ok) and chg_res.value.alternatives[0].alternative_hub_id == "H03"


@pytest.mark.tc_m4_015
@pytest.mark.parametrize(
    ("method", "args", "expected_err"),
    [
        ("plan", ("",), ErrorCode.INVALID_INPUT),
        ("plan", ("   ",), ErrorCode.INVALID_INPUT),
        (
            "suggest_alternative_hubs",
            (AlternativeHubRequest(requested_hub_id=""),),
            ErrorCode.INVALID_INPUT,
        ),
        (
            "suggest_alternative_hubs",
            (AlternativeHubRequest(requested_hub_id="H01", limit=0),),
            ErrorCode.INVALID_INPUT,
        ),
        ("find_alternative_charging", ([], ""), ErrorCode.INVALID_INPUT),
        (
            "find_alternative_charging",
            ([DisplacedChargingRequest("")], "H01"),
            ErrorCode.INVALID_INPUT,
        ),
    ],
)
def test_input_validation_empty_or_invalid_inputs(
    test_env: AllocationEnv,
    operator_actor: Actor,
    method: str,
    args: tuple[object, ...],
    expected_err: ErrorCode,
) -> None:
    """Validation: empty IDs, zero limits and invalid arguments return INVALID_INPUT."""
    service, alt_hub_svc, alt_charge_svc = (
        test_env.service,
        test_env.alt_hub,
        test_env.alt_charge,
    )
    if method == "plan":
        res = service.plan(operator_actor, *args)  # type: ignore[arg-type]
    elif method == "suggest_alternative_hubs":
        res = alt_hub_svc.suggest_alternative_hubs(*args)  # type: ignore[arg-type]
    else:
        res = alt_charge_svc.find_alternative_charging(*args)  # type: ignore[arg-type]
    assert isinstance(res, Err) and res.code == expected_err


# M4-7: Router Security (require_operator, 401, 403, acting_as)
ROUTER_ENDPOINTS: list[tuple[str, str, dict[str, object] | None]] = [
    ("POST", "/allocation/tasks/plan", {"slot_id": "slot1"}),
    ("GET", "/allocation/tasks", None),
    ("GET", "/allocation/tasks/TASK-TEST", None),
    ("POST", "/allocation/tasks/TASK-TEST/approve", {}),
    ("POST", "/allocation/tasks/TASK-TEST/pickup", None),
    ("POST", "/allocation/tasks/TASK-TEST/return", {}),
    ("POST", "/allocation/tasks/TASK-TEST/cancel", {}),
    ("GET", "/allocation/alternatives/hubs?requested_hub_id=H01", None),
    (
        "POST",
        "/allocation/alternatives/charging",
        {"displaced_requests": [], "failed_hub_id": "H01"},
    ),
    ("POST", "/allocation/arbitrate", {"requests": []}),
    ("GET", "/allocation/config", None),
    ("PUT", "/allocation/config", {}),
]


def _make_api_client(base_now: datetime) -> TestClient:
    repo = InMemoryRepository()
    clock = FixedClock(base_now)
    settings = Settings(
        core=CoreConfig(), auth=AuthConfig(secret_key="secret-key-at-least-32-bytes-long-padding!")
    )
    app = build_app(settings, repository=repo, clock=clock, module_names=("allocation",))
    core: CoreFacade = app.state.core
    admin = Actor("OP01", Role.OPERATOR, "core")

    spec = NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Hub 1",
                "Z1",
                10,
                1,
                vehicles=tuple(
                    VehicleSpec(f"V00{i}", f"PLATE-{i}", VehicleType.E_BIKE, 80.0) for i in range(4)
                ),
            ),
            HubSpec("H02", "Hub 2", "Z2", 10, 1),
        ),
        users=(
            UserSpec("OP01", "OP-01", Role.OPERATOR, hash_password("pw-op", 1000)),
            UserSpec("STU01", "STU-01", Role.STUDENT, hash_password("pw-stu", 1000)),
        ),
    )
    core.commands.load_network(spec, admin)
    core.register_provider(ProviderPort.RESERVATION_DEMAND, StubReservationDemand(base_now))
    return TestClient(app)


@pytest.mark.tc_m4_031
@pytest.mark.parametrize(("method", "path", "body"), ROUTER_ENDPOINTS)
def test_m4_7_router_endpoints_reject_unauthenticated_with_401(
    base_now: datetime, method: str, path: str, body: dict[str, object] | None
) -> None:
    """M4-7: Every allocation router endpoint returns 401 UNAUTHENTICATED without Bearer token."""
    client = _make_api_client(base_now)
    res = client.request(method, path, json=body)
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == "Bearer"
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.tc_m4_032
@pytest.mark.parametrize(("method", "path", "body"), ROUTER_ENDPOINTS)
def test_m4_7_router_endpoints_reject_student_with_403(
    base_now: datetime, method: str, path: str, body: dict[str, object] | None
) -> None:
    """M4-7: Every allocation router endpoint returns 403 FORBIDDEN for student role."""
    client = _make_api_client(base_now)
    login_res = client.post("/auth/login", json={"code": "STU-01", "password": "pw-stu"})
    assert login_res.status_code == 200
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    res = client.request(method, path, json=body, headers=headers)
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.tc_m4_032
def test_m4_7_router_endpoints_allow_operator_and_use_acting_as(base_now: datetime) -> None:
    """M4-7: Operator token is accepted and endpoints construct actor
    via acting_as(principal, 'allocation').
    """
    client = _make_api_client(base_now)
    login_res = client.post("/auth/login", json={"code": "OP-01", "password": "pw-op"})
    assert login_res.status_code == 200
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    assert client.get("/allocation/config", headers=headers).status_code == 200
    assert (
        client.post(
            "/allocation/tasks/plan", json={"slot_id": "slot_api"}, headers=headers
        ).status_code
        == 200
    )

    res_alt = client.get("/allocation/alternatives/hubs?requested_hub_id=H02", headers=headers)
    assert res_alt.status_code == 200
    assert {"candidates", "as_of", "reason_code"}.issubset(res_alt.json().keys())


# M4-6: Direct Imports from core.providers
@pytest.mark.tc_m4_011
def test_m4_6_direct_imports_from_core_providers() -> None:
    """M4-6: ReservationDemand, UpcomingBookings, OpenTrips and related
    types are directly imported from core.providers.
    """
    import core.providers as cp

    expected = [
        "ReservationDemand",
        "UpcomingBookings",
        "OpenTrips",
        "BookingDemand",
        "BookingDemandKind",
        "OpenTripDemand",
        "AlternativeHubProvider",
        "AlternativeChargingProvider",
        "AlternativeHubRequest",
        "HubAlternative",
        "AlternativeHubResult",
        "DisplacedChargingRequest",
        "ChargingAlternative",
        "AlternativeChargingResult",
    ]
    for sym in expected:
        assert hasattr(cp, sym), f"core.providers is missing exported symbol {sym}"
