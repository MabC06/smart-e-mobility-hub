# M8 Integration Test Cases

> **Owner:** M8 — Testing, QA & Report Integration Lead  
> **Baseline:** `develop` at `0056f23` (2026-11-26, every PR up to #63 merged; rerun by M1). First round: testing branch `01d68e7` (2026-11-23).  
> **Implementation:** `tests/integration/`  
> **Test environment:** FastAPI `TestClient`, isolated SQLite repository, deterministic two-Hub fixture.

These cases exercise the real `src/main.py::build_app` composition root. They are not a substitute for module unit tests or DS-STD performance tests.

| TC ID | Scenario | Verifies | Technique | Expected result | Implementation |
|---|---|---|---|---|---|
| TC-M8-016 | Build the application with the real module installation sequence | D-013, Core API spec §8 | Integration / composition | Reservation, Charging, Allocation, Monitoring, Simulation and UI components/routes are installed; OpenAPI is available | `test_build_app_installs_the_expected_modules_and_routes` |
| TC-M8-017 | Check provider registration against D-020 | D-020, NFR-22 | Interface contract | M3 and M4 providers are registered; M2 `RESERVATION_DEMAND` is registered and callable through Core (PR #54); `HOLD_CONSUMER` is not registered | `test_provider_registration_matches_the_phase_3_contract` |
| TC-M8-018 | Call ChargingDemand through Core's provider registry | FR-06, D-020 | Integration / contract | Registered M3 provider returns a successful empty scheduled-session list for a valid Hub with no sessions | `test_charging_demand_provider_is_callable_through_core` |
| TC-M8-019 | Read Hubs through the authenticated Core REST API | FR-01, NFR-16 | API integration / EP | Unauthenticated request returns 401; authenticated student receives both seeded Hubs | `test_core_read_api_requires_authentication_and_returns_seeded_hubs` |
| TC-M8-020 | Reject student access to operator-only module endpoints | NFR-16, D-023 | Security / role partition | Charging queue, Allocation tasks and Monitoring incidents return 403 to a student | `test_operator_only_module_endpoints_reject_student` |
| TC-M8-021 | Allow an operator to read module views | NFR-16, D-023 | Security / integration | Operator receives 200 from Charging, Allocation and Monitoring read endpoints | `test_operator_can_read_charging_allocation_and_monitoring_views` |
| TC-M8-022 | Request alternative Hubs through M4's installed provider | FR-10, UC-M4-05, BR-M4-10, D-020 | Integration / provider contract | Authenticated operator receives a valid response with candidates, timestamp and reason code | `test_allocation_alternative_hub_endpoint_uses_installed_provider` |

## Execution status

All seven cases passed on 2026-11-26 on `develop` at `0056f23` (Windows, Python 3.12.10, FastAPI 0.162.0, Starlette 1.10.0), in the integration run and in the full run (1,560 passed, 1 skipped):

```powershell
python -m pytest -q tests/integration --disable-warnings
``` TC-M8-016 inspects OpenAPI paths instead of assuming every `app.routes` entry exposes `.path`; the UI login route is checked through an HTTP request. See `../test-execution-report.md`.

## Explicitly blocked / not covered

- Hold-consumption integration: not covered, because `HOLD_CONSUMER` is not registered and no module consumes an M2 hold (DEV-16). Reservation demand is covered (TC-M8-017, TC-M8-027).
- Journeys across modules are covered by the UI tests on the real modules: rental with search, hold, pick-up and return (TC-M7-028, 029, 034, 035), private parking (TC-M7-036), charging (TC-M7-037, 040), vehicle, point and Hub commands with an incident (TC-M7-039), simulation to dispatch (TC-M7-041). No screen reads sample data (TC-M7-018).
- NFR measurements are not part of these small-fixture tests; see the cases below and `../nfr-measurements.md`.

## Performance measurement cases (D-024)

| TC ID | Scenario | Verifies | Technique | Acceptance | Implementation |
|---|---|---|---|---|---|
| TC-M8-023 | Measure each selected read endpoint over 100 sequential requests on DS-STD | NFR-02, D-024 | Performance / percentile analysis | Per endpoint p95 ≤500 ms and max ≤2,000 ms | `tests/performance/measure_nfr02_03.py` |
| TC-M8-024 | Measure immediate charging writes over 100 sequential operations on DS-STD | NFR-03, D-024 | Performance / percentile analysis | p95 ≤1,000 ms | `tests/performance/measure_nfr02_03.py` |

Executed 2026-11-26 at `267919e` (`develop` `0056f23` plus script fixes): TC-M8-023 **Pass** (p95 5.8–20.9 ms, max ≤ 98.9 ms; `evidence/nfr02-03-develop.json`); TC-M8-024 **Pass** (p95 231.4 ms; a write now also binds its Hub's queue, TC-M3-039). First round at `01d68e7`: p95 2.84–12.91 ms and 10.573 ms (`evidence/nfr02-03-phase34.json`).

## Measurement cases added in Phase 3+4

Script: `tests/performance/measure_nfr01_04_05.py`; each measurement runs on a freshly loaded DS-STD. Results are in `../nfr-measurements.md`; raw files `../evidence/nfr01-04-05-develop-run1.json` … `run3.json` (first round: `nfr01-04-05-run1.json` … `run3.json`, `nfr01-04-05-phase34-stub.json`).

| TC ID | Scenario | Verifies | Technique | Acceptance | Result (`develop`, 2026-11-26) |
|---|---|---|---|---|---|
| TC-M8-025 | Write, then read `GET /charging/sessions`, 100 times | NFR-01 | Performance / read-after-write | New state visible in the next read; p95 ≤ 1,000 ms | **Pass**: 100/100 visible (read at the Hub the write answered with); p95 7.2–8.1 ms |
| TC-M8-026 | `POST /charging/schedule/optimize` per Hub, 15 queued requests on each of 10 Hubs; depth sweep 5–50 on H01 | NFR-04, FR-11 | Performance | ≤ 3,000 ms per Hub | **Pass** at depth 15 (worst 1.75 s). Depth 50: 4.19, 4.26, 4.22 s, so exceeds in every run (DEF-M3-007, Accepted) |
| TC-M8-027 | `POST /allocation/tasks/plan` on DS-STD | NFR-04, FR-10 | Performance | ≤ 5,000 ms, status 200 | **Pass** with M2's real provider: 3 × 5 runs, all 200, max 358 ms |
| TC-M8-028 | `POST /simulation/runs` for each standard scenario | NFR-05, FR-12 | Performance | Each of 5 scenarios ≤ 30,000 ms | **Pass**: SC-01 to SC-05, 5 runs each, slowest 148 ms |
| TC-M8-029 | Run each scenario 5 times with the same seed; compare operational state and output (wall-clock fields `as_of`, `executed_at`, `taken_at` removed) | NFR-12, NFR-13, FR-12 | Metamorphic / repeat-run | State unchanged after the runs; outputs identical | **Pass** for SC-01 to SC-05 (3 of 3 rounds) |