# 09. Testing and Validation

> **Status:** Working draft — 2026-11-20  
> **Owner:** M8 — Testing, QA & Report Integration Lead  
> **Baseline:** supplied repository snapshot `bb5c622`; latest local test execution includes the TC-M8-016 test adjustment described in `docs/testing/test-execution-report.md`.

## 9.1 Testing approach

Testing follows the layered strategy defined in `docs/testing/test-plan-final.md`: module unit/component tests are owned by each module member; M8 coordinates integration/system verification, requirements traceability, NFR evidence and consolidated reporting. Test cases use the `TC-M<n>-###` convention and identify the requirements they verify.

Integration tests build the application through `src/main.py::build_app` with an isolated SQL repository. The M8 integration suite checks application composition, D-020 provider registration, Core provider invocation, authenticated Core reads, role-based access to Charging/Allocation/Monitoring endpoints, and M4's alternative-Hub provider route.

## 9.2 Integration and regression results

On 2026-11-20, the user's local Python 3.12.10 workspace produced:

| Test run | Result |
|---|---|
| `python -m pytest -q tests/integration --disable-warnings` | 7 passed, 1 warning in 1.31 s |
| `python -m pytest -q tests/integration tests/iot_sim tests/core/test_main.py tests/core/test_providers.py` | 66 passed, 1 warning in 15.54 s |
| `python -m pytest -q` | 1,400 passed, 1 skipped, 1 warning in 106.68 s |

The full repository regression completed successfully; this supersedes the earlier draft's incomplete/timeout note. One test was skipped and is not counted as passed. The warning is a Starlette deprecation warning emitted through `fastapi.testclient`: use of `httpx` with `starlette.testclient` is deprecated and `httpx2` is recommended. It did not fail the test runs.

TC-M8-016 initially failed because the test accessed `.path` on every item in `app.routes`, but the tested FastAPI/Starlette combination includes an internal `_IncludedRouter` object without that attribute. The test was adjusted to inspect the generated OpenAPI paths for API routes and to check `/ui/login` using an HTTP request. The subsequent integration run passed all seven cases. This was a test compatibility correction, not an application defect.

These results establish regression evidence for the user's local workspace. The M3–M6 PRs have been reported complete by their owners but remain unmerged; do not treat this run as sign-off of unmerged PR contents unless those PR branches were included in the tested workspace.

## 9.3 Integration limitations

The supplied `bb5c622` snapshot does not register M2's `ReservationDemand` or `HoldConsumer` providers in `reservation.install()`. Therefore, dependent Reservation–Charging/Allocation workflows remain blocked in that snapshot and TC-M8-017 must be revalidated after the relevant M2 implementation is merged.

The UI implementation in the supplied snapshot still reads from `ui.sample_data`; it cannot be treated as an end-to-end Core-integrated interface. The seven M8 integration tests also do not prove that every business workflow across Reservation, Charging, Allocation, Monitoring and Simulation works end to end.

## 9.4 Non-functional validation

A D-024 sequential measurement run was performed on Python 3.12.10 against DS-STD, with 100 samples per operation. The raw evidence is `docs/testing/evidence/nfr02-03-python312-rerun.json`.

- **NFR-02:** four read endpoints returned 100/100 successful HTTP 200 responses. p95 values ranged from 9.067 ms to 39.059 ms; maximum values ranged from 13.263 ms to 94.486 ms. All four met p95 ≤500 ms and max ≤2,000 ms.
- **NFR-03:** `POST /charging/requests/immediate` returned 100/100 successful HTTP 200 responses, with p95 33.610 ms and zero write errors; it met p95 ≤1,000 ms.

NFR-02 and NFR-03 are therefore **Pass for the measured endpoints/operation only**. These local TestClient/in-memory SQLite measurements do not establish production performance or prove that every system endpoint meets the targets.

NFR-01, NFR-04, NFR-05, NFR-14 and the remaining system-level NFR evidence are not complete. NFR-14 specifically requires an independent member to perform the fresh-clone check.

## 9.5 Coverage and traceability

The full pytest suite passed as recorded above, but this does not replace the NFR-24 coverage thresholds. Current CI coverage artifacts still need to be checked against Core ≥70% and Reservation, Charging, Allocation, Monitoring and Simulation ≥60%.

FR/BR/UC traceability remains partial. Module owners must confirm their requirement-to-test mappings, and M8 must complete the NFR-26 duplicate/orphan audit before claiming complete traceability.

## 9.6 Defect summary

The existing defect log records seven earlier defects (one High and six Low), all marked Closed after PR #39. M2 and M5 still need their module owners to confirm their entries. The latest integration, focused regression and full repository runs reported no failing tests. The initial TC-M8-016 test-harness `AttributeError` was resolved by correcting the route-inspection assertion; it is not recorded as an application defect.

## 9.7 Overall assessment

M8 has completed the recorded integration and regression runs in the local workspace: 7 integration tests passed, 66 focused tests passed, and the full repository suite completed with 1,400 passed and 1 skipped. NFR-02 and NFR-03 passed for their measured scope on Python 3.12.10.

This is not a final quality sign-off. Independent NFR-14 fresh-clone verification, remaining NFR measurements, current CI coverage confirmation, complete FR/BR/UC traceability, confirmation of M2/M5 defect-log entries, and post-merge integration validation remain open.
