# ID Traceability Sheet

> **Owner:** M8 · **Version:** v1.2 · **Date:** 2026-11-25 · **Baseline:** `01d68e7` (testing branch); v1.2 by M1 for PR #58
> Generated from `docs/requirements/*.md` and the test-case documents (`docs/testing/test-cases/*.md`, `reservation-phase2.md`, M7 test docstrings).

Rule (NFR-26): `FR / BR / UC / NFR → TC → result → defect`. `Covered` = at least one TC names the ID. A TC listed here passed on 01d68e7 unless `test-cases/integration.md` records it as Blocked or Partial (TC-M8-027 Blocked; TC-M8-028 Partial; TC-M8-026 passes at 15 queued per Hub only). TC-M2-024 to TC-M2-026 and TC-M7-028 to TC-M7-033 came after 01d68e7; they passed on PR #58 (`76a0877`, 1524 passed). M8's rerun on `develop` replaces this baseline.

**Summary:** 181 TCs. FR 11/12; BR 26/34; UC 28/38; NFR 18/27 have a TC. TCs with no FR/BR/UC: TC-M5-016, TC-M8-016 (decision references D-013/D-018). Orphan TC references: none.

**NFR-26 is not yet met:** the uncovered IDs below are listed with the reason known so far; module owners must confirm or add TCs.

## 1. Functional requirements

| ID | Status | Test cases |
|---|---|---|
| FR-01 | Covered | TC-M7-001, TC-M7-002, TC-M7-003, TC-M7-009, TC-M7-017, TC-M8-001, TC-M8-009, TC-M8-010, TC-M8-012, TC-M8-013, TC-M8-019 |
| FR-02 | Covered | TC-M7-002, TC-M7-004, TC-M7-009 |
| FR-03 | Covered | TC-M2-001, TC-M2-002, TC-M2-003, TC-M2-004, TC-M2-006, TC-M2-008, TC-M2-014, TC-M2-015, TC-M2-019, TC-M2-022, TC-M2-023, TC-M2-024, TC-M2-026, TC-M7-002, TC-M7-009, TC-M7-028, TC-M7-030 |
| FR-04 | Covered | TC-M2-001, TC-M2-004, TC-M2-006, TC-M2-007, TC-M2-008, TC-M2-010, TC-M2-012, TC-M2-016, TC-M2-017, TC-M2-020, TC-M2-024, TC-M2-026, TC-M7-010, TC-M7-028, TC-M7-029 |
| FR-05 | **GAP** | — |
| FR-06 | Covered | TC-M3-006, TC-M3-007, TC-M3-014, TC-M3-015, TC-M3-016, TC-M7-023, TC-M8-018 |
| FR-07 | Covered | TC-M3-019, TC-M3-020, TC-M3-021, TC-M7-024, TC-M7-025 |
| FR-08 | Covered | TC-M5-003, TC-M5-004, TC-M5-012, TC-M5-013, TC-M5-014, TC-M5-015, TC-M7-009, TC-M7-016, TC-M7-017 |
| FR-09 | Covered | TC-M5-001, TC-M5-002, TC-M5-003, TC-M5-004, TC-M5-005, TC-M5-006, TC-M5-007, TC-M5-008, TC-M5-009, TC-M5-010, TC-M5-011, TC-M5-015, TC-M5-020, TC-M7-008, TC-M7-011, TC-M7-016, TC-M7-019, TC-M8-013 |
| FR-10 | Covered | TC-M4-001, TC-M4-002, TC-M4-003, TC-M4-004, TC-M4-005, TC-M4-006, TC-M4-011, TC-M4-012, TC-M4-013, TC-M4-014, TC-M4-015, TC-M4-018, TC-M4-019, TC-M4-020, TC-M4-021, TC-M4-022, TC-M4-023, TC-M4-024, TC-M4-025, TC-M4-026, TC-M4-028, TC-M4-029, TC-M7-007, TC-M7-009, TC-M7-016, TC-M7-021, TC-M7-022, TC-M8-022, TC-M8-027 |
| FR-11 | Covered | TC-M3-001, TC-M3-002, TC-M3-004, TC-M3-022, TC-M3-023, TC-M3-024, TC-M3-025, TC-M3-027, TC-M3-034, TC-M4-004, TC-M4-007, TC-M4-008, TC-M4-009, TC-M4-010, TC-M4-011, TC-M4-015, TC-M4-016, TC-M4-017, TC-M4-018, TC-M4-019, TC-M4-029, TC-M8-026 |
| FR-12 | Covered | TC-M6-001, TC-M6-002, TC-M7-016, TC-M7-031, TC-M7-032, TC-M8-028, TC-M8-029 |

