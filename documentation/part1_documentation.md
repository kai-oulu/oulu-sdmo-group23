# Part 1 Technical Documentation — Oulu SDMO Group 23

**Members:** Kim Nguyen | Manh Nguyen | Quoc Nguyen | Danish Sharjeel | Kaiquan Mah  
**Branch:** `arena/04f59b2c-oulu-sdmo-group23`  
**Python:** 3.13, package manager `uv`, dependencies `cryptography`, `mlkem`

---

## 1. Project Overview & Requirements Mapping

**Goal:** Modernize small legacy edge-cloud system (simulated ATmega328P sensor → edge gateway → cloud) for post-quantum cryptography (ML-KEM), using LLM as untrusted assistant, with critical evaluation.

**Requirements from rqmts1/rqmts2 checklist:**

| Requirement | Status | Evidence |
|-------------|--------|----------|
| AI-assisted development: generate components with LLM, record prompts/outputs/decisions | ✅ Done | `02_design_decisions_n_key_llm_interactions.md` logs 10 interactions (baseline scaffolding, protocol, framing, test plan, test gen, gateway hardening, ML-KEM, cloud+DB+analytics, forwarding+fallback, Docker+CI) |
| Baseline analysis: understand initial architecture, run system, baseline tests/measurements | ✅ Done | `01_baseline_analysis.md` with architecture diagrams, measurements (28B overhead, 95B JSON), 27/33 tests initially |
| Critical evaluation & maintenance: test, review, correct, improve LLM artefacts | ✅ Done | Fixed gateway to make 33/33 pass, corrected `mlkem` API (`key_gen` not `generate`), changed logging to file to avoid test pollution, updated large packet test |
| ML-KEM integration: use existing implementation, at least one path | ✅ Done | `src/pqc_utils.py` + `cloud_service.py` + gateway forwarding, ML-KEM-512 hybrid `ct(768)||nonce(12)||aes_ct`, file-based pk distribution |
| Preserve legacy compatibility / migration & fallback strategy | ✅ Done | `04_migration_fallback_strategy.md` phased migration (Phase0 PSK, Phase1 hybrid offload, Phase2 future), fallback to `gateway_fallback.log` |
| Operations: automate build/testing, deployment to test env, health checks, logs, metrics | ✅ Done | `.github/workflows/ci.yml` (uv sync --frozen + pytest), `Dockerfile` (python:3.13-slim + uv sync --frozen), `docker-compose.yml` with healthchecks, health endpoints 5001/6001, logging to files, metrics counters, PQC observability |
| Final evaluation: strengths/weaknesses, tech debt, risks | ✅ Done | `06_final_evaluation.md` with R1-R5 + new R6,R7, tech debt table |

**Usage of AI (per rqmts2):**
- Must use AI to create code (Part1): Yes, all src files generated via LLM prompts logged in 02_
- Must manually evaluate AI-generated code continuously: Yes, via pytest, manual tamper tests, API validation via REPL, log pollution fix
- Must include prompts in technical documentation: Yes, in 02_ (10 interactions)
- Must report how/where AI used: Yes, in 02_ accepted/modified/rejected matrix
- Must not use AI for personal reflections (Part3): Noted, will be manual

**Constraints:**
- Keep design simple (4h limit): Done — single-threaded gateway, SQLite stdlib, stdlib http.server for health, no Flask, no Prometheus, no per-device keys, no TLS, file-based pk

---

## 2. Architecture

### 2.1 Baseline (2-tier, initial)
```
[Legacy Device: ATmega328P sim] --AES-128-GCM PSK, TCP 5000, EOF--> [Edge Gateway]
  2KB SRAM/32KB Flash, 16B PSK, 12B nonce, 28B overhead (12 nonce+16 tag)
```

### 2.2 Final (3-tier, with PQC, DB, analytics)
```
[Legacy Device] --AES-GCM PSK, TCP 5000, EOF--> [Edge Gateway: 5000 data + 5001 health]
                                                    | decrypt, validate schema, replay check (seen_nonces set)
                                                    | metrics: received/rejected/replayed/forwarded/fallback
                                                    | load cloud_public_key.bin (800B)
                                                    | if ok: pqc_utils.encrypt_for_cloud() -> TCP 6000
                                                    | else: fallback to gateway_fallback.log
                                                    v
                                             [Cloud Service: 6000 data + 6001 health/analytics]
                                                    | split ct(768)||nonce(12)||aes_ct
                                                    | decaps(dk,ct) -> ss 32B, AES-256-GCM decrypt
                                                    | INSERT INTO telemetry.db (SQLite)
                                                    | analytics: COUNT, AVG(temp/humidity), last 10, decaps_ok/fail, avg_decaps_ms, success_rate
```

