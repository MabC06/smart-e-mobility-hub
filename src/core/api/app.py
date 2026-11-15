"""The REST interface of core (docs/design/architecture/core-api-spec.md, section 8).

Read-only for the user interface, plus the sensor intake of the simulator. State-changing
endpoints of a workflow belong to the module that owns it and call core in-process.

Rules (NFR-16, NFR-18, NFR-21):
- Every endpoint except ``POST /auth/login`` needs a bearer token (401 without one).
- Operator-only endpoints give 403 to a student. A student sees fleet vehicles only, never the
  private vehicles of other students.
- Invalid input gives 400 with a message; an unexpected failure gives 500 with a generic message
  and no stack trace, and is logged.
- Every error has the same body: ``{"error": {"code", "message", "details"}}``.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, FastAPI, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.api.errors import ApiError, fail
from core.api.schemas import (
    ChargingPointOut,
    ErrorOut,
    HubOut,
    LoginIn,
    LoginOut,
    MeOut,
    SensorResultOut,
    SpaceOut,
    StateLogOut,
    VehicleOut,
)
from core.api.security import check_bearer, check_role
from core.auth import AuthService, Principal
from core.domain.enums import (
    ChargingPointStatus,
    Ownership,
    Role,
    SpaceStatus,
    VehicleState,
    VehicleType,
)
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.result import Err
from core.sensors import SensorEvent
from core.views import VehicleFilter

logger = logging.getLogger("core.api")

STATUS_OF: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.INVALID_TRANSITION: 409,
    ErrorCode.CLAIM_CONFLICT: 409,
    ErrorCode.HUB_FULL: 409,
    ErrorCode.SPACE_NOT_FREE: 409,
    ErrorCode.RESOURCE_UNAVAILABLE: 409,
    ErrorCode.BATTERY_TOO_LOW: 409,
    ErrorCode.INTERNAL_ERROR: 500,
}

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorOut} for status in (400, 401, 403, 404, 409, 500)
}


def _error_response(error: Err) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if error.code is ErrorCode.UNAUTHENTICATED else None
    body = {
        "error": {
            "code": error.code.value,
            "message": error.message,
            "details": jsonable_encoder(dict(error.details)),
        }
    }
    return JSONResponse(body, status_code=STATUS_OF[error.code], headers=headers)


def _raise_if_err(result: object) -> None:
    if isinstance(result, Err):
        raise ApiError(result)


def create_router(core: CoreFacade, auth: AuthService) -> APIRouter:
    """All endpoints of core. Mount it in the application (``src/main.py``)."""
    router = APIRouter()

    def principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
        return check_bearer(auth, authorization)

    def operator(who: Annotated[Principal, Depends(principal)]) -> Principal:
        return check_role(who, Role.OPERATOR, "this endpoint is for operators")

    def simulator(who: Annotated[Principal, Depends(principal)]) -> Principal:
        if who.role is not Role.OPERATOR or who.module != "iot_sim":
            raise fail(
                ErrorCode.FORBIDDEN, "this endpoint is for the simulator's service credential"
            )
        return who

    def known_hub(hub_id: str) -> None:
        _raise_if_err(core.queries.get_hub(hub_id))

    @router.post("/auth/login", response_model=LoginOut, responses=_ERRORS, tags=["auth"])
    def login(body: LoginIn) -> LoginOut:
        result = auth.login(body.code, body.password)
        if isinstance(result, Err):
            raise ApiError(result)
        return LoginOut.model_validate(result.value)

    @router.get("/me", response_model=MeOut, responses=_ERRORS, tags=["auth"])
    def me(who: Annotated[Principal, Depends(principal)]) -> MeOut:
        return MeOut.model_validate(who)

    @router.get("/hubs", response_model=list[HubOut], responses=_ERRORS, tags=["hubs"])
    def list_hubs(_who: Annotated[Principal, Depends(principal)]) -> list[HubOut]:
        return [HubOut.model_validate(h) for h in core.queries.list_hubs()]

    @router.get("/hubs/{hub_id}", response_model=HubOut, responses=_ERRORS, tags=["hubs"])
    def get_hub(hub_id: str, _who: Annotated[Principal, Depends(principal)]) -> HubOut:
        result = core.queries.get_hub(hub_id)
        if isinstance(result, Err):
            raise ApiError(result)
        return HubOut.model_validate(result.value)

    @router.get(
        "/hubs/{hub_id}/vehicles",
        response_model=list[VehicleOut],
        responses=_ERRORS,
        tags=["hubs"],
    )
    def list_vehicles(
        hub_id: str,
        who: Annotated[Principal, Depends(principal)],
        state: VehicleState | None = None,
        vehicle_type: Annotated[VehicleType | None, Query(alias="type")] = None,
        min_battery: Annotated[float | None, Query(ge=0, le=100)] = None,
    ) -> list[VehicleOut]:
        known_hub(hub_id)
        # A student sees the rental fleet only, never other students' private vehicles.
        ownership = Ownership.FLEET if who.role is Role.STUDENT else None
        found = core.queries.find_vehicles(
            VehicleFilter(
                hub_id=hub_id,
                state=state,
                vehicle_type=vehicle_type,
                min_battery=min_battery,
                ownership=ownership,
            )
        )
        return [VehicleOut.model_validate(v) for v in found]

    @router.get(
        "/hubs/{hub_id}/spaces", response_model=list[SpaceOut], responses=_ERRORS, tags=["hubs"]
    )
    def list_spaces(
        hub_id: str,
        _who: Annotated[Principal, Depends(operator)],
        status: SpaceStatus | None = None,
    ) -> list[SpaceOut]:
        known_hub(hub_id)
        return [SpaceOut.model_validate(s) for s in core.queries.list_spaces(hub_id, status)]

    @router.get(
        "/hubs/{hub_id}/charging-points",
        response_model=list[ChargingPointOut],
        responses=_ERRORS,
        tags=["hubs"],
    )
    def list_charging_points(
        hub_id: str,
        _who: Annotated[Principal, Depends(operator)],
        status: ChargingPointStatus | None = None,
    ) -> list[ChargingPointOut]:
        known_hub(hub_id)
        points = core.queries.list_charging_points(hub_id, status)
        return [ChargingPointOut.model_validate(p) for p in points]

    @router.get(
        "/vehicles/{vehicle_id}/state-log",
        response_model=list[StateLogOut],
        responses=_ERRORS,
        tags=["vehicles"],
    )
    def state_log(
        vehicle_id: str,
        _who: Annotated[Principal, Depends(operator)],
        limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
    ) -> list[StateLogOut]:
        _raise_if_err(core.queries.get_vehicle(vehicle_id))
        return [
            StateLogOut.model_validate(r) for r in core.queries.get_state_log(vehicle_id, limit)
        ]

    @router.post(
        "/sensor-events", response_model=SensorResultOut, responses=_ERRORS, tags=["simulator"]
    )
    def sensor_event(
        who: Annotated[Principal, Depends(simulator)],
        payload: Annotated[dict[str, Any], Body()],
    ) -> SensorResultOut:
        """The body is read loosely on purpose: core checks it and rejects, logs and announces a
        bad event itself (NFR-10), whatever is wrong with it."""
        raw_time = payload.get("at")
        moment: Any = raw_time
        if isinstance(raw_time, str):
            try:
                moment = datetime.fromisoformat(raw_time)
            except ValueError:
                moment = raw_time
        event = SensorEvent(
            event_id=payload.get("event_id"),  # type: ignore[arg-type]
            source=payload.get("source"),  # type: ignore[arg-type]
            type=payload.get("type"),  # type: ignore[arg-type]
            entity_id=payload.get("entity_id"),  # type: ignore[arg-type]
            at=moment,
            value=payload.get("value"),
        )
        result = core.commands.apply_sensor_event(event, who.actor())
        if isinstance(result, Err):
            raise ApiError(result)
        return SensorResultOut.model_validate(result.value)

    return router


def create_app(
    core: CoreFacade,
    auth: AuthService,
    expose_docs: bool = True,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    """An application with only the core endpoints (handy for tests and for M7's mock server)."""
    app = FastAPI(
        title="Smart E-Mobility Hub - core",
        version="0.1.0",
        docs_url="/docs" if expose_docs else None,
        redoc_url=None,
        lifespan=lifespan,
        openapi_url="/openapi.json" if expose_docs else None,
    )
    app.state.auth = auth  # the sign-in checks of the module routers read it (security.py)
    app.include_router(create_router(core, auth))

    @app.exception_handler(ApiError)
    async def on_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.error)

    @app.exception_handler(RequestValidationError)
    async def on_invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else "invalid request"
        return _error_response(Err(ErrorCode.INVALID_INPUT, message))

    @app.exception_handler(Exception)
    async def on_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected failure in the REST interface")
        return _error_response(Err(ErrorCode.INTERNAL_ERROR, "unexpected failure; try again later"))

    return app
