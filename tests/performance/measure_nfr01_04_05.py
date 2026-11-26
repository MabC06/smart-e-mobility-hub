"""Measure NFR-01, NFR-04 and NFR-05 on the DS-STD fixture (M8).

Usage from repository root:
    python tests/performance/measure_nfr01_04_05.py \
        --output docs/testing/evidence/nfr01-04-05-<run-id>.json

What is measured (all sequential, in-process FastAPI TestClient, in-memory SQLite):

* NFR-01: after an accepted write (POST /charging/requests/immediate) the next read
  (GET /charging/sessions) already shows the new request. Target: p95 <= 1 s.
* NFR-04: POST /charging/schedule/optimize for every Hub, each <= 3 s; and one network-wide
  POST /allocation/tasks/plan <= 5 s. The allocation planner needs M2's ReservationDemand
  provider. Without it the endpoint answers 503 and the result is reported as BLOCKED, never
  as PASS. ``--stub-reservation-demand`` registers a stub that returns *empty* demand so the
  planner's own run time can still be timed; the report then says the provider was a stub.
* NFR-05: POST /simulation/runs for each of the five standard scenarios SC-01 to SC-05. Each
  run <= 30 s. Also records that the operational state read before and after the runs is
  identical (NFR-12 evidence) and that repeated runs with one seed give the same output (NFR-13
  evidence, ignoring the simulation id).

Since 2026-11-25 M3's request routes bind the Hub's queue at once (BR-M3-03), so a queue of a
given depth is built through M3's service (``app.state.charging``), which only queues; the
measured operation is still ``POST /charging/schedule/optimize``.

It does not use concurrency or a production database.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402
from measure_nfr02_03 import git_commit, summarize  # noqa: E402

import main as app_main  # noqa: E402
from core.actor import Actor  # noqa: E402
from core.auth import hash_password  # noqa: E402
from core.domain.entities import Vehicle  # noqa: E402
from core.domain.enums import Role  # noqa: E402
from core.providers import (  # noqa: E402
    OpenTrips,
    ProviderPort,
    UpcomingBookings,
)
from core.repository.sql import SqlRepository  # noqa: E402
from core.result import Err, Ok  # noqa: E402
from iot_sim import build_network_spec  # noqa: E402

NFR01_P95_MS = 1000.0
NFR04_CHARGING_MS = 3000.0
NFR04_ALLOCATION_MS = 5000.0
NFR05_SCENARIO_MS = 30000.0
VOLATILE_KEYS = frozenset({"as_of", "executed_at", "taken_at"})


class StubReservationDemand:
    """Empty-demand stand-in for M2's port. Used only with --stub-reservation-demand."""

    def __init__(self, core: Any) -> None:
        self._core = core

    def upcoming_bookings(self, hub_id: str, horizon: Any) -> Any:
        now = self._core.queries.get_config().as_of
        return Ok(UpcomingBookings(as_of=now, horizon_end=now + horizon, bookings=()))

    def open_trips(self, hub_id: str) -> Any:
        return Ok(OpenTrips(as_of=self._core.queries.get_config().as_of, trips=()))


def timed(client: TestClient, method: str, path: str, **kwargs: Any) -> tuple[float, Any]:
    start = time.perf_counter()
    response = client.request(method, path, **kwargs)
    return (time.perf_counter() - start) * 1000, response


def verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def measure_nfr01(
    client: TestClient, headers: dict[str, str], vehicles: list[Vehicle], count: int
) -> dict[str, Any]:
    """Write one request, then read it back at once. Time = from write accepted to read done."""
    candidates = [v for v in vehicles if v.hub_id and v.battery_pct < 100]
    if len(candidates) < count:
        raise RuntimeError(f"only {len(candidates)} eligible vehicles for {count} samples")
    samples: list[float] = []
    statuses: list[int] = []
    visible = 0
    write_errors: list[dict[str, Any]] = []
    for index, vehicle in enumerate(candidates[:count], start=1):
        request_id = f"NFR01-{index:03d}"
        payload = {
            "request_id": request_id,
            "vehicle_id": vehicle.vehicle_id,
            "hub_id": vehicle.hub_id,
            "target_soc": 100.0,
            "queue_if_full": True,
        }
        _, write = timed(
            client, "POST", "/charging/requests/immediate", json=payload, headers=headers
        )
        if write.status_code != 200:
            write_errors.append({"request_id": request_id, "status": write.status_code})
            continue
        # M3 may move the request to another Hub when it binds the queue (BR-M3-02), so the
        # next read is of the Hub the write answered with.
        hub_now = write.json().get("hub_id", vehicle.hub_id)
        elapsed, read = timed(
            client, "GET", "/charging/sessions", params={"hub_id": hub_now}, headers=headers
        )
        samples.append(elapsed)
        statuses.append(read.status_code)
        if read.status_code == 200 and any(row["request_id"] == request_id for row in read.json()):
            visible += 1
    result = summarize("write then GET /charging/sessions", samples, statuses)
    result["writes_attempted"] = count
    result["new_state_visible_in_next_read"] = visible
    result["write_errors"] = write_errors
    result["target_p95_ms"] = NFR01_P95_MS
    result["verdict"] = verdict(
        not write_errors and visible == count and float(result["p95_ms"]) <= NFR01_P95_MS  # type: ignore[arg-type]
    )
    return result


