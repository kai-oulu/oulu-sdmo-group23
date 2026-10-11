# Final Evaluation — Strengths, Weaknesses, Technical Debt, Risks

## 0. Acronyms (explicit, for non-CS readers)

- **PQC = Post-Quantum Cryptography**: new crypto that resists quantum computers
- **ML-KEM = Module-Lattice-based Key Encapsulation Mechanism** (NIST FIPS 203, based on CRYSTALS-Kyber): a PQC algorithm to agree on a secret key
- **KEM = Key Encapsulation Mechanism**: method where one side encrypts a random secret with public key, other side decrypts it
- **PSK = Pre-Shared Key**: same secret key flashed into all devices at factory, used for AES
- **AES-GCM = Advanced Encryption Standard - Galois/Counter Mode**: symmetric encryption that gives confidentiality + integrity tag
- **pk = public key** (ML-KEM encapsulation key, 800 Bytes), **sk/dk = secret key / decapsulation key** (1632B private), **ct = ciphertext** (768B encapsulated secret), **ss = shared secret** (32B random that becomes AES key), **B = Bytes**, **KB = Kilobytes**
- **TTL = Time To Live**: how long we keep an entry before deleting it
- **OOM = Out Of Memory**: program uses too much RAM and crashes
- **LRU = Least Recently Used**: cache eviction policy — remove oldest unused entries first
- **MITM = Man-In-The-Middle**: attacker sits between two parties, can read/modify traffic
- **DoS = Denial of Service**: attacker makes service unavailable by crashing or overloading it
- **TLS = Transport Layer Security**: HTTPS-like protocol that gives authentication + encryption
- **HSM = Hardware Security Module**, **KMS = Key Management System**: hardware/software to store private keys safely
- **DB = Database**, **ORM = Object-Relational Mapper** (we avoided ORM, used raw sqlite3)
- **E2E = End-to-End**, **EOF = End-Of-File** (close TCP to signal end of message)
- **MTU = Maximum Transmission Unit**: max packet size radio can send

## 1. Overview

We modernized from initial 2-tier baseline (legacy sensor → gateway, 27/33 tests passing) into 3-tier system with PQC (legacy sensor → gateway → cloud) that works end-to-end and passes **33/33 tests**. Gateway now validates JSON schema, checks replay, stays alive on malformed input, forwards via ML-KEM-512 hybrid to cloud, with fallback to local log. Cloud stores telemetry in SQLite DB and exposes analytics via health endpoints. CI/CD and Docker respect `pyproject.toml` + `uv.lock` + `.python-version`.

E2E evidence: 2 legacy sends → gateway metrics `received 2, forwarded 2`, cloud metrics `db_rows 2, avg_temp 21.8, decaps_ok 2, success_rate 1.0`, file `telemetry.db` has 2 rows. Fallback evidence: when cloud down → `gateway_fallback.log` has entry, `fallback_local=1`.

## 2. Strengths

