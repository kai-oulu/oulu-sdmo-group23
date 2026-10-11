# Part 1 Technical Documentation — Oulu SDMO Group 23

**Members (by contribution):** Kaiquan Mah | Quoc Nguyen | Danish Sharjeel | Manh Nguyen | Kim Nguyen  
**Branches:** `arena/04f59b2c-oulu-sdmo-group23` (dev, this doc) + `main` (CI green, 33/33)  
**Date:** 2026-10-11, **Python:** 3.13, **Package manager:** `uv`, **Deps:** `cryptography>=50.0.1`, `mlkem>=0.0.3`  
**Entry point for peer review:** this file consolidates 01-06 + README + code evidence

> **Inspiration from grp28 example (non-authoritative, not committed):** grp28 had clear structure — cover + TOC + requirements traceability + architecture diagrams (2-tier → 3-tier) + design decisions with LLM logs + implementation snippets + testing evidence (unit/integration/E2E) + operations (CI/CD, Docker, monitoring) + final evaluation (strengths/weaknesses/tech debt/risks) + references + appendix. We follow similar flow but keep it minimal for 4h scope, per course Q&A: keep it plain and simple, don't make project bigger than needed. We do NOT commit grp28 PDFs per instruction.

---

## Table of Contents

0. Acronyms  
1. Executive Summary & E2E Evidence  
2. Requirements Mapping (rqmts1/rqmts2)  
3. Baseline Analysis (01_)  
4. Architecture (2-tier → 3-tier)  
5. Design Decisions & LLM Interactions (02_, 10 total)  
6. ML-KEM Integration (03_, dual-wheel fix)  
7. Migration & Fallback Strategy (04_)  
8. Operations (05_, CI/CD, Docker, logging, metrics, DB analytics, PQC observability)  
9. Testing & Evaluation (33/33, E2E, fallback, PQC round-trip, tamper)  
10. Final Evaluation (06_ v3, strengths, weaknesses & tech debt, risks R1-R7, what-if)  
11. References (public)  
12. Appendix: Files, How to Run Tests, LLM Prompts

---

## 0. Acronyms (for non-CS readers, explicit)

- **PQC = Post-Quantum Cryptography**: crypto resistant to quantum computers
- **ML-KEM = Module-Lattice-based Key Encapsulation Mechanism** (NIST FIPS 203, CRYSTALS-Kyber): PQC KEM
- **KEM = Key Encapsulation Mechanism**: one side encrypts random secret with public key, other decrypts
- **PSK = Pre-Shared Key**: same 16B key flashed into all devices at factory
- **AES-GCM = Advanced Encryption Standard - Galois/Counter Mode**: symmetric AEAD (confidentiality + 16B tag for integrity)
- **pk = public key** (ML-KEM encaps key 800B), **sk/dk = secret/decaps key** 1632B private, **ct = ciphertext** 768B, **ss = shared secret** 32B (becomes AES-256 key), **B=Bytes**
- **TTL = Time To Live**, **OOM = Out Of Memory**, **LRU = Least Recently Used**
- **MITM = Man-In-The-Middle**, **DoS = Denial of Service**, **TLS = Transport Layer Security**
- **HSM = Hardware Security Module**, **KMS = Key Management System**, **DB = Database**, **ORM = Object-Relational Mapper** (we avoided)
- **E2E = End-to-End**, **EOF = End-Of-File** (close TCP to signal end), **MTU = Maximum Transmission Unit**
- **CI/CD = Continuous Integration/Continuous Deployment**, **SRAM = Static RAM**

---

## 1. Executive Summary & E2E Evidence

**Goal:** Modernize small legacy edge-cloud system (simulated ATmega328P sensor → edge gateway → cloud) for PQC, using LLM as untrusted assistant, with critical evaluation, per 4h peer-review scope.

**What we built (minimal but functional):**
- 2-tier baseline (legacy → gateway, 27/33 tests) → 3-tier (legacy → gateway → cloud) with ML-KEM-512 hybrid on Link2, 33/33 tests
- Gateway hardened: `try/except InvalidTag, ValueError, UnicodeDecodeError, JSONDecodeError`, schema validation `REQUIRED_FIELDS`, replay cache `seen_nonces=set()`
- Cloud: SQLite `telemetry.db` (stdlib, 1 table, no ORM) + analytics `COUNT, AVG(temp/humidity), last 10, decaps_ok/fail, avg_decaps_ms, success_rate` via health 6001 JSON
- Gateway health 5001 metrics: received/rejected/replayed/invalid_json/invalid_schema/empty/forwarded_to_cloud/fallback_local/cloud_fail
- Fallback: if `cloud_public_key.bin` missing or cloud unreachable (TCP 6000 refused/timeout), gateway appends `<timestamp> <json>` to `gateway_fallback.log` + `fallback_local++` (business continuity, per CISA hybrid guidance)
- Operations: CI via `astral-sh/setup-uv` reading `.python-version` + `uv.lock`, `uv sync --frozen --all-groups` + `pytest -v`; Dockerfile `python:3.13-slim` + `uv sync --frozen --no-install-project`; docker-compose with named volume `pqc-shared` for pk sharing, healthchecks, `depends_on healthy`; logging to files (`gateway.log`, `cloud.log`, `pqc.log`) to keep stdout clean for tests; health via stdlib `http.server` (no Flask)

