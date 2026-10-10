# ML-KEM Integration - Link 2: Edge Gateway to Cloud Service

## 1. Objective
Integrate post-quantum key encapsulation (ML-KEM) into at least one communication path (Link 2) using an existing library, preserving legacy compatibility for Link 1 (ATmega328P).


## 2. Library Choice

**Chosen library:** `mlkem==0.0.3` (Rust binding, Python wrapper)

**Alternatives evaluated:**
- `kyber-py` (pure Python, suggested in course Q&A): heavier, slower, more code
- `liboqs` Python wrapper: requires native liboqs install, complex for Docker
- `cryptography` does not yet include ML-KEM in stable release

**Decision: Accepted `mlkem`**
- Minimal, pip-installable, no native deps beyond Rust compiled wheel
- API validated: `ML_KEM(ParameterSet.ML_KEM_512).key_gen() -> ek 800B, dk 1632B`, `encaps(ek) -> ss 32B, ct 768B`, `decaps(dk, ct) -> ss`
- Works with `uv sync --frozen` and `python:3.13-slim` Docker
- Documented as tech debt: file-based public key distribution, future should use certificate or KMS

**Why ML-KEM-512 (not 768/1024):**
| Param set | Security | Public key | Ciphertext | Shared secret | Use case |
|-----------|----------|------------|------------|---------------|----------|
| ML-KEM-512 | ~AES-128 (Category 1) | 800B | 768B | 32B | Lightest, constrained gateway |
| ML-KEM-768 | ~AES-192 (Category 3) | 1184B | 1088B | 32B | NIST recommended default |
| ML-KEM-1024 | ~AES-256 (Category 5) | 1568B | 1568B | 32B | Highest |

- ML-KEM-512 has lowest wire overhead (800+768=1568B vs 2272B for 768) - this matters for a gateway forwarding input data from many sensors
- Still 128-bit classical security, sufficient for telemetry with short secrecy lifetime (minutes/hours, not decades)
- Cloud stores telemetry short-term, not long-term archival
- Documented: if long-term confidentiality needed (e.g., medical), we should use ML-KEM-768 or 1024


## 3. Hybrid Encryption Design (Link 2)

**Why hybrid:** ML-KEM is KEM, not encryption. It establishes 32B shared secret, then we use symmetric AES-256-GCM for actual data.

**Wire format:**
```
packet = ct (768B) || nonce (12B) || aes_ciphertext + tag (variable, ~65B for small JSON)
Total ~845B for typical telemetry {"device_id":..., "temperature":21.8,...}
```

**Flow:**
1. Cloud on start: `ek, dk = ML_KEM(ML_KEM_512).key_gen()`, save `ek` to `cloud_public_key.bin` (800B)
2. Gateway after validating legacy AES-GCM payload:
   - Load `cloud_public_key.bin` (if missing → fallback)
   - `ss, ct = mlkem.encaps(ek)` - encaps time logged (~0.03ms)
   - `nonce = os.urandom(12)`, `aes_ct = AESGCM(ss).encrypt(nonce, telemetry_json_bytes, None)`
   - Packet = ct + nonce + aes_ct, send via TCP to cloud:6000, EOF framing
3. Cloud: recv until EOF, split ct/nonce/aes_ct, `ss = mlkem.decaps(dk, ct)` (~0.04ms), `AESGCM(ss).decrypt(nonce, aes_ct)`, JSON parse, insert into SQLite

**Post-Quantum Cryptography observability logged:**
- `encaps_ms`, `decaps_ms`, `ct_len=768`, `total_len`, `ss_len=32`, `success_rate = decaps_ok/(ok+fail)`
- Exposed via health endpoints 5001 (gateway) and 6001 (cloud)


## 4. Code Snippets

**Keygen (cloud_service.py):**
```python
from mlkem import ML_KEM, ParameterSet
mlkem_obj = ML_KEM(ParameterSet.ML_KEM_512)
ek, dk = mlkem_obj.key_gen()
ek_bytes = ek.to_bytes()  # 800B
dk_bytes = dk.to_bytes()  # 1632B
Path("cloud_public_key.bin").write_bytes(ek_bytes)
```

**Encrypt (pqc_utils.py):**
```python
ss, ct = mlkem_obj.encaps(ek)  # ss 32B, ct 768B
nonce = os.urandom(12)
aes_ct = AESGCM(ss).encrypt(nonce, plaintext, None)
packet = ct + nonce + aes_ct
```

**Decrypt (pqc_utils.py):**
```python
ct = packet[:768]
nonce = packet[768:780]
aes_ct = packet[780:]
ss = mlkem_obj.decaps(dk, ct)
plaintext = AESGCM(ss).decrypt(nonce, aes_ct, None)
```

## 5. Security Properties

- **Confidentiality:** ML-KEM secure against quantum (Module-LWE hardness), AES-256-GCM secure
- **Integrity:** AES-GCM tag verifies tampering on Link2, same as Link1
- **No forward secrecy for PSK Link1** - documented as a weakness (global PSK/Pre-Shared Key)
- **Post-Quantum Cryptography Link2 has no forward secrecy either if dk/decapsulation key is leaked** - should rotate keys periodically (future work)
- **Replay protection:** Gateway tracks seen nonces for Link1, cloud relies on gateway filtering + timestamp check (future improvement: add nonce cache in cloud too)


## 6. Remaining Limitations

- File-based public key distribution (no cert, no rotation) - documented as Phase1, future build should use KMS/Key Management Service or mutual TLS with Post-Quantum Cryptography certs
- No key rotation, no TTL on seen_nonces (in-memory set grows)
- ML-KEM-512 only, not 768 (trade-off for simplicity)


## 7. References

- NIST FIPS 203 ML-KEM standardised in August 2024 - https://www.encryptionconsulting.com/education-center/ml-kem-fips-203/
- ML-KEM sizes: 800B pk (public key / encapsulation key), 768B ct (ciphertext) - https://vucense.com/privacy-sovereignty/post-quantum-cryptography/ml-kem-fips-203-implementation-guide-2026/



