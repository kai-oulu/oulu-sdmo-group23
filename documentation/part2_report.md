# Post-Quantum Cryptography Transition from an Organisation Information/Cyber Security Perspective

**Perspective 3: Information security and organizational cybersecurity**  
**Course:** Oulu Software DEV-Maintenance-Ops - Group 23  
**Members:** Kaiquan Mah | Quoc Nguyen | Danish Sharjeel | Manh Nguyen | Kim Nguyen  
**Note:** This report is written from the perspective of someone not from a Computer Science background. Technical details from `part1_documentation.md` are summarised using simpler language where possible  
**Repository is accessible from:** https://github.com/kai-oulu/oulu-sdmo-group23/tree/main

---

## 1. Summary: Quantum is a Business Risk Today

Quantum computers will break RSA and elliptic-curve cryptography that protects internet traffic today. The threat is not something in the future when quantum computing is usable everywhere. Instead the threat is happening now based on a "harvest now, decrypt later" concept, where attackers can gather encrypted data now (like taking our locked safe) and open it later when quantum computers can pick our old locks [5].

NIST published a quantum standard FIPS 203 ML-KEM (Module-Lattice-based Key Encapsulation Mechanism) in August 2024 [1]. ML-KEM is described as a quantum-safe lock that even quantum computers cannot pick. It comes in 3 strengths: ML-KEM-512 (~AES-128 security, Category 1), 768 (~AES-192, Category 3), 1024 (~AES-256, Category 5) [1][2].

For organizations with thousands of low-cost sensors, they cannot replace all their sensor devices overnight. EU and CISA both recommend a hybrid deployment: keep legacy sensor devices running while adding PQC (Post-Quantum Cryptography) on internet-facing links, with fallbacks to ensure compatibility with legacy sensor devices [3][5]. Migration will take **10-20 years** for organizations that use alot of sensor devices [3].

If your data needs **5+ years of confidentiality** (medical records, IP, financial, government secrets), migration is already overdue. EU notes with CRQC (cryptographically relevant quantum computer) predicted by 2030, if cover time is 5 years or more, it is already too late for many to move in time [3]. For such data, "harvest now, decrypt later" means traffic captured today can be decrypted retroactively once quantum arrives [2].

**What is cover time? (simple explanation for non-CS):**
- **Cover time = how long you need your data to stay secret.** Think of it as expiry date for confidentiality.
  - Medical record: needs 20+ years secret (patient privacy law)
  - Bank transaction / trade secret / IP: 7-10 years
  - Sensor telemetry for factory: maybe 1-2 years (short-lived)
  - Government secret: 25+ years
- **Why it matters with quantum:** Attacker can do "harvest now, decrypt later" — they don't need quantum computer today. They just **record your encrypted traffic now** (like copying a locked safe) and **store it**. When quantum computer arrives in 2030 that can pick old RSA/ECC locks, they **open the safe and read the old data** [2][5].
- **Example timeline:** Today is 2026. You send medical data encrypted with RSA. Attacker records it. Quantum computer arrives 2030 (4 years later). If that medical data needs 20 years cover time (until 2046), attacker in 2030 can decrypt data that should have stayed secret until 2046 — **16 years too early**. So even though quantum is 4 years away, your 20-year data is already at risk today [3].
- **Rule of thumb for executives:** `If (cover time + migration time) > (time until CRQC)`, you are already late. Migration itself takes 10-20 years [3], so if CRQC by 2030 (4 years away) and migration takes 10 years, any data needing >0 years confidentiality is at risk. That's why CISA says start inventory now [5].
- **Our system example:** Our temperature telemetry maybe needs 1-2 years cover time (short-lived) — so 512-bit (~AES-128) is enough [1]. But if same system collected health data, we should use ML-KEM-768 or 1024 for longer cover time [1][2].

Our group's system (in the [GitHub repo](https://github.com/kai-oulu/oulu-sdmo-group23/tree/main)) is a minimal but working example of this hybrid deployment approach: legacy sensors retain the lightweight AES encryption method when communicating with the edge gateway, and the edge gateway communicates with the cloud service protected by Post-Quantum Cryptography, with a SQLite database for analytics and fallback logging via files for business continuity. It shows how an organization can start now and migrate to using Post-Quantum Cryptography without disrupting operations.

