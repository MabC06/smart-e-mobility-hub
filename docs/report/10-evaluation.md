# 6. Evaluation, Conclusion and AI Usage Declaration

> **Status:** Final v1.0 · **Owner:** M1 · **Date:** 2026-11-26
> The measured figures are from Section 5 (rerun on `develop` at `0056f23`); the deviations are the DEV rows of Section 4.4.

## 6.1 Evaluation against the objectives

| Objective | Result | Evidence | What is missing |
|---|---|---|---|
| O-1 Accurate, near-real-time view of every Hub | Met | FR-01, FR-02, FR-08 implemented; a write is visible to the next read (NFR-01, p95 ≤ 8.1 ms); screens refresh by polling | The screens poll every few seconds instead of receiving pushed updates |
| O-2 Rental, parking and private-EV bookings without conflicts | Met | FR-02 to FR-05 and FR-07; claims in `core` refuse every overlap (BR-M1-01); 42 concurrency tests with 20 to 50 simultaneous requests: one wins, the rest get a conflict (NFR-06) | Parking and charging for a private EV are booked separately, not as one bundle (DEV-15) |
| O-3 Efficient use of charging capacity | Met at the standard load | The queue ranks by emergency battery, a booking in the next hour, lowest battery, then request time (BR-M3-03); a queued request is bound as soon as a slot is free; a failed point moves its sessions (BR-M3-02); one Hub's schedule in ≤ 1.75 s (NFR-04) | No power limit per Hub (DEV-06); planning exceeds 3 s at 50 queued requests on one Hub (DEF-M3-007) |
| O-4 Capacity warnings, incidents and redistribution | Met | Hubs at 90 % are flagged (BR-M5-01); incidents from sensor events, point failures, overdue Trips and heartbeat loss, with escalation after 5 min (BR-M5-04); M4 plans, the operator approves, the vehicles are picked up and returned (FR-10); network plan ≤ 358 ms (NFR-04) | Relocation is Hub to Hub, without routes or travel time (DEV-04) |
| O-5 What-if on a copy, with recommendations | Met | SC-01 to SC-05 run on a snapshot; the operational state is unchanged after every run and the same seed gives the same report (NFR-12, NFR-13); each scenario ≤ 148 ms (NFR-05); a recommendation can be sent to M4 as a task | The scenarios count over the whole horizon per Hub instead of stepping through time (DEV-08) |
| O-6 Consistent, traceable process | Mostly met | All 12 FRs, 28 of 34 BRs and 36 of 38 UCs have a test case; 1,578 tests, 94 % coverage, CI on every PR; 29 decisions and 42 defects recorded | Six BRs and two UCs have no test case (Section 5.5) |

## 6.2 Strengths

- **One owner of shared state.** Every change to a Hub, space, charging point or vehicle goes through `core`, which checks the rules once, so no module keeps its own copy of a resource that could drift from the others.
- **Atomic, conflict-free operations.** Claims, the unit of work and optimistic versions make a pick-up or a return apply fully or not at all, and no resource is given twice; this is tested, not assumed (NFR-06, NFR-09).
- **Modules that could be built in parallel.** Modules depend only on `core`, and a test in CI rejects any other import (NFR-22). Eight people worked on separate packages and joined them through events and provider ports.
- **Repeatable.** An injectable clock, seeded randomness and sorted snapshots make tests and What-if runs give the same result every time; a fresh clone runs in 5 commands (NFR-13, NFR-14).
- **One set of routes for every client.** The pages call the same REST routes as any other client, with the user's token (D-026), so role checks are written once. The student pages also work on a phone.
- **A visible process.** Every change went through a reviewed pull request and CI; decisions, defects, AI use and traceability are kept in the repository and were updated to the end.

## 6.3 Scalability and use on phones

**Today.** The system is one process with one SQLite database (A-08, DEV-03). On the standard dataset (10 Hubs, 400 spaces, 61 charging points, 350 vehicles, 1,005 users) reads answer in p95 ≤ 21 ms and writes in p95 ≤ 231 ms, far under the targets, but these are sequential requests; no figure exists for many users at once (D-024, DEV-01). A new Hub, space, point or vehicle is data only, with no code change (NFR-15).

**Path to more Hubs and users.** The design keeps the steps open, in this order:

1. **PostgreSQL instead of SQLite.** Modules reach the database only through the `Repository` interface and SQLAlchemy Core, so the store can change without changing a module. This removes the single-writer limit of SQLite.
2. **Several application processes.** The entities already carry versions, so conflicts are detected in the database. The in-process lock would be replaced by database transactions, and the in-process event bus by an outbox table or a message broker, so that events survive a crash and reach every process.
3. **Separate services along the module boundaries.** Modules already talk only through `core`, events and provider ports (NFR-22); each port could become a network call. Atomic operations across modules would then need compensating steps, which is why this step comes last.
4. **Work in the background.** The lazy sweeps of M2 (DEV-17) and the periodic checks of M5 would run on a scheduler; the charging planner would rank a long queue incrementally instead of re-planning it whole (DEF-M3-007).

