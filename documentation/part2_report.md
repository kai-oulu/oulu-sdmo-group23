# Post-Quantum Cryptography Transition from an Organisation Information/Cyber Security Perspective

**Perspective 3: Information security and organizational cybersecurity**  
**Course:** Oulu Software DEV-Maintenance-Ops — Group 23  
**Members:** Kaiquan Mah | Quoc Nguyen | Danish Sharjeel | Manh Nguyen | Kim Nguyen  
**System reference:** Hybrid Traditional & Post-Quantum Cryptography Compatible Sensor-EdgeGateway-Cloud System (Link1 AES-128-GCM PSK legacy, Link2 ML-KEM-512 hybrid PQC)

> **Audience note:** This report is written for C-suite/managers, non-CS background. Technical details from `part1_documentation.md` are summarized in business-risk language with public citations [1]-[5].

---

## 1. Executive Summary: Quantum is a Business Risk Today, Not in 10 Years

Quantum computers will break RSA and elliptic-curve cryptography that protects internet traffic today. The threat is not future — it is **harvest-now-decrypt-later**: attackers steal encrypted data now (like stealing a locked safe) and plan to open it later when quantum computers can pick the old lock [5].

NIST finalized the first post-quantum standard **FIPS 203 ML-KEM** (Module-Lattice-based Key Encapsulation Mechanism, based on CRYSTALS-Kyber) in August 2024 [1]. ML-KEM is described as a quantum-safe lock that even quantum computers cannot pick. It comes in three strengths: ML-KEM-512 (~AES-128 security, Category 1), 768 (~AES-192, Category 3), 1024 (~AES-256, Category 5) [1][2].

For organizations with thousands of low-cost sensors, you cannot replace all devices overnight. EU and CISA both recommend **hybrid deployment**: keep legacy running while adding PQC on internet-facing links, with fallback to ensure availability [3][5]. Migration will take **10-20 years** for large fleets [3].

Our Group 23 system is a minimal but working example of this hybrid strategy: legacy sensors stay on lightweight AES, gateway translates to PQC for cloud, with SQLite analytics and fallback log for business continuity. It shows how an organization can start now without disrupting operations.

---

## 2. Why Legacy Matters: 2KB RAM Cannot Do PQC

Our baseline device simulates **ATmega328P** (Arduino Uno): 16 MHz, 32KB Flash, **2KB SRAM** working memory. It sends telemetry JSON ~95B, encrypted via AES-128-GCM with 16B pre-shared key `legacy_secret_16`, 12B random nonce prepended, wire packet ~123B, overhead 28B (12 nonce + 16 tag), 0B HTTP overhead via raw TCP + EOF framing [4].

ML-KEM-512 needs **secret key 1632B** plus **1000-1500B workspace** for polynomial operations = ~3KB total, exceeding 2KB SRAM → stack overflow and crash [4]. This is not unique to our simulation — many real low-cost IoT devices (LoRaWAN, Zigbee, BLE) have similar constraints and cannot be upgraded to PQC without hardware replacement [4].

**Implication for organization:** You cannot push a firmware update to make old sensors quantum-safe. EU roadmap explicitly states hybrid-PQC ciphers/certificates are needed for legacy compatibility and hardware replacement may be required [3]. Forcing PQC onto 2KB devices would exhaust RAM and battery.

**Our solution (offload pattern):** Keep Link1 unchanged (no firmware update). Let **edge gateway (Linux/Raspberry Pi)** act as security translator — it has enough RAM, decrypts AES-GCM, validates schema (`device_id, timestamp, temperature, humidity, status`), checks replay (`seen_nonces=set()`), then re-encrypts for cloud via PQC [4]. This pattern is recommended for constrained IoT [4].

---

## 3. Organizational Migration Roadmap: What CISA and EU Tell Executives

CISA PQC initiative outlines a phased, risk-based migration, not a big-bang replacement [5]:

1. **Inventory:** List all systems performing cryptography — including hidden IoT sensors, gateways, cloud APIs. Most organizations discover 60-80% more crypto use than expected (inventory challenge).
2. **Risk assessment:** Identify data with long secrecy lifetime (medical, financial, critical infrastructure telemetry) at risk from harvest-now-decrypt-later [5].
3. **Roadmap:** Prioritize internet-facing links first (gateway→cloud), then internal. EU recommends hybrid approach to keep legacy working during transition [3].
4. **Hybrid migration:** Deploy PQC alongside classical crypto, with fallback. If PQC fails, system degrades gracefully, not total outage — critical for business continuity [5].
5. **Supply chain:** Work with vendors to ensure new devices are PQC-capable. CISA product categories list (Jan 2026) now prioritizes PQC-capable products in procurement [5].

