# Design Decisions and Key LLM Interactions

This markdown document contains
* significant/relevant prompt logs
* design decisions (accepted, modified, and rejected)
* current system limitations
* remaining project risks

---

## 1. Significant Input Prompts and LLM Interactions

In accordance with course guidelines, this section logs the human-AI interactions, recording the prompts provided to the LLM, the generated outputs, and subsequent human technical evaluations.

### 1.1. Interaction 1: Baseline Architecture & Scaffolding

* **Context / Objective:** Implement a lightweight sensor simulation representing an ATmega328P microcontroller communicating securely with an Edge Gateway.
* **Prompt Given to LLM:**
  > *"Write two Python scripts using the `cryptography` library. One is `legacy_device.py` which encrypts sensor JSON telemetry using AES-GCM and a pre-shared key, connects to `127.0.0.1:5000` via TCP, sends the data, and disconnects. The second is `edge_gateway.py` which listens on port 5000, receives the encrypted bytes, decrypts the payload with the same key, and prints the sensor data."*
* **LLM Output Summary:**
  * Proposed an initial `legacy_device.py` generating JSON telemetry, using `AESGCM(PRE_SHARED_KEY)`, generating a 12-byte random nonce via `os.urandom(12)`, prepending the nonce to the ciphertext, and pushing via a standard TCP client socket.
  * Proposed `edge_gateway.py` with a standard socket server loop, slicing `[:12]` for the nonce, decrypting the remaining ciphertext, and decoding UTF-8.
* **Human Review & Corrections:**
  * **Evaluation:** Basic `AESGCM` cryptography seemed to be implemented correctly.
  * **Issue Identified (Environment):** Running the code initially resulted in `Import "cryptography" could not be resolved`.
  * **Human Action:** Configured project dependencies using modern Python tooling (`uv init`, `uv add cryptography`, `uv sync`) and set the IDE interpreter to `./.venv`.


### 1.2. Interaction 2: Protocol Selection & Transport Inquiries

* **Context / Objective:** Determining the transport mechanism between the sensor and gateway.
* **Prompt Given to LLM:**
  > *"Should we use WebSockets or HTTP REST with Flask/FastAPI to stream the sensor data to the gateway?"*
* **LLM Output Summary:**
  * Outlined the benefits of WebSockets (persistent bidirectional framing) and HTTP (standard REST APIs), but also noted that microcontrollers often use simpler TCP or MQTT.
* **Human Review & Decision:**
  * **Rejected WebSockets and HTTP:** A real ATmega328P has only 2 KB of SRAM and 32 KB of Flash. Running an HTTP/1.1 client stack with verbose text headers (that add approximately 200–500 bytes extra per request) or a WebSocket client with Sec-WebSocket handshakes and framing masks would exhaust the 2 KB RAM.
  * **Accepted Bare TCP:** Raw TCP sockets were chosen as the closest software simulation of an embedded serial link (UART / RS-485) or direct modem socket.


### 1.3. Interaction 3: Packet Framing & Message Boundaries

* **Context / Objective:** Resolving TCP stream boundary detection.
* **Prompt Given to LLM:**
  > *"How should the edge gateway know when the sensor has finished sending the encrypted message over the TCP socket?"*
* **LLM Output Summary:**
  * Suggested three alternatives: (1) Length-prefixed framing (4-byte binary integer header), (2) Delimiter-based framing (e.g. newline or null-byte termination), or (3) Socket closure (`EOF`).
* **Human Review & Decision:**
  * **Rejected Delimiters:** Ciphertext contains arbitrary binary bytes, meaning any delimiter byte could appear randomly inside the encrypted stream, causing premature truncation unless base64-encoded (which adds 33% bloat).
  * **Accepted Socket Closure (`EOF`):** For the baseline, closing the socket after transmission (`client.sendall(packet)` followed by socket close) allows the gateway to read until `conn.recv()` returns empty bytes (`b""`). This keeps the simulated microcontroller code minimal and avoids complex buffer state machines.



### 1.4. Interaction 4 (Testing Step 1): Codebase Analysis, Test Plan

