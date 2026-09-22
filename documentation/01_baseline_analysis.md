# Baseline Analysis
This markdown file documents the following items based Project slide 4 of 14.:
```
Baseline analysis:
Understand and document the initial architecture, run the system, and establish baseline tests and measurements
```

## 1. Initial Architecture
* The initial system architecture consists of 2 tiers, with the legacy device and edge gateway only.
```
+---------------------------------------------------------------------------------------------------+
|                                       SYSTEM ARCHITECTURE                                         |
+---------------------------------------------------------------------------------------------------+

 [       Tier 1: Sensor      ]              [ Tier 2: Edge Gateway ]
 
 +---------------------------+              +---------------------+
 |   Simulated Legacy Device |              |    Edge Gateway     |
 |    (legacy_device.py)     |              |  (edge_gateway.py)  |
 |                           |              |                     |
 | • Profile: ATmega328P     |              | • Linux / Pi host   |
 | • 2 KB SRAM / 32 KB Flash | AES-128-GCM  | • Decrypts AES-GCM  |
 | • Symmetric encryption    | ------------>| • Validates schema  |
 | • Raw TCP / Port 5000     |   (Link 1)   | • Encapsulates PQC  |
 | • EOF message framing     |              | • Forwards to cloud |
 +---------------------------+              +---------------------+
```

* After implementing the 2-tier architecture, we will add the cloud service as the 3rd tier, with ML-KEM (a post-quantum cryptographic algorithm) to encrypt communications between the Edge Gateway and Cloud Service.
```
+---------------------------------------------------------------------------------------------------+
|                                       SYSTEM ARCHITECTURE                                         |
+---------------------------------------------------------------------------------------------------+

 [       Tier 1: Sensor      ]              [ Tier 2: Edge Gateway ]             [ Tier 3: Cloud Service ]
 
 +---------------------------+              +---------------------+             +----------------------+
 |   Simulated Legacy Device |              |    Edge Gateway     |             |    Cloud Service     |
 |    (legacy_device.py)     |              |  (edge_gateway.py)  |             |  (cloud_service.py)  |
 |                           |              |                     |             |                      |
 | • Profile: ATmega328P     |              | • Linux / Pi host   |             | • Ingestion API      |
 | • 2 KB SRAM / 32 KB Flash | AES-128-GCM  | • Decrypts AES-GCM  |  ML-KEM-512 | • Decapsulates PQC   |
 | • Symmetric encryption    | ------------>| • Validates schema  | ----------> | • Stores telemetry   |
 | • Raw TCP / Port 5000     |   (Link 1)   | • Encapsulates PQC  |  (Link 2)   |                      |
 | • EOF message framing     |              | • Forwards to cloud |             |                      |
 +---------------------------+              +---------------------+             +----------------------+
```


## 2. Component Roles & Communication Links
**Link 1: Sensor Node to Edge Gateway (Implemented Baseline)**
   * **Medium: Bare TCP socket (port 5000) over a local network.**
   * **Security Scheme: Symmetric AES-128-GCM** authenticated encryption using a 16-byte Pre-Shared Key (PSK).
   * **Message Framing:** Single-shot connection closure (`EOF`). The sensor transmits the packet and immediately closes the socket writer, eliminating the memory overhead of length-prefix decoding on 8-bit hardware.

**Link 2: Edge Gateway to Cloud Service (Post-Quantum Channel - Planned)**
   * **Medium: TCP / TLS or secure HTTP API.**
   * **Security Scheme: ML-KEM-512 Post-Quantum Key Encapsulation Mechanism.**
   * **Role:** The Edge Gateway acts as a security translator, upgrading from low-overhead symmetric encryption to post-quantum-resistant cryptography, before sending the payload over the public Internet to the Cloud Service.


## 3. Temperature Sensor Device Specifications
* Device: Arduino Uno (Microchip ATmega328P 8-bit AVR microcontroller)
* Key Specs:
  * 16 MHz CPU: Single-core
  * 32 KB Flash: Non-volatile program storage holding the compiled machine code
  * 2 KB SRAM: Working memory