**E2E evidence (tested 2026-10-11):**
```bash
# Terminal1 Cloud
uv run python src/cloud_service.py  # generates cloud_public_key.bin 800B + telemetry.db
# Terminal2 Gateway
uv run python src/edge_gateway.py  # listens 5000 + 5001
# Terminal3 Legacy x2
uv run python src/legacy_device.py
uv run python src/legacy_device.py
# Verify
curl http://127.0.0.1:5001/health  # {"received":2,"forwarded_to_cloud":2}
curl http://127.0.0.1:6001/health  # {"db_rows":2,"analytics":{"avg_temperature":21.8},"pqc":{"decaps_ok":2,"success_rate":1.0}}
sqlite3 telemetry.db "SELECT COUNT(*) FROM telemetry;"  # 2
```
Fallback evidence: stop cloud, send legacy → `gateway_fallback.log` has entry, health `fallback_local=1`.

**CI evidence:** `origin/main` run `38103152286` success 32s, `arena` run `38102098201` success 38s, both 33/33.

---

## 2. Requirements Mapping (from rqmts1/rqmts2 checklist)

| Requirement | Status | Evidence (file:line) |
|-------------|--------|----------------------|
| AI-assisted development: generate components with LLM, record prompts/outputs/decisions | ✅ Done | `02_` logs 10 interactions: 1 scaffolding, 2 protocol, 3 framing, 4 test plan, 5 test gen, 6 gateway hardening, 7 ML-KEM, 8 cloud+DB+analytics, 9 forwarding+fallback, 10 Docker+CI |
| Baseline analysis: understand initial architecture, run system, baseline tests/measurements | ✅ Done | `01_` with 2-tier diagram, measurements plaintext 95B, wire 123B, overhead 28B (12 nonce+16 tag), 27/33 tests initially, gap analysis |
| Critical evaluation & maintenance: test, review, correct, improve LLM artefacts | ✅ Done | Fixed gateway crash → 33/33, corrected `mlkem` API (`key_gen` not `generate`), fixed logging to file (was polluting stdout), fixed large packet test payload, fixed dual-wheel `mlkem` import (Rust vs pure Python), fixed missing `import os` in cloud_service |
| ML-KEM integration: use existing implementation, at least one path | ✅ Done | `src/pqc_utils.py` 258 lines, `cloud_service.py` 400 lines, `edge_gateway.py` 388 lines, ML-KEM-512 hybrid `ct(768)||nonce(12)||aes_ct` ~845B, file-based pk distribution `cloud_public_key.bin` 800B, supports both Rust binding (rust.so 909KB) and pure Python (fastmath.so 80KB, empty __init__.py) wheels |
| Preserve legacy compatibility / migration & fallback strategy | ✅ Done | `04_` phased: Phase0 PSK only, Phase1 hybrid offload (current, legacy unchanged, no firmware update for 2KB SRAM device), Phase2 future PQC-capable ESP32, fallback to `gateway_fallback.log` if pk missing or cloud down |
| Operations: automate build/testing, deployment to test env, health checks, logs, metrics | ✅ Done | `05_` + `.github/workflows/ci.yml` (setup-uv, uv sync --frozen --all-groups, pytest -v, pqc round-trip, import checks, PYTHONPATH), `Dockerfile` (python:3.13-slim, uv sync --frozen --no-install-project, HEALTHCHECK), `docker-compose.yml` (cloud+gateway, healthchecks, depends_on healthy, volume pqc-shared), logging file-only, metrics counters, PQC observability encaps_ms/decaps_ms, DB analytics |
| Final evaluation: strengths/weaknesses, tech debt, risks | ✅ Done | `06_` v3 with acronym glossary, strengths with evidence, weaknesses & tech debt combined table with why it matters, risks R1-R7 consolidated with status Mitigated/Not mitigated + remaining, what-if-not-fully-integrated per course Q&A, conclusion concise |
| Simple DB at cloud side (SQLite) to store telemetry | ✅ Done | `telemetry.db` 1 table `telemetry(id, device_id, timestamp, temperature, humidity, status, received_at, source_ip, pqc_decaps_ms, raw_json)`, stdlib sqlite3, no ORM, gitignored |
| Observability includes simple analytics on cloud side (avg temp, counts, PQC success rate) | ✅ Done | Cloud health 6001 returns `db_rows`, `analytics.avg_temperature`, `avg_humidity`, `last_10`, `pqc.decaps_ok`, `decaps_fail`, `success_rate`, `avg_decaps_ms` |
| Consolidate all Part1 docs into 1 full part1_documentation.md | ✅ Done | This file, inspired by grp28 example structure but our content, maps requirements |
| Part2 perspective: InfoSec/org cybersecurity, C-suite/manager audience, public citations | ⏳ Next | Will be `part2_report.md`, non-CS friendly, business risk focus, with NIST/CISA/ENISA citations |