**Wire formats:**
- Link1: `nonce(12) || ciphertext+tag`, plaintext JSON ~95B, total ~123B
- Link2: `ct(768) || nonce(12) || aes_ct+tag` ~845B for small JSON (768+12+65)

**Why offload PQC to gateway:**
- ATmega328P 2KB SRAM cannot hold ML-KEM-512 sk 1632B + workspace 1000-1500B = ~3KB → stack overflow
- Gateway Linux/Pi has enough RAM, measures encaps 0.03ms, decaps 0.04ms negligible

---

## 3. Component Details

### 3.1 legacy_device.py
- `generate_telemetry()`: device_id sensor-node-01, timestamp int(time.time()), temperature 21.8, humidity 55.4, status OK
- `encrypt_payload(data, key)`: json dumps → utf-8, AESGCM(key), os.urandom(12) nonce, prepend nonce
- `main()`: TCP client to 127.0.0.1:5000, sendall, close (EOF framing)
- PSK: `b"legacy_secret_16"` 16B (128-bit)

### 3.2 edge_gateway.py (hardened)
- `decrypt_payload(packet, key)`: slice [:12] nonce, [12:] ct, AESGCM decrypt, utf-8 decode
- `validate_telemetry_schema(payload)`: checks REQUIRED_FIELDS subset
- `seen_nonces=set()` replay cache (tech debt: no TTL)
- `metrics` dict with lock: received, rejected, replayed, invalid_json, invalid_schema, empty, forwarded_to_cloud, fallback_local, cloud_fail, uptime_start
- `forward_to_cloud(json_str)`: load pk file, if missing/unreachable → append to `gateway_fallback.log` + fallback counter, else `pqc_utils.encrypt_for_cloud` + TCP send to cloud:6000
- `start_gateway()`: TCP server 5000, accept loop with try/except for InvalidTag, ValueError, UnicodeDecodeError, JSONDecodeError, logs warning + continue (no crash), health thread 5001 via http.server returning JSON metrics
- Logging: FileHandler `gateway.log` (not stderr to keep tests clean, tests merge stdout+stderr)

### 3.3 pqc_utils.py
- Constants: PK_LEN 800, SK_LEN 1632, CT_LEN 768, SS_LEN 32, NONCE_LEN 12, CLOUD_PK_PATH cloud_public_key.bin
- `get_mlkem_instance()`: `ML_KEM(ParameterSet.ML_KEM_512)`
- `generate_keypair(save_path)`: `ek, dk = mlkem_obj.key_gen()`, save ek 800B to file, return ek_bytes, dk_bytes, mlkem_obj
- `load_public_key(path)`: read 800B, validate length
- `encrypt_for_cloud(plaintext, ek_bytes)`: load ek via EncapsKey.from_bytes, `ss, ct = mlkem_obj.encaps(ek)`, AESGCM(ss).encrypt(nonce, plaintext), packet = ct+nonce+aes_ct, metrics encaps_ms, total_len
- `decrypt_from_gateway(packet, dk_bytes, mlkem_obj)`: split ct/nonce/aes_ct, `ss = mlkem_obj.decaps(dk, ct)`, AESGCM(ss).decrypt, metrics decaps_ms
- Logging to `pqc.log` file

### 3.4 cloud_service.py
- Config: CLOUD_HOST 127.0.0.1, CLOUD_PORT 6000 data, HEALTH 6001, DB_PATH telemetry.db
- `init_db()`: sqlite3 connect check_same_thread=False, CREATE TABLE IF NOT EXISTS telemetry(id, device_id, timestamp, temperature, humidity, status, received_at, source_ip, pqc_decaps_ms, raw_json)
- `insert_telemetry(...)`: INSERT with ?, update db_rows metric
- `get_analytics()`: COUNT, AVG(temp/humidity), MAX(timestamp), last 10 ORDER BY received_at DESC, pqc success_rate, avg_decaps_ms, uptime
- `HealthHandler`: GET /health or /analytics returns JSON with db_rows, analytics, pqc, uptime
- `start_health_server()`: HTTPServer 6001 in daemon thread
- `start_cloud()`: generate keypair via pqc_utils, save pk, init_db, start health thread, TCP server 6000 recv until EOF, decrypt via pqc_utils, JSON parse, insert, counters decaps_ok/fail, json_fail, total_received, logging to cloud.log file

