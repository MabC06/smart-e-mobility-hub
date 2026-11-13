# Stakeholder and actor analysis

> Consolidation owner: M2 - 2452620. Updated 2026-11-01. Draft for module-owner review; identifiers follow CONTRIBUTING section 5.

## Boundary and stakeholders

The system boundary contains the application UI, Core and business modules. Student and Operator are external human actors. Private EV owner specializes Student; it is an ownership-dependent role, not a separate authentication mechanism. The simulated sensor/event source (`iot_sim`, M8) is an external supporting actor under D-004. Core, scheduler, allocation engine, database and clock are internal collaborators, not external actors in the overview. No real charging hardware, payment provider, GPS service or external identity provider is assumed.

| Stakeholder | Interest / responsibility | Participation |
|---|---|---|
| Student / renter | Find a usable vehicle, receive a reliable hold, pick up and return safely | Primary actor for M2 rental and parking; charging requests through M3 |
| Private EV owner (Student) | Register ownership, reserve parking/charging, arrive and depart without duplicate occupancy | Specialized actor for M3 private profile/charging and M2 private parking |
| Operator / duty supervisor | Monitor capacity, handle incidents, authorize dispatch and evaluate simulation | Operator actor; supervisor is an escalation responsibility within this role, pending any future permission split |
| Campus mobility service owner | Capacity, availability, safety and operational policy | Stakeholder; no additional login/UC invented |
| Development / QA team (M1-M8) | Consistent contracts, testability and traceability | Stakeholders; module names are not human actors |
| Course evaluators | Assess design, traceability and honest AI declaration | Stakeholders; no runtime use case |

## Actor participation by use case

Ranges below enumerate consecutive IDs in the cited owner document. This is an actor-participation index, not a reverse FR/BR traceability sheet; M8 derives the latter from owner `Trace:` fields.

| Actor / participant | Use cases | Role and boundary qualification |
|---|---|---|
| Student | UC-M2-01, UC-M2-02, UC-M2-03, UC-M2-04, UC-M2-05 | Primary: search, reserve, cancel, pick up, return rental |
| Student | UC-M2-06, UC-M2-07 | Primary: reserve/cancel parking, either private stay or active rental return hold |
| Private EV owner | UC-M2-08 | Primary: private arrival/departure; inherited Student parking goals apply |
| Student | UC-M3-01, UC-M3-02, UC-M3-03 | Primary: immediate charging, future charging, cancel/modify charging |
| Private EV owner | UC-M3-04, UC-M3-05 | Primary: register private EV profile and reserve its charging slot |
| Operator | UC-M3-06, UC-M3-07, UC-M3-08 | Supervise queue/scheduling and failure recovery; automatic triggers stay internal, not additional external actors |
| Operator | UC-M4-01, UC-M4-02, UC-M4-03, UC-M4-04, UC-M4-09 | View recommendations; approve/reject/adjust; execute; cancel; change allocation settings |
| Student via M2 | UC-M4-05 | Beneficiary/requester of advisory alternative Hubs, reached through Core |
| Internal allocation / charging flow | UC-M4-06, UC-M4-07, UC-M4-08 | Arbitration, displaced-charging lookup and re-plan; M3 is a collaborator, not an external actor. UC-M4-07 is invoked from UC-M3-08 per D-012 |
| Operator | UC-M5-01, UC-M5-02 | Primary: monitor network and handle operational incidents |
| Operator | UC-M6-01 | Primary: configure/run isolated what-if simulation and inspect results |
| Operator | UC-M7-01 through UC-M7-10 | UI participation; most entries are views of owner use cases, mapped below |
| Simulated sensor/event source | UC-M4-03, UC-M4-08; UC-M5-01, UC-M5-02 | Supporting: dispatch observations, re-plan triggers, resource status and incident events via Core |
| Simulated sensor/event source | UC-M2-08; UC-M7-01, UC-M7-03, UC-M7-07, UC-M7-08 | Supporting occupancy/status evidence; not authorization to bypass ownership, custody or Core transition checks |

Student reports may trigger incident handling, but the inspected M5 table names Operator as the primary actor. No separate student incident-report UC is invented here. Authentication is a precondition in the owner documents; a new login UC ID is not allocated by this consolidation.

## UI overlap and consistency

| M7 UI entry | Canonical business use case(s) / treatment |
|---|---|
| UC-M7-01 | View of UC-M5-01 |
| UC-M7-02 | M7-owned resource-state override; coordinate legal transitions/authorization with M1 and incident effects with M5 |
| UC-M7-03, UC-M7-04 | Views of UC-M3-06 and UC-M3-07 respectively |
| UC-M7-05 | View of UC-M4-01 |
| UC-M7-06 | View of UC-M4-02 and UC-M4-03 |
| UC-M7-07 | Views of UC-M5-01 and UC-M5-02 |
| UC-M7-08 | View of UC-M5-02 |
| UC-M7-09, UC-M7-10 | Views of UC-M6-01 |

M7 describes applying recommendations in its UI. M6 simulation execution never mutates operational state: application is a separately authorized operational command with fresh checks, owned by the relevant module. M4's `REBALANCE` reservation proposal differs from M2's typed task-owned ResourceClaim proposal; see the [M2 reconciliation](fr-02-05-07-reservation.md). Neither is silently treated as an agreed interface.

## Overview and module ownership

![System use-case overview](use-case-diagrams/uc-overview.svg)

[Editable source](use-case-diagrams/uc-overview.puml). Goal groups do not allocate additional use-case IDs. M2 owns rental/parking, M3 charging, M4 allocation/dispatch, M5 monitoring/incidents, M6 simulation and M7 operator views. Detailed M2 use cases appear in the [requirements](fr-02-05-07-reservation.md), with [rental](use-case-diagrams/uc-m2-rental.svg) and [parking](use-case-diagrams/uc-m2-parking.svg) diagrams.
