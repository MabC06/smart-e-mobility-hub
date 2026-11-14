# Database Schema

> Owner: M7 (Nguyễn Trung Kiên) · Date: 2026-11-10 · Reviewer: M5 (Đỗ Hoàng Việt)
> Sources: `erd.md` (Figures 3.4 to 3.7); the code of `core` on `develop` (`6777736`); the code of M2, M4 and M5 on their open branches (Section 1). Every table, column and constraint below was read from the code, and the DDL that SQLAlchemy generates from it was checked against this document.

## 1. Scope

This document maps the ERD (`erd.md`) to the SQLite schema that the code creates. It lists every table with its columns, keys and CHECK constraints, and says which part of the code owns it.

- The whole system uses one SQLite database, set by `DATABASE_URL` (`src/main.py:133`). If it is empty, the database is in memory (`sqlite://`) and is lost when the app stops. `sqlite:///data/hub.db` keeps it in a file (`.env.example:13`).
- Every connection switches foreign keys on. A file database also uses write-ahead logging (`src/core/repository/sql.py:62-66`).
- There is no migration tool. `core` creates its tables with `metadata.create_all` when the repository opens (`sql.py:95-103`). A module's table is created when the module registers it in `install` (`sql.py:105-109`), so the table of a module that is not installed does not exist.
- Module tables are written in the same transaction as `core`'s tables: a change to a vehicle and the module's record commit or roll back together (NFR-09, D-018, `core-api-spec.md` Section 5.2).

| Owner | Tables | Source | Status |
|---|---|---|---|
| `core` | 7 entity tables (Section 4) and 3 internal tables (Section 5) | `src/core/repository/schema.py` | On `develop` |
| M2 | `rental_reservations`, `rental_trips` | `origin/feat/reservation-booking-flow` (`e25578d`) | Not merged |
| M4 | `m4_dispatch_tasks` | `origin/feat/allocation-phase2` (`64a07a1`) | Not merged |
| M5 | `monitoring_incidents`, `monitoring_incident_audit_logs` | `origin/feat/monitoring-incident` (`650cfc0`) | Not merged |
| M3, M6 | None: the code keeps its data in memory | `origin/feat/charging-phase2`, `origin/feat/m6-simulation-impl` | Not merged |

With all three module branches installed, the database has 15 tables.

## 2. How a table is registered

Each stored entity has a `TableSpec(entity, table, id_column, enums, versioned)` (`schema.py:242-248`). `core` has eight, one per entity of the class diagram (`schema.py:251-281`). A module adds its own with `core.register_entity(spec)` in `install` (D-018).

| Field | Meaning |
|---|---|
| `entity` | The dataclass stored in the table |
| `table` | The SQLAlchemy `Table`, built on `core`'s `metadata` so that foreign keys to `core`'s tables resolve |
| `id_column` | The primary-key column |
| `enums` | Columns whose stored text is turned back into an enum when a row is read (`sql.py:246-250`) |
| `versioned` | The row has a `version` column for optimistic locking: an update is `UPDATE ... WHERE id = ? AND version = ?`, and no changed row is a `VersionConflictError` (`sql.py:289-317`, D-018) |

`check_spec` (`schema.py:284-315`) and `add_spec` (`schema.py:318-338`) refuse a module's spec with a `ValueError` unless:

1. The entity is a dataclass.
2. Its class name is not the name of a `core` entity, because the change log identifies entities by class name.
3. Its `ID_FIELD` equals `id_column`, and that column is in the table.
4. The dataclass fields and the table columns are exactly the same names.
5. `versioned` equals the class attribute `VERSIONED`, and a versioned entity has a `version` field.
6. Every column named in `enums` is in the table.
7. No other registered class has the same name, and no other spec uses the same table name. Registering the same spec again does nothing.

The five module specs of Section 6 pass these checks.

## 3. Type mapping