### 3.5 DB Schema (SQLite, simple)
```sql
telemetry(
  id INTEGER PK AUTOINCREMENT,
  device_id TEXT,
  timestamp INTEGER,
  temperature REAL,
  humidity REAL,
  status TEXT,
  received_at INTEGER,
  source_ip TEXT,
  pqc_decaps_ms REAL,
  raw_json TEXT
)
```
- No ORM, raw sqlite3, file `telemetry.db` gitignored, created at runtime
- Analytics queries: COUNT, AVG, last 10

---

## 4. How to Run

### Local (3 terminals, per 01_baseline + updated)
```bash
# Setup
uv sync --frozen
# or pip install cryptography mlkem

# Terminal1 Cloud
uv run python src/cloud_service.py
# Generates cloud_public_key.bin (800B) and telemetry.db

# Terminal2 Gateway
uv run python src/edge_gateway.py
# Listens 5000 + health 5001

# Terminal3 Legacy
uv run python src/legacy_device.py

# Verify
curl http://127.0.0.1:5001/health
curl http://127.0.0.1:6001/health
sqlite3 telemetry.db "SELECT * FROM telemetry;"
```

### Docker (simulated deployment)
```bash
docker build -t edge-gateway:test .
docker-compose up
# cloud 6000:6000, 6001:6001, gateway 5000:5000, 5001:5001, depends_on healthy
# Volumes share cloud_public_key.bin

# Legacy via local (connects to gateway:5000)
python src/legacy_device.py
```

---

## 5. Baseline Analysis Summary (link to 01_)

- Initial architecture 2-tier only, Link1 AES-128-GCM, 28B overhead, 0B HTTP overhead (raw TCP+EOF)
- Measurements: plaintext ~95B, wire packet 12+95+16=123B
- Baseline tests: 27 passed, 6 failed documenting R1-R3 (gateway crash, no schema, no replay)
- Planned improvements: try/except boundary, schema validation, nonce cache — implemented in Step1, now 33/33 pass

---

## 6. Design Decisions & LLM Interactions (summary, full in 02_)

| Area | Accepted | Rejected | Rationale |
|------|----------|----------|-----------|
| PQC placement | Offload to gateway | Run ML-KEM on sensor | 3KB >2KB SRAM overflow |
| Local link | AES-128-GCM PSK 16B | ChaCha20, CBC, WebSockets, HTTP | AEAD + low overhead, bare TCP closest to UART |
| Framing | EOF closure | Delimiter, length-prefix | Ciphertext arbitrary bytes, delimiter would need base64 bloat |
| Key distribution | PSK in ROM | ECDH/DH | Factory-flashed PSK avoids asymmetric handshake |
| Nonce | 12B random per packet | Counter, static | GCM breaks if nonce reused |
| PQC lib | mlkem==0.0.3 Rust binding | kyber-py, liboqs, cryptography | Minimal, pip-installable, works with uv + Docker |
| PQC param | ML-KEM-512 (800B pk, 768B ct) | 768 (1184B pk) / 1024 (1568B) | Lowest overhead for gateway, 128-bit security sufficient for short-lived telemetry |
| Hybrid | KEM+AES-256-GCM | Pure PQC encrypt | ML-KEM is KEM, not encryption |
| DB | SQLite stdlib | JSONL, ORM, Postgres | Stdlib, 1 file, enables analytics queries |
| Health | stdlib http.server | Flask/FastAPI | No extra dep, simple |
| CI | astral-sh/setup-uv, uv sync --frozen | pip install -r requirements.txt | Project uses pyproject.toml + uv.lock + .python-version |
| Docker | python:3.13-slim + uv sync --frozen | pip install directly | Respects locked versions, reproducible |

**LLM interactions 10 total:** 1 baseline scaffolding, 2 protocol selection, 3 framing, 4 test plan, 5 test gen, 6 gateway hardening, 7 ML-KEM integration, 8 cloud+DB+analytics, 9 forwarding+fallback+health, 10 Docker+CI. Each logged with prompt, output summary, accepted/modified/rejected, verification via pytest/REPL/curl.

---

## 7. ML-KEM Integration (summary, full in 03_)

- Library: mlkem 0.0.3, API `ML_KEM(ML_KEM_512).key_gen() -> ek 800B, dk 1632B`, `encaps(ek) -> ss 32B, ct 768B`, `decaps(dk, ct) -> ss`
- Hybrid: ss as AES-256-GCM key, wire format ct||nonce||aes_ct ~845B
- File-based pk distribution Phase1, cloud writes pk on start, gateway reads
- PQC observability: encaps_ms ~0.03ms, decaps_ms ~0.04ms, ct_len, success_rate
- Security: quantum-resistant (Module-LWE), integrity via GCM tag, no forward secrecy if dk leaked (documented)