QUEUE_ACTOR = Actor("OP-01", Role.OPERATOR, "charging")  # an account of DS-STD


def fill_queue(env: Env, hub_id: str, depth: int, prefix: str) -> int:
    """Queue ``depth`` requests at one Hub through M3's service, which does not bind them."""
    pool = [v for v in env.vehicles if v.hub_id == hub_id and v.battery_pct < 100][:depth]
    for index, vehicle in enumerate(pool, start=1):
        env.charging.submit_charging_request(
            f"{prefix}-{hub_id}-{index:03d}", vehicle.vehicle_id, hub_id, QUEUE_ACTOR
        )
    return len(pool)


def measure_nfr04_charging(env: Env, queue_depth: int) -> dict[str, Any]:
    """Fill each Hub's charging queue with the same depth, then time optimisation per Hub."""
    client, headers, hub_ids = env.client, env.headers, env.hub_ids
    per_hub: dict[str, Any] = {}
    for hub_id in hub_ids:
        fill_queue(env, hub_id, queue_depth, "NFR04")
    for hub_id in hub_ids:
        queued_before = len(
            client.get("/charging/queue", params={"hub_id": hub_id}, headers=headers).json()
        )
        elapsed, response = timed(
            client,
            "POST",
            "/charging/schedule/optimize",
            params={"hub_id": hub_id},
            headers=headers,
        )
        bound = len(response.json()) if response.status_code == 200 else None
        per_hub[hub_id] = {
            "queued_before": queued_before,
            "bound_by_optimize": bound,
            "status": response.status_code,
            "elapsed_ms": round(elapsed, 3),
            "verdict": verdict(response.status_code == 200 and elapsed <= NFR04_CHARGING_MS),
        }
    worst = max(item["elapsed_ms"] for item in per_hub.values())
    return {
        "operation": "POST /charging/schedule/optimize?hub_id=<each Hub>",
        "queue_depth_per_hub": queue_depth,
        "target_ms_per_hub": NFR04_CHARGING_MS,
        "hubs": per_hub,
        "worst_ms": worst,
        "verdict": verdict(all(item["verdict"] == "PASS" for item in per_hub.values())),
    }


def measure_nfr04_depth_sweep(depths: list[int], stub: bool) -> list[dict[str, Any]]:
    """Time optimisation of ONE Hub (H01) at several queue depths, fresh environment each time."""
    rows: list[dict[str, Any]] = []
    for depth in depths:
        with environment(stub) as env:
            available = fill_queue(env, "H01", depth, "SWEEP")
            queued = len(
                env.client.get(
                    "/charging/queue", params={"hub_id": "H01"}, headers=env.headers
                ).json()
            )
            elapsed, response = timed(
                env.client,
                "POST",
                "/charging/schedule/optimize",
                params={"hub_id": "H01"},
                headers=env.headers,
            )
            rows.append(
                {
                    "requested_depth": depth,
                    "available_vehicles": available,
                    "queued_before": queued,
                    "status": response.status_code,
                    "elapsed_ms": round(elapsed, 3),
                    "ms_per_queued_request": round(elapsed / queued, 1) if queued else None,
                    "within_3s": response.status_code == 200 and elapsed <= NFR04_CHARGING_MS,
                }
            )
    return rows


def measure_nfr04_allocation(
    client: TestClient, headers: dict[str, str], runs: int, provider: str
) -> dict[str, Any]:
    samples: list[float] = []
    statuses: list[int] = []
    bodies: list[str] = []
    for _ in range(runs):
        elapsed, response = timed(
            client, "POST", "/allocation/tasks/plan", json={"slot_id": "slot1"}, headers=headers
        )
        samples.append(elapsed)
        statuses.append(response.status_code)
        bodies.append(response.text[:200])
    result: dict[str, Any] = summarize("POST /allocation/tasks/plan", samples, statuses)
    result["reservation_demand_provider"] = provider
    result["target_ms"] = NFR04_ALLOCATION_MS
    if any(code == 503 for code in statuses):
        result["verdict"] = "BLOCKED"
        result["reason"] = (
            "503 RESOURCE_UNAVAILABLE: no ReservationDemand provider is registered (M2). "
            "The timing is not evidence for NFR-04."
        )
        result["first_body"] = bodies[0]
    else:
        ok = all(code == 200 for code in statuses) and max(samples) <= NFR04_ALLOCATION_MS
        result["verdict"] = verdict(ok)
        if provider != "registered":
            result["note"] = "Timed with an empty-demand stub provider, not M2's implementation."
    return result


