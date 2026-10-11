# Migration and Fallback Strategy — Legacy Device Compatibility

## 1. Legacy Constraint: Why Arduino Can't Do PQC

- Device profile: ATmega328P, 16 MHz, 32 KB Flash, **2 KB SRAM**
- ML-KEM-512 requirements: secret key 1632B + working memory 1000-1500B for polynomial operations = ~3KB total
- Result: **Stack overflow, crash** — physically impossible to run ML-KEM on 2 KB SRAM
- Measurement from baseline: ML-KEM-512 secret key alone exceeds 80% of SRAM
- Conclusion: Legacy device must stay on lightweight symmetric crypto (AES-128-GCM, 16B key, 12B nonce, 28B overhead)

This is same as real-world IoT: many low-cost sensors cannot be upgraded to PQC without hardware replacement [1][2]

## 2. Phased Migration Strategy (Org-friendly, C-suite view)

### Phase 0: Legacy Only (Baseline, initial repo)
- Link1: Legacy → Gateway: AES-128-GCM PSK, TCP 5000, EOF framing
- Link2: Gateway → Cloud: not implemented or plaintext
- Risk: harvest-now-decrypt-later on Link2 if internet-facing

### Phase 1: Hybrid Offload (Current Implementation, 4h scope)
- Link1: **Unchanged** — legacy devices keep AES-128-GCM PSK, no firmware update needed
- Gateway: **Security translator** — decrypts AES-GCM, validates schema, checks replay, then **encapsulates with ML-KEM-512** and AES-256-GCM to cloud
- Link2: **PQC-protected** — `ct(768)||nonce(12)||aes_ct`, cloud decaps and stores in SQLite
- Public key distribution: **File-based** — cloud writes `cloud_public_key.bin` (800B) on start, gateway reads file. Simple for simulation, documented as tech debt.
- Benefits: No legacy disruption, PQC on internet-facing link, fallback possible
- Trade-off: Gateway is single point of trust, must be hardened (done: try/except, schema, replay)

### Phase 2: Future PQC-Capable Devices (Beyond 4h, documented as roadmap)
- New devices with >8KB SRAM (e.g., ESP32, Raspberry Pi Pico) could run ML-KEM-512 directly
- Link1 could become hybrid: AES-GCM + ML-KEM, or pure PQC
- Gateway would support both old PSK and new PQC devices (negotiation)
- Cloud would support both ML-KEM-512 and 768 (for long-term confidentiality)
- Requires hardware replacement for old fleet — cost/time (10-20 years for large orgs per CISA)

## 3. Fallback Strategy (Business Continuity)

**Goal:** System stays available even if PQC fails, cloud down, or keys missing — critical for org.

| Failure Mode | Detection | Fallback Action | Observability |
|--------------|-----------|-----------------|---------------|
| Cloud public key file missing (`cloud_public_key.bin` not found) | `FileNotFoundError` on load | Gateway logs warning, appends telemetry JSON to `gateway_fallback.log` with timestamp, increments `fallback_local` metric | Health 5001 `fallback_local++`, log `cloud_public_key not available` |
| Cloud unreachable (TCP 6000 connection refused, timeout) | `ConnectionRefusedError`, `OSError`, `socket.timeout` | Same as above: fallback log + `cloud_fail++` + `fallback_local++` | Health 5001 `cloud_fail`, `fallback_local`, log `Cloud unreachable` |
| PQC decaps fail in cloud (corrupted ct, wrong key) | Exception in `decrypt_from_gateway` | Cloud logs warning, increments `decaps_fail`, does NOT crash, continues listening | Health 6001 `decaps_fail`, `success_rate`, log `Rejected PQC packet` |
| PQC encaps fail in gateway | Exception in `encrypt_for_cloud` | Fallback log + `fallback_local` | Health 5001, log `Unexpected error in forward_to_cloud` |
| Legacy malformed packet (InvalidTag, truncated, replay) | `InvalidTag`, `ValueError`, `seen_nonces` check | Gateway logs warning, increments `rejected`/`replayed`, continues listening (no crash) | Health 5001 `rejected`, `replayed`, logs, 33/33 tests pass |

**Store-and-forward:** `gateway_fallback.log` format: `<unix_timestamp> <json>`, e.g., `1791603565 {"device_id":...}`. Operator can later replay to cloud manually or via script. Documented as minimal persistence.

**Why fallback matters for org:** Per CISA/ENISA guidance, hybrid deployment with fallback ensures legacy devices keep working during PQC migration, avoiding downtime. If PQC implementation has bug, system degrades gracefully to local log, not total outage.

## 4. Legacy Compatibility Preservation

- **Link1 unchanged:** Same PSK `legacy_secret_16`, same 12B nonce prepended, same EOF framing — legacy device code not modified after baseline
- **No firmware update required** for ATmega328P — justified by SRAM analysis
- **Gateway per-device subkeys not implemented** (global PSK) — documented as tech debt, future should have per-device keys in protected Flash
- **Backward compatibility:** New gateway still accepts old legacy payloads (with required fields), old gateway would reject PQC packets (expected)

## 5. LLM Interaction Summary

- Prompt: "Design migration and fallback strategy for legacy ATmega328P that cannot run ML-KEM due to 2KB SRAM, need phased rollout and fallback if cloud PQC fails"
- LLM suggested: immediate firmware update to all devices to support ML-KEM-768 — rejected as impossible due to SRAM overflow
- LLM suggested: use TLS 1.3 with PQC for Link1 — rejected, TLS overhead 200-500B too large for 2KB device
- Accepted: offload pattern (gateway as translator), phased migration, file-based pk distribution for simplicity, store-and-forward fallback log
- Human evaluation: verified SRAM calculation (1632+1500=~3KB >2KB), tested fallback by stopping cloud and checking `gateway_fallback.log` has entry

## 6. Remaining Risks

- File-based pk distribution has no authentication — attacker could replace `cloud_public_key.bin` with own key (mitigation future: sign pk file or use cert)
- `seen_nonces` in-memory set grows forever, no TTL — could OOM with many devices (mitigation: add TTL or LRU cache)
- Global PSK — if one device extracted, all compromised (mitigation: per-device subkeys)
- No key rotation for ML-KEM — dk stays in memory (mitigation: rotate daily, persist securely)

## 7. References (public)

- [1] https://www.helpnetsecurity.com/2025/07/10/david-warburton-f5-labs-eu-pqc-roadmap/ — EU roadmap, hybrid for legacy, hardware replacement may be needed
- [2] https://eureka.patsnap.com/report-how-to-adapt-post-quantum-standards-to-existing-legacy-systems — legacy constraints, computational overhead
- [3] https://www.cisa.gov/topics/risk-management/quantum — CISA PQC initiative, phased migration

