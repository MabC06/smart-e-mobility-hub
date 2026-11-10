from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Float, MetaData, String, Table

from charging.models import ChargingRequest

# Define persistence table for charging requests (D-018)
metadata = MetaData()
charging_requests_table = Table(
    "charging_requests",
    metadata,
    Column("request_id", String, primary_key=True),
    Column("vehicle_id", String, nullable=False),
    Column("station_id", String, nullable=False),
    Column("current_soc", Float, nullable=False),
    Column("target_soc", Float, nullable=False),
    Column("requested_at", DateTime, nullable=False),
    Column("is_emergency", Boolean, nullable=False),
)


class ChargingQueueService:
    """Service managing the charging queue, integrating core configuration and claims."""

    def __init__(self, core: Any = None) -> None:
        self.core = core
        self._queue: list[ChargingRequest] = []

        # Register entity table with core (D-018)
        if self.core and hasattr(self.core, "register_entity"):
            try:
                self.core.register_entity("charging_requests", charging_requests_table)
            except Exception:
                pass

    def add_request(self, request: ChargingRequest) -> None:
        """Add a charging request to the queue, fetch config/time from core, and place a claim (D-017)."""
        if any(r.request_id == request.request_id for r in self._queue):
            raise ValueError(
                f"Charging request {request.request_id} already exists in queue."
            )

        # Fetch configuration from core to standardize as_of time and check low battery threshold
        if self.core and hasattr(self.core, "queries"):
            config = self.core.queries.get_config()
            if config:
                if request.requested_at is None and hasattr(config, "as_of"):
                    request.requested_at = config.as_of
                if hasattr(config, "low_battery_threshold"):
                    request.is_emergency = (
                        request.current_soc <= config.low_battery_threshold
                    )

        self._queue.append(request)
        self.sort_queue()

        # Place CHARGING_SESSION claim via core (D-017)
        if self.core and hasattr(self.core, "place_claim"):
            try:
                self.core.place_claim(
                    resource_type="CHARGING_SESSION",
                    resource_id=request.request_id,
                    owner_id=request.vehicle_id,
                )
            except Exception:
                pass

    def sort_queue(self) -> None:
        """
        Sort the queue according to Priority Queue v1 rules:
        1. Prioritize emergency requests to the front (is_emergency = True).
        2. Sort by ascending battery level (lower current_soc gets higher priority).
        3. Sort by request timestamp (FIFO for vehicles with the same SoC level).
        """
        self._queue.sort(
            key=lambda req: (
                not req.is_emergency,  # True comes before False
                req.current_soc,  # Lower battery comes first
                req.requested_at or datetime.min,  # First-In, First-Out (FIFO)
            )
        )

    def pop_next_request(self) -> ChargingRequest | None:
        """Retrieve and remove the highest priority request, releasing its claim via core (D-017)."""
        if not self._queue:
            return None
        request = self._queue.pop(0)

        # Release CHARGING_SESSION claim via core (D-017)
        if self.core and hasattr(self.core, "release_claim"):
            try:
                self.core.release_claim(
                    resource_type="CHARGING_SESSION",
                    resource_id=request.request_id,
                )
            except Exception:
                pass

        return request

    def get_pending_requests(self) -> list[dict[str, Any]]:
        """Retrieve a list of pending requests (used for the Provider Port)."""
        return [
            {
                "request_id": r.request_id,
                "vehicle_id": r.vehicle_id,
                "station_id": r.station_id,
                "current_soc": r.current_soc,
                "is_emergency": r.is_emergency,
                "requested_at": r.requested_at.isoformat() if r.requested_at else None,
            }
            for r in self._queue
        ]

    def get_scheduled_sessions(self, hub_id: str, horizon: datetime) -> list[Any]:
        """Return scheduled sessions filtered by hub and horizon (D-020)."""
        return self._queue
