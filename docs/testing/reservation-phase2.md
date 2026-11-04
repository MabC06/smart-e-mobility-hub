# M2 Phase 2 test guide

Owner: M2 — 2452620. Updated: 2026-11-05.

The booking service uses real Core commands and both real repository implementations.
Only fault-injection tests replace a command/repository method. The tests verify the
November 8 happy-path slice plus input, authorization, retry and atomicity guards.
They do not claim Phase 3 parking/cancellation/expiry/provider integration coverage.

## Execution

From the repository root, install `requirements-dev.txt`, then run:

```text
python -m pytest -q
ruff check .
ruff format --check .
mypy
python -m pytest tests/reservation -q --cov=reservation --cov-fail-under=60
```

CI also enforces Core coverage of at least 70% using Python 3.12 on Linux. The
local run used Python 3.14.4 on Windows and the same pinned dependency versions.
SQLAlchemy/mypy used their official pure-Python builds because Windows blocked
their optional compiled binaries. No repository dependency versions were changed.

## Traceability

Each row maps directly to a registered pytest marker; for example
`python -m pytest -m tc_m2_007 -q`. Parametrized instances retain the same TC ID
and expose the repository/input partition in their pytest node IDs.

| TC ID / pytest marker suffix | Verifies | Technique and expected result |
|---|---|---|
| TC-M2-001 / `001` | FR-03/04, UC-M2-02/04/05, BR-M2-04/09/10, NFR-09 | Full rental at planned durations 5/30/120: retain origin on reserve, release on pickup, due time from actual pickup, occupy destination once. |
| TC-M2-002 / `002` | FR-03, NFR-18 | Invalid ID/version/duration/battery partitions, NaN/Infinity/bools: no writes or events. |
| TC-M2-003 / `003` | FR-03, BR-M2-02 | Battery boundaries 14.99/15/15.01/19.99/20, requested minimum and 100: rental floor is distinct from shared lockout. |
| TC-M2-004 / `004` | FR-03, BR-M2-02, NFR-08 | Private/faulty/Returned/wrong-origin vehicle excluded. |
| TC-M2-005 / `005` | NFR-16 | Unknown/inactive/operator/role mismatch denied across all three operations. |
| TC-M2-006 / `006` | FR-03/04, NFR-09 | Stale Vehicle version at each operation: unchanged Core and M2 state. |
| TC-M2-007 / `007` | UC-M2-04, BR-M2-04 | Deadline −1 ms / equality / +1 ms: only strictly before expiry can pick up. |
| TC-M2-008 / `008` | FR-03/04, BR-M2-09/10, D-015 | Lost-response retries after completion return existing M2 records without Core mutation calls. |
| TC-M2-009 / `009` | NFR-16/18, BR-M2-09/10 | Foreign/missing IDs, changed booking fields and return destination: no disclosure, duplicate or relocation. |
| TC-M2-010 / `010` | BR-M2-10, NFR-07/09 | Occupied destination or future space claim: NO_PARKING, Trip remains open. |
| TC-M2-011 / `011` | NFR-09/25 | Inject module-write/commit failure after shared writes at each operation: complete rollback, no published success event. |
| TC-M2-012 / `012` | D-017, NFR-09 | Claim release failure after pickup transition: complete rollback. |
| TC-M2-013 / `013` | D-015, NFR-06/09 | Twelve simultaneous identical reserve/pickup/return calls: one booking, one Trip, three Vehicle transitions. |
| TC-M2-014 / `014` | BR-M2-03, NFR-06 | Same student concurrently books two different vehicles: one success, one LIMIT_REACHED. |
| TC-M2-015 / `015` | BR-M2-02, NFR-06 | Different students contend for one vehicle: one success, one conflict, one claim. |
| TC-M2-016 / `016` | BR-M2-02, NFR-16 | Battery/account changed after confirmation: pickup rechecks current eligibility. |
| TC-M2-017 / `017` | D-016, BR-M2-14 | Fault reported while in use: verified return ends IncidentAborted and vehicle enters Maintenance with actual occupancy. |
| TC-M2-018 / `018` | D-013/018/020, NFR-22 | Repeat install safely registers same tables; unfinished providers remain absent. |
| TC-M2-019 / `019` | FR-03, NFR-06/18 | Unknown resources or M4 dispatch claim: no new rental writes. |
| TC-M2-020 / `020` | FR-04, BR-M2-10 | Return to a Hub different from planned destination: actual receipt reflects accepted destination, no automatic hold. |
| TC-M2-021 / `021` | D-015/018/022, NFR-09 | Close/reopen SQLite, retry reservation, continue pickup/return, reopen and retry return: durable business records and non-colliding Core IDs. |
| TC-M2-022 / `022` | FR-03, BR-M2-02 | Unknown/maintenance origin Hub cannot admit a rental. |

`tests/core/test_id_recovery.py` adds the accompanying Core regression checks:
resume maximum numeric counters per prefix, preserve persisted identifiers when
constructing another facade on either repository, and honor an explicitly supplied
generator. M1 owns acceptance of this Core fix (D-022).

Failure assertions compare the Core snapshot **and** M2 records, persistent audit
records and published events. A Core-only snapshot cannot prove M2 rollback because
it omits module records (D-018). A failed test initially exposed ID reset after
SQLite reopen; the regression test remains to prevent that failure from returning.

Local verification on 2026-11-05: **1,165 passed, 1 skipped** across the full
repository, including **131 M2 tests**. Core line coverage: **98.68%**; M2 line
coverage: **96.46%**. `ruff check .`, `ruff format --check .` and strict `mypy`
(44 source files) pass. The CI link is recorded in the submission PR. M8's human
signoff and the student's personal review remain pending.
