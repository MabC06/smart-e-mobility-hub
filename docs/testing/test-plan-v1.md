# Test Plan — v1

> **Owner:** M8 — Testing, QA & Report Integration Lead  
> **Baseline:** `develop` snapshot `6777736` (2026-11-05)  
> **Status:** Phase 1/2 working version; update as module requirements and interfaces are finalized  
> **Related:** `docs/requirements/nfr.md`, `docs/requirements/reference-dataset.md`, `docs/design/architecture/core-api-spec.md`, `docs/design/simulation/iot-sim-design.md`, `CONTRIBUTING.md`

## 1. Purpose and objectives

This plan defines how Smart E-Mobility Hub will be verified from module-level behavior through integration and system testing. It provides a repeatable method to:

1. Verify functional requirements (FR), business rules (BR), and use cases (UC).
2. Detect invalid input, boundary, state-transition, resource-conflict, concurrency, and failure-handling defects.
3. Verify module interactions through the public `core` interface and enforce NFR-22 module boundaries.
4. Collect measurable evidence for applicable NFRs, especially performance, consistency, isolation, determinism, security, and coverage.
5. Maintain traceability from requirements to test cases, execution evidence, and defects.

## 2. Scope

### 2.1 In scope

- Core state management, entity invariants, claims, state machines, snapshots, and sensor intake.
- Reservation and trip workflows (M2).
- Charging requests, private-EV charging, queueing, and scheduling (M3).
- Allocation and dispatch planning/execution (M4).
- Monitoring, hub status, and incident handling (M5).
- What-if simulation and coordination recommendations (M6).
- UI behavior relevant to NFR-20 and NFR-21 (M7).
- Deterministic IoT network seeding and event generation (M8).
- Cross-module integration and end-to-end student/operator workflows.
- DS-STD performance and reference-data sanity checks.

### 2.2 Out of scope

- Physical sensors, vehicles, chargers, radio networks, and hardware-in-the-loop testing.
- Production deployment, real payment processing, university SSO, and real-world routing.
- Load beyond the documented DS-STD/DS-STRESS profiles unless separately approved.
- Full UI usability study beyond the agreed peer walkthrough and rubric evidence.

## 3. Test levels and ownership

| Level | Purpose | Owner | Location |
|---|---|---|---|
| Unit | Verify functions/classes in isolation | Each module owner | `tests/<module>/` |
| Component | Verify one module with controlled Core/provider dependencies | Each module owner | `tests/<module>/` |
| Integration | Verify contracts and workflows across modules | M8, with module owners | `tests/integration/` |
| System / end-to-end | Verify selected student and operator journeys | M8 coordinates; M7 supports UI | `tests/integration/` |
| Non-functional | Measure NFR targets and collect evidence | M8 coordinates; relevant owner fixes | `tests/` + `docs/testing/` |

Module owners write and maintain their own unit tests. M8 does not replace their tests; M8 verifies cross-module behavior and signs off that required tests exist and pass.

## 4. Test design techniques

Use the technique assignment in [`test-technique-assignment.md`](test-technique-assignment.md). At minimum, derive cases using:

- **Equivalence Partitioning (EP):** valid/invalid categories, roles, entity states, and input types.
- **Boundary Value Analysis (BVA):** numeric limits, capacities, battery thresholds, date/time intervals, queue sizes.
- **Decision Table Testing:** combinations of role, resource availability, battery, Hub status, and claim conflicts.
- **State-Transition Testing:** valid/invalid transitions and state preservation after rejection.
- **Pairwise / combination testing:** configuration combinations where exhaustive enumeration is impractical.
- **Concurrency / conflict testing:** simultaneous claims and optimistic-version conflicts.
- **Fault injection:** sensor errors, charger failure, provider unavailable, transaction rollback.
- **Metamorphic / determinism testing:** same seed and ordered events produce the same generated dataset and output.
- **Performance / load testing:** latency and throughput under DS-STD with 100 concurrent sessions.
- **Static analysis / architecture checks:** import-boundary checks and CI quality gates.
- **Exploratory / usability review:** operator status visibility and understandable rejection messages.