**Usage of AI (per rqmts2):**
- Must use AI to create code (Part1): Yes, all src generated via LLM prompts logged in 02_
- Must manually evaluate AI-generated code continuously: Yes, via pytest, REPL, E2E, log pollution fix, dual-wheel fix, os import fix
- Must include prompts in technical documentation: Yes, in 02_ sections 1.1-1.10 + appendix here
- Must report how/where AI used: Yes, accepted/modified/rejected matrix in 02_ and summary below
- Must not use AI for personal reflections (Part3): Noted, will be manual

**Constraints:**
- Keep design simple (4h limit): Done — single-threaded data plane (2 threads total: 1 data + 1 health), SQLite stdlib, http.server stdlib, no Flask, no Prometheus, no per-device keys, no TLS, file-based pk

---

## 3. Baseline Analysis Summary (link to 01_)

- **Initial architecture 2-tier only:** `[Legacy ATmega328P sim] --AES-128-GCM PSK 16B, TCP 5000, EOF--> [Edge Gateway]`
- **Measurements:** plaintext JSON ~95B, wire packet 12B nonce + 95B JSON + 16B tag = 123B, overhead 28B, 0B HTTP overhead (raw TCP+EOF)
- **Baseline tests:** 27 passed, 6 failed documenting risks R1-R3 (gateway crash on `InvalidTag` exit 1, no schema validation, no replay protection)
- **Device constraints:** ATmega328P 2KB SRAM / 32KB Flash, ML-KEM-512 sk 1632B + workspace 1000-1500B = ~3KB >2KB → stack overflow, so PQC must be offloaded to gateway (Linux/Pi)
- **Planned improvements:** try/except boundary, REQUIRED_FIELDS schema, seen_nonces replay cache — implemented in Step1, now 33/33 pass

---

## 4. Architecture

### 4.1 Baseline (2-tier, initial)

```
[Legacy Device: ATmega328P sim] --AES-128-GCM PSK, TCP 5000, EOF--> [Edge Gateway]
  2KB SRAM/32KB Flash, 16B PSK, 12B nonce, 28B overhead (12 nonce+16 tag)
```

### 4.2 Final (3-tier, with PQC, DB, analytics)

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
- Link2: `ct(768) || nonce(12) || aes_ct+tag` ~845B for small JSON (768+12+65), ss 32B as AES-256-GCM key

**Why offload PQC to gateway:** 3KB >2KB SRAM overflow, gateway has enough RAM, encaps 0.03ms Rust / 0.82ms pure Python, decaps 0.04ms / 1.46ms negligible.

**Threading model (clarification for concurrent starvation question):**
- **2 threads total:** (1) main TCP data thread `accept()` + blocking `recv()` = single-threaded data plane, processes one sensor at a time, others wait in TCP backlog queue (starvation = they starve, not served), (2) health HTTP thread 5001 daemon.
- No contradiction with "single-threaded gateway" — we mean data plane single-threaded, for simplicity per 4h limit. Future: `asyncio` or thread pool.

---

## 5. Design Decisions & LLM Interactions (summary, full in 02_)

| Area | Accepted | Rejected | Rationale |
|------|----------|----------|-----------|
| PQC placement | Offload to gateway | Run ML-KEM on sensor | 3KB >2KB SRAM overflow |
| Local link | AES-128-GCM PSK 16B | ChaCha20, CBC, WebSockets, HTTP | AEAD + low overhead, bare TCP closest to UART |
| Framing | EOF closure | Delimiter, length-prefix | Ciphertext arbitrary bytes, delimiter would need base64 bloat |
| Key distribution | PSK in ROM | ECDH/DH | Factory-flashed PSK avoids asymmetric handshake |
| Nonce | 12B random per packet | Counter, static | GCM breaks if nonce reused |
| PQC lib | mlkem==0.0.3 (supports both Rust and pure Python wheels) | kyber-py, liboqs, cryptography | Minimal, pip-installable, works with uv + Docker, dual-wheel fix added |
| PQC param | ML-KEM-512 (800B pk, 768B ct) | 768 (1184B pk) / 1024 (1568B) | Lowest overhead for gateway, 128-bit security sufficient for short-lived telemetry |
| Hybrid | KEM+AES-256-GCM | Pure PQC encrypt | ML-KEM is KEM, not encryption |
| DB | SQLite stdlib | JSONL, ORM, Postgres | Stdlib, 1 file, enables analytics queries COUNT/AVG/last10 |
| Health | stdlib http.server | Flask/FastAPI | No extra dep, simple |
| CI | astral-sh/setup-uv, uv sync --frozen --all-groups | pip install -r requirements.txt | Project uses pyproject.toml + uv.lock + .python-version, PYTHONPATH fix |
| Docker | python:3.13-slim + uv sync --frozen | pip install directly | Respects locked versions, reproducible |

