from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ScenarioType(StrEnum):
    DEMAND_SURGE = "SCENARIO_01_DEMAND_SURGE"
    HUB_AT_CAPACITY = "SCENARIO_02_HUB_AT_CAPACITY"
    CHARGING_SURGE = "SCENARIO_03_CHARGING_SURGE"
    CHARGER_FAILURE = "SCENARIO_04_CHARGER_FAILURE"
    VEHICLE_IMBALANCE = "SCENARIO_05_VEHICLE_IMBALANCE"


SCENARIO_ALIASES = {
    "SC-01": ScenarioType.DEMAND_SURGE,
    "DEMAND_SURGE": ScenarioType.DEMAND_SURGE,
    "SC-02": ScenarioType.HUB_AT_CAPACITY,
    "HUB_AT_CAPACITY": ScenarioType.HUB_AT_CAPACITY,
    "SC-03": ScenarioType.CHARGING_SURGE,
    "CHARGING_SURGE": ScenarioType.CHARGING_SURGE,
    "SC-04": ScenarioType.CHARGER_FAILURE,
    "CHARGER_FAILURE": ScenarioType.CHARGER_FAILURE,
    "SC-05": ScenarioType.VEHICLE_IMBALANCE,
    "VEHICLE_IMBALANCE": ScenarioType.VEHICLE_IMBALANCE,
    **{scenario.value: scenario for scenario in ScenarioType},
}


@dataclass
class DemandSurgeParams:
    target_hub_ids: list[str]
    surge_multiplier: float = 1.5
    duration_minutes: int = 60
    destination_distribution: dict[str, float] | None = None

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
class HubCapacityParams:
    """SC-02: returns arrive at the target Hubs faster than they have free spaces."""

    target_hub_ids: list[str]
    incoming_return_rate: int = 6  # returns per 10 minutes at each target Hub
    duration_minutes: int = 60

    def __post_init__(self) -> None:
        if not self.target_hub_ids:
            raise ValueError("target_hub_ids must not be empty")
        if not (1 <= self.incoming_return_rate <= 60):
            raise ValueError("incoming_return_rate must be between 1 and 60 per 10 minutes")
        if not (15 <= self.duration_minutes <= 360):
            raise ValueError("duration_minutes must be between 15 and 360")


@dataclass
class ChargingSurgeParams:
    """SC-03: many fleet vehicles fall under the charging threshold at once."""

    target_hub_ids: list[str] = field(default_factory=list)  # empty: every Hub
    soc_threshold: float = 20.0
    extra_drained_per_hub: int = 0
    charge_minutes: int = 60  # one charging point serves one vehicle in this time

    def __post_init__(self) -> None:
        if not (1.0 <= self.soc_threshold <= 100.0):
            raise ValueError("soc_threshold must be between 1 and 100")
        if not (0 <= self.extra_drained_per_hub <= 100):
            raise ValueError("extra_drained_per_hub must be between 0 and 100")
        if not (15 <= self.charge_minutes <= 240):
            raise ValueError("charge_minutes must be between 15 and 240")


@dataclass
class ChargerFailureParams:
    """SC-04: some charging points stop for a time (mean time to repair)."""

    failed_charging_point_ids: list[str]
    failure_offset_minutes: int = 0
    mttr_minutes: int = 120
    soc_threshold: float = 20.0
    charge_minutes: int = 60

    def __post_init__(self) -> None:
        if not self.failed_charging_point_ids:
            raise ValueError("failed_charging_point_ids must not be empty")
        if not (0 <= self.failure_offset_minutes <= 360):
            raise ValueError("failure_offset_minutes must be between 0 and 360")
        if not (15 <= self.mttr_minutes <= 720):
            raise ValueError("mttr_minutes must be between 15 and 720")
        if not (15 <= self.charge_minutes <= 240):
            raise ValueError("charge_minutes must be between 15 and 240")


@dataclass
class ImbalanceParams:
    """SC-05: idle vehicles at some Hubs while others run short."""

    source_hub_ids: list[str]
    destination_hub_ids: list[str]
    batch_size: int = 10
    transit_delay_minutes: int = 15

    def __post_init__(self) -> None:
        if not self.source_hub_ids or not self.destination_hub_ids:
            raise ValueError("source_hub_ids and destination_hub_ids must not be empty")
        if set(self.source_hub_ids) & set(self.destination_hub_ids):
            raise ValueError("a Hub cannot be both a source and a destination")
        if not (5 <= self.batch_size <= 20):
            raise ValueError("batch_size must be between 5 and 20 (UC-M4-03)")
        if not (0 <= self.transit_delay_minutes <= 120):
            raise ValueError("transit_delay_minutes must be between 0 and 120")


ScenarioParams = (
    DemandSurgeParams
    | HubCapacityParams
    | ChargingSurgeParams
    | ChargerFailureParams
    | ImbalanceParams
)


@dataclass
class SimulationConfig:
    simulation_id: str
    scenario_id: ScenarioType
    parameters: ScenarioParams
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
    """Result of one run. ``baseline_*`` is doing nothing; ``mitigated_*`` applies every
    recommendation (FR-12.6). ``metric_name`` says what a request and an unmet request are.
    ``random_seed`` is the seed of the run, so a saved report can be run again (NFR-13)."""

    simulation_id: str
    scenario_id: str
    snapshot_id: str
    executed_at: datetime
    baseline_shortage_rate_pct: float
    hub_metrics: list[HubImpactMetrics]
    recommendations: list[dict[str, object]]
    metric_name: str = "Vehicle shortage rate"
    mitigated_shortage_rate_pct: float = 0.0
    mitigated_hub_metrics: list[HubImpactMetrics] = field(default_factory=list)
    random_seed: int = 42
