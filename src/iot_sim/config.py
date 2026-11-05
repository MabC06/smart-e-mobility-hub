"""Configuration for the deterministic IoT simulator (M8)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimulatorConfig:
    """Inputs that control a reproducible simulation run."""

    seed: int = 0
    battery_drain_min_pct: float = 0.5
    battery_drain_max_pct: float = 2.0
    private_arrival_count: int = 5

    def __post_init__(self) -> None:
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if not 0 <= self.battery_drain_min_pct <= self.battery_drain_max_pct:
            raise ValueError("battery drain bounds must satisfy 0 <= min <= max")
        if self.private_arrival_count < 0:
            raise ValueError("private_arrival_count must be non-negative")
