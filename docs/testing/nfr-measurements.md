# NFR Measurements — M8

> **Owner:** M8 · **Date:** 2026-11-23 · **Commit measured:** `01d68e764876a4c22fad53145843d164339784f9` (clean working tree) · **Python 3.12.10**, FastAPI 0.162.0 TestClient, in-memory SQLite, Windows
> Method (D-024): sequential requests in-process on DS-STD (seed 2026: 10 Hubs, 400 spaces, 61 charging points, 350 vehicles, 1,005 users). No concurrent load. Timings are TestClient/in-memory figures, not production guarantees.
> Scripts: `tests/performance/measure_nfr02_03.py`, `tests/performance/measure_nfr01_04_05.py`. Raw files: `docs/testing/evidence/`.

## 1. Results

| NFR | Target | Measured (01d68e7) | Verdict |
|---|---|---|---|
| NFR-01 | API read reflects an accepted write, p95 ≤ 1 s | 100/100 writes visible in the next read; read-after-write p95 3.97–5.23 ms, max ≤ 6.40 ms (3 runs) | **Pass** (API part). UI ≤ 5 s is M7's part and is not measured here |
| NFR-02 | Reads p95 ≤ 500 ms, max ≤ 2 s | 4 endpoints, 100/100 HTTP 200 each: p95 10.831 / 12.908 / 11.221 / 2.840 ms; max ≤ 41.589 ms | **Pass** for the 4 measured endpoints |
| NFR-03 | Writes p95 ≤ 1 s | `POST /charging/requests/immediate`: 100/100 OK, p95 10.573 ms, max 12.232 ms | **Pass** for the measured operation |
| NFR-04 (charging) | Schedule for one Hub ≤ 3 s | Queue depth 15 per Hub, all 10 Hubs: worst 1.03 s, 1.03 s, 1.50 s, 1.41 s (stub run and runs 1–3) | **Pass** at depth 15; see 2 for depth 50 |
| NFR-04 (allocation) | Network recommendation ≤ 5 s | `POST /allocation/tasks/plan` returns 503 `RESOURCE_UNAVAILABLE`: no `ReservationDemand` provider registered (M2) | **Blocked** until M2 registers its provider. With an empty-demand stub: p95 78.7 ms (reference only, not a pass) |
| NFR-05 | Each of 5 scenarios ≤ 30 s | SC-01 only: 5/5 OK, p95 113–164 ms. SC-02 to SC-05 are not implemented (DEV-08) | **Partial** (SC-01 passes) |
| NFR-12 | Operational state unchanged after a run | State hash identical before/after, 3 runs + stub run (SC-01); `tests/simulation` isolation tests pass | **Pass** for SC-01 |
| NFR-13 | Same seed ⇒ same output | Two runs identical after removing wall-clock fields (`as_of`, `executed_at`, `taken_at`), 3 runs + stub run | **Pass** for SC-01 |
| NFR-14 | Fresh clone ≤ 15 min, ≤ 5 commands | Not performed | **Open** |
| NFR-24 | core ≥ 70 %, others ≥ 60 % | core 98.8 %, reservation 96.3 %, charging 88.2 %, allocation 91.5 %, monitoring 87.3 %, simulation 92.4 % (one full run, 1501 passed, 1 skipped) | **Pass** |

## 2. NFR-04 charging: depth sweep on Hub H01 (limitation)

DS-STD gives each Hub up to 15 queued requests in the measurement, which is the realistic load. A sweep on H01 shows how the time grows with the queue:

| Queue depth | stub run | run 1 | run 2 | run 3 |
|---|---|---|---|---|
| 5 | 19.9 ms | 20.4 ms | 31.6 ms | 26.9 ms |
| 10 | 47.2 ms | 41.0 ms | 69.3 ms | 53.7 ms |
| 15 | 122.0 ms | 122.6 ms | 170.4 ms | 160.9 ms |
| 30 | 674.6 ms | 666.7 ms | 943.8 ms | 923.1 ms |
| 50 | 2,636 ms | 2,669 ms | **3,834 ms** | **3,555 ms** |

Depth 50 exceeds 3 s in 2 of 4 recorded runs (and in two earlier console runs: 3.04 s and 3.10 s). Time per queued request rises from about 4 ms to 53–77 ms, so the cost grows faster than linearly. Run-to-run spread is machine load. Recorded as proposed **DEF-M3-007** (Medium) in `defect-log.md`; M3 to confirm the cause. Report section 4.4 states: NFR-04 for charging holds at the DS-STD load (15 per Hub) and is not shown for queues of about 50.

## 3. NFR-04 allocation and NFR-05 scenarios: why not complete

- **Allocation:** `develop` plus PRs #45–#52 contains no M2 provider for `ProviderPort.RESERVATION_DEMAND` or `HOLD_CONSUMER` (PR #52 changes documents only; DEV-09, DEV-16). TC-M8-017 therefore still asserts the absence. Rerun `measure_nfr01_04_05.py` (without `--stub-reservation-demand`) once M2 registers the providers.
- **Scenarios:** M6 implements the demand surge only (DEV-08). SC-02 to SC-05 are reported as not implemented, not as passed.

## 4. Evidence files

| File | Content |
|---|---|
| `nfr02-03-phase34.json` | NFR-02, NFR-03 on 01d68e7 (supersedes `nfr02-03-python312-rerun.json`, taken on `bb5c622`) |
| `nfr01-04-05-run1.json` … `run3.json` | NFR-01, 04, 05, 12, 13 without a provider stub |
| `nfr01-04-05-phase34-stub.json` | Same, with the empty-demand stub (allocation timing, reference only) |

Reproduce:

```powershell
py tests/performance/measure_nfr02_03.py --output docs/testing/evidence/nfr02-03-phase34.json --count 100
py tests/performance/measure_nfr01_04_05.py --output docs/testing/evidence/nfr01-04-05-run1.json
```
