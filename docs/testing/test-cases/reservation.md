# M2 Reservation & Trip test cases

Owner: M2, Đặng Tuấn Kiệt (2452620). Requirements:
[FR-02 through FR-05 and FR-07 parking](../../requirements/fr-02-05-07-reservation.md).
See the [test plan](../test-plan-v1.md) for the standard case format.

Baseline fixture `F1` is [rental](../../../tests/reservation/conftest.py):
Core with a deterministic clock and the real memory and SQLite repositories.
Active students U1 and U2 are present. Fleet vehicles V1/V2 are eligible at H1
and occupy S1/S2. Destination H2 has one free space S3. The default request
uses U1, R1, V1, H1, H2 and the observed vehicle version. Tests separately
prepare invalid or conflicting conditions. F2 is an on-disk temporary SQLite
database which is closed and reopened by TC-M2-021.

Fixture `F3` builds the app with real Core authentication, a fixed clock and
SQLite. It seeds two students, an operator, an eligible fleet vehicle at H1,
a free destination at H2 and a full destination at H3. HTTP requests use
bearer tokens issued by Core's sign-in endpoint.

`EP` is equivalence partitioning, `BVA` is boundary value analysis, `ST` is
state transition, `CT` is conflict/concurrency, `FI` is failure injection, and
`INT` is integration/contract. Priority H identifies correctness, safety and
access control. M identifies other validation or setup.

Run `python -m pytest tests/reservation -q --cov=reservation --cov-fail-under=60`
from the repository root. For an individual case, use
`python -m pytest tests/reservation -m tc_m2_007 -q`, replacing the marker
suffix with the case number. Each parametrized instance is part of the same
case. Evidence names point to [test_booking.py](../../../tests/reservation/test_booking.py)
unless another file is stated.