---

## 2. Why Legacy Matters: 2KB RAM Cannot Do PQC (Post-Quantum Cryptography)

Our baseline sensor device simulates **ATmega328P** (Arduino Uno): 16 MHz, 32KB Flash, **2KB SRAM** working memory. It sends telemetry JSON ~95B, encrypted via AES-128-GCM with 16B pre-shared key `legacy_secret_16`, 12B random nonce prepended, wire packet ~123B, overhead 28B (12 nonce + 16 tag), 0B HTTP overhead via raw TCP + EOF framing [4].

ML-KEM-512 needs **secret key 1632B** plus **1000-1500B workspace** for polynomial operations = ~3KB total, exceeding 2KB SRAM → stack overflow and crash [4]. This is not unique to our simulation - many real-world low-cost IoT devices (LoRaWAN, Zigbee, BLE) have similar constraints and cannot be upgraded to Post-Quantum Cryptography without hardware replacement [4]. PQC also introduces larger key sizes and increased processing power compared to classical crypto, and existing protocols assume specific key sizes that PQC exceeds, requiring protocol modifications [4].

**Implication for organization:** You cannot push a firmware update to make old sensors quantum-safe. EU roadmap shares that hybrid-PQC ciphers/certificates are needed for legacy compatibility and hardware replacement may be required [3]. Forcing Post-Quantum Cryptography onto 2KB devices would exhaust RAM and battery. Many legacy low-cost IoT devices may not support PQC at all, necessitating hardware replacements in some cases [3].

**Our solution (offload pattern):** Keep Link1 unchanged between legacy sensor device and the edge gateway (no firmware update). Let **edge gateway (Linux/Raspberry Pi)** act as the secure intermediary - it has enough RAM, decrypts AES-GCM, validates schema of the data received from the sensor, checks that the sensor data was not part of a replay attack, then re-encrypts for sending to the cloud service via Post-Quantum Cryptography [4]. This pattern is recommended for resource-constrained sensor devices [4]. Gateway measures encaps ~0.03ms Rust / 0.82ms pure Python, decaps ~0.04ms / 1.46ms — negligible for gateway, but would be heavy for battery-powered sensor.

---

## 3. Organization Migration Approach

CISA's Post-Quantum Cryptography initiative shares a phased, risk-based migration, not a sudden replacement [5]:

1. **Inventory:** List all systems performing cryptography - including hidden IoT sensors, gateways, cloud APIs. Most organizations discover 60-80% more cryptography use than expected (inventory challenge). **Include non-production:** internal APIs, test/dev platforms are often overlooked and frequently targeted precisely because they lag behind in security [3]. EU emphasizes first mapping and creating an inventory of cryptographic systems [3]. CISA recommends **Automated Cryptographic Discovery and Inventory (ACDI) Tools** to automate this [5]. Maintaining a detailed cryptographic asset register is essential to assess risk at each endpoint [3].

2. **Risk assessment:** Identify data with long secrecy lifetime (medical, financial, critical infrastructure telemetry) at risk from the "harvest now, decrypt later" concept [5]. **Use cover time to prioritize:** List each data type, ask "how many years must this stay secret?" — medical 20y, financial 7-10y, IP 10y, telemetry 1-2y. If cover time extends beyond 2030 (predicted CRQC), that data is already at risk from traffic captured today [2][3]. Example: medical record sent in 2026 needs secrecy until 2046 (20y cover time). Attacker records encrypted traffic in 2026, decrypts in 2030 with quantum, reads data 16 years before it should be public. So prioritize long cover time data first [3].

3. **Approach:** Prioritize internet-facing communication links first (e.g. gateway to cloud communication links), then internal communication links. EU recommends a hybrid approach to keep legacy sensor devices working during the transition [3]. **TLS 1.3 should be first step** as it provides necessary foundation for future PQC support [3].

