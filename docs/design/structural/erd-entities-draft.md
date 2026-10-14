# Initial Data-Entity List for the ERD (Draft v1.0)

> **Status:** Draft v1.0 · **Owner:** M7 (Nguyễn Trung Kiên) · **Date:** 2026-10-11 · **Reviewer:** M5 (Đỗ Hoàng Việt)
> This document defines the initial catalog of persistent data entities, key attributes, state enumerations, and relationships for the **Smart E-Mobility Hub** relational database schema (SQLAlchemy 2.x on SQLite/PostgreSQL per `D-002`).
> It serves as the Phase 0 structural baseline to be synchronized with M1's Core Class Diagram (`docs/design/structural/class-diagram-core.md`) by 2026-10-16 and finalized into `docs/design/structural/erd.md` by 2026-10-24.

---

## 1. Data Modeling Principles & Architectural Constraints

To guarantee consistency between Requirements, Architecture (`M1`), Implementation, and Testing (`M8`), this entity draft enforces the following project constraints from `docs/report/01-introduction.md` and `docs/design/architecture/tech-stack-proposal.md`:

1. **Single Source of Truth in `core`:** All core infrastructure and resource states (`Hub`, `Vehicle`, `ParkingSpace`, `ChargingPoint`) are owned by `core` and persisted in the relational store.
2. **Optimistic Locking for Concurrency (`NFR-06`, `NFR-09`):** As specified in `tech-stack-proposal.md` §2, `Vehicle`, `ParkingSpace`, `ChargingPoint`, and `Reservation` include an integer `version` column for optimistic concurrency control to prevent double-booking and race conditions.
3. **Strict State-Machine Alignment:** Entity status columns use strict enumerations matching the lifecycle states defined for M1 (`Vehicle`), M2 (`Reservation`), M3 (`ChargingSession`), and M5 (`Incident`).
4. **What-if Simulation Isolation (`NFR-12`):** During a What-if Simulation run (`M6`), the simulated evolution of vehicles, hubs, and chargers operates on an **in-memory repository snapshot** cloned from `core`—never mutating the operational tables below. Only scenario run metadata, configurable inputs, and resulting recommendations (`SimulationRun`, `CoordinationRecommendation`) are optionally persisted for operator review/reporting.
5. **Scope Boundaries (`A-01` to `A-11`):**
   - Trips are strictly hub-to-hub (`A-01`); no GPS trajectory or map tile tables are included (`A-02`).
   - Three rental vehicle types exist, plus student-owned private EVs (`A-03`, `A-11`).
   - No billing, pricing, payment, or penalty entities are included (`A-07`).

---

## 2. Summary Catalog of Data Entities (by Module Ownership)

| Entity Group | Entity / Table Name | Primary Module Owner | Related FRs | Operational vs. Analytical |
|---|---|---|---|---|
| **A. Core Domain & Infrastructure** | `Hub` | M1 (`core`) | `FR-01`, `FR-08` | Operational (Core state) |
| **A. Core Domain & Infrastructure** | `ParkingSpace` | M1 (`core`) | `FR-01`, `FR-05`, `FR-07`, `FR-08` | Operational (Core state, optimistic lock) |
| **A. Core Domain & Infrastructure** | `ChargingPoint` | M1 (`core`) | `FR-01`, `FR-06`, `FR-07`, `FR-08`, `FR-09` | Operational (Core state, optimistic lock) |
| **A. Core Domain & Infrastructure** | `Vehicle` | M1 (`core`) | `FR-01` to `FR-04`, `FR-06` to `FR-11` | Operational (Core state, optimistic lock) |
| **B. Actors & Accounts** | `UserAccount` | M1 / M2 | All (`A-06`) | Operational (Seeded auth & role) |
| **C. Reservation & Trip (Student)** | `Reservation` | M2 (`reservation`) | `FR-03`, `FR-04`, `FR-05`, `FR-07` | Operational (Workflow, optimistic lock) |
| **C. Reservation & Trip (Student)** | `Trip` | M2 (`reservation`) | `FR-04` | Operational (Pick-up to return lifecycle) |
| **D. Charging & Smart Scheduling** | `ChargingSession` | M3 (`charging`) | `FR-06`, `FR-07`, `FR-11` | Operational (Queue & charging lifecycle) |
| **E. Resource Allocation & Dispatch** | `RedistributionTask` | M4 (`allocation`) | `FR-10`, `FR-11` | Operational (Hub-to-hub vehicle dispatch) |
| **F. Monitoring & Incident Handling** | `Incident` | M5 (`monitoring`) | `FR-08`, `FR-09` | Operational (Equipment/resource failures) |
| **F. Monitoring & Incident Handling** | `CapacityAlert` | M5 (`monitoring`) | `FR-08` | Operational (Hub threshold warnings) |
| **G. What-if Simulation Metadata** | `SimulationRun` | M6 (`simulation`) | `FR-12` | Analytical / Read-only snapshot metadata |
| **G. What-if Simulation Metadata** | `CoordinationRecommendation` | M6 (`simulation`) | `FR-12`, `FR-10`, `FR-11` | Analytical / Recommendation output |