## 5. Test environment

- Python **3.12** (D-002); use the repository virtual environment.
- Run tests from the repository root.
- Core tests use `InMemoryRepository` for fast deterministic tests and the SQL repository for persistence/contract tests.
- API tests use FastAPI's test client and an isolated test database/repository.
- All timestamps must be timezone-aware UTC. Use injected/frozen clocks for time-sensitive tests.
- Simulated data must use explicit seeds; tests must not depend on wall-clock time or external services.
- Do not use production credentials. Tests use isolated keys/configuration.
- CI runs Ruff, Ruff format check, mypy, pytest, and the import-boundary test according to the current workflow.

## 6. Test data strategy

### 6.1 DS-STD

Use `docs/requirements/reference-dataset.md` as the authoritative source:

- 10 Hubs; 400 parking spaces; 61 charging points.
- 250 rental vehicles; 1,000 student accounts; 5 operator accounts.
- 100 registered private EVs.
- Rental fleet distribution: 60% above 70% battery, 25% from 30–70%, 15% below 30%; vehicle types 50% e-bike, 30% e-scooter, 20% electric motorcycle.
- 100 concurrent sessions for NFR-02 and NFR-03.

### 6.2 Focused fixtures

Use small purpose-built fixtures for boundary and conflict cases rather than loading DS-STD into every unit test. Fixtures must name their assumptions and avoid hidden global mutable state.

### 6.3 Determinism

- Pass seeds as parameters; do not rely on a global random generator.
- Sort entities and outputs by stable IDs before comparison or serialization.
- Same seed + same ordered event stream must produce identical dataset/event payloads (NFR-13).
- Store generated data only when small; otherwise document how to regenerate it.

## 7. Entry and exit criteria

### 7.1 Entry criteria

A test activity may begin when:

- Relevant FR/BR/UC IDs and expected behavior are available.
- The module/API or an agreed stub is available.
- Required fixtures and expected outcomes are defined.
- Dependencies and environment are installable.
- For integration tests, participating interfaces are implemented or frozen sufficiently to test.

### 7.2 Exit criteria

A milestone is test-complete when:

- All planned critical/high-priority cases are executed or explicitly marked Blocked with a reason.
- No unresolved critical defect remains; accepted defects have an owner and rationale.
- Integration tests pass for the agreed scope.
- Coverage targets in NFR-24 are reported (Core ≥70%; reservation, charging, allocation, monitoring, simulation ≥60%).
- Applicable NFR measurements and deviations are recorded.
- Every active FR, BR, and UC has at least one test; no duplicate/orphan IDs remain in the traceability sheet.
- Test execution report and defect log are updated.
- M8 sign-off confirms tests exist and pass; it is not a substitute for code review.

## 8. Defect management

Record each defect in `docs/testing/defect-log.md` with:

- Defect ID, title, severity (Critical/High/Medium/Low), related TC and requirement IDs.
- Environment/commit, reproducible steps, expected vs actual result, evidence.
- Status, owner, fix PR/commit, retest result, and resolution.

A failed test must not be silently changed to pass. If the expected behavior is wrong, obtain owner/Lead agreement and update the authoritative requirement/design first.

## 9. Traceability and test-case convention

- Test IDs follow `TC-M<n>-###`; integration/system tests use M8 IDs.
- Every case includes `Verifies:` and `Technique:` metadata.
- Requirement-to-test links are maintained in `traceability-sheet.md`, not manually duplicated in requirements.
- Standard case format: ID, title, verifies, technique, priority, preconditions, steps/input, expected result, actual result, status, evidence.
- Planned test cases remain `Planned` until executed; do not mark them `Pass` merely because code exists.

## 10. NFR verification strategy

