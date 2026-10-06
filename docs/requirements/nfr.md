# Non-Functional Requirements (NFR) — v1

> **Status:** Draft v1 · **Owner:** M1 · **Date:** 2026-10-05 · Phase 0 deliverable (due 2026-10-10)
> All targets are **proposals** to be agreed by the team and re-validated by measurement in Sprint 2 (2026-11-07 to 2026-11-13), tied to the reference dataset DS-STD (A-11).
> Each requirement states a measurable target and how it is verified, so that M8 can derive test cases (`TC-xxx`) from it.

## 1. Conventions

- **ID:** `NFR-xx`. IDs are reused in commits, PRs and tests (CONTRIBUTING section 5).
- **p95:** 95th-percentile response time measured at the API boundary.
- **DS-STD (reference dataset, A-11):** 10 Hubs, 400 parking spaces, 61 charging points, 250 rental vehicles, 100 registered private EVs, 1,000 student accounts. Performance targets assume 100 concurrent sessions. Full specification: `docs/requirements/reference-dataset.md`.
- **DS-STRESS:** 2x DS-STD.
- **Priority:** M = must (core to the rubric or to correctness), S = should, C = could.

## 2. Performance

| ID | Requirement | Target | Verification | Related | Prio |
|---|---|---|---|---|---|
| NFR-01 | After `core` accepts a state update, subsequent reads return the new state; the UI shows it shortly after. | API read reflects the update within 1 s (p95). UI shows it within 5 s. | Integration test with timestamps; UI polling/refresh interval check. | FR-01, FR-08 | M |
| NFR-02 | Read operations (view Hubs, search vehicles, dashboard queries) respond quickly under load. | p95 ≤ 500 ms and max ≤ 2 s on DS-STD with 100 concurrent sessions. | Load script (e.g. concurrent requests against seeded data). | FR-01, FR-02, FR-08 | M |
| NFR-03 | Write operations (reserve, pick up, return, parking reservation, charging request) respond quickly. | p95 ≤ 1 s on DS-STD with 100 concurrent sessions. | Load script. | FR-03 to FR-07 | M |
| NFR-04 | Allocation and scheduling computations finish in interactive time. | Charging schedule for one Hub ≤ 3 s. Network-wide redistribution recommendation ≤ 5 s (DS-STD). | Timed unit/integration tests. | FR-10, FR-11 | S |
| NFR-05 | A What-if scenario completes in acceptable time without hurting normal operation. | Each of the 5 standard scenarios ≤ 30 s on DS-STD. While one runs, NFR-02 p95 grows by at most 20%. | Timed scenario tests; load script during a run. | FR-12 | S |

## 3. Data consistency and reliability

| ID | Requirement | Target | Verification | Related | Prio |
|---|---|---|---|---|---|
| NFR-06 | No double allocation of a vehicle, parking space or charging slot. | With 20 to 50 simultaneous requests for the same resource, exactly one succeeds and the others get a conflict error. 0 violations over 100 repeated runs. | Concurrency test. | FR-03, FR-05, FR-06; BR (double booking) | M |
| NFR-07 | Capacity and uniqueness invariants always hold. | Occupied parking ≤ capacity; charging points per Hub ≤ parking spaces, and a vehicle being charged occupies exactly one parking space, its bay (D-007); at most one active charging session per charging point (A-04); each vehicle in exactly one state. 0 violations, checked after every integration test and every simulation run. | Invariant-check helper called by tests. | FR-01 to FR-11 | M |
| NFR-08 | Only transitions allowed by the state machines are executed. | 100% of disallowed transitions are rejected with an explicit error code and leave the state unchanged. Every valid transition and every invalid (state, event) pair of the Vehicle state machine has at least one test. | State-transition testing. | All state machines | M |
| NFR-09 | Multi-entity operations are atomic. | Pick-up (vehicle state + reservation state + parking space release) either fully applies or fully rolls back. 0 partial states after fault injection at each step. | Fault-injection test. | FR-03, FR-04, FR-05 | M |
| NFR-10 | The system tolerates faulty input and equipment failures. | A malformed sensor event is rejected and logged with no state change and no crash. A charging-point failure event interrupts its sessions and creates an incident within 5 s, while other Hubs keep working. | Invalid-event tests; failure-injection via `iot_sim`. | FR-09 | M |
| NFR-11 | Stable under continuous operation. | 60 minutes of continuous run at peak-hour event rate: no crash, no unhandled exception, and NFR-02 still met at the end. | Soak test with `iot_sim`. | FR-08 | S |

## 4. Isolation and reproducibility

