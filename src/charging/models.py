from dataclasses import dataclass, field
from datetime import datetime, timezone

# Business Rule: Low battery emergency threshold (BR-M3-01)
LOW_BATTERY_THRESHOLD: float = 15.0


@dataclass
class ChargingRequest:
    request_id: str
    vehicle_id: str
    station_id: str
    current_soc: float  # State of Charge (0.0 to 100.0)
    target_soc: float = 100.0
    # Use lambda with datetime.now(timezone.utc) instead of utcnow() to avoid deprecation warnings
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_emergency: bool = False

    def __post_init__(self) -> None:
        if not (0.0 <= self.current_soc <= 100.0):
            raise ValueError(
                f"Invalid current_soc: {self.current_soc}. Must be between 0.0 and 100.0."
            )
        if not (0.0 <= self.target_soc <= 100.0):
            raise ValueError(
                f"Invalid target_soc: {self.target_soc}. Must be between 0.0 and 100.0."
            )

        if self.current_soc <= LOW_BATTERY_THRESHOLD:
            self.is_emergency = True
