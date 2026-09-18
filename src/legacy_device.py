import json
import os
import socket
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 128-bit (16 bytes) Pre-Shared Key (PSK)
# In real embedded systems, this is flashed onto the microcontroller ROM.
PRE_SHARED_KEY = b"legacy_secret_16"
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 5000


def generate_telemetry() -> dict:
    """Generates standard sensor telemetry data."""
    return {
        "device_id": "sensor-node-01",
        "timestamp": int(time.time()),
        "temperature": 21.8,
        "humidity": 55.4,
        "status": "OK",
    }


def encrypt_payload(data: dict, key: bytes) -> bytes:
    """Serializes and encrypts the payload using AES-128-GCM."""
    # 1. Convert python dictionary to raw JSON bytes
    raw_bytes = json.dumps(data).encode("utf-8")

    # 2. Initialize AES-GCM engine with our pre-shared key
    aesgcm = AESGCM(key)

    # 3. Generate a 12-byte (96-bit) cryptographically random Nonce (Number Used Once).
    # Reusing nonces in GCM breaks security completely; fresh random bytes are mandatory per message.
    nonce = os.urandom(12)

    # 4. Encrypt the data. AESGCM handles encryption and calculates a 16-byte authentication tag.
    ciphertext = aesgcm.encrypt(nonce, raw_bytes, None)

    # 5. Pack the packet: prepend the 12-byte nonce to the ciphertext.
    # The receiver needs the nonce to decrypt, but the nonce does not need to be secret.
    return nonce + ciphertext


def main():
    payload = generate_telemetry()
    packet = encrypt_payload(payload, PRE_SHARED_KEY)

    # Open standard TCP client socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((GATEWAY_HOST, GATEWAY_PORT))
        # Transmit the entire packet (nonce + ciphertext + tag)
        client.sendall(packet)
        # Exiting the 'with' block automatically closes the socket,
        # which signals an EOF (End of File) to the gateway receiver.


if __name__ == "__main__":
    main()