**LLM interactions 10 total + 2 fixes:**

1. **Baseline scaffolding:** Prompt "Write two Python scripts using cryptography... legacy_device.py encrypts... edge_gateway.py listens..." → LLM gave AES-GCM + TCP, accepted after fixing `cryptography` import via `uv`.
2. **Protocol selection:** "Should we use WebSockets or HTTP REST..." → LLM suggested WebSockets/HTTP, rejected (200-500B headers bloat >2KB SRAM), accepted bare TCP.
3. **Framing:** "How should gateway know when sensor finished sending..." → LLM suggested length-prefix, delimiter, EOF, accepted EOF (close socket) for minimal RAM.
4. **Test plan (Topic 1-4):** "I am new to this codebase. Please analyze src/legacy_device.py and src/edge_gateway.py... propose test approach..." → LLM gave 5 topics, we accepted 1-4 (unit, integration, security, robustness), rejected Topic5 load testing (too complex for 4h).
5. **Test generation (Topic 1-4):** "Please proceed to generate code for topics 1 to 4 only..." → LLM generated 33 tests, we fixed large packet test payload to include REQUIRED_FIELDS.
6. **Gateway hardening:** "My edge_gateway.py crashes when it receives malformed AES-GCM packets... How should I harden it to pass these tests...?" → LLM suggested try/except + schema + replay, accepted, plus we fixed log pollution (file-only logging, not stderr, because tests merge stdout+stderr via `stderr=STDOUT` and `wait_for_line` would get concatenated lines).
7. **ML-KEM integration:** "I need to integrate ML-KEM-512 into my edge-cloud system. I have mlkem==0.0.3 library. Show how to generate keypair, encapsulate..." → LLM gave `ML_KEM(ParameterSet.ML_KEM_512).key_gen() -> ek, dk` and `encaps(ek) -> ss, ct`, we accepted but corrected API for dual-wheel: Rust has `EncapsKey.from_bytes`, pure Python uses bytes directly, and `ParameterSet.ML_KEM_512` vs `ML_KEM_512` const.
8. **Cloud+DB+analytics:** "Create a cloud_service.py that listens on TCP 6000 for PQC packets... stores in SQLite... health/analytics endpoint on 6001..." → LLM gave SQLite + http.server, accepted, added `check_same_thread=False` for thread safety, added `init_db()` creates table if not exists.
9. **Forwarding+fallback+health:** "Extend edge_gateway.py to forward telemetry to cloud via PQC: try load cloud_public_key.bin, if missing or cloud unreachable, append JSON to gateway_fallback.log..." → LLM gave forwarding + fallback, accepted, added metrics `forwarded_to_cloud`, `fallback_local`, `cloud_fail`, health 5001 JSON.
10. **Docker+CI:** "Generate GitHub Actions CI and Dockerfile and docker-compose for Python project using uv package manager, with pyproject.toml, uv.lock, .python-version 3.13..." → LLM gave `setup-uv` + `uv sync --frozen` + Dockerfile `python:3.13-slim` + `uv sync --frozen --no-install-project`, accepted, fixed to add `PYTHONPATH` and `--all-groups` and `import os` missing.

**Additional fixes (CI failures, not LLM but human):**

- **Fix 11:** `ModuleNotFoundError: No module named 'src'` — `conftest.py` only added `src/` to path, so `from src.pqc_utils import ...` fallback failed. Fixed by inserting both PROJECT_ROOT and src/ into sys.path, and only fallback when error contains `pqc_utils`, not masking dependency errors.
- **Fix 12:** `ImportError: cannot import name 'ML_KEM' from 'mlkem'` — mlkem 0.0.3 has 2 wheels: Rust (rust.so 909KB, `__init__.py` exports ML_KEM) and pure Python (fastmath.so 80KB, empty `__init__.py`). CI Python 3.13 got pure Python. Fixed by trying Rust first, fallback to pure Python `from mlkem.ml_kem import ML_KEM` + `from mlkem.parameter_set import ML_KEM_512`, flag `RUST_BINDING`.
- **Fix 13:** `NameError: name 'os' is not defined` in `cloud_service.py` line 63 `CLOUD_HOST = os.getenv(...)` — missing `import os`. Fixed by adding `import os`.

---

## 6. ML-KEM Integration (summary, full in 03_)