## 2. Business rules

| ID | Status | Test cases |
|---|---|---|
| BR-M1-01 | Covered | TC-M4-024 |
| BR-M1-02 | Covered | TC-M4-017, TC-M4-018 |
| BR-M1-03 | **GAP** | — |
| BR-M2-02 | Covered | TC-M2-003, TC-M2-004, TC-M2-015, TC-M2-016, TC-M2-022 |
| BR-M2-03 | Covered | TC-M2-014 |
| BR-M2-04 | Covered | TC-M2-001, TC-M2-007, TC-M2-023, TC-M2-026 |
| BR-M2-05 | Covered | TC-M2-023 |
| BR-M2-09 | Covered | TC-M2-001, TC-M2-008, TC-M2-009, TC-M2-025 |
| BR-M2-10 | Covered | TC-M2-001, TC-M2-008, TC-M2-009, TC-M2-010, TC-M2-020, TC-M2-025 |
| BR-M2-11 | **GAP** | — |
| BR-M2-12 | **GAP** | — |
| BR-M2-14 | Covered | TC-M2-017 |
| BR-M2-15 | Covered | TC-M2-026 |
| BR-M3-01 | Covered | TC-M3-006, TC-M3-014, TC-M3-022, TC-M3-036 |
| BR-M3-02 | Covered | TC-M3-022, TC-M3-026, TC-M3-027, TC-M3-034, TC-M3-035, TC-M3-036, TC-M4-016 |
| BR-M3-03 | Covered | TC-M3-001, TC-M3-002, TC-M3-003, TC-M3-004, TC-M3-005 |
| BR-M4-01 | Covered | TC-M4-007, TC-M4-008, TC-M4-009 |
| BR-M4-02 | Covered | TC-M4-007, TC-M4-024 |
| BR-M4-03 | Covered | TC-M4-001, TC-M4-005, TC-M4-014, TC-M4-024, TC-M4-030 |
| BR-M4-04 | Covered | TC-M4-004, TC-M4-018, TC-M4-019, TC-M4-020, TC-M4-025 |
| BR-M4-05 | Covered | TC-M4-001, TC-M4-003, TC-M4-030 |
| BR-M4-06 | Covered | TC-M4-001, TC-M4-021, TC-M4-030 |
| BR-M4-07 | **GAP** | — |
| BR-M4-08 | Covered | TC-M4-018, TC-M4-020, TC-M4-024, TC-M4-026, TC-M4-028 |
| BR-M4-09 | **GAP** | — |
| BR-M4-10 | Covered | TC-M4-012, TC-M4-013, TC-M4-016, TC-M8-022 |
| BR-M4-11 | **GAP** | — |
| BR-M4-12 | **GAP** | — |
| BR-M5-01 | Covered | TC-M5-013, TC-M5-014 |
| BR-M5-02 | Covered | TC-M5-003 |
| BR-M5-03 | Covered | TC-M5-001 |
| BR-M5-04 | Covered | TC-M5-008 |
| BR-M5-05 | Covered | TC-M5-005 |
| BR-M6-03 | **GAP** | — |

## 3. Use cases

