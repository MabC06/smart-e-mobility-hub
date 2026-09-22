# Smart E-Mobility Hub

A coordination system for shared electric mobility resources (e-bikes/e-scooters) across the VNU-HCM Urban Area. Course project for **Software Engineering — HK261**.

The system manages Mobility Hubs consisting of parking spaces, charging points, and vehicles, serving two main actor groups: **students** (rent vehicles, reserve, charge) and **operators** (monitor, handle incidents, coordinate, run What-if Simulations).

> **Internal target deadline:** Nov 25 (the course's official deadline has not been announced yet — update this once known)

---

## Table of Contents

- [Scope](#scope)
- [Team](#team)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Git Workflow](#git-workflow)
- [Project Documentation](#project-documentation)
- [Testing](#testing)
- [Generative AI Usage Declaration](#generative-ai-usage-declaration)

---

## Scope

Per the assignment specification, the system must support at least the following core capabilities:

- View Mobility Hubs and their current resource status
- Find suitable rental electric vehicles, view availability & battery information
- Reserve rental electric vehicles, pick up and return them
- Reserve parking spaces
- Request or schedule charging services
- Support private-vehicle users reserving parking and charging resources
- Monitor vehicles, parking capacity, charging points, and hub utilization
- Handle operational incidents (unavailable vehicles, failed charging points)
- Coordinate/redistribute rental vehicles among Mobility Hubs
- Coordinate charging priorities and schedules
- Run What-if Simulation scenarios and generate coordination recommendations

## Team

| Member | Module |
|---|---|
| Member 1 | Core Domain, State Management & System Architecture (Lead) |
| Member 2 | Reservation & Trip (Student) |
| Member 3 | Charging Request & Smart Scheduling |
| Member 4 | Resource Allocation & Vehicle Dispatching |
| Member 5 | Operator Monitoring & Incident Handling |
| Member 6 | What-if Simulation & Coordination Design |
| Member 7 | UI/UX Design & Structural-Data Design |
| Member 8 | Testing, QA & Report Integration Lead |

Detailed task breakdown, deliverables per member, and the team timeline: see `docs/task-assignment-timeline.docx`.

## Repository Structure

Proposed source layout, organized by module so each member can work independently with minimal conflicts:

```
smart-e-mobility-hub/
├── docs/                     # SRS, design docs, test plan, task assignment & timeline
│   ├── requirements/
│   ├── design/                # architecture, class diagram, ERD, UML
│   └── testing/
├── src/
│   ├── core/                  # Member 1 — domain model & state management
│   ├── reservation/           # Member 2 — reserve, pick up/return
│   ├── charging/               # Member 3 — charging request & scheduling
│   ├── allocation/            # Member 4 — resource allocation & dispatching
│   ├── monitoring/            # Member 5 — operator monitoring & incident handling
│   ├── simulation/            # Member 6 — what-if simulation
│   └── ui/                    # Member 7 — student & operator interfaces
├── tests/                     # Member 8 — consolidated test cases by module
├── .github/                   # PR template, CI workflow (if any)
└── README.md
```

> This is an initial proposal — update it once the team finalizes the detailed architecture in the System Design phase.

## Tech Stack

> _TBD — to be filled in once the team finalizes the stack during the Design phase._

- Backend language/framework: _TBD_
- Frontend: _TBD_
- Database: _TBD_
- UML/wireframing tools: _TBD_
- Test-case management: _TBD_

## Getting Started

```bash
# Clone the repo
git clone <repo-url>
cd smart-e-mobility-hub

# Install dependencies (update once the tech stack is set)
# ...

# Run the project locally
# ...
```

## Git Workflow

**Branches:**
- `main` — always in a working state, only receives merges via reviewed Pull Requests; used to tag versions for demos/submission
- `develop` — integration branch where modules are merged before going to `main`
- `feature/<module>-<short-description>` — each member works on their own branch per module, e.g. `feature/reservation-booking-flow`, `feature/charging-scheduling`

**Process:**
1. Branch `feature/...` off `develop`
2. Implement + write tests for the change
3. Push the branch, open a Pull Request into `develop`
4. At least one review required (preferably from the owner of a directly related module)
5. Address review comments, merge once approved
6. Periodically (end of each sprint): merge `develop` into `main`

**Cross-review pairing for closely related modules:**
- Reservation (M2) & Charging (M3) ↔ review Resource Allocation (M4)
- Core Domain (M1) ↔ review What-if Simulation (M6)
- Operator Monitoring (M5) ↔ review changes to Core Domain (M1)

**Other conventions:**
- Commit messages follow Conventional Commits, e.g. `feat(reservation): add conflict check`
- Enable branch protection on `main` and `develop`: no direct pushes, PR + at least 1 approval required
- A PR is only "Done" once it includes the corresponding test cases (Member 8 signs off on test coverage for PRs touching important business logic)
- Track progress via GitHub Projects (Kanban), mapped to the 8 modules and the phases in the timeline

## Project Documentation

| Document | Location |
|---|---|
| Assignment specification | `docs/requirements/assignment-spec.pdf` |
| Report Guideline & Rubric | `docs/requirements/guideline-rubric.pdf` |
| Task Assignment & Timeline | `docs/task-assignment-timeline.docx` |
| Software Architecture | `docs/design/architecture.*` |
| Class Diagram / ERD | `docs/design/` |
| Use-case Diagrams & Tables | `docs/requirements/` |
| Test Plan & Test Cases | `docs/testing/` |

## Testing

The test suite covers the following categories (per the rubric requirements):
- Normal operation
- Invalid input / operation
- Boundary & capacity conditions
- Resource conflicts
- State transitions
- Equipment/resource failures
- What-if Simulation scenarios
- Integration across modules

The detailed Test Plan (objectives, scope, entry/exit criteria, environment, schedule) is maintained by Member 8 at `docs/testing/test-plan.md`.

## Generative AI Usage Declaration

Per course requirements, any use of Generative AI tools during the project (analysis, design, coding, report writing, etc.) must be transparently declared: which tool, for what purpose, and which parts of the work were AI-generated, revised, or verified by the student. Each member records their own AI usage in `docs/ai-usage-declaration.md`; Member 8 consolidates the final version before submission.
