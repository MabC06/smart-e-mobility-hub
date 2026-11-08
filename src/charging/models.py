from dataclasses import dataclass, field
from datetime import UTC, datetime

LOW_BATTERY_THRESHOLD = 15.0


@dataclass
class ChargingRequest:
    request_id: str
    vehicle_id: str
    station_id: str
    current_soc: float
    target_soc: float = 100.0
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_emergency: bool = False

    def __post_init__(self) -> None:
        if not (0.0 <= self.current_soc <= 100.0):
            raise ValueError("current_soc must be between 0.0 and 100.0")
        if not (0.0 <= self.target_soc <= 100.0):
            raise ValueError("target_soc must be between 0.0 and 100.0")

        if self.current_soc <= LOW_BATTERY_THRESHOLD:
            self.is_emergency = True
