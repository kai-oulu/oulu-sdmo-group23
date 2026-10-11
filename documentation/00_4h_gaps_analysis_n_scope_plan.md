# 4-Hour Gaps Analysis & Scope Plan — Group 23 (v4 with pre-check, DB, analytics, Part1 consolidation)

> Goal: pass peer review (11 Oct) with minimal viable 3-tier + PQC + CI/CD + DB + observability + docs. Keep design simple!
> Audience for Part2: C-suite/managers, non-CS background, business risk focus.

## PROGRESS LOG (updated 2026-10-10)
- [x] Step 0 PRE-CHECK: Ran pytest → 27 passed, 6 failed (baseline confirmed). ML-KEM lib works (pk 800B, ct 768B). cloud_service.py empty confirmed.
- [x] Step 1 FIX GATEWAY: Implemented hardening (try/except, REQUIRED_FIELDS, seen_nonces replay cache, logging, metrics). Fixed 1 extra test (large packet) by updating payload to include required fields. Result: **33 passed, 0 failed** (pytest -v). Manual E2E legacy→gateway works.
- [x] Step 2 PQC + Cloud + DB + Analytics (DONE, broken into sub-steps below)
  - [x] 2a: pqc_utils.py (ML-KEM helpers) — round-trip test ok, packet 845B (768 ct +12 nonce + aes)
  - [x] 2b: cloud_service.py with SQLite DB init + insert — creates telemetry.db, table, inserts, pk 800B file
  - [x] 2c: cloud analytics + health endpoint 6001 + PQC metrics — health returns db_rows, avg_temp, last_10, decaps_ok/fail, avg_decaps_ms, success_rate
  - [x] 2d: gateway forwarding to cloud + fallback log — forward_to_cloud() with PQC encrypt, fallback to gateway_fallback.log when pk missing or cloud down, metrics forwarded/fallback
  - [x] 2e: E2E test legacy→gateway→cloud→DB — tested: 2 msgs → DB has 2 rows, health 6001 shows db_rows 2, avg_temp 21.8, decaps_ok 2, success_rate 1.0; gateway health 5001 shows received 2, forwarded 2; fallback test: no cloud → fallback.log has 1 entry, metrics fallback_local=1
- [x] Step 3 Ops (Docker, CI) — DONE: CI yml with test + docker build jobs, Dockerfile simple python:3.13-slim with HEALTHCHECK, docker-compose with cloud+gateway, healthchecks, volumes for pk sharing, now respects pyproject.toml + uv.lock + .python-version (setup-uv, uv sync --frozen)
- [x] Step 4 Docs consolidation + Part1 final — DONE (Part1): Created 03_mlkem_integration.md, 04_migration_fallback_strategy.md, 05_operations.md, 06_final_evaluation.md, part1_documentation.md consolidated, updated 02_design_decisions_n_key_llm_interactions.md with Interactions 6-10 (gateway hardening, ML-KEM, cloud+DB+analytics, forwarding+fallback+health, Docker+CI), updated README with 3-tier instructions, updated .gitignore for *.db, *.bin
- [x] Step 4 Part1 final polish — DONE: 06_final_evaluation.md v2 removed redundancy (LLM eval duplicated from 02_, Risks remain list duplicating R1-R7, Conclusion repeating Strengths/Weaknesses), new structure Overview with E2E evidence, Strengths with evidence, Weaknesses & Tech Debt combined table with why it matters, Risks R1-R7 consolidated status, What If Not Fully Integrated per course Q&A, Conclusion concise; explained Dockerfile implicit convention (docker-compose build: . == build {context: ., dockerfile: Dockerfile} implicit, docker build . == docker build -f Dockerfile .); runtime table pyproject.toml+uv.lock+.python-version used local+CI+Docker, Dockerfile local+CI, compose local only, ci.yml GitHub only; pytest 33/33 still pass, artifacts cleaned
- [ ] Step 4 Part2 report — next: part2_report.md perspective 3, C-suite/manager audience, non-CS friendly, with public citations

## 0. PRE-CHECK: Test Current Build BEFORE Any Edits (CRITICAL)

**Why:** Ensures baseline works, avoids debugging compounded issues after edits.