* **Context / Objective:** A team member (Quoc) reviewed the initial code in the project to establish the baseline test suite for `src/legacy_device.py` and `src/edge_gateway.py`. Before writing code, they used the LLM to analyze the codebase and create a test plan with topics and sub-topics.
* **Prompt Given to LLM (Prompt 1):**
  > *"I am new to this codebase. Please analyze `src/legacy_device.py` and `src/edge_gateway.py` in detail. Based on their architecture, propose a good test approach. Break it down into big topics and sub-topics covering unit, security, integration, and boundary validation. Also suggest how we should test because the gateway is supposed to run a continuous listening loop."*
* **LLM Analysis & Topic Proposal:**
  * **Codebase Analysis:**
    * `legacy_device.py`: Generates dictionary telemetry (`device_id`, `timestamp`, `temperature`, `humidity`, `status`), encrypts via `AESGCM(key)` with a fresh 12-byte random nonce prepended, connects over TCP to port 5000, pushes bytes with `sendall()`, and closes socket writer (`EOF` framing).
    * `edge_gateway.py`: Binds `127.0.0.1:5000` with `SO_REUSEADDR`, loops `accept()`, reads 1024-byte chunks until EOF (`b""`), slices first 12 bytes as nonce, decrypts remainder with `AESGCM`, and prints raw string.
  * **Proposed Big Topics & Sub-Topics:**
    1. **Topic 1: Core Functional Unit Testing (`tests/unit/`)**
       * Sub-topic 1.1: Telemetry schema and default values verification.
       * Sub-topic 1.2: End-to-end cryptographic round-trip (encrypt $\rightarrow$ decrypt).
       * Sub-topic 1.3: Wire format & packet layout (verifying 12-byte nonce placement at `[0:12]`).
       * Sub-topic 1.4: Payload edge cases (empty dictionaries `{}`, non-ASCII UTF-8 Unicode characters).
    2. **Topic 2: Cryptographic Security & Malformed Input Handling (`tests/unit/`)**
       * Sub-topic 2.1: Key validation (rejection of wrong 16-byte key, invalid key length, non-bytes types).
       * Sub-topic 2.2: AEAD tamper resistance (bit-flipping in ciphertext, in GMAC tag, and in nonce).
       * Sub-topic 2.3: Wire truncation defense (packets cut short by 1, 8, or 16 bytes).
       * Sub-topic 2.4: Serialization & encoding boundaries (non-JSON serializable inputs, non-UTF8 bytes).
    3. **Topic 3: Network & TCP Stream Flow Integration (`tests/integration/`)**
       * Sub-topic 3.1: End-to-end live TCP delivery on ephemeral loopback ports.
       * Sub-topic 3.2: TCP stream fragmentation & reassembly (sending packet across multiple split `sendall` chunks).
    4. **Topic 4: Gateway Robustness, Failure Modes & Edge Boundaries (`tests/integration/`)**
       * Sub-topic 4.1: Gateway survivability on malformed packets, mid-stream disconnects, and zero-byte connections.
       * Sub-topic 4.2: Framing boundaries: Multiple packets sharing one connection, payloads $>1024$ bytes.
       * Sub-topic 4.3: Application-layer validation: Non-JSON plaintexts, missing required schema keys.
       * Sub-topic 4.4: Replay attack vulnerability testing.
    5. **Topic 5: Advanced Scenarios (Candidate topic for evaluation):**
       * Sub-topic 5.1: Multi-client concurrency & load testing (e.g., 50 parallel sensors).
       * Sub-topic 5.2: Fuzz testing with Hypothesis.
  * **Test Fixture Architecture Proposal:**
    * Create a custom `GatewayProcess` class wrapping `subprocess.Popen` with stdout directed to a daemon worker thread pushing lines into a thread-safe `queue.Queue`. This avoids pipe buffer deadlocks when reading stdout from a long-running process.
    * Use dynamic ephemeral port reservation (`socket.bind(("127.0.0.1", 0))`) so every test runs against an isolated gateway without port collision (`EADDRINUSE`).
* **Human Alignment & Decisions:**
  * **Accepted Topics 1 to 4:** Agreed that Topics 1 to 4 are comprehensive enough to test that the baseline code works.
  * **Dropped Topic 5:** Dropped multi-client load testing and fuzzing because the current baseline gateway is intentionally single-threaded. Also adding external fuzzing libraries could add unnecessary scope and complexity to this project.


### 1.5. Interaction 5 (Testing Step 2): Test Case Generation, Review and Run