- **Library:** `mlkem==0.0.3`, supports both Rust binding (fast) and pure Python (fastmath) — we handle both via `RUST_BINDING` flag
  - Rust API: `ML_KEM(ParameterSet.ML_KEM_512).key_gen() -> (EncapsKey 800B, DecapsKey 1632B)`, `encaps(ek: EncapsKey) -> (ss 32B, ct 768B)`, `decaps(dk: DecapsKey, ct) -> ss`, `EncapsKey.from_bytes()`
  - Pure Python API: `ML_KEM(ML_KEM_512).key_gen() -> (ek_bytes 800B, dk_bytes 1632B)`, `encaps(ek_bytes) -> (ss, ct)`, `decaps(dk_bytes, ct) -> ss`
- **Param set choice:** ML-KEM-512 (800B pk + 768B ct = 1568B) vs 768 (1184+1088=2272B) vs 1024 (1568+1568=3136B) — lowest overhead for gateway, 128-bit security sufficient for short-lived telemetry (not decades). If long-term confidentiality needed (medical), should use 768.
- **Hybrid:** ss 32B as AES-256-GCM key, wire format `ct||nonce||aes_ct` ~845B, integrity via GCM tag
- **File-based pk distribution Phase1:** Cloud on start `generate_keypair()` writes `cloud_public_key.bin` 800B to `CLOUD_PK_PATH` (env var, default `./cloud_public_key.bin`, Docker `/app/shared/cloud_public_key.bin` via volume `pqc-shared`), gateway `load_public_key()` tries primary + fallbacks `shared/`, `/app/shared/`
- **PQC observability:** `encaps_ms` ~0.03ms Rust / 0.82ms pure Python, `decaps_ms` ~0.04ms / 1.46ms, `ct_len`, `total_len`, `success_rate`, `fallback rate`, logged to `pqc.log`
- **Security:** quantum-resistant (Module-LWE), integrity via GCM tag, no forward secrecy if dk leaked (documented as tech debt)
- **Constrained radio note:** 800B pk + 768B ct overhead matters for constrained radio = low-power wireless like LoRaWAN (51B MTU), Zigbee (127B MTU), BLE (27-251B MTU), NB-IoT low bandwidth, battery-powered, can't afford 1.5KB extra (needs fragmentation, more battery). In our TCP/Ethernet sim it's fine, documented as Risk R4.

---

## 7. Migration & Fallback Strategy (summary, full in 04_)

- **Phase0 (legacy only):** PSK 16B, no PQC, gateway just decrypts and prints
- **Phase1 (current, hybrid offload):** Legacy unchanged (no firmware update needed for 2KB SRAM device), gateway translates AES-GCM (Link1) → ML-KEM-512 + AES-256-GCM (Link2) → cloud, file-based pk, fallback to `gateway_fallback.log` if pk missing or cloud unreachable (TCP 6000 refused/timeout) → `fallback_local++`, `cloud_fail++`. Cloud decaps fail → `decaps_fail++` but stays alive. Business continuity per CISA hybrid guidance.
- **Phase2 (future):** PQC-capable devices (ESP32 with >8KB SRAM) could run ML-KEM directly, gateway supports both legacy and PQC devices, file-based pk replaced by KMS/certificate, add TLS 1.3 with PQC certs
- **Fallback table:**

| Condition | Action | Metric |
|-----------|--------|--------|
| `cloud_public_key.bin` missing or invalid length | Append `<timestamp> <json>` to `gateway_fallback.log` | `fallback_local++` |
| Cloud TCP 6000 unreachable (refused, timeout) | Same fallback | `cloud_fail++`, `fallback_local++` |
| PQC decaps fail (tampered, wrong key) | Log warning, stay alive | `decaps_fail++` |
| Malformed legacy (InvalidTag, truncated, non-JSON, wrong schema, replay) | Log warning, reject, stay alive | `rejected++`, `replayed++`, etc. |

- **Legacy compatibility:** Link1 unchanged, global PSK `legacy_secret_16` (tech debt: per-device subkeys future), EOF framing preserved

---

## 8. Operations (summary, full in 05_)

