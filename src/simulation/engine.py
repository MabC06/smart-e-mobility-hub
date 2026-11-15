import random
from typing import Any

from core.facade import CoreFacade
from core.views import VehicleFilter, VehicleState
from simulation.models import (
    HubImpactMetrics,
    SimulationConfig,
    SimulationReport,
)


class SimulationEngine:
    def __init__(
        self,
        config: SimulationConfig,
        sandbox: CoreFacade,
        snapshot: Any,
    ) -> None:
        self.config = config
        self.sandbox = sandbox
        self.snapshot = snapshot
        self.rng = random.Random(config.random_seed)

    def run_demand_surge(self) -> SimulationReport:
        target_hubs = self.config.parameters.target_hub_ids
        multiplier = self.config.parameters.surge_multiplier

        hub_metrics: list[HubImpactMetrics] = []
        recommendations: list[dict[str, Any]] = []

        total_shortage = 0
        total_requests_all = 0

        hubs = self.sandbox.queries.list_hubs()
        hubs_map = {h.hub_id: h for h in hubs}

        for hub_id in target_hubs:
            hub = hubs_map.get(hub_id)
            if not hub:
                continue

            available_vehicles_list = self.sandbox.queries.find_vehicles(
                VehicleFilter(
                    hub_id=hub_id,
                    state=VehicleState.AVAILABLE,
                    min_battery=20.0,
                )
            )
            available_vehicles = len(available_vehicles_list)

            base_requests = max(10, available_vehicles * 2)
            simulated_requests = int(base_requests * multiplier)
            unmet = max(0, simulated_requests - available_vehicles)

            shortage_pct = (unmet / simulated_requests * 100.0) if simulated_requests > 0 else 0.0

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
                donor_hub_id = self._find_donor_hub(hub_id)
                if donor_hub_id:
                    batch_size = min(20, max(5, unmet))
                    recommendations.append(
                        {
                            "recommendation_type": "VEHICLE_REDISTRIBUTION",
                            "source_hub_id": donor_hub_id,
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

        return SimulationReport(
            simulation_id=self.config.simulation_id,
            scenario_id=self.config.scenario_id.value,
            snapshot_id=getattr(self.snapshot, "snapshot_id", "UNKNOWN"),
            executed_at=getattr(self.snapshot, "taken_at", None),
            baseline_shortage_rate_pct=baseline_pct,
            hub_metrics=hub_metrics,
            recommendations=recommendations,
        )

    def _find_donor_hub(self, target_hub_id: str) -> str | None:
        all_hubs = sorted(self.sandbox.queries.list_hubs(), key=lambda h: h.hub_id)
        candidates = [
            h.hub_id for h in all_hubs if h.hub_id != target_hub_id and h.available_vehicles > 5
        ]
        if not candidates:
            return None
        return self.rng.choice(candidates)
