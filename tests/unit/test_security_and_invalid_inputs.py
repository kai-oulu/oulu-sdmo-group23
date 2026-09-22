"""Deterministic security and invalid-input tests for AES-GCM packet handling."""

import json

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import edge_gateway
import legacy_device


def test_decrypt_payload_rejects_different_valid_length_key(
    telemetry_payload, test_key, fixed_nonce
) -> None:
    """Security unit test: detects acceptance of a packet encrypted under another AES key."""
    packet = legacy_device.encrypt_payload(telemetry_payload, test_key)

    with pytest.raises(InvalidTag):
        edge_gateway.decrypt_payload(packet, b"different_key_16")


def test_decrypt_payload_rejects_modified_ciphertext(
    telemetry_payload, test_key, fixed_nonce
) -> None:
    """Security unit test: detects loss of AES-GCM ciphertext-integrity verification."""
    packet = bytearray(legacy_device.encrypt_payload(telemetry_payload, test_key))
    packet[12] ^= 1

    with pytest.raises(InvalidTag):
        edge_gateway.decrypt_payload(bytes(packet), test_key)


def test_decrypt_payload_rejects_modified_authentication_tag(
    telemetry_payload, test_key, fixed_nonce
) -> None:
    """Security unit test: detects acceptance of a packet with an altered final GCM tag byte."""
    packet = bytearray(legacy_device.encrypt_payload(telemetry_payload, test_key))
    packet[-1] ^= 1

    with pytest.raises(InvalidTag):
        edge_gateway.decrypt_payload(bytes(packet), test_key)


def test_decrypt_payload_rejects_modified_nonce(
    telemetry_payload, test_key, fixed_nonce
) -> None:
    """Security unit test: detects authentication bypass after nonce manipulation."""
    packet = bytearray(legacy_device.encrypt_payload(telemetry_payload, test_key))
    packet[0] ^= 1

    with pytest.raises(InvalidTag):
        edge_gateway.decrypt_payload(bytes(packet), test_key)


def test_decrypt_payload_accepts_replayed_valid_packet(
    telemetry_payload, test_key, fixed_nonce
) -> None:
    """Security unit test: documents the current absence of replay detection in this function."""
    packet = legacy_device.encrypt_payload(telemetry_payload, test_key)

    assert edge_gateway.decrypt_payload(packet, test_key) == json.dumps(telemetry_payload)
    assert edge_gateway.decrypt_payload(packet, test_key) == json.dumps(telemetry_payload)


def test_encrypt_payload_rejects_invalid_key_length(telemetry_payload) -> None:
    """Negative unit test: detects any change to the crypto library's invalid-key rejection."""
    with pytest.raises(ValueError):
        legacy_device.encrypt_payload(telemetry_payload, b"fifteen-byte!!")


def test_encrypt_payload_rejects_non_bytes_key(telemetry_payload) -> None:
    """Negative unit test: detects acceptance of a key with an invalid runtime type."""
    with pytest.raises(TypeError):
        legacy_device.encrypt_payload(telemetry_payload, "legacy_secret_16")  # type: ignore[arg-type]


def test_encrypt_payload_rejects_non_json_serializable_value(test_key) -> None:
    """Negative unit test: detects suppressed JSON serialization failures."""
    with pytest.raises(TypeError):
        legacy_device.encrypt_payload({"unsupported": object()}, test_key)


@pytest.mark.parametrize("packet", [b"", b"\x00" * 7])
def test_decrypt_payload_rejects_nonce_shorter_than_aesgcm_minimum(
    packet, test_key
) -> None:
    """Negative unit test: detects malformed nonce acceptance before authentication can occur."""
    with pytest.raises(ValueError):
        edge_gateway.decrypt_payload(packet, test_key)


@pytest.mark.parametrize("packet", [b"\x00" * 8, b"\x00" * 11, b"\x00" * 12])
def test_decrypt_payload_rejects_missing_ciphertext_or_tag(packet, test_key) -> None:
    """Negative unit test: detects successful decryption without a complete GCM authentication tag."""
    with pytest.raises(InvalidTag):
        edge_gateway.decrypt_payload(packet, test_key)


@pytest.mark.parametrize("bytes_removed", [1, 8, 16])
def test_decrypt_payload_rejects_truncated_valid_packet(
    bytes_removed, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Negative unit test: detects acceptance of a packet truncated in ciphertext or tag bytes."""
    packet = legacy_device.encrypt_payload(telemetry_payload, test_key)

    with pytest.raises(InvalidTag):
        edge_gateway.decrypt_payload(packet[:-bytes_removed], test_key)


def test_decrypt_payload_raises_for_authenticated_non_utf8_plaintext(test_key, fixed_nonce) -> None:
    """Negative unit test: detects silent handling of authenticated bytes that cannot be UTF-8 decoded."""
    ciphertext_and_tag = AESGCM(test_key).encrypt(fixed_nonce, b"\xff", None)

    with pytest.raises(UnicodeDecodeError):
        edge_gateway.decrypt_payload(fixed_nonce + ciphertext_and_tag, test_key)


def test_decrypt_payload_returns_authenticated_non_json_utf8_text(test_key, fixed_nonce) -> None:
    """Unit boundary test: documents that the gateway decodes but does not parse JSON text."""
    ciphertext_and_tag = AESGCM(test_key).encrypt(fixed_nonce, b"not-json", None)

    assert edge_gateway.decrypt_payload(fixed_nonce + ciphertext_and_tag, test_key) == "not-json"