- **Local run:** 3 terminals, `uv sync --frozen --all-groups`, cloud 6000+6001, gateway 5000+5001, legacy ephemeral client
- **Docker:** Dockerfile `FROM python:3.13-slim`, `pip install uv`, `COPY pyproject.toml uv.lock .python-version README.md ./`, `RUN uv sync --frozen --no-install-project`, `ENV PATH="/app/.venv/bin:$PATH"`, `HEALTHCHECK` via socket, `CMD ["python", "src/edge_gateway.py"]` (overridden for cloud). docker-compose with `cloud`+`gateway`, `depends_on healthy`, volumes `pqc-shared:/app/shared` for pk sharing, ports 5000,5001,6000,6001, env vars `CLOUD_HOST=cloud`, `CLOUD_PK_PATH=/app/shared/cloud_public_key.bin`
- **Dockerfile implicit convention explained:** `docker-compose.yml` `build: .` implicitly reads `./Dockerfile` (explicit form `build: {context: ., dockerfile: Dockerfile}`), `ci.yml` `docker build -t ... .` implicitly `docker build -f Dockerfile -t ... .` — both use same Dockerfile without mentioning name. Runtime table: `pyproject.toml+uv.lock+.python-version` used local+CI+Docker, Dockerfile used local Docker+CI docker-build, docker-compose local only, ci.yml GitHub only
- **CI:** `.github/workflows/ci.yml` on push to `main`/`arena/*` + PRs, jobs `test` (setup-uv, uv sync --frozen --all-groups, uv pip install pytest, PYTHONPATH set, pytest -v 33 tests, pqc round-trip `python src/pqc_utils.py`, import checks `import src.pqc_utils` + top-level `import edge_gateway`, verify `.python-version`/pyproject/uv.lock) + `docker-build` (needs: test, `docker build -t ... .` verifies builds). CI now green after fixes.
- **Logging:** File handlers `gateway.log`, `cloud.log`, `pqc.log` (gitignored via `*.log`) to keep stdout clean for tests — tests merge stdout+stderr via `stderr=STDOUT` and `wait_for_line` looks for `Received from device:`, so logging to stderr would cause concatenated lines like `Received...2026-10-10 INFO...` → test failure. Fixed by logging to file only.
- **Metrics:** Gateway `received`, `rejected`, `replayed`, `invalid_json`, `invalid_schema`, `empty`, `forwarded_to_cloud`, `fallback_local`, `cloud_fail`, `replay_cache_size`, `uptime_s`; Cloud `total_received`, `decaps_ok`, `decaps_fail`, `json_fail`, `db_rows`, `avg_decaps_ms`, `success_rate`, `uptime_s`
- **Health:** Gateway 5001 `/health` → metrics JSON, Cloud 6001 `/health` → `db_rows`, `analytics.avg_temperature`, `avg_humidity`, `last_10`, `pqc` metrics
- **PQC observability:** `encaps_ms`, `decaps_ms`, `ct_len`, `total_len`, `success_rate`, `fallback rate`, logged
- **DB analytics:** SQLite `telemetry.db`, queries `COUNT`, `AVG`, `last 10`, created at runtime, gitignored `*.db`, `*.bin`

---

## 9. Testing & Evaluation

- **Pytest 33 tests:** 5 unit legacy/gateway, 11 security/invalid, 2 TCP flow, 10 robustness, 2 negative
  - Baseline: 27 passed, 6 failed (gateway crash, no schema, no replay)
  - After hardening: 33 passed, 0 failed (both Rust and pure Python venvs)
  - Large packet test updated to include REQUIRED_FIELDS to pass schema validation
- **Manual tamper test:** `packet[15] ^= 0xFF` → `InvalidTag` detected (from 01_)
- **Packet overhead:** plaintext 95B, wire 123B, overhead 28B (12 nonce+16 tag)
- **PQC round-trip:** `python src/pqc_utils.py` → packet 845B, encaps 0.03ms Rust / 0.82ms pure Python, decaps 0.04ms / 1.46ms, round-trip OK, `rust_binding` flag in metrics
- **E2E:** 2 legacy sends → DB 2 rows, cloud health `db_rows 2, avg_temp 21.8, decaps_ok 2, success_rate 1.0`, gateway health `received 2, forwarded 2`
- **Fallback:** Stop cloud, send legacy → `gateway_fallback.log` has entry, health `fallback_local=1`, `cloud_fail=1`
- **CI:** `origin/main` run `38103152286` success 32s after fixes, `arena` run `38102098201` success 38s

---

## 10. Final Evaluation (summary, full in 06_ v3 no redundancy)

### 10.0 Acronyms (already in Section 0)

### 10.1 Overview

2-tier baseline 27/33 → 3-tier PQC 33/33. E2E evidence: 2 sends → gateway `received 2 forwarded 2`, cloud `db_rows 2 avg_temp 21.8 decaps_ok 2 success_rate 1.0`. Fallback evidence: cloud down → `gateway_fallback.log` entry + `fallback_local=1`. CI/CD and Docker respect `pyproject.toml` + `uv.lock` + `.python-version`.

### 10.2 Strengths (with evidence)