def strip_volatile(value: Any) -> Any:
    """Drop wall-clock fields (``as_of``, ``executed_at``, ``taken_at``) before comparing."""
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def differing_paths(a: Any, b: Any, path: str = "") -> list[str]:
    if type(a) is not type(b):
        return [path or "<root>"]
    if isinstance(a, dict):
        found: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                found.append(f"{path}/{key}")
            else:
                found.extend(differing_paths(a[key], b[key], f"{path}/{key}"))
        return found
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}[len {len(a)} vs {len(b)}]"]
        return [
            d
            for i, (x, y) in enumerate(zip(a, b, strict=True))
            for d in differing_paths(x, y, f"{path}[{i}]")
        ]
    return [] if a == b else [path or "<root>"]


def measure_nfr05(
    client: TestClient, headers: dict[str, str], hub_ids: list[str], runs: int
) -> dict[str, Any]:
    def snapshot() -> list[Any]:
        parts = [client.get("/hubs", headers=headers).json()]
        for hub_id in hub_ids[:3]:
            parts.append(client.get(f"/hubs/{hub_id}/vehicles", headers=headers).json())
        return [strip_volatile(part) for part in parts]

    points = client.get(f"/hubs/{hub_ids[0]}/charging-points", headers=headers).json()
    inputs: dict[str, dict[str, Any]] = {
        "SC-01": {"target_hub_ids": hub_ids[:2], "surge_multiplier": 2.0, "duration_minutes": 60},
        "SC-02": {"target_hub_ids": hub_ids[:2], "incoming_return_rate": 12},
        "SC-03": {"target_hub_ids": [], "extra_drained_per_hub": 10},
        "SC-04": {"failed_charging_point_ids": [p["charging_point_id"] for p in points[:2]]},
        "SC-05": {"source_hub_ids": hub_ids[1:3], "destination_hub_ids": hub_ids[:1]},
    }
    before = snapshot()
    samples: list[float] = []
    statuses: list[int] = []
    per_scenario: dict[str, Any] = {}
    run_diff: list[str] = []
    for scenario, fields in inputs.items():
        times: list[float] = []
        reports: list[Any] = []
        for index in range(1, runs + 1):
            sim_id = f"NFR05_{scenario}_{index:03d}".replace("-", "")
            payload = {
                "simulation_id": sim_id,
                "scenario_id": scenario,
                "time_horizon_minutes": 120,
                "time_step_minutes": 15,
                "random_seed": 42,
                **fields,
            }
            elapsed, response = timed(
                client, "POST", "/simulation/runs", json=payload, headers=headers
            )
            samples.append(elapsed)
            times.append(elapsed)
            statuses.append(response.status_code)
            if response.status_code == 200:
                reports.append(
                    json.loads(
                        json.dumps(strip_volatile(response.json()), default=str).replace(
                            sim_id, "<ID>"
                        )
                    )
                )
        diff = [d for other in reports[1:] for d in differing_paths(reports[0], other)]
        run_diff.extend(f"{scenario}{d}" for d in diff)
        per_scenario[scenario] = {
            "runs_ok": len(reports),
            "max_ms": round(max(times), 3),
            "same_output": len(reports) == runs and not diff,
        }
    after = snapshot()
    result: dict[str, Any] = summarize("POST /simulation/runs (SC-01 to SC-05)", samples, statuses)
    result["scenarios"] = per_scenario
    result["target_ms_per_scenario"] = NFR05_SCENARIO_MS
    result["ignored_wall_clock_keys"] = sorted(VOLATILE_KEYS)
    state_diff = differing_paths(before, after)
    result["nfr12_operational_state_unchanged"] = not state_diff
    if state_diff:
        result["nfr12_differences"] = state_diff[:20]
    result["nfr13_same_seed_same_output"] = all(
        item["same_output"] for item in per_scenario.values()
    )
    if run_diff:
        result["nfr13_differences"] = sorted(set(run_diff))[:20]
    ok = (
        all(code == 200 for code in statuses)
        and max(samples) <= NFR05_SCENARIO_MS
        and result["nfr12_operational_state_unchanged"]
    )
    result["verdict"] = "PASS" if ok else "FAIL"
    return result


class Env:
    def __init__(self, client: TestClient, headers: dict[str, str], vehicles: list[Vehicle]):
        self.client = client
        self.headers = headers
        self.vehicles = vehicles
        self.hub_ids: list[str] = []
        self.provider = "not registered"
        self.loaded: Any = None
        self.charging: Any = None