| Field type in the dataclass | Column type in SQLite | Notes |
|---|---|---|
| `str`, `int`, `float`, `bool` | `VARCHAR`, `INTEGER`, `FLOAT`, `BOOLEAN` | M5 uses `TEXT` for three long text columns (Section 6.3) |
| `datetime` | `DATETIME` through `UtcDateTime` | Stored as UTC without a zone and read back as aware UTC; a time without a zone is refused (`schema.py:58-72`, D-005) |
| `StrEnum` | `VARCHAR` with the enum's value | `core` adds `CHECK (column IN (...))` named `ck_<table>_<column>` (`_in_values`, `schema.py:78-80`). M2 writes its own CHECK. M4 and M5 have none |
| `dict` | `JSON` | Only `domain_events.payload` |
| `T \| None` | The same type, nullable | Every other column is `NOT NULL` |

## 4. core tables

These are the seven tables of Figure 3.4 in `erd.md`. Columns are in table order, and each column has the same name as the entity's field (rule 4 of Section 2). `PK` primary key, `FK` foreign key, `UK` unique. The enumerated values are in `erd.md` Section 6, and the rules that need several rows (capacity, overlapping claims, state transitions) are in `erd.md` Section 7.

### 4.1 `hubs`

Entity `Hub` (`entities.py:31-47`), table `schema.py:83-99`, versioned.

| Column | Type | Null | Key |
|---|---|---|---|
| `hub_id` | `VARCHAR` | No | PK |
| `name` | `VARCHAR` | No | UK |
| `zone_code` | `VARCHAR` | No | |
| `parking_capacity` | `INTEGER` | No | |
| `charging_point_count` | `INTEGER` | No | |
| `status` | `VARCHAR` | No | |
| `version` | `INTEGER` | No | |

CHECK: `ck_hubs_capacity` (`parking_capacity > 0`), `ck_hubs_charging_points` (`0 <= charging_point_count <= parking_capacity`, D-007), `ck_hubs_status` (`HubStatus`).

- `status` is stored. `core` does not derive it from occupancy: M5 decides `WARNING` or `CRITICAL` and `core` stores it with `set_hub_status` (`src/core/services/commands.py:838-842`).
- The counters (occupied spaces, occupancy ratio, charging points in use) are not columns. `core` computes them from the spaces when a Hub is read (`entities.py:5`, NFR-07).

### 4.2 `user_accounts`

Entity `UserAccount` (`entities.py:157-165`), table `schema.py:101-110`, not versioned.

| Column | Type | Null | Key |
|---|---|---|---|
| `user_id` | `VARCHAR` | No | PK |
| `code` | `VARCHAR` | No | UK |
| `role` | `VARCHAR` | No | |
| `is_active` | `BOOLEAN` | No | |
| `password_hash` | `VARCHAR` | Yes | |

CHECK: `ck_user_accounts_role` (`Role`).

- `password_hash` holds a salted hash, never the password (`entities.py:165`, NFR-17). An account with no hash cannot log in (`src/core/auth.py:161`).

### 4.3 `parking_spaces`

Entity `ParkingSpace` (`entities.py:50-59`), table `schema.py:112-123`, versioned.

| Column | Type | Null | Key |
|---|---|---|---|
| `parking_space_id` | `VARCHAR` | No | PK |
| `hub_id` | `VARCHAR` | No | FK → `hubs` |
| `label` | `VARCHAR` | No | UK with `hub_id` (`uq_parking_spaces_label`) |
| `status` | `VARCHAR` | No | |
| `occupant_vehicle_id` | `VARCHAR` | Yes | |
| `version` | `INTEGER` | No | |

CHECK: `ck_parking_spaces_status` (`SpaceStatus`).

- `occupant_vehicle_id` has no foreign key. The link the database checks is `vehicles.parking_space_id` (Section 4.5), and `core` keeps both sides equal (`erd.md` Section 3).

### 4.4 `charging_points`

Entity `ChargingPoint` (`entities.py:62-75`), table `schema.py:125-142`, versioned.

| Column | Type | Null | Key |
|---|---|---|---|
| `charging_point_id` | `VARCHAR` | No | PK |
| `hub_id` | `VARCHAR` | No | FK → `hubs` |
| `parking_space_id` | `VARCHAR` | No | FK → `parking_spaces`, UK |
| `power_rate_kw` | `FLOAT` | No | |
| `status` | `VARCHAR` | No | |
| `version` | `INTEGER` | No | |

