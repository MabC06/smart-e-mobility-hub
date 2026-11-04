# Core API Specification

**Owner:** M1 — Đoàn Nhật Minh (2452738)
**Version:** v1.1 · 2026-11-04 — D-020 splits the port `DemandSource` into `ReservationDemand` (M2) and `ChargingDemand` (M3), decided by their owners (§6.1, §10 point 10). v1.0 (2026-11-04) was the first released version, decided by the Lead; checked against the module PRs after their round-2 fixes. From now on every change follows D-006 (entry in `DECISIONS.md`, version bump, M1 approves the PR).
**Related:** `class-diagram-core.md`, `vehicle-state-machine.md`, `docs/requirements/fr-01-core.md`, D-003, D-005, D-006

## 1. Purpose

The only way for other modules to read or change Hub, vehicle, parking-space and charging-point state (D-003). Modules call it in-process (modular monolith, A-08) through `CoreFacade`. A small part is also exposed as REST for the UI (section 7). The interface is written as Python protocols with Pydantic types, so M2–M6 can code against stubs until the real `core` lands.

## 2. Conventions

| Topic | Rule |
|---|---|
| Time | All timestamps are UTC (`datetime`, timezone-aware). `core` reads time from an injected `Clock`; callers never pass "now" (D-005). |
| IDs | Opaque strings. Dataset IDs: `H01`…`H10` for Hubs (`reference-dataset.md`). |
| Optimistic locking | Every command that changes an entity carries `expected_version`. A mismatch gives `VERSION_CONFLICT` and changes nothing (D-002). |
| Actor | Every command carries `actor: Actor(user_id, role, module)`. A role that may not run the command gives `FORBIDDEN` (NFR-16). `module` is the calling module, written to the state-change log (NFR-25). |
| Errors | Commands never raise for business failures. They return `Result[T]` = `Ok(value)` or `Err(code, message, details)`. Malformed input gives `INVALID_INPUT` (NFR-18). |
| Atomicity | One command is atomic. Several commands that must succeed together run in a `UnitOfWork` (section 5), all-or-nothing (NFR-09). |
| Idempotency | `core` has no store of past command results. A command repeated after it succeeded is judged on the current state: for most it returns a state error (e.g. `INVALID_TRANSITION`), which the calling module treats as "already done". Returning the earlier result of a retried request is the caller's job (decided: M2 reads its own Reservation / Trip record before it calls `core`; if two identical requests race and one loses with `VERSION_CONFLICT` or `INVALID_TRANSITION`, M2 re-reads its record and returns the outcome the winner recorded). The one exception is `place_claim`, which returns the existing claim when the same holder repeats the same request. |
| Logging | Each successful state change writes a `StateChangeRecord` (NFR-25). |

## 3. Error codes

| Code | When |
|---|---|
| `UNAUTHENTICATED` | No token, a bad or expired token, or a wrong account or password (REST only). |
| `INVALID_INPUT` | Missing field, wrong type, value out of range (e.g. battery 120). |
| `NOT_FOUND` | Unknown entity ID. |
| `FORBIDDEN` | Role or module not allowed for this command. |
| `VERSION_CONFLICT` | `expected_version` differs from the current version. |
| `INVALID_TRANSITION` | The Vehicle state machine does not allow this event in the current state (`BR-M1-03`). |
| `CLAIM_CONFLICT` | The new claim overlaps an active claim on the same resource (`BR-M1-01`). |
| `HUB_FULL` | Occupying a space would exceed the Hub's capacity, or no free space exists (`BR-M1-02`). |
| `SPACE_NOT_FREE` | The named space is occupied or in maintenance. |
| `RESOURCE_UNAVAILABLE` | The vehicle, space or charging point is in `MAINTENANCE`, `OUT_OF_SERVICE` or has a fault flag. |
| `BATTERY_TOO_LOW` | Guard of `reserve` / `mark_ready` failed. |
| `INTERNAL_ERROR` | Unexpected failure; the transaction is rolled back. |

Each error code has at least one test (NFR-08, NFR-18).

### 3.1 Mapping to M2's result codes

M2's design uses its own result names and asked M1 for a stable mapping (they are not an HTTP contract). Proposal:

| Core code | M2 design code |
|---|---|
| `VERSION_CONFLICT`, `CLAIM_CONFLICT` | `CONFLICT` |
| `HUB_FULL`, `SPACE_NOT_FREE` | `NO_PARKING` |
| `RESOURCE_UNAVAILABLE`, `BATTERY_TOO_LOW` | `RESOURCE_UNAVAILABLE` |
| `INVALID_TRANSITION` | `INVALID_STATE` |
| `NOT_FOUND` | `NOT_FOUND_OR_NOT_OWNED` |

Codes that M2 decides itself, not from `core`: `LIMIT_REACHED` (student quota), `HUB_CRITICAL` (M2 reads the Hub `status`), `EXPIRED`, `ALREADY_CANCELLED`, `LINKED_CHARGING`, `NO_VEHICLE`.

## 4. Read interface — `HubQueries`

Reads return the committed state. After a successful command, the next read shows it (NFR-01). Reads never take locks that block commands.

| Operation | Input | Output | Used by |
|---|---|---|---|
| `list_hubs()` | – | `HubView[]`: id, name, zone, `parking_capacity`, `occupied`, `free_spaces`, `charging_points`, `charging_in_use`, `available_vehicles` (rental fleet only, private EVs are not counted), `status` | UI, M2, M4, M5 (FR-01) |
| `get_hub(hub_id)` | hub id | `HubView` | all |
| `find_vehicles(filter)` | `hub_id?`, `state?`, `vehicle_type?`, `min_battery?`, `ownership?` | `VehicleView[]` sorted by `vehicle_id` | M2 (FR-02), M3, M4 |
| `get_vehicle(vehicle_id)` | id | `VehicleView`: state, battery, hub, space, `fault_flag`, `version` | all |
| `list_spaces(hub_id, status?)` | hub id | `SpaceView[]` | M2, M4 |
| `list_charging_points(hub_id, status?)` | hub id | `ChargingPointView[]` | M3, M5 |
| `find_free_space(hub_id, from, to, charging_bay?)` | hub id, window, optional bay filter | The lowest-numbered space of the Hub that is free and has no `ACTIVE` claim in the window, as a `SpaceView` (the same answer for the same state). Nothing is held: the caller places the claim with `place_claim`, which still decides on a conflict. `charging_bay = true` looks at bays only, `false` at ordinary spaces only. Errors: `HUB_FULL` (no such space), `NOT_FOUND`, `INVALID_INPUT` | M2, M4 |
| `get_claims(resource_id, from, to)` | resource id, window | `ClaimView[]` (active claims overlapping the window) | M2, M3, M4 |
| `get_state_log(entity_id, limit?)` | entity id | `StateChangeRecord[]` newest first | M5, operators (NFR-25) |
| `get_config()` | – | `CoreConfig`: `LOW_BATTERY_THRESHOLD` (15), near-capacity limit (90 %), `as_of` | M2, M3, M4, M5 (named configuration values, `nfr.md` note 3) |

`HubView` numbers satisfy `BR-M1-02`: `occupied ≤ parking_capacity` and `charging_points ≤ parking_capacity`.

Outputs are sorted by ID so results are the same in repeated runs (NFR-13). Every read result carries `as_of`, the UTC time of the commit it reflects, and every view carries `version`; M2's search (FR-02) shows both to the student.

## 5. Command interface — `StateCommands`

All commands return `Result[T]`. "Event" is published after commit only.

