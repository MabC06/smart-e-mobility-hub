# M3 - Charging Session State Machine Design

> **Owner:** M3 - Võ Thanh An  
> **Date:** 2026-11-06  
> **Status:** Proposed for Team Review

This document defines the lifecycle and state transitions specific to an M3 charging session at a Mobility Hub. The state machine ensures safe energy transfer, strict hardware interlocks, and real-time synchronization with core services.

---

## 1. Charging Session State Machine Diagram

![Charging Session State Machine](charging-diagrams/charging-session-state-machine.svg)

- **PlantUML Source:** [`charging-session-state-machine.puml`](charging-diagrams/charging-session-state-machine.puml)
- **Traceability:** FR-06.2, FR-07.M3.1; UC-M3-02; BR-M3-01, BR-M1-02.

---

## 2. Session State Transition Details

| Current State | Trigger Event               | Guard Condition / Rule                                      | Next State  | Action & Description                                                         |
| :------------ | :-------------------------- | :---------------------------------------------------------- | :---------- | :--------------------------------------------------------------------------- |
| `AVAILABLE`   | Cable plugged in (`PlugIn`) | Port verified & vehicle identity authenticated (`BR-M3-01`) | `PREPARING` | Initialize session tracking record and reserve port allocation.              |
| `PREPARING`   | Hardware ready              | Voltage check passed & mechanical latch secured             | `CHARGING`  | Close the high-voltage power relay to initiate energy flow.                  |
| `CHARGING`    | Target SoC reached          | Vehicle battery management system signals target met        | `COMPLETED` | Open power relay safely, unlock connector latch, and log metrics.            |
| `CHARGING`    | Fault detected              | Overcurrent, thermal spike, or emergency stop tripped       | `FAULTED`   | Instantly trip safety relay (`TripRelay`), cut power, and alert maintenance. |
| `CHARGING`    | User cancellation           | Valid stop command received via user app or local interface | `CANCELLED` | Safely terminate current flow, release port lock, and close session.         |

---

## 3. System Interfacing & Claim Management

- **Resource Claim Management (D-017):** Module M3 independently places and releases its own `CHARGING_SESSION` resource claims during the charging lifecycle. A claim is placed upon entering `PREPARING` and safely released when transitioning to terminal states (`COMPLETED`, `CANCELLED`, or `FAULTED`).
- **Provider Port Integration (D-020):** Charging sessions and demand data are exposed to **Module M4** (Smart Scheduling) and **Module M6** (Billing / Operations) exclusively via the `ChargingDemand` provider port (`ChargingDemandProvider`).
- **Private EV Onboarding:** Private Electric Vehicles (Private EVs) must be registered in the system using the `register_vehicle` interface before initiating a charging session state transition.

---

## 4. Key Design Rules

- **Fail-Safe Isolation:** Any fault or interruption during the `CHARGING` state immediately drives the hardware into `FAULTED` or `CANCELLED`, ensuring zero risk of electrical arcing or equipment damage.
- **Core Telemetry:** State changes are instantaneously pushed to the core management engine to update hub availability metrics.
