from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.api.security import require_operator
from simulation.models import (
    DemandSurgeParams,
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
    scenario_id: str = Field(..., examples=["DEMAND_SURGE"])
    target_hub_ids: list[str] = Field(default_factory=list, examples=[["H01"]])
    surge_multiplier: float = Field(default=2.0, ge=1.0)
    duration_minutes: int = Field(default=60, gt=0)
    time_horizon_minutes: int = Field(default=120, gt=0)
    time_step_minutes: int = Field(default=15, gt=0)
    random_seed: int = Field(default=42)


@router.post("/runs", response_model=dict, status_code=status.HTTP_200_OK)
def run_simulation_endpoint(
    req: RunSimulationRequest,
    service: SimulationService = Depends(get_simulation_service),  # noqa: B008
    _operator: dict = Depends(require_operator),  # noqa: B008
) -> dict:
    valid_scenarios = [
        ScenarioType.DEMAND_SURGE.value,
        "SCENARIO_01_DEMAND_SURGE",
        "SC-01",
        "DEMAND_SURGE",
    ]

    if req.scenario_id not in valid_scenarios:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_SCENARIO",
                "message": (
                    f"Scenario '{req.scenario_id}' is not supported. "
                    "Only DEMAND_SURGE (SC-01) is implemented."
                ),
            },
        )

    try:
        config = SimulationConfig(
            simulation_id=req.simulation_id,
            scenario_id=ScenarioType.DEMAND_SURGE,
            parameters=DemandSurgeParams(
                target_hub_ids=req.target_hub_ids,
                surge_multiplier=req.surge_multiplier,
                duration_minutes=req.duration_minutes,
            ),
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
