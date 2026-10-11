# Module Implementation Guide: Legacy Link Baseline

This document covers the installation, execution steps, and code explanation for the communication channel between the **Legacy Device** and the **Edge Gateway**.

---

## 1. Environment Setup & Prerequisites

This project uses `uv` as the fast Python package manager.

### Prerequisites

* Python 3.13 or newer
* `uv` installed (`curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh` or via package manager)

### Dependency Installation

Ensure you are in the project root directory (`oulu-sdmo-group23/`).

1. Add the core cryptographic dependency:
```bash
uv add cryptography

```


2. Synchronize the environment:
```bash
uv sync

```



---

## 2. How to Run the Simulation

The simulation requires two separate terminal windows because `edge_gateway.py` acts as a continuous listener, while `legacy_device.py` runs as an ephemeral client.

### Terminal 1: Start the Edge Gateway

Run the gateway first so it binds to the port and awaits incoming data:

```bash
uv run python src/edge_gateway.py

```

*Expected output:*

```text
Edge Gateway listening for legacy devices on port 5000...

```

### Terminal 2: Run the Legacy Device

In a new terminal window, execute the simulated sensor node:

```bash
uv run python src/legacy_device.py

```

*Expected behavior:*

* The script generates the telemetry payload, encrypts it, transmits it via TCP, closes the connection, and terminates cleanly.



### Observe the Output

Switch back to **Terminal 1** (Edge Gateway). You will see the decrypted data printed to the console:

```text
Received from device: {"device_id": "sensor-node-01", "timestamp": 1726478400, "temperature": 21.8, "humidity": 55.4, "status": "OK"}

```

---

## 3. Detailed Code Walkthrough

### 3.1 `src/legacy_device.py`

This script simulates an embedded sensor node (such as an ATmega328P profile).

---

### 3.2 `src/edge_gateway.py`

This script acts as the edge ingestion server, receiving symmetric data and parsing it.

---

## 4. Architectural Notes

* **Packet Framing:** TCP does not have inherent message boundaries. Instead of adding complex byte-length headers, message boundary detection is achieved via socket closure (`EOF`). This keeps the legacy device code minimal and avoids buffer framing errors.
* **Security Model:** AES-128-GCM is an AEAD (Authenticated Encryption with Associated Data) scheme. It prevents both eavesdropping (confidentiality) and tampering/bit-flipping (integrity/authenticity) on the legacy link.