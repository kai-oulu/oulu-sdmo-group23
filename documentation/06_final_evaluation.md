# Final Evaluation - Strengths, Weaknesses, Technical Debt, Risks

## 0. Acronyms
- **PQC = Post-Quantum Cryptography**: new crypto that resists quantum computers
- **ML-KEM = Module-Lattice-based Key Encapsulation Mechanism** (NIST FIPS 203, based on CRYSTALS-Kyber): a PQC algorithm to agree on a secret key
- **KEM = Key Encapsulation Mechanism**: method where one side encrypts a random secret with public key, other side decrypts it
- **PSK = Pre-Shared Key**: same secret key flashed into all devices at factory, used for AES
- **AES-GCM = Advanced Encryption Standard - Galois/Counter Mode**: symmetric encryption that gives confidentiality + integrity tag
- **pk = public key** (ML-KEM encapsulation key, 800 Bytes), **sk/dk = secret key / decapsulation key** (1632B private), **ct = ciphertext** (768B encapsulated secret), **ss = shared secret** (32B random that becomes AES key), **B = Bytes**, **KB = Kilobytes**
- **TTL = Time To Live**: how long we keep an entry before deleting it
- **OOM = Out Of Memory**: program uses too much RAM and crashes
- **LRU = Least Recently Used**: cache eviction policy - remove oldest unused entries first
- **MITM = Man-In-The-Middle**: attacker sits between two parties, can read/modify traffic
- **DoS = Denial of Service**: attacker makes service unavailable by crashing or overloading it
- **TLS = Transport Layer Security**: HTTPS-like protocol that gives authentication + encryption
- **HSM = Hardware Security Module**, **KMS = Key Management System**: hardware/software to store private keys safely
- **DB = Database**, **ORM = Object-Relational Mapper** (we avoided ORM, used raw sqlite3)
- **E2E = End-to-End**, **EOF = End-Of-File** (close TCP to signal end of message)
- **MTU = Maximum Transmission Unit**: max packet size radio can send


## 1. Overview

We modernized from an initial 2-tier baseline system (legacy sensor → gateway, 27/33 tests) into a 3-tier system with PQC (legacy → gateway → cloud) that works end-to-end and passed **33/33 tests**. The gateway now validates schema, checks replay, stays alive on malformed input, forwards via ML-KEM-512 hybrid to cloud, with fallback to local log. Cloud stores telemetry in SQLite and exposes analytics via health endpoints. CI/CD and Docker respect `pyproject.toml` + `uv.lock` + `.python-version`.

E2E evidence: 2 legacy sends → gateway `received 2, forwarded 2`, cloud `db_rows 2, avg_temp 21.8, decaps_ok 2, success_rate 1.0`, `telemetry.db` has 2 rows. Fallback evidence: cloud down → `gateway_fallback.log` has entry, `fallback_local=1`.


## 2. Strengths

- **End-to-end 3-tier works:** Legacy AES-128-GCM PSK (TCP 5000, EOF) → gateway decrypt + validate + replay check → PQC hybrid `ct(768)||nonce(12)||aes_ct` ~845B → cloud decaps + SQLite insert. This satisfies the core requirement of integrating ML-KEM into at least one path (Link2) while preserving Link1.
- **Robust gateway:** Previously crashed on `InvalidTag` (exit 1). Now wrapped in `try/except InvalidTag, ValueError, UnicodeDecodeError, JSONDecodeError`, logs warning, continues. Schema validation (`REQUIRED_FIELDS`) and replay cache (`seen_nonces=set()`) added. Result: 33/33 tests pass (was 27/33).
- **Minimal but functional PQC:** Library `mlkem==0.0.3` (Rust binding) chosen for simplicity over `kyber-py` and `liboqs`. ML-KEM-512 selected for lowest overhead (800B pk + 768B ct = 1568B vs 2272B for 768). Hybrid with AES-256-GCM (ss 32B as key). Measured encaps ~0.03ms, decaps ~0.04ms - negligible for gateway.
- **Simple DB as observability:** SQLite `telemetry.db` (stdlib, 1 table, no ORM) with `COUNT, AVG(temp/humidity), last 10` queries. Exposed via cloud health 6001 JSON and gateway health 5001 metrics. This is the "simple analytics" requested - managers can see how many messages protected by PQC vs fallback, avg temp, recent telemetry.
- **Fallback ensures availability:** If `cloud_public_key.bin` missing or cloud unreachable (TCP 6000 refused/timeout), gateway appends `<timestamp> <json>` to `gateway_fallback.log` + `fallback_local++`. Cloud decaps fail → `decaps_fail++` but stays alive. This is business continuity, per CISA hybrid guidance.
- **Operations complete but simple:** CI via `astral-sh/setup-uv` reading `.python-version` + `uv.lock`, `uv sync --frozen` + `pytest -v`; Dockerfile `python:3.13-slim` + `uv sync --frozen --no-install-project` (respects lock); docker-compose with named volume `pqc-shared` for pk sharing, healthchecks, `depends_on healthy`; logging to files (`gateway.log`, `cloud.log`, `pqc.log`) to keep stdout clean for tests; health endpoints via stdlib `http.server` (no Flask).


## 3. Weaknesses and Technical Debt

We kept design simple for our current project as we have limited understanding of cryptography and post-quantum cryptography, so several weaknesses remain. Each is documented as tech debt with future mitigation.

