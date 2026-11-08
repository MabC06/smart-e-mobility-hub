from typing import Any

from src.charging.models import ChargingRequest


class ChargingQueueService:
    def __init__(self) -> None:
        self._queue: list[ChargingRequest] = []

    def add_request(self, request: ChargingRequest) -> None:
        """Add a charging request to the queue."""
        if any(r.request_id == request.request_id for r in self._queue):
            raise ValueError(
                f"Charging request {request.request_id} already exists in queue."
            )

        self._queue.append(request)
        self.sort_queue()

    def sort_queue(self) -> None:
        """
        Sort the queue according to Priority Queue v1 rules:
        1. Prioritize emergency requests to the front (is_emergency = True).
        2. Sort by ascending battery level (lower current_soc gets higher priority).
        3. Sort by request timestamp (FIFO for vehicles with the same SoC level).
        """
        self._queue.sort(
            key=lambda req: (
                not req.is_emergency,  # False comes after True
                req.current_soc,  # Lower battery comes first
                req.requested_at,  # First-In, First-Out (FIFO)
            )
        )

    def pop_next_request(self) -> ChargingRequest | None:
        """Retrieve and remove the highest priority request from the queue."""
        if not self._queue:
            return None
        return self._queue.pop(0)

    def get_pending_requests(self) -> list[dict[str, Any]]:
        """Retrieve a list of pending requests (used for the Provider Port)."""
        return [
            {
                "request_id": r.request_id,
                "vehicle_id": r.vehicle_id,
                "station_id": r.station_id,
                "current_soc": r.current_soc,
                "is_emergency": r.is_emergency,
                "requested_at": r.requested_at.isoformat(),
            }
            for r in self._queue
        ]