| ID | Status | Test cases |
|---|---|---|
| UC-M2-01 | **GAP** | — |
| UC-M2-02 | Covered | TC-M2-001, TC-M2-002, TC-M2-003, TC-M2-004, TC-M2-005, TC-M2-006, TC-M2-008, TC-M2-009, TC-M2-011, TC-M2-013, TC-M2-014, TC-M2-015, TC-M2-019, TC-M2-021, TC-M2-022, TC-M2-024, TC-M7-028, TC-M7-030 |
| UC-M2-03 | Covered | TC-M2-023, TC-M2-024, TC-M7-028 |
| UC-M2-04 | Covered | TC-M2-001, TC-M2-005, TC-M2-006, TC-M2-007, TC-M2-008, TC-M2-009, TC-M2-011, TC-M2-012, TC-M2-013, TC-M2-016, TC-M2-021, TC-M2-024, TC-M7-029 |
| UC-M2-05 | Covered | TC-M2-001, TC-M2-005, TC-M2-006, TC-M2-008, TC-M2-009, TC-M2-010, TC-M2-011, TC-M2-013, TC-M2-017, TC-M2-020, TC-M2-021, TC-M2-024, TC-M7-029 |
| UC-M2-06 | **GAP** | — |
| UC-M2-07 | **GAP** | — |
| UC-M2-08 | **GAP** | — |
| UC-M3-01 | Covered | TC-M3-006, TC-M3-016 |
| UC-M3-02 | Covered | TC-M3-006, TC-M3-007, TC-M3-008, TC-M3-009, TC-M3-010, TC-M3-011, TC-M3-012, TC-M3-013 |
| UC-M3-03 | Covered | TC-M3-015, TC-M3-016, TC-M3-017 |
| UC-M3-04 | Covered | TC-M3-019, TC-M3-020, TC-M3-021 |
| UC-M3-05 | Covered | TC-M3-021 |
| UC-M3-06 | Covered | TC-M3-001, TC-M3-002, TC-M3-004 |
| UC-M3-07 | Covered | TC-M3-022, TC-M3-023, TC-M3-024, TC-M3-025, TC-M3-026, TC-M3-028, TC-M3-034 |
| UC-M3-08 | Covered | TC-M3-016, TC-M3-018, TC-M3-027, TC-M3-028, TC-M3-029 |
| UC-M4-01 | Covered | TC-M4-001, TC-M4-002, TC-M4-003, TC-M4-004, TC-M4-005, TC-M4-006, TC-M4-014, TC-M4-021, TC-M4-022, TC-M4-023, TC-M4-028 |
| UC-M4-02 | Covered | TC-M4-018, TC-M4-024, TC-M4-025, TC-M4-028 |
| UC-M4-03 | Covered | TC-M4-018, TC-M4-019, TC-M4-026, TC-M4-028 |
| UC-M4-04 | Covered | TC-M4-020, TC-M4-028 |
| UC-M4-05 | Covered | TC-M4-011, TC-M4-012, TC-M4-013, TC-M4-014, TC-M4-029, TC-M8-022 |
| UC-M4-06 | Covered | TC-M4-007, TC-M4-008, TC-M4-009, TC-M4-010, TC-M4-029 |
| UC-M4-07 | Covered | TC-M3-034, TC-M3-035, TC-M4-011, TC-M4-016, TC-M4-017, TC-M4-029 |
| UC-M4-08 | Covered | TC-M4-021 |
| UC-M4-09 | Covered | TC-M4-030 |
| UC-M5-01 | **GAP** | — |
| UC-M5-02 | **GAP** | — |
| UC-M6-01 | **GAP** | — |
| UC-M7-01 | Covered | TC-M7-017 |
| UC-M7-02 | **GAP** | — |
| UC-M7-03 | Covered | TC-M7-023 |
| UC-M7-04 | **GAP** | — |
| UC-M7-05 | Covered | TC-M7-022 |
| UC-M7-06 | Covered | TC-M7-007, TC-M7-021 |
| UC-M7-07 | Covered | TC-M7-006, TC-M7-020 |
| UC-M7-08 | Covered | TC-M7-008, TC-M7-011, TC-M7-019 |
| UC-M7-09 | Covered | TC-M7-031, TC-M7-032 |
| UC-M7-10 | **GAP** | — |

## 4. Non-functional requirements