* It will give us plain sensor telemetry (e.g., Temperature, Device ID, Timestamp).
* It is a lightweight Python script simulating the payload and packet size.
* No hardware or complex emulators required.
* The device has a memory limit. And ML-KEM-512 requires the use of keys (e.g. a 1,632 bytes secret key), while the device's working memory might need 1000 to 1500 bytes for computations. So this adds up to approximately 3 KB, which exceeds the 2KB SRAM ceiling and cause stack overflow crashes.
* We will use simple lightweight key based encryptions (AES-128 or ChaCha20). The sensor cannot handle anything more complex.
* **Baseline Cryptographic Approach:**
  * Symmetric encryption via **AES-128-GCM**.
  * A 16-byte Pre-Shared Key (PSK) stored in protected Flash memory.
  * A fresh 12-byte **cryptographically secure random nonce prepended to each message to protect confidentiality, i.e. against eavesdropping.**
  * An automated 16-byte GMAC authentication tag appended to the ciphertext to ensure **tamper detection, therefore it protects against tampering/bit-flipping (integrity/authenticity).**
* We will keep the payload output simple as well:
```json
{
  "device_id": "sensor-node-01",
  "timestamp": 1726478400,
  "temperature": 21.8,
  "humidity": 55.4,
  "status": "OK"
}
```


## 4. How to run the system

### Prerequisites
* Python 3.13 or newer
* `uv` package manager installed

### Installation & Environment Setup
From the repository root:
```bash
uv sync
```

### Running the System Simulation
The simulation requires 2 active processes:

1. **Start the Edge Gateway (Terminal 1):**
   ```bash
   uv run python src/edge_gateway.py
   ```
   *Expected output:*
   ```text
   Edge Gateway listening for legacy devices on port 5000...
   ```

2. **Trigger the Legacy Sensor Node (Terminal 2):**
   ```bash
   uv run python src/legacy_device.py
   ```
   *Behavior:* Generates a reading, encrypts the payload, connects to port 5000, transmits the packet, and cleanly closes the connection.

3. **Verify Reception (Terminal 1):**
   The gateway decrypts and prints the authenticated telemetry:
   ```text
   Received from device: {"device_id": "sensor-node-01", "timestamp": 1726478400, "temperature": 21.8, "humidity": 55.4, "status": "OK"}
   ```



## 5. What baseline tests and measurements are there
The baseline implementation is evaluated using 4 automated testing suites and 2 quantitative performance measurement areas:

### 5.1. Functional Unit Tests (`tests/unit/test_legacy_device_and_gateway.py`)
* **Telemetry Schema Integrity:** Verifies all mandatory keys (`device_id`, `timestamp`, `temperature`, `humidity`, `status`) and types match the contract.
* **Cryptographic Round-Trip Interoperability:** Validates that data encrypted by `legacy_device.encrypt_payload` successfully decrypts to identical JSON text in `edge_gateway.decrypt_payload`.
* **Packet Layout Verification:** Verifies the 12-byte random nonce is correctly placed at index `[0:12]`.
* **Edge-Case Payloads:** Tests empty JSON dictionaries (`{}`) and multi-byte UTF-8 Unicode characters (e.g., `åäö`, Chinese characters).

### 5.2. Cryptographic Security & Boundary Tests (`tests/unit/test_security_and_invalid_inputs.py`)
* **Key Mismatch Rejection:** Confirms decryption with an incorrect 16-byte key fails with `InvalidTag`.
* **Tamper Proofing (Bit-Flipping):** Confirms that flipping 1 bit in ciphertext, tag, or nonce raises `InvalidTag` and rejects the payload.
* **Type & Length Validation:** Confirms exceptions are raised when passing invalid key lengths (e.g., 15 bytes), non-byte types, or non-serializable objects.
* **Truncation Defense:** Confirms packets shortened by 1, 8, or 16 bytes fail GMAC tag verification.

### 5.3. TCP Protocol & Integration Tests (`tests/integration/test_gateway_tcp_flow.py`)
* **End-to-End TCP Transmission:** Tests real socket delivery from client to listening gateway on an isolated loopback port.
* **TCP Stream Chunking & Fragmentation:** Verifies that a packet sent in fragmented segments (1 byte + 12 bytes + remainder) is correctly accumulated and parsed across `conn.recv()` boundaries.

### 5.4. Robustness & Acceptance Tests (`tests/integration/test_gateway_failure_and_robustness.py`)
* **Gateway Fault Tolerance:** Confirms the gateway process does not crash when encountering malformed packets, truncated data, or empty connections.
* **Replay Attack Rejection:** Ensures identical replayed packets are detected and discarded.
* **Schema Conformance:** Rejects authenticated payloads missing required telemetry fields.
* **Buffer Overflow Handling:** Verifies the gateway dynamically handles payloads larger than the initial 1,024-byte buffer.

### 5.5. Baseline Measurements
* **Wire Protocol Overhead:** 
  * Plaintext JSON payload: approximately 95 bytes.
  * Total Encrypted packet: 12-byte nonce + 95-byte ciphertext + 16-byte GMAC tag = 123 bytes.
  * Exact cryptographic overhead: **28 bytes** (constant).
* **Network Overhead 0 bytes:**
  * Raw TCP + EOF framing avoids HTTP headers (which add approximately 200–500 extra bytes per request) and WebSocket handshakes, preserving sensor battery life.


## 6. How to run baseline tests and measurements

### 6.1. Running the Automated Test Suite
Ensure the test dependencies (`pytest`) are installed, then execute:

```bash
# Run all unit and integration tests
uv run pytest -v

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only network integration tests
uv run pytest tests/integration/ -v
```

### 6.2. Baseline Test Results & Gap Analysis of Current Limitations

Execution of the full test suite (`pytest`) gave us **27 passing tests** and **6 failing tests**:

```text
=========================== short test summary info ============================
FAILED tests/integration/test_gateway_failure_and_robustness.py::test_gateway_remains_available_after_malformed_nonempty_packet
FAILED tests/integration/test_gateway_failure_and_robustness.py::test_gateway_remains_available_after_connection_closes_mid_packet
FAILED tests/integration/test_gateway_failure_and_robustness.py::test_gateway_remains_available_after_two_packets_share_one_connection
FAILED tests/integration/test_gateway_failure_and_robustness.py::test_gateway_rejects_authenticated_non_json_payload_and_processes_valid_packet
FAILED tests/integration/test_gateway_failure_and_robustness.py::test_gateway_rejects_wrong_telemetry_schema_and_processes_valid_packet
FAILED tests/integration/test_gateway_failure_and_robustness.py::test_gateway_rejects_replayed_packet_and_processes_new_valid_packet
========================= 6 failed, 27 passed in 6.46s =========================
```

**Analysis of Current Baseline Limitations:**
1. **Lack of Gateway Recovery Boundary (Crash on Bad Input):**
   * Currently, `edge_gateway.py` does not wrap packet decryption in a `try...except` block.
   * If an invalid, malformed, or truncated packet arrives, `aesgcm.decrypt()` raises `InvalidTag`, which causes the entire gateway process to terminate. Subsequent legitimate clients are rejected.
2. **Missing Application Schema Validation:**
   * **The gateway** assumes any successfully decrypted UTF-8 string is valid telemetry. It does not validate required JSON fields (`temperature`, `humidity`, etc.) before processing.
3. **Vulnerability to Replay Attacks:**
   * **The gateway does not track observed nonces or enforce incremental timestamps.** An attacker intercepting an authenticated packet can replay it, and the gateway will process it as fresh telemetry.

**Planned Improvements**
* Implement an exception handling boundary in `edge_gateway.py` to log bad packets and continue listening.
* Add JSON schema validation on the decrypted payload.
* Add nonce/timestamp cache to detect and reject replayed packets.



### 6.3. Verifying Cryptographic Tampering Manually
To visually observe AES-GCM detecting a modified byte in the terminal (i.e. detecting unauthorized modification):
```bash
uv run python -c "
import legacy_device, edge_gateway
payload = legacy_device.generate_telemetry()
packet = bytearray(legacy_device.encrypt_payload(payload, legacy_device.PRE_SHARED_KEY))
packet[15] ^= 0xFF  # Corrupt one byte of ciphertext
try:
    edge_gateway.decrypt_payload(bytes(packet), legacy_device.PRE_SHARED_KEY)
except Exception as e:
    print('Tamper detected successfully:', type(e).__name__)
"
```

### 6.4. Measuring Packet Overhead (To prove Section 5.5. Baseline Measurements)
To inspect the exact byte sizes in your console:
```bash
uv run python -c "
import json, legacy_device
raw = json.dumps(legacy_device.generate_telemetry()).encode('utf-8')
enc = legacy_device.encrypt_payload(legacy_device.generate_telemetry(), legacy_device.PRE_SHARED_KEY)
print(f'Plaintext Size:  {len(raw)} bytes')
print(f'Wire Packet:     {len(enc)} bytes (Nonce: 12, Tag: 16, Overhead: 28 bytes)')
"
```


