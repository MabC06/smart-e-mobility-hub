# Smart E-Mobility Hub

A coordination system for shared electric mobility resources (e-bikes/e-scooters) across the VNU-HCM Urban Area. Course project for **Software Engineering — HK261**.

The system manages Mobility Hubs consisting of parking spaces, charging points, and vehicles, serving two main actor groups: **students** (rent vehicles, reserve, charge) and **operators** (monitor, handle incidents, coordinate, run What-if Simulations).

---

## Table of Contents

- [Scope](#scope)
- [Team](#team)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Contributing](#contributing)
- [Documentation & Deliverables](#documentation--deliverables)
- [Testing](#testing)
- [Generative AI Usage Declaration](#generative-ai-usage-declaration)
- [Demo](#demo)

---



## Scope

Per the assignment specification, the system supports at least the following 12 core capabilities. Each has an ID (`FR-xx`) used in commits, pull requests, test cases and the report for traceability.


| ID    | Functional capability                                                           | Main module(s) |
| ----- | ------------------------------------------------------------------------------- | -------------- |
| FR-01 | View Mobility Hubs and their current resource status                            | M1             |
| FR-02 | Find suitable rental electric vehicles; view availability & battery information | M2             |
| FR-03 | Reserve rental electric vehicles                                                | M2             |
| FR-04 | Pick up and return rental electric vehicles                                     | M2             |
| FR-05 | Reserve parking spaces                                                          | M2             |
| FR-06 | Request or schedule charging services                                           | M3             |
| FR-07 | Support private-vehicle users in reserving parking and charging resources       | M2, M3         |
| FR-08 | Monitor vehicles, parking capacity, charging points, and Hub utilization        | M5             |
| FR-09 | Handle operational incidents (unavailable vehicles, failed charging points)     | M5             |
| FR-10 | Coordinate/redistribute rental vehicles among Mobility Hubs                     | M4             |
| FR-11 | Coordinate charging priorities and schedules                                    | M3, M4         |
| FR-12 | Run What-if Simulation scenarios and generate coordination recommendations      | M6             |


> The `FR-xx` numbering follows the order of the capabilities in the course guideline. It must stay identical to the IDs used in `docs/requirements/`. Non-functional requirements (`NFR-xx`), business rules (`BR-xx`), use cases (`UC-xx`) and test cases (`TC-xxx`) are defined in the same documents; see the "Requirement IDs" section of [CONTRIBUTING.md](CONTRIBUTING.md).

**Out of scope** (per the assignment): physical hardware development and sophisticated 3D map interfaces. Vehicle, parking and charging state may come from simulated data.

## Team


| Member | Module                                                     | Name              | Student ID |
| ------ | ---------------------------------------------------------- | ----------------- | ---------- |
| M1     | Core Domain, State Management & System Architecture (Lead) | Đoàn Nhật Minh    | 2452738    |
| M2     | Reservation & Trip (Student)                               | Đặng Tuấn Kiệt    | 2452620    |
| M3     | Charging Request & Smart Scheduling                        | Võ Thanh An       | 2452030    |
| M4     | Resource Allocation & Vehicle Dispatching                  | Huỳnh Minh Nhật   | 2412466    |
| M5     | Operator Monitoring & Incident Handling                    | Đỗ Hoàng Việt     | 2453413    |
| M6     | What-if Simulation & Coordination Design                   | Thân Ngô Tuấn     | 2453366    |
| M7     | UI/UX Design & Structural-Data Design                      | Nguyễn Trung Kiên | 2452615    |
| M8     | Testing, QA & Report Integration Lead; IoT data simulator  | Lý Thành Tín      | 2453252    |


Task breakdown, deliverables per member and the team timeline: [docs/task-assignment-timeline.md](docs/task-assignment-timeline.md).

## Repository Structure

Proposed layout, organized by module so each member can work independently with minimal conflicts. Update it once the architecture is finalized in the System Design phase.

```
smart-e-mobility-hub/
├── docs/
│   ├── requirements/          # assignment spec, rubric, FR/NFR/BR, use-case diagrams & tables
│   ├── design/
│   │   ├── architecture/      # architecture diagram + justification
│   │   ├── structural/        # class diagram, ERD
│   │   ├── behavioral/        # activity, sequence, state machine diagrams
│   │   ├── ui/                # wireframes, UI flow
│   │   └── simulation/        # What-if scenario & recommendation design
│   ├── testing/               # test plan, test cases, execution report, defect log
│   ├── report/                # integrated final report
│   ├── ai-usage/              # one declaration file per member: <student-id>.md
│   ├── DECISIONS.md           # assumptions & key decisions
│   └── task-assignment-timeline.md
├── src/
│   ├── core/                  # M1 — domain model & state management
│   ├── reservation/           # M2 — reserve, pick up/return
│   ├── charging/              # M3 — charging request & scheduling
│   ├── allocation/            # M4 — resource allocation & dispatching
│   ├── monitoring/            # M5 — operator monitoring & incident handling
│   ├── simulation/            # M6 — what-if simulation
│   ├── iot_sim/               # M8 — simulated sensor/event feed & seed data
│   └── ui/                    # M7 — student & operator interfaces
├── tests/
│   ├── <module>/              # unit tests, written by each module's owner
│   └── integration/           # integration tests, owned by M8
├── .github/                   # pull_request_template.md, CI workflow (if any)
├── .env.example               # required environment variables (names only)
├── .gitignore
├── CONTRIBUTING.md            # coding rules & Git workflow
└── README.md
```

Diagrams are stored as source files (PlantUML / Mermaid / draw.io) next to their exported images.

No hardware is used, so vehicle, parking and charging-point state comes from simulated data. `src/iot_sim/` (owner: M8) generates the seed data and a simulated sensor/event feed (battery drain/charge, parking occupancy changes, charging-point failures, peak-hour demand) and pushes it into the system through the state-update interface of `core`. It is separate from the What-if Simulation (`src/simulation/`, M6), which runs hypothetical scenarios on a copy of the state.

## Tech Stack

> *TBD — to be filled in once the team finalizes the stack during the Design phase. Record the decision in* `docs/DECISIONS.md`*.*

- Backend language/framework: *TBD*
- Frontend: *TBD*
- Database: *TBD*
- UML/wireframing tools: *TBD*
- Test framework / test-case management: *TBD*



## Getting Started

```bash
# 1. Clone the repo
git clone <repo-url>
cd smart-e-mobility-hub

# 2. Set your identity for THIS repo only (how to get your noreply email: see CONTRIBUTING.md, section 2)
git config --local user.name  "<Student ID> <Full name>"
git config --local user.email "<your GitHub noreply email>"

# 3. Configure environment variables
cp .env.example .env        # then fill in values; never commit .env

# 4. Install dependencies   (update once the tech stack is set)
# ...

# 5. Run the project locally (update once the tech stack is set)
# ...

# 6. Run tests              (update once the tech stack is set)
# ...
```



## Contributing

All rules (branching, commits, pull requests, review, code style, security) live in **[CONTRIBUTING.md](CONTRIBUTING.md)**. In short:

- Branches: `main` (releases/demo, protected) ← `develop` (integration, protected) ← `<type>/<module>-<short-desc>`, e.g. `feat/reservation-booking-flow`.
- Commits follow Conventional Commits with the module as scope: `feat(reservation): add conflict check (FR-03)`.
- Every change goes through a Pull Request into `develop` with at least one review and the matching tests. The Lead merges `develop` into `main` via PR.
- Never commit secrets, `.env`, or large/generated files.

Progress is tracked on GitHub Projects (Kanban), mapped to the 8 modules and the project phases.

## Documentation & Deliverables


| Item                                         | Location                                 |
| -------------------------------------------- | ---------------------------------------- |
| Assignment specification                     | `docs/requirements/assignment-spec.pdf`  |
| Report Guideline & Rubric                    | `docs/requirements/guideline-rubric.pdf` |
| Task assignment & timeline                   | `docs/task-assignment-timeline.md`       |
| Requirements (FR/NFR/BR), use cases          | `docs/requirements/`                     |
| Software architecture                        | `docs/design/architecture/`              |
| Class diagram, ERD                           | `docs/design/structural/`                |
| Activity / sequence / state machine diagrams | `docs/design/behavioral/`                |
| UI wireframes & flows                        | `docs/design/ui/`                        |
| What-if Simulation design                    | `docs/design/simulation/`                |
| Test plan, test cases, results               | `docs/testing/`                          |
| Final report                                 | `docs/report/`                           |
| Assumptions & decisions                      | `docs/DECISIONS.md`                      |
| Generative AI declarations                   | `docs/ai-usage/`                         |


Final submission consists of the report, the source code, the pre-recorded demo (≈3 minutes within the ≈20-minute presentation; live demos are not permitted) and the AI usage declaration. Large files such as the demo video are **not** committed; link them in the [Demo](#demo) section.

## Testing

The test suite covers the following categories (per the rubric):

- Normal operation
- Invalid input / operation
- Boundary & capacity conditions
- Resource conflicts
- State transitions
- Equipment/resource failures
- What-if Simulation scenarios
- Integration across modules

Ownership: each module owner writes the unit tests for their module in `tests/<module>/`. M8 owns the Test Plan (`docs/testing/test-plan.md`), the standardized test-case documents linked to `FR`/`UC` IDs, integration tests in `tests/integration/`, and the execution/defect report. A PR touching important business logic is only "Done" once its tests are included and M8 has confirmed that the tests are included and passing.

## Generative AI Usage Declaration

Per course requirements, any use of Generative AI (analysis, design, coding, report writing, etc.) must be transparently declared: which tool, for what purpose, and which parts were AI-generated, revised, or verified by the student. Students remain responsible for understanding and defending everything they submit.

Each member records their own usage in `docs/ai-usage/<student-id>.md` **at the time of use**, not at the end. M8 consolidates the final declaration before submission.

## Demo

*Link to the recorded demo video: TBD (do not commit the video file).*