**Executed 2026-10-10 baseline:**
- **Pytest**: `/tmp/venv/bin/python -m pytest -v` → 27 passed, 6 failed (matches 01_baseline_analysis.md)
  - Failed: malformed_nonempty, mid_packet, two_packets_share_one_connection, non_json_payload, wrong_schema, replayed_packet
  - Root cause: gateway lacks try/except, schema validation, replay cache → crashes exit 1
- **Manual E2E**: legacy→gateway happy path works but crashes on bad input
- **Cloud**: `src/cloud_service.py` 0 bytes empty → biggest gap
- **ML-KEM lib**: `mlkem==0.0.3` works: `ML_KEM(ML_KEM_512).key_gen() -> pk 800B, sk 1632B`, `encaps -> ss 32B, ct 768B`, `decaps ok True`
  - API: `m = ML_KEM(ParameterSet.ML_KEM_512); ek, dk = m.key_gen(); ss, ct = m.encaps(ek); ss2 = m.decaps(dk, ct)`

**Pre-check checklist:**
- [x] Run pytest, record 27/33
- [x] Run legacy+gateway happy path manually, capture output
- [x] Confirm cloud_service empty
- [x] Confirm mlkem API works
- [x] Git status clean, on branch `arena/...`
- [x] Ensure not committing 02a/b/c txts or reference PDFs (check .gitignore)

**Post-fix check (Step 1):**
- [x] pytest → 33 passed, 0 failed
- [x] Manual E2E with 2 sends works (logs show valid telemetry)
- [x] No regression in unit tests

## 1. Repo Deep Dive Summary

**Exists:**
- `legacy_device.py`: AES-128-GCM, 12B nonce, EOF framing, TCP 5000
- `edge_gateway.py`: now hardened, 33/33 pass
- `cloud_service.py`: empty (to be built)
- Tests: now 33/33 pass
- Docs: `01_baseline_analysis.md`, `02_design_decisions...md` logs 5 LLM interactions
- `pyproject.toml`: cryptography + mlkem

**Missing:**
1. Cloud tier + ML-KEM Link2 + simple DB + analytics
2. Ops: CI/CD, Docker, health, logging, metrics, PQC observability
3. Docs: migration/fallback, ML-KEM integration, ops, final eval, consolidated Part1 doc
4. Part2 report draft perspective 3

## 2. Course Q&A Clarifications (Instructor, from slides/forum)

- Hosting: entire pipeline is modelled/simulating, just code → `docker-compose up` local is enough, no real cloud deploy needed. Generate all code via LLM from scratch (requirement).
- ML-KEM lib: free choice, e.g. `kyber-py` example → keep `mlkem==0.0.3`, validated API above, simplest.
- Incomplete integration OK if documented in final evaluation → aim minimal viable, document gaps.
- Operational suitability: assess BOTH fit for ops needs AND perf/security → need health + metrics + logging.
- Presentation: what feels important to you → focus on legacy 2KB SRAM constraint, PQC offload pattern, LLM trust issues.

## 3. Do we need a simple DB at cloud? YES — reasoning

- Cloud role: "Ingestion API, Decapsulates PQC, Stores telemetry" → storing expected
- Peer review checks 3-tier E2E persistence, not just print
- Decision: **SQLite (stdlib, 1 file, 20 lines)** — enables analytics queries
- Design: `sqlite3.connect('telemetry.db')`, table:
  ```sql
  CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT, timestamp INTEGER, temperature REAL, humidity REAL, status TEXT,
    received_at INTEGER, source_ip TEXT, pqc_decaps_ms REAL
  )
  ```
- Gitignore `*.db`, `*.bin`, `*.log`, create at runtime

**Observability = analytics on cloud — YES:**
- Minimal analytics:
  - Counters: total_received, decaps_fail, json_invalid
  - SQL: COUNT, AVG(temp/humidity), last 10, MAX(timestamp)
  - PQC: avg_decaps_ms, success_rate
  - Health 6001 JSON: db_rows, analytics, pqc metrics, uptime
  - Gateway health 5001: received, rejected, replayed, forwarded, fallback
  - Logs: INFO timestamp + PQC observability (encaps_ms, ct_len=768)

## 4. Minimal Architecture v3 (with DB + analytics)

