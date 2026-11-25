from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.api.security import require_operator
from simulation.models import (
    SCENARIO_ALIASES,
    ChargerFailureParams,
    ChargingSurgeParams,
    DemandSurgeParams,
    HubCapacityParams,
    ImbalanceParams,
    ScenarioParams,
    ScenarioType,
    SimulationConfig,
)
from simulation.service import SimulationService

router = APIRouter(prefix="/simulation", tags=["simulation"])

_simulation_service: SimulationService | None = None


def set_simulation_service(service: SimulationService) -> None:
    global _simulation_service
    _simulation_service = service


def get_simulation_service() -> SimulationService:
    if _simulation_service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "SERVICE_NOT_INITIALIZED",
                "message": "SimulationService is not installed.",
            },
        )
    return _simulation_service


class RunSimulationRequest(BaseModel):
    simulation_id: str = Field(..., examples=["SIM_RUN_001"])
    scenario_id: str = Field(..., examples=["SC-01"])
    target_hub_ids: list[str] = Field(default_factory=list, examples=[["H01"]])
    # SC-01
    surge_multiplier: float = Field(default=2.0, ge=1.0)
    duration_minutes: int = Field(default=60, gt=0)
    # SC-02
    incoming_return_rate: int = Field(default=6, gt=0)
    # SC-03 and SC-04
    soc_threshold: float = Field(default=20.0, gt=0)
    extra_drained_per_hub: int = Field(default=0, ge=0)
    charge_minutes: int = Field(default=60, gt=0)
    failed_charging_point_ids: list[str] = Field(default_factory=list)
    failure_offset_minutes: int = Field(default=0, ge=0)
    mttr_minutes: int = Field(default=120, gt=0)
    # SC-05
    source_hub_ids: list[str] = Field(default_factory=list)
    destination_hub_ids: list[str] = Field(default_factory=list)
    batch_size: int = Field(default=10, gt=0)
    transit_delay_minutes: int = Field(default=15, ge=0)
    # every scenario
    time_horizon_minutes: int = Field(default=120, gt=0)
    time_step_minutes: int = Field(default=15, gt=0)
    random_seed: int = Field(default=42)


def _parameters(scenario: ScenarioType, req: RunSimulationRequest) -> ScenarioParams:
    """The parameter object of one scenario; its checks raise ValueError (400)."""
    if scenario is ScenarioType.DEMAND_SURGE:
        return DemandSurgeParams(req.target_hub_ids, req.surge_multiplier, req.duration_minutes)
    if scenario is ScenarioType.HUB_AT_CAPACITY:
        return HubCapacityParams(req.target_hub_ids, req.incoming_return_rate, req.duration_minutes)
    if scenario is ScenarioType.CHARGING_SURGE:
        return ChargingSurgeParams(
            req.target_hub_ids, req.soc_threshold, req.extra_drained_per_hub, req.charge_minutes
        )
    if scenario is ScenarioType.CHARGER_FAILURE:
        return ChargerFailureParams(
            req.failed_charging_point_ids,
            req.failure_offset_minutes,
            req.mttr_minutes,
            req.soc_threshold,
            req.charge_minutes,
        )
    return ImbalanceParams(
        req.source_hub_ids, req.destination_hub_ids, req.batch_size, req.transit_delay_minutes
    )


@router.post("/runs", response_model=dict, status_code=status.HTTP_200_OK)
def run_simulation_endpoint(
    req: RunSimulationRequest,
    service: SimulationService = Depends(get_simulation_service),  # noqa: B008
    _operator: dict = Depends(require_operator),  # noqa: B008
) -> dict:
    """Run one of the five standard scenarios (SC-01 to SC-05) on a sandbox copy (FR-12)."""
    scenario = SCENARIO_ALIASES.get(req.scenario_id)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_SCENARIO",
                "message": f"Scenario '{req.scenario_id}' is not one of SC-01 to SC-05.",
            },
        )

    try:
        config = SimulationConfig(
            simulation_id=req.simulation_id,
            scenario_id=scenario,
            parameters=_parameters(scenario, req),
            time_horizon_minutes=req.time_horizon_minutes,
            time_step_minutes=req.time_step_minutes,
            random_seed=req.random_seed,
        )
        report = service.run_simulation(config)
        return report.to_dict() if hasattr(report, "to_dict") else report.__dict__

    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_INPUT", "message": str(err)},
        ) from err