| ID | Requirement | Target | Verification | Related | Prio |
|---|---|---|---|---|---|
| NFR-12 | What-if Simulation never changes real operational state. | For all 5 standard scenarios, a hash of the operational state is identical before and after; 0 writes reach the operational store. | Test with state hash and a write-guard on the operational repository. | FR-12 | M |
| NFR-13 | Results are deterministic. | Same seed + same ordered events ⇒ identical state hash and identical simulation output in two runs. Outputs are sorted before being written. | Repeat-run comparison test. | FR-12; CONTRIBUTING 9.8, 9.13 | M |
| NFR-14 | Reproducible from a clean clone. | Install, run and test in ≤ 15 minutes using ≤ 5 documented commands. Tests run with one command. | Fresh-clone check by a member who did not write the setup docs. | All | M |

## 5. Scalability

| ID | Requirement | Target | Verification | Related | Prio |
|---|---|---|---|---|---|
| NFR-15 | Handles growth of the network. | DS-STRESS (2x DS-STD) works correctly, with NFR-02 and NFR-03 relaxed to 2x. Adding a Hub, parking space, charging point or vehicle needs only data/config, no code change. | Load test on DS-STRESS; add-a-Hub test. | FR-01, FR-08 | S |

## 6. Security

| ID | Requirement | Target | Verification | Related | Prio |
|---|---|---|---|---|---|
| NFR-16 | Authentication and role-based access (A-06). | Every API except login needs authentication. Operator-only operations return 403 for the student role. 100% of endpoints have an authorization test. | Authorization test per endpoint. | FR-08 to FR-12 | M |
| NFR-17 | Credentials and secrets are protected. | Passwords stored salted and hashed. 0 secrets in the repository (secret scanning on, `.env` ignored). | Repo scan; code review. | CONTRIBUTING 11 | M |
| NFR-18 | External input is validated. | Every input is checked for type, range and allowed values. Invalid input returns a 4xx error with a clear message, never a 5xx. | Invalid-input tests derived by equivalence partitioning and boundary-value analysis. | All | M |

## 7. Usability

| ID | Requirement | Target | Verification | Related | Prio |
|---|---|---|---|---|---|
| NFR-19 | Students can reserve a vehicle easily. | A first-time user completes "find and reserve a vehicle" in ≤ 4 screens and ≤ 60 s. At least 80% of at least 5 testers succeed without help. | Usability walkthrough with peers. | FR-02, FR-03 | S |
| NFR-20 | Operators see critical status at a glance. | The dashboard main view shows Hubs at or above the near-capacity threshold (configurable, default to be set by M5) and active incidents without extra navigation. | Review against wireframes and the running UI. | FR-08, FR-09 | S |
| NFR-21 | Rejections are understandable. | Every rejected operation shows the cause and, where possible, an alternative (e.g. another Hub). No raw stack traces are shown. | UI review; invalid-input tests check message content. | FR-03, FR-05, FR-06 | S |

## 8. Maintainability and traceability

| ID | Requirement | Target | Verification | Related | Prio |
|---|---|---|---|---|---|
| NFR-22 | Modules are decoupled. | Modules interact only through the `core` interface. A static import check finds 0 imports of another module's internals. | Automated import check (CI once available). | CONTRIBUTING 9.2 | M |
| NFR-23 | Code quality is enforced. | Formatter, linter and type checker report 0 errors. Public functions are typed and documented. Dependency versions are pinned. | CI/pre-commit checks. | CONTRIBUTING 9.10, 9.12 | S |
| NFR-24 | Business logic is well tested. | Line coverage ≥ 80% for `core`; ≥ 70% for `reservation`, `charging`, `allocation`, `monitoring`, `simulation`. M8 signs off. | Coverage report. | CONTRIBUTING 6, 10 | S |
| NFR-25 | State changes are auditable. | Every state transition is logged with UTC timestamp, entity, previous and new state, trigger, and source/actor. Operators can query the log of one entity. | Log inspection in integration tests. | FR-09 | S |
| NFR-26 | Requirements are traceable. | Every FR, BR and UC has at least one TC; every PR and commit cites an ID where applicable. 0 orphan IDs in the traceability sheet. | Traceability sheet maintained by M8. | CONTRIBUTING 5 | M |

## 9. Portability

| ID | Requirement | Target | Verification | Related | Prio |
|---|---|---|---|---|---|
| NFR-27 | Runs on the team's machines. | Same setup and run commands work on Windows 10/11 and Ubuntu 22.04 or later. | Fresh-clone check on both; CI on Linux. | NFR-14 | S |

## 10. Open points for team agreement

1. Are DS-STD (A-11) and the p95 targets realistic for the chosen stack? To be measured in Sprint 2.
2. Near-capacity threshold and low-battery threshold values (M5 and M3 propose; named config in `.env.example`).
3. Coverage thresholds in NFR-24: confirm with M8.
4. Whether NFR-19 usability testing is feasible within the schedule, otherwise downgrade to a walkthrough review.

## 11. Mapping to the rubric (Requirements, 2.3)

The list covers performance (§2), reliability and data consistency (§3), isolation/reproducibility (§4), scalability (§5), security (§6), usability (§7), maintainability and testability (§8), and portability (§9), as suggested by the report guideline.