```
[Legacy Device] --AES-GCM PSK, TCP 5000, EOF--> [Edge Gateway]
                                                    | decrypt, validate, replay check
                                                    | counters: received/rejected/replayed/forwarded/fallback
                                                    | health 5001 JSON
                                                    | load cloud_public_key.bin (800B)
                                                    | if ok: pqc_utils.encrypt_for_cloud() -> TCP 6000
                                                    | else: fallback to gateway_fallback.log
                                                    v
                                             [Cloud Service] TCP 6000 data, 6001 health/analytics
                                                    | split ct(768)||nonce(12)||aes_ct
                                                    | decaps(dk,ct) -> ss, AES-256-GCM decrypt
                                                    | INSERT INTO telemetry (sqlite)
                                                    | health/analytics JSON + logs
```

Wire Link2: `ct(768) + nonce(12) + aes_ciphertext+tag`, hybrid AES-256-GCM with ss 32B
- Public key distribution: cloud writes `cloud_public_key.bin` on start, gateway reads file (Phase1 file-based)
- Fallback: gateway store-and-forward, cloud logs decaps fails but keeps running

## 5. Must-Do Checklist (priority order for 4h)

### Step 0 (15min) — PRE-CHECK
- [x] pytest 27/33 recorded
- [x] Manual happy path test
- [x] Confirm mlkem works
- [x] Git status clean
- [x] After each fix: re-run pytest

### Step 1 (30min) — Fix gateway to make 33/33 pass
- [x] `edge_gateway.py`: REQUIRED_FIELDS, seen_nonces=set(), try/except, log reject, continue
- [x] Handle empty buffer, concatenated packets
- [x] Add logging + counters
- [x] Update large packet test to include required fields
- [x] Test: pytest → 33/33

### Step 2 (60-75min) — PQC + Cloud + DB + Analytics (BROKEN DOWN)

#### 2a: pqc_utils.py — ML-KEM helpers (15min)
- [x] Create `src/pqc_utils.py`
  - Constants: `MLKEM_PARAM=ML_KEM_512`, `CT_LEN=768`, `PK_LEN=800`, `SS_LEN=32`
  - `generate_keypair() -> (ek, dk, mlkem_obj)` + save `cloud_public_key.bin`
  - `encrypt_for_cloud(plaintext_bytes: bytes, ek_bytes: bytes) -> packet: ct+nonce+aes_ct` with timing
  - `decrypt_from_gateway(packet: bytes, dk, mlkem_obj) -> plaintext_bytes` with timing
  - Use AESGCM with ss (32B) as key, 12B random nonce
  - Logging for PQC observability
- [x] Test: unit test for round-trip `encrypt->decrypt` in python REPL — OK packet 845B

#### 2b: cloud_service.py — DB init + core loop (20min)
- [x] Implement `cloud_service.py`:
  - On start: `mlkem_obj = ML_KEM(ML_KEM_512); ek, dk = key_gen(); save pk`
  - `init_db()`: sqlite3 create table if not exists
  - `insert_telemetry(device_id, timestamp, temp, humidity, status, received_at, source_ip, decaps_ms)`
  - TCP server 6000: recv until EOF, split `[:768]` ct, `[768:780]` nonce, rest aes_ct, decaps, AES decrypt, json loads, insert
  - Counters: `total_received`, `decaps_ok`, `decaps_fail`, `json_fail`
  - Logging INFO with timestamps
- [x] Test: run cloud alone, check `telemetry.db` created — OK 12K, pk 800B, health returns db_rows 0

#### 2c: cloud analytics + health endpoint 6001 (15min)
- [x] Add `get_analytics()`:
  - `SELECT COUNT(*)`, `AVG(temperature)`, `AVG(humidity)`, `SELECT * ORDER BY received_at DESC LIMIT 10`
  - PQC metrics: `avg_decaps_ms`, `success_rate = ok/(ok+fail)`
  - Uptime tracking
- [x] Add health thread: simple TCP or HTTP server on 6001 returning JSON with `status, db_rows, analytics, pqc, uptime`
  - Minimal: socket server that on accept returns JSON, or use `http.server` stdlib
  - No Flask/FastAPI to keep simple
- [x] Test: curl health endpoint, check JSON — OK returns analytics, pqc success_rate 1.0

