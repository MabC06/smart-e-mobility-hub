<!-- BEGIN M3: Charging & Smart Scheduling -->

# 05: Behavioral Design

## M3 contribution - Charging & Smart Scheduling

> Author: Võ Thanh An. Date: 2026-11-06. **Proposed for team review**.

### Design overview

The behavioral design of Module M3 models the complete lifecycle of electric vehicle charging operations, real-time load balancing, and dynamic queue management across Mobility Hubs. The interaction logic operates on a strict **Interlock and State-Driven Architecture**:

1. **Session Lifecycle Execution:** Every session transitions through formal charging states centered around the baseline `AVAILABLE` state. Physical cable connection, parameter validation (`FR-07.M3.1`), and hardware interlocks (`BR-M3-01`) must be satisfied before power relays close and transition the session to `CHARGING`.
2. **Dynamic Priority & Smart Load Balancing:** The background scheduler continuously re-ranks waiting vehicles based on battery depletion urgency (% SoC) and imminent trip schedule proximity (`BR-M3-03`). Vehicles reaching $\text{SoC} \le 15\%$ trigger an immediate `LOW_BATTERY_THRESHOLD` override flag, elevating them to the head of the active queue.
3. **3-Tier Conflict & Fault Resolution:** Hardware point failures or capacity contention (`UC-M3-08`) trigger an automated 3-tier fallback cascade (`BR-M3-02`): (1) local bay swap at zero operational cost, (2) time-slot shift, or (3) escalation to Module M4 (`UC-M4-07`) for cross-Hub alternative routing.

### UML diagram index

| Artifact              | IDs and Intent                                                                                                                              | Detailed Source and Discussion                                                                                                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Activity Diagram      | Activity workflow covering request validation, dynamic priority queue sorting, load balancing, and 3-tier fault resolution                  | [`charging-activity-diagram.puml`](../design/behavioral/charging-diagrams/charging-activity-diagram.puml) / [Activity Preview](../design/behavioral/charging-diagrams/charging-activity-diagram.svg)             |
| State Machine Diagram | Session lifecycle state transitions enforcing `AVAILABLE` baseline, `PREPARING`, `CHARGING`, `SUSPENDED`, `FAULTED`, and `COMPLETED` states | [`charging-session-state-machine.puml`](../design/behavioral/charging-diagrams/charging-session-state-machine.puml) / [State Preview](../design/behavioral/charging-diagrams/charging-session-state-machine.svg) |

All behavioral diagrams for M3 are maintained as editable `.puml` PlantUML sources with generated `.svg` visual assets in `docs/design/behavioral/charging-diagrams/`.

### Key design decisions

- **OCPP State Alignment & Port Isolation:** The charging state machine strictly adheres to standard EV charging infrastructure protocols (OCPP-compliant states). Ports marked as `OUT_OF_SERVICE` or `FAULTED` are isolated at the database query level, preventing the allocation algorithm from double-booking damaged hardware (NFR-06).
- **Decoupled Grid Load Smoothing:** Power delivery regulation (`SUSPENDED_EVSE`) operates independently from user session state. When peak grid loads occur, energy transfer is temporarily throttled without aborting the underlying user reservation or locking state.
- **Emergency Relay Interlocking:** High-voltage relay disconnects are decoupled from software response loops, triggering hardware-level power isolation within $<100\text{ ms}$ upon fault detection (NFR-08/09).

### Interface alignment and integration

1. **Module M1 (Telemetry Interlock):** M3 listens to M1 telemetry streams for connector latch verification, voltage stability, and thermal alerts before authorizing state transitions (`AVAILABLE` $\rightarrow$ `PREPARING` $\rightarrow$ `CHARGING`).
2. **Module M4 (Cross-Hub Overflow Delegation):** When local Hub capacity is fully saturated or a hardware fault cannot be resolved locally, M3 invokes M4's `AlternativeChargingProvider` port (`UC-M4-07`) to route displaced vehicles to optimal adjacent Hubs.
3. **State Auditability:** All session state changes, priority recalculation events, and fault redirections are written to an immutable event audit log in compliance with NFR-25.
<!-- END M3: Charging & Smart Scheduling -->
