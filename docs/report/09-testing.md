# 5. Testing and Validation

> **Status:** Final for the report — 2026-11-26 (first round 2026-11-23, superseded)  
> **Owner:** M8 — Testing, QA & Report Integration Lead (rerun on `develop` by M1)  
> **Baseline:** `develop` at `0056f23` (every PR up to #63 merged); NFR measurements on `267919e` (`0056f23` plus fixes to the measurement scripts only). Details: `docs/testing/test-execution-report.md`, `docs/testing/nfr-measurements.md`.

## 5.1 Testing approach

Testing follows the layered strategy in `docs/testing/test-plan-final.md`: module owners write unit and component tests; M8 coordinates integration verification, traceability, NFR evidence and reporting. Test cases use the `TC-M<n>-###` convention and cite the requirements they verify (215 test cases are documented).

Integration tests build the application through `src/main.py::build_app` with an isolated SQL repository. They check application composition, D-020 provider registration, Core provider invocation, authenticated Core reads, role-based access to Charging, Allocation and Monitoring endpoints, and M4's alternative-Hub route. The UI tests drive the real modules through the pages, so they also act as end-to-end journeys: rental with search, return-space hold, pick-up and return; private parking; charging change and cancel; vehicle, point and Hub commands; charging sessions; and a simulation recommendation sent to dispatch.

## 5.2 Regression results

On 2026-11-26, on `develop` at `0056f23` (Windows, Python 3.12.10, pytest 9.2.0):

| Check | Result |
|---|---|
| ruff check / ruff format --check / mypy | Clean (217 files formatted; 50 source files) |
| CI on `develop` (GitHub Actions run `45666388041`) | Success |
| Full suite (`pytest -q`) | 1,560 passed, 1 skipped, 1 warning |
| M8 integration (7), NFR-22 import boundaries (25), NFR-06 concurrency (42), simulator (14) | All passed |
| Per module: reservation 180, charging 48, allocation 95, monitoring 40, simulation 18, UI 95 | All passed |

The skipped test (`tests/core/test_module_entities.py:316`) applies only to the SQL repository ("only the database has foreign keys") and is not counted as passed. The single warning is a Starlette deprecation notice about `httpx` in `starlette.testclient`; it did not fail any run.

After the last demo review (section 5.6) the suite has 1,566 tests, all passing, with six new test cases (TC-M2-033, TC-M3-040 to TC-M3-042, TC-M7-046, TC-M7-047). The demo was also run by hand on the seeded network (`SEED_ON_START`, `DEMO_PASSWORD`, D-028) for every student and operator screen, at 1366 × 768, 1920 × 1080 and on a phone (D-027).

## 5.3 Integration limitations

- M2 registers `ReservationDemand` but not `HoldConsumer`, and does not ask M4 for an alternative Hub (DEV-16). No other module consumes an M2 hold, so no flow is blocked.
- The parking/charging bundle (BR-M2-12) is not implemented (DEV-15): a private EV books parking and charging separately.
- M6 counts per Hub over the whole horizon instead of stepping through time (DEV-08).
- No figure exists for concurrent users (D-024, DEV-01).

## 5.4 Non-functional validation

Measurements follow D-024: sequential requests, in-process client, DS-STD (seed 2026; 10 Hubs, 400 spaces, 61 charging points, 350 vehicles, 1,005 users). They are TestClient and in-memory SQLite timings and are not production guarantees.

| NFR | Target | Result | Verdict |
|---|---|---|---|
| NFR-01 | Read after write, p95 ≤ 1 s | 100/100 visible; p95 7.2–8.1 ms (3 runs) | Pass (API) |
| NFR-02 | Reads p95 ≤ 500 ms, max ≤ 2 s | 4 endpoints: p95 5.8–20.9 ms; max ≤ 98.9 ms | Pass (4 endpoints) |
| NFR-03 | Writes p95 ≤ 1 s | `POST /charging/requests/immediate`: p95 231 ms (includes binding the Hub's queue) | Pass (1 operation) |
| NFR-04 charging | ≤ 3 s per Hub | 15 queued per Hub: worst 1.75 s. 50 queued on one Hub: 4.19–4.26 s | Pass at DS-STD load; exceeds at depth 50 |
| NFR-04 allocation | ≤ 5 s | With M2's real provider: max 358 ms (3 × 5 runs) | Pass |
| NFR-05 | Each scenario ≤ 30 s | SC-01 to SC-05, 5 runs each: slowest 148 ms | Pass |
| NFR-12, NFR-13 | State unchanged; same seed same output | Both hold for every scenario in 3 rounds | Pass |
| NFR-14 | Fresh clone ≤ 15 min, ≤ 5 commands | 5 commands, 4m34s (2026-11-23, not repeated) | Pass |

The NFR-04 charging time rises faster than linearly with queue depth (about 10 ms per queued request at depth 5, about 84 ms at depth 50). This is defect DEF-M3-007 (Medium, Accepted by the Lead as a known limitation because NFR-04 passes at the DS-STD load); M3 describes it in section 4.4. NFR-03 is slower than in the first round (10.6 ms) because a request now binds its Hub's queue at once (TC-M3-039), still four times under the target.

## 5.5 Coverage and traceability

Line coverage meets NFR-24 for every module: core 98.8 % (≥ 70 %); reservation 92.1 %, charging 89.0 %, allocation 91.7 %, monitoring 87.3 %, simulation 92.7 %, ui 91.9 %, iot_sim 99.0 % (each ≥ 60 %); 94 % for the whole repository. CI checks the thresholds on every push (D-025).

Traceability (`docs/testing/traceability-sheet.md`): all 12 FR, 28 of 34 BR, 36 of 38 UC and 18 of 27 NFR have a test case. Uncovered: BR-M1-03 (no test found), BR-M2-12 (parking/charging bundle, not implemented), four M4 rules declared unused (BR-M4-07/09/11/12) and UC-M5-01/02 (M5 tests cite FR and BR only). Of the nine NFRs without a TC ID, four are withdrawn (NFR-11, 19, 23, 27) and five are verified another way: NFR-14 by the fresh-clone run, NFR-24 by CI, NFR-26 by the sheet itself, NFR-15 and NFR-17 by core tests listed in `nfr-evidence-core.md`.

## 5.6 Defect summary

35 defects are recorded (0 Critical, 7 High, 11 Medium, 17 Low): 34 Closed and 1 Accepted. Six were found by running the demo on the seeded network on 2026-11-25 and 26: due bookings that never expired (DEF-M2-002, High), Trips never marked overdue (DEF-M2-003), charging requests left queued while points were free (DEF-M3-008), a vehicle list that included vehicles M2 refuses (DEF-M7-001), bookings shown without their day (DEF-M7-002) and a stale stylesheet on phones (DEF-M7-003). Each was fixed with a new test. A last review of every demo journey on 2026-11-26 found six more, all fixed: a "charge now" request for an EV away from the Hub that could never start and showed core's raw text (DEF-M3-009, Medium), no way for a student to finish their own charging (DEF-M7-004, Medium), and four unclear messages or defaults (DEF-M2-004, DEF-M3-010, DEF-M7-005, DEF-M7-006). The Accepted one is DEF-M3-007 (Medium, NFR-04 at queue depth 50). No test failed in the runs above.

## 5.7 Overall assessment

On `develop` all tests pass, static checks and CI are clean, coverage exceeds every threshold, and NFR-01 to NFR-05, NFR-12, NFR-13, NFR-14 and NFR-24 are met within their measured scope, with NFR-04 for charging met at the standard load. The remaining limits (section 5.3, DEF-M3-007, the traceability gaps in 5.5) are known and stated in section 4.4. This is the final sign-off for the report and the demo.
