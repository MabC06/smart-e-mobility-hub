# Reference Dataset (DS-STD) — v1

> **Status:** Draft v1 · **Owner:** M1 · **Date:** 2026-10-06
> Defined by assumption **A-12** in `docs/DECISIONS.md` (replaces A-10). Any change to a number here needs a new entry in `docs/DECISIONS.md`.

## 1. Purpose and users

DS-STD is the **reference configuration** of the system. It is a set of design parameters for a pilot-scale deployment, not a forecast of real demand.

| Used by | For |
|---|---|
| M1, M8 | Quality targets in `docs/requirements/nfr.md` (NFR-01 to NFR-05, NFR-15) and load tests |
| M8 | Implementing the seed configuration and event feed of `src/iot_sim/` (this document is the specification; the numbers are not duplicated in code) |
| M6 | Building the 5 standard What-if scenarios on a realistic starting state |
| M2 to M5 | Unit and integration test data (boundary and conflict cases) |
| M7, M8 | Demo data |

All values must be **configurable** and **reproducible from a seed** (`IOT_SIM_SEED`). Code never hard-codes them (CONTRIBUTING 9.3, 9.13).

## 2. Totals

| Item | Value |
|---|---|
| Mobility Hubs | 10 |
| Parking spaces | 400 |
| Charging points | 61 |
| Rental vehicles | 250 |
| Seeded student accounts | 1,000 |
| Seeded operator accounts | 5 |
| Registered private EVs | 100 (about 30 active at peak, estimate) |

Parking spaces and charging points are shared by rental and private vehicles. Every charging point is attached to one parking space (a charging bay): 61 of the 400 spaces are charging bays (D-010).

## 3. Hubs

| ID | Name | Type | Parking spaces | Charging points | Initial rental vehicles | Rental fill |
|---|---|---|---|---|---|---|
| H01 | Metro | Metro station | 70 | 10 | 50 | 71% |
| H02 | Dorm A | Dormitory | 60 | 10 | 35 | 58% |
| H03 | Dorm B | Dormitory | 50 | 8 | 30 | 60% |
| H04 | Dorm C | Dormitory | 40 | 6 | 25 | 63% |
| H05 | Campus A | Campus | 50 | 8 | 30 | 60% |
| H06 | Campus B | Campus | 40 | 6 | 25 | 63% |
| H07 | Campus C | Campus | 30 | 4 | 20 | 67% |
| H08 | Library/Service A | Library / service area | 25 | 4 | 14 | 56% |
| H09 | Library/Service B | Library / service area | 20 | 3 | 12 | 60% |
| H10 | Library/Service C | Library / service area | 15 | 2 | 9 | 60% |
| | **Total** | | **400** | **61** | **250** | **62.5%** |

"Rental fill" is initial rental vehicles divided by parking spaces. Hubs differ in size on purpose, so that redistribution, alternative-Hub suggestions and capacity alerts are meaningful.

## 4. Distributions

**Initial battery level of rental vehicles**

| Share | Battery level |
|---|---|
| 60% | above 70% |
| 25% | 30% to 70% |
| 15% | below 30% |

**Rental vehicle types**

| Share | Type |
|---|---|
| 50% | e-bike |
| 30% | e-scooter |
| 20% | electric motorcycle |

## 5. Demand profile

Peak activity means pickups plus returns at a Hub (D-011).

| Period | Peak activity at | Default main flow (from to) |
|---|---|---|
| Morning | H01 (Metro) | H01 and dormitories to campuses H05 to H07 |
| Midday | Campuses H05 to H07 | Campuses and library/service Hubs H08 to H10 in both directions; campuses to dormitories |
| Evening | Dormitories H02 to H04 | Campuses and library/service Hubs to dormitories; small flow from dormitories to H01 |

The main flow carries 60% to 70% of trips in its period (starting value, configurable; M6 tunes it per scenario).

## 6. Load parameters

| Parameter | Value | Used in |
|---|---|---|
| Concurrent sessions for performance targets | 100 | NFR-02, NFR-03 |
| Simultaneous requests on one vehicle or Hub in conflict tests | 20 to 50 | NFR-06 |
| DS-STRESS | 2x DS-STD: 20 Hubs repeating the DS-STD profiles with small seeded variation; 800 parking spaces, 122 charging points, 500 rental vehicles, 2,000 student accounts, 200 private EVs, 200 concurrent sessions (D-013) | NFR-15 |

## 7. Sanity checks (for M8 to assert in tests)

1. The Hub table sums to 400 parking spaces, 61 charging points and 250 rental vehicles.
2. For every Hub, initial rental vehicles ≤ parking spaces, and charging points ≤ parking spaces (D-010).
3. Battery and vehicle-type shares match section 4 within rounding (at most 1 vehicle difference per class).
4. Generating the dataset twice with the same seed gives an identical result (NFR-13).

## 8. Decisions taken on former open points

All are proposals in `docs/DECISIONS.md` until confirmed.

| # | Question | Proposed answer | Decision | To confirm |
|---|---|---|---|---|
| 1 | Is a charging point attached to a parking space? | Yes: a charging bay is a parking space with a charging point; 61 of 400 spaces. Bay-related rules are left to the Requirements Analysis. | D-010 | M1 with the team |
| 2 | Direction of vehicle flows per period | Defined in section 5; main flow 60% to 70% of trips. | D-011 | M6, M8 |
| 3 | Meaning of "active private EV" and its distribution | Holds a reservation in the peak window or is at a Hub; about 30 distributed in proportion to parking spaces; 50% request charging. | D-012 | M3 |
| 4 | How DS-STRESS is built | 20 Hubs repeating the DS-STD profiles, 2x totals. | D-013 | M8 |

## 9. Handoff

- **M8** derives the seed configuration in `src/iot_sim/` from sections 2 to 6 and implements the sanity checks in section 7.
- **M6** uses sections 3 to 5 as the initial state of the What-if scenarios.
- **M1** maintains this document and the link to A-12.