---

## 3. Detailed Entity Attributes, Keys & State Enumerations

### 3.1 Group A — Core Domain & Infrastructure Entities (`M1`)

#### 1. `Hub`
Represents a physical Mobility Hub in the VNU-HCM Urban Area (e.g., Metro Station, Dormitory A, Dormitory B, University Campuses; 10 Hubs in reference dataset `A-11`).
- **Primary Key:** `hub_id` (String / UUID)
- **Attributes:**
  - `name` (String, not null, unique)
  - `zone_code` (String — e.g., `METRO`, `DORM`, `CAMPUS`, `SERVICE`)
  - `location_description` (String)
  - `total_parking_capacity` (Integer, not null, $> 0$)
  - `total_charging_points` (Integer, not null, $\ge 0$)
  - `status` (Enum: `ACTIVE`, `CAPACITY_WARNING`, `FULL`, `MAINTENANCE`)
  - `updated_at` (Timestamp)

#### 2. `ParkingSpace`
Represents an individual parking slot within a `Hub` (400 total spaces in `A-11`).
- **Primary Key:** `parking_space_id` (String / UUID)
- **Foreign Keys:**
  - `hub_id` $\rightarrow$ `Hub.hub_id` (not null)
- **Attributes:**
  - `space_label` (String — e.g., `H01-P01`)
  - `status` (Enum: `AVAILABLE`, `RESERVED`, `OCCUPIED`, `MAINTENANCE`)
  - `has_charger_access` (Boolean — indicates whether a `ChargingPoint` is co-located)
  - `version` (Integer, not null, default `1` — **Optimistic Locking** per `D-002`)
  - `updated_at` (Timestamp)

#### 3. `ChargingPoint`
Represents a charging unit at a `Hub` capable of charging any of the three vehicle types (`A-03`) one vehicle at a time at a fixed power rate (`A-04`; 61 points in `A-11`).
- **Primary Key:** `charging_point_id` (String / UUID)
- **Foreign Keys:**
  - `hub_id` $\rightarrow$ `Hub.hub_id` (not null)
  - `parking_space_id` $\rightarrow$ `ParkingSpace.parking_space_id` (nullable/unique — if tied to a dedicated charging bay)
- **Attributes:**
  - `point_code` (String — e.g., `H01-CP01`)
  - `power_rate_kw` (Float, not null — fixed charging rate per `A-04`)
  - `status` (Enum: `AVAILABLE`, `SCHEDULED`, `CHARGING`, `FAILED`, `MAINTENANCE`)
  - `version` (Integer, not null, default `1` — **Optimistic Locking** per `D-002`)
  - `updated_at` (Timestamp)