EU roadmap adds: expect **10-20 years** for full migration in large organizations, need vendor cooperation, and need to plan for constrained radio overhead [3].

**Cost lens for executives:** Replacing 10,000 sensors at €50 each = €500k + installation + downtime. Hybrid offload lets you keep old sensors running while new PQC-capable devices (e.g., ESP32 with >8KB SRAM) are phased in.

---

## 4. Our Phased Strategy as a Concrete Organizational Example

We implemented exactly the hybrid strategy CISA/EU recommend, in 4 hours with LLM assistance, to show feasibility:

**Phase 0 — Legacy Only (Baseline, 27/33 tests):**
- Link1: Legacy → Gateway AES-128-GCM PSK, TCP 5000, EOF
- Link2: not PQC or plaintext
- Risk: harvest-now-decrypt-later on internet-facing Link2 if it goes over public internet [5]

**Phase 1 — Hybrid Offload (Current, 33/33 tests, minimal viable):**
- **Link1 unchanged:** Legacy devices keep same PSK, same 12B nonce, same EOF — zero disruption. This preserves investment.
- **Gateway as translator:** After validating telemetry, gateway loads `cloud_public_key.bin` 800B [2] (cloud writes on start, shared via Docker volume `pqc-shared`), encapsulates: `ss, ct = ML-KEM.encaps(ek)` where `ct` 768B [2], `ss` 32B random becomes AES-256-GCM key. Wire format `ct(768)||nonce(12)||aes_ct` ~845B total for small JSON [2]. Measured encaps ~0.03ms Rust binding / 0.82ms pure Python, decaps ~0.04ms / 1.46ms — negligible for gateway [2].
- **Why ML-KEM-512:** Lowest overhead 800B pk + 768B ct = 1568B vs 2272B for 768 [2]. Still 128-bit security, sufficient for short-lived telemetry (minutes/hours, not decades). If long-term confidentiality needed (medical), should use 768 [1].
- **Cloud:** Decapsulates `ss = ML-KEM.decaps(dk, ct)`, AES-GCM decrypts, inserts into SQLite `telemetry.db` 1 table, no ORM. Analytics via health 6001 JSON: `db_rows`, `COUNT`, `AVG(temperature/humidity)`, `last 10`, `decaps_ok/fail`, `success_rate = ok/(ok+fail)`, `avg_decaps_ms` [2].
- **Fallback ensures availability:** If `cloud_public_key.bin` missing or cloud unreachable (TCP 6000 refused/timeout), gateway appends `<timestamp> <json>` to `gateway_fallback.log` + increments `fallback_local` + `cloud_fail` metrics. Cloud decaps fail → `decaps_fail++` but stays alive. Health 5001 shows `received, rejected, replayed, forwarded_to_cloud, fallback_local, cloud_fail, replay_cache_size, uptime_s`. This is business continuity per CISA hybrid guidance [5]. Operator can replay log later — no data loss.
- **Operational suitability:** CI via `astral-sh/setup-uv` reading `.python-version` 3.13 + `uv.lock`, `uv sync --frozen`, pytest 33/33 (was 27/33 baseline — gateway crash on `InvalidTag` exit 1, no schema, no replay), Dockerfile `python:3.13-slim` + `uv sync --frozen --no-install-project` respects lock, docker-compose with healthchecks `depends_on healthy`, volume `pqc-shared`. Logging file-only (`gateway.log`, `cloud.log`, `pqc.log`) to keep stdout clean for tests — tests merge stdout+stderr via `stderr=STDOUT`.

**Phase 2 — Future PQC-Capable Devices (Roadmap beyond 4h):**
- New devices with >8KB SRAM (ESP32, Raspberry Pi Pico) could run ML-KEM-512 directly
- Gateway supports both old PSK and new PQC devices (negotiation)
- File-based pk replaced by KMS/certificate, add TLS 1.3 with PQC certs
- Requires hardware replacement — cost/time 10-20y per CISA/EU [3][5]