| Operation | Input | Effect | Errors | Event | Typical caller |
|---|---|---|---|---|---|
| `transition_vehicle(vehicle_id, event, expected_version, ctx)` | `event` is one of the events in `vehicle-state-machine.md` (`reserve`, `release_reservation`, `pickup`, `return`, `return_faulty`, `mark_ready`, `start_charging`, `finish_charging`, `interrupt_charging`, `report_fault`, `repair`, and for private EVs only `arrive`, `depart`); `ctx` carries `claim_id` (the claim that backs `reserve`, `pickup`, `start_charging`; for `return` and `arrive` the caller's hold on the destination space, which is consumed), `min_battery` for `reserve`, the destination `hub_id` or `parking_space_id` for `return`, `return_faulty` and `arrive` (with only a Hub, the lowest free space is chosen), `charging_point_id` for `start_charging`, and the new battery level when known | Applies the transition and its guard (T1–T15). After a successful `repair` (T12), `core` also applies `mark_ready` (T6) in the same call when its guard passes, so the result is `AVAILABLE`; both steps are logged and both `VehicleStateChanged` events are published. A private vehicle does not use the rental events (`reserve`, `release_reservation`, `pickup`, `return`, `return_faulty`) and a fleet vehicle does not use `arrive` and `depart`; these give `INVALID_TRANSITION`. `arrive` and `depart` need an operator, M2 or iot_sim (`FORBIDDEN` otherwise). `arrive` occupies a space like `return`; `depart` frees it (`vehicle-state-machine.md §7, point 1). `pickup` frees the origin space; `return` occupies a destination space; `start_charging` requires the bay | `NOT_FOUND`, `FORBIDDEN`, `VERSION_CONFLICT`, `INVALID_TRANSITION`, `BATTERY_TOO_LOW`, `HUB_FULL`, `SPACE_NOT_FREE`, `RESOURCE_UNAVAILABLE` | `VehicleStateChanged`, `SpaceOccupancyChanged` | M2, M3, M4, M5 |
| `place_claim(resource_type, resource_id, holder_kind, holder_ref, start_at, end_at)` | resource and interval, with `start_at < end_at` | Creates an `ACTIVE` claim if it overlaps none (`BR-M1-01`). If an `ACTIVE` claim with the same resource, `holder_kind`, `holder_ref` and interval already exists, returns that claim (a retry is not a conflict) | `INVALID_INPUT`, `NOT_FOUND`, `CLAIM_CONFLICT`, `RESOURCE_UNAVAILABLE` | `ClaimPlaced` | M2, M3, M4 |
| `release_claim(claim_id)` | claim id | Sets the claim to `RELEASED`; releasing twice returns the same claim (no error) | `NOT_FOUND`, `FORBIDDEN` | `ClaimReleased` | M2, M3, M4 |
| `register_vehicle(ownership, plate_or_code, vehicle_type, battery_capacity_kwh, battery_pct, connector_type?, owner_user_id?)` | `owner_user_id` and `connector_type` are required for `PRIVATE` | Creates a vehicle. Fleet vehicles come from the seed and start `AVAILABLE` in a space; a private EV is registered by M3 (`UC-M3-04`, `FR-07.M3.1`) for its owner and starts `IN_USE`, away from every Hub, until it arrives. M3 keeps the charging profile, `core` keeps the vehicle (`vehicle-state-machine.md` §7, point 1) | `INVALID_INPUT` (incl. duplicate `plate_or_code`), `NOT_FOUND` (owner), `FORBIDDEN` | – | M3, seed loader |
| `occupy_space(vehicle_id, parking_space_id, claim_id?, expected_version)` | A vehicle and a space | Private EV arrival (`UC-M2-08`): the same as the event `arrive` on that vehicle, so the vehicle goes from `IN_USE` to `AVAILABLE` and the space is occupied. With `claim_id`, the vehicle's claim on that space becomes the occupancy. A fleet vehicle is placed by `return`, not by this command | `NOT_FOUND`, `VERSION_CONFLICT`, `INVALID_TRANSITION`, `SPACE_NOT_FREE`, `HUB_FULL`, `FORBIDDEN` | `VehicleStateChanged`, `SpaceOccupancyChanged` | M2 |
| `free_space(parking_space_id, expected_version)` | A space | Removes the occupancy (private EV departure, sensor `SPACE_FREED`): the same as the event `depart`. The vehicle then has no space and is `IN_USE`. A charging vehicle cannot leave | `NOT_FOUND`, `VERSION_CONFLICT`, `INVALID_TRANSITION`, `FORBIDDEN` | `VehicleStateChanged`, `SpaceOccupancyChanged` | M2, iot_sim |
| `set_charging_point_status(charging_point_id, status, expected_version)` | `AVAILABLE`, `CHARGING`, `OUT_OF_SERVICE`, `MAINTENANCE` | Changes the point. `OUT_OF_SERVICE` does not by itself end sessions; the event lets M3 interrupt them (FR-09, UC-M3-08) | `VERSION_CONFLICT`, `FORBIDDEN` | `ChargingPointStatusChanged` | M3, M5, iot_sim |
| `set_hub_status(hub_id, status, expected_version)` | `ACTIVE`, `WARNING`, `CRITICAL`, `MAINTENANCE` | Stores the status decided by M5 (`BR-M5-01`, `BR-M5-02`) | `VERSION_CONFLICT`, `FORBIDDEN` (operator or `monitoring` only) | `HubStatusChanged` | M5 |
| `apply_sensor_event(event, actor)` | `SensorEvent`: `event_id`, `source`, `type`, `entity_id`, `at`, `value` (the values each type expects are in `core/sensors.py`) | Applies the event or rejects it with no change at all (NFR-10), logs a warning and publishes `SensorEventRejected`. `BATTERY_LEVEL` sets the battery. `SPACE_OCCUPIED` / `SPACE_FREED` confirm the recorded occupancy; only a private EV arrives or leaves by sensor (a fleet vehicle moves with `return` / `pickup`), and an event that contradicts the record is rejected. `CHARGER_FAULT` sets the point `OUT_OF_SERVICE` (`value = False` clears it). `VEHICLE_FAULT` is `report_fault`. `HEARTBEAT` changes nothing. An event that only confirms the record is accepted with `changed = false`, so a repeating feed is harmless | `INVALID_INPUT`, `NOT_FOUND`, `INVALID_TRANSITION`, `FORBIDDEN` (not `iot_sim`) | as the underlying change; `VehicleBatteryChanged`; `SensorHeartbeat` | iot_sim only |
| `load_network(spec, actor)` | `NetworkSpec` (`core/seed.py`): Hubs with their space and charging-point counts and fleet vehicles, users, private vehicles | Loads a whole network into an empty store, all or nothing. IDs come from the Hub ID (`H01-S001`, `H01-CP01`), fleet vehicles fill the free spaces before the charging bays, private vehicles start `IN_USE`, away from every Hub. Refuses a store that already holds data. M8 builds the spec from `reference-dataset.md`; `iot_sim` never writes to storage itself (CONTRIBUTING 9.13) | `INVALID_INPUT`, `FORBIDDEN` | – | iot_sim, operator |

**Who cleans up claims.** Every claim has a holder module (`RESERVATION` is M2's, `CHARGING_SESSION` is M3's, `DISPATCH_TASK` is M4's). `core` never ends a claim by itself, not even when its end time has passed: the holder knows what must happen next (cancel the reservation, free the vehicle, tell the student, update its quota), and `core` does not. Each module releases its own claims with `release_claim` when its record ends or expires; `core` refuses a release by another module (`FORBIDDEN`), an operator may release any. Every module can read all claims with `get_claims`, so it can see who holds a resource, but it cannot release a claim that is not its own. An `ACTIVE` claim whose end time has passed blocks nobody (overlap is decided by the intervals), so a late release only leaves a stale row. There is no `expire_claims` command: `release_claim` already does the job and each module knows its own claims. The status `EXPIRED` is kept in the enumeration for later.

Claims and state changes are separate on purpose: a reservation first places claims (vehicle, and optionally a destination space), then moves the vehicle. For multi-step cases use the unit of work below.

`core` does not refuse a claim because the Hub is `CRITICAL`. The caller reads `status` from `get_hub` and rejects the booking itself (`BR-M5-02`; M2 does it in `UC-M2-06`).

### 5.1 Unit of work

```python
with core.unit_of_work() as uow:
    r1 = uow.commands.transition_vehicle(vid, "pickup", v, ctx)
    r2 = uow.commands.release_claim(claim_id)
    if r1.is_err or r2.is_err:
        uow.rollback()
    else:
        uow.commit()
```

- Leaving the block without `commit()` rolls everything back.
- Events are published only after `commit()`.
- Conflicts on the same entities are serialized (optimistic version check at commit; the caller retries on `VERSION_CONFLICT`).
- A unit of work belongs to one thread of control. It does not nest.
- A command that returns an error inside a unit of work undoes its own changes (a savepoint) and leaves the rest of the unit as it was, so the caller may continue or roll back the whole unit. `commit()` returns a `Result`.
- One lock serializes the writers of a process, so concurrent commands run one after another (NFR-06).

Standard multi-entity operations (NFR-09), named so M2/M4 and M8 refer to the same thing:

| Operation | Steps inside one unit of work |
|---|---|
| Reserve rental | `place_claim(VEHICLE)` + `transition_vehicle(reserve)` |
| Pick up | `transition_vehicle(pickup)` + `release_claim` for the origin space (if any); the Trip and reservation changes are made by M2 in the same unit |
| Return | `transition_vehicle(return)` (occupies destination space) + release the return-parking claim |
| Start charging | `place_claim(CHARGING_POINT)` + `transition_vehicle(start_charging)` + `set_charging_point_status(CHARGING)` |
| Dispatch task step | As Pick up / Return, with `holder_kind = DISPATCH_TASK` |
| Private arrival | `occupy_space` (or `transition_vehicle(arrive)`) with the parking claim (it becomes the occupancy); for a parking + charging bundle, M3 starts charging in the same unit |
| Private departure | M3 stops any charging, then `free_space` |
| Move a parking claim to another space | `release_claim` + `place_claim` (M2 `UC-M2-08`, unexpected occupant) |

M2 and M4 write their own tables (Reservation, Trip, task) inside the same unit, as described in §5.2. M2 first reads its own record (see Idempotency in §2), so the step "Core reads the existing reservation via an M2 port" in M2's `s1`–`s3` is done by M2 before it calls `core`, and `core` needs no port for it.

### 5.2 Module records in the unit of work

A module's own records (Reservation, Trip, ChargingSession, task) are stored by `core`'s repository, so a change to a vehicle and the module's record commit or roll back together (NFR-09). The module does not open a second transaction.

1. **Register the table at start-up**, in `install(core, app)`: `core.register_entity(TableSpec(entity, table, id_column, enums, versioned))` (`core.repository.schema.TableSpec`). Rules, checked at registration (a `ValueError` says what is wrong): the entity is a dataclass with `ID_FIELD` equal to the id column; the table has one column per field and no more; `versioned` matches the class attribute `VERSIONED` and a versioned entity has a `version` field; the class name and the table name are not used by core or by another module. Registering the same spec twice does nothing. Build the `Table` on `core.repository.schema.metadata`, so a `ForeignKey("vehicles.vehicle_id")` works; the database then refuses a record of an unknown vehicle. Core creates the table if it does not exist (there is no migration tool).
2. **Write inside a unit of work:** `uow.repository.add(record)` and `uow.repository.update(record, expected_version)` next to `uow.commands.*`. Use it only inside the `with` block and on the same thread. A versioned record is optimistically locked like core's own (`VersionConflictError`). `uow.rollback()`, an exception, or leaving without `commit()` undoes the module's records too, and `snapshot_version` conflicts cover them.
3. **Read** with `core.get_entity(Type, id)` and `core.query_entities(Type, predicate)`; both take core's lock, so they are safe from any thread. Reading the table directly would race with a running transaction and is not allowed.
4. Events of the module are published after `commit()` returns `Ok`, with the module's own use of the `EventBus`.
5. An unregistered type is refused (`UnknownEntityError`) on both repositories, so a test with the `InMemoryRepository` catches a forgotten registration.

The snapshot (§7) and the invariant checker cover core's data only.

## 6. Events — `EventBus`

In-process publish/subscribe. Handlers run after commit; a handler failure never undoes the commit and is logged. Delivery order follows commit order.

| Event | Payload | Typical subscribers |
|---|---|---|
| `VehicleStateChanged` | `vehicle_id`, `previous`, `new`, `event`, `hub_id`, `at`, `actor` | M3 (start/stop queueing), M4 (re-plan), M5 (incident rules) |
| `SpaceOccupancyChanged` | `hub_id`, `parking_space_id`, `occupied`, `occupied_count`, `at` | M5 (`BR-M5-01`, `BR-M5-02` thresholds), M4 |
| `ChargingPointStatusChanged` | `charging_point_id`, `hub_id`, `previous`, `new`, `at` | M3 (interrupt sessions), M5 |
| `HubStatusChanged` | `hub_id`, `previous`, `new`, `at` | UI, M2 (block new parking reservations when `CRITICAL`, `BR-M5-02`), M4 |
| `ClaimPlaced`, `ClaimReleased` | `claim_id`, resource, holder, interval | M2, M3, M4 |
| `VehicleBatteryChanged` | `vehicle_id`, `previous`, `new`, `low` (at or below `LOW_BATTERY_THRESHOLD`), `hub_id`, `at` | M5 (`BR-M5-05`, `INC-BAT-01`), M3 |
| `SensorHeartbeat` | `source`, `entity_id`, `sent_at`, `received_at` | M5 (telemetry loss, `INC-COMM-01`) |
| `SensorEventRejected` | `event_id`, `source`, `type`, `entity_id`, `code`, `reason` | M5, M8 |

Subscribers use `events.subscribe(type, handler)`; they do not import the publisher.

### 6.1 Provider ports

Interfaces defined in `core`, implemented by other modules and registered through `core.register_provider(port, impl)`. They are read-only and return `Result[T]`. One module implements one port (D-020); the argument and result types of a port are defined in `core.providers`, written by its owner and reviewed by its callers. If no provider is registered or it fails, the caller gets `RESOURCE_UNAVAILABLE` and must not assume an answer.

| Port | Operation | Implemented by | Used in |
|---|---|---|---|
| `ReservationDemand` | `upcoming_bookings(hub_id, horizon)`, `open_trips(hub_id)` (with `expected_return_at`) | M2 | M4 `s1-plan`; M6, which needs the due times that are not in the snapshot (§7) |
| `ChargingDemand` | `scheduled_sessions(hub_id, horizon)` | M3 | M4 `s1-plan`; M6 (§7) |
| `AlternativeHubProvider` | `suggest_alternative_hubs(request) -> (candidates, as_of)` | M4 (`UC-M4-05`) | M2 `s3-return`, `s4-alt-hubs` |
| `AlternativeChargingProvider` | `find_alternative_charging(requests, hub_id)` | M4 (`UC-M4-07`) | M3 `s5-alt-charging` (`UC-M3-08`, D-012) |
| `HoldConsumer` | `consume_hold(holder_ref)`, called inside the unit of work | M2 | M4 `s3-execute` |

## 7. Snapshot — `SnapshotService` (for M6 and M4)

`export_snapshot() -> OperationalSnapshot`

- Read-only and consistent: all entities as of one commit point, taken inside one read transaction.
- Contains: `snapshot_id`, `taken_at`, `version` (a counter that grows with every commit), `hubs`, `parking_spaces`, `charging_points`, `vehicles`, `claims` (active only), sorted by ID.
- `version` lets M4 start its plan on a snapshot and later detect that the state moved on (`s2-approve`: "begin unit of work on a fresh snapshot (version)"). A unit of work opened with a `snapshot_version` fails with `VERSION_CONFLICT` if any entity it touches changed since then.
- Battery is `battery_pct` (0–100) everywhere, as in the ERD. M6's draft uses `soc` as a fraction; M6 converts when it loads the snapshot.
- Holds no references to live objects or connections. M6 builds its own mutable state from it (M6 design §4.5, §7.5). It may also load the snapshot into the `InMemoryRepository` of `core` to reuse the transition rules (class diagram §3; open in `architecture-diagram.md` §11). Either way the operational store is never written (NFR-12).
- Same state ⇒ same `snapshot_id` hash (NFR-13).
- `OperationalSnapshot.to_dict()` gives plain JSON data. `OperationalSnapshot.to_repository()` loads it into a new `InMemoryRepository`; `CoreFacade.check_invariants()` (or `InvariantChecker.check(repo)`) lists what is wrong in any store, including a loaded one.
- A plan made on a snapshot opens `core.unit_of_work(snapshot_version=snapshot.version)`; `commit()` returns `VERSION_CONFLICT` if anything the unit wrote was committed by someone else after that version.
- Names: M6's illustrative contract (`m6-simulation-design.md` §7.3) uses other names and says the final ones follow M1's model. Mapping: `total_capacity` → `parking_capacity`; `occupied_spaces` → derived `occupied`; `type` → `vehicle_type`; `soc` (fraction 0–1) → `battery_pct` (0–100); `point_id` → `charging_point_id`; `power_kw` → `power_rate_kw`; vehicles and charging points nested in a hub → flat lists with `hub_id`.
- Not in the snapshot: reservations, trips, charging sessions and tasks belong to M2–M4. The snapshot has their claims (resource, holder, interval) but not due times such as `expected_return_at`. M6 reads those through `ReservationDemand` and `ChargingDemand` (§6.1); M2 asked for them ("a snapshot must include future claims and due times").
- M6 validates the snapshot before use (M6 design §7.4). `core` guarantees unique IDs, referential consistency and `occupied ≤ parking_capacity` (`BR-M1-02`).

## 8. REST endpoints for the UI (read-only, plus the simulator's intake)

Served by FastAPI from `src/core/api` (`create_router(core, auth)` returns the router; `src/main.py` will mount it with the routers of the other modules). Handlers are plain `def` functions. The OpenAPI schema generated from the Pydantic models (`/openapi.json`) is the interface document for M7.

| Method and path | Maps to | Who |
|---|---|---|
| `POST /auth/login` | `{code, password}` → `{access_token, token_type, expires_at, user_id, role}` | anyone |
| `GET /me` | the caller: `user_id`, `role`, `module` | any logged-in user |
| `GET /hubs` | `list_hubs` | student, operator |
| `GET /hubs/{hub_id}` | `get_hub` | student, operator |
| `GET /hubs/{hub_id}/vehicles?state=&type=&min_battery=` | `find_vehicles`. A student gets the rental fleet only; an operator also sees private vehicles | student, operator |
| `GET /hubs/{hub_id}/spaces?status=` | `list_spaces` | operator |
| `GET /hubs/{hub_id}/charging-points?status=` | `list_charging_points` | operator |
| `GET /vehicles/{vehicle_id}/state-log?limit=` | `get_state_log` | operator |
| `POST /sensor-events` | `apply_sensor_event`; the body is read loosely so that core can reject, log and announce a bad event itself (NFR-10) | the simulator's service credential only |

State-changing endpoints are provided by the module that owns the workflow (reservation, charging, allocation, monitoring). They call `core` in-process.

**Authentication (A-06, NFR-16, NFR-17).** Seeded accounts with two roles. `POST /auth/login` gives a signed bearer token (`Authorization: Bearer <token>`) that lasts `ACCESS_TOKEN_TTL_MINUTES` (default 60). Passwords are stored as salted PBKDF2-SHA256 hashes (`PASSWORD_HASH_ITERATIONS`), the signing key is `SECRET_KEY` (no default: core refuses to start without one). The account is read again on every request, so a deactivated user or a changed role takes effect at once. Every endpoint except `/auth/login` needs a token. The simulator uses a service token (`issue_service_token("iot_sim", ...)`), which is not tied to an account.

**Errors.** One body for all of them: `{"error": {"code", "message", "details"}}`. A failed login gives the same message whether the code or the password was wrong. Status codes:

| Status | Codes |
|---|---|
| 400 | `INVALID_INPUT` (also malformed requests and bad query values) |
| 401 | `UNAUTHENTICATED` (with `WWW-Authenticate: Bearer`) |
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 409 | `VERSION_CONFLICT`, `CLAIM_CONFLICT`, `HUB_FULL`, `SPACE_NOT_FREE`, `INVALID_TRANSITION`, `RESOURCE_UNAVAILABLE`, `BATTERY_TOO_LOW` |
| 500 | `INTERNAL_ERROR` (generic message, no stack trace; the cause goes to the log) |

## 9. Mapping to requirements

| Requirement | Where covered |
|---|---|
| FR-01 | `list_hubs`, `get_hub`, `find_vehicles`, `list_spaces`, `list_charging_points`, REST `GET /hubs` |
| BR-M1-01 | `place_claim` and `CLAIM_CONFLICT` |
| BR-M1-02 | `HUB_FULL`, `SPACE_NOT_FREE`, bay rule in `start_charging` |
| BR-M1-03 | `transition_vehicle` and `INVALID_TRANSITION` |
| NFR-01 | Reads show the committed state; events after commit |
| NFR-06 | `CLAIM_CONFLICT` plus `VERSION_CONFLICT` |
| NFR-09 | `UnitOfWork` |
| NFR-10 | `apply_sensor_event` rejects malformed input |
| NFR-12, NFR-13 | `SnapshotService`, sorted outputs, injected clock |
| NFR-16, NFR-18 | `Actor` and `FORBIDDEN`; `INVALID_INPUT` |
| NFR-25 | `StateChangeRecord`, `get_state_log` |
| NFR-22 | Provider ports (§6.1); imports point into `core` |
| FR-07 (M3, private EV) | `register_vehicle`, `occupy_space`, `free_space` |

## 10. Decisions behind this version

1. **Claim granularity for parking.** Settled in the draft: a claim is always on a named space. For "any free space at Hub X", M2 (`UC-M2-06`) or M4 asks `find_free_space` first and then places the claim in the same unit of work. M2 adapts its design.
2. **Shape of the unit-of-work port for M2/M4 tables.** Settled in the draft: the module registers its table with `core.register_entity` and writes through `uow.repository` (§5.2). This replaces the earlier proposals (`unit_of_work(extra=[...])` and an in-transaction hook). M2 and M4 follow it.
3. **Where the low-battery threshold is read.** Decided: `LOW_BATTERY_THRESHOLD` (15%) in `core` config, read by M3 and M5 through a `get_config()` query. M3 (`BR-M3-03`) and M5 (`BR-M5-05`) say "at or below" the threshold after their fixes, and M2's `RENTAL_POOL_LOCKOUT` uses ≤ 15% too, so `core` treats a vehicle at exactly 15% as low. M2 adds its own rental floor `RENTAL_MIN_SOC` = 20%, passed to `reserve` as `min_battery` (a caller filter, not a `core` setting).
4. **M5 hub status.** `set_hub_status` assumes M5 decides and `core` stores. If `core` should derive it from occupancy, remove the command. M5 (`BR-M5-01`, `BR-M5-02`) and M7's ERD (`Hub.status`) both treat it as a stored value, so the draft keeps it.
5. **Calls from `core` to other modules.** M2's `s3-return` and M4's `s1-plan`, `s3-execute`, `s4-alt-hubs`, `s5-alt-charging` show `core` calling M2, M3 or M4 (demand data, "consume the hold", alternative Hubs or bays). M2's `s1`–`s3` also have a step "Core reads the existing reservation via an M2 port"; this one is not needed, because M2 reads its own record first. `core` importing them would break D-003 and NFR-22. Decided: `core` defines the **provider ports** of section 6.1 and the other module registers an implementation at start-up, so the dependency still points into `core`. M2 and M4 keep their sequence diagrams, with "Core" read as "Core port".
6. **Idempotency.** Settled with M2's PR #11 (no command-result store in `core`, M2 answers from its own record). A change follows D-006.
7. **Private EV vehicle states.** Draft decision: a private EV away from every Hub is `IN_USE`; `arrive` and `depart` move it in and out (`vehicle-state-machine.md` §7, point 1; D-016).
8. **Operator override (M7 `UC-M7-02`).** Settled in the draft: `repair` goes on to `mark_ready` by itself when the readiness check passes, so the operator presses once and M7's example `Maintenance → Available` works (`vehicle-state-machine.md` §7, point 5). If the battery is at or below the threshold the vehicle stays `Returned`.
9. **Names in the ERD.** The differences listed in `class-diagram-core.md` §2.1 are for M7 to apply in the final ERD.
10. **Provider ports have one implementer each.** `DemandSource` had two implementers (M2 and M3), but the registry accepts one provider per port. It is split into `ReservationDemand` (M2) and `ChargingDemand` (M3), decided by the port owners (D-020). The code follows in M1's Phase 3 work; no module uses a port before that.