CHECK: `ck_charging_points_power` (`power_rate_kw > 0`), `ck_charging_points_status` (`ChargingPointStatus`).

- The unique `parking_space_id` makes a charging point 1-1 with its bay (D-007).

### 4.5 `vehicles`

Entity `Vehicle` (`entities.py:78-100`), table `schema.py:144-181`, versioned.

| Column | Type | Null | Key |
|---|---|---|---|
| `vehicle_id` | `VARCHAR` | No | PK |
| `plate_or_code` | `VARCHAR` | No | UK |
| `ownership` | `VARCHAR` | No | |
| `vehicle_type` | `VARCHAR` | No | |
| `battery_pct` | `FLOAT` | No | |
| `battery_capacity_kwh` | `FLOAT` | No | |
| `state` | `VARCHAR` | No | |
| `fault_flag` | `BOOLEAN` | No | |
| `hub_id` | `VARCHAR` | Yes | FK → `hubs` |
| `parking_space_id` | `VARCHAR` | Yes | FK → `parking_spaces`, UK |
| `owner_user_id` | `VARCHAR` | Yes | FK → `user_accounts` |
| `connector_type` | `VARCHAR` | Yes | |
| `version` | `INTEGER` | No | |

CHECK: `ck_vehicles_battery` (`0 <= battery_pct <= 100`), `ck_vehicles_capacity` (`battery_capacity_kwh > 0`), `ck_vehicles_location` (`hub_id` and `parking_space_id` both null or both set), `ck_vehicles_owner` (`PRIVATE` with an `owner_user_id`, `FLEET` without), `ck_vehicles_ownership` (`Ownership`), `ck_vehicles_vehicle_type` (`VehicleType`), `ck_vehicles_state` (`VehicleState`).

- The unique `parking_space_id` means one vehicle per space.

### 4.6 `resource_claims`

Entity `ResourceClaim` (`entities.py:103-122`), table `schema.py:183-199`, not versioned.

| Column | Type | Null | Key |
|---|---|---|---|
| `claim_id` | `VARCHAR` | No | PK |
| `resource_type` | `VARCHAR` | No | Index `ix_resource_claims_resource` with `resource_id` |
| `resource_id` | `VARCHAR` | No | |
| `holder_kind` | `VARCHAR` | No | |
| `holder_ref` | `VARCHAR` | No | |
| `start_at` | `DATETIME` | No | |
| `end_at` | `DATETIME` | No | |
| `status` | `VARCHAR` | No | |

CHECK: `ck_resource_claims_interval` (`start_at < end_at`), `ck_resource_claims_resource_type` (`ResourceType`), `ck_resource_claims_holder_kind` (`HolderKind`), `ck_resource_claims_status` (`ClaimStatus`).

- No column is a foreign key: `resource_id` can name a vehicle, a space or a charging point, and `holder_ref` names a module's record, so `core` does not depend on module tables (D-003, D-017). `core` checks that the resource exists (`erd.md` Section 3).

### 4.7 `state_change_records`

Entity `StateChangeRecord` (`entities.py:125-141`), table `schema.py:201-213`, not versioned.

| Column | Type | Null | Key |
|---|---|---|---|
| `record_id` | `VARCHAR` | No | PK |
| `at` | `DATETIME` | No | |
| `entity_type` | `VARCHAR` | No | |
| `entity_id` | `VARCHAR` | No | Index `ix_state_change_records_entity` |
| `previous_state` | `VARCHAR` | No | |
| `new_state` | `VARCHAR` | No | |
| `trigger` | `VARCHAR` | No | |
| `actor` | `VARCHAR` | No | |

- `core` adds one row for each state change, in the same transaction as the change (`src/core/services/runtime.py:65-85`, NFR-25). The index serves the log of one entity.
- `entity_type` and `entity_id` can name any entity, so there is no foreign key.

## 5. core's internal tables

`schema.py` creates three more tables that are not in the ERD.

