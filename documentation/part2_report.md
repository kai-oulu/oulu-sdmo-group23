# Post-Quantum Cryptography Transition from an Organisation Information/Cyber Security Perspective

**Perspective 3: Information security and organizational cybersecurity**  
**Course:** Oulu Software DEV-Maintenance-Ops - Group 23  
**Members:** Kaiquan Mah | Quoc Nguyen | Danish Sharjeel | Manh Nguyen | Kim Nguyen  
**Note:** This report is written from the perspective of someone not from a Computer Science background. Technical details from `part1_documentation.md` are summarised using simpler language where possible  
**Repository is accessible from:** https://github.com/kai-oulu/oulu-sdmo-group23/tree/main

---

## 1. Summary: Quantum is a Business Risk Today

Quantum computers will break RSA and elliptic-curve cryptography that protects internet traffic today. The threat is not something in the future when quantum computing is usable everywhere. Instead the threat is happening now based on a "harvest now, decrypt later" concept, where  attackers can gather encrypted data now (like taking our locked safe) and open it later when quantum computers can pick our old locks.

NIST published a quantum standard FIPS 203 ML-KEM (Module-Lattice-based Key Encapsulation Mechanism) in August 2024 [1]. ML-KEM is described as a quantum-safe lock that even quantum computers cannot pick. It comes in 3 strengths: ML-KEM-512 (~AES-128 security, Category 1), 768 (~AES-192, Category 3), 1024 (~AES-256, Category 5) [1][2].

For organizations with thousands of low-cost sensors, they cannot replace all their sensor devices overnight. EU and CISA both recommend a hybrid deployment: keep legacy sensor devices running while adding PQC (Post-Quantum Cryptography) on internet-facing links, with fallbacks to ensure compatibility with legacy sensor devices [3][5]. Migration will take **10-20 years** for organizations that use alot of sensor devices [3].

Our group's system (in the [GitHub repo](https://github.com/kai-oulu/oulu-sdmo-group23/tree/main)) is a minimal but working example of this hybrid deployment approach: legacy sensors retain the lightweight AES encryption method when communicating with the edge gateway, and the edge gateway communicates with the cloud service protected Post-Quantum Cryptography, with a SQLite database for analytics and fallback logging via files for business continuity. It shows how an organization can start now and migrate to using Post-Quantum Cryptography without disrupting operations.

---

## 2. Why Legacy Matters: 2KB RAM Cannot Do PQC (Post-Quantum Cryptography)

Our baseline sensor device simulates **ATmega328P** (Arduino Uno): 16 MHz, 32KB Flash, **2KB SRAM** working memory. It sends telemetry JSON ~95B, encrypted via AES-128-GCM with 16B pre-shared key `legacy_secret_16`, 12B random nonce prepended, wire packet ~123B, overhead 28B (12 nonce + 16 tag), 0B HTTP overhead via raw TCP + EOF framing [4].

ML-KEM-512 needs **secret key 1632B** plus **1000-1500B workspace** for polynomial operations = ~3KB total, exceeding 2KB SRAM → stack overflow and crash [4]. This is not unique to our simulation - many real-world low-cost IoT devices (LoRaWAN, Zigbee, BLE) have similar constraints and cannot be upgraded to Post-Quantum Cryptography without hardware replacement [4].

**Implication for organization:** You cannot push a firmware update to make old sensors quantum-safe. EU roadmap shares that hybrid-PQC ciphers/certificates are needed for legacy compatibility and hardware replacement may be required [3]. Forcing Post-Quantum Cryptography onto 2KB devices would exhaust RAM and battery.

**Our solution (offload pattern):** Keep Link1 unchanged between legacy sensor device and the edge gateway (no firmware update). Let **edge gateway (Linux/Raspberry Pi)** act as the secure intermediary - it has enough RAM, decrypts AES-GCM, validates schema of the data received from the sensor, checks that the sensor data was not part of a replay attack, then re-encrypts for sending to the cloud service via Post-Quantum Cryptography [4]. This pattern is recommended for resource-constrained sensor devices [4].

---

## 3. Organization Migration Approach

CISA's Post-Quantum Cryptography initiative shares a phased, risk-based migration, not a sudden replacement [5]:

1. **Inventory:** List all systems performing cryptography - including hidden IoT sensors, gateways, cloud APIs. Most organizations discover 60-80% more cryptography use than expected (inventory challenge).
2. **Risk assessment:** Identify data with long secrecy lifetime (medical, financial, critical infrastructure telemetry) at risk from the "harvest now, decrypt later" concept [5].
3. **Approach:** Prioritize internet-facing communication links first (e.g. gateway to cloud communication links), then internal communication links. EU recommends a hybrid approach to keep legacy sensor devices working during the transition [3].
4. **Hybrid migration:** Deploy Post-Quantum Cryptography alongside traditional cryptography, with a fallback for backward compatibility. If Post-Quantum Cryptography fails, fallback avoids bringing the whole system down, which is very important for business continuity [5].
5. **Supply chain:** Work with vendors to ensure new sensor devices are PQC-capable. CISA's product categories list (Jan 2026) now prioritizes PQC-capable products in procurement [5].

