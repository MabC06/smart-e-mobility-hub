import random

from simulation.models import (
    HubImpactMetrics,
    SimulationConfig,
    SimulationReport,
)


class SimulationEngine:
    def __init__(self, config: SimulationConfig, sandbox_core: object) -> None:
        self.config = config
        self.sandbox = sandbox_core
        self.rng = random.Random(config.random_seed)

    def run_demand_surge(self) -> SimulationReport:
        target_hubs = self.config.parameters.target_hub_ids
        multiplier = self.config.parameters.surge_multiplier

        hub_metrics: list[HubImpactMetrics] = []
        recommendations: list[dict[str, object]] = []

        total_shortage = 0
        total_requests_all = 0

        # Lấy danh sách hub từ sandbox core queries
        hubs = self.sandbox.queries.list_hubs()
        hubs_map = {h.id: h for h in hubs}

        for hub_id in target_hubs:
            hub = hubs_map.get(hub_id)
            if not hub:
                continue

            # Lấy xe của hub thông qua find_vehicles
            hub_vehicles = self.sandbox.queries.find_vehicles(hub_id=hub_id)
            available_vehicles = len(
                [
                    v
                    for v in hub_vehicles
                    if getattr(v, "state", "") == "AVAILABLE" and getattr(v, "soc", 0.0) >= 0.2
                ]
            )

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
                donor_hub_id = self._find_donor_hub(hub_id, hubs_map)
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

        # Lấy report time từ snapshot.taken_at chuẩn (không dùng datetime.now fallback)
        snapshot_meta = self.sandbox.snapshots.get_metadata()
        report_time = snapshot_meta.taken_at

        return SimulationReport(
            simulation_id=self.config.simulation_id,
            scenario_id=self.config.scenario_id.value,
            snapshot_id=snapshot_meta.snapshot_id,
            executed_at=report_time,
            baseline_shortage_rate_pct=baseline_pct,
            hub_metrics=hub_metrics,
            recommendations=recommendations,
        )

    def _find_donor_hub(self, target_hub_id: str, hubs_map: dict[str, object]) -> str | None:
        candidates = []
        for hid in hubs_map:
            if hid != target_hub_id:
                vehs = self.sandbox.queries.find_vehicles(hub_id=hid)
                if len(vehs) > 5:
                    candidates.append(hid)
        if not candidates:
            return None
        return self.rng.choice(candidates)
