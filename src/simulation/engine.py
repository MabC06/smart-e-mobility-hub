"""Discrete-event simulation engine for Module M6.

Traces: FR-12.4, NFR-13, UC-M4-03, D-005
"""

import random
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from simulation.models import (
    HubImpactMetrics,
    SimulationConfig,
    SimulationReport,
)
from simulation.snapshot import IsolatedSandboxState, SimulatedHub


class SimulationEngine:
    def __init__(
        self, config: SimulationConfig, initial_state: IsolatedSandboxState
    ):
        self.config = config
        self.state: IsolatedSandboxState = deepcopy(initial_state)
        # M6-5: Isolated local RNG for deterministic execution (NFR-13)
        self.rng = random.Random(config.random_seed)

    def run_demand_surge(self) -> SimulationReport:
        target_hubs = self.config.parameters.target_hub_ids
        multiplier = self.config.parameters.surge_multiplier

        hub_metrics: List[HubImpactMetrics] = []
        recommendations: List[Dict[str, Any]] = []

        total_shortage = 0
        total_requests_all = 0

        for hub_id in target_hubs:
            hub = self.state.hubs.get(hub_id)
            if not hub:
                continue

            available_vehicles = len(
                [v for v in hub.vehicles if v.state == "AVAILABLE" and v.soc >= 0.2]
            )

            base_requests = max(10, available_vehicles * 2)
            simulated_requests = int(base_requests * multiplier)
            unmet = max(0, simulated_requests - available_vehicles)

            shortage_pct = (
                (unmet / simulated_requests * 100.0)
                if simulated_requests > 0
                else 0.0
            )

            total_shortage += unmet
            total_requests_all += simulated_requests

            hub_metrics.append(
                HubImpactMetrics(
                    hub_id=hub_id,
                    total_requests=simulated_requests,
                    unmet_requests=unmet,
                    shortage_rate_pct=round(shortage_pct, 2),
                )
            )

            if unmet > 0:
                donor_hub = self._find_donor_hub(hub_id)
                if donor_hub:
                    batch_size = min(20, max(5, unmet))
                    recommendations.append(
                        {
                            "recommendation_type": "VEHICLE_REDISTRIBUTION",
                            "source_hub_id": donor_hub.hub_id,
                            "destination_hub_id": hub_id,
                            "batch_size": batch_size,
                            "reason": f"Demand surge shortage at {hub_id}",
                        }
                    )

        baseline_pct = (
            round((total_shortage / total_requests_all * 100.0), 2)
            if total_requests_all > 0
            else 0.0
        )

        # M6-6: Use snapshot taken_at for report time (D-005, NFR-13)
        report_time = self.state.taken_at or datetime.now(timezone.utc)

        return SimulationReport(
            simulation_id=self.config.simulation_id,
            scenario_id=self.config.scenario_id.value,
            snapshot_id=self.state.snapshot_id,
            executed_at=report_time,
            baseline_shortage_rate_pct=baseline_pct,
            hub_metrics=hub_metrics,
            recommendations=recommendations,
        )

    def _find_donor_hub(self, target_hub_id: str) -> Optional[SimulatedHub]:
        candidates = [
            h
            for hid, h in self.state.hubs.items()
            if hid != target_hub_id and len(h.vehicles) > 5
        ]
        if not candidates:
            return None
        return self.rng.choice(candidates)