* **Context / Objective:** Get LLM to generate code for the tests based on the agreed parts of the test plan. Then the developer executed the tests on the baseline codebase.
* **Prompt Given to LLM (Prompt 2):**
  > *"Please proceed to generate code for topics 1 to 4 only. Topic 5 will make the project too complex and add unnecessary scope, so please avoid that. Also please provide the steps and commands to run the tests."*
* **LLM Output Summary:**
  * Generated 5 test files that can be tested using pytest.
  * Provided commands to run the tests.
* **Human Review, Execution & Triage:**
  * **Code Review:** The developer reviewed the generated test files. The tests looked good and correctly followed the agreed topics.
  * **Test Execution:** Ran `pytest -v` across the full set of tests.
  * **Empirical Outcome:** **27 tests passed, 6 tests failed.**
    * All unit tests (16/16) and basic TCP flow tests (2/2) passed.
    * 6 robustness tests failed in `test_gateway_failure_and_robustness.py`.
  * **Technical Analysis of Failures:**
    * The test failures were not due to test errors. The test failures were because of real architectural limitations in `edge_gateway.py`. Specifically, the baseline gateway lacks a `try...except` block around decryption (crashing the process on invalid inputs), has no JSON schema validation, and does not check for replayed packets.
  * **Conclusion & Decision:** The test code was verified to be correct and complete. Rather than prompting the LLM further to implement fixes in the gateway code, the developer preserved the failing tests to show that this was a limitation in the baseline code.


### 1.6. Interaction 6 (Gateway Hardening): Fixing 6 Failing Tests

* **Context / Objective:** Fix gateway to not crash on malformed packets, add schema validation and replay protection, make 33/33 tests pass.
* **Prompt Given to LLM:**
  > *"My edge_gateway.py crashes when it receives malformed AES-GCM packets (InvalidTag) and it accepts any JSON without validating required fields device_id, timestamp, temperature, humidity, status, and it doesn't check for replayed nonces. How should I harden it to pass these tests: test_gateway_remains_available_after_malformed_nonempty_packet, test_gateway_remains_available_after_connection_closes_mid_packet, test_gateway_remains_available_after_two_packets_share_one_connection, test_gateway_rejects_authenticated_non_json_payload_and_processes_valid_packet, test_gateway_rejects_wrong_telemetry_schema_and_processes_valid_packet, test_gateway_rejects_replayed_packet_and_processes_new_valid_packet? Keep it simple, single-threaded, with logging and metrics."*
* **LLM Output Summary:**
  * Suggested wrapping decrypt in try/except InvalidTag, ValueError, UnicodeDecodeError, JSONDecodeError, logging warning and continuing loop
  * Suggested REQUIRED_FIELDS set and `REQUIRED_FIELDS.issubset(payload.keys())` for schema validation
  * Suggested `seen_nonces=set()` for replay protection, check `if nonce in seen_nonces: reject`, add after successful validation
  * Suggested metrics dict and logging to file
* **Human Review & Decision:**
  * **Accepted:** try/except boundary, REQUIRED_FIELDS validation, seen_nonces set, metrics counters, logging to file (to keep stdout clean for tests that capture stdout+stderr merged)
  * **Modified:** LLM suggested logging to stderr — changed to file handler `gateway.log` because tests use `stderr=STDOUT` merged pipe, logging to stderr polluted `wait_for_line` (caused "Received ...Gateway health listening" concatenated line). Fixed by logging to file only.
  * **Modified:** Large packet test `test_gateway_decrypts_large_packet_received_across_multiple_chunks` originally used payload `{"device_id":..., "samples": "x"*5000}` missing required fields, so after adding schema validation it failed. Updated test payload to include required fields + samples to still test buffer accumulation.
  * **Verification:** Ran `pytest -v` → 33 passed, 0 failed. Manual E2E legacy→gateway with 2 sends works, logs show valid telemetry.

### 1.7. Interaction 7 (ML-KEM Integration): PQC Library and Hybrid Design

