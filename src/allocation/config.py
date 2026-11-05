"""Configuration parameters for Resource Allocation & Vehicle Dispatching (M4).

Follows CONTRIBUTING rule 9.3 (no magic numbers, configurable parameters).
Covers parameters designed in docs/design/architecture/allocation-algorithm-design.md §7.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AllocationConfig:
    """Settings constraining allocation planning, task creation and alternatives lookup."""

    horizon_minutes: int = 30
    safety_stock: int = 3
    parking_buffer: int = 3
    min_dispatch_battery: float = 30.0
    max_tasks_per_hub: int = 3
    max_vehicles_per_task: int = 10
    task_timeout_minutes: int = 60
    staleness_limit_minutes: int = 15
    reservation_lookahead_minutes: int = 30

    # Relative closeness between hubs (lower number = closer).
    # Default symmetric distances between known reference hubs (DS-STD).
    closeness_matrix: dict[tuple[str, str], int] = field(default_factory=dict)

    def get_closeness(self, hub_a: str, hub_b: str) -> int:
        """Return relative distance between two hubs. Default is 99 if unspecified."""
        if hub_a == hub_b:
            return 0
        pair = (hub_a, hub_b)
        if pair in self.closeness_matrix:
            return self.closeness_matrix[pair]
        reverse_pair = (hub_b, hub_a)
        if reverse_pair in self.closeness_matrix:
            return self.closeness_matrix[reverse_pair]
        return 99


def default_config() -> AllocationConfig:
    """Create default configuration with the standard DS-STD topology."""
    distances: dict[tuple[str, str], int] = {
        ("H01", "H02"): 1,
        ("H01", "H03"): 1,
        ("H01", "H04"): 2,
        ("H01", "H05"): 2,
        ("H02", "H03"): 1,
        ("H02", "H05"): 2,
        ("H03", "H08"): 3,
        ("H05", "H08"): 1,
        ("H04", "H06"): 1,
        ("H06", "H07"): 1,
        ("H07", "H08"): 2,
        ("H08", "H09"): 1,
        ("H09", "H10"): 1,
    }
    return AllocationConfig(closeness_matrix=distances)
