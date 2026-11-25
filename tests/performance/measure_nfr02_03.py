"""Run D-024 sequential NFR-02/03 measurements against the DS-STD fixture.

Usage from repository root:
python tests/performance/measure_nfr02_03.py --output docs/testing/evidence/nfr02-03-<run-id>.json

This creates an isolated in-memory SQLite app, loads DS-STD, then executes sequential
in-process HTTP requests. It does not use concurrency or a production database.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

import main as app_main  # noqa: E402
from core.actor import Actor  # noqa: E402
from core.auth import hash_password  # noqa: E402
from core.domain.entities import Vehicle  # noqa: E402
from core.domain.enums import Role  # noqa: E402
from core.repository.sql import SqlRepository  # noqa: E402
from core.result import Err  # noqa: E402
from iot_sim import build_network_spec  # noqa: E402


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no timing samples")
    index = max(0, min(len(ordered) - 1, int((p / 100) * len(ordered) + 0.999999) - 1))
    return ordered[index]


def summarize(name: str, samples: list[float], statuses: list[int]) -> dict[str, object]:
    return {
        "name": name,
        "samples": len(samples),
        "success_count": sum(200 <= code < 300 for code in statuses),
        "status_codes": {str(code): statuses.count(code) for code in sorted(set(statuses))},
        "p50_ms": round(percentile(samples, 50), 3),
        "p95_ms": round(percentile(samples, 95), 3),
        "max_ms": round(max(samples), 3),
        "raw_ms": [round(value, 3) for value in samples],
    }


def timed_requests(
    client: TestClient, method: str, path: str, headers: dict[str, str], count: int = 100
):
    samples: list[float] = []
    statuses: list[int] = []
    for _ in range(count):
        start = time.perf_counter()
        response = client.request(method, path, headers=headers)
        samples.append((time.perf_counter() - start) * 1000)
        statuses.append(response.status_code)
    return samples, statuses


def main_run(output: Path, count: int = 100) -> dict[str, object]:
    secret = "nfr-measurement-local-test-secret"
    settings = app_main.Settings.from_env(
        {
            "SECRET_KEY": secret,
            "LOG_LEVEL": "WARNING",
            "PASSWORD_HASH_ITERATIONS": "1000",
        }
    )
    spec = build_network_spec(seed=2026)
    users = tuple(
        replace(user, password_hash=hash_password("measurement-pass", 1000))
        if user.code in {"STU-0001", "OPS-01"}
        else user
        for user in spec.users
    )
    spec = replace(spec, users=users)

    repository = SqlRepository.open("sqlite://")
    app = app_main.build_app(settings, repository=repository)
    loaded = app.state.core.commands.load_network(spec, Actor("SIM", Role.OPERATOR, "iot_sim"))
    if isinstance(loaded, Err):
        repository.close()
        raise RuntimeError(f"DS-STD seed failed: {loaded.code}: {loaded.message}")

    result: dict[str, object] = {
        "run_at_utc": datetime.now(UTC).isoformat(),
        "commit": "bb5c622 (supplied repository snapshot)",
        "python": sys.version,
        "environment": "FastAPI TestClient + in-memory SQLite; sequential; no concurrency",
        "dataset": {
            "seed": 2026,
            "hubs": loaded.value.hubs,
            "parking_spaces": loaded.value.parking_spaces,
            "charging_points": loaded.value.charging_points,
            "vehicles": loaded.value.vehicles,
            "users": loaded.value.users,
        },
        "sample_count_per_operation": count,
    }
    try:
        with TestClient(app) as client:
            login = client.post(
                "/auth/login", json={"code": "OPS-01", "password": "measurement-pass"}
            )
            if login.status_code != 200:
                raise RuntimeError(f"operator login failed: {login.status_code} {login.text}")
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            reads = {}
            for name, path in (
                ("GET /hubs", "/hubs"),
                ("GET /hubs/H01/vehicles", "/hubs/H01/vehicles"),
                ("GET /api/v1/monitoring/metrics/hubs", "/api/v1/monitoring/metrics/hubs"),
                ("GET /charging/queue", "/charging/queue"),
            ):
                samples, statuses = timed_requests(client, "GET", path, headers, count)
                reads[name] = summarize(name, samples, statuses)
            result["nfr02_read_endpoints"] = reads

            vehicles = sorted(repository.query(Vehicle), key=lambda row: row.vehicle_id)
            write_samples: list[float] = []
            write_statuses: list[int] = []
            write_errors: list[dict[str, object]] = []
            candidates = [
                vehicle for vehicle in vehicles if vehicle.hub_id and vehicle.battery_pct < 100
            ]
            if len(candidates) < count:
                raise RuntimeError(f"only {len(candidates)} eligible vehicles for {count} writes")
            for index, vehicle in enumerate(candidates[:count], start=1):
                payload = {
                    "request_id": f"NFR03-{index:03d}",
                    "vehicle_id": vehicle.vehicle_id,
                    "hub_id": vehicle.hub_id,
                    "target_soc": 100.0,
                    "queue_if_full": True,
                }
                start = time.perf_counter()
                response = client.post(
                    "/charging/requests/immediate", json=payload, headers=headers
                )
                write_samples.append((time.perf_counter() - start) * 1000)
                write_statuses.append(response.status_code)
                if not 200 <= response.status_code < 300:
                    write_errors.append(
                        {
                            "request_id": payload["request_id"],
                            "status": response.status_code,
                            "body": response.text,
                        }
                    )
            result["nfr03_write_operation"] = summarize(
                "POST /charging/requests/immediate", write_samples, write_statuses
            )
            result["nfr03_write_errors"] = write_errors

        return result
    finally:
        repository.close()


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    report = main_run(args.output, args.count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "nfr02_read_endpoints"}, indent=2
        )
    )
    for name, metrics in report["nfr02_read_endpoints"].items():
        print(name, {key: metrics[key] for key in ("samples", "success_count", "p95_ms", "max_ms")})


if __name__ == "__main__":
    cli_main()