#### 4. `Vehicle`
Represents both shared fleet electric vehicles (250 rental vehicles in `A-11`) and registered student-owned private EVs (100 private EVs in `A-11`) to allow unified parking and charging association, distinguished by `ownership_type`. *(Note for M1 coordination: can be mapped as Single-Table Inheritance or separate `PrivateVehicle` table during Phase 1 review).*
- **Primary Key:** `vehicle_id` (String / UUID)
- **Foreign Keys:**
  - `current_hub_id` $\rightarrow$ `Hub.hub_id` (nullable — `NULL` when `InUse` between Hubs)
  - `current_parking_space_id` $\rightarrow$ `ParkingSpace.parking_space_id` (nullable)
  - `owner_user_id` $\rightarrow$ `UserAccount.user_id` (nullable — `NULL` for `FLEET` vehicles; populated for `PRIVATE` EVs)
- **Attributes:**
  - `plate_or_code` (String, unique, not null)
  - `ownership_type` (Enum: `FLEET`, `PRIVATE`)
  - `vehicle_type` (Enum: `E_BIKE`, `E_SCOOTER`, `E_MOTORCYCLE` — 3 types per `A-03`)
  - `battery_level_pct` (Integer / Float, $0 \le \text{value} \le 100$)
  - `battery_capacity_kwh` (Float, $> 0$)
  - `status` (Enum matching M1 State Machine: `AVAILABLE`, `RESERVED`, `IN_USE`, `RETURNED`, `CHARGING`, `MAINTENANCE`)
  - `version` (Integer, not null, default `1` — **Optimistic Locking** per `D-002`)
  - `updated_at` (Timestamp)

---

### 3.2 Group B — Actors & Accounts (`M1` / `M2`)

#### 5. `UserAccount`
Represents seeded user accounts for students and operators (`A-06`).
- **Primary Key:** `user_id` (String / UUID)
- **Attributes:**
  - `university_id_or_code` (String, unique, not null — e.g., Student ID or Operator ID)
  - `full_name` (String, not null)
  - `email` (String, unique)
  - `role` (Enum: `STUDENT`, `OPERATOR`)
  - `has_private_ev` (Boolean, default `false`)
  - `is_active` (Boolean, default `true`)

---

### 3.3 Group C — Reservation & Trip Entities (`M2`)

#### 6. `Reservation`
Covers rental vehicle reservations (`FR-03`), destination/origin parking space reservations (`FR-05`), and private EV parking reservations (`FR-07`).
- **Primary Key:** `reservation_id` (String / UUID)
- **Foreign Keys:**
  - `user_id` $\rightarrow$ `UserAccount.user_id` (not null)
  - `vehicle_id` $\rightarrow$ `Vehicle.vehicle_id` (nullable — required for vehicle rental or private EV booking)
  - `pickup_hub_id` $\rightarrow$ `Hub.hub_id` (not null — target Hub for parking or vehicle pickup)
  - `return_hub_id` $\rightarrow$ `Hub.hub_id` (nullable — planned destination Hub for rental trip)
  - `reserved_parking_space_id` $\rightarrow$ `ParkingSpace.parking_space_id` (nullable)
- **Attributes:**
  - `reservation_type` (Enum: `FLEET_VEHICLE_RENTAL`, `PARKING_ONLY`, `PRIVATE_EV_PARKING_CHARGING`)
  - `created_at` (Timestamp, not null)
  - `scheduled_start_time` (Timestamp, not null)
  - `hold_expires_at` (Timestamp, not null — enforces hold-time limit BR)
  - `ended_at` (Timestamp, nullable)
  - `status` (Enum matching M2 State Machine: `PENDING`, `CONFIRMED`, `ACTIVE`, `COMPLETED`, `CANCELLED`, `EXPIRED`)
  - `cancellation_reason` (String, nullable)
  - `version` (Integer, not null, default `1` — **Optimistic Locking** per `D-002`)