4. **Hybrid migration:** Deploy Post-Quantum Cryptography alongside traditional cryptography, with a fallback for backward compatibility. If Post-Quantum Cryptography fails, fallback avoids bringing the whole system down, which is very important for business continuity [5]. Both EU and NIST advise **hybrid-PQC ciphers and hybrid digital certificates** — hybrid provides security of new PQC while allowing legacy devices that do not support PQC to continue using classical crypto [3]. This requires both ends (browser/server, IoT device/cloud) to support same algorithms [3].

5. **Supply chain:** Work with vendors to ensure new sensor devices are PQC-capable. CISA's product categories list (Jan 2026) now prioritizes PQC-capable products in procurement [5]. CISA develops and regularly updates this list via EO 14306 [5].

EU roadmap adds: expect **10-20 years** for full migration in large organizations, need vendor cooperation, and need to plan for constrained radio overhead [3]. The web has seen most rapid progress: **hybrid-PQC ciphers already adopted in 8.6% of world's top 1M websites**, but hybrid-PQC certificates still early stages [3] — shows migration is feasible and already started.

**Cost lens for executives:** Replacing 10,000 sensors at €50 each = €500k + installation + downtime. Hybrid offload lets you keep old sensors running while new PQC-capable devices (e.g., ESP32 with >8KB SRAM) are phased in.

---

## 4. Our Phased Strategy as an Organization Example

We implemented a hybrid strategy which CISA/EU recommend, to show that the hybrid strategy is feasible:

**Phase 1 - Legacy Only (Baseline, 27/33 tests passed):**
- Link1: Legacy → Gateway AES-128-GCM PSK, TCP 5000, EOF
- Link2: No Post-Quantum Cryptography. Plaintext only
- Risk: "harvest now, decrypt later" is possible on internet-facing edge gateway and cloud service communications, if the communications is via the public internet [5]

**Phase 2 - Hybrid Approach (Current Build, 33/33 tests passed):**
- **Link1 Between Legacy Sensor Device to Edge Gateway unchanged:** Legacy devices keep same PSK/Pre-Shared Key. This preserves our legacy sensor devices and keeps them working until they are ready to migrate to Post-Quantum Cryptography.
- **Edge Gateway:** After validating telemetry data received from sensor device, gateway loads the public key `cloud_public_key.bin` 800B [2] and encapsulates. Wire format `ct(768)||nonce(12)||aes_ct` ~845B total [2]. This is exactly the hybrid pattern: KEM establishes 32B shared secret `ss` without transmitting it directly (Module-LWE hardness), then AES-256-GCM encrypts actual data [2].
- **Why ML-KEM-512:** Lowest overhead 800B pk + 768B ct = 1568B vs 2272B for 768 (1184+1088) vs 3136B for 1024 (1568+1568) [2]. Offers around 128-bit security, sufficient for short-lived telemetry (minutes/hours). **2026 recommendation is ML-KEM-768 as default** — balances strong security and reasonable sizes, TLS hybrid group **X25519MLKEM768** uses it [2]. Choose **ML-KEM-1024 if you need longer-term margin or must follow NSA CNSA 2.0**, which requires 1024 for national security systems [2]. If long-term confidentiality is needed (medical), we should use 768 [1]. We chose 512 for minimal viable gateway (Linux/Pi) — encaps 0.03ms Rust / 0.82ms pure Python, decaps 0.04ms / 1.46ms [2].
- **Cloud Service:** Decapsulates `ss = ML-KEM.decaps(dk, ct)`, AES-GCM decrypts, inserts into SQLite `telemetry.db`. Analytics via health 6001: `db_rows`, `COUNT`, `AVG(temperature/humidity)`, `last 10`, `decaps_ok/fail`, `success_rate`, `avg_decaps_ms` [2].
- **Fallback ensures availability:** If public key missing or cloud unreachable (TCP 6000 refused/timeout), gateway logs to `gateway_fallback.log` `<timestamp> <json>` + `fallback_local++`, `cloud_fail++`. This offers business continuity per CISA hybrid guidance [5]. IT team can replay log later — no data loss. Cloud decaps fail → `decaps_fail++` but stays alive.
- **Operational suitability:** CI via `astral-sh/setup-uv` reading `.python-version` 3.13 + `uv.lock`, `uv sync --frozen --all-groups`, pytest 33/33, `pqc_utils.py` round-trip, Dockerfile `python:3.13-slim` + `uv sync --frozen --no-install-project` respects lock, compose with `depends_on healthy`, volume `pqc-shared`, logging file-only to keep tests clean.

