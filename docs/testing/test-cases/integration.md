# M8 Integration Test Cases

> **Owner:** M8 — Testing, QA & Report Integration Lead  
> **Baseline:** testing branch `01d68e764876a4c22fad53145843d164339784f9` (2026-11-23); `develop` plus approved, not-yet-merged PRs #45, #47–#52  
> **Implementation:** `tests/integration/`  
> **Test environment:** FastAPI `TestClient`, isolated SQLite repository, deterministic two-Hub fixture.

These cases exercise the real `src/main.py::build_app` composition root. They are not a substitute for module unit tests or DS-STD performance tests.

| TC ID | Scenario | Verifies | Technique | Expected result | Implementation |
|---|---|---|---|---|---|
| TC-M8-016 | Build the application with the real module installation sequence | D-013, Core API spec §8 | Integration / composition | Reservation, Charging, Allocation, Monitoring, Simulation and UI components/routes are installed; OpenAPI is available | `test_build_app_installs_the_expected_modules_and_routes` |
| TC-M8-017 | Check provider registration against D-020 | D-020, NFR-22 | Interface contract | M3 and M4 providers are registered; M2 `RESERVATION_DEMAND` is registered and callable through Core (PR #54); `HOLD_CONSUMER` is not registered. Passes only when PR #54 is merged (not at `01d68e7`) | `test_provider_registration_matches_the_phase_3_contract` |
| TC-M8-018 | Call ChargingDemand through Core's provider registry | FR-06, D-020 | Integration / contract | Registered M3 provider returns a successful empty scheduled-session list for a valid Hub with no sessions | `test_charging_demand_provider_is_callable_through_core` |
| TC-M8-019 | Read Hubs through the authenticated Core REST API | FR-01, NFR-16 | API integration / EP | Unauthenticated request returns 401; authenticated student receives both seeded Hubs | `test_core_read_api_requires_authentication_and_returns_seeded_hubs` |
| TC-M8-020 | Reject student access to operator-only module endpoints | NFR-16, D-023 | Security / role partition | Charging queue, Allocation tasks and Monitoring incidents return 403 to a student | `test_operator_only_module_endpoints_reject_student` |
| TC-M8-021 | Allow an operator to read module views | NFR-16, D-023 | Security / integration | Operator receives 200 from Charging, Allocation and Monitoring read endpoints | `test_operator_can_read_charging_allocation_and_monitoring_views` |
| TC-M8-022 | Request alternative Hubs through M4's installed provider | FR-10, UC-M4-05, BR-M4-10, D-020 | Integration / provider contract | Authenticated operator receives a valid response with candidates, timestamp and reason code | `test_allocation_alternative_hub_endpoint_uses_installed_provider` |

## Execution status

All seven cases passed on 2026-11-23 at `01d68e7` (Windows, Python 3.12.10, FastAPI 0.162.0, Starlette 1.10.0):

```powershell
py -m pytest -q tests/integration --disable-warnings
```

Result: **7 passed, 1 warning in 1.03 s**. They also pass in the focused run (66 passed) and the full run (1,501 passed, 1 skipped). TC-M8-016 inspects OpenAPI paths instead of assuming every `app.routes` entry exposes `.path`; the UI login route is checked through an HTTP request. See `../test-execution-report.md`.

## Explicitly blocked / not covered

- Hold-consumption integration: **Blocked** because `HOLD_CONSUMER` is not registered. Reservation-demand integration becomes testable once PR #54 is merged; revalidate then.
- Full rental → dispatch → charging → monitoring workflow: not covered; needs the M2 providers.
- UI-to-Core operational journey: not covered; several UI screens still read `ui.sample_data` (DEV-10 to DEV-12). Recheck against M7's latest PR.
- NFR measurements are not part of these small-fixture tests; see the cases below and `../nfr-measurements.md`.

## Performance measurement cases (D-024)

| TC ID | Scenario | Verifies | Technique | Acceptance | Implementation |
|---|---|---|---|---|---|
| TC-M8-023 | Measure each selected read endpoint over 100 sequential requests on DS-STD | NFR-02, D-024 | Performance / percentile analysis | Per endpoint p95 ≤500 ms and max ≤2,000 ms | `tests/performance/measure_nfr02_03.py` |
| TC-M8-024 | Measure immediate charging writes over 100 sequential operations on DS-STD | NFR-03, D-024 | Performance / percentile analysis | p95 ≤1,000 ms | `tests/performance/measure_nfr02_03.py` |

Executed 2026-11-23 at `01d68e7`: TC-M8-023 **Pass** (p95 2.84–12.91 ms, max ≤ 41.6 ms; `evidence/nfr02-03-phase34.json`); TC-M8-024 **Pass** (p95 10.573 ms). The earlier file `nfr02-03-python312-rerun.json` (`bb5c622`) is superseded.

## Measurement cases added in Phase 3+4

Script: `tests/performance/measure_nfr01_04_05.py`; each measurement runs on a freshly loaded DS-STD. Results are in `../nfr-measurements.md`; raw files `../evidence/nfr01-04-05-run1.json` … `run3.json` and `nfr01-04-05-phase34-stub.json`.

| TC ID | Scenario | Verifies | Technique | Acceptance | Result (01d68e7) |
|---|---|---|---|---|---|
| TC-M8-025 | Write, then read `GET /charging/sessions`, 100 times | NFR-01 | Performance / read-after-write | New state visible in the next read; p95 ≤ 1,000 ms | **Pass**: 100/100 visible; p95 3.97–5.23 ms |
| TC-M8-026 | `POST /charging/schedule/optimize` per Hub, 15 queued requests on each of 10 Hubs; depth sweep 5–50 on H01 | NFR-04, FR-11 | Performance | ≤ 3,000 ms per Hub | **Pass** at depth 15 (worst 1.50 s). Depth 50: 2.64, 2.67, 3.56, 3.83 s, so exceeds in 2 of 4 runs (DEF-M3-007, Accepted) |
| TC-M8-027 | `POST /allocation/tasks/plan` on DS-STD | NFR-04, FR-10 | Performance | ≤ 5,000 ms, status 200 | **Blocked**: 503 `RESOURCE_UNAVAILABLE`, no M2 provider. Stub timing p95 78.7 ms is reference only |
| TC-M8-028 | `POST /simulation/runs` for each standard scenario | NFR-05, FR-12 | Performance | Each of 5 scenarios ≤ 30,000 ms | **Partial**: SC-01 passes (p95 113–164 ms); SC-02–05 not implemented (DEV-08) |
| TC-M8-029 | Run SC-01 twice with the same seed; compare operational state hash and output (wall-clock fields `as_of`, `executed_at`, `taken_at` removed) | NFR-12, NFR-13, FR-12 | Metamorphic / repeat-run | State unchanged after run; outputs identical | **Pass** for SC-01 (4 of 4 runs) |