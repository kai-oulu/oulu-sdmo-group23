"""
Created 2026.10.10
PQC Utilities for ML-KEM-512 hybrid encryption (Link 2: Gateway -> Cloud)
- Uses mlkem library (Rust binding) with NIST FIPS 203 ML-KEM-512
- Hybrid pattern: ML-KEM encaps -> 32B shared secret -> AES-256-GCM encrypt telemetry
- Wire format: ct(768) || nonce(12) || aes_ciphertext+tag
"""

import logging
import os
import time
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from mlkem import ML_KEM, ParameterSet

# Constants for ML-KEM-512 (lightest, suitable for gateway)
PK_LEN = 800  # Encaps key (public) length
SK_LEN = 1632  # Decaps key (secret) length
CT_LEN = 768  # Ciphertext length
SS_LEN = 32  # Shared secret length
NONCE_LEN = 12  # AES-GCM nonce

CLOUD_PK_PATH = Path("cloud_public_key.bin")

# Use file logging to avoid polluting stdout in tests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("pqc.log"),
    ],
)


def get_mlkem_instance():
    """Get ML-KEM-512 instance"""
    return ML_KEM(ParameterSet.ML_KEM_512)


def generate_keypair(
    save_path: Path = CLOUD_PK_PATH,
) -> Tuple[bytes, bytes, ML_KEM]:
    """
    Generate ML-KEM-512 keypair and save public key to file.
    Returns (ek_bytes, dk_bytes, mlkem_obj)
    ek = encaps key (public, 800B), dk = decaps key (secret, 1632B)
    """
    mlkem_obj = get_mlkem_instance()
    ek, dk = mlkem_obj.key_gen()  # ek is EncapsKey, dk is DecapsKey
    ek_bytes = ek.to_bytes()
    dk_bytes = dk.to_bytes()

    assert len(ek_bytes) == PK_LEN, f"Unexpected pk len {len(ek_bytes)}"
    assert len(dk_bytes) == SK_LEN, f"Unexpected sk len {len(dk_bytes)}"

    # Save public key for gateway to read (file-based distribution - Phase1)
    save_path.write_bytes(ek_bytes)
    logging.info(
        f"Generated ML-KEM-512 keypair: pk {len(ek_bytes)}B saved to {save_path}, sk {len(dk_bytes)}B in memory"
    )
    return ek_bytes, dk_bytes, mlkem_obj


def load_public_key(path: Path = CLOUD_PK_PATH) -> bytes:
    """Load public key from file"""
    if not path.exists():
        raise FileNotFoundError(f"Public key file not found: {path}")
    data = path.read_bytes()
    if len(data) != PK_LEN:
        raise ValueError(f"Invalid pk length {len(data)}, expected {PK_LEN}")
    return data


def encrypt_for_cloud(plaintext: bytes, ek_bytes: bytes) -> Tuple[bytes, dict]:
    """
    Hybrid encrypt: ML-KEM encaps + AES-256-GCM
    Returns (packet, metrics)
    packet = ct(768) || nonce(12) || aes_ct+tag
    metrics = {encaps_ms, aes_encrypt_ms, ct_len, total_len}
    """
    start = time.time()

    # Load ek from bytes and encaps
    from mlkem import EncapsKey

    mlkem_obj = get_mlkem_instance()
    # EncapsKey.from_bytes needs param set? Try without, fallback with param
    try:
        ek = EncapsKey.from_bytes(ek_bytes)
    except TypeError:
        # Some versions require param set
        ek = EncapsKey.from_bytes(ek_bytes, ParameterSet.ML_KEM_512)

    encaps_start = time.time()
    ss, ct = mlkem_obj.encaps(ek)
    encaps_ms = (time.time() - encaps_start) * 1000

    assert len(ss) == SS_LEN
    assert len(ct) == CT_LEN

    # AES-256-GCM encrypt plaintext with ss as key
    aes_start = time.time()
    nonce = os.urandom(NONCE_LEN)
    aesgcm = AESGCM(ss)  # ss is 32B -> AES-256
    aes_ct = aesgcm.encrypt(nonce, plaintext, None)
    aes_ms = (time.time() - aes_start) * 1000

    packet = ct + nonce + aes_ct

    total_ms = (time.time() - start) * 1000
    metrics = {
        "encaps_ms": round(encaps_ms, 2),
        "aes_encrypt_ms": round(aes_ms, 2),
        "total_ms": round(total_ms, 2),
        "ct_len": len(ct),
        "nonce_len": len(nonce),
        "aes_ct_len": len(aes_ct),
        "total_len": len(packet),
        "ss_len": len(ss),
    }

    logging.info(
        f"PQC encrypt: encaps {metrics['encaps_ms']}ms, AES {metrics['aes_encrypt_ms']}ms, total {len(packet)}B (ct 768 + nonce 12 + aes {len(aes_ct)})"
    )

    return packet, metrics


def decrypt_from_gateway(
    packet: bytes, dk_bytes: bytes, mlkem_obj: ML_KEM = None
) -> Tuple[bytes, dict]:
    """
    Hybrid decrypt: split packet, decaps ct -> ss, AES-GCM decrypt
    Returns (plaintext, metrics)
    """
    start = time.time()

    if len(packet) < CT_LEN + NONCE_LEN + 16:  # 16 is min tag
        raise ValueError(f"Packet too short {len(packet)}")

    ct = packet[:CT_LEN]
    nonce = packet[CT_LEN : CT_LEN + NONCE_LEN]
    aes_ct = packet[CT_LEN + NONCE_LEN :]

    # Decaps
    from mlkem import DecapsKey

    if mlkem_obj is None:
        mlkem_obj = get_mlkem_instance()

    try:
        dk = DecapsKey.from_bytes(dk_bytes)
    except TypeError:
        dk = DecapsKey.from_bytes(dk_bytes, ParameterSet.ML_KEM_512)

    decaps_start = time.time()
    ss = mlkem_obj.decaps(dk, ct)
    decaps_ms = (time.time() - decaps_start) * 1000

    assert len(ss) == SS_LEN

    # AES decrypt
    aes_start = time.time()
    aesgcm = AESGCM(ss)
    plaintext = aesgcm.decrypt(nonce, aes_ct, None)
    aes_ms = (time.time() - aes_start) * 1000

    total_ms = (time.time() - start) * 1000
    metrics = {
        "decaps_ms": round(decaps_ms, 2),
        "aes_decrypt_ms": round(aes_ms, 2),
        "total_ms": round(total_ms, 2),
        "ct_len": len(ct),
        "total_len": len(packet),
    }

    logging.info(
        f"PQC decrypt: decaps {metrics['decaps_ms']}ms, AES {metrics['aes_decrypt_ms']}ms, total {len(packet)}B"
    )

    return plaintext, metrics


# Simple self-test when run directly
if __name__ == "__main__":
    print("Testing PQC utils round-trip...")
    ek_b, dk_b, mlkem_o = generate_keypair(Path("/tmp/test_pk.bin"))
    msg = b'{"device_id":"sensor-node-01","temperature":21.8}'
    pkt, enc_metrics = encrypt_for_cloud(msg, ek_b)
    print(f"Encrypted packet len {len(pkt)}, metrics {enc_metrics}")
    plain, dec_metrics = decrypt_from_gateway(pkt, dk_b, mlkem_o)
    print(f"Decrypted: {plain}, metrics {dec_metrics}")
    assert plain == msg
    print("Round-trip OK!")