**Phase 3 - Future PQC-Capable Devices:**
- New devices with >8KB SRAM (ESP32, Raspberry Pi Pico) could run ML-KEM-512 directly
- Edge Gateway supports both old PSK and new PQC devices (negotiation)
- File-based pk will be replaced by KMS/certificate, add TLS 1.3 with PQC certs (TLS 1.3 foundation [3])
- Requires hardware replacements, 10-20y timeline [3][5]

---

## 5. Risks & Conclusion: Start Preparing Your Inventory Now

**Compliance Requirements:** CISA product categories list (Jan 2026) prioritizes PQC-capable products — procurement should require ML-KEM support [5]. EU roadmap requires inventory of all crypto systems [3]. **EU roadmap is more than advice — it will be enforced** through directives/regulations. PQC not explicitly in GDPR, but GDPR, NIS2 (2022), Cyber Resilience Act (2024) take risk-based approach requiring up-to-date policies and industry best practices [3]. NIST guidance more explicit about protocols but doesn't enforce — up to regulators to adopt [3].

**Enforcement timeline:** Both EU and NIST recommend **non-PQC encryption removed by 2030 for critical systems, all others by 2035** [3]. With CRQC predicted by 2030 by many, organizations with 5+ year cover time are already late [3].

**Market maturity:** Hybrid-PQC ciphers already in **8.6% of top 1M websites** [3], native ML-KEM in **OpenSSL 3.5+ (April 2025)**, deployed in Chrome/Firefox hybrid TLS [2] — migration has started, feasible now.

**Cost & Timeline:** Full migration 10-20 years for orgs with many sensors, especially when sensors are in faraway locations [3][5]. Start inventory now, adopt hybrid (Phase 2) to protect internet-facing links without disrupting legacy, plan hardware refresh to PQC-capable devices.

**Key Actions:**
1. **Inventory** all crypto now (including hidden IoT, non-prod internal APIs, test/dev) — likely 60-80% more than you think [3]. Use automated discovery tools like CISA ACDI [5].
2. **Adopt hybrid with fallback** — keep legacy running, add PQC on internet-facing links, ensure business continuity [5]. Both ends must support same algorithms [3]. TLS 1.3 first step [3].
3. **Measure PQC observability**: Track encaps/decaps ms, `success_rate = decaps_ok/(ok+fail)`, `fallback_local`, via health 6001/5001 and DB analytics — KPIs for migration progress.
4. **Plan key management upgrades** (per-device subkeys, sign pk file, KMS, rotation) and hardware replacement budget. Choose param set based on data lifetime: 512 for short-lived telemetry, 768 default [2], 1024 for NSA CNSA 2.0 national security [2].

As Group 23, our system demonstrates that even a small team with LLM assistance can build a working hybrid PQC system (33/33 tests, SQLite analytics, fallback for legacy availability) — proving organizational transition is feasible if started now, before 2030 deadline [3].

---

## References

- [1] NIST FIPS 203 ML-KEM standardised in August 2024 - https://www.encryptionconsulting.com/education-center/ml-kem-fips-203/
- [2] ML-KEM sizes: 800B pk (public key / encapsulation key), 768B ct (ciphertext) - https://vucense.com/privacy-sovereignty/post-quantum-cryptography/ml-kem-fips-203-implementation-guide-2026/
- [3] EU roadmap, hybrid for legacy, hardware replacement may be needed - https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/
- [4] Legacy constraints, computational overhead - https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems
- [5] CISA PQC initiative, phased migration - https://www.cisa.gov/topics/risk-management/quantum