| NFR | Verification approach | Evidence |
|---|---|---|
| NFR-01 | Timestamp accepted update and subsequent Core read; UI refresh timing | Integration timing log |
| NFR-02 | Read API load test, DS-STD, 100 concurrent sessions; p95 ≤500 ms, max ≤2 s | Raw results + summary |
| NFR-03 | Write API load test; p95 ≤1 s | Raw results + summary |
| NFR-04 | Time charging schedule ≤3 s/Hub and network redistribution ≤5 s | Benchmark output |
| NFR-05 | Time each of five M6 scenarios ≤30 s | Scenario benchmark output |
| NFR-06 | 20–50 simultaneous requests for same resource; repeat 100 runs | Conflict/concurrency report |
| NFR-07 | Run invariant checker after every integration and simulation run | Invariant output |
| NFR-08 | Exercise valid and invalid state/event pairs | Transition matrix |
| NFR-09 | Inject failure at each multi-entity operation step | Rollback assertions |
| NFR-10 | Malformed sensor event and charger/vehicle failure injection | Rejection event + unchanged-state assertion |
| NFR-12 | Hash operational state before/after each simulation | Matching hashes + write-guard evidence |
| NFR-13 | Repeat same seed/event order twice | Identical normalized outputs |
| NFR-14 | Fresh clone and setup by a member other than the author; ≤15 min, ≤5 commands | Checklist and elapsed time |
| NFR-15 | Add a Hub and related entities by data/config only | Add-a-Hub test |
| NFR-16 | Authorization test for every endpoint and operator-only operation | Endpoint-role matrix |
| NFR-17 | Secret scan and repository hygiene review | Scan result |
| NFR-18 | EP/BVA for every external input; invalid input returns 4xx, not 5xx | Invalid-input matrix |
| NFR-20 | Review operator dashboard against wireframes and near-capacity/incident states | Screenshot/review notes |
| NFR-21 | Review rejection messages; no stack traces; alternatives where possible | UI/API evidence |
| NFR-22 | Automated static import-boundary check | CI result |
| NFR-24 | Coverage report per named module | CI coverage artifact |
| NFR-25 | Inspect audit records for UTC, entity, previous/new state, trigger, actor | Integration assertions |
| NFR-26 | Traceability orphan/duplicate scan | Traceability audit |

Withdrawn NFR-11, NFR-19, NFR-23, and NFR-27 are retained in the traceability sheet for ID stability and are not acceptance criteria.

## 11. Schedule and deliverables

The authoritative schedule is `docs/task-assignment-timeline.md`. M8 milestones:

| Date | Deliverable |
|---|---|
| 06/11 | Minimal `iot_sim`: DS-STD seed builder, battery drain, parking occupancy |
| 08/11 | Full event feed, test data set, Test Plan final draft |
| 12/11 | Test Plan final, standard-format test cases, integration skeleton, module PR test sign-offs |
| 18/11 | Integration execution, NFR measurements, execution report, consolidated defect log, Testing report draft |
| 22/11 | Evaluation/conclusion integration, final consistency checklist and report assembly |

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Module requirements or APIs change late | Rework and broken integration tests | Trace version/commit; update tests with owner review |
| DS-STD makes unit tests slow | Feedback delay | Use small fixtures for unit tests; DS-STD for integration/performance |
| Randomized feed causes flaky tests | Unreproducible failures | Explicit seed, frozen time, sorted event order |
| M8 becomes a bottleneck for sign-offs | PR queue | Review test existence/pass status as PRs arrive; do not wait until code freeze |
| Cross-module assumptions diverge | Integration defects | Use Core API spec and provider-port contracts as single interface references |

## 13. Open items

- Confirm exact test/load tooling with the team and record it in `docs/DECISIONS.md` if it changes project conventions.
- Add module-specific test IDs as M2–M6 finalize BR/UC tables.
- Build the integration skeleton after module interfaces and `main.build_app` are stable.
- Expand the minimal IoT feed with charger faults, vehicle faults, heartbeat, and demand-pattern events by 08/11.
