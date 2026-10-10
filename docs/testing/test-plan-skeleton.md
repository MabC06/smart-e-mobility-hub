# Test Plan — Skeleton

> **Owner:** M8 — Testing, QA & Report Integration Lead
> **Phase:** Phase 0 — Requirements Analysis
> **Status:** Skeleton (v0.1)
> **Last updated:** 2026-10-09

This document defines the structure and initial testing strategy for Smart E-Mobility Hub. It is intentionally a skeleton for Phase 0; detailed test cases, test data, environment configuration, and execution results will be completed as the requirements and design are locked.

## 1. Testing Objectives

- Verify that every functional requirement (FR), business rule (BR), and use case (UC) is covered by at least one test case.
- Verify normal, invalid, boundary, conflict, state-transition, failure, simulation, and integration behavior.
- Detect regressions and integration defects between modules.
- Validate measurable non-functional requirements (NFRs) where practical, including performance, consistency, reliability, determinism, security, usability, and code quality.
- Provide traceable evidence for the final Testing and Validation section of the report.

## 2. Testing Scope

### 2.1 In Scope

- Core state management and state-transition behavior.
- Reservation and trip flows.
- Charging requests and scheduling.
- Resource allocation and vehicle dispatching.
- Monitoring and incident handling.
- What-if simulation and coordination recommendations.
- IoT simulated sensor/event feed and its interaction with the core state-update interface.
- Cross-module integration and end-to-end flows.
- Relevant NFR verification defined in `docs/requirements/nfr.md`.

### 2.2 Out of Scope

- Physical vehicle, charging-station, or sensor hardware testing.
- Sophisticated 3D map interfaces.
- Production-scale infrastructure testing beyond the datasets and environments defined by the team.

## 3. Features / Requirements to Be Tested

The primary functional scope is FR-01 through FR-12. Detailed mapping is maintained in [`traceability-sheet.md`](traceability-sheet.md).

| Area | IDs | Primary owner | Test ownership |
|---|---|---|---|
| Core / Hub status | FR-01 | M1 | M1 + M8 integration |
| Reservation / trip | FR-02–05, FR-07 | M2 | M2 + M8 integration |
| Charging / scheduling | FR-06, FR-07, FR-11 | M3 | M3 + M8 integration |
| Allocation / dispatch | FR-10, FR-11 | M4 | M4 + M8 integration |
| Monitoring / incidents | FR-08–09 | M5 | M5 + M8 integration |
| What-if simulation | FR-12 | M6 | M6 + M8 integration |
| UI / data consistency | Cross-cutting | M7 | M7 + M8 review |
| IoT simulator | Cross-cutting | M8 | M8 |

## 4. Testing Levels

1. **Unit testing** — owned by each module owner in `tests/<module>/`.
2. **Integration testing** — owned by M8 in `tests/integration/`.
3. **System / end-to-end testing** — selected cross-module user and operator flows.
4. **Non-functional testing** — targeted verification of measurable NFRs.

## 5. Testing Types / Techniques

Each applicable module should use course techniques and link the resulting test cases to requirement IDs.

- Equivalence Partitioning (EP)
- Boundary Value Analysis (BVA)
- Decision Table Testing
- State-Transition Testing
- Error / invalid-input testing
- Conflict / concurrency testing
- Failure-injection testing
- Integration testing
- Regression testing
- Performance / load / soak testing where required by NFRs
- Usability review for applicable UI requirements
- Determinism / reproducibility checks for simulation and IoT data
- Security / authorization checks where applicable

## 6. Test Environment

Initial environment requirements:

- Development/test machines: Windows 10/11 and Ubuntu 22.04+ compatibility target.
- Clean-clone setup must be reproducible according to NFR-14.
- Final language/framework/database/test framework: **TBD during Phase 1** and recorded in `docs/DECISIONS.md`.
- Test execution must use deterministic seeds where simulated data is involved.

## 7. Test Data