| Table | Columns | Purpose |
|---|---|---|
| `meta` (`schema.py:226-231`) | `key VARCHAR` PK, `value INTEGER` not null | One row, `key = 'version'`: the commit counter. It starts at 0 (`sql.py:99-103`) and goes up by one at each commit that wrote a record (`sql.py:161-181`). |
| `change_log` (`schema.py:233-239`) | `entity_type VARCHAR`, `entity_id VARCHAR` (together the PK), `version INTEGER` not null | For each record, the commit counter at which it was last written, also for module records. `unit_of_work(snapshot_version=...)` uses it to find records changed since a snapshot (`sql.py:221-233`). `entity_type` is the class name, which is why rules 2 and 7 of Section 2 forbid two classes with the same name. |
| `domain_events` (`schema.py:215-222`) | `event_id VARCHAR` PK, `type VARCHAR`, `at DATETIME`, `payload JSON`, all not null | Has a `TableSpec` (`schema.py:278`), but no code writes to it: events go through the in-memory `EventBus` (`runtime.py:60-63`). |

- `meta` and `change_log` have no `TableSpec`. They are not entities, and only the repository writes them, in the same transaction as the data.
- They are not drawn in the ERD because they hold no domain data (`erd.md` Section 3). `domain_events` is an open point for M1: remove it or store events (`erd.md` Section 10, point 7).

## 6. Module tables

Each module builds its tables on `core`'s `metadata` and registers them with `core.register_entity` in `install` (Section 2). None of these branches is merged, so `develop` does not have these tables yet. Paths below are on the module's branch.

| Spec | Entity | Table | `id_column` | `enums` | `versioned` | Code |
|---|---|---|---|---|---|---|
| `RESERVATION_SPEC` | `RentalReservation` | `rental_reservations` | `reservation_id` | `status` | `True` | `src/reservation/storage.py:66-68` |
| `TRIP_SPEC` | `RentalTrip` | `rental_trips` | `trip_id` | `status` | `True` | `src/reservation/storage.py:69` |
| `DISPATCH_TASK_SPEC` | `DispatchTask` | `m4_dispatch_tasks` | `task_id` | `status`, `vehicle_type` | `True` | `src/allocation/models.py:81-87` |
| `INCIDENT_SPEC` | `IncidentTicket` | `monitoring_incidents` | `incident_id` | `incident_type`, `severity`, `status` | `True` | `src/monitoring/schema.py:56-66` |
| `AUDIT_SPEC` | `TicketAuditLog` | `monitoring_incident_audit_logs` | `log_id` | `previous_status`, `new_status` | `False` | `src/monitoring/schema.py:68-77` |

### 6.1 M2: `rental_reservations` and `rental_trips`

Branch `origin/feat/reservation-booking-flow`. Entities `RentalReservation` and `RentalTrip` (`src/reservation/models.py:41-76`), tables `src/reservation/storage.py:18-65`. `install` calls `register_tables` (`src/reservation/__init__.py:12-17`, `storage.py:72-75`).

`rental_reservations`:

| Column | Type | Null | Key |
|---|---|---|---|
| `reservation_id` | `VARCHAR` | No | PK |
| `user_id` | `VARCHAR` | No | FK → `user_accounts` |
| `vehicle_id` | `VARCHAR` | No | FK → `vehicles` |
| `origin_hub_id` | `VARCHAR` | No | FK → `hubs` |
| `destination_hub_id` | `VARCHAR` | Yes | FK → `hubs` |
| `selected_min_battery` | `FLOAT` | No | |
| `planned_duration_minutes` | `INTEGER` | No | |
| `confirmed_at` | `DATETIME` | No | |
| `hold_expires_at` | `DATETIME` | No | |
| `claim_id` | `VARCHAR` | No | FK → `resource_claims`, UK |
| `status` | `VARCHAR` | No | |
| `version` | `INTEGER` | No | |

CHECK (no names): `selected_min_battery BETWEEN 0 AND 100`, `planned_duration_minutes BETWEEN 5 AND 120`, `confirmed_at < hold_expires_at`, `status IN ('CONFIRMED','ACTIVE','COMPLETED','CANCELLED','EXPIRED')`.

