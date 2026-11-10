"""Data models and validation schemas for Module M6 (Simulation & Coordination).

Traces: FR-12.2, FR-12.4, FR-12.5, BR-M6-03
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ScenarioType(str, Enum):
    DEMAND_SURGE = "SCENARIO_01_DEMAND_SURGE"
    HUB_AT_CAPACITY = "SCENARIO_02_HUB_AT_CAPACITY"
    CHARGING_SURGE = "SCENARIO_03_CHARGING_SURGE"
    CHARGER_FAILURE = "SCENARIO_04_CHARGER_FAILURE"
    VEHICLE_IMBALANCE = "SCENARIO_05_VEHICLE_IMBALANCE"


@dataclass
class DemandSurgeParams:
    target_hub_ids: List[str]
    surge_multiplier: float = 1.5
    duration_minutes: int = 60
    destination_distribution: Optional[Dict[str, float]] = None

    def __post_init__(self) -> None:
        if not self.target_hub_ids:
            raise ValueError("target_hub_ids must not be empty")
        if not (1.0 <= self.surge_multiplier <= 5.0):
            raise ValueError("surge_multiplier must be between 1.0 and 5.0")
        if not (15 <= self.duration_minutes <= 360):
            raise ValueError("duration_minutes must be between 15 and 360")
        if self.destination_distribution is not None:
            total = sum(self.destination_distribution.values())
            if not (0.99 <= total <= 1.01):
                raise ValueError("Destination probabilities must sum up to 1.0")


@dataclass
class SimulationConfig:
    simulation_id: str
    scenario_id: ScenarioType
    parameters: DemandSurgeParams
    time_horizon_minutes: int = 120
    time_step_minutes: int = 5
    random_seed: int = 42

    def __post_init__(self) -> None:
        if not (30 <= self.time_horizon_minutes <= 360):
            raise ValueError("time_horizon_minutes must be between 30 and 360")
        if not (1 <= self.time_step_minutes <= 15):
            raise ValueError("time_step_minutes must be between 1 and 15")


@dataclass
class HubImpactMetrics:
    hub_id: str
    total_requests: int
    unmet_requests: int
    shortage_rate_pct: float


@dataclass
class SimulationReport:
    simulation_id: str
    scenario_id: str
    snapshot_id: str
    executed_at: datetime
    baseline_shortage_rate_pct: float
    hub_metrics: List[HubImpactMetrics]
    recommendations: List[Dict[str, Any]]