EU roadmap adds: expect **10-20 years** for full migration in large organizations, need vendor cooperation, and need to plan for constrained radio overhead [3].

**Cost lens for executives:** Replacing 10,000 sensors at €50 each = €500k + installation + downtime. Hybrid offload lets you keep old sensors running while new PQC-capable devices (e.g., ESP32 with >8KB SRAM) are phased in.

---

## 4. Our Phased Strategy as an Organization Example

We implemented a hybrid strategy which CISA/EU recommend, to show that the hybrid strategy is feasible:

**Phase 1 - Legacy Only (Baseline, 27/33 tests passed):**
- Link1: Legacy → Gateway AES-128-GCM PSK, TCP 5000, EOF
- Link2: No Post-Quantum Cryptography. Plaintext only
- Risk: "harvest now, decrypt later" is possible on internet-facing edge gateway and cloud service communications, if the communications is via the public internet [5]

**Phase 2 - Hybrid Approach (Current Build, 33/33 tests passed):**
- **Link1 Between Legacy Sensor Device to Edge Gateway unchanged:** Legacy devices keep same PSK/Pre-Shard Key. This preserves our legacy sensor devices and keeps them working until they are ready to migrate to Post-Quantum Cryptography.
- **Edge Gateway:** After validating telemetry data received from sensor device, gateway loads the public key and encapsulates the data.
- **Why ML-KEM-512:** Lowest overhead 800B pk + 768B ct = 1568B vs 2272B for 768 [2]. Offers around 128-bit security, sufficient for short-lived telemetry (with a life of minutes/hours). If long-term confidentiality is needed (e.g. in medical domain), we should use ML-KEM 768 [1].
- **Cloud Service:** Decapsulates the data, AES-GCM decrypts, inserts data into SQLite database. Analytics is performed on the SQLite database via health checks and querying for aggregated metrics [2].
- **Fallback ensures availability:** If the public key is missing or the cloud service is unreachable (e.g. TCP 6000 refused/timeout), the edge gateway will log sensor data and metrics to the `gateway_fallback.log`. This offers business continuity following CISA's hybrid approach guidelines [5]. The IT team can use the logs to do a replay later - so there is no data loss.
- **Operational suitability:** CI-CD via GitHub actions, and managing libraries via `uv`, Dockerfile for reproducible environments taking into account our library dependencies from `uv`.

**Phase 3 - Future PQC-Capable Devices:**
- New devices with >8KB SRAM (ESP32, Raspberry Pi Pico) could run ML-KEM-512 directly
- Edge Gateway supports both old PSK/Pre-Shared Key and new PQC/Post-Quantum Cryptography devices
- File-based pk/public key will be replaced by KMS(Key Management Service)/certificate, add TLS 1.3 with PQC certs
- Requires sensor device hardware replacements [3][5]


---


## 5. Risks & Conclusion: Start Preparing Your Inventory Now

**Compliance Requirements:** CISA's product categories list (Jan 2026) prioritizes PQC-capable products. So procurement should require ML-KEM support for sensor devices [5]. EU's roadmap requires organizations to prepare an inventory of all systems performing cryptography [3].

**Cost & Timeline:** Full migration of around 10 to 20 years for organizations with alot of sensor devices, where timeline might be long also because sensors might be found numerous faraway locations [3][5]. Start preparing a systems inventory now, then adopt a hybrid approach (like our Phase 2 approach above) to protect internet-facing communications links without disrupting legacy devices. Then plan for a sensor device hardware refresh to PQC-capable devices.

**Key Actions:**
1. **Inventory** of all cryptography-performing systems now (including hidden IoT/sensor devices). Organizations likely have 60-80% more than they think [3]
2. **Adopt a hybrid migration approach** with fallback - This keeps legacy sensor devices running, while add Post-Quantum Cryptography on internet-facing communication links, to ensure business continuity [5]
3. **Measure PQC observability metrics**: For example, track PQC encapsulation/decapsulation times (in millisecond), success rate, fallback rate, via health checks and analytics on the database collecting your sensor data and metrics.
4. **Plan key management upgrades** (e.g. implement per-device subkeys, sign primary key/pk file, key management system/KMS, key rotation) **and hardware replacement budget**

As part of group 23, the system we created demonstrates that even a small team with LLM assistance can build a working hybrid Post-Quantum Cryptography system, with tests passing, and metrics on the sensor data and health checks, with fallback to ensure backward compatibility with legacy sensor devices availability. So this proejct proves that the organization transition to Post-Quantum Cryptography is feasible if organizations started now.

---

## References

- [1] NIST FIPS 203 ML-KEM standardised in August 2024 - https://www.encryptionconsulting.com/education-center/ml-kem-fips-203/
- [2] ML-KEM sizes: 800B pk (public key / encapsulation key), 768B ct (ciphertext) - https://vucense.com/privacy-sovereignty/post-quantum-cryptography/ml-kem-fips-203-implementation-guide-2026/
- [3] EU roadmap, hybrid for legacy, hardware replacement may be needed - https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/
- [4] Legacy constraints, computational overhead - https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems
- [5] CISA PQC initiative, phased migration - https://www.cisa.gov/topics/risk-management/quantum

