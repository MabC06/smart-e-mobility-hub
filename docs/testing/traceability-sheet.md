# ID Traceability Sheet

> **Owner:** M8 - Testing, QA & Report Integration Lead
> **Phase:** Phase 3
> **Status:** Updated partial baseline (v0.2)
> **Last updated:** 2026-11-20
> **Related design:** [`IoT Simulator Design`](../design/simulation/iot-sim-design.md)

## Purpose

This sheet is the single working index for requirement-to-test traceability. It will be updated as the team locks FR/BR/UC definitions and creates standardized test cases. `Planned` means the requirement is known but the final test case has not yet been assigned.

### Traceability rule

`FR / NFR / BR / UC → TC → execution result → defect (if any)`

Per NFR-26, every FR, BR, and UC must have at least one test case and there must be no orphan IDs at submission time.

## 1. Functional Requirements

| ID | Type | Primary owner | Status | Test Case ID(s) | Notes |
|---|---|---|---|---|---|
| FR-01 | Functional requirement | M1 | Partial | TC-M7-001, TC-M7-002, TC-M7-003, TC-M8-019 | Core Hub read and UI prototype coverage; remaining Core behavior needs module-owner mapping |
| FR-02 | Functional requirement | M2 | Planned | — | To be linked after module requirement tables are finalized |
| FR-03 | Functional requirement | M2 | Partial | TC-M2-001..TC-M2-023 | Reservation booking/lifecycle tests; FR sub-requirement granularity still needs owner confirmation |
| FR-04 | Functional requirement | M2 | Partial | TC-M2-001..TC-M2-023 | Trip/pickup/return behavior appears in M2 test mapping; FR sub-requirement granularity still needs owner confirmation |
| FR-05 | Functional requirement | M2 | Planned | — | To be linked after module requirement tables are finalized |
| FR-06 | Functional requirement | M3 | Planned | — | To be linked after module requirement tables are finalized |
| FR-07 | Functional requirement | M2/M3 | Planned | — | To be linked after module requirement tables are finalized |
| FR-08 | Functional requirement | M5 | Partial | TC-M7-001, TC-M7-002, TC-M7-006, TC-M7-009 | UI prototype and authenticated module-view coverage; incident behavior needs M5 mapping |
| FR-09 | Functional requirement | M5 | Planned | — | To be linked after module requirement tables are finalized |
| FR-10 | Functional requirement | M4 | Partial | TC-M7-007, TC-M7-009, TC-M8-022 | Allocation UI prototype and alternative-Hub provider route; remaining M4 cases need owner mapping |
| FR-11 | Functional requirement | M3/M4 | Planned | — | To be linked after module requirement tables are finalized |
| FR-12 | Functional requirement | M6 | Planned | — | To be linked after module requirement tables are finalized |

## 2. Non-Functional Requirements

