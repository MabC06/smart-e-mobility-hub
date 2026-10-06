# Decisions & Assumptions Log

> Required by CONTRIBUTING sections 1.4 and 12. Every entry has an ID, a date, an owner and a status.
> Changing a shared interface or the `core` API contract also needs an entry here (CONTRIBUTING section 3).

**Status values:** `Proposed` (waiting for team agreement) · `Accepted` · `Superseded by D-xxx` · `Rejected`

**Owner format:** module (M1-M8) plus `<Student ID> <Full name>` (see the Team table in `README.md`).

---

## 1. Decisions

| ID | Date | Owner | Decision | Rationale | Status |
|---|---|---|---|---|---|
| D-001 | 2026-10-06 | M1 2452738 Đoàn Nhật Minh | Branch protection is **not available** on GitHub Free + private repo, so `main`/`develop` cannot be technically locked down. Substitute with a process-based rule instead (CONTRIBUTING section 8): no direct pushes, only the Lead merges to `main`, 1 manual approval per PR, CI checked manually before approving. | GitHub does not support enforcing these rules on our plan; the team follows them by convention instead. | Accepted |
| D-002 | 2026-10-05 | M1 2452738 Đoàn Nhật Minh | Tech stack: see `docs/design/architecture/tech-stack-proposal.md` (Python + FastAPI + SQLAlchemy/SQLite, React + Vite + TypeScript, pytest, ruff, mypy). | Needs team agreement; final target date 2026-10-10. | Proposed |
| D-003 | 2026-10-05 | M1 2452738 Đoàn Nhật Minh | Architecture direction: modular monolith in which `core` is the only owner of hub/vehicle/charger state. Other modules read and change state only through the `core` interface; modules publish and consume domain events in-process. What-if simulation works on a snapshot copy of the state. | Matches CONTRIBUTING section 9 (rules 2, 4, 5, 13). To be justified and finalized in the architecture document. | Proposed (finalize by 2026-10-26) |
| D-004 | 2026-10-05 | M1 2452738 Đoàn Nhật Minh | System boundary: the IoT simulator (`src/iot_sim/`) represents the physical sensor/event layer. It is a *source of events outside the system boundary*, even though its code lives in the repo, and it only talks to the system through the `core` state-update interface. | Keeps the boundary consistent with "no hardware" and with CONTRIBUTING rule 9.13. | Proposed |
| D-005 | 2026-10-05 | M1 2452738 Đoàn Nhật Minh | Time handling: store all timestamps in UTC; display in ICT (UTC+7). Code reads time from an injectable clock (never directly from the system clock) so tests and simulations are deterministic. | Reservation hold times, expiry and scheduling must be testable and reproducible (NFR-13). | Proposed |
| D-006 | 2026-10-05 | M1 2452738 Đoàn Nhật Minh | Core interface change protocol: (1) announce in the team channel, (2) add an entry to this file, (3) bump the interface spec version, (4) M1 approves the PR. Proposed notice period for non-urgent changes: 48 hours. | CONTRIBUTING section 3 requires telling the team first; this makes it concrete. | Proposed |
| D-007 | 2026-10-06 | M1 2452738 Đoàn Nhật Minh | Charging bays: ChargingPoint is 1-1 with ParkingSpace (a "charging bay"); charging points per Hub ≤ parking spaces per Hub. Full model and side effects: `docs/requirements/reference-dataset.md` §2, §8 Q1. | A vehicle being charged is still parked, so separate capacities would break the Hub capacity invariant (NFR-07). | Proposed (affects the class diagram; review with the team) |
| D-008 | 2026-10-06 | M1 2452738 Đoàn Nhật Minh | Demand profile: peak = pickups + returns per period, with a dominant flow per Hub type. Full definition: `docs/requirements/reference-dataset.md` §5, §8 Q2. | Produces the Hub-short-of-vehicles / Hub-short-of-parking situations FR-10 and the capacity scenario need. | Proposed (M6 and M8 to confirm and tune) |
| D-009 | 2026-10-06 | M1 2452738 Đoàn Nhật Minh | "Active private EV" definition and its charging-request share. Full definition: `docs/requirements/reference-dataset.md` §8 Q3. | Gives seed data and charging-contention tests a precise, reproducible basis. | Proposed (M3 to confirm the charging share) |
| D-010 | 2026-10-06 | M1 2452738 Đoàn Nhật Minh | DS-STRESS = 2x DS-STD via 20 Hubs. Full spec: `docs/requirements/reference-dataset.md` §6. | Stresses NFR-04/NFR-15 through Hub-pair growth (45 to 190 pairs), not just bigger Hubs. | Proposed (M8 to confirm) |

