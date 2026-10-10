# ID Traceability Sheet

> **Owner:** M8 - Testing, QA & Report Integration Lead
> **Phase:** Phase 0 - Requirements Analysis
> **Status:** Initial baseline (v0.1)
> **Last updated:** 2026-10-09

## Purpose

This sheet is the single working index for requirement-to-test traceability. It will be updated as the team locks FR/BR/UC definitions and creates standardized test cases. `Planned` means the requirement is known but the final test case has not yet been assigned.

### Traceability rule

`FR / NFR / BR / UC → TC → execution result → defect (if any)`

Per NFR-26, every FR, BR, and UC must have at least one test case and there must be no orphan IDs at submission time.

## 1. Functional Requirements

| ID | Type | Primary owner | Status | Test Case ID(s) | Notes |
|---|---|---|---|---|---|
| FR-01 | Functional requirement | M1 | Planned | — | To be linked after module requirement tables are finalized |
| FR-02 | Functional requirement | M2 | Planned | — | To be linked after module requirement tables are finalized |
| FR-03 | Functional requirement | M2 | Planned | — | To be linked after module requirement tables are finalized |
| FR-04 | Functional requirement | M2 | Planned | — | To be linked after module requirement tables are finalized |
| FR-05 | Functional requirement | M2 | Planned | — | To be linked after module requirement tables are finalized |
| FR-06 | Functional requirement | M3 | Planned | — | To be linked after module requirement tables are finalized |
| FR-07 | Functional requirement | M2/M3 | Planned | — | To be linked after module requirement tables are finalized |
| FR-08 | Functional requirement | M5 | Planned | — | To be linked after module requirement tables are finalized |
| FR-09 | Functional requirement | M5 | Planned | — | To be linked after module requirement tables are finalized |
| FR-10 | Functional requirement | M4 | Planned | — | To be linked after module requirement tables are finalized |
| FR-11 | Functional requirement | M3/M4 | Planned | — | To be linked after module requirement tables are finalized |
| FR-12 | Functional requirement | M6 | Planned | — | To be linked after module requirement tables are finalized |

## 2. Non-Functional Requirements

| ID | Requirement (short form) | Related FR / Reference | Priority | Status | Test Case ID(s) |
|---|---|---|---|---|---|
| NFR-01 | After `core` accepts a state update, subsequent reads return the new state; the UI shows it shortly after. | FR-01, FR-08 | M | Planned | — |
| NFR-02 | Read operations (view Hubs, search vehicles, dashboard queries) respond quickly under load. | FR-01, FR-02, FR-08 | M | Planned | — |
| NFR-03 | Write operations (reserve, pick up, return, parking reservation, charging request) respond quickly. | FR-03 to FR-07 | M | Planned | — |
| NFR-04 | Allocation and scheduling computations finish in interactive time. | FR-10, FR-11 | S | Planned | — |
| NFR-05 | A What-if scenario completes in acceptable time without hurting normal operation. | FR-12 | S | Planned | — |
| NFR-06 | No double allocation of a vehicle, parking space or charging slot. | FR-03, FR-05, FR-06; BR (double booking) | M | Planned | — |
| NFR-07 | Capacity and uniqueness invariants always hold. | FR-01 to FR-11 | M | Planned | — |
| NFR-08 | Only transitions allowed by the state machines are executed. | All state machines | M | Planned | — |
| NFR-09 | Multi-entity operations are atomic. | FR-03, FR-04, FR-05 | M | Planned | — |
| NFR-10 | The system tolerates faulty input and equipment failures. | FR-09 | M | Planned | — |
| NFR-11 | Stable under continuous operation. | FR-08 | S | Planned | — |
| NFR-12 | What-if Simulation never changes real operational state. | FR-12 | M | Planned | — |
| NFR-13 | Results are deterministic. | FR-12; CONTRIBUTING 9.8, 9.13 | M | Planned | — |
| NFR-14 | Reproducible from a clean clone. | All | M | Planned | — |
| NFR-15 | Handles growth of the network. | FR-01, FR-08 | S | Planned | — |
| NFR-16 | Authentication and role-based access (A-06). | FR-08 to FR-12 | M | Planned | — |
| NFR-17 | Credentials and secrets are protected. | CONTRIBUTING 11 | M | Planned | — |
| NFR-18 | External input is validated. | All | M | Planned | — |
| NFR-19 | Students can reserve a vehicle easily. | FR-02, FR-03 | S | Planned | — |
| NFR-20 | Operators see critical status at a glance. | FR-08, FR-09 | S | Planned | — |
| NFR-21 | Rejections are understandable. | FR-03, FR-05, FR-06 | S | Planned | — |
| NFR-22 | Modules are decoupled. | CONTRIBUTING 9.2 | M | Planned | — |
| NFR-23 | Code quality is enforced. | CONTRIBUTING 9.10, 9.12 | S | Planned | — |
| NFR-24 | Business logic is well tested. | CONTRIBUTING 6, 10 | S | Planned | — |
| NFR-25 | State changes are auditable. | FR-09 | S | Planned | — |
| NFR-26 | Requirements are traceable. | CONTRIBUTING 5 | M | Planned | — |
| NFR-27 | Runs on the team's machines. | NFR-14 | S | Planned | — |

## 3. Business Rules

Business-rule IDs are not yet present in the current requirements directory. Module owners are expected to add their draft BRs during Phase 0. M8 will populate this section once the BR tables are committed.

| ID | Module | Rule | Related FR / UC | Status | Test Case ID(s) |
|---|---|---|---|---|---|
| BR-xx | TBD | Pending module requirements | TBD | Pending | — |

## 4. Use Cases

Use-case tables are being produced by M2–M7 during Phase 0. M8 will populate this section from the consolidated use-case definitions after Requirements v1 is locked.

| ID | Use Case | Actor | Related FR | Status | Test Case ID(s) |
|---|---|---|---|---|---|
| UC-xx | Pending consolidated use-case tables | TBD | TBD | Pending | — |

## 5. Test Cases

Standardized test cases will be created in `docs/testing/test-cases/` after the FR/BR/UC baseline is locked.

| TC ID | Test Case | Technique | Linked IDs | Status |
|---|---|---|---|---|
| TC-xxx | Pending test-case set | TBD | TBD | Planned |

## 6. Coverage / Orphan Check

| Check | Current status | Target |
|---|---|---|
| FR coverage | Planned | Every FR has ≥1 TC |
| BR coverage | Pending BR definitions | Every BR has ≥1 TC |
| UC coverage | Pending UC definitions | Every UC has ≥1 TC |
| NFR coverage | Planned | Applicable NFRs have evidence/tests |
| Orphan IDs | Not yet checkable | 0 orphan FR/BR/UC |

## 7. Update Protocol

1. Module owner adds/updates FR, BR, or UC → M8 updates this sheet.
2. M8 assigns standardized `TC-xxx` IDs when test cases are created.
3. Test execution records Pass / Fail / Blocked and evidence.
4. Failed tests link to the defect log.
5. Before code freeze and final submission, M8 performs an orphan-ID check.
