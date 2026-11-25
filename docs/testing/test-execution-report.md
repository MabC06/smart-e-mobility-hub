# Test Execution Report — M8

> **Owner:** M8 — Testing, QA & Report Integration Lead (rerun on `develop` by M1, 2026-11-26)
> **Baseline:** `develop` at `0056f23` (Merge pull request #63; every PR up to #63 merged, nothing local). NFR measurements: `267919e` = `0056f23` plus three fixes to the measurement scripts only.
> **Execution date:** 2026-11-26 · **Environment:** Windows, Python 3.12.10, pytest 9.2.0, FastAPI 0.162.0, Starlette 1.10.0, ruff 0.17.3, mypy 2.4.1
> **Status:** Regression, coverage and NFR measurements complete on `develop`. The first round (2026-11-23, testing branch `01d68e7`) is superseded; its open items are closed or listed in section 6.

## 1. Static checks

| Check | Command | Result |
|---|---|---|
| Lint | `python -m ruff check .` | All checks passed |
| Format | `python -m ruff format --check .` | 217 files already formatted |
| Types | `python -m mypy` | Success: no issues found in 50 source files |
| CI on `develop` | GitHub Actions run `45666388041` on `0056f23` (lint, format, types, tests, coverage per module) | Success |

## 2. Test runs

| Suite | Command | Result |
|---|---|---|
| Full repository, with coverage | `python -m pytest -q --cov=core --cov=reservation --cov=charging --cov=allocation --cov=monitoring --cov=simulation --cov=ui --cov=iot_sim` | **1,560 passed, 1 skipped, 1 warning** |
| M8 integration | `tests/integration` | 7 passed |
| NFR-22 import boundaries | `tests/core/test_import_boundaries.py` | 25 passed |
| Reservation (M2) | `tests/reservation` | 180 passed |
| Charging (M3) | `tests/charging` | 48 passed |
| Allocation (M4) | `tests/allocation` | 95 passed |
| Monitoring (M5) | `tests/monitoring` | 40 passed |
| Simulation (M6) | `tests/simulation` | 18 passed |
| UI (M7) | `tests/ui` | 95 passed |
| Simulator (M8) | `tests/iot_sim` | 14 passed |
| NFR-06 concurrency | `tests/core/test_concurrency.py` | 42 passed |

The skipped test is `tests/core/test_module_entities.py:316`, skipped with the reason "only the database has foreign keys" (it applies to the SQL repository only). It is reported as skipped, not passed. The single warning is a Starlette deprecation notice about `httpx` in `starlette.testclient`.

### Coverage (NFR-24)

| Module | Statements | Missed | Coverage | Threshold | Result |
|---|---|---|---|---|---|
| core | 2,581 | 30 | 98.8 % | 70 % | Pass |
| reservation | 857 | 68 | 92.1 % | 60 % | Pass |
| charging | 654 | 72 | 89.0 % | 60 % | Pass |
| allocation | 845 | 70 | 91.7 % | 60 % | Pass |
| monitoring | 519 | 66 | 87.3 % | 60 % | Pass |
| simulation | 371 | 27 | 92.7 % | 60 % | Pass |
| ui | 704 | 57 | 91.9 % | 60 % | Pass |
| iot_sim | 104 | 1 | 99.0 % | 60 % | Pass |

Whole repository: 94 % (6,821 statements, 401 missed).

## 3. Integration cases (TC-M8-016 to TC-M8-022)

| Test case | Scenario | Result |
|---|---|---|
| TC-M8-016 | Application composition and route mounting | Pass |
| TC-M8-017 | Provider registration: M3/M4 providers, M2 `RESERVATION_DEMAND` registered and callable, `HOLD_CONSUMER` not registered | Pass |
| TC-M8-018 | ChargingDemand provider callable through Core | Pass |
| TC-M8-019 | Authenticated Core Hub read | Pass |
| TC-M8-020 | Student denied operator-only endpoints | Pass |
| TC-M8-021 | Operator reads Charging, Allocation, Monitoring views | Pass |
| TC-M8-022 | M4 alternative-Hub endpoint uses installed provider | Pass |

End-to-end journeys through the UI are covered by the UI tests on the real modules: rental with search, hold, pick-up and return (TC-M7-028, 029, 034, 035), private parking (TC-M7-036), charging change and cancel (TC-M7-037), vehicle, point and Hub commands (TC-M7-039), charging sessions (TC-M7-040), simulation to dispatch (TC-M7-041). They were also run by hand on the seeded network on 2026-11-25 and 2026-11-26, including on a phone.

## 4. NFR results

Summary (details and raw files: `nfr-measurements.md`): NFR-01 Pass (API); NFR-02 Pass (4 endpoints, p95 ≤ 20.9 ms); NFR-03 Pass (p95 231 ms); NFR-04 charging Pass at 15 queued per Hub (worst 1.75 s), exceeds 3 s at depth 50 in every run (DEF-M3-007, Accepted); NFR-04 allocation **Pass** with M2's real provider (max 358 ms); NFR-05 **Pass** for all five scenarios (slowest 148 ms); NFR-12 and NFR-13 Pass for SC-01 to SC-05; NFR-14 Pass (2026-11-23, not repeated); NFR-24 Pass.

## 5. Defects

29 recorded defects: 28 Closed and 1 Accepted (0 Critical, 7 High, 9 Medium, 13 Low; `defect-log.md`). Six were found on 2026-11-25 and 26 by running the demo on the seeded network (DEF-M2-002, DEF-M2-003, DEF-M3-008, DEF-M7-001 to 003) and fixed in PRs #59, #62 and #63 with new tests. The Accepted one is DEF-M3-007 (Medium, NFR-04 at depth 50). No test failed in the runs above.

## 6. Limitations and open items

1. **M2 `HoldConsumer`** is not registered and M2 does not call M4 for an alternative Hub (DEV-16). No other module consumes an M2 hold, so no flow is blocked by it.
2. **Parking/charging bundle** (BR-M2-12) is not implemented (DEV-15); a private EV books parking and charging separately.
3. **M6** counts per Hub over the whole horizon; `time_step_minutes` does not evolve the state (DEV-08).
4. **Concurrent load** is not measured (D-024, DEV-01).
5. **Traceability:** BR 28/34 and UC 36/38 have a test case; the rest are listed with reasons in `traceability-sheet.md` section 5.
6. **NFR-14** was not repeated after 2026-11-23.

## 7. Exit assessment

On `develop` at `0056f23` all tests pass, static checks and CI are clean, every module meets its coverage threshold, and NFR-01 to NFR-05, NFR-12, NFR-13, NFR-14 and NFR-24 are met within their measured scope, with NFR-04 for charging met at the standard load. The remaining items in section 6 are known limitations recorded in report section 4.4; none blocks the release for the report and the demo.
