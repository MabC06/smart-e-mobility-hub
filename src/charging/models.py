from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChargingRequest:
    request_id: str
    vehicle_id: str
    station_id: str
    current_soc: float
    target_soc: float = 100.0
    requested_at: datetime | None = None
    is_emergency: bool = False

    def __post_init__(self) -> None:
        if not (0.0 <= self.current_soc <= 100.0):
            raise ValueError("current_soc must be between 0.0 and 100.0")
        if not (0.0 <= self.target_soc <= 100.0):
            raise ValueError("target_soc must be between 0.0 and 100.0")
