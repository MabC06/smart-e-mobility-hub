# 09. Testing and Validation

> **Status:** Draft for integration — 2026-11-23  
> **Owner:** M8 — Testing, QA & Report Integration Lead  
> **Baseline:** testing branch `01d68e764876a4c22fad53145843d164339784f9` (`develop` plus approved, not-yet-merged PRs #45, #47–#52). Details: `docs/testing/test-execution-report.md`, `docs/testing/nfr-measurements.md`.

## 9.1 Testing approach

Testing follows the layered strategy in `docs/testing/test-plan-final.md`: module owners write unit and component tests; M8 coordinates integration verification, traceability, NFR evidence and reporting. Test cases use the `TC-M<n>-###` convention and cite the requirements they verify (172 test cases are documented).

Integration tests build the application through `src/main.py::build_app` with an isolated SQL repository. They check application composition, D-020 provider registration, Core provider invocation, authenticated Core reads, role-based access to Charging, Allocation and Monitoring endpoints, and M4's alternative-Hub route.

## 9.2 Regression results

On 2026-11-23, on Python 3.12.10 (Windows, pytest 9.2.0), clean working tree:

| Check | Result |
|---|---|
| ruff check / ruff format --check / mypy | Clean (202 files formatted; 47 source files) |
| Full suite (`pytest -q`) | 1,501 passed, 1 skipped, 1 warning |
| M8 integration (7), focused regression (66), NFR-22 import boundaries (25), NFR-06 concurrency (42) | All passed |
| Per module: reservation 159, charging 45, allocation 93, monitoring 40, simulation 9, UI 75 | All passed |

The skipped test (`tests/core/test_module_entities.py:316`) applies only to the SQL repository ("only the database has foreign keys") and is not counted as passed. The single warning is a Starlette deprecation notice about `httpx` in `starlette.testclient`; it did not fail any run. An earlier TC-M8-016 failure (route inspection in the test, not the application) was fixed in the test.

## 9.3 Integration limitations

- M2 registers neither `ReservationDemand` nor `HoldConsumer`; the M2 pull request #52 changes documents only. Allocation planning therefore returns 503 and workflows that need reservation demand are blocked. TC-M8-017 asserts this absence and must be updated when M2 registers the providers.
- The UI reads sample data for several screens (DEV-10 to DEV-12), so it is not shown to be integrated with Core.
- M6 implements only the demand-surge scenario SC-01 (DEV-08).
- No end-to-end journey (rental → dispatch → charging → monitoring) has been executed.

## 9.4 Non-functional validation

Measurements follow D-024: sequential requests, in-process client, DS-STD (seed 2026; 10 Hubs, 400 spaces, 61 charging points, 350 vehicles, 1,005 users). They are TestClient and in-memory SQLite timings and are not production guarantees.

| NFR | Target | Result | Verdict |
|---|---|---|---|
| NFR-01 | Read after write, p95 ≤ 1 s | 100/100 visible; p95 3.97–5.23 ms | Pass (API) |
| NFR-02 | Reads p95 ≤ 500 ms, max ≤ 2 s | 4 endpoints: p95 2.84–12.91 ms; max ≤ 41.6 ms | Pass (4 endpoints) |
| NFR-03 | Writes p95 ≤ 1 s | `POST /charging/requests/immediate`: p95 10.6 ms | Pass (1 operation) |
| NFR-04 charging | ≤ 3 s per Hub | 15 queued per Hub: worst 1.50 s. 50 queued on one Hub: 2.64–3.83 s | Pass at DS-STD load; exceeds at depth 50 |
| NFR-04 allocation | ≤ 5 s | 503, no M2 provider | Blocked |
| NFR-05 | Each scenario ≤ 30 s | SC-01: p95 113–164 ms; SC-02–05 not implemented | Partial |
| NFR-12, NFR-13 | State unchanged; same seed same output | Both hold for SC-01 in 4 runs | Pass (SC-01) |
| NFR-14 | Fresh clone ≤ 15 min, ≤ 5 commands | Not performed | Open |

The NFR-04 charging time rises faster than linearly with queue depth (about 4 ms per queued request at depth 5, 53–77 ms at depth 50). This is recorded as proposed defect DEF-M3-007 and, if not fixed, goes into section 4.4 as a limitation. No concurrent-load figure exists (DEV-01).

## 9.5 Coverage and traceability

Line coverage meets NFR-24 for every named module (local run): core 98.8 % (≥ 70 %); reservation 96.3 %, charging 88.2 %, allocation 91.5 %, monitoring 87.3 %, simulation 92.4 % (each ≥ 60 %). The CI coverage artifact has not been checked.

Traceability (`docs/testing/traceability-sheet.md`) is incomplete: 11 of 12 FR, 25 of 34 BR and 21 of 38 UC have a test case. Uncovered: FR-05 (parking hold, not implemented by M2); nine BR (parking and overdue rules of M2, four M4 rules declared unused, BR-M1-03, BR-M6-03); 17 UC (parking and search flows of M2, UC-M5-01/02, UC-M6-01, UC-M7-01 to 10). Module owners must confirm or add tests; NFR-26 is not yet met.

## 9.6 Defect summary

22 defects are recorded (0 Critical, 6 High, 5 Medium, 11 Low); all are Closed. One further entry, DEF-M3-007 (Medium, NFR-04 at depth 50), is proposed and awaits M3. No test failed in the runs above.

## 9.7 Overall assessment

On the testing branch all executed tests pass, static checks are clean, coverage exceeds the thresholds, and NFR-01, 02, 03 and 12/13 (SC-01) are met within their measured scope; NFR-04 for charging is met at the standard load.

This is a conditional sign-off, not a final one. Open: NFR-14 fresh-clone check; NFR-04 allocation (needs M2 providers); NFR-05 for SC-02–SC-05; NFR-26 traceability gaps; confirmation of DEF-M3-007; a repeat run on `develop` after the PRs merge; and the CI coverage artifact.