* **Context / Objective:** Integrate ML-KEM into Link 2 (gateway→cloud) using existing library, keep legacy Link 1 unchanged.
* **Prompt Given to LLM:**
  > *"I need to integrate ML-KEM-512 into my edge-cloud system. I have mlkem==0.0.3 library. Show how to generate keypair, encapsulate, decapsulate, and build hybrid encryption where ML-KEM shared secret (32B) is used as AES-256-GCM key to encrypt telemetry JSON. Wire format should be ct(768)||nonce(12)||aes_ct. Keep it simple, file-based public key distribution."*
* **LLM Output Summary:**
  * Initially suggested `MLKEM512.keygen()` and `ek.encaps()` which do not exist in `mlkem==0.0.3`
  * Suggested hybrid pattern: KEM + AES-GCM, which is correct
  * Suggested file-based pk distribution for simplicity
* **Human Review & Decision:**
  * **Rejected:** `MLKEM512.keygen()` — tested via `python -c "import mlkem; help(mlkem)"` and REPL, found correct API is `ML_KEM(ParameterSet.ML_KEM_512).key_gen() -> ek, dk` and `mlkem_obj.encaps(ek) -> ss, ct` and `mlkem_obj.decaps(dk, ct) -> ss`
  * **Accepted:** Hybrid pattern, file-based distribution (cloud writes `cloud_public_key.bin` 800B, gateway reads), wire format ct+nonce+aes_ct, constants PK_LEN=800, CT_LEN=768, SS_LEN=32
  * **Modified:** Added timing metrics `encaps_ms`, `decaps_ms` for PQC observability, added logging
  * **Verification:** Tested round-trip via `python src/pqc_utils.py` → packet 845B, encaps 0.03ms, decaps 0.04ms, decrypt matches original. Also tested via REPL `encrypt_for_cloud` then `decrypt_from_gateway`.

### 1.8. Interaction 8 (Cloud Service + SQLite DB + Analytics)

* **Context / Objective:** Build cloud service that decapsulates PQC, stores telemetry in simple DB, and provides analytics as observability.
* **Prompt Given to LLM:**
  > *"Create a cloud_service.py that listens on TCP 6000 for PQC packets (ct 768 + nonce 12 + aes_ct), decapsulates using ML-KEM-512 private key, AES-GCM decrypts, stores in SQLite telemetry.db with table telemetry(id, device_id, timestamp, temperature, humidity, status, received_at, source_ip, pqc_decaps_ms, raw_json), and has health/analytics endpoint on 6001 returning JSON with db_rows, avg temp/humidity, last 10, decaps_ok/fail, success_rate, avg_decaps_ms. Keep it simple, stdlib only, no Flask."*
* **LLM Output Summary:**
  * Suggested using `sqlite3` stdlib, `http.server` for health endpoint (no Flask), threading for health server, metrics dict with lock for thread safety, `check_same_thread=False` for sqlite
  * Suggested `CREATE TABLE IF NOT EXISTS` and `INSERT` with `?` placeholders
  * Suggested analytics queries `SELECT COUNT(*), AVG(temperature)` and `last 10 ORDER BY received_at DESC`
* **Human Review & Decision:**
  * **Accepted:** SQLite with stdlib, http.server for health (rejected Flask to keep simple), threading, metrics with lock, analytics queries
  * **Modified:** LLM suggested logging to stderr — changed to file handler `cloud.log` to keep stdout clean for tests and Docker logs
  * **Verification:** Ran cloud alone → `telemetry.db` 12K created, pk 800B file, `curl http://127.0.0.1:6001/health` returns JSON with db_rows 0, analytics empty, pqc metrics. Then E2E with gateway: 2 sends → DB has 2 rows, health shows db_rows 2, avg_temp 21.8, decaps_ok 2, success_rate 1.0.

### 1.9. Interaction 9 (Gateway Forwarding + Fallback + Health)

* **Context / Objective:** Extend gateway to forward validated telemetry to cloud via PQC, with fallback to local log if cloud down or pk missing, and add health endpoint 5001.
* **Prompt Given to LLM:**
  > *"Extend edge_gateway.py to forward telemetry to cloud via PQC: try load cloud_public_key.bin, if missing or cloud unreachable, append JSON to gateway_fallback.log with timestamp and increment fallback_local metric. Use pqc_utils.encrypt_for_cloud and TCP send to 127.0.0.1:6000. Add health endpoint on 5001 returning JSON with received, rejected, replayed, forwarded_to_cloud, fallback_local, cloud_fail, replay_cache_size, uptime. Keep it simple, stdlib http.server, thread-safe metrics."*
