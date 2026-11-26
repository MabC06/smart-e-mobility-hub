"""TC-M6-006..010: scenarios SC-02 to SC-05 and the baseline/mitigated comparison (FR-12)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import main
from core.auth import hash_password
from core.clock import FixedClock
from core.domain.enums import Role, VehicleType
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec, charging_point_id
from simulation.models import (
    ChargerFailureParams,
    ChargingSurgeParams,
    HubCapacityParams,
    ImbalanceParams,
    ScenarioType,
    SimulationConfig,
)

PASSWORD = "m6-test-password"


def _fleet(prefix: str, batteries: list[float]) -> tuple[VehicleSpec, ...]:
    return tuple(
        VehicleSpec(f"{prefix}-{i:02d}", f"{prefix}-{i:02d}", VehicleType.E_BIKE, b)
        for i, b in enumerate(batteries)
    )


@pytest.fixture
def app():
    settings = main.Settings.from_env(
        {"SECRET_KEY": "m6-scenario-test-token-key-0123456789", "LOG_LEVEL": "WARNING"}
    )
    application = main.build_app(
        settings,
        clock=FixedClock(datetime(2026, 11, 25, 9, tzinfo=UTC)),
        module_names=("simulation",),
    )
    network = NetworkSpec(
        hubs=(
            # H1: 4 spaces, 2 charging points, 3 vehicles of which 2 are drained.
            HubSpec("H1", "Lecture", "A", 4, 2, vehicles=_fleet("A", [10, 12, 90])),
            # H2: 30 spaces, 4 charging points, 20 vehicles all charged.
            HubSpec("H2", "Dorm", "B", 30, 4, vehicles=_fleet("B", [90] * 20)),
        ),
        users=(UserSpec("OP", "OPERATOR", Role.OPERATOR, hash_password(PASSWORD, 1000)),),
    )
    assert isinstance(application.state.core.commands.load_network(network, main.SEEDER), Ok)
    return application


def _run(app, scenario: ScenarioType, params, horizon: int = 120):
    config = SimulationConfig("SIM-T", scenario, params, time_horizon_minutes=horizon)
    before = app.state.core.snapshots.export_snapshot()
    report = app.state.simulation_service.run_simulation(config)
    assert app.state.core.snapshots.export_snapshot() == before  # FR-12.1: live state unchanged
    return report


@pytest.mark.tc_m6_006
def test_hub_at_capacity_sends_returns_to_the_hub_with_most_space(app):
    """TC-M6-006 · Verifies: FR-12, UC-M6-01.

    Expected: 36 returns in 60 min at H1 with 1 free space leave 35 unmet; H2 takes 10 more
    (its free spaces), so the mitigated unmet count is 25; the live state does not change.
    """
    report = _run(app, ScenarioType.HUB_AT_CAPACITY, HubCapacityParams(["H1"], 6, 60))

    (row,) = report.hub_metrics
    assert (row.total_requests, row.unmet_requests) == (36, 35)
    (rec,) = report.recommendations
    assert rec["recommendation_type"] == "ALTERNATIVE_RETURN_HUB"
    assert (rec["source_hub_id"], rec["destination_hub_id"], rec["batch_size"]) == (
        "H1",
        "H2",
        10,
    )
    assert report.mitigated_hub_metrics[0].unmet_requests == 25
    assert report.metric_name == "Return rejection rate"
    assert report.mitigated_shortage_rate_pct < report.baseline_shortage_rate_pct


@pytest.mark.tc_m6_007
def test_charging_surge_shifts_drained_vehicles_to_spare_chargers(app):
    """TC-M6-007 · Verifies: FR-12, UC-M6-01.

    Expected: in 60 min H1's 2 points serve 2 of its 2 drained + 3 extra vehicles (3 unmet);
    H2 has spare chargers, so all 3 shift there and the mitigated unmet count is 0.
    """
    params = ChargingSurgeParams(["H1"], soc_threshold=20.0, extra_drained_per_hub=3)
    report = _run(app, ScenarioType.CHARGING_SURGE, params, horizon=60)

    (row,) = report.hub_metrics
    assert (row.total_requests, row.unmet_requests) == (5, 3)
    (rec,) = report.recommendations
    assert rec["recommendation_type"] == "CHARGING_SHIFT" and rec["batch_size"] == 3
    assert report.mitigated_shortage_rate_pct == 0.0


@pytest.mark.tc_m6_008
def test_charger_failure_lowers_capacity_for_the_repair_time(app):
    """TC-M6-008 · Verifies: FR-12, UC-M6-01.

    Expected: both H1 points down for the whole 60 min leave its 2 drained vehicles unserved;
    an unknown point is refused with ValueError.
    """
    failed = [charging_point_id("H1", 1), charging_point_id("H1", 2)]
    report = _run(
        app, ScenarioType.CHARGER_FAILURE, ChargerFailureParams(failed, 0, 60), horizon=60
    )

    (row,) = report.hub_metrics
    assert (row.hub_id, row.total_requests, row.unmet_requests) == ("H1", 2, 2)
    assert report.recommendations[0]["destination_hub_id"] == "H2"
    with pytest.raises(ValueError, match="unknown charging point"):
        _run(app, ScenarioType.CHARGER_FAILURE, ChargerFailureParams(["CP-NONE"]))


@pytest.mark.tc_m6_009
def test_imbalance_moves_a_batch_that_arrives_after_the_transit_delay(app):
    """TC-M6-009 · Verifies: FR-12, BR-M6-03.

    Expected: H1 has 1 rentable vehicle for 10 requests (9 unmet); H2 sends min(10, 9, 20-5) = 9;
    after 15 of 120 min in transit 7 count, so 2 stay unmet; a Hub cannot be both sides.
    """
    report = _run(app, ScenarioType.VEHICLE_IMBALANCE, ImbalanceParams(["H2"], ["H1"], 10, 15))

    (row,) = report.hub_metrics
    assert (row.total_requests, row.unmet_requests) == (10, 9)
    (rec,) = report.recommendations
    assert rec["recommendation_type"] == "VEHICLE_REDISTRIBUTION" and rec["batch_size"] == 9
    assert report.mitigated_hub_metrics[0].unmet_requests == 2
    with pytest.raises(ValueError):
        ImbalanceParams(["H1"], ["H1"])


@pytest.mark.tc_m6_010
@pytest.mark.parametrize(
    ("scenario", "fields"),
    [
        ("SC-01", {"target_hub_ids": ["H1"]}),
        ("SC-02", {"target_hub_ids": ["H1"]}),
        ("SC-03", {}),
        ("SC-04", {"failed_charging_point_ids": [charging_point_id("H2", 1)]}),
        ("SC-05", {"source_hub_ids": ["H2"], "destination_hub_ids": ["H1"]}),
    ],
)
def test_every_standard_scenario_runs_through_the_route(app, scenario, fields):
    """TC-M6-010 · Verifies: FR-12, UC-M7-09, NFR-21.

    Expected: 200 with the baseline and mitigated rates; an unknown Hub is 400 INVALID_INPUT.
    """
    client = TestClient(app)
    token = client.post("/auth/login", json={"code": "OPERATOR", "password": PASSWORD}).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    body = {"simulation_id": "SIM-R", "scenario_id": scenario, **fields}

    response = client.post("/simulation/runs", headers=headers, json=body)

    assert response.status_code == 200, response.text
    assert {"baseline_shortage_rate_pct", "mitigated_shortage_rate_pct"} <= set(response.json())
    if scenario in ("SC-02", "SC-05"):
        key = "target_hub_ids" if scenario == "SC-02" else "destination_hub_ids"
        wrong = client.post("/simulation/runs", headers=headers, json={**body, key: ["H9"]})
        assert wrong.status_code == 400
        assert wrong.json()["detail"]["code"] == "INVALID_INPUT"
