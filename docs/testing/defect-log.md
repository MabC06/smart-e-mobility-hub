# Defect Log

> **Status:** template with the first entries · **Consolidated by:** M8 (`test-plan-v1.md` section 8) · **Started by:** M1, 2026-11-16
> Every member records the defects of their own module in their own block by 17/11 (`task-assignment-timeline.md`, Phase 4). M8 merges the summary into report section 5.4. A failed test is never changed to pass to close a defect (`test-plan-v1.md` section 8).

## 1. How to record a defect

1. Add **one row** to your module's table in section 3. Copy an existing row and change it.
2. Only for a **Critical** or **High** defect, or one with status **Accepted**, also add a short detail block under the table (steps, expected, actual, resolution), like DEF-M6-001. Medium and Low defects are one row only.
3. ID: `DEF-M<n>-###`, numbered per module, never reused (same rule as `TC-M<n>-###`, D-011).
4. Severity, from the scale below. If unsure, pick the higher one.
5. Status: `Open` → `Fixed` (fix merged) → `Closed` (retest passed). `Accepted` means it stays, with a reason; it then also goes into report section 4.4.
6. "Found by": a test case (`TC-...`), a PR review (with the review code), or integration.
7. Update your line in the summary table (section 2).

| Severity | Meaning | Example |
|---|---|---|
| Critical | Shared state becomes wrong or the system cannot run | Two reservations hold the same space |
| High | A required feature gives a wrong result | A recommendation moves vehicles out of a Hub that is itself short |
| Medium | A feature works but part of it is wrong or missing, with a workaround | A filter ignores one parameter |
| Low | Documentation, naming, typing or duplicated code; behaviour is right | A formula in the report does not render |

## 2. Summary (for report section 5.4)

| Module | Found | Critical | High | Medium | Low | Closed | Open / Accepted |
|---|---|---|---|---|---|---|---|
| M1 core | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| M2 reservation | 1 | 0 | 1 | 0 | 0 | 1 | 0 |
| M3 charging | 1 | 0 | 0 | 0 | 1 | 1 | 0 |
| M4 allocation | 1 | 0 | 0 | 0 | 1 | 1 | 0 |
| M5 monitoring | — | | | | | | |
| M6 simulation | 5 | 0 | 1 | 0 | 4 | 5 | 0 |
| **Total** | **8** | **0** | **2** | **0** | **6** | **8** | **0** |

The initial seven entries were found by reviewing PRs before or at merge (inspection) and fixed by M1 in PR #39, which merged into `develop` on 2026-11-15 (`686b4b0`). Retest for all of them: `python -m pytest -q` on `686b4b0`, 1393 passed, 1 skipped; ruff, format and mypy clean.

## 3. Defects by module

<!-- BEGIN M1: Core -->
### M1 Core

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| — | No defect recorded yet | | | | | | |
<!-- END M1: Core -->

<!-- BEGIN M2: Reservation & Trip -->
### M2 Reservation & Trip

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M2-001 | Reopening SQLite could reuse persisted Core IDs and cause a valid pickup to fail | High | TC-M2-021 | D-022, FR-04, UC-M2-04, NFR-09 | Closed | The default Core generator resumes each prefix above the maximum persisted numeric suffix; injected generators retain their own behavior | PR #24, `e25578d`; D-022 released in PR #40 |

**DEF-M2-001** (High)
- Steps: create and reserve V1 on a file-backed SQLite store; close it;
  open a new facade on the same store; call pickup on the original booking.
- Expected: pickup succeeds with fresh shared record IDs and starts one Trip.
  Original failure: the reset default counters reused a stored ID, so a valid
  pickup could fail before commit.
- Resolution: seed the default generator from stored Core IDs. Retest with
  TC-M2-021 and `tests/core/test_id_recovery.py`: 6 passed on `bb5c622`
  on 2026-11-23. See [execution evidence](evidence/m2-validation-2026-11-23.json).
<!-- END M2: Reservation & Trip -->

<!-- BEGIN M3: Charging & Smart Scheduling -->
### M3 Charging & Smart Scheduling

<!-- M3 adds rows here by 17/11. -->

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M3-001 | Report section 3.3 (M3) listed session states (`AVAILABLE`, `PREPARING`, `SUSPENDED`, `FAULTED`) that the code does not have | Low | Review of the report at merge (M1) | UC-M3-08, BR-M3-02 | Closed | M3 block rewritten to match the code and `charging-session-state-machine.md` | PR #39, `deac134` |
<!-- END M3: Charging & Smart Scheduling -->

<!-- BEGIN M4: Resource Allocation & Dispatching -->
### M4 Resource Allocation & Dispatching

<!-- M4 adds rows here by 17/11. -->

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M4-001 | `allocation/service.py` kept five private copies of M2's port types | Low | Review of PR #27 (M4-6) | FR-10, D-020 | Closed | Copies removed; `ReservationDemand`, `UpcomingBookings`, `OpenTrips` imported from `core.providers`; behaviour unchanged | PR #39, `abeb4ca` |
<!-- END M4: Resource Allocation & Dispatching -->

<!-- BEGIN M5: Monitoring & Incident Handling -->
### M5 Monitoring & Incident Handling

<!-- M5 adds rows here by 17/11. -->

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
<!-- END M5: Monitoring & Incident Handling -->

<!-- BEGIN M6: What-if Simulation -->
### M6 What-if Simulation

<!-- M6 adds rows here by 17/11. -->

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M6-001 | Demand surge could take vehicles from a Hub that is itself a surge target | High | M1 while fixing the merge of PR #30 | FR-12, UC-M6-01 | Closed | See below | PR #39, `45e9781` |
| DEF-M6-002 | Design document showed `export_snapshot()` returning a `dict` | Low | Review of PR #18 (M6-8) | NFR-12, core-api-spec §7 | Closed | Interface changed to `OperationalSnapshot` from `core.services.snapshot` | PR #39, `8f75fab` |
| DEF-M6-003 | Critical-battery metric used 20 % instead of core's 15 % | Low | Review of PR #18 (M6-11) | FR-12, core-api-spec §10 point 3 | Closed | Metric reads `battery_pct(v) ≤ LOW_BATTERY_THRESHOLD` | PR #39, `8f75fab` |
| DEF-M6-004 | Use-case diagram existed only as a Mermaid block, not as `.puml`/`.svg` | Low | Review of PR #18 (M6-14) | UC-M6-01 | Closed | `uc-m6-simulation.puml` and `.svg` added and linked | PR #39, `8f75fab` |
| DEF-M6-005 | Formulas and lists in report section 3.5 did not render | Low | Review of PR #18 (M6-15) | FR-12 | Closed | Formulas written as `$$...$$`, lists split | PR #39, `e048c39` |

**DEF-M6-001** (High)
- Steps: run the demand-surge scenario with two target Hubs, H01 and H02, and a third Hub H03 with spare vehicles (`src/simulation/engine.py`, `_find_donor_hub`, on `e612961`).
- Expected: every recommendation takes vehicles from H03. Actual: only the Hub being served was excluded, so H02, also short, could be the donor for H01.
- Resolution: the donor search skips every surge target. Retest: new test `test_a_surge_target_is_never_chosen_as_donor` passes.
<!-- END M6: What-if Simulation -->