* **LLM Output Summary:**
  * Suggested `forward_to_cloud()` function with try load pk, try socket create_connection with timeout, fallback to file append, metrics with lock
  * Suggested health handler similar to cloud, threading
* **Human Review & Decision:**
  * **Accepted:** forward_to_cloud logic, fallback log format `<timestamp> <json>`, metrics `forwarded_to_cloud`, `fallback_local`, `cloud_fail`, health thread on 5001
  * **Modified:** Removed `print` for health listening to keep stdout clean for tests (only log to file), added `metrics_lock` for thread safety
  * **Verification:** Tested fallback: stop cloud, send legacy → `gateway_fallback.log` has entry, health 5001 shows fallback_local=1. Tested E2E with cloud up: 2 sends → DB 2 rows, gateway health forwarded=2, cloud health decaps_ok=2.

### 1.10. Interaction 10 (Docker + CI/CD + pyproject.toml/uv.lock/.python-version)

* **Context / Objective:** Create CI/CD and Docker that respect pyproject.toml, uv.lock, .python-version, keep simple.
* **Prompt Given to LLM:**
  > *"Generate GitHub Actions CI and Dockerfile and docker-compose for Python project using uv package manager, with pyproject.toml, uv.lock, .python-version 3.13. CI should run pytest -v, test PQC utils, check imports. Dockerfile should be python:3.13-slim, respect locked versions via uv sync --frozen, and have HEALTHCHECK. docker-compose should have cloud and gateway services with healthchecks and volume sharing for public key. Keep it simple."*
* **LLM Output Summary:**
  * Initially suggested `pip install -r requirements.txt` — rejected, project uses pyproject.toml + uv, not requirements.txt
  * Suggested Flask for health — rejected, we use stdlib http.server
  * Suggested `astral-sh/setup-uv` action, `uv sync --frozen`, Dockerfile with `pip install uv && uv sync --frozen --no-install-project`, `ENV PATH .venv/bin`
* **Human Review & Decision:**
  * **Rejected:** requirements.txt approach, Flask
  * **Accepted:** `astral-sh/setup-uv@v4` with cache, `uv python install`, `uv sync --frozen`, `uv pip install pytest`, `uv run pytest -v`, Dockerfile with `COPY pyproject.toml uv.lock .python-version README.md`, `uv sync --frozen --no-install-project`, `ENV PATH .venv/bin`, HEALTHCHECK via socket connect, docker-compose with `depends_on healthy` and bind mounts for pk file
  * **Modified:** Added `[dependency-groups] dev = ["pytest>=8.0"]` to pyproject.toml to track pytest as dev dep, while main deps remain locked in uv.lock
  * **Verification:** Ran `pytest -v` 33 passed after pyproject.toml edit, checked Dockerfile copies correct files, CI yml contains checks for .python-version, pyproject.toml, uv.lock existence

---

## 2. Design Decisions: Accepted, Modified, and Rejected

The following matrix documents the architectural trade-offs evaluated during the baseline phase:

| Decision Area | Option Selected (Accepted) | Alternatives Evaluated | Status | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **PQC Placement** | Offload ML-KEM to Edge Gateway | Run ML-KEM-512 directly on the sensor | **Rejected** | ML-KEM-512 requires ~1,632 bytes for secret keys and 1,000–1,500 bytes working memory (~3 KB total). The sensor has only 2 KB SRAM, causing an unavoidable stack overflow. |
| **Local Link Security** | AES-128-GCM with 16-byte PSK | ChaCha20-Poly1305, Plain AES-CBC | **Accepted** | AES-GCM provides Authenticated Encryption with Associated Data (AEAD), ensuring both confidentiality and tamper detection (GMAC tag). |
| **Transport Layer** | Bare TCP Socket (`port 5000`) | WebSockets, HTTP/REST, MQTT | **Rejected** | WebSockets and HTTP introduce 200–500 bytes of header overhead per message, exhausting sensor RAM and wasting battery power. |
| **Packet Framing** | Single-shot Connection Closure (`EOF`) | 4-byte Length-Prefix Header, Delimiter framing | **Accepted / Modified** | EOF framing simplifies microcontroller memory management. (Noted as a temporary trade-off: persistent connections with length headers may be considered in future sprints). |
| **Key Distribution** | Pre-Shared Key (PSK) in ROM | Dynamic Key Exchange (Diffie-Hellman / ECDH) | **Accepted** | Embedded sensors commonly store factory-flashed PSKs in write-protected Flash ROM to avoid compute-intensive asymmetric handshakes. |
| **Nonce Generation** | Fresh 12-byte random nonce per packet | Sequential counter, Static Nonce | **Accepted** | AES-GCM security completely collapses if nonces are reused with the same key. A 96-bit random nonce ensures freshness without requiring persistent EEPROM write cycles. |

