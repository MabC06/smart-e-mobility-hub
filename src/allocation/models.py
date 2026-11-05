"""Data models for Resource Allocation & Vehicle Dispatching (M4).

Implements the DispatchTask entity (BR-M4-08, D-018) that joins core's transactions.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from sqlalchemy import Column, ForeignKey, Integer, String, Table

from core.domain.enums import VehicleType
from core.repository.schema import TableSpec, metadata


class DispatchTaskStatus(StrEnum):
    """Life cycle states of a DispatchTask (BR-M4-08)."""

    RECOMMENDED = "RECOMMENDED"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(slots=True)
class DispatchTask:
    """An allocation redistribution task moving vehicles from a surplus hub to a deficit hub.

    Complies with core entity contract (ID_FIELD, VERSIONED) to join transactions (D-018).
    """

    ID_FIELD: ClassVar[str] = "task_id"
    VERSIONED: ClassVar[bool] = True

    task_id: str
    source_hub_id: str
    target_hub_id: str
    vehicle_type: VehicleType
    quantity: int
    vehicle_ids: str = ""  # Comma-separated list of assigned vehicle IDs
    status: DispatchTaskStatus = DispatchTaskStatus.RECOMMENDED
    priority: int = 1
    reason: str = ""
    version: int = 1

    @property
    def assigned_vehicles(self) -> list[str]:
        """Parsed list of assigned vehicle IDs."""
        if not self.vehicle_ids.strip():
            return []
        return [v.strip() for v in self.vehicle_ids.split(",") if v.strip()]

    def is_terminal(self) -> bool:
        """Return True if task is in a terminal state."""
        return self.status in {
            DispatchTaskStatus.COMPLETED,
            DispatchTaskStatus.CANCELLED,
            DispatchTaskStatus.REJECTED,
            DispatchTaskStatus.FAILED,
        }


dispatch_tasks = Table(
    "m4_dispatch_tasks",
    metadata,
    Column("task_id", String, primary_key=True),
    Column("source_hub_id", String, ForeignKey("hubs.hub_id"), nullable=False),
    Column("target_hub_id", String, ForeignKey("hubs.hub_id"), nullable=False),
    Column("vehicle_type", String, nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("vehicle_ids", String, nullable=False, default=""),
    Column("status", String, nullable=False),
    Column("priority", Integer, nullable=False, default=1),
    Column("reason", String, nullable=False, default=""),
    Column("version", Integer, nullable=False, default=1),
)

DISPATCH_TASK_SPEC = TableSpec(
    DispatchTask,
    dispatch_tasks,
    "task_id",
    {"status": DispatchTaskStatus, "vehicle_type": VehicleType},
    True,
)
