"""What-if engine of M6 (FR-12): five standard scenarios on a sandbox copy of Core.

Each scenario counts, per Hub, the requests of its kind (rentals, returns or charging needs)
and how many the Hub cannot serve over the time horizon. It then proposes recommendations and
recomputes the same numbers as if every recommendation were applied, so the report compares
the baseline (do nothing) with the mitigated plan (FR-12.4 to FR-12.6). The engine reads only
the sandbox, so the live state never changes (FR-12.1, NFR-12).

Recommendation types: ``VEHICLE_REDISTRIBUTION`` (an M4 dispatch task, BR-M6-03 batch 5..20),
``ALTERNATIVE_RETURN_HUB`` (send returns to another Hub, M2/M4) and ``CHARGING_SHIFT`` (send
vehicles to charge at another Hub, M3).
"""

import random
from typing import Any

from core.domain.enums import ChargingPointStatus, Ownership, VehicleState
from core.facade import CoreFacade
from core.services.snapshot import OperationalSnapshot
from core.views import HubView, VehicleFilter
from simulation.models import (
    ChargerFailureParams,
    ChargingSurgeParams,
    DemandSurgeParams,
    HubCapacityParams,
    HubImpactMetrics,
    ImbalanceParams,
    ScenarioType,
    SimulationConfig,
    SimulationReport,
)

DONOR_KEEP = 5  # a donor Hub keeps at least this many available vehicles
RENTAL_MIN_SOC = 20.0
WORKING_POINTS = (ChargingPointStatus.AVAILABLE, ChargingPointStatus.CHARGING)


def _rate(rows: list[HubImpactMetrics]) -> float:
    total = sum(r.total_requests for r in rows)
    unmet = sum(r.unmet_requests for r in rows)
    return round(unmet / total * 100.0, 2) if total else 0.0


def _row(hub_id: str, total: int, unmet: int) -> HubImpactMetrics:
    unmet = max(0, min(unmet, total))
    pct = round(unmet / total * 100.0, 2) if total else 0.0
    return HubImpactMetrics(hub_id, total, unmet, pct)