| Weakness / Debt | Why It Matters | Impact | Future Mitigation |
|-----------------|----------------|--------|-------------------|
| **Global 16B PSK/Pre-Shared Key for all devices** | All devices share same 16B key. If one device is physically tampered with and its Flash ROM is extracted, an attacker can decrypt all Link1 traffic and forge telemetry data. | High if device is tampered | Per-device subkeys derived from a master, stored in protected Flash, key rotation |
| **Replay cache no TTL (Time To Live), no persistence** | `seen_nonces=set()` is a Python set in RAM that remembers 12B nonces we already saw to block replay. Two problems: (1) grows forever → could OOM (Out Of Memory) with many devices, (2) **On restart, the `seen_nonces` set gets cleared → replayed packets accepted again**: when gateway process restarts, RAM is wiped, set becomes empty `set()`, so attacker can replay an old captured packet and gateway thinks it is new because nonce not in empty set. | Medium (memory leak, replay after restart) | LRU (Least Recently Used) cache with TTL e.g., 5 min, or timestamp window (only accept packets whose timestamp is within last 5 min), persist cache to file/DB |
| **File-based pk distribution, no auth** | `cloud_public_key.bin` has no signature. Attacker replacing the file can MITM Link2 (decrypt gateway→cloud). | Medium (MITM Man in the Middle) | Sign pk/public key file, use certificate, or fetch via TLS with pinning, or KMS/key management system |
| **No key rotation** | ML-KEM dk/decapsulation key stays in memory, never rotated. If leaked, all past and future Link2 messages compromised (no forward secrecy). | Medium (long-term exposure) | Rotate daily, store dk/decapsulation key in HSM/Hardware Security Module or encrypted file, versioned keys |
| **No TLS on Link2** | PQC KEM provides confidentiality but no server authentication beyond file-based pk/public key. | Medium (no server auth) | Add TLS 1.3 with PQC certs or hybrid certs |
| **Single-threaded gateway (data plane) - other sensors can get stuck in the queue** | **Thread count clarification:** we have **2 threads in total**: (1) main TCP data thread that does `accept()` + blocking `recv()` = waits for one sensor at a time, (2) health HTTP thread on port 5001. So data path is single-threaded. While gateway processes one sensor (decrypt, validate, forward to cloud), other sensors that connect at same time wait in the TCP queue. If 100 sensors send data all at once to the gateway, they timeout. | Low (scalability) | `asyncio` (asynchronous I/O) or thread pool (rejected for simplicity) |
| **Logs no rotation, DB no backup** | `gateway.log`, `cloud.log`, `pqc.log` grow forever → disk full. `telemetry.db` single file, no backup → data loss. | Low | `RotatingFileHandler`, periodic DB backup/replication |

We intentionally kept the above technical debts for simplicity.


## 4. Risks

| # | Risk | Severity | Status | Remaining |
|---|------|----------|--------|-----------|
| **R1** | Gateway DoS/Denial of Service via malformed input (crash on InvalidTag) | High | **Mitigated:** try/except + schema + replay, now 33/33 pass, stays alive | Large payload could still cause high CPU load when decrypting, so we should add rate limiting functionality |
| **R2** | Replay attacks (stale telemetry reinjected) | Medium | **Mitigated:** seen_nonces set rejects replayed nonce (if nonce already seen, drop) | No TTL (Time To Live), restart clears cache → replay possible after restart. Should add timestamp window: only accept packets where `now - timestamp < 5 min`, and keep nonces only for that window |
| **R3** | PSK/Pre-Shared Key extraction (physical tampering) | Medium | **Not mitigated:** global PSK/Pre-Shared Key still exists | Per-device keys, protected Flash |
| **R4** | PQC performance & memory overhead | Medium | **Mitigated/measured:** encaps 0.03ms, decaps 0.04ms negligible for gateway (Linux/Pi) | 800B pk (public key) + 768B ct (ciphertext) overhead matters for constrained radio. **Constrained radio** = low-power wireless like LoRaWAN, Zigbee, BLE, NB-IoT with small MTU (e.g., 51-250B max), low bandwidth, battery-powered. Sending 1568B extra each message is heavy for them. In our simulated TCP/Ethernet setup it is fine, but for real battery sensors with constrained radio/LoRa, it would be a problem. |
| **R5** | Scalability & concurrent starvation | Low | **Not mitigated:** single-threaded | asyncio or thread pool future |
| **R6** | File-based pk/public key MITM | Medium | **Not mitigated:** pk/public key file no auth | Sign pk/public key or use secure distribution |
| **R7** | DB no backup | Low | **Not mitigated:** single file | Periodic backup |

Overall, high-severity R1 is fixed, medium R2 partially fixed, others documented as technical debt.


## 5. What If ML-KEM Not Fully Integrated?

Current integration is minimal viable and works E2E (tested). If PQC path fails:

- **Cloud down or pk/public key missing:** Gateway fallback to `gateway_fallback.log` ensures no data loss (business continuity). Operator can replay log later.
- **Decaps fail:** Cloud increments `decaps_fail`, logs will show a warning, system stays alive, `success_rate` exposed via health 6001 shows degradation.
- **Gaps documented:** No key rotation, no cert, ML-KEM-512 only (not 768 for long-term confidentiality), file-based distribution.
