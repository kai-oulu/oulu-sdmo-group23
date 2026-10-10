# Migration and Fallback Strategy - Legacy Device Compatibility

## 1. Legacy Constraint: Why Arduino Can't Do Post-Quantum Cryptography

- Device profile: ATmega328P, 16 MHz, 32 KB Flash, **2 KB SRAM**
- ML-KEM-512 requirements: secret key 1632B + working memory 1000-1500B for polynomial operations = approx 3KB total
- Result: **Stack overflow, crash** - physically impossible to run ML-KEM on 2 KB SRAM
- Measurement from baseline: ML-KEM-512 secret key alone exceeds 80% of SRAM
- Conclusion: Legacy device must stay on lightweight symmetric crypto (AES-128-GCM, 16B key, 12B nonce, 28B overhead)

This is same as real-world IoT: many low-cost sensors cannot be upgraded to Post-Quantum Cryptography without hardware replacement ([HelpNet](https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/), [Eureka](https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems))


## 2. Phased Migration Strategy
Taking reference from US CISA (Cybersecurity n Infrastructure Security Agency) PQC (Post-Quantum Cryptography) initiative's [phased migration guide](https://www.cisa.gov/topics/risk-management/quantum).

### Phase 1: Legacy Only (Baseline, initial repo before adding on to the build on 2026.10.10)
- Link1: Legacy → Gateway: AES-128-GCM PSK, TCP 5000, EOF framing
- Link2: Gateway → Cloud: not implemented or plaintext
- Risk: harvest-now-decrypt-later on Link2 if internet-facing

### Phase 2: Hybrid Legacy Sensors and PQC Gateway-Cloud Link (Current Implementation since 2026.10.10)
- Link1: **Unchanged** - legacy devices keep AES-128-GCM PSK, no firmware update needed
- Gateway: **Security translator** - decrypts AES-GCM, validates schema, checks replay, then **encapsulates with ML-KEM-512** and AES-256-GCM to cloud
- Link2: **PQC-protected** - `ct(768)||nonce(12)||aes_ct`, cloud decaps and stores in SQLite
- Public key distribution: **File-based** - cloud writes `cloud_public_key.bin` (800B) on start, gateway reads file. Simple for simulation, documented as tech debt.
- Benefits: No legacy disruption, Post-Quantum Cryptography on internet-facing link, fallback possible
- Trade-off: Gateway is the single point of trust, which must be hardened (implementatino so far: try/except, schema, replay)

### Phase 3: Future PQC-Capable Devices and PQC Gateway-Cloud Link (Future Work)
- New devices with >8KB SRAM (e.g., ESP32, Raspberry Pi Pico) could run ML-KEM-512 directly
- Link1 could become hybrid: AES-GCM + ML-KEM, or pure PQC
- Gateway would support both old PSK/Pre-Shared Key devices and new PQC devices
- Cloud would support both ML-KEM-512 and 768 (for long-term confidentiality)
- Requires hardware replacement for the old set of sensor devices - which needs cost/time


## 3. Fallback Strategy (Business Continuity)

**Goal:** System stays available even if Post-Quantum Cryptography fails, cloud down, or keys missing - very important for an organisation.

| Failure Mode | Detection | Fallback Action | Observability |
|--------------|-----------|-----------------|---------------|
| Cloud public key file missing (`cloud_public_key.bin` not found) | `FileNotFoundError` on load | Gateway logs warning, appends telemetry JSON to `gateway_fallback.log` with timestamp, increments `fallback_local` metric | Health 5001 `fallback_local++`, log `cloud_public_key not available` |
| Cloud unreachable (TCP 6000 connection refused, timeout) | `ConnectionRefusedError`, `OSError`, `socket.timeout` | Same as above: fallback log + `cloud_fail++` + `fallback_local++` | Health 5001 `cloud_fail`, `fallback_local`, log `Cloud unreachable` |
| PQC decaps fail in cloud (corrupted ct, wrong key) | Exception in `decrypt_from_gateway` | Cloud logs warning, increments `decaps_fail`, does NOT crash, continues listening | Health 6001 `decaps_fail`, `success_rate`, log `Rejected PQC packet` |
| PQC encaps fail in gateway | Exception in `encrypt_for_cloud` | Fallback log + `fallback_local` | Health 5001, log `Unexpected error in forward_to_cloud` |
| Legacy malformed packet (InvalidTag, truncated, replay) | `InvalidTag`, `ValueError`, `seen_nonces` check | Gateway logs warning, increments `rejected`/`replayed`, continues listening (no crash) | Health 5001 `rejected`, `replayed`, logs, 33/33 tests pass |

**Store-and-forward:** `gateway_fallback.log` format: `<unix_timestamp> <json>`, e.g., `1791603565 {"device_id":...}`. Operator can later replay to cloud manually or via script. Documented as minimal persistence.

**Why fallback matters for org:** Following CISA guidance, a hybrid setup with fallback ensures non-PQC legacy devices keep working during Post-Quantum Cryptography migration, avoiding downtime. If Post-Quantum Cryptography implementation has bugs, system degrades gracefully to local logging, not causing a total outage.


## 4. Legacy Compatibility Preservation

- **Link1 unchanged:** Same PSK/Pre-Shared Key `legacy_secret_16`, same 12B nonce prepended, same EOF framing - legacy device code not modified after baseline
- **No firmware update required** for ATmega328P - justified by SRAM analysis
- **Gateway per-device subkeys not implemented** (global PSK) - documented as tech debt, future should have per-device keys in protected Flash
- **Backward compatibility:** New gateway still accepts old legacy payloads (with required fields), old gateway would reject PQC packets (expected)


## 5. Remaining Risks

- File-based pk/public key distribution has no authentication - attacker could replace `cloud_public_key.bin` with their own key (Mitigation in future: sign pk/public key file or use cert)
- `seen_nonces` in-memory set grows forever, no TTL - could OOM with many devices (Mitigation in future: add TTL or LRU cache)
- Global PSK/Pre-Shared Key - if extracted from 1 device, all other devices will be compromised (Mitigation in future: per-device subkeys)
- No key rotation for ML-KEM - dk/decapsulation key stays in memory (Mitigation in future: rotate daily, and store decapsulation keys securely eg in a key management store)

## 6. References

- EU roadmap, hybrid for legacy, hardware replacement may be needed - https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/
- legacy constraints, computational overhead - https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems
- CISA PQC initiative, phased migration - https://www.cisa.gov/topics/risk-management/quantum