class SimulationEngine:
    def __init__(
        self,
        config: SimulationConfig,
        sandbox: CoreFacade,
        snapshot: OperationalSnapshot,
    ) -> None:
        self.config = config
        self.sandbox = sandbox
        self.snapshot = snapshot
        self.rng = random.Random(config.random_seed)
        self.hubs = {h.hub_id: h for h in sandbox.queries.list_hubs()}

    def run(self) -> SimulationReport:
        """Run the scenario of the config."""
        runners = {
            ScenarioType.DEMAND_SURGE: self.run_demand_surge,
            ScenarioType.HUB_AT_CAPACITY: self._hub_at_capacity,
            ScenarioType.CHARGING_SURGE: self._charging_surge,
            ScenarioType.CHARGER_FAILURE: self._charger_failure,
            ScenarioType.VEHICLE_IMBALANCE: self._vehicle_imbalance,
        }
        return runners[self.config.scenario_id]()

    # ------------------------------------------------------------------ helpers

    def _params[P](self, kind: type[P]) -> P:
        params = self.config.parameters
        if not isinstance(params, kind):
            raise ValueError(f"{self.config.scenario_id.value} needs {kind.__name__}")
        return params

    def _known(self, hub_ids: list[str]) -> list[HubView]:
        unknown = [h for h in hub_ids if h not in self.hubs]
        if unknown:
            raise ValueError(f"unknown Hub {unknown[0]!r}")
        return [self.hubs[h] for h in hub_ids]

    def _available(self, hub_id: str) -> int:
        return len(
            self.sandbox.queries.find_vehicles(
                VehicleFilter(
                    hub_id=hub_id,
                    state=VehicleState.AVAILABLE,
                    min_battery=RENTAL_MIN_SOC,
                    ownership=Ownership.FLEET,
                )
            )
        )

    def _drained(self, hub_id: str, threshold: float) -> int:
        """Fleet vehicles parked at the Hub under the threshold, plus those charging there."""
        vehicles = self.sandbox.queries.find_vehicles(
            VehicleFilter(hub_id=hub_id, ownership=Ownership.FLEET)
        )
        return sum(
            1
            for v in vehicles
            if v.state is VehicleState.CHARGING
            or (v.battery_pct < threshold and v.state is not VehicleState.MAINTENANCE)
        )

    def _report(
        self,
        metric_name: str,
        rows: list[HubImpactMetrics],
        recommendations: list[dict[str, Any]],
        relief: dict[str, int],
    ) -> SimulationReport:
        mitigated = [
            _row(r.hub_id, r.total_requests, r.unmet_requests - relief.get(r.hub_id, 0))
            for r in rows
        ]
        return SimulationReport(
            simulation_id=self.config.simulation_id,
            scenario_id=self.config.scenario_id.value,
            snapshot_id=self.snapshot.snapshot_id,
            executed_at=self.snapshot.taken_at,
            baseline_shortage_rate_pct=_rate(rows),
            hub_metrics=rows,
            recommendations=recommendations,
            metric_name=metric_name,
            mitigated_shortage_rate_pct=_rate(mitigated),
            mitigated_hub_metrics=mitigated,
            random_seed=self.config.random_seed,
        )

    @staticmethod
    def _recommend(
        kind: str, source: str, destination: str, batch: int, reason: str
    ) -> dict[str, Any]:
        return {
            "recommendation_type": kind,
            "source_hub_id": source,
            "destination_hub_id": destination,
            "batch_size": batch,
            "reason": reason,
        }

    # ------------------------------------------------------------------ SC-01

    def run_demand_surge(self) -> SimulationReport:
        params = self._params(DemandSurgeParams)
        rows: list[HubImpactMetrics] = []
        recommendations: list[dict[str, Any]] = []
        relief: dict[str, int] = {}
        for hub_id in params.target_hub_ids:
            if hub_id not in self.hubs:
                continue
            available = self._available(hub_id)
            requests = int(max(10, available * 2) * params.surge_multiplier)
            unmet = max(0, requests - available)
            rows.append(_row(hub_id, requests, unmet))
            if unmet > 0:
                donor = self._find_donor_hub(hub_id)
                if donor:
                    batch = min(20, max(5, unmet))
                    recommendations.append(
                        self._recommend(
                            "VEHICLE_REDISTRIBUTION",
                            donor,
                            hub_id,
                            batch,
                            f"Demand surge shortage at {hub_id}",
                        )
                    )
                    relief[hub_id] = relief.get(hub_id, 0) + batch
        return self._report("Vehicle shortage rate", rows, recommendations, relief)

    def _find_donor_hub(self, target_hub_id: str) -> str | None:
        """A hub with more than 5 available vehicles that is not itself a surge target."""
        params = self._params(DemandSurgeParams)
        targets = set(params.target_hub_ids) | {target_hub_id}
        all_hubs = sorted(self.sandbox.queries.list_hubs(), key=lambda h: h.hub_id)
        candidates = [
            h.hub_id for h in all_hubs if h.hub_id not in targets and h.available_vehicles > 5
        ]
        if not candidates:
            return None
        return self.rng.choice(candidates)

    # ------------------------------------------------------------------ SC-02

    def _hub_at_capacity(self) -> SimulationReport:
        params = self._params(HubCapacityParams)
        targets = self._known(params.target_hub_ids)
        target_ids = {h.hub_id for h in targets}
        spare = {h.hub_id: h.free_spaces for h in self.hubs.values() if h.hub_id not in target_ids}
        rows: list[HubImpactMetrics] = []
        recommendations: list[dict[str, Any]] = []
        relief: dict[str, int] = {}
        for hub in targets:
            returns = params.incoming_return_rate * params.duration_minutes // 10
            unmet = max(0, returns - hub.free_spaces)
            rows.append(_row(hub.hub_id, returns, unmet))
            if unmet == 0 or not spare:
                continue
            neighbour = max(sorted(spare), key=lambda h: spare[h])
            batch = min(unmet, spare[neighbour])
            if batch <= 0:
                continue
            spare[neighbour] -= batch
            relief[hub.hub_id] = batch
            recommendations.append(
                self._recommend(
                    "ALTERNATIVE_RETURN_HUB",
                    hub.hub_id,
                    neighbour,
                    batch,
                    f"{hub.hub_id} has {hub.free_spaces} free spaces for {returns} returns",
                )
            )
        return self._report("Return rejection rate", rows, recommendations, relief)

    # ------------------------------------------------------------------ SC-03 and SC-04

    def _working_points(self, hub_id: str) -> list[str]:
        return [
            p.charging_point_id
            for p in self.sandbox.queries.list_charging_points(hub_id)
            if p.status in WORKING_POINTS
        ]

    def _shift_charging(
        self,
        rows: list[HubImpactMetrics],
        spare: dict[str, int],
        cause: str,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        recommendations: list[dict[str, Any]] = []
        relief: dict[str, int] = {}
        for row in rows:
            if row.unmet_requests == 0:
                continue
            others = {h: n for h, n in spare.items() if h != row.hub_id and n > 0}
            if not others:
                continue
            target = max(sorted(others), key=lambda h: others[h])
            batch = min(row.unmet_requests, others[target])
            spare[target] -= batch
            relief[row.hub_id] = batch
            recommendations.append(
                self._recommend(
                    "CHARGING_SHIFT",
                    row.hub_id,
                    target,
                    batch,
                    f"{cause} at {row.hub_id}: {row.unmet_requests} vehicles cannot charge",
                )
            )
        return recommendations, relief

    def _charging_surge(self) -> SimulationReport:
        params = self._params(ChargingSurgeParams)
        horizon = self.config.time_horizon_minutes
        hubs = self._known(params.target_hub_ids) if params.target_hub_ids else []
        if not hubs:
            hubs = sorted(self.hubs.values(), key=lambda h: h.hub_id)
        rows: list[HubImpactMetrics] = []
        spare: dict[str, int] = {}
        for hub in sorted(self.hubs.values(), key=lambda h: h.hub_id):
            capacity = len(self._working_points(hub.hub_id)) * horizon // params.charge_minutes
            need = self._drained(hub.hub_id, params.soc_threshold)
            if hub in hubs:
                need += params.extra_drained_per_hub
                rows.append(_row(hub.hub_id, need, need - capacity))
            spare[hub.hub_id] = max(0, capacity - need)
        recommendations, relief = self._shift_charging(rows, spare, "Charging surge")
        return self._report("Charging overflow rate", rows, recommendations, relief)

    def _charger_failure(self) -> SimulationReport:
        params = self._params(ChargerFailureParams)
        horizon = self.config.time_horizon_minutes
        failed_by_hub: dict[str, int] = {}
        points = {
            p.charging_point_id: p
            for hub_id in self.hubs
            for p in self.sandbox.queries.list_charging_points(hub_id)
        }
        for point_id in params.failed_charging_point_ids:
            point = points.get(point_id)
            if point is None:
                raise ValueError(f"unknown charging point {point_id!r}")
            failed_by_hub[point.hub_id] = failed_by_hub.get(point.hub_id, 0) + 1
        start = min(params.failure_offset_minutes, horizon)
        downtime = min(params.mttr_minutes, horizon - start)
        rows: list[HubImpactMetrics] = []
        spare: dict[str, int] = {}
        for hub_id in sorted(self.hubs):
            working = len(self._working_points(hub_id))
            failed = min(failed_by_hub.get(hub_id, 0), working)
            point_minutes = working * horizon - failed * downtime
            capacity = point_minutes // params.charge_minutes
            need = self._drained(hub_id, params.soc_threshold)
            if hub_id in failed_by_hub:
                rows.append(_row(hub_id, need, need - capacity))
            spare[hub_id] = max(0, capacity - need)
        recommendations, relief = self._shift_charging(rows, spare, "Charging-point failure")
        return self._report("Charging overflow rate", rows, recommendations, relief)

    # ------------------------------------------------------------------ SC-05

    def _vehicle_imbalance(self) -> SimulationReport:
        params = self._params(ImbalanceParams)
        horizon = self.config.time_horizon_minutes
        sources = {h.hub_id: self._available(h.hub_id) for h in self._known(params.source_hub_ids)}
        rows: list[HubImpactMetrics] = []
        recommendations: list[dict[str, Any]] = []
        relief: dict[str, int] = {}
        arriving = max(0.0, (horizon - params.transit_delay_minutes) / horizon)
        for hub in self._known(params.destination_hub_ids):
            available = self._available(hub.hub_id)
            requests = max(10, available * 2)
            unmet = max(0, requests - available)
            rows.append(_row(hub.hub_id, requests, unmet))
            if unmet == 0:
                continue
            donor = max(sorted(sources), key=lambda h: sources[h])
            batch = min(params.batch_size, unmet, sources[donor] - DONOR_KEEP)
            if batch < 1:
                continue
            sources[donor] -= batch
            relief[hub.hub_id] = int(batch * arriving)
            recommendations.append(
                self._recommend(
                    "VEHICLE_REDISTRIBUTION",
                    donor,
                    hub.hub_id,
                    batch,
                    f"Imbalance: {hub.hub_id} short by {unmet}, {donor} has idle vehicles",
                )
            )
        return self._report("Vehicle shortage rate", rows, recommendations, relief)