---

## 3. Current System Limitations

Empirical testing (including 27 passing tests and 6 failing integration tests in `tests/`) reveals specific boundaries in the current baseline:

### 3.1. Absence of Gateway Recovery Boundary (Crash on Bad Input)
* **Observed Behavior:** If an adversary transmits malformed bytes, a truncated packet, or data encrypted with a wrong key, `aesgcm.decrypt()` raises `cryptography.exceptions.InvalidTag`.
* **Impact:** In the current `edge_gateway.py`, this unhandled exception crashes the entire gateway process (`exit status 1`). Any subsequent connections from legitimate sensors are refused.

### 3.2. Lack of Telemetry Application Schema Validation
* **Observed Behavior:** The gateway decrypts the payload and blindly logs `Received from device: {raw_data}` as long as the bytes form valid UTF-8.
* **Impact:** An authenticated payload missing critical sensor fields (e.g., missing `temperature` or `timestamp`) or containing arbitrary string data is accepted without validation.

### 3.3. Vulnerability to Replay Attacks
* **Observed Behavior:** The gateway processes any packet with a valid GMAC tag.
* **Impact:** An eavesdropper who records a valid sensor transmission can re-transmit the exact same byte sequence. The gateway will accept, decrypt, and log the duplicate reading as legitimate telemetry.

### 3.4. Single-Client Synchronous Blocking Loop
* **Observed Behavior:** `edge_gateway.py` executes a single-threaded synchronous loop (`server.accept()` followed by blocking `conn.recv()`).
* **Impact:** While the gateway reads or decrypts data from one sensor, no other sensor can connect. If one client stalls, the gateway hangs for all nodes.

### 3.5. TCP Handshake Overhead
* **Observed Behavior:** Using connection closure (`EOF`) as the message boundary requires opening and closing a TCP socket for each reading.
* **Impact:** Every reading requires a full TCP 3-way handshake (`SYN` $\rightarrow$ `SYN-ACK` $\rightarrow$ `ACK`) and teardown (`FIN` $\rightarrow$ `ACK`), introducing network latency.

---

## 4. Remaining Project Risks and Mitigation Roadmap

| # | Identified Risk | Severity | Potential Impact | Planned Mitigation Strategy (Sprint 2 / Future) |
| :---: | :--- | :---: | :--- | :--- |
| **R1** | **Gateway Denial of Service (Crash via Malformed Input)** | **High** | A single bad transmission terminates the gateway process. | Wrap socket parsing and decryption in `try...except (InvalidTag, ValueError, UnicodeDecodeError)` blocks to log anomalies and keep the listening loop alive. |
| **R2** | **Replay Attacks on Legacy Link** | **Medium** | Stale or malicious telemetry can be reinjected into the cloud pipeline. | Add a sliding-window timestamp validator or track seen nonces in an in-memory gateway cache with a short time-to-live (TTL). |
| **R3** | **Pre-Shared Key (PSK) Extraction** | **Medium** | Physical tampering with a sensor could expose the symmetric key. | Use protected internal Flash memory on embedded targets, plan for gateway-side per-device subkeys rather than a global shared key. |
| **R4** | **PQC Performance & Memory Overhead on Gateway** | **Medium** | Integrating `mlkem` for Cloud forwarding may increase CPU latency. | Benchmark ML-KEM-512 encapsulation time and memory footprint on the edge gateway host to ensure real-time ingestion. |
| **R5** | **Scalability & Concurrent Node Starvation** | **Low** | Multiple sensor nodes transmitting simultaneously could cause connection timeouts. | Refactor `edge_gateway.py` to use asynchronous I/O (`asyncio`) or a multi-threaded connection worker pool. |