| ID | Status | Test cases |
|---|---|---|
| NFR-01 | Covered | TC-M5-003, TC-M5-004, TC-M5-013, TC-M8-025 |
| NFR-02 | Covered | TC-M8-023 |
| NFR-03 | Covered | TC-M8-024 |
| NFR-04 | Covered | TC-M8-026, TC-M8-027 |
| NFR-05 | Covered | TC-M8-028 |
| NFR-06 | Covered | TC-M2-013, TC-M2-014, TC-M2-015, TC-M2-019, TC-M2-023, TC-M3-024, TC-M3-036, TC-M4-024, TC-M4-025 |
| NFR-07 | Covered | TC-M2-010, TC-M2-024, TC-M4-018, TC-M4-019, TC-M4-020, TC-M8-001, TC-M8-009, TC-M8-010, TC-M8-012, TC-M8-014 |
| NFR-08 | Covered | TC-M2-004, TC-M3-007, TC-M3-008, TC-M3-010, TC-M3-013, TC-M3-018, TC-M4-026 |
| NFR-09 | Covered | TC-M2-001, TC-M2-006, TC-M2-010, TC-M2-011, TC-M2-012, TC-M2-013, TC-M2-021, TC-M2-023, TC-M2-024, TC-M2-025, TC-M3-010, TC-M3-016, TC-M3-024, TC-M4-018, TC-M4-024 |
| NFR-10 | Covered | TC-M3-005, TC-M3-027, TC-M3-029, TC-M4-022, TC-M5-001, TC-M5-002, TC-M5-005, TC-M5-006, TC-M5-009, TC-M5-020, TC-M8-013, TC-M8-015 |
| NFR-11 | **GAP** | — |
| NFR-12 | Covered | TC-M6-003, TC-M6-004, TC-M8-029 |
| NFR-13 | Covered | TC-M4-006, TC-M4-009, TC-M4-012, TC-M4-027, TC-M6-005, TC-M8-002, TC-M8-003, TC-M8-004, TC-M8-005, TC-M8-007, TC-M8-008, TC-M8-029 |
| NFR-14 | **GAP** | — |
| NFR-15 | **GAP** | — |
| NFR-16 | Covered | TC-M2-005, TC-M2-009, TC-M2-016, TC-M2-023, TC-M2-024, TC-M2-025, TC-M3-007, TC-M3-009, TC-M3-011, TC-M3-013, TC-M3-017, TC-M3-020, TC-M3-030, TC-M3-031, TC-M3-032, TC-M3-033, TC-M4-031, TC-M4-032, TC-M5-017, TC-M5-018, TC-M5-019, TC-M7-001, TC-M7-012, TC-M7-013, TC-M7-014, TC-M7-015, TC-M7-026, TC-M7-033, TC-M8-019, TC-M8-020, TC-M8-021 |
| NFR-17 | **GAP** | — |
| NFR-18 | Covered | TC-M2-002, TC-M2-009, TC-M2-019, TC-M2-025, TC-M3-012, TC-M3-023, TC-M3-029, TC-M4-010, TC-M4-015, TC-M4-025, TC-M4-029, TC-M5-011, TC-M5-020, TC-M7-005, TC-M8-006, TC-M8-011, TC-M8-015 |
| NFR-19 | **GAP** | — |
| NFR-20 | Covered | TC-M7-006, TC-M7-020 |
| NFR-21 | Covered | TC-M3-014, TC-M3-031, TC-M4-013, TC-M7-002, TC-M7-005, TC-M7-012, TC-M7-014, TC-M7-016, TC-M7-018, TC-M7-021, TC-M7-024, TC-M7-027, TC-M7-030, TC-M7-032 |
| NFR-22 | Covered | TC-M2-018, TC-M4-011, TC-M4-027, TC-M8-017 |
| NFR-23 | **GAP** | — |
| NFR-24 | **GAP** | — |
| NFR-25 | Covered | TC-M2-011, TC-M5-006, TC-M5-008, TC-M5-010 |
| NFR-26 | **GAP** | — |
| NFR-27 | **GAP** | — |

## 5. Known gaps and reasons

| ID(s) | Reason / action |
|---|---|
| FR-05, UC-M2-06/07/08, BR-M2-11/12 | Parking hold, parking lifecycle and overdue handling are not implemented by M2 (DEV-15, DEV-17). Confirm with M2: accept as out of scope or add TCs |
| UC-M2-01 | Student search flow has no service/router (DEV-14) |
| UC-M5-01/02, UC-M6-01 | M5/M6 TCs cite FR/BR only; owners to add the UC reference to existing TCs if they match |
| UC-M7-02, UC-M7-04, UC-M7-10 | Not offered in the UI: O2 changes no vehicle or charging point and O3 cannot change the queue (DEV-12); O6 shows the result but cannot approve, reject or export a recommendation (DEV-11) |
| BR-M4-07/09/11/12 | Declared unused in the requirements; M4 to confirm and mark withdrawn |
| BR-M1-03, BR-M6-03 | No TC found; owners to confirm |
| NFR-14, NFR-24, NFR-26 | Verified by a fresh-clone check (NFR-14, not yet done), CI/coverage report (NFR-24, passed locally) and this sheet (NFR-26); no TC ID by design |
| NFR-15, NFR-17 | Core tests exist (`nfr-evidence-core.md`) but no TC ID cites them; M1/M8 to add IDs |
| NFR-11, 19, 23, 27 | Withdrawn |