#### 7. `Trip`
Tracks the actual hub-to-hub rental journey (`A-01`, `FR-04`) once a student picks up a reserved rental vehicle.
- **Primary Key:** `trip_id` (String / UUID)
- **Foreign Keys:**
  - `reservation_id` $\rightarrow$ `Reservation.reservation_id` (unique, not null)
  - `user_id` $\rightarrow$ `UserAccount.user_id` (not null)
  - `vehicle_id` $\rightarrow$ `Vehicle.vehicle_id` (not null)
  - `origin_hub_id` $\rightarrow$ `Hub.hub_id` (not null)
  - `destination_hub_id` $\rightarrow$ `Hub.hub_id` (nullable until return completed)
  - `return_parking_space_id` $\rightarrow$ `ParkingSpace.parking_space_id` (nullable until return completed)
- **Attributes:**
  - `pickup_time` (Timestamp, not null)
  - `return_time` (Timestamp, nullable)
  - `start_battery_pct` (Float, not null)
  - `end_battery_pct` (Float, nullable)
  - `status` (Enum: `IN_PROGRESS`, `COMPLETED`, `OVERDUE`, `INCIDENT_ABORTED`)

---

### 3.4 Group D — Charging Request & Smart Scheduling Entities (`M3`)

#### 8. `ChargingSession`
Represents both charging requests in the priority queue and active/completed charging sessions for fleet or private EVs (`FR-06`, `FR-07`, `FR-11`).
- **Primary Key:** `charging_session_id` (String / UUID)
- **Foreign Keys:**
  - `vehicle_id` $\rightarrow$ `Vehicle.vehicle_id` (not null)
  - `hub_id` $\rightarrow$ `Hub.hub_id` (not null)
  - `charging_point_id` $\rightarrow$ `ChargingPoint.charging_point_id` (nullable when still `REQUESTED` in queue; populated when `SCHEDULED`/`CHARGING`)
  - `requested_by_user_id` $\rightarrow$ `UserAccount.user_id` (nullable — student for private EV/manual request, operator, or `NULL` if system auto-queued on vehicle return)
  - `related_reservation_id` $\rightarrow$ `Reservation.reservation_id` (nullable — links to upcoming usage requirement or private EV slot)
- **Attributes:**
  - `request_type` (Enum: `FLEET_AUTO`, `FLEET_OPERATOR`, `PRIVATE_USER`)
  - `initial_battery_pct` (Float, not null)
  - `target_battery_pct` (Float, not null, default `80.0` or `100.0`)
  - `priority_score` (Float, not null — computed from battery threshold, upcoming reservation urgency, and waiting time)
  - `requested_at` (Timestamp, not null)
  - `scheduled_start_time` (Timestamp, nullable)
  - `scheduled_end_time` (Timestamp, nullable)
  - `actual_start_time` (Timestamp, nullable)
  - `actual_end_time` (Timestamp, nullable)
  - `status` (Enum matching M3 State Machine: `REQUESTED`, `SCHEDULED`, `CHARGING`, `COMPLETED`, `INTERRUPTED`, `FAILED`)
  - `failure_or_interrupt_reason` (String, nullable)

---

### 3.5 Group E — Resource Allocation & Vehicle Dispatching Entities (`M4`)

#### 9. `RedistributionTask`
Represents an operator-approved or system-generated vehicle dispatching order to rebalance rental vehicles between Hubs (`FR-10`).
- **Primary Key:** `task_id` (String / UUID)
- **Foreign Keys:**
  - `source_hub_id` $\rightarrow$ `Hub.hub_id` (not null)
  - `destination_hub_id` $\rightarrow$ `Hub.hub_id` (not null)
  - `vehicle_id` $\rightarrow$ `Vehicle.vehicle_id` (not null)
  - `target_parking_space_id` $\rightarrow$ `ParkingSpace.parking_space_id` (nullable — reserved at destination Hub)
  - `initiated_by_operator_id` $\rightarrow$ `UserAccount.user_id` (nullable)
- **Attributes:**
  - `priority_level` (Enum: `LOW`, `NORMAL`, `HIGH`, `URGENT`)
  - `status` (Enum: `PLANNED`, `IN_TRANSIT`, `COMPLETED`, `CANCELLED`)
  - `created_at` (Timestamp, not null)
  - `completed_at` (Timestamp, nullable)

---

### 3.6 Group F — Operator Monitoring & Incident Handling Entities (`M5`)

