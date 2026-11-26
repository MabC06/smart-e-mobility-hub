# NFR Measurements — M8

> **Owner:** M8 (rerun by M1 on 2026-11-26) · **Commit measured:** `267919e` = `develop` at `0056f23` (all PRs up to #63 merged) plus three fixes to the measurement scripts only (`1a1fba6`, `95d96e7`, `267919e`); clean working tree · **Python 3.12.10**, FastAPI 0.162.0 TestClient, in-memory SQLite, Windows
> Method (D-024): sequential requests in-process on DS-STD (seed 2026: 10 Hubs, 400 spaces, 61 charging points, 350 vehicles, 1,005 users). No concurrent load. Timings are TestClient/in-memory figures, not production guarantees.
> Scripts: `tests/performance/measure_nfr02_03.py`, `tests/performance/measure_nfr01_04_05.py`. Raw files: `docs/testing/evidence/`. The first round (2026-11-23, testing branch `01d68e7`) is kept in section 5 for comparison.

## 1. Results

| NFR | Target | Measured on `develop` (`267919e`) | Verdict |
|---|---|---|---|
| NFR-01 | API read reflects an accepted write, p95 ≤ 1 s | 100/100 writes visible in the next read; read-after-write p95 7.17–8.06 ms, max ≤ 10.37 ms (3 runs) | **Pass** (API part). The UI part (≤ 5 s) is met by design: pages read on each load and O1 polls every 3 s |
| NFR-02 | Reads p95 ≤ 500 ms, max ≤ 2 s | 4 endpoints, 100/100 HTTP 200 each: `GET /hubs` p95 20.6 ms, `GET /hubs/H01/vehicles` 20.9 ms, `GET /api/v1/monitoring/metrics/hubs` 14.7 ms, `GET /charging/queue` 5.8 ms; max ≤ 98.9 ms | **Pass** for the 4 measured endpoints |
| NFR-03 | Writes p95 ≤ 1 s | `POST /charging/requests/immediate`: 100/100 OK, p95 231.4 ms, max 286.1 ms | **Pass** for the measured operation (see note 1) |
| NFR-04 (charging) | Schedule for one Hub ≤ 3 s | Queue of 15 per Hub (9 to 15 where a Hub has fewer vehicles), all 10 Hubs: worst Hub 1.64 s, 1.75 s, 1.73 s (3 runs) | **Pass** at the DS-STD load; see section 2 for depth 50 |
| NFR-04 (allocation) | Network recommendation ≤ 5 s | `POST /allocation/tasks/plan` with M2's real `ReservationDemand` provider: 5/5 HTTP 200, max 309 ms, 358 ms, 335 ms (3 runs) | **Pass** (first measurement with the real provider) |
| NFR-05 | Each of 5 scenarios ≤ 30 s | SC-01 to SC-05, 5 runs each, all HTTP 200; slowest run per scenario across 3 rounds: SC-01 148 ms, SC-02 50 ms, SC-03 114 ms, SC-04 128 ms, SC-05 73 ms | **Pass** for all five scenarios |
| NFR-12 | Operational state unchanged after a run | State read before and after the 25 runs is identical in all 3 rounds; `tests/simulation` isolation tests pass (TC-M6-006 to 009 also check it per scenario) | **Pass** |
| NFR-13 | Same seed ⇒ same output | For each scenario, 5 runs with seed 42 give the same report after removing wall-clock fields (`as_of`, `executed_at`, `taken_at`), 3 rounds | **Pass** |
| NFR-14 | Fresh clone ≤ 15 min, ≤ 5 commands | Not repeated: measured by M8 on 2026-11-23 on a local clone (`fresh-nfr14`), 5 commands, 4m34s. The setup steps have not changed since | **Pass** (2026-11-23) |
| NFR-24 | core ≥ 70 %, others ≥ 60 % | core 98.8 %, reservation 92.1 %, charging 89.0 %, allocation 91.7 %, monitoring 87.3 %, simulation 92.7 %, ui 91.9 %, iot_sim 99.0 % (one full run, 1,560 passed, 1 skipped); CI run `45666388041` on `0056f23` (coverage step included): success | **Pass** |

Notes:

1. **NFR-03 is slower than on 2026-11-23 (10.6 ms → 231 ms p95), by design.** Since PR #62 M3's request routes bind the Hub's queue right after a request is queued (BR-M3-03, TC-M3-039), so one write now includes an `optimize_queue` for its Hub, and allocation reads M2's real demand. It stays four times under the 1 s target.
2. **NFR-01 reads the Hub the request ended at.** When no slot is free at the requested Hub within 2 hours, M3 moves the request to the Hub that M4 suggests (BR-M3-02); 34 of the 100 requests moved. The script reads the Hub the write answered with (`267919e`); reading the original Hub would miss those 34 and is not a visibility failure.

## 2. NFR-04 charging: depth sweep on Hub H01 (limitation)

DS-STD gives each Hub up to 15 queued requests in the measurement, which is the realistic load. The queue is built through M3's service, which only queues (since PR #62 the routes would bind each request at once). A sweep on H01:

| Queue depth | run 1 | run 2 | run 3 | 2026-11-23 (4 runs) |
|---|---|---|---|---|
| 5 | 49.2 ms | 52.2 ms | 39.0 ms | 19.9–31.6 ms |
| 10 | 83.4 ms | 90.1 ms | 80.8 ms | 41.0–69.3 ms |
| 15 | 220.3 ms | 226.4 ms | 190.4 ms | 122.0–170.4 ms |
| 30 | 1,081.8 ms | 1,120.8 ms | 1,036.8 ms | 666.7–943.8 ms |
| 50 | **4,185.2 ms** | **4,260.4 ms** | **4,223.5 ms** | 2,636–3,834 ms |

Depth 50 now exceeds 3 s in every run. The cost per queued request grows from about 10 ms at depth 5 to about 84 ms at depth 50, so it grows faster than linearly; the step up from 2026-11-23 comes from the booking factor, which now reads M2's real demand for each Hub. This is **DEF-M3-007** (Medium, Accepted by the Lead on 2026-11-24 as a known limitation): NFR-04 for charging holds at the DS-STD load (15 per Hub) and is not met for queues of about 50. Report section 4.4 states it.

## 3. What is still not measured

- **Concurrent load:** all figures are sequential (D-024, DEV-01).
- **UI timings:** NFR-01's UI part (≤ 5 s) is not timed; pages read on every load.
- **NFR-14:** not repeated after 2026-11-23.

## 4. Evidence files

| File | Content |
|---|---|
| `nfr02-03-develop.json` | NFR-02, NFR-03 on `267919e` |
| `nfr01-04-05-develop-run1.json` … `run3.json` | NFR-01, 04 (charging, sweep, allocation with M2's provider), 05 (SC-01 to SC-05), 12, 13 on `267919e` |
| `nfr02-03-phase34.json`, `nfr01-04-05-run1.json` … `run3.json`, `nfr01-04-05-phase34-stub.json` | First round, testing branch `01d68e7` (2026-11-23), kept for comparison |

Reproduce:

```powershell
python tests/performance/measure_nfr02_03.py --output docs/testing/evidence/nfr02-03-develop.json --count 100
python tests/performance/measure_nfr01_04_05.py --output docs/testing/evidence/nfr01-04-05-develop-run1.json
```

## 5. First round (2026-11-23, testing branch `01d68e7`)

NFR-01 p95 3.97–5.23 ms; NFR-02 p95 2.84–12.91 ms; NFR-03 p95 10.6 ms; NFR-04 charging worst 1.50 s at 15 per Hub; NFR-04 allocation blocked (no M2 provider; 78.7 ms with an empty-demand stub, reference only); NFR-05 SC-01 only, p95 113–164 ms; NFR-12/13 Pass for SC-01; coverage core 98.8 %, reservation 96.3 %, charging 88.2 %, allocation 91.5 %, monitoring 87.3 %, simulation 92.4 % (1,501 passed). Superseded by section 1.