**Phones.** Students use the same web pages on a phone: the student screens adapt from 360 px wide with plain CSS (D-027), and they were used on a real phone over Wi-Fi during the demo. Operator screens stay desktop screens for the control room. A native phone app would be one more client of the existing REST routes, signing in with the same bearer token (D-023), so the server would not change; push notifications would need a service that turns domain events into messages.

## 6.4 Limitations and future work

| Limitation | Effect | Future work |
|---|---|---|
| One deployment, logically separated Hubs (A-08, DEV-03) | Failures between Hubs are not modelled | Steps 1 to 3 of 6.3 |
| No concurrent load test (DEV-01) | Behaviour at many simultaneous users is unknown; correctness under concurrency is tested | A load test with a tool such as Locust on PostgreSQL |
| Charging planning at deep queues (DEF-M3-007) | More than 3 s at 50 queued requests on one Hub | Incremental ranking; batch binding |
| No power limit per Hub (DEV-06) | The planner can schedule every bay at full power | A power budget per Hub in `core` and a peak-shaving rule |
| What-if counts over the horizon (DEV-08) | Effects that depend on order in time are approximated | Step the state per `time_step_minutes` |
| Parking and charging booked separately (DEV-15); `HoldConsumer` not registered (DEV-16) | A private EV owner makes two bookings | Joint booking through the hold port |
| No background scheduler (DEV-17) | Deadlines apply when the next student uses M2 | A scheduler for M2 sweeps and M5 checks |
| Traceability gaps (Section 5.5) | Six BRs and two UCs have no test case | Tests for BR-M1-03 and the M5 use cases |
| Withdrawn NFRs (NFR-11, 19, 23, 27) | No soak test, no usability test with users | A 60-minute soak run and a usability walkthrough |

## 6.5 Conclusion

The team built a working Smart E-Mobility Hub system: students find, reserve, pick up and return vehicles and book parking and charging, on a laptop or a phone; operators watch every Hub, handle incidents, redistribute vehicles, manage the charging queues and try What-if scenarios before acting. All twelve functional requirements are implemented and tested, the measured quality targets are met at the standard load, and the known limits are stated with their effects.

The main lesson is that a single owner of shared state, with claims and atomic units of work, let eight people build separate modules that still agree on every resource. The cost of that choice is one deployment; the steps to scale it are known and follow the module boundaries that the design already enforces.

## 6.6 AI usage declaration

Every member used generative AI and declared it at the time of use in `docs/ai-usage/<student-id>.md`, one row per task with what the AI produced, what the member changed or checked, and the final use (CONTRIBUTING rule 5). The team rules were the same for everyone: AI output enters the repository only through a pull request reviewed by another member, it must pass CI (lint, format, types, tests, coverage, import boundaries), and the author must be able to explain every line.

| Member | Module | AI tools | Used for | How the output was checked |
|---|---|---|---|---|
| M1 2452738 | `core`, integration | Claude Code (Claude Sonnet 5, Sonnet 5.5, Opus 5.5) | Drafting documents and review comments, cross-module ID checks, `core` code and tests, integration fixes, the backend and UI completed in Phase 4, the rerun on `develop` | Tests and CI on every change, the demo run on a laptop and a phone, PR review |
| M2 2452620 | `reservation` | OpenAI Codex | Requirements, UML sources, report sections, M2 code and tests, review guidance | PR status and ID checks, rendered diagrams, link checks, tests |
| M3 2452030 | `charging` | Gemini, Claude | Requirements and BR-M3, priority workflow, service code, review fixes, report sections and test cases | Unit tests, review by M1, NFR-04 measurement |
| M4 2412466 | `allocation` | Claude (claude.ai, Sonnet 5.5), Antigravity | Requirements, diagrams, algorithm design, module code and tests, review fixes | Boundary and regression tests, PR review |
| M5 2453413 | `monitoring` | Gemini | FR-08 and FR-09, incident types and escalation rules, use-case tables, module code | Unit tests, PR review |
| M6 2453366 | `simulation` | ChatGPT (GPT-4o), Gemini | Requirements, design formatting, PlantUML and Mermaid diagrams, lint fixes, refactoring | ruff, format and mypy before each commit; isolation tests (NFR-12) |
| M7 2452615 | `ui` | Gemini, Claude | ERD and operator use-case drafts, review fixes, UI code and tests | Checked against `core` and the module routes; UI tests; PR review |
| M8 2453252 | `iot_sim`, testing | ChatGPT, Claude, Gemini | Testing deliverables, the IoT simulator, NFR measurement scripts, verification reports | Runs of the test suite and the measurements; review against the project documents |

Each member declares that they understand the content they submitted, can explain and defend it, and remain responsible for its correctness and originality. The detailed logs are in `docs/ai-usage/`.