@contextmanager
def environment(stub: bool) -> Iterator[Env]:
    """A fresh app, a fresh in-memory database and a freshly loaded DS-STD (seed 2026)."""
    settings = app_main.Settings.from_env(
        {
            "SECRET_KEY": "nfr-measurement-local-test-secret",
            "LOG_LEVEL": "WARNING",
            "PASSWORD_HASH_ITERATIONS": "1000",
        }
    )
    spec = build_network_spec(seed=2026)
    users = tuple(
        replace(user, password_hash=hash_password("measurement-pass", 1000))
        if user.code == "OPS-01"
        else user
        for user in spec.users
    )
    spec = replace(spec, users=users)

    repository = SqlRepository.open("sqlite://")
    app = app_main.build_app(settings, repository=repository)
    core = app.state.core
    loaded = core.commands.load_network(spec, Actor("SIM", Role.OPERATOR, "iot_sim"))
    if isinstance(loaded, Err):
        repository.close()
        raise RuntimeError(f"DS-STD seed failed: {loaded.code}: {loaded.message}")

    provider = "not registered"
    if core.providers.is_registered(ProviderPort.RESERVATION_DEMAND):
        provider = "registered"
    elif stub:
        core.register_provider(ProviderPort.RESERVATION_DEMAND, StubReservationDemand(core))
        provider = "STUB (empty demand)"

    try:
        with TestClient(app) as client:
            login = client.post(
                "/auth/login", json={"code": "OPS-01", "password": "measurement-pass"}
            )
            if login.status_code != 200:
                raise RuntimeError(f"operator login failed: {login.status_code} {login.text}")
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            vehicles = sorted(repository.query(Vehicle), key=lambda row: row.vehicle_id)
            env = Env(client, headers, vehicles)
            env.hub_ids = sorted(
                row["hub_id"] for row in client.get("/hubs", headers=headers).json()
            )
            env.provider = provider
            env.loaded = loaded.value
            env.charging = app.state.charging
            yield env
    finally:
        repository.close()


def main_run(
    count: int, queue_depth: int, plan_runs: int, sim_runs: int, stub: bool, depths: list[int]
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "run_at_utc": datetime.now(UTC).isoformat(),
        "commit": git_commit(),
        "python": sys.version,
        "environment": "FastAPI TestClient + in-memory SQLite; sequential; no concurrency",
        "isolation": "every measurement below runs on its own freshly loaded DS-STD (seed 2026)",
    }
    with environment(stub) as env:
        report["dataset"] = {
            "seed": 2026,
            "hubs": env.loaded.hubs,
            "vehicles": env.loaded.vehicles,
        }
        report["reservation_demand_provider"] = env.provider
        report["nfr05"] = measure_nfr05(env.client, env.headers, env.hub_ids, sim_runs)
    with environment(stub) as env:
        report["nfr01"] = measure_nfr01(env.client, env.headers, env.vehicles, count)
    with environment(stub) as env:
        report["nfr04_charging"] = measure_nfr04_charging(env, queue_depth)
    report["nfr04_charging_depth_sweep_H01"] = measure_nfr04_depth_sweep(depths, stub)
    with environment(stub) as env:
        report["nfr04_allocation"] = measure_nfr04_allocation(
            env.client, env.headers, plan_runs, env.provider
        )
    return report


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100, help="NFR-01 samples")
    parser.add_argument("--queue-depth", type=int, default=15, help="requests per Hub for NFR-04")
    parser.add_argument(
        "--depths", default="5,10,15,30,50", help="queue depths for the single-Hub sweep"
    )
    parser.add_argument("--plan-runs", type=int, default=5, help="allocation plan repetitions")
    parser.add_argument("--sim-runs", type=int, default=5, help="repetitions per scenario")
    parser.add_argument(
        "--stub-reservation-demand",
        action="store_true",
        help="register an empty-demand stub when M2's provider is missing (clearly labelled)",
    )
    args = parser.parse_args()
    depths = [int(x) for x in args.depths.split(",") if x.strip()]
    report = main_run(
        args.count,
        args.queue_depth,
        args.plan_runs,
        args.sim_runs,
        args.stub_reservation_demand,
        depths,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    def short(block: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in block.items() if k not in {"raw_ms", "hubs"}}

    print("commit:", report["commit"], "| provider:", report["reservation_demand_provider"])
    print("NFR-01 ", short(report["nfr01"]))
    for hub_id, item in report["nfr04_charging"]["hubs"].items():
        print("NFR-04 charging", hub_id, item)
    print("NFR-04 charging overall:", report["nfr04_charging"]["verdict"])
    for row in report["nfr04_charging_depth_sweep_H01"]:
        print("NFR-04 sweep H01", row)
    print("NFR-04 allocation", short(report["nfr04_allocation"]))
    print("NFR-05 ", short(report["nfr05"]))


if __name__ == "__main__":
    cli_main()