| ID | Requirement (short form) | Related FR / Reference | Priority | Status | Test Case ID(s) |
|---|---|---|---|---|---|
| NFR-01 | After `core` accepts a state update, subsequent reads return the new state; the UI shows it shortly after. | FR-01, FR-08 | M | Planned | — |
| NFR-02 | Read operations meet the p95/max targets over ≥100 sequential requests per endpoint (D-024). | FR-01, FR-02, FR-08 | M | Pass (4 measured endpoints; system-wide coverage remains partial) | TC-M8-023 |
| NFR-03 | Write operations meet the p95 target over ≥100 sequential operations on DS-STD (D-024). | FR-03 to FR-07 | M | Pass (1 measured operation; system-wide coverage remains partial) | TC-M8-024 |
| NFR-04 | Allocation and scheduling computations finish in interactive time. | FR-10, FR-11 | M | Planned | — |
| NFR-05 | A What-if scenario completes in acceptable time. | FR-12 | M | Planned | — |
| NFR-06 | No double allocation of a vehicle, parking space or charging slot. | BR-M1-01 | M | Planned | — |
| NFR-07 | Capacity and uniqueness invariants always hold. | BR-M1-02, BR-M1-03 | M | Planned | — |
| NFR-08 | Only transitions allowed by the state machines are executed. | BR-M1-03 | M | Planned | — |
| NFR-09 | Multi-entity operations are atomic. | FR-03, FR-04, FR-05 | M | Planned | — |
| NFR-10 | The system tolerates faulty input and equipment failures. | FR-09 | M | Planned | — |
| NFR-11 | **Withdrawn.** Stable under continuous operation. | FR-08 | Withdrawn | Withdrawn | — |
| NFR-12 | What-if Simulation never changes real operational state. | FR-12 | M | Planned | — |
| NFR-13 | Results are deterministic. | FR-12; CONTRIBUTING 9.8, 9.13 | M | Planned | — |
| NFR-14 | Reproducible from a clean clone. | All | M | Not run | Independent fresh-clone check required |
| NFR-15 | Handles growth of the network. | FR-01, FR-08 | M | Planned | — |
| NFR-16 | Authentication and role-based access (A-06). | FR-08 to FR-12 | M | Partial | TC-M8-019, TC-M8-020, TC-M8-021; module security tests |
| NFR-17 | Credentials and secrets are protected. | CONTRIBUTING 11 | M | Planned | — |
| NFR-18 | External input is validated. | All | M | Planned | — |
| NFR-19 | **Withdrawn.** Students can reserve a vehicle easily. | FR-02, FR-03 | Withdrawn | Withdrawn | — |
| NFR-20 | Operators see critical status at a glance. | FR-08, FR-09 | M | Planned | — |
| NFR-21 | Rejections are understandable. | FR-03, FR-05, FR-06 | M | Planned | — |
| NFR-22 | Modules are decoupled. | CONTRIBUTING 9.2 | M | Partial | TC-M8-017; `tests/core/test_import_boundaries.py` |
| NFR-23 | **Withdrawn.** Code quality is enforced. | CONTRIBUTING 9.10, 9.12 | Withdrawn | Withdrawn | — |
| NFR-24 | Business logic is well tested. | CONTRIBUTING 6, 10 | M | Planned | — |
| NFR-25 | State changes are auditable. | FR-09 | M | Planned | — |
| NFR-26 | Requirements are traceable. | CONTRIBUTING 5 | M | Partial | Traceability audit still open |
| NFR-27 | **Withdrawn.** Runs on the team's machines. | NFR-14 | Withdrawn | Withdrawn | — |

## 3. Business Rules

This is a partial extraction from the module requirements documents. The row below is linked to an implemented API-level integration case; remaining BR IDs and module-owned test IDs still require owner-by-owner reconciliation before NFR-26 sign-off.

| ID | Module | Rule | Related FR / UC | Status | Test Case ID(s) |
|---|---|---|---|---|---|
| BR-M4-10 | M4 | If nothing is available, refuse with a reason (`NO_VEHICLE`, `NO_PARKING`, `NO_CHARGER`, `ALL_HUBS_FULL`) and suggest other Hubs if any | FR-10.6 | Partial | TC-M8-022 |

## 4. Use Cases

This is a partial extraction from the committed module requirements and use-case documents. Remaining use cases still require module-owner test-case mapping before NFR-26 sign-off.

| ID | Use Case | Actor | Related FR | Status | Test Case ID(s) |
|---|---|---|---|---|---|
| UC-M4-05 | Suggest alternative Hubs | Student (via M2), System | FR-10.6 | Partial | TC-M8-022 |

## 5. Test Cases

Standardized test cases will be created in `docs/testing/test-cases/` after the FR/BR/UC baseline is locked.

