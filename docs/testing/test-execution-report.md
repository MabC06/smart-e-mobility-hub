# Test Execution Report — M8

> **Owner:** M8 — Testing, QA & Report Integration Lead  
> **Repository baseline:** `bb5c622` (supplied snapshot, 2026-11-18); local test workspace includes the TC-M8-016 route-inspection test adjustment described below  
> **Execution date:** 2026-11-20  
> **Test environment:** Python 3.12.10 (user-reported), FastAPI 0.162.0, Starlette 1.10.0  
> **Status:** Regression evidence updated; full-system QA sign-off remains open.

## 1. Scope executed

| Suite | Command | Result | Notes |
|---|---|---|---|
| M8 integration suite | `python -m pytest -q tests/integration --disable-warnings` | **7 passed, 1 warning** | Real `build_app()` composition; isolated SQLite repository; deterministic fixture |
| Focused regression suite | `python -m pytest -q tests/integration tests/iot_sim tests/core/test_main.py tests/core/test_providers.py` | **66 passed, 1 warning** | Includes M8 integration, IoT simulator, Core application and provider tests |
| Full repository suite | `python -m pytest -q` | **1,400 passed, 1 skipped, 1 warning** | Completed successfully in 106.68 s (1:46) |
| NFR-02 read measurements | `python tests/performance/measure_nfr02_03.py --output docs/testing/evidence/nfr02-03-python312-rerun.json --count 100` | **100/100 successful per endpoint** | Python 3.12.10; four selected read endpoints; sequential DS-STD run |
| NFR-03 write measurements | Same command | **100/100 successful** | Python 3.12.10; 100 sequential immediate-charging writes |

The three pytest results above are from the user's local workspace on 2026-11-20. The full-suite result supersedes the earlier incomplete/timeout observation recorded in the previous draft.

## 2. Integration suite results

| Test case | Scenario | Result |
|---|---|---|
| TC-M8-016 | Application composition and route mounting | Pass |
| TC-M8-017 | Provider registration matches the tested Phase 3 snapshot contract | Pass |
| TC-M8-018 | ChargingDemand provider callable through Core | Pass |
| TC-M8-019 | Authenticated Core Hub read | Pass |
| TC-M8-020 | Student denied operator-only endpoints | Pass |
| TC-M8-021 | Operator can read Charging, Allocation and Monitoring views | Pass |
| TC-M8-022 | M4 alternative-Hub endpoint uses installed provider | Pass |

Execution command:

```powershell
python -m pytest -q tests/integration --disable-warnings
```

Observed result: **7 passed, 1 warning in 1.31 s**.

### TC-M8-016 test adjustment

The route assertion was changed to inspect the generated OpenAPI paths rather than assuming every object in `app.routes` exposes a `.path` attribute. The previous assertion raised `AttributeError` on an internal `_IncludedRouter` object under the tested FastAPI/Starlette versions. The test continues to verify the required API paths and checks the UI login route with an HTTP request. This was a test-implementation compatibility adjustment; it is not recorded as an application defect.

## 3. Focused and full regression results

Focused regression command:

```powershell
python -m pytest -q tests/integration tests/iot_sim tests/core/test_main.py tests/core/test_providers.py
```

Observed result: **66 passed, 1 warning in 15.54 s**.

Full repository command:

```powershell
python -m pytest -q
```

Observed result: **1,400 passed, 1 skipped, 1 warning in 106.68 s**.

The skipped test remains reported as skipped; it is not counted as passed. The warning is a `StarletteDeprecationWarning` from `fastapi.testclient`, stating that using `httpx` with `starlette.testclient` is deprecated and recommending `httpx2`. It did not fail the test run. Track this as a dependency/deprecation maintenance item, not as a failed functional test.

## 4. NFR-02 and NFR-03 measurement results

The latest raw measurement file is:

`docs/testing/evidence/nfr02-03-python312-rerun.json`

It records Python 3.12.10, commit `bb5c622`, FastAPI TestClient, in-memory SQLite, sequential execution without concurrency, DS-STD seed 2026, and 100 samples per operation.

- **NFR-02:** all four measured read endpoints returned 100/100 HTTP 200 responses. Their p95 values ranged from 9.067 ms to 39.059 ms; maximum values ranged from 13.263 ms to 94.486 ms. All four satisfy p95 ≤500 ms and max ≤2,000 ms.
- **NFR-03:** `POST /charging/requests/immediate` returned 100/100 HTTP 200 responses, with p95 33.610 ms and zero recorded write errors. This satisfies p95 ≤1,000 ms.

These are **PASS results for the measured endpoints and operation only**. They do not establish that every read or write API meets the NFR targets, nor do TestClient/in-memory SQLite timings constitute production performance guarantees. See `nfr-measurements.md` and the raw JSON for full details.

## 5. Environment and limitations

- The measurement JSON identifies commit `bb5c622`. The pytest results were run in the user's local workspace, which also contained the TC-M8-016 test adjustment. The exact commit containing that adjustment was not supplied with the test output.
- Integration tests use an isolated SQLite database and deterministic fixture data. They do not use DS-STD except for the separate NFR measurement runner.
- The full repository test suite completed; this supersedes the earlier timeout note.
- CI coverage thresholds have not been verified from a current PR Checks/coverage artifact.
- The current integration cases do not constitute complete end-to-end coverage of every Reservation → Allocation → Charging → Monitoring business workflow.
- The PRs for M3–M6 have been reported as completed by their owners but are not yet merged. The current results must not be described as sign-off of their unmerged PR contents unless those PR branches were explicitly included in the tested workspace.

## 6. Blocked / incomplete integration scope

1. **Reservation provider:** the tested snapshot's `reservation.install()` does not register `ProviderPort.RESERVATION_DEMAND` or `ProviderPort.HOLD_CONSUMER`. Revalidate TC-M8-017 and dependent workflows after the relevant M2 implementation is merged.
2. **UI integration:** `src/ui/routes.py` in the supplied snapshot reads `ui.sample_data`; current UI pages are not evidence of an end-to-end Core-integrated interface. Recheck against M7's latest PR before final sign-off.
3. **Full business journeys:** rental → dispatch → charging → monitoring has not been executed as one end-to-end flow in this suite.
4. **NFR-14:** independent fresh-clone verification has not been performed.
5. **NFR-01, NFR-04, NFR-05 and remaining NFRs:** evidence remains incomplete; see `nfr-measurements.md`.

## 7. Defects and observations

The existing defect log contains seven previously recorded defects (one High and six Low, all recorded Closed after PR #39). M2 and M5 summary entries still require module-owner confirmation. The latest M8 integration, focused regression and full-suite runs reported no failing tests. No new application defect is inferred from the earlier TC-M8-016 `AttributeError`, because it was resolved by correcting the test's route-inspection method and all seven integration tests then passed.

The single Starlette deprecation warning is recorded as a maintenance observation. It did not cause a test failure.

## 8. Exit assessment

**M8 has completed the recorded integration and regression runs on the local workspace:** 7 integration tests passed, 66 focused tests passed, and the full repository suite completed with 1,400 passed and 1 skipped. NFR-02 and NFR-03 passed for their measured scope on Python 3.12.10.

**M8 Testing & Validation is not fully signed off.** Independent NFR-14 fresh-clone verification, remaining NFR evidence, current CI coverage confirmation, complete FR/BR/UC traceability, confirmation of M2/M5 defect-log entries, and post-merge integration validation of the M3–M6 PRs remain open.
