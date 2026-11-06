# 5. Behavioral and Interaction Design

> **Status:** Draft v1.0 · **Lead Consolidator:** Whole Team · **Owner (M5 Sections):** Đỗ Hoàng Việt  
> This document specifies the behavioral dynamics, workflow logic, and component interactions of the Smart E-Mobility Hub system using UML Activity, Sequence, and State Machine diagrams.

---

## 5.1 Activity Diagrams

### 5.1.5 Incident Handling Workflow (Module M5)

The incident management workflow (`FR-09`, `UC-M5-02`) handles automated failure ingestion, immediate safety interlocks, human triage, and resolution closure.

```mermaid
flowchart TD
    START(["● Start: Anomaly Detected"]) --> INTAKE["Ingest Incident Signal (from IoT Sim Telemetry or Operator)"]
    INTAKE --> CREATE["Classify Severity & Create Incident Ticket (Status: OPEN)"]

    CREATE --> COND_INTERLOCK{"Requires Automated<br/>Safety Interlock?<br/>(BR-M5-03, BR-M5-05)"}
    COND_INTERLOCK -->|"Yes"| LOCK["Isolate Resource Immediately<br/>(OUT_OF_SERVICE / Lockout)"]
    COND_INTERLOCK -->|"No"| ALERT["Publish to Operator Work Queue"]
    LOCK --> ALERT

    ALERT --> COND_TIME{"Operator Claims Ticket<br/>within 5 Minutes?<br/>(BR-M5-04)"}
    COND_TIME -->|"No (Timeout)"| ESCALATE["Transition to ESCALATED<br/>& Alert Duty Supervisor"]
    COND_TIME -->|"Yes"| CLAIM["Operator Acknowledges Ticket<br/>(Status: IN_PROGRESS)"]
    ESCALATE --> CLAIM

    CLAIM --> COND_FIX{"Can Incident Be<br/>Resolved Remotely?"}
    COND_FIX -->|"Yes"| RESET["Issue Remote Soft-Reset / Configuration"]
    COND_FIX -->|"No"| TECH["Dispatch Field Technician to Hub Site"]

    RESET --> VERIFY{"Device Resumed<br/>Healthy State?"}
    VERIFY -->|"Yes"| RESTORE["Restore Resource State in core (Available / Active)"]
    VERIFY -->|"No"| TECH
    TECH --> RESTORE

    RESTORE --> CLOSE["Record Root Cause & Resolution Notes<br/>(RESOLVED → CLOSED, Commit Audit Log)"]
    CLOSE --> END_NODE(["◉ End: Incident Resolved"])
```

#### Workflow Narrative:
1. **Intake & Triage:** Fault signals arrive asynchronously from sensor dropouts or charger fault codes. The intake engine instantiates an `IncidentTicket` with status `OPEN`.
2. **Automated Interlocks (`BR-M5-03`, `BR-M5-05`):** If electrical or battery hazards are present, the system immediately cuts charger power and marks the socket `OUT_OF_SERVICE`, or locks out low-battery vehicles ($\le 15\%$) from the rental inventory.
3. **5-Minute Escalation Window (`BR-M5-04`):** For High and Critical tickets, an unacknowledged ticket remaining `OPEN` for $> 5$ minutes automatically promotes to `ESCALATED`, notifying the Duty Supervisor.
4. **Corrective Recovery:** Software/communication anomalies receive an automated remote reset. If hardware remains unresponsive, a field technician is dispatched for physical part replacement.
5. **Closure & Audit Trail (`NFR-25`):** Once verified healthy, the operator logs root cause notes, marks the ticket `RESOLVED` $\rightarrow$ `CLOSED`, and appends the entry to `TicketAuditLog`.

---

## 5.2 Sequence Diagrams

### 5.2.5 Hub Capacity Warning & Status Synchronization (Module M5)

This sequence diagram illustrates the streamlined, event-driven interaction between the telemetry intake, `monitoring` engine, `core` state store, and the Operator Dashboard when a Hub reaches capacity thresholds (`FR-08`, `UC-M5-01`, `BR-M5-01`, `BR-M5-02`).

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Operator
    participant UI as Operator Dashboard (M7)
    participant Core as Core Domain (M1)
    participant M5 as MonitoringService (M5)
    participant IoT as IoT Simulator (M8)

    %% 1. Telemetry Intake
    IoT->>Core: apply_sensor_event(SpaceOccupiedEvent)
    activate Core
    Core->>Core: Commit space state & publish domain event
    Core-->>M5: Event: SpaceOccupancyChanged(hub_id, space_id)
    Core-->>IoT: 200 OK (Accepted)
    deactivate Core

    %% 2. Evaluation & Status Transition
    activate M5
    M5->>Core: get_hub(hub_id)
    Core-->>M5: HubView(occupied=36, capacity=40, version=12)

    M5->>M5: Calculate occupancy ratio = 36 / 40 = 90% (BR-M5-01)

    alt Occupancy >= 90% and < 100% (BR-M5-01: Warning)
        M5->>Core: set_hub_status(hub_id, WARNING, expected_version=12)
        activate Core
        Core->>Core: Verify version, commit WARNING, log audit
        Core-->>M5: Ok(HubStatusView: WARNING, version=13)
        deactivate Core
    else Occupancy == 100% (BR-M5-02: Critical)
        M5->>Core: set_hub_status(hub_id, CRITICAL, expected_version=12)
        activate Core
        Core-->>M5: Ok(HubStatusView: CRITICAL, version=13)
        deactivate Core
    end
    deactivate M5

    %% 3. UI Synchronization
    loop HTMX Polling (every 3 seconds - NFR-01)
        UI->>Core: GET /api/v1/hubs/overview
        Core-->>UI: Return Hubs (Status = WARNING / CRITICAL)
        UI->>Operator: Display Warning Badge & Alert Banner
    end
```

#### Key Architecture Principles Demonstrated:
1. **Separation of Concerns:** Telemetry ingestion is decoupled from evaluation via asynchronous domain events (`SpaceOccupancyChanged`).
2. **Authority over Hub Health (`set_hub_status`):** `core` acts as the persistent store; `monitoring` (M5) is the authoritative evaluator that decides when a Hub becomes `WARNING` or `CRITICAL`.
3. **Concurrency Safety:** All status transitions apply optimistic locking (`expected_version`), rejecting dirty writes if concurrent operations alter Hub state.
4. **Latency Verification (`NFR-01`):** Telemetry updates reflect on the operator console within 3–5 seconds through HTMX active polling.

