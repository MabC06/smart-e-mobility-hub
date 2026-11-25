# Test Execution Report — M8

> **Owner:** M8 — Testing, QA & Report Integration Lead
> **Baseline:** testing branch at `01d68e764876a4c22fad53145843d164339784f9` (clean working tree). It is `develop` plus the approved, not-yet-merged PRs #45, #47–#52 merged locally by M8. The exact hash is not the hash of `develop`.
> **Execution date:** 2026-11-23 · **Environment:** Windows, Python 3.12.10, pytest 9.2.0, FastAPI 0.162.0, Starlette 1.10.0, ruff 0.17.3, mypy 2.4.1
> **Status:** Regression, NFR evidence, and NFR-14 fresh-clone check complete for the scope below; full sign-off remains open (section 6).

## 1. Static checks

| Check | Command | Result |
|---|---|---|
| Lint | `py -m ruff check .` | All checks passed |
| Format | `py -m ruff format --check .` | 202 files already formatted |
| Types | `py -m mypy` | Success: no issues found in 47 source files |

## 2. Test runs

| Suite | Command | Result |
|---|---|---|
| Full repository, with coverage | `py -m pytest -q --cov=core --cov=reservation --cov=charging --cov=allocation --cov=monitoring --cov=simulation` | **1,501 passed, 1 skipped, 1 warning in 368.82 s** |
| M8 integration | `py -m pytest -q tests/integration` | 7 passed |
| Focused regression | `tests/integration tests/iot_sim tests/core/test_main.py tests/core/test_providers.py` | 66 passed |
| NFR-22 import boundaries | `tests/core/test_import_boundaries.py` | 25 passed |
| Reservation (M2) | `tests/reservation` | 159 passed |
| Charging (M3) | `tests/charging` | 45 passed |
| Allocation (M4) | `tests/allocation` | 93 passed |
| Monitoring (M5) | `tests/monitoring` | 40 passed |
| Simulation (M6) | `tests/simulation` | 9 passed (NFR-12/13 subset: 3 passed) |
| UI (M7) | `tests/ui` | 75 passed |
| NFR-06 concurrency | `tests/core/test_concurrency.py` | 42 passed |
| NFR-14 fresh clone (`fresh-nfr14`) | 5 commands, total elapsed **4m34s** (274 s), including `py -m pytest -q` (1,501 passed, 1 skipped in 95.66 s), `ruff`, `mypy`, and Uvicorn startup | **Pass** (≤ 5 commands, ≤ 15 min) |

The skipped test is `tests/core/test_module_entities.py:316`, skipped with the reason "only the database has foreign keys" (it applies to the SQL repository only, not the in-memory one). It is reported as skipped, not passed. A second full run with `-rs` gave 1,501 passed, 1 skipped in 215.73 s (the 368.82 s run was under coverage), and the fresh-clone `fresh-nfr14` run gave 1,501 passed, 1 skipped, 1 warning in 95.66 s. The single warning is `StarletteDeprecationWarning` (`httpx` with `starlette.testclient`; `httpx2` recommended): a maintenance item, not a failure.

### Coverage (NFR-24)

| Module | Statements | Missed | Coverage | Threshold | Result |
|---|---|---|---|---|---|
| core | 2,581 | 30 | 98.8 % | 70 % | Pass |
| reservation | 349 | 13 | 96.3 % | 60 % | Pass |
| charging | 612 | 72 | 88.2 % | 60 % | Pass |
| allocation | 779 | 66 | 91.5 % | 60 % | Pass |
| monitoring | 519 | 66 | 87.3 % | 60 % | Pass |
| simulation | 158 | 12 | 92.4 % | 60 % | Pass |

## 3. Integration cases (TC-M8-016 to TC-M8-022)

| Test case | Scenario | Result |
|---|---|---|
| TC-M8-016 | Application composition and route mounting | Pass |
| TC-M8-017 | Provider registration: M3/M4 providers, M2 `RESERVATION_DEMAND` registered and callable (PR #54), `HOLD_CONSUMER` not registered | Pass at `01d68e7` with the earlier version of the test, which asserted both M2 ports absent. The updated test passes only with PR #54 merged; rerun on `develop` |
| TC-M8-018 | ChargingDemand provider callable through Core | Pass |
| TC-M8-019 | Authenticated Core Hub read | Pass |
| TC-M8-020 | Student denied operator-only endpoints | Pass |
| TC-M8-021 | Operator reads Charging, Allocation, Monitoring views | Pass |
| TC-M8-022 | M4 alternative-Hub endpoint uses installed provider | Pass |

## 4. NFR results

Summary (details and raw files: `nfr-measurements.md`): NFR-01 Pass (API); NFR-02 Pass (4 endpoints); NFR-03 Pass (1 operation); NFR-04 charging Pass at 15 queued per Hub (exceeds 3 s at depth 50 in 2 of 4 runs → DEF-M3-007, Accepted); NFR-04 allocation **Blocked** (no M2 provider); NFR-05 Partial (SC-01 only); NFR-12 and NFR-13 Pass for SC-01; NFR-14 **Pass** (5 commands, 4m34s ≤ 15 min on `fresh-nfr14`, `1,501 passed, 1 skipped` in 95.66 s, Uvicorn startup verified with `hubs=10, parking_spaces=400, charging_points=61, vehicles=350, users=1005`); NFR-22 Pass; NFR-24 Pass; NFR-06 Pass.

## 5. Defects

23 recorded defects: 22 Closed and 1 Accepted (0 Critical, 6 High, 6 Medium, 11 Low; `defect-log.md`). The Accepted one is DEF-M3-007 (Medium, NFR-04 at depth 50; Lead decision 2026-11-24, known limitation). No test failed in the runs above. The earlier TC-M8-016 `AttributeError` was a test-implementation issue, not an application defect.

## 6. Limitations and open items

1. **M2 providers:** at `01d68e7` `reservation.install()` registered neither `RESERVATION_DEMAND` nor `HOLD_CONSUMER` (PR #52 is documentation only). PR #54 registers `RESERVATION_DEMAND`; `HOLD_CONSUMER` stays unregistered. Allocation timing and every flow that needs reservation demand or hold data (rental → dispatch → charging → monitoring) are not verified end to end.
2. **M6:** only SC-01 (demand surge) exists; SC-02 to SC-05 not implemented (DEV-08).
3. **M7:** UI pages read `ui.sample_data` for several screens (DEV-10 to DEV-12); UI tests do not prove Core integration of those screens.
4. **NFR-14 note:** completed by M8 on a local clone (`fresh-nfr14`) in 5 commands and 4m34s (`<= 5` commands, `<= 15` min); if independent verification by another member is still desired per `nfr-evidence-core.md`, it can be recorded alongside this run.
5. **Not merged into `develop`:** results apply to the local testing branch; they must be repeated on `develop` after the merges.
6. CI coverage artifact was not checked; coverage above is from the local run.
7. Concurrent-load figures are not measured (D-024; DEV-01).
8. FR/BR/UC traceability has gaps; see `traceability-sheet.md`.

## 7. Exit assessment

All executed suites pass and static checks are clean on the testing branch. M8 sign-off is **conditional**: open items 1–3, 5, and 8 above must be closed or accepted into report section 4.4.