---

## 8. Migration & Fallback Strategy (summary, full in 04_)

- **Phase0:** Legacy only, PSK, no PQC
- **Phase1 (current):** Hybrid offload — legacy unchanged, gateway translates AES-GCM → ML-KEM-512 + AES-256-GCM → cloud, file-based pk, fallback to `gateway_fallback.log` if pk missing or cloud down
- **Phase2 (future):** PQC-capable devices (ESP32) with >8KB SRAM, could run ML-KEM directly, gateway supports both
- **Fallback table:** pk missing → fallback log + fallback_local++, cloud unreachable → same + cloud_fail++, decaps fail → decaps_fail++, malformed legacy → rejected/replayed
- **Legacy compatibility:** Link1 unchanged, no firmware update needed, global PSK (tech debt: per-device keys future)

---

## 9. Operations (summary, full in 05_)

- **Local run:** 3 terminals, uv sync --frozen, cloud 6000+6001, gateway 5000+5001, legacy ephemeral
- **Docker:** Dockerfile FROM python:3.13-slim, pip install uv, COPY pyproject.toml uv.lock .python-version README.md, uv sync --frozen --no-install-project, ENV PATH .venv/bin, HEALTHCHECK via socket, CMD gateway (overridden for cloud). docker-compose with cloud+gateway, depends_on healthy, volumes for pk sharing
- **CI:** .github/workflows/ci.yml on push to main/arena/* + PRs, jobs test (setup-uv, uv sync --frozen, uv pip install pytest, uv run pytest -v 33 tests, pqc round-trip, import check, verify .python-version/pyproject.toml/uv.lock) + docker-build (verify builds)
- **Logging:** File handlers gateway.log, cloud.log, pqc.log (not stderr to keep tests clean, tests merge stdout+stderr)
- **Metrics:** Gateway received/rejected/replayed/invalid_json/invalid_schema/empty/forwarded_to_cloud/fallback_local/cloud_fail, replay_cache_size, uptime; Cloud total_received/decaps_ok/decaps_fail/json_fail/db_rows/avg_decaps_ms/success_rate/uptime
- **Health:** Gateway 5001 /health → metrics JSON, Cloud 6001 /health → db_rows, analytics avg_temp/humidity/last_10, pqc metrics
- **PQC observability:** encaps_ms, decaps_ms, ct_len, total_len, success_rate, fallback rate
- **DB analytics:** SQLite telemetry.db, queries COUNT, AVG, last 10

---

## 10. Testing & Evaluation

- **Pytest:** 33 tests (5 unit legacy/gateway, 11 security/invalid, 2 TCP flow, 10 robustness, 2 negative)
  - Baseline: 27 passed, 6 failed (gateway crash, no schema, no replay)
  - After hardening: 33 passed, 0 failed
  - Large packet test updated to include required fields to pass schema validation
- **Manual tamper test:** `packet[15] ^= 0xFF` → InvalidTag detected (from 01_)
- **Packet overhead measurement:** plaintext 95B, wire 123B, overhead 28B (12 nonce+16 tag)
- **PQC round-trip:** `python src/pqc_utils.py` → packet 845B, encaps 0.03ms, decaps 0.04ms, round-trip OK
- **E2E:** 2 legacy sends → DB 2 rows, cloud health db_rows 2, avg_temp 21.8, decaps_ok 2, success_rate 1.0; gateway health received 2, forwarded 2
- **Fallback:** Stop cloud, send legacy → fallback.log has entry, health fallback_local=1

---

## 11. Final Evaluation (summary, full in 06_ — v2 no redundancy)

- **Overview:** 2-tier baseline 27/33 → 3-tier PQC 33/33. E2E evidence: 2 legacy sends → gateway `received 2 forwarded 2`, cloud `db_rows 2 avg_temp 21.8 decaps_ok 2 success_rate 1.0`. Fallback evidence: cloud down → `gateway_fallback.log` entry + `fallback_local=1`.
- **Strengths (with evidence):** E2E 3-tier works (Link1 AES-128-GCM EOF → gateway validate+replay → Link2 `ct768||nonce12||aes_ct` ~845B → cloud decaps+SQLite); Robust gateway (try/except InvalidTag/ValueError/Unicode/JSON → 33/33); Minimal PQC `mlkem==0.0.3` ML-KEM-512 800B pk+768B ct encaps 0.03ms decaps 0.04ms; SQLite observability COUNT/AVG/last10 + health 5001/6001; Fallback for availability (CISA hybrid guidance); Ops simple but complete (uv.lock respected, docker-compose volume pqc-shared, healthchecks, file logging clean stdout for tests).
- **Weaknesses & Tech Debt combined (why it matters):** Global PSK `legacy_secret_16` → physical extraction all compromised; Replay cache no TTL/no persistence → OOM + replay after restart; File-based pk no auth → MITM; No rotation → no forward secrecy; No TLS → no server auth; Single-threaded → starvation; Logs no rotation DB no backup → disk full/data loss. Intentionally kept for 4h simplicity.
- **Risks consolidated R1-R7:** R1 DoS via malformed High Mitigated (try/except+schema+replay 33/33) remaining large payload CPU; R2 Replay Medium Mitigated (seen_nonces) remaining no TTL; R3 PSK extraction Medium Not mitigated; R4 PQC overhead Medium Mitigated/measured negligible; R5 Scalability Low Not mitigated; R6 pk MITM Medium Not mitigated; R7 DB no backup Low Not mitigated.
- **What If Not Fully Integrated (per course Q&A):** Cloud down/pk missing → fallback log ensures no loss; Decaps fail → decaps_fail++ stays alive success_rate shows degradation; Gaps documented (no rotation, no cert, 512 only, file-based). OK for peer review as 3-tier works + fallback documented.
- **Conclusion concise:** Meets peer review with simple design: legacy preserved (no firmware update for 2KB SRAM device), PQC on internet-facing Link2 via offload, SQLite analytics + fallback, CI/CD+Docker respects lockfiles. Remaining work is tech debt prioritized future.

---

## 12. References (public, for Part1)

- [1] NIST FIPS 203 ML-KEM standard https://www.encryptionconsulting.com/education-center/ml-kem-fips-203/
- [2] ML-KEM sizes https://vucense.com/privacy-sovereignty/post-quantum-cryptography/ml-kem-fips-203-implementation-guide-2026/
- [3] CISA PQC Initiative https://www.cisa.gov/topics/risk-management/quantum
- [4] EU PQC roadmap hybrid https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/
- [5] Legacy constraints https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems

---

## 13. Appendix: LLM Prompts Full Log

See `02_design_decisions_n_key_llm_interactions.md` sections 1.1-1.10 for full prompts, LLM output summaries, human review, accepted/modified/rejected, verification steps.

**Key prompts:**
- Interaction1: "Write two Python scripts using cryptography library... legacy_device.py encrypts... edge_gateway.py listens..."
- Interaction2: "Should we use WebSockets or HTTP REST..."
- Interaction3: "How should edge gateway know when sensor finished sending..."
- Interaction4: "I am new to this codebase. Please analyze src/legacy_device.py and src/edge_gateway.py... propose test approach..."
- Interaction5: "Please proceed to generate code for topics 1 to 4 only..."
- Interaction6: "My edge_gateway.py crashes when it receives malformed AES-GCM packets... How should I harden it to pass these tests...?"
- Interaction7: "I need to integrate ML-KEM-512 into my edge-cloud system. I have mlkem==0.0.3 library. Show how to generate keypair, encapsulate..."
- Interaction8: "Create a cloud_service.py that listens on TCP 6000 for PQC packets... stores in SQLite... health/analytics endpoint on 6001..."
- Interaction9: "Extend edge_gateway.py to forward telemetry to cloud via PQC: try load cloud_public_key.bin, if missing or cloud unreachable, append JSON to gateway_fallback.log..."
- Interaction10: "Generate GitHub Actions CI and Dockerfile and docker-compose for Python project using uv package manager, with pyproject.toml, uv.lock, .python-version 3.13..."

---

## 14. How to Run Tests

```bash
uv sync --frozen
uv pip install pytest
uv run pytest -v
# or /tmp/venv/bin/python -m pytest -v
# Expected: 33 passed
```

---

## 15. Files

- `src/legacy_device.py`, `src/edge_gateway.py`, `src/pqc_utils.py`, `src/cloud_service.py`
- `tests/unit/`, `tests/integration/`, `tests/conftest.py`
- `documentation/01_baseline_analysis.md`, `02_design_decisions_n_key_llm_interactions.md`, `03_mlkem_integration.md`, `04_migration_fallback_strategy.md`, `05_operations.md`, `06_final_evaluation.md`, `part1_documentation.md`, `00_4h_gaps_analysis_n_scope_plan.md`
- `.github/workflows/ci.yml`, `Dockerfile`, `docker-compose.yml`
- `pyproject.toml`, `uv.lock`, `.python-version`, `README.md`

