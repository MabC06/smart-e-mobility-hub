"""Discrete-event simulation engine for operational what-if scenarios.

Traces: FR-12.3, FR-12.4, FR-12.5, BR-M6-03, UC-M4-03
"""

import math
import random
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List

from .models import HubImpactMetrics, SimulationConfig, SimulationReport
from .snapshot import IsolatedSandboxState


class SimulationEngine:
    """Discrete-Event Engine executing Scenario 1: Demand Surge."""

    def __init__(self, config: SimulationConfig, initial_state: IsolatedSandboxState):
        self.config = config
        self.state: IsolatedSandboxState = deepcopy(initial_state)
        random.seed(config.random_seed)

    def run_demand_surge(self) -> SimulationReport:
        params = self.config.parameters
        hub_metrics: List[HubImpactMetrics] = []
        recommendations: List[Dict[str, Any]] = []

        total_system_requests = 0
        total_system_unmet = 0

        for hub_id, hub in self.state.hubs.items():
            # Eligible vehicles: AVAILABLE and SoC >= 20%
            available_vehicles = [
                v for v in hub.vehicles
                if v.state == "AVAILABLE" and v.battery_pct >= 20.0
            ]
            available_count = len(available_vehicles)

            # Surge generation
            base_demand = max(5, available_count)
            is_target = hub_id in params.target_hub_ids
            multiplier = params.surge_multiplier if is_target else 1.0
            generated_requests = int(math.ceil(base_demand * multiplier))

            unmet = max(0, generated_requests - available_count)
            shortage_rate = (unmet / generated_requests * 100.0) if generated_requests > 0 else 0.0

            total_system_requests += generated_requests
            total_system_unmet += unmet

            hub_metrics.append(HubImpactMetrics(
                hub_id=hub_id,
                total_requests=generated_requests,
                unmet_requests=unmet,
                shortage_rate_pct=round(shortage_rate, 2)
            ))

            # Rule R1: Rebalancing & Dispatch Recommendation
            if unmet > 0:
                needed = unmet
                for other_id, other_hub in self.state.hubs.items():
                    if other_id == hub_id:
                        continue
                    other_avail = len([
                        v for v in other_hub.vehicles
                        if v.state == "AVAILABLE" and v.battery_pct >= 20.0
                    ])
                    # Keep safety buffer of 3 vehicles at origin hub
                    surplus = max(0, other_avail - 3)
                    if surplus > 0:
                        # Batch size bounds 5-20 per dispatch task (UC-M4-03)
                        transfer_qty = min(needed, surplus, 20)
                        if transfer_qty >= 1:
                            recommendations.append({
                                "recommendation_type": "VEHICLE_REDISTRIBUTION",
                                "target_module": "M4",
                                "source_hub_id": other_id,
                                "destination_hub_id": hub_id,
                                "batch_size": transfer_qty,
                                "trigger_reason": f"Shortage of {unmet} vehicles at {hub_id} during peak surge",
                                "aligned_with": "UC-M4-03",
                                "status": "PENDING_OPERATOR_APPROVAL"
                            })
                            needed -= transfer_qty
                    if needed <= 0:
                        break

        baseline_shortage = (
            (total_system_unmet / total_system_requests * 100.0)
            if total_system_requests > 0 else 0.0
        )

        return SimulationReport(
            simulation_id=self.config.simulation_id,
            scenario_id=self.config.scenario_id.value,
            snapshot_id=self.state.snapshot_id,
            executed_at=datetime.now(timezone.utc),
            baseline_shortage_rate_pct=round(baseline_shortage, 2),
            hub_metrics=hub_metrics,
            recommendations=recommendations
        )