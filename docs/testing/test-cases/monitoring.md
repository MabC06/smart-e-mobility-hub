# Monitoring & Incident Handling Test Cases

> **Owner:** M5 (Đỗ Hoàng Việt) · **Status:** Executed and passing  
> **Test folder:** `tests/monitoring/`

| TC ID | Test case | Verifies | Technique | Expected result |
|---|---|---|---|---|
| TC-M5-001 | Charging point hardware breakdown triggers INC-HW-01 | FR-09.1, FR-09.2, BR-M5-03, NFR-10 | State-transition / Event | `CHARGING_POINT_FAILURE` incident created with `CRITICAL` severity and error code `ERR_CHARGER_OUT_OF_SERVICE` |
| TC-M5-002 | SensorEventRejected triggers parking sensor fault INC-HW-02 | FR-09.1, FR-09.2, NFR-10 | Negative / Boundary / Event | `PARKING_SENSOR_FAULT` incident created with `MEDIUM` severity, mapped to correct `hub_id` |
| TC-M5-003 | Hub reaches 100% capacity triggers INC-CAP-01 | FR-08.3, FR-09.1, BR-M5-02, NFR-01 | Boundary / Threshold | `HUB_CAPACITY_FULL` ticket created with `HIGH` severity; Hub state transitions to `CRITICAL` |
| TC-M5-004 | Hub rental inventory < 2 units triggers INC-CAP-02 | FR-08.2, FR-09.1, NFR-01 | BVA / Fleet inventory | `HUB_VEHICLE_DEFICIT` ticket created with `MEDIUM` severity for target Hub |
| TC-M5-005 | Vehicle battery SoC <= 15% triggers INC-BAT-01 | FR-09.1, FR-09.3, BR-M5-05, NFR-10 | BVA / Safety interlock | `BATTERY_CRITICAL_FAULT` ticket created with `HIGH` severity and error code `ERR_BATTERY_CRITICAL` |
| TC-M5-006 | Telemetry heartbeat loss > 30s triggers INC-COMM-01 | FR-09.1, FR-09.2, NFR-10, NFR-25 | Timeout / Heartbeat | `TELEMETRY_CONNECTION_LOSS` ticket created with `CRITICAL` severity when elapsed time > 30s |
| TC-M5-007 | Vehicle rental trip overdue > 60m triggers INC-USR-01 | FR-09.1, FR-09.2 | Timeout / Operational | `OVERDUE_VEHICLE` ticket created with `LOW` severity and error code `WARN_RENTAL_OVERDUE` |
| TC-M5-008 | Unacknowledged HIGH/CRITICAL incident auto-escalates after 5m | BR-M5-04, FR-09.4, NFR-25 | Timeout / Escalation rule | Status changes from `OPEN` to `ESCALATED`; audit log appended; LOW tickets remain unaffected |
| TC-M5-009 | Repeated failure events for same component deduplicate | FR-09.1, NFR-10 | Idempotency / Duplicate rejection | Exactly 1 `OPEN` ticket exists for the affected entity; no duplicate tickets created |
| TC-M5-010 | Complete incident lifecycle transition with audit log | FR-09.4, NFR-25 | State-transition | Sequential transitions `OPEN` -> `IN_PROGRESS` -> `RESOLVED` -> `CLOSED`; 4 audit log records appended |
| TC-M5-011 | Illegal lifecycle transitions and invalid inputs are rejected | FR-09.4, NFR-18 | Error guessing / Negative | Direct jump `OPEN` -> `CLOSED` rejected; empty resolution notes raise `ValueError`; unknown ID raises `IncidentNotFoundError` |
| TC-M5-012 | Aggregate utilization metrics across individual and network Hubs | FR-08.1, FR-08.2 | Calculation / Aggregation | Parking occupancy % and charger utilization % correctly computed from live entities |
| TC-M5-013 | Hub occupancy >= 90% transitions Hub status to WARNING | FR-08.3, FR-08.4, BR-M5-01, NFR-01 | BVA / Capacity threshold | Hub status updated to `WARNING` via `core.commands.set_hub_status` |
| TC-M5-014 | Hub occupancy dropping below 90% recovers Hub status to ACTIVE | FR-08.4, BR-M5-01 | State recovery | Hub status transitions from `WARNING` back to `ACTIVE` upon freeing parking spaces |
| TC-M5-015 | REST API router endpoints CRUD and security verification | FR-08, FR-09, D-014 | Functional / Integration | Operator with valid bearer token accesses metrics, creates, queries, acknowledges, resolves and closes tickets |
| TC-M5-016 | Module installation into core facade and FastAPI application | D-013, D-018 | Architectural / Installation | Tables `monitoring_incidents` and `monitoring_incident_audit_logs` registered; event handlers bound; router mounted |
| TC-M5-017 | Unauthenticated requests to monitoring endpoints rejected with 401 | NFR-16, D-014, D-023 | Security / Authentication | All 11 endpoints reject unauthenticated requests with `UNAUTHENTICATED` (HTTP 401) |
| TC-M5-018 | Student accounts calling operator endpoints rejected with 403 | NFR-16, D-014, D-023 | Security / RBAC | All 11 endpoints reject student bearer tokens with `FORBIDDEN` (HTTP 403) |
| TC-M5-019 | Operator accounts successfully authenticate and call monitoring API | NFR-16, D-014, D-023 | Security / RBAC | Operator bearer token accepted on all endpoints; actor ID recorded in audit logs |

## Execution record

| Run date | Commit | Command | Result | Evidence |
|---|---|---|---|---|
| 2026-11-17 | Phase 3/4 Final | `pytest tests/monitoring/ -v` | 39 passed (16 functional + 23 security) | Coverage 88% on `src.monitoring` (exceeds 60% threshold) |