## 2. Assumptions

| ID | Date | Owner | Assumption | Impact if wrong |
|---|---|---|---|---|
| A-01 | 2026-10-05 | M1 | Rental trips are hub-to-hub: a vehicle is picked up at a hub and must be returned to a parking space at a hub. In-trip GPS tracking and route planning are out of scope. | Return/dispatch logic and the Vehicle state machine would need an "in transit" location model. |
| A-02 | 2026-10-05 | M1 | "Find suitable vehicles and hubs for a journey" means filtering and ranking hubs/vehicles by origin hub, destination hub, availability and battery level; it is not map routing. | Search (FR-02) would need geographic distance and routing data. |
| A-03 | 2026-10-05 | M1 | There are three rental vehicle types (e-bike, e-scooter, electric motorcycle). All charging points are compatible with all vehicle types. | Charging compatibility rules would be added to scheduling (M3) and allocation (M4). |
| A-04 | 2026-10-05 | M1 | A charging point serves one vehicle at a time, at a fixed power rate; charging time is linear in battery percentage. Battery swapping is out of scope — vehicles are only recharged in place. | Scheduling (M3) would need a charge-curve model; a swap station would add a new resource type, workflow and state to Vehicle and Hub. |
| A-05 | 2026-10-05 | M1 | Private vehicles are registered by the student (plate number and type) before reserving parking or charging. | Registration flow and data model would change. |
| A-06 | 2026-10-05 | M1 | Authentication is simplified: seeded accounts with two roles (student, operator). No university SSO. | Security design (NFR-16) would grow. |
| A-07 | 2026-10-05 | M1 | Payment, pricing, billing, penalties and user ratings are out of scope. | Additional actors and business rules. |
| A-08 | 2026-10-05 | M1 | One deployment instance. "Distributed operational environment" in the assignment is represented by logically separated modules and hubs communicating through the `core` interface, not by physically separate services. This is stated as a limitation in the report. | If separate services are required, the architecture and consistency strategy change. |
| A-09 | 2026-10-05 | M1 | Operators are a single trusted group; there is no per-hub operator permission model. | Role model and audit requirements would extend. |
| A-10 | 2026-10-05 | M1 | The course's official deadline has not been announced; the team uses 2026-11-25 as the internal target (see `docs/task-assignment-timeline.md`). | Timeline compression or extension. |
| A-11 | 2026-10-06 | M1 2452738 Đoàn Nhật Minh | Reference dataset DS-STD and DS-STRESS. Full numbers, per-hub table and distributions: `docs/requirements/reference-dataset.md`. | Performance and scalability targets (NFR-01 to NFR-05, NFR-15), the seed data of `iot_sim` and the What-if scenarios (M6) must be re-derived. |

## 3. How to add an entry

1. Pick the next free ID (`D-xxx` for decisions, `A-xx` for assumptions).
2. Fill date, owner, text, rationale (or impact) and status.
3. An entry that is still `Proposed` (decisions) or that nothing else cites by ID yet may be deleted outright if it turns out to be unnecessary or wrong — nothing was built on it, so there is nothing to preserve a trail for. After deleting one, renumber the later IDs so the sequence stays contiguous, and update every file that cites a renumbered ID (`grep -rn "D-0\|A-0"` across `docs/`).
4. An entry that was `Accepted` (acted on) or is cited by ID elsewhere (code, PRs, another doc) must never be deleted. If it is replaced, set its status to `Superseded by D-xxx` and add the new row (this keeps its old ID, so no renumbering here).
5. If a decision's full content is already fully specified in its own doc (for example a dataset spec), keep only a short pointer here instead of duplicating the text — the other doc stays authoritative and this log stays the index.
6. Reference the entry ID in the PR description ("Assumptions" section of the PR template).