- **E2E 3-tier works:** Legacy AES-128-GCM PSK (TCP 5000, EOF) → gateway decrypt + validate + replay check → PQC hybrid `ct(768)||nonce(12)||aes_ct` ~845B → cloud decaps + SQLite insert. Satisfies core requirement: integrate ML-KEM into at least one path (Link2 internet-facing) while preserving Link1.
- **Robust gateway:** Previously crashed on `InvalidTag` exit 1. Now `try/except InvalidTag, ValueError, UnicodeDecodeError, JSONDecodeError`, logs warning, continues. Schema `REQUIRED_FIELDS` + replay cache `seen_nonces=set()` → 33/33.
- **Minimal but functional PQC:** `mlkem==0.0.3` supports both Rust and pure Python wheels (dual-wheel fix), ML-KEM-512 lowest overhead 800B pk+768B ct, hybrid AES-256-GCM ss 32B, encaps 0.03ms Rust / 0.82ms pure, decaps 0.04ms / 1.46ms negligible for gateway.
- **Simple DB as observability:** SQLite `telemetry.db` stdlib, 1 table, no ORM, `COUNT, AVG, last 10`, exposed via health 6001 JSON + 5001 metrics — managers see PQC vs fallback, avg temp, recent telemetry.
- **Fallback ensures availability:** If `cloud_public_key.bin` missing or cloud unreachable, gateway fallback to log + `fallback_local++`, cloud decaps fail → `decaps_fail++` but stays alive — business continuity per CISA hybrid guidance.
- **Operations complete but simple:** CI `setup-uv` + `uv.lock`, Dockerfile `python:3.13-slim` + `uv sync --frozen`, compose volume `pqc-shared`, healthchecks, `depends_on healthy`, file logging clean stdout for tests, health via stdlib `http.server`.

### 10.3 Weaknesses and Technical Debt (combined, with why it matters)

| Weakness / Debt | Why It Matters (plain English) | Impact | Future Mitigation |
|-----------------|--------------------------------|--------|-------------------|
| **Global 16B PSK (Pre-Shared Key) `legacy_secret_16`** | All devices share same 16B key. If one device physically tampered and Flash ROM extracted, attacker can decrypt all Link1 traffic and forge telemetry. | High if tampered | Per-device subkeys from master, protected Flash, rotation |
| **Replay cache no TTL (Time To Live), no persistence** | `seen_nonces=set()` in RAM stores 12B nonces seen. Grows forever → OOM (Out Of Memory). **On restart, set cleared → replayed packets accepted again**: RAM wiped, set empty, attacker can replay old captured packet, gateway thinks new because nonce not in empty set. | Medium | LRU (Least Recently Used) cache with TTL e.g., 5 min, timestamp window (only accept packets where `now - timestamp <5min`), persist to file/DB |
| **File-based pk (public key) distribution, no auth (authentication)** | `cloud_public_key.bin` 800B no signature. Attacker replacing file can MITM (Man-In-The-Middle) Link2. | Medium | Sign pk file, use certificate, fetch via TLS pinning, KMS (Key Management System) |
| **No key rotation** | ML-KEM dk (decaps key/private 1632B) stays in memory forever, never rotated. If leaked, all past/future Link2 messages compromised (no forward secrecy). | Medium | Rotate daily, store dk in HSM (Hardware Security Module) or encrypted file, versioned keys |
| **No TLS (Transport Layer Security) on Link2** | PQC KEM gives confidentiality but no server authentication beyond file-based pk. | Medium | Add TLS 1.3 with PQC certs or hybrid certs |
| **Single-threaded gateway (data plane) — concurrent starvation** | **2 threads total:** (1) main TCP data thread `accept()`+blocking `recv()` single-threaded data plane, (2) health HTTP thread 5001. **Concurrent starvation** = while processing one sensor, others wait in TCP queue (starve, not served). If 100 sensors send at once, timeout. Not contradiction with single-threaded point — we mean data plane single-threaded for simplicity. | Low | `asyncio` or thread pool (rejected for 4h) |
| **Logs no rotation, DB no backup** | `gateway.log`, `cloud.log`, `pqc.log` grow forever → disk full. `telemetry.db` single file, no backup → data loss. | Low | `RotatingFileHandler`, periodic DB backup/replication |

Intentionally kept for 4h simplicity per course guidance.

### 10.4 Risks (Consolidated R1-R7)

