# M8 Integration Test Cases

> **Owner:** M8 — Testing, QA & Report Integration Lead  
> **Baseline:** repository snapshot `bb5c622` (2026-11-18)  
> **Implementation:** `tests/integration/`  
> **Test environment:** FastAPI `TestClient`, isolated SQLite repository, deterministic two-Hub fixture.

These cases exercise the real `src/main.py::build_app` composition root. They are not a substitute for module unit tests or DS-STD performance tests.

| TC ID | Scenario | Verifies | Technique | Expected result | Implementation |
|---|---|---|---|---|---|
| TC-M8-016 | Build the application with the real module installation sequence | D-013, Core API spec §8 | Integration / composition | Reservation, Charging, Allocation, Monitoring, Simulation and UI components/routes are installed; OpenAPI is available | `test_build_app_installs_the_expected_modules_and_routes` |
| TC-M8-017 | Check provider registration against D-020 | D-020, NFR-22 | Interface contract | M3 and M4 providers are registered; M2 ReservationDemand and HoldConsumer remain absent in this snapshot | `test_provider_registration_matches_the_phase_3_contract` |
| TC-M8-018 | Call ChargingDemand through Core's provider registry | FR-06, D-020 | Integration / contract | Registered M3 provider returns a successful empty scheduled-session list for a valid Hub with no sessions | `test_charging_demand_provider_is_callable_through_core` |
| TC-M8-019 | Read Hubs through the authenticated Core REST API | FR-01, NFR-16 | API integration / EP | Unauthenticated request returns 401; authenticated student receives both seeded Hubs | `test_core_read_api_requires_authentication_and_returns_seeded_hubs` |
| TC-M8-020 | Reject student access to operator-only module endpoints | NFR-16, D-023 | Security / role partition | Charging queue, Allocation tasks and Monitoring incidents return 403 to a student | `test_operator_only_module_endpoints_reject_student` |
| TC-M8-021 | Allow an operator to read module views | NFR-16, D-023 | Security / integration | Operator receives 200 from Charging, Allocation and Monitoring read endpoints | `test_operator_can_read_charging_allocation_and_monitoring_views` |
| TC-M8-022 | Request alternative Hubs through M4's installed provider | FR-10, UC-M4-05, BR-M4-10, D-020 | Integration / provider contract | Authenticated operator receives a valid response with candidates, timestamp and reason code | `test_allocation_alternative_hub_endpoint_uses_installed_provider` |

## Execution status

The seven cases above passed in the user's local workspace on 2026-11-20 using:

```powershell
python -m pytest -q tests/integration --disable-warnings
```

Result: **7 passed, 1 warning in 1.31 s**. The test environment used Python 3.12.10, FastAPI 0.162.0 and Starlette 1.10.0 (versions supplied by the user). TC-M8-016 was adjusted to inspect OpenAPI paths instead of assuming every `app.routes` entry exposes `.path`; the UI login route is checked through an HTTP request. See `../test-execution-report.md` for focused and full regression results and limitations.

## Explicitly blocked / not covered

- Reservation-demand and hold-consumption integration: Blocked in the tested `bb5c622` snapshot until M2 registers `ReservationDemand` and `HoldConsumer` in `reservation.install()`. Revalidate after the relevant M2 PR is merged.
- Full rental → dispatch → charging workflow: not covered by these cases; requires the M2 provider contract and corresponding business-flow test data.
- UI-to-Core operational journey: not covered in the supplied `bb5c622` snapshot; the UI source uses `ui.sample_data`. Recheck against M7's latest PR before final sign-off.
- NFR-02/03 performance: not covered by these small-fixture integration tests; the separate DS-STD run is recorded in `../nfr-measurements.md` and `../evidence/nfr02-03-python312-rerun.json`.


## Performance measurement cases (D-024)

| TC ID | Scenario | Verifies | Technique | Acceptance | Implementation |
|---|---|---|---|---|---|
| TC-M8-023 | Measure each selected read endpoint over 100 sequential requests on DS-STD | NFR-02, D-024 | Performance / percentile analysis | Per endpoint p95 ≤500 ms and max ≤2,000 ms | `tests/performance/measure_nfr02_03.py` |
| TC-M8-024 | Measure immediate charging writes over 100 sequential operations on DS-STD | NFR-03, D-024 | Performance / percentile analysis | p95 ≤1,000 ms | `tests/performance/measure_nfr02_03.py` |