**High-level info from codebase to include in executive report:** Yes, essential. The hybrid numbers (95B JSON → 123B wire 28B overhead legacy vs 845B PQC, 800B pk, 768B ct, 2KB vs 3KB SRAM, 33/33 tests, fallback log, DB analytics) make the abstract PQC transition concrete and measurable for managers.

---

## 5. Key Management & Supply Chain: From PSK in Flash to PQC Public Key File

**Legacy Link1:** Global 16B PSK `legacy_secret_16` stored in protected Flash ROM (real device). If one device physically stolen and Flash extracted, attacker can decrypt all Link1 traffic and forge telemetry — High impact if tampered (documented as tech debt). Future: per-device subkeys derived from master key, rotation.

**PQC Link2:** File-based pk distribution Phase1 — cloud writes `cloud_public_key.bin` 800B [2] on start, gateway reads file. No signature — attacker replacing file can do MITM (Man-In-The-Middle) on Link2 (Risk R6). Future: sign pk file, use certificate, fetch via TLS pinning, or KMS [3].

**Supply chain reality:** EU notes 60-80% of organizations need vendor cooperation for PQC migration [3]. CISA now prioritizes PQC-capable products in procurement [5]. For our system, we chose `mlkem==0.0.3` library because it is pip-installable, works with `uv` + Docker, supports both Rust binding (rust.so 909KB fast) and pure Python (fastmath.so 80KB) wheels — we added dual-wheel fix with `RUST_BINDING` flag after CI got pure Python wheel (empty `__init__.py`) while local had Rust wheel. This shows supply chain complexity even for small project.

**Constrained radio note (for executives planning LoRaWAN/Zigbee):** 800B pk + 768B ct overhead matters for low-power wireless like LoRaWAN (51B MTU), Zigbee (127B MTU), BLE (27-251B MTU), NB-IoT low bandwidth, battery-powered — sending 1.5KB extra needs fragmentation, more battery [2]. In our TCP/Ethernet simulation it's fine, but for real battery sensor with LoRa it would be problem — documented as Risk R4.

---

## 6. LLM as Untrusted Assistant: Risk and Mitigation

We used LLM as untrusted assistant per course requirement — 10 major interactions logged in `02_design_decisions_n_key_llm_interactions.md` plus 3 human CI fixes:

- **Interaction 1-3:** Baseline scaffolding, protocol selection (rejected WebSockets/HTTP 200-500B overhead), framing (rejected delimiters — ciphertext contains arbitrary bytes)
- **Interaction 4-5:** Test plan (Topics 1-4 accepted, dropped Topic5 fuzzing) and test generation → 27/33 baseline revealing real gaps
- **Interaction 6:** Gateway hardening → try/except boundary, REQUIRED_FIELDS, seen_nonces set, logging file-only (fix for stdout+stderr merged pipe pollution)
- **Interaction 7:** ML-KEM integration — LLM suggested `MLKEM512.keygen()` which does not exist in `mlkem==0.0.3` → human correction via REPL `ML_KEM(ParameterSet.ML_KEM_512).key_gen()`
- **Interaction 8-9:** Cloud + SQLite + analytics (accepted stdlib http.server, rejected Flask) and gateway forwarding + fallback + health
- **Interaction 10:** Docker + CI — LLM suggested `pip install -r requirements.txt` (rejected, we use pyproject.toml + uv) and Flask (rejected)
- **Fix 11-13 (human):** ModuleNotFoundError src (robust sys.path), ImportError ML_KEM dual-wheel, NameError os missing import

**Lesson for organization:** LLM can generate boilerplate quickly but proposes insecure/wrong APIs (static nonce would collapse AES-GCM security, `MLKEM512.keygen()` does not exist). Must be manually evaluated via pytest (27→33), REPL API testing, E2E checks, and CI. This mirrors enterprise risk: AI-generated code needs human review and automated tests.

---

## 7. Observability & Analytics: What Managers Need to See

Executives don't need packet dumps — they need business metrics:

- **Gateway health 5001:** `received, rejected, replayed, invalid_json, invalid_schema, empty, forwarded_to_cloud, fallback_local, cloud_fail, replay_cache_size, uptime_s` — shows PQC distribution failures and attack attempts
- **Cloud health 6001:** `db_rows, total_received, analytics {total_count, avg_temperature, avg_humidity, max_timestamp, last_10}, pqc {decaps_ok, decaps_fail, json_fail, success_rate, avg_decaps_ms}, uptime_s` — shows how many messages protected by PQC vs fallback, average temperature, recent telemetry
- **PQC observability:** `encaps_ms` ~0.03ms Rust / 0.82ms pure, `decaps_ms` ~0.04ms / 1.46ms, `ct_len=768`, `total_len` ~845B, `success_rate`, `fallback rate`, `rust_binding` flag logged to `pqc.log`
- **Simple DB:** SQLite `telemetry.db` stdlib, 1 table, no ORM, queries `COUNT, AVG, last 10` — enables managers to see PQC success rate and business continuity

**Example E2E evidence (tested 2026-10-11):** 2 legacy sends → gateway `received 2, forwarded 2`, cloud `db_rows 2, avg_temp 21.8, decaps_ok 2, success_rate 1.0`, `telemetry.db` 2 rows. Fallback: cloud down → `gateway_fallback.log` entry + `fallback_local=1` — no data loss, business continuity per CISA [5].

---

## 8. Risks, Compliance & Conclusion: Start Inventory Now

**Risks consolidated R1-R7 (from 06_ v3, same as 5.4 in Part1):**

| # | Risk | Severity | Status | Remaining |
|---|------|----------|--------|-----------|
| R1 | Gateway DoS via malformed input (crash on InvalidTag) | High | **Mitigated:** try/except + schema + replay, 33/33 pass | Rate limiting needed |
| R2 | Replay attacks | Medium | **Mitigated:** seen_nonces set | No TTL, restart clears cache → replay after restart |
| R3 | PSK extraction | Medium | **Not mitigated:** global PSK | Per-device keys, protected Flash |
| R4 | PQC perf & memory overhead | Medium | **Mitigated/measured:** 0.03ms/0.82ms encaps | 800B pk+768B ct heavy for constrained radio LoRaWAN 51B MTU [2] |
| R5 | Scalability concurrent starvation | Low | **Not mitigated:** 2 threads total (1 data +1 health) | asyncio/thread pool future |
| R6 | File-based pk MITM | Medium | **Not mitigated:** pk file no auth | Sign pk, cert, KMS [3] |
| R7 | DB no backup | Low | **Not mitigated:** single file | Periodic backup |

High-severity R1 fixed, R2 partially, others documented as tech debt — acceptable for 4h scope, per course Q&A incomplete integration OK if documented.

**Compliance:** CISA product categories list (Jan 2026) prioritizes PQC-capable products — procurement should require ML-KEM support [5]. EU roadmap requires inventory of all crypto-performing systems [3].

**Cost & Timeline:** Full migration 10-20y for large fleets [3][5]. Start with inventory now, adopt hybrid offload (like our Phase1) to protect internet-facing links without disrupting legacy, measure `success_rate` and `fallback_local` as KPIs, plan hardware refresh for PQC-capable devices (ESP32 >8KB SRAM).

**Call to Action for Executives:**
1. **Inventory** all crypto now (including hidden IoT) — you likely have 60-80% more than you think [3]
2. **Adopt hybrid** with fallback (gateway offload pattern) — keep legacy running, add PQC on internet-facing Link2, ensure business continuity [5]
3. **Measure** PQC observability: `encaps_ms`, `decaps_ms`, `success_rate`, `fallback rate` via health endpoints + DB analytics
4. **Plan** key management upgrade (per-device subkeys, sign pk file, KMS, rotation) and hardware replacement budget

Our Group 23 system demonstrates that even a small team with LLM assistance can build a working hybrid PQC system in 4 hours, with 33/33 tests passing, SQLite analytics, and fallback ensuring availability — proving the organizational transition is feasible if started now.

---

## References (public, same 5 used in Part1)

- [1] NIST FIPS 203 ML-KEM standardised in August 2024 — https://www.encryptionconsulting.com/education-center/ml-kem-fips-203/
- [2] ML-KEM sizes: 800B pk (public key / encapsulation key), 768B ct (ciphertext) — https://vucense.com/privacy-sovereignty/post-quantum-cryptography/ml-kem-fips-203-implementation-guide-2026/
- [3] EU roadmap, hybrid for legacy, hardware replacement may be needed — https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/
- [4] Legacy constraints, computational overhead — https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems
- [5] CISA PQC initiative, phased migration — https://www.cisa.gov/topics/risk-management/quantum