| # | Risk | Severity | Status | Remaining |
|---|------|----------|--------|-----------|
| **R1** | Gateway DoS (Denial of Service) via malformed input (crash on InvalidTag) | High | **Mitigated:** try/except + schema + replay, now 33/33 pass, stays alive | Large payload could still cause high CPU when decrypting, should add rate limiting |
| **R2** | Replay attacks (stale telemetry reinjected) | Medium | **Mitigated:** seen_nonces set rejects replayed nonce | No TTL, restart clears cache → replay possible after restart. Should add timestamp window: only accept where `now - timestamp <5min` |
| **R3** | PSK (Pre-Shared Key) extraction (physical tampering) | Medium | **Not mitigated:** global PSK still | Per-device keys, protected Flash |
| **R4** | PQC performance & memory overhead | Medium | **Mitigated/measured:** encaps 0.03ms Rust / 0.82ms pure, decaps 0.04ms / 1.46ms negligible for gateway (Linux/Pi) | 800B pk + 768B ct overhead matters for constrained radio (low-power wireless LoRaWAN 51B MTU, Zigbee 127B MTU, BLE 27-251B MTU, NB-IoT low bandwidth, battery-powered, can't afford 1.5KB extra) — in our TCP/Ethernet sim fine, documented |
| **R5** | Scalability & concurrent starvation | Low | **Not mitigated:** single-threaded data plane (2 threads total, 1 for data) | asyncio or thread pool future |
| **R6** | File-based pk (public key) MITM (Man-In-The-Middle) | Medium | **Not mitigated:** pk file no auth | Sign pk or use secure distribution |
| **R7** | DB (Database) no backup | Low | **Not mitigated:** single file | Periodic backup |

Overall, high-severity R1 fixed, medium R2 partially fixed, others documented as debt.

### 10.5 What If ML-KEM Not Fully Integrated? (Per Course Q&A: OK to Document)

Current integration minimal viable and works E2E (tested). If PQC path fails:

- **Cloud down or pk (public key) missing:** Gateway fallback to `gateway_fallback.log` ensures no data loss (business continuity). Operator can replay log later.
- **Decaps fail (decapsulation = private key decrypt fails):** Cloud increments `decaps_fail`, logs warning, stays alive, `success_rate` exposed via health 6001 shows degradation.
- **Gaps documented:** No key rotation, no cert (certificate), ML-KEM-512 only (not 768 for long-term confidentiality), file-based distribution. For peer review, sufficient — 3-tier works, PQC path exists, fallback documented, per course guidance that incomplete integration is OK if documented.

### 10.6 Conclusion

System meets peer review requirements with simple design: legacy compatibility preserved (Link1 unchanged, no firmware update needed for 2KB SRAM device), PQC added on internet-facing Link2 via gateway offload pattern, with SQLite DB and analytics as observability and fallback for availability. Tests improved from 27/33 to 33/33 after hardening. CI/CD and Docker respect `pyproject.toml` + `uv.lock` + `.python-version` for reproducibility.

Remaining work is tech debt (global PSK, replay cache TTL, pk authentication, key rotation, TLS, scalability) prioritized for future sprints. LLM was used as untrusted assistant (10 interactions logged in 02_) and manually evaluated via pytest, REPL API testing, E2E checks — insecure suggestions (static nonce, `MLKEM512.keygen()`, Flask, requirements.txt) were rejected or corrected.

---

## 11. References (public, for Part1)

- [1] NIST FIPS 203 ML-KEM standard https://www.encryptionconsulting.com/education-center/ml-kem-fips-203/
- [2] ML-KEM sizes https://vucense.com/privacy-sovereignty/post-quantum-cryptography/ml-kem-fips-203-implementation-guide-2026/
- [3] CISA PQC Initiative https://www.cisa.gov/topics/risk-management/quantum
- [4] EU PQC roadmap hybrid https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/
- [5] Legacy constraints https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems
- [6] CISA product categories list Jan 2026 — prioritizing PQC-capable products in procurement (cloud, networking, endpoint)
- [7] ENISA/EU PQC roadmap — hybrid-PQC ciphers/certificates for legacy compatibility, inventory of all systems performing crypto
- [8] grp28 example documentation structure (non-authoritative, not committed) — inspired TOC, requirements mapping, architecture diagrams, LLM logs, testing evidence, operations, final eval

---

## 12. Appendix

### 12.1 Files

- `src/legacy_device.py` (1985B), `src/edge_gateway.py` (388 lines, hardened + PQC forwarding + fallback + health 5001), `src/pqc_utils.py` (258 lines, dual-wheel Rust/pure Python support), `src/cloud_service.py` (400 lines, SQLite + analytics + health 6001)
- `tests/unit/`, `tests/integration/`, `tests/conftest.py` (inserts both PROJECT_ROOT and src/ for import compatibility)
- `documentation/01_baseline_analysis.md`, `02_design_decisions_n_key_llm_interactions.md` (10+3 interactions), `03_mlkem_integration.md`, `04_migration_fallback_strategy.md`, `05_operations.md`, `06_final_evaluation.md` v3, `part1_documentation.md` (this file), `00_4h_gaps_analysis_n_scope_plan.md` (progress log with checkboxes)
- `.github/workflows/ci.yml`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `uv.lock`, `.python-version`, `README.md`

### 12.2 How to Run Tests

```bash
uv sync --frozen --all-groups
uv run pytest -v
# or PYTHONPATH=. /tmp/venv/bin/python -m pytest -v
# Expected: 33 passed
uv run python src/pqc_utils.py
# Expected: packet 845B, Round-trip OK, rust_binding True/False
```

### 12.3 LLM Prompts Full Log

See `02_design_decisions_n_key_llm_interactions.md` sections 1.1-1.10 + fixes 11-13 for full prompts, output summaries, human review, accepted/modified/rejected, verification via pytest/REPL/curl.

Key prompts:
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
- Fix11: "ModuleNotFoundError: No module named 'src'" → robust sys.path handling
- Fix12: "ImportError: cannot import name 'ML_KEM' from 'mlkem'" → dual-wheel support
- Fix13: "NameError: name 'os' is not defined" → add import os

---

**End of Part1 consolidated documentation — peer review entry point.**