#### 10. `Incident`
Records operational failures such as damaged/unavailable vehicles, failed charging points, or blocked spaces (`FR-09`).
- **Primary Key:** `incident_id` (String / UUID)
- **Foreign Keys:**
  - `hub_id` $\rightarrow$ `Hub.hub_id` (not null)
  - `vehicle_id` $\rightarrow$ `Vehicle.vehicle_id` (nullable)
  - `charging_point_id` $\rightarrow$ `ChargingPoint.charging_point_id` (nullable)
  - `parking_space_id` $\rightarrow$ `ParkingSpace.parking_space_id` (nullable)
  - `reported_by_user_id` $\rightarrow$ `UserAccount.user_id` (nullable — `NULL` if reported automatically by `iot_sim`)
  - `assigned_operator_id` $\rightarrow$ `UserAccount.user_id` (nullable)
- **Attributes:**
  - `incident_type` (Enum: `CHARGING_POINT_FAILURE`, `PARKING_SENSOR_FAULT`, `HUB_CAPACITY_FULL`, `HUB_VEHICLE_DEFICIT`, `BATTERY_CRITICAL_FAULT`, `TELEMETRY_CONNECTION_LOSS`, `OVERDUE_VEHICLE`)
  - `severity` (Enum: `LOW`, `MEDIUM`, `HIGH`)
  - `escalation_level` (Integer, default `0` — increments per M5 escalation BRs)
  - `status` (Enum: `OPEN`, `IN_PROGRESS`, `ESCALATED`, `CLOSED`)
  - `description` (Text, not null)
  - `resolution_notes` (Text, nullable)
  - `created_at` (Timestamp, not null)
  - `resolved_at` (Timestamp, nullable)

#### 11. `CapacityAlert`
Tracks utilization warnings when a Hub approaches parking or charging capacity limits (`FR-08`).
- **Primary Key:** `alert_id` (String / UUID)
- **Foreign Keys:**
  - `hub_id` $\rightarrow$ `Hub.hub_id` (not null)
  - `acknowledged_by_operator_id` $\rightarrow$ `UserAccount.user_id` (nullable)
- **Attributes:**
  - `alert_type` (Enum: `PARKING_NEAR_CAPACITY`, `PARKING_FULL`, `VEHICLE_SHORTAGE`, `CHARGING_QUEUE_CONGESTION`)
  - `utilization_pct` (Float, not null)
  - `threshold_pct` (Float, not null)
  - `status` (Enum: `ACTIVE`, `ACKNOWLEDGED`, `AUTO_RESOLVED`)
  - `triggered_at` (Timestamp, not null)
  - `resolved_at` (Timestamp, nullable)

---

### 3.7 Group G — What-if Simulation & Recommendation Metadata (`M6`)

*(Note: Transient simulated states of hubs/vehicles/chargers live strictly in memory per `NFR-12`. These two entities store the scenario execution log and output recommendations for the Operator Dashboard).*

#### 12. `SimulationRun`
- **Primary Key:** `simulation_run_id` (String / UUID)
- **Foreign Keys:**
  - `operator_id` $\rightarrow$ `UserAccount.user_id` (not null)
  - `target_hub_id` $\rightarrow$ `Hub.hub_id` (nullable — if scenario targets a specific Hub)
