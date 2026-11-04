# M2 rental service — Phase 2

This contribution implements the November 8 booking-service scope: reserve,
pickup and return against the released Core. The November 6 design is reviewed
separately in [PR #11](https://github.com/MabC06/smart-e-mobility-hub/pull/11).
It is an in-process service, not a completed UI or REST API.

## Entry points

`install(core, app)` registers `rental_reservations` and `rental_trips` through
`core.register_entity` and sets `app.state.reservation` to a `BookingService`.
The composition root calls this automatically. The caller must supply an
authenticated Core `Actor`; never construct it from untrusted request fields.
The service rechecks the stored account and fixes the command module to
`reservation`. Only active students can use these rental operations.

| Function | Input and effect |
|---|---|
| `reserve(request, actor)` | `ReserveRequest` contains a reservation resource ID, vehicle, origin, optional advisory destination, observed **Vehicle** version, minimum battery and planned duration. Creates one Confirmed booking and vehicle claim, requests Core Reserved state, and keeps origin occupied. |
| `pickup(reservation_id, origin_hub_id, expected_version, actor)` | Before the exclusive ten-minute deadline, starts one Trip, calculates due time from actual pickup, requests Core InUse/source release, releases M2's vehicle claim, and marks the booking Active. |
| `return_trip(trip_id, destination_hub_id, expected_version, actor)` | Requests Core safe-space selection and Return, completes the Trip/booking, and records actual Hub/space/time. A reported in-use fault uses ReturnFaulty and IncidentAborted. No space means no return writes. |

All methods return `Ok(record)` or `BookingError(code, message)`. The version
parameter is always the observed Core Vehicle version, not the M2 record version.
Returned records are detached copies; changing one does not write the database.
Core alone changes shared vehicles, spaces and claims.

For a fresh request the calling boundary allocates a unique reservation resource
ID (for example a UUID string), then retains it across retries. Reuse that same ID
and immutable booking fields after a lost response. A matching existing booking
returns its current recorded state, including a terminal state; it never creates
a second rental. Changed fields or another owner's ID are rejected. Pickup uses
one stable Trip ID per reservation. A matching return retry returns the original
destination and time; it cannot relocate a completed vehicle. There is no command
key, payload hash, retention cache or Core command-result store (D-015).

Each operation reads M2 records under the Core unit-of-work lock before any Core
mutation. Quota checks, Core commands and M2 writes share one transaction. Every
`Err` is checked; only explicit successful commit publishes Core events. Racing
identical requests see the winner's M2 record before considering their stale
Vehicle versions. Repository failures roll back the complete operation.

Policy values are the M2 design defaults, still subject to review: ten-minute
immediate hold, minimum rental battery 20% plus the caller's higher minimum,
shared Core low-battery lockout, one live rental per student, planned duration
5–120 minutes (default 30). Times come from Core's injected clock via
`get_config().as_of`; clients do not send authoritative time.

## File and function guide

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | `install` registers tables and wires the service into the application. It does not register unfinished providers. |
| [models.py](models.py) | `ReserveRequest` and the M2-owned `RentalReservation` / `RentalTrip` dataclasses, with stable persisted statuses. Pending validation is transient. |
| [service.py](service.py) | Public workflow methods above; `_actor` checks account authorization, `_execute` maps repository failures after rollback, private operation methods own the transaction. Small ID/version helpers reject invalid inputs. |
| [storage.py](storage.py) | SQL table definitions and `register_tables`; `read` / `all_reservations` read through Core; `add` / `update` use the caller's UOW repository. Local casts bridge Core v1.1's closed Entity type annotation, without changing runtime storage rules. |
| [results.py](results.py) | `BookingErrorCode` / `BookingError`; `from_core` maps Core failures and removes other holders' details from responses. |
| [Core providers](../core/providers.py) | M2-owned `ReservationDemand` / `HoldConsumer` Protocols and immutable result dataclasses under D-020/D-021. These are contract definitions only. |
| [Core IDs](../core/ids.py), [facade](../core/facade.py) | D-022 regression fix: the default generator resumes above persisted Core IDs, so a new command after SQLite reopen does not reuse an audit/claim/vehicle ID. Fresh sequences and explicit custom generators remain supported. |
| [M2 tests](../../tests/reservation/) | Real Core tests on memory and SQLite, plus actual database reopen. See the [traceability guide](../../docs/testing/reservation-phase2.md). |

## Integration boundaries

The [Core API v1.2 proposal](../../docs/design/architecture/core-api-spec.md#62-m2-port-types-v12-proposal-d-021)
defines M2 provider argument/result shapes for M1/M4/M6 review. The service does
not install successful-empty placeholders. Until Phase 3 registration, the Core
registry correctly reports RESOURCE_UNAVAILABLE for an absent provider.

The following are **not implemented by this Phase 2 slice**: search/UI routes,
cancellation and expiry sweeps, fault-before-pickup invalidation, parking lifecycle
and return holds, M3 charging bundles, M4 alternatives/hold consumption, overdue
processing, provider implementations and full simulation integration. Expired
pickup is rejected without mutation; until M2 expiry processing is implemented,
the Confirmed record/Reserved vehicle still require lifecycle cleanup. Core never
performs that cleanup automatically (D-017). This is not a complete production
rental feature.

Core snapshots exclude M2 records. Demand DTOs supply advisory booking/due-time
information, not a complete restorable M2 snapshot. Core's unit-of-work lock is a
single-process boundary; this contribution does not claim multi-process admission
serialization or durable event delivery. The ID recovery fix covers IDs actually
persisted in Core tables, not a new durable event outbox.

M1 must review Core changes; M7 reviews the M2 workflow; M8 must sign off that the
tests exist and pass. Provider callers M4/M6 must review the proposed shapes.
No approval or merge is implied by passing automated checks.