Initial test-data categories:

- Normal valid hub, vehicle, parking, charging-point, reservation, and incident records.
- Boundary/capacity values.
- Invalid and malformed inputs.
- Conflicting reservations / resource requests.
- Valid and invalid state-transition events.
- Charging-point and vehicle failure events.
- Peak-hour demand and occupancy events.
- The five standard What-if scenarios.
- Reproducible IoT event streams generated from a seed.

Detailed seed data and datasets will be finalized after the class diagram, ERD, and Core API are stable.

## 8. Roles and Responsibilities

| Role | Responsibility |
|---|---|
| M8 | Own Test Plan, standardized test cases, traceability, integration tests, test execution report, defect-log consolidation, QA sign-off, IoT simulator, report testing integration. |
| M1–M6 | Own unit tests for their modules and provide implementation/design information needed for integration testing. |
| M7 | Own UI/data-design validation and review M8 IoT simulator output against ERD/class diagram. |
| All members | Apply testing techniques to their own module, record AI usage, fix defects, and provide test evidence. |
| M4 | Primary reviewer for M8 test deliverables. |
| M7 | Reviewer for M8 IoT simulator deliverables. |

## 9. Entry Criteria

A test activity may begin when the required scope is sufficiently stable and:

- Relevant FR/BR/UC IDs are available.
- The required module/API or agreed stub/mock is available.
- Test data and expected results are defined.
- The test environment and dependencies are documented.
- For integration testing, the relevant module interfaces are implemented or frozen enough to test.

## 10. Exit Criteria

For a release/milestone, testing is considered complete when:

- Planned critical/high-severity defects are resolved or explicitly accepted.
- Required test cases have been executed and results recorded.
- Integration tests pass for the agreed scope.
- No orphan FR/BR/UC remains in the traceability sheet.
- Required NFR evidence is collected or deviations are documented.
- Test execution report and defect log are updated.
- M8 provides QA sign-off for applicable PRs after confirming tests exist and pass.

## 11. Testing Schedule

| Phase / Date | M8 deliverable |
|---|---|
| Phase 0 — 11/10 | Test Plan skeleton, traceability sheet, AI-usage template |
| Phase 1 — 25/10 | Test Plan v1; testing-technique assignment; IoT simulator design/checklist |
| Phase 2 — 05/11 | IoT simulator, seed/test data, Test Plan final preparation |
| Phase 3 — 12/11 | Standardized test cases, traceability, integration-test skeleton, PR sign-offs |
| Phase 4 — 18/11 | Execute integration tests; test execution report; consolidated defect log; testing report draft |
| Phase 5 — 22/11 | Final Testing/Evaluation/Conclusion/AI Declaration integration and report consistency check |

## 12. Tools / Automation

- GitHub + Pull Requests for review and traceability.
- Project-selected unit/integration test framework: **TBD**.
- Coverage tooling: **TBD**.
- Linter / formatter / type checker: **TBD**.
- Load/performance tooling: **TBD** based on final stack.
- Automated CI checks: **TBD**.

## 13. Test Case Standard (Planned)

The standardized test-case format will include at least:

| Field | Description |
|---|---|
| TC ID | Unique `TC-xxx` identifier |
| Requirement / UC | Linked `FR`, `NFR`, `BR`, and/or `UC` IDs |
| Technique | EP, BVA, decision table, state transition, etc. |
| Preconditions | Required initial state/data |
| Input / Event | Data or action under test |
| Expected Result | Observable expected behavior |
| Actual Result | Recorded during execution |
| Status | Pass / Fail / Blocked |
| Evidence | Relevant output/log/screenshot/reference |

## 14. Open Items for Phase 1

- Finalize FR/BR/UC numbering after requirements v1 is locked.
- Finalize test framework and CI command after tech-stack decision.
- Define concrete test datasets and seeds.
- Assign testing techniques to each module/test family.
- Define the Core state-update interface needed by `iot_sim` and integration tests.
