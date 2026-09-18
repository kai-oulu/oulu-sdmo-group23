import socket
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Must match the legacy device's pre-shared key
PRE_SHARED_KEY = b"legacy_secret_16"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 5000


def decrypt_payload(encrypted_packet: bytes, key: bytes) -> str:
    """Extracts nonce, verifies authenticity, and decrypts the payload."""
    # 1. Slice the first 12 bytes to recover the nonce
    nonce = encrypted_packet[:12]

    # 2. Slice the remainder to get the ciphertext + GMAC auth tag
    ciphertext = encrypted_packet[12:]

    # 3. Decrypt using AES-GCM
    aesgcm = AESGCM(key)
    # aesgcm.decrypt() checks the authentication tag first.
    # If the packet was modified or the key is wrong, it raises InvalidTag and crashes.
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)

    # 4. Decode raw UTF-8 bytes back into a JSON string
    return decrypted_bytes.decode("utf-8")


def start_gateway():
    # Set up TCP server socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        # SO_REUSEADDR allows restarting the server immediately without port-lock errors
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((LISTEN_HOST, LISTEN_PORT))
        server.listen()
        print(
            f"Edge Gateway listening for legacy devices on port {LISTEN_PORT}..."
        )

        while True:
            # Block until a legacy device connects
            conn, addr = server.accept()
            with conn:
                buffer = bytearray()
                while True:
                    # Read incoming chunks of data
                    chunk = conn.recv(1024)
                    if not chunk:
                        # Empty bytes indicate client closed connection (EOF)
                        break
                    buffer.extend(chunk)

                if buffer:
                    raw_data = decrypt_payload(bytes(buffer), PRE_SHARED_KEY)
                    print(f"Received from device: {raw_data}")


if __name__ == "__main__":
    start_gateway()