| TC ID and title | Verifies | Technique | Priority | Preconditions | Steps / input | Expected result | Actual result | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| TC-M2-001 Complete rental | FR-03/04, UC-M2-02/04/05, BR-M2-04/09/10, NFR-09 | ST/BVA | H | F1 | Reserve for 5/30/120 min, pick up at +2 min, return at H2 | Confirmed then Active then Completed. Origin occupancy holds until pickup. Due time uses pickup. S3 receives V1 exactly once | Automated assertions matched expected result | Pass | `test_complete_rental` |
| TC-M2-002 Reject malformed requests | FR-03, UC-M2-02, NFR-18 | EP/BVA | M | F1 | Mix invalid ID, version, duration and battery classes including bool, NaN and infinity | INVALID_INPUT. Fingerprint unchanged | Automated assertions matched expected result | Pass | `test_invalid_input_never_mutates` |
| TC-M2-003 Rental battery boundary | FR-03, UC-M2-02, BR-M2-02 | EP/BVA | H | F1 | Set battery around 15/20 and a requested 80 or 100 | Admission requires both the implemented rental threshold and the requested minimum. Rejection leaves state unchanged | Automated assertions matched expected result | Pass | `test_battery_partitions` |
| TC-M2-004 Ineligible vehicle | FR-03/04, UC-M2-02, BR-M2-02, NFR-08 | EP | H | F1 | Attempt to reserve a private, faulty, wrong-origin or Returned vehicle | RESOURCE_UNAVAILABLE. Fingerprint unchanged | Automated assertions matched expected result | Pass | `test_ineligible_vehicle` |
| TC-M2-005 Active student guard | UC-M2-02/04/05, NFR-16 | EP | H | F1 | Reserve, pick up and return as unknown, inactive, operator or mismatched role | FORBIDDEN for each attempt. Fingerprint unchanged | Automated assertions matched expected result | Pass | `test_only_active_students` |
| TC-M2-006 Vehicle version conflict | FR-03/04, UC-M2-02/04/05, NFR-09 | CT | H | F1, prepare each operation | Send mismatching vehicle version | CONFLICT. Core and M2 state remain unchanged | Automated assertions matched expected result | Pass | `test_stale_version_rolls_back` |
| TC-M2-007 Pickup deadline | FR-04, UC-M2-04, BR-M2-04 | BVA | H | F1, Confirmed R1 | Attempt pickup at expiry minus 1 ms, expiry and expiry plus 1 ms | Only earliest attempt succeeds. EXPIRED at and after the boundary with no writes | Automated assertions matched expected result | Pass | `test_pickup_deadline` |
| TC-M2-008 Retry business records | FR-03/04, UC-M2-02/04/05, BR-M2-09/10, D-015 | ST | H | F1, completed R1 | Repeat matching original requests with Core mutation methods forbidden | Existing reservation/Trip read back. Fingerprint unchanged | Automated assertions matched expected result | Pass | `test_matching_retries_read_records_even_after_completion` |
| TC-M2-009 Reject foreign/mismatched requests | UC-M2-02/04/05, BR-M2-09/10, NFR-16/18 | EP | H | F1, active R1 | Use U2 or missing IDs, edit duration or pickup hub, then try a different hub on completed return retry | Foreign/missing records get NOT_FOUND_OR_NOT_OWNED. Changed payloads get INVALID_INPUT. Neither causes a write | Automated assertions matched expected result | Pass | `test_foreign_records_and_mismatched_retries` |
| TC-M2-010 Full or committed destination | FR-04, UC-M2-05, BR-M2-10, NFR-07/09 | CT | H | F1, active trip | Occupy S3 or add an overlapping future claim; attempt return at H2 | NO_PARKING. Trip remains open; no return writes | Automated assertions matched expected result | Pass | `test_full_destination_leaves_trip_open` |
| TC-M2-011 Atomicity on write/commit failure | UC-M2-02/04/05, NFR-09/25 | FI | H | F1, prepare each operation | Inject a module write or commit failure after Core work for reserve/pickup/return | Full rollback of Core and M2. No successful event published | Automated assertions matched expected result | Pass | `test_storage_failure_rolls_back_core_and_module` |
| TC-M2-012 Pickup claim release failure | FR-04, UC-M2-04, D-017, NFR-09 | FI | H | F1, Confirmed R1 | Inject a failure when pickup releases the claim | Full rollback including the attempted pickup transition and occupancy change | Automated assertions matched expected result | Pass | `test_claim_release_failure_rolls_back_pickup` |
| TC-M2-013 Identical concurrent retries | UC-M2-02/04/05, D-015, NFR-06/09 | CT | H | F1 | Submit 12 identical reserve, pickup or return calls concurrently for each stage | One booking, one Trip and one vehicle transition per stage | Automated assertions matched expected result | Pass | `test_concurrent_identical_requests_return_one_record` |
| TC-M2-014 Student quota under concurrency | FR-03, UC-M2-02, BR-M2-03, NFR-06 | CT | H | F1 | U1 tries to reserve V1 and V2 concurrently | One success and one LIMIT_REACHED | Automated assertions matched expected result | Pass | `test_quota_serializes_across_different_vehicles` |
| TC-M2-015 Vehicle contention | FR-03, UC-M2-02, BR-M2-02, NFR-06 | CT | H | F1 | U1 and U2 try to reserve V1 concurrently | One success, one conflict and one claim | Automated assertions matched expected result | Pass | `test_two_students_cannot_reserve_one_vehicle` |
| TC-M2-016 Pickup rechecks eligibility | FR-04, UC-M2-04, BR-M2-02, NFR-16 | EP/ST | H | F1, Confirmed R1 | Change the vehicle's battery or deactivate its owner after reservation, then pick up | Pickup rejects current battery/account ineligibility | Automated assertions matched expected result | Pass | `test_pickup_rechecks_battery_and_account` |
| TC-M2-017 Faulty trip return | FR-04, UC-M2-05, D-016, BR-M2-14 | ST | H | F1, active trip | Report vehicle fault during use and return with actual capacity | Trip IncidentAborted, vehicle Maintenance, actual bay occupied | Automated assertions matched expected result | Pass | `test_faulty_trip_uses_core_faulty_return` |
| TC-M2-018 Module installation | D-013/018/020, NFR-22 | INT | M | F1 app/core | Repeat M2 installation and inspect registered entities/providers | Tables register safely. After PR #54, `ReservationDemand` is registered and `HoldConsumer` remains absent | Automated assertions matched the expectation at each revision | Pass | [`test_install_registers_entities_and_read_provider_once`][router-install] |
| TC-M2-019 Unknown resource and dispatch claim | FR-03, UC-M2-02, NFR-06/18 | EP/CT | H | F1 | Use unknown vehicle/Hub or reserve a vehicle already claimed by dispatch | Rejected with no new rental write | Automated assertions matched expected result | Pass | `test_unknown_resources_and_competing_claim` |
| TC-M2-020 Advisory destination | FR-04, UC-M2-05, BR-M2-10 | ST | M | F1, active trip | Return to a suitable Hub other than the planned Hub | Receipt records accepted destination and actual space | Automated assertions matched expected result | Pass | `test_return_can_choose_different_hub_from_advisory_destination` |
| TC-M2-021 Persisted retry after SQLite reopen | UC-M2-02/04/05, D-015/018/022, NFR-09 | INT | H | F2 | Reserve, reopen and retry, continue pickup/return, reopen and retry receipt | Original results recovered, no persisted Core ID collision, invariant check clean | Automated assertions matched expected result | Pass | [`test_retry_survives_database_reopen`](../../../tests/reservation/test_persistence.py) |
| TC-M2-022 Origin Hub eligibility | FR-03, UC-M2-02, BR-M2-02 | EP | H | F1 | Reserve at a missing or Maintenance origin Hub | Booking rejected with the expected error for that origin | Automated assertions matched expected result | Pass | `test_origin_must_exist_and_accept_rentals` |
| TC-M2-023 Unused booking release | FR-03, UC-M2-03, BR-M2-04/05, D-017, NFR-06/09/16 | BVA/EP/ST/CT/FI | H | F1, Confirmed R1 | Exercise owner and foreign cancel, deadline, disabled-owner sweep, active trip, existing Maintenance, pickup/cancel race, fault injection at release/transition/write/commit | Cancelled before the boundary, Expired when due. Retries return the stored terminal record. Occupancy and Maintenance are preserved. Active trip remains in use. Race has one winner. Injected failures roll back | Automated assertions matched expected result | Pass | [`test_lifecycle.py`](../../../tests/reservation/test_lifecycle.py) |
| TC-M2-024 Authenticated rental journey | FR-03/04, UC-M2-02/03/04/05, D-015/023, NFR-07/09/16 | INT/ST | H | F3, student token | Reserve, list bookings, pick up and return. Retry the same operations. Separately cancel a confirmed booking | HTTP 200. Pickup opens one trip and vacates its origin. Return occupies the destination and closes the trip. Cancel preserves parked occupancy. Retries return the stored outcome | 2 HTTP tests passed | Pass | [`test_router.py`][router-tests] |
| TC-M2-025 API authorization, validation and failures | D-023, BR-M2-09/10, NFR-09/16/18, M2-1 | INT/EP/FI | H | F3, two student tokens and an operator token | Try all endpoints without a token and as the operator. Try foreign and missing IDs, invalid input, stale versions and a full Hub. Inject write and list storage failures | 401/403 for access denial, identical 404 for foreign and missing records, 400 for invalid rental input, and 409 for a stale version or full Hub. Write failure returns 500 and rolls back. List failure returns 503. No storage details leak | 3 HTTP tests passed | Pass | [`test_router.py`][router-tests] |
| TC-M2-026 ReservationDemand over Core | D-020/021, BR-M2-04/15, FR-03/04 | INT/BVA | H | F1, installed provider | Read pickup demand at active and expired boundaries. Try an invalid horizon and an unknown Hub. Read open trips at origin and planned destination before and after the overdue boundary and after return | Sorted live holds and open trips. An omitted destination stays absent. Overdue is reported only after due time plus 60 min. Completed trips are excluded. Reads do not change shared state | 8 cases passed across memory and SQLite | Pass | [`test_provider.py`][provider-tests] |
| TC-M2-027 Vehicle search | FR-02, UC-M2-01, BR-M2-02, NFR-16/18 | INT/EP | H | F4, student and operator tokens | Search H1 with no filter, by type and by minimum battery; reserve one vehicle as another student and search again. Search without a token, as the operator, with a minimum over 100, an unknown type and an unknown Hub | Fleet vehicles at 20% or more, sorted by battery then ID; filters apply; a reserved vehicle is left out. 401, 403, 400 for invalid input and 404 for an unknown Hub; no shared state changes | 2 HTTP tests passed | Pass | [`test_search_sweep.py`][sweep-tests] |
| TC-M2-028 Expiry on the next request | FR-03, UC-M2-03, BR-M2-04, D-017 | INT/BVA/ST | H | F4, Confirmed R1 | Reserve a second vehicle before the deadline; set the clock to the deadline and list bookings; search and reserve again | Second booking refused with LIMIT_REACHED; at the deadline the next request records R1 as EXPIRED and frees V1; the new booking is Confirmed | 1 HTTP test passed | Pass | [`test_search_sweep.py`][sweep-tests] |
| TC-M2-029 Overdue Trip | FR-04, UC-M2-05, BR-M2-15 | INT/BVA/ST | H | F4, picked-up R1 | List bookings at due + 60 min and one second later; return the vehicle | Still IN_PROGRESS at the boundary, OVERDUE after it with the booking ACTIVE; the return completes the Trip | 1 HTTP test passed | Pass | [`test_search_sweep.py`][sweep-tests] |
| TC-M2-030 Return-space hold | FR-05, UC-M2-05, UC-M2-06, BR-M2-03/04/10/11 | INT/ST/BVA | H | F5, picked-up R1 | Hold a space at H2, repeat the same ID, return to H2. Separately hold at H2, ask a second hold, return to H3, move the clock to the deadline. Ask a hold with no Trip | The return parks V1 in the held space; the hold is COMPLETED and its claim released. A second hold is LIMIT_REACHED; a return to H3 leaves the H2 hold, which expires at its deadline and releases its claim; no Trip gives 404 | 2 HTTP tests passed | Pass | [`test_parking.py`][parking-tests] |
| TC-M2-031 Private parking stay | FR-05, FR-07, UC-M2-06, UC-M2-08, BR-M2-11 | INT/ST/BVA | H | F5, private EV P1 away | Book H2 30 min ahead for 60 min; arrive before the start; arrive 5 min after the start; depart | Early arrival is INVALID_STATE; arrival parks P1 in the held space (ACTIVE); departure frees the space and completes the booking | 1 HTTP test passed | Pass | [`test_parking.py`][parking-tests] |
| TC-M2-032 Private parking limits, cancel and expiry | FR-05, FR-07, UC-M2-07, BR-M2-03/04/05, NFR-18 | EP/BVA/ST | H | F5 | Book another student's EV, a 20-min stay, a start after 25 h; book twice; cancel; book again and move the clock to the arrival deadline | 404, 400, 400; LIMIT_REACHED; CANCELLED with the claim released; EXPIRED on the next request with the claim released | 1 HTTP test passed | Pass | [`test_parking.py`][parking-tests] |
| TC-M2-033 Departure while charging | FR-07, UC-M2-08, NFR-21 | INT/ST | M | Hub with 2 bays, private EV P1 arrived in bay H1-S001 and charging | Depart; finish charging; depart again | First depart 409 INVALID_STATE saying the EV is still charging, P1 stays CHARGING; after finishing, the depart completes the booking | 1 HTTP test passed | Pass |

## Execution record

| Run date | Commit | Environment | Command | Result | Evidence |
|---|---|---|---|---|---|
| 2026-11-23 | `bb5c622` | Windows, Python 3.14.4, memory and SQLite | `python -m pytest tests/reservation -q --cov=reservation --cov-fail-under=60` | 159 passed, 96.01% (313/326) | [M2 validation evidence](../evidence/m2-validation-2026-11-23.json) |
| 2026-11-24 | `6488bc2` (PR #54) | Windows, Python 3.14.4, memory and SQLite | `python -m pytest tests/reservation -q --cov=reservation --cov-fail-under=60` | 172 passed, 96.70% (439/454). TC-M2-024 to TC-M2-026 accounted for 13 passes | [Code revision][router-revision] |
| 2026-11-25 | branch `fix/reservation-search-expiry-overdue` | Windows, Python 3.12.10, memory and SQLite | `python -m pytest tests/reservation -q --cov=reservation --cov-fail-under=60` | 176 passed, 95.61% (523/547). TC-M2-027 to TC-M2-029 accounted for 4 passes | [`test_search_sweep.py`][sweep-tests] |
| 2026-11-25 | branch `feat/reservation-parking` | Windows, Python 3.12.10, memory and SQLite | `python -m pytest tests/reservation -q --cov=reservation --cov-fail-under=60` | 180 passed, 92.07% (789/857). TC-M2-030 to TC-M2-032 accounted for 4 passes | [`test_parking.py`][parking-tests] |

The November 23 baseline covers TC-M2-001 through TC-M2-023. The November 24
run also covers the authenticated API and the `ReservationDemand` provider
from PR #54. The November 25 run adds FR-02 search and the sweep that expires due
bookings and marks overdue Trips on the next request. The `feat/reservation-parking`
run adds the return-space hold and private parking (FR-05, FR-07 parking). The
parking/charging bundle (BR-M2-12) and `HoldConsumer` remain outside this evidence.
Fixture `F5` is the HTTP app of `test_parking.py`: H1 with V1, H2 and H3 with two
free spaces each, two students, and one private EV of each student away from every Hub.
Fixture `F4` is the HTTP app of `test_search_sweep.py`: H1 with five fleet
vehicles (one under 20%), H2 with two free spaces, two students and an operator.
Use the [Phase 2 guide](../reservation-phase2.md) for the historical execution
and the [defect log](../defect-log.md) for regression disposition. A successful
coverage run supports the NFR-24 threshold for M2. M8 records team sign-off.

[router-install]: https://github.com/MabC06/smart-e-mobility-hub/blob/6488bc2c3ae7b369b3b5f969fb395d658b4c0e53/tests/reservation/test_booking.py#L480
[router-tests]: https://github.com/MabC06/smart-e-mobility-hub/blob/6488bc2c3ae7b369b3b5f969fb395d658b4c0e53/tests/reservation/test_router.py
[provider-tests]: https://github.com/MabC06/smart-e-mobility-hub/blob/6488bc2c3ae7b369b3b5f969fb395d658b4c0e53/tests/reservation/test_provider.py
[sweep-tests]: ../../../tests/reservation/test_search_sweep.py
[parking-tests]: ../../../tests/reservation/test_parking.py
[router-revision]: https://github.com/MabC06/smart-e-mobility-hub/commit/6488bc2c3ae7b369b3b5f969fb395d658b4c0e53