#### 2d: gateway forwarding to cloud + fallback (15min)
- [x] Extend `edge_gateway.py`:
  - Add `CLOUD_HOST=127.0.0.1`, `CLOUD_PORT=6000`, `CLOUD_PK_PATH=cloud_public_key.bin`
  - Add `forward_to_cloud(telemetry_json_str: str) -> bool`:
    - Try load pk file, if missing → log warning, append to `gateway_fallback.log`, increment fallback counter, return False
    - Else: call `pqc_utils.encrypt_for_cloud`, socket sendall to cloud:6000, with try/except
    - On cloud down / exception → fallback log + counter
  - Call `forward_to_cloud` after successful legacy decrypt
  - Update metrics: `forwarded_to_cloud`, `fallback_local`
  - Add health thread 5001 returning JSON with metrics
- [x] Test: gateway forwarding with cloud down (should fallback), then with cloud up — OK fallback.log has entry, metrics fallback_local=1; with cloud up forwarded=2

#### 2e: E2E test legacy→gateway→cloud→DB (10min)
- [x] Run 3 terminals: cloud (6000+6001), gateway (5000+5001), legacy
- [x] Check: gateway prints `Received`, cloud prints/logs, `telemetry.db` has row `SELECT *` — OK 2 rows
- [x] Check health endpoints: `nc 127.0.0.1 5001`, `nc 127.0.0.1 6001` or curl — OK both return JSON
- [x] Run pytest again → still 33/33 (ensure no regression) — OK 33 passed
- [x] Document fallback scenario: stop cloud, send legacy, check `gateway_fallback.log` — OK