`rental_trips`:

| Column | Type | Null | Key |
|---|---|---|---|
| `trip_id` | `VARCHAR` | No | PK |
| `reservation_id` | `VARCHAR` | No | FK → `rental_reservations`, UK |
| `user_id` | `VARCHAR` | No | FK → `user_accounts` |
| `vehicle_id` | `VARCHAR` | No | FK → `vehicles` |
| `origin_hub_id` | `VARCHAR` | No | FK → `hubs` |
| `picked_up_at` | `DATETIME` | No | |
| `expected_return_at` | `DATETIME` | No | |
| `status` | `VARCHAR` | No | |
| `returned_at` | `DATETIME` | Yes | |
| `return_hub_id` | `VARCHAR` | Yes | FK → `hubs` |
| `return_space_id` | `VARCHAR` | Yes | FK → `parking_spaces` |
| `version` | `INTEGER` | No | |

CHECK (no names): `picked_up_at < expected_return_at`, `status IN ('IN_PROGRESS','COMPLETED','OVERDUE','INCIDENT_ABORTED')`, and `returned_at`, `return_hub_id`, `return_space_id` all null or all set.

- The unique `claim_id` gives each reservation its own claim, and the unique `reservation_id` allows at most one trip per reservation.
- M2 is the only module that writes CHECK constraints for its enums.

### 6.2 M4: `m4_dispatch_tasks`

Branch `origin/feat/allocation-phase2`. Entity `DispatchTask` (`src/allocation/models.py:28-63`), table `models.py:66-79`. `install` registers it (`src/allocation/__init__.py:21-29`).

| Column | Type | Null | Key |
|---|---|---|---|
| `task_id` | `VARCHAR` | No | PK |
| `source_hub_id` | `VARCHAR` | No | FK → `hubs` |
| `target_hub_id` | `VARCHAR` | No | FK → `hubs` |
| `vehicle_type` | `VARCHAR` | No | |
| `quantity` | `INTEGER` | No | |
| `vehicle_ids` | `VARCHAR` | No | |
| `status` | `VARCHAR` | No | |
| `priority` | `INTEGER` | No | |
| `reason` | `VARCHAR` | No | |
| `version` | `INTEGER` | No | |

No CHECK constraint.

- `vehicle_ids` is one text column of vehicle IDs separated by commas (`models.py:43`), so the database cannot check them against `vehicles`.
- `vehicle_type` uses `core`'s `VehicleType`, and `status` uses `DispatchTaskStatus` (`models.py:16-25`). Both are checked only when a row is read back as an enum.
- The defaults of `vehicle_ids`, `priority`, `reason` and `version` (`models.py:74-78`) are set by SQLAlchemy on insert. They are not `DEFAULT` clauses in the table.

### 6.3 M5: `monitoring_incidents` and `monitoring_incident_audit_logs`

Branch `origin/feat/monitoring-incident`. Entities `IncidentTicket` and `TicketAuditLog` (`src/monitoring/domain.py:43-87`), tables `src/monitoring/schema.py:20-54`. `install` registers both (`src/monitoring/__init__.py:20-31`).

`monitoring_incidents`:

| Column | Type | Null | Key |
|---|---|---|---|
| `incident_id` | `VARCHAR` | No | PK |
| `incident_type` | `VARCHAR` | No | |
| `severity` | `VARCHAR` | No | |
| `status` | `VARCHAR` | No | |
| `hub_id` | `VARCHAR` | No | FK → `hubs` |
| `entity_type` | `VARCHAR` | No | |
| `entity_id` | `VARCHAR` | No | |
| `error_code` | `VARCHAR` | Yes | |
| `description` | `TEXT` | No | |
| `reported_by` | `VARCHAR` | No | |
| `assigned_operator_id` | `VARCHAR` | Yes | |
| `resolution_notes` | `TEXT` | Yes | |
| `created_at` | `DATETIME` | No | |
| `acknowledged_at` | `DATETIME` | Yes | |
| `escalated_at` | `DATETIME` | Yes | |
| `resolved_at` | `DATETIME` | Yes | |
| `closed_at` | `DATETIME` | Yes | |
| `version` | `INTEGER` | No | |