| TC ID | Test Case | Technique | Linked IDs | Status |
|---|---|---|---|---|
| TC-M8-001 | Build DS-STD totals | Data sanity / BVA | FR-01, NFR-07 | Pass |
| TC-M8-002 | Verify rental battery bands | EP / data sanity | NFR-13 | Pass |
| TC-M8-003 | Verify rental vehicle types | EP / data sanity | NFR-13 | Pass |
| TC-M8-004 | Repeat dataset generation with same seed | Determinism | NFR-13 | Pass |
| TC-M8-005 | Different seed preserves shape but changes values | Metamorphic | NFR-13 | Pass |
| TC-M8-006 | Reject negative seed | EP | NFR-18 | Pass |
| TC-M8-007 | Repeat event generation with same inputs | Determinism | NFR-13 | Pass |
| TC-M8-008 | Ensure event IDs are unique and timestamps ordered | Structural / BVA | NFR-13 | Pass |
| TC-M8-009 | Generate battery drain for every fleet vehicle | EP | FR-01, NFR-07 | Pass |
| TC-M8-010 | Generate paired private-EV occupancy events | State transition | FR-01, NFR-07 | Pass |
| TC-M8-011 | Reject naive event start time | EP | NFR-18 | Pass |
| TC-M8-012 | Seed Core from DS-STD | Integration | FR-01, NFR-07 | Pass |
| TC-M8-013 | Apply minimal feed | Integration / state transition | FR-01, FR-09, NFR-10 | Pass |
| TC-M8-014 | Check Core invariants after feed | Invariant check | NFR-07 | Pass |
| TC-M8-015 | Refuse to seed a non-empty store | Negative / boundary | NFR-10, NFR-18 | Pass |
| TC-M8-016 | Build application through the composition root | Integration / composition | D-013, Core API spec §8 | Pass |
| TC-M8-017 | Verify D-020 provider registration and expected missing M2 ports | Interface contract | D-020, NFR-22 | Pass |
| TC-M8-018 | Call ChargingDemand through Core provider registry | Integration / contract | D-020 | Pass |
| TC-M8-019 | Authenticate Core Hub read API | API integration / EP | FR-01, NFR-16 | Pass |
| TC-M8-020 | Reject student access to operator-only module endpoints | Security / role partition | NFR-16, D-023 | Pass |
| TC-M8-021 | Allow operator read access to Charging, Allocation and Monitoring | Security / integration | NFR-16, D-023 | Pass |
| TC-M8-022 | Call M4 alternative-Hub provider through API | Integration / provider contract | FR-10, UC-M4-05, BR-M4-10, D-020 | Pass |
| TC-M8-023 | Measure 100 sequential read requests per endpoint on DS-STD | Performance / sequential timing | NFR-02, D-024 | Pass (4 endpoints; Python 3.12.10) |
| TC-M8-024 | Measure 100 sequential write operations on DS-STD | Performance / sequential timing | NFR-03, D-024 | Pass (1 operation; Python 3.12.10) |

## 6. Coverage / Orphan Check

| Check | Current status | Target |
|---|---|---|
| FR coverage | Partial | Every FR has ≥1 TC |
| BR coverage | Partial / owner confirmation needed | Every BR has ≥1 TC |
| UC coverage | Pending UC definitions | Every UC has ≥1 TC |
| NFR coverage | Partial; NFR-02/03 pass only for measured scope; other NFRs remain open | Applicable NFRs have evidence/tests |
| Orphan IDs | Not yet verified | 0 orphan FR/BR/UC |

## 7. Update Protocol

1. Module owners add or update FR, BR, or UC definitions in their respective module documents. M8 updates this sheet to reflect the changes.
2. M8 collects TC IDs from test files and tables, derives the BR → UC and requirement → TC relationships from the `Trace:` and `Verifies:` entries, and checks for duplicate and orphan IDs.
3. Test execution records Pass / Fail / Blocked and evidence.
4. Failed tests link to the defect log.
5. Before code freeze and final submission, M8 performs an orphan-ID check.
