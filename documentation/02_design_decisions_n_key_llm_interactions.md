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