`monitoring_incident_audit_logs`:

| Column | Type | Null | Key |
|---|---|---|---|
| `log_id` | `VARCHAR` | No | PK |
| `incident_id` | `VARCHAR` | No | FK → `monitoring_incidents` |
| `previous_status` | `VARCHAR` | No | |
| `new_status` | `VARCHAR` | No | |
| `changed_by` | `VARCHAR` | No | |
| `action` | `VARCHAR` | No | |
| `reason` | `TEXT` | Yes | |
| `timestamp` | `DATETIME` | No | |

No CHECK constraint in either table.

- `incident_type` stores the enum's value, which is the incident code such as `INC-HW-01`, not the member name `CHARGING_POINT_FAILURE` (`domain.py:18-25`).
- `action` is a plain string, not an enum in the spec. The values are written by the service: `CREATE`, `ACKNOWLEDGE`, `ESCALATE`, `RESOLVE`, `CLOSE` (`src/monitoring/service.py:240, 282, 321, 365, 403`).
- `entity_type`, `entity_id`, `reported_by`, `changed_by` and `assigned_operator_id` have no foreign key.

### 6.4 Modules with no table

| Module | Where the data is kept | Evidence |
|---|---|---|
| M3 | The charging requests are a Python list in `ChargingQueueService` | `origin/feat/charging-phase2:src/charging/service.py:8`; `src/charging/__init__.py` has no `install` |
| M6 | A run returns a `SimulationReport` and stores nothing | `origin/feat/m6-simulation-impl:src/simulation/service.py:16-27`; `src/simulation/__init__.py` is empty |

The charging queue is lost when the app stops, and simulation results are not kept. Section 7 lists this as a limitation.

## 7. Differences between the ERD and the code

### 7.1 Found while writing this document

| # | `erd.md` | Code (branch `origin/feat/monitoring-incident` for rows 1 and 2) | Proposed action |
|---|---|---|---|
| 1 | Section 6 lists `monitoring_incidents.incident_type` by member name, with the code in brackets | The stored value is the code, such as `INC-HW-01` (`src/monitoring/domain.py:18-25`) | M7: say in `erd.md` Section 6 that the code is the stored value |
| 2 | Section 6 lists `monitoring_incident_audit_logs.action` as an enumerated column | A plain string, not in `AUDIT_SPEC`'s `enums` (`src/monitoring/schema.py:68-77`); the values exist only in M5's service | M5: make it an enum, or M7 marks it in `erd.md` Section 6 as values used by the service |
| 3 | Not stated | M4 and M5 have no CHECK on their enum columns, while `core` and M2 have. A wrong value is stored and fails only when the row is read back (`sql.py:246-250`) | M4, M5: add CHECK constraints as M2 does |

### 7.2 Limitations

- M3 and M6 store nothing (Section 6.4). The charging queue is lost when the app stops; `erd.md` Section 5 expects a `charging_session` table.
- With an empty `DATABASE_URL` the whole database is in memory and is lost when the app stops (Section 1). A demo that must survive a restart needs a file URL (`.env.example:13`).
- There is no migration tool. `create_all` only creates missing tables (`sql.py:95-98`), so a changed table in an existing database file is not altered.

### 7.3 Open points from `erd.md` Section 10

The points that affect the schema are still open, checked on 2026-11-10 against the branches in Section 1:

- Point 1: `PENDING` is not stored. M2's code has five statuses (`src/reservation/models.py:9-14`).
- Point 2: `vehicle_ids` is still a comma-separated column (Section 6.2).
- Point 5: M3 still has no table and no session status (Section 6.4).
- Point 6: M2 still has no parking-reservation fields; its branch has only the two rental tables.
- Point 7: `domain_events` is still created and not written.
- Point 8: `architecture-diagram.md` Section 6 still lists the Phase 0 table names of M2 to M6 (`architecture-diagram.md:104`).

Points 3 and 4 are about the design documents of M4 and M5 and do not change the schema.