- **Attributes:**
  - `scenario_type` (Enum matching M6's 5 standard scenarios: `DEMAND_SURGE`, `HUB_AT_CAPACITY`, `CHARGING_SURGE`, `CHARGING_POINT_FAILURE`, `VEHICLE_IMBALANCE`)
  - `random_seed` (Integer, not null — ensures reproducibility per `NFR-13`)
  - `config_parameters_json` (JSON / Text — configurable inputs such as surge multiplier, failure ratio, duration)
  - `snapshot_taken_at` (Timestamp, not null)
  - `impact_metrics_json` (JSON / Text — unmet reservations, peak utilization %, avg charging wait time)
  - `executed_at` (Timestamp, not null)

#### 13. `CoordinationRecommendation`
- **Primary Key:** `recommendation_id` (String / UUID)
- **Foreign Keys:**
  - `simulation_run_id` $\rightarrow$ `SimulationRun.simulation_run_id` (not null)
  - `source_hub_id` $\rightarrow$ `Hub.hub_id` (nullable)
  - `destination_hub_id` $\rightarrow$ `Hub.hub_id` (nullable)
- **Attributes:**
  - `action_type` (Enum: `REDISTRIBUTE_VEHICLES`, `REPRIORITIZE_CHARGING`, `REDIRECT_USERS_TO_ALT_HUB`)
  - `recommended_quantity` (Integer, nullable)
  - `rationale` (Text, not null)
  - `estimated_impact_improvement` (String / JSON)

---

## 4. Relationship & Cardinality Matrix

| Parent Entity | Child Entity | Cardinality | Relationship Semantics |
|---|---|---|---|
| `Hub` | `ParkingSpace` | `1 : N` | A Hub contains multiple parking spaces; each space belongs to exactly one Hub. |
| `Hub` | `ChargingPoint` | `1 : N` | A Hub contains multiple charging points; each point belongs to one Hub. |
| `Hub` | `Vehicle` | `1 : 0..N` | A Hub currently hosts zero or more parked vehicles (`NULL` when a vehicle is `IN_USE`). |
| `ParkingSpace` | `Vehicle` | `0..1 : 0..1` | An occupied parking space holds at most one vehicle at any instant. |
| `UserAccount` | `Vehicle` | `0..1 : 0..N` | A student may register private EV(s); fleet vehicles have `owner_user_id = NULL`. |
| `UserAccount` | `Reservation` | `1 : 0..N` | A student places zero or more reservations over time. |
| `Reservation` | `Trip` | `1 : 0..1` | A confirmed vehicle reservation results in at most one completed/active rental trip. |
| `Vehicle` | `ChargingSession` | `1 : 0..N` | A vehicle participates in multiple charging sessions over its lifecycle (at most one active at a time). |
| `ChargingPoint` | `ChargingSession` | `0..1 : 0..N` | A charging point serves many sessions over time, but at most one `CHARGING` session at a time (`A-04`). |
| `Hub` | `RedistributionTask` | `1 : 0..N` | A Hub acts as source or destination for multiple vehicle redistribution tasks. |
| `Hub` / `Vehicle` / `ChargingPoint` | `Incident` | `1 : 0..N` | Operational incidents are logged against a Hub and optionally a specific failed vehicle or charger. |
| `SimulationRun` | `CoordinationRecommendation` | `1 : 1..N` | Each What-if Simulation run produces one or more coordination recommendations. |

---

## 5. Draft Conceptual ERD Preview (Mermaid)

```mermaid
erDiagram
    HUB ||--o{ PARKING_SPACE : "contains"
    HUB ||--o{ CHARGING_POINT : "contains"
    HUB ||--o{ VEHICLE : "currently hosts"
    HUB ||--o{ CAPACITY_ALERT : "triggers"
    HUB ||--o{ INCIDENT : "logs"

    USER_ACCOUNT ||--o{ RESERVATION : "places"
    USER_ACCOUNT ||--o{ VEHICLE : "owns (if PRIVATE)"
    USER_ACCOUNT ||--o{ SIMULATION_RUN : "executes"

    VEHICLE ||--o{ RESERVATION : "booked in"
    PARKING_SPACE ||--o{ RESERVATION : "reserved in"
    RESERVATION ||--o| TRIP : "initiates"

    VEHICLE ||--o{ CHARGING_SESSION : "requests"
    CHARGING_POINT ||--o{ CHARGING_SESSION : "serves"

    HUB ||--o{ REDISTRIBUTION_TASK : "source / destination"
    VEHICLE ||--o{ REDISTRIBUTION_TASK : "dispatched in"

    VEHICLE ||--o{ INCIDENT : "involves"
    CHARGING_POINT ||--o{ INCIDENT : "involves"

    SIMULATION_RUN ||--|{ COORDINATION_RECOMMENDATION : "generates"