- **End-to-end 3-tier works:** Legacy Link1: AES-128-GCM with PSK (TCP port 5000, EOF framing) → gateway decrypt + validate + replay check → Link2 PQC hybrid `ct(768B)||nonce(12B)||aes_ct` ~845B total → cloud decaps + SQLite insert. This satisfies core requirement: integrate ML-KEM into at least one path (Link2 internet-facing) while preserving Link1 (no firmware change for 2KB SRAM sensor).
- **Robust gateway (was crashing):** Previously gateway crashed with `InvalidTag` exception and exited with code 1 when attacker tampered packet. Now wrapped in `try/except InvalidTag, ValueError, UnicodeDecodeError, JSONDecodeError`, logs warning, continues running. Added schema validation (`REQUIRED_FIELDS = device_id, timestamp, temperature, humidity, status`) and replay cache (`seen_nonces=set()` stores 12B random nonces seen). Result: 33/33 tests pass (was 27/33).
- **Minimal but functional PQC:** Library `mlkem==0.0.3` (Rust binding, pip-installable) chosen over `kyber-py` and `liboqs` for simplicity. ML-KEM-512 chosen for lowest overhead: pk public key 800B + ct ciphertext 768B = 1568B total vs 2272B for ML-KEM-768. Hybrid: ss shared secret 32B used as AES-256-GCM key to encrypt actual JSON. Measured encaps ~0.03ms, decaps ~0.04ms — negligible for gateway running Linux/Raspberry Pi.
- **Simple DB as observability:** SQLite `telemetry.db` (Python stdlib, 1 table, no ORM) with queries `COUNT`, `AVG(temp/humidity)`, `last 10 rows`. Exposed via cloud health port 6001 JSON and gateway health port 5001 metrics. This is "simple analytics" requested — managers can see how many messages protected by PQC vs fallback, average temperature, recent telemetry.
- **Fallback ensures availability:** If `cloud_public_key.bin` file missing or cloud unreachable (TCP 6000 refused/timeout), gateway appends `<timestamp> <json>` to `gateway_fallback.log` + increments `fallback_local`. Cloud decaps fail → `decaps_fail++` but stays alive. This is business continuity, per CISA hybrid guidance: keep service up even if PQC path fails.
- **Operations complete but simple:** CI via `astral-sh/setup-uv` reading `.python-version` + `uv.lock`, `uv sync --frozen` + `pytest -v`; Dockerfile `python:3.13-slim` + `uv sync --frozen --no-install-project` (respects lock); docker-compose with named volume `pqc-shared` for pk sharing, healthchecks, `depends_on healthy`; logging to files (`gateway.log`, `cloud.log`, `pqc.log`) to keep stdout clean for tests; health endpoints via stdlib `http.server` (no Flask dependency).

## 3. Weaknesses and Technical Debt

We kept design simple for 4h limit and limited crypto background, so several weaknesses remain. Each documented as tech debt with future mitigation.

| Weakness / Debt | Why It Matters (plain English) | Impact | Future Mitigation |
|-----------------|--------------------------------|--------|-------------------|
| **Global 16B PSK (Pre-Shared Key) for all devices `legacy_secret_16`** | All sensors share same 16 Byte key. If one device is physically stolen and attacker reads its Flash ROM chip, attacker can decrypt all Link1 traffic and forge fake temperature data for all devices. | High if device tampered | Per-device subkeys derived from master key, store in protected Flash, add key rotation |
| **Replay cache no TTL (Time To Live), no persistence** | `seen_nonces=set()` is a Python set in RAM that remembers 12B nonces we already saw to block replay. Two problems: (1) grows forever → could OOM (Out Of Memory) with many devices, (2) **On restart, set cleared → replayed packets accepted again**: when gateway process restarts, RAM is wiped, set becomes empty `set()`, so attacker can replay an old captured packet and gateway thinks it is new because nonce not in empty set. | Medium (memory leak, replay after restart) | LRU (Least Recently Used) cache with TTL e.g., 5 min, or timestamp window (only accept packets whose timestamp is within last 5 min), persist cache to file/DB |
| **File-based pk (public key) distribution, no auth (authentication)** | `cloud_public_key.bin` (800B) has no signature. If attacker replaces file on disk, they can do MITM (Man-In-The-Middle) on Link2 gateway→cloud. | Medium (MITM) | Sign pk file with private key, use certificate, or fetch via TLS with pinning, or KMS (Key Management System) |
| **No key rotation** | ML-KEM dk (decapsulation key = private key, 1632B) stays in memory forever, never changed. If leaked, all past and future Link2 messages compromised (no forward secrecy = old messages can be decrypted). | Medium (long-term exposure) | Rotate daily, store dk in HSM (Hardware Security Module) or encrypted file, versioned keys |
| **No TLS (Transport Layer Security) on Link2** | PQC KEM gives confidentiality (no one can read) but no server authentication beyond file-based pk. Gateway does not know it really talks to real cloud. | Medium (no server auth) | Add TLS 1.3 with PQC certificates or hybrid certs |
| **Single-threaded gateway (data plane) — concurrent starvation risk** | **Thread count clarification:** we have **2 threads total**: (1) main TCP data thread that does `accept()` + blocking `recv()` = waits for one sensor at a time, (2) health HTTP thread on port 5001. So data path is single-threaded. **Concurrent starvation** means: while gateway processes one sensor (decrypt, validate, forward to cloud), other sensors that connect at same time wait in TCP queue (they starve, not served). If 100 sensors send at once, they timeout. This does NOT contradict single-threaded point — we intentionally said single-threaded for simplicity, 2 threads total but only 1 handles sensor data. | Low (scalability) | `asyncio` (asynchronous I/O) or thread pool (rejected for simplicity) |
| **Logs no rotation, DB no backup** | `gateway.log`, `cloud.log`, `pqc.log` grow forever → disk full. `telemetry.db` single file, no backup → data loss if disk fails. | Low | `RotatingFileHandler`, periodic DB backup/replication |

We intentionally kept these for simplicity per course guidance.

## 4. Risks (Consolidated R1-R7)

| # | Risk | Severity | Status | Remaining (what still needs fixing) |
|---|------|----------|--------|--------------------------------------|
| **R1** | Gateway DoS (Denial of Service) via malformed input (crash on InvalidTag) | High | **Mitigated:** try/except + schema + replay, now 33/33 pass, stays alive | Large payload could still cause high CPU when decrypting, should add rate limiting |
| **R2** | Replay attacks (stale telemetry reinjected) | Medium | **Mitigated:** seen_nonces set rejects replayed nonce (if nonce already seen, drop) | No TTL (Time To Live), restart clears cache → replay possible after restart. Should add timestamp window: only accept packets where `now - timestamp < 5 min`, and keep nonces only for that window |
| **R3** | PSK (Pre-Shared Key) extraction (physical tampering) | Medium | **Not mitigated:** global PSK still | Per-device keys, protected Flash |
| **R4** | PQC performance & memory overhead | Medium | **Mitigated/measured:** encaps 0.03ms, decaps 0.04ms negligible for gateway (Linux/Pi) | 800B pk (public key) + 768B ct (ciphertext) overhead matters for constrained radio, documented. **Constrained radio** = low-power wireless like LoRaWAN, Zigbee, BLE, NB-IoT with small MTU (e.g., 51-250B max), low bandwidth, battery-powered. Sending 1568B extra each message is heavy for them (needs fragmentation, more battery). In our simulated TCP/Ethernet setup it's fine, but for real battery sensor with LoRa it would be problem. |
| **R5** | Scalability & concurrent starvation | Low | **Not mitigated:** single-threaded data plane (2 threads total, 1 for data) | asyncio or thread pool future |
| **R6** | File-based pk (public key) MITM (Man-In-The-Middle) | Medium | **Not mitigated:** pk file no auth (authentication) | Sign pk or use secure distribution |
| **R7** | DB (Database) no backup | Low | **Not mitigated:** single file `telemetry.db` | Periodic backup |

Overall, high-severity R1 fixed, medium R2 partially fixed, others documented as debt.

## 5. What If ML-KEM Not Fully Integrated? (Per Course Q&A: OK to Document)

Current integration is minimal viable and works E2E (tested). If PQC path fails:

- **Cloud down or pk (public key) missing:** Gateway fallback to `gateway_fallback.log` ensures no data loss (business continuity). Operator can replay log later.
- **Decaps fail (decapsulation = private key decrypt fails):** Cloud increments `decaps_fail`, logs warning, stays alive, `success_rate` exposed via health 6001 shows degradation.
- **Gaps documented:** No key rotation, no cert (certificate), ML-KEM-512 only (not 768 for long-term confidentiality), file-based distribution. For peer review, this is sufficient — 3-tier works, PQC path exists, fallback documented, per course guidance that incomplete integration is OK if documented.

## 6. Conclusion

System meets peer review requirements with simple design: legacy compatibility preserved (Link1 unchanged, no firmware update needed for 2KB SRAM device), PQC added on internet-facing Link2 via gateway offload pattern, with SQLite DB and analytics as observability and fallback for availability. Tests improved from 27/33 to 33/33 after hardening. CI/CD and Docker respect `pyproject.toml` + `uv.lock` + `.python-version` for reproducibility.

Remaining work is tech debt (global PSK, replay cache TTL, pk authentication, key rotation, TLS, scalability) prioritized for future sprints. LLM was used as untrusted assistant (10 interactions logged in 02_) and manually evaluated via pytest, REPL API testing, E2E checks — insecure suggestions (static nonce, `MLKEM512.keygen()`, Flask, requirements.txt) were rejected or corrected.