### Step 3 (45min) — Operations (UPDATED to respect pyproject.toml + uv.lock + .python-version + inline comments + volume fix)
- [x] `.github/workflows/ci.yml`: now uses `astral-sh/setup-uv@v4` which reads `.python-version` (3.13) and `uv.lock`, runs `uv sync --frozen` (respects pyproject.toml + uv.lock), then `uv pip install pytest` + `uv run pytest -v` — created, tested locally 33 passed, pqc round-trip ok, imports ok, verifies consistency of .python-version, pyproject.toml, uv.lock. Added detailed inline comments explaining: test job runs first, docker-build needs test (sequential dependency), how docker build works (COPY pyproject.toml uv.lock .python-version README.md, RUN uv sync --frozen --no-install-project, ENV PATH .venv/bin), how it links to docker-compose (compose uses same Dockerfile, CI just verifies builds, compose is for local deployment)
- [x] `Dockerfile`: now FROM python:3.13-slim, `pip install uv`, COPY pyproject.toml uv.lock .python-version README.md, RUN `uv sync --frozen --no-install-project` (respects lock, creates .venv), ENV PATH .venv/bin, HEALTHCHECK — updated to respect all three files, simple, reproducible, with comments
- [x] `docker-compose.yml`: FIXED volume issue: old used file bind mounts ./cloud_public_key.bin:/app/cloud_public_key.bin fragile (if host file doesn't exist Docker creates DIRECTORY). New uses named volume `pqc-shared:/app/shared` with env CLOUD_PK_PATH=/app/shared/cloud_public_key.bin, DB_PATH=/app/shared/telemetry.db, FALLBACK_LOG=/app/shared/gateway_fallback.log. Cloud writes pk to shared volume, gateway reads same. Documented where files come from: cloud_public_key.bin generated by cloud on startup, telemetry.db created by init_db(), gateway_fallback.log created by forward_to_cloud() when pk missing or cloud down. Sensor flow: legacy on host -> host 127.0.0.1:5000 -> mapped to gateway container 5000 -> PQC forward to cloud container via CLOUD_HOST=cloud:6000 Docker DNS. Tests use running_gateway fixture (subprocess, not Docker)
- [x] .gitignore entries for *.db, *.bin, *.log — added telemetry.db, *.db, *.bin, fallback logs
- [x] `pyproject.toml`: added `[dependency-groups] dev = ["pytest>=8.0"]` so pytest is tracked as dev dep, while main deps (cryptography, mlkem) remain locked in uv.lock
- [x] Verified: pytest still 33 passed after pyproject.toml edit and inline comments added, Dockerfile copies correct files, CI checks them
- [x] Added inline comments to `pqc_utils.py`, `edge_gateway.py`, `cloud_service.py` explaining improvements, where files come from, env var overrides for Docker, fallback logic, logging file-only to keep tests clean, metrics thread-safety, PQC observability

### Step 4 (90min) — Docs consolidation + Part1 final + Report draft
- [ ] Create `documentation/part1_documentation.md` (single entry for peer review, inspired by reference example flow but NOT authoritative):
  1. Overview & Requirements mapping
  2. Architecture (2-tier baseline + 3-tier final)
  3. Component Details (legacy, gateway, cloud, pqc_utils, DB schema)
  4. How to Run (local 3 terminals + docker-compose)
  5. Baseline Analysis summary
  6. Design Decisions & LLM Interactions
  7. ML-KEM Integration
  8. Migration & Fallback Strategy
  9. Operations (CI/CD, deployment, logging, metrics, health, PQC observability, DB analytics)
  10. Testing & Evaluation (33/33)
  11. Final Evaluation (strengths, weaknesses, tech debt, risks R1-R5)
  12. References (public sources)
  13. Appendix: LLM prompts full log
- [ ] Update `02_design_decisions_n_key_llm_interactions.md`: add Interactions 6-10 (gateway hardening, ML-KEM, cloud+DB+analytics, Docker+CI, monitoring)
- [ ] New `03_mlkem_integration.md`
- [ ] New `04_migration_fallback_strategy.md`
- [ ] New `05_operations.md`
- [ ] New `06_final_evaluation.md`
- [ ] Update README
- [ ] Draft `report_perspective3_draft.md` (max 5 pages, C-suite friendly)

### What to SKIP to stay in 4h
- No per-device subkeys (global PSK, doc as debt)
- No TLS on Link2 (justify: PQC KEM gives confidentiality)
- No asyncio (keep sync + try/except)
- No ORM (raw sqlite3)
- No Prometheus/Grafana (JSON health)
- No frontend

## 6. Part2 Report — Perspective 3 Research Plan (C-suite, non-CS)

**Perspective**: Information security and organizational cybersecurity
**Audience**: C-suite, managers, non-CS — avoid heavy math, focus on business risk, cost, timeline, fallback

**Writing style:**
- Analogies: "harvest now decrypt later = stealing locked safe to open later"
- Explain ML-KEM as "NIST-approved lock quantum computers can't pick"
- Focus: risk, why act now, migration cost, keeping legacy running, fallback
- Tables, phased roadmap, business continuity

**Public sources:**
- [1] https://www.encryptionconsulting.com/education-center/ml-kem-fips-203/
- [2] https://www.cisa.gov/topics/risk-management/quantum
- [3] https://www.aha.org/fbi-tlp-alert/2023-08-23-quantum-readiness-migration-post-quantum-cryptography
- [4] https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/
- [5] https://vucense.com/privacy-sovereignty/post-quantum-cryptography/ml-kem-fips-203-implementation-guide-2026/
- [6] https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems
- [7] https://thequantuminsider.com/2026/05/12/cryptographic-inventory-challenges-post-quantum-transitions/
- [8] https://www.digicert.com/content/dam/digicert/pdfs/guide/ultimate-guide-to-pqc.pdf

**Report structure (5 pages max):**
1. Exec Summary: quantum threat = business risk
2. Why legacy matters: 2KB RAM can't do PQC (needs 3KB), offload to gateway
3. Org migration roadmap (CISA 5 priorities)
4. Our phased strategy: Phase0 PSK, Phase1 hybrid offload, Phase2 future devices, fallback
5. Key mgmt & supply chain: PSK in Flash vs ML-KEM pk file, vendor cooperation 60-80%
6. LLM as untrusted: risk of AI code (static nonce), caught via tests
7. Observability & analytics: DB + health + PQC metrics for managers
8. Risks & compliance, conclusion with cost/timeline 10-20y

## 7. LLM Prompt Log Template

For each artifact log:
- Context/objective
- Prompt given
- LLM output summary
- Human review: accepted/modified/rejected + why + how verified

Need: baseline (done), test plan (done), gateway hardening (done, needs doc), ML-KEM integration, cloud+DB+analytics, Docker+CI, monitoring.

## 8. Next Steps

Order:
1. [x] Pre-check + fix gateway -> 33/33
2. [ ] Step 2a-2e PQC + Cloud + DB + Analytics (now broken down)
3. [ ] Step 3 Docker + CI + health/logging
4. [ ] Step 4 Docs + consolidated part1 doc + report draft

Will NOT commit 02a/b/c.txt or reference PDFs.

