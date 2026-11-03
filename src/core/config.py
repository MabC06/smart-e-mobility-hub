"""Named configuration values of core (CONTRIBUTING 9.3: no magic numbers in code).

Defaults follow docs/requirements/nfr.md, note 3: LOW_BATTERY_THRESHOLD 15 % and the
near-capacity limit 90 % (BR-M5-01). Both can be overridden by environment variables.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

LOW_BATTERY_THRESHOLD_ENV = "LOW_BATTERY_THRESHOLD"
NEAR_CAPACITY_THRESHOLD_ENV = "NEAR_CAPACITY_THRESHOLD"


@dataclass(frozen=True, slots=True)
class CoreConfig:
    """A battery level at or below ``low_battery_threshold`` counts as low (M3, M5)."""

    low_battery_threshold: float = 15.0
    near_capacity_threshold: float = 90.0

    def __post_init__(self) -> None:
        for name, value in (
            ("low_battery_threshold", self.low_battery_threshold),
            ("near_capacity_threshold", self.near_capacity_threshold),
        ):
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be between 0 and 100, got {value}")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "CoreConfig":
        env = os.environ if environ is None else environ
        defaults = cls()
        return cls(
            low_battery_threshold=_read_percent(
                env, LOW_BATTERY_THRESHOLD_ENV, defaults.low_battery_threshold
            ),
            near_capacity_threshold=_read_percent(
                env, NEAR_CAPACITY_THRESHOLD_ENV, defaults.near_capacity_threshold
            ),
        )


def _read_percent(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
