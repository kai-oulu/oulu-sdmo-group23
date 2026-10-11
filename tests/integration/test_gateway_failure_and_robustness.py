"""Real loopback tests for gateway failure modes and TCP robustness boundaries."""

import json
import socket

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import edge_gateway
import legacy_device


def _send_and_close(port: int, data: bytes) -> None:
    """Transmit a payload over the gateway's EOF-delimited TCP protocol."""
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.sendall(data)
        client.shutdown(socket.SHUT_WR)


def _encrypt_plaintext(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    """Build a valid AES-GCM packet for gateway validation-boundary tests."""
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def test_gateway_remains_available_after_malformed_nonempty_packet(
    running_gateway, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Resilience acceptance test: rejects malformed input without losing later valid traffic."""
    _send_and_close(running_gateway.port, b"not-an-aes-gcm-packet")
    valid_packet = legacy_device.encrypt_payload(telemetry_payload, test_key)
    _send_and_close(running_gateway.port, valid_packet)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(telemetry_payload)
    assert running_gateway.process.poll() is None


def test_gateway_remains_available_after_connection_closes_mid_packet(
    running_gateway, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Resilience acceptance test: rejects a truncated packet and serves a later valid client."""
    packet = legacy_device.encrypt_payload(telemetry_payload, test_key)
    _send_and_close(running_gateway.port, packet[:20])
    _send_and_close(running_gateway.port, packet)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(telemetry_payload)
    assert running_gateway.process.poll() is None


def test_gateway_ignores_empty_connection_and_processes_later_valid_packet(
    running_gateway, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Robustness integration test: detects failure to continue after EOF occurs before any bytes."""
    _send_and_close(running_gateway.port, b"")
    packet = legacy_device.encrypt_payload(telemetry_payload, test_key)
    _send_and_close(running_gateway.port, packet)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(telemetry_payload)


def test_gateway_remains_available_after_two_packets_share_one_connection(
    running_gateway, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Resilience acceptance test: rejects an ambiguously framed connection without ending service."""
    first_packet = legacy_device.encrypt_payload(telemetry_payload, test_key)
    second_packet = legacy_device.encrypt_payload(telemetry_payload, test_key)
    _send_and_close(running_gateway.port, first_packet + second_packet)
    _send_and_close(running_gateway.port, first_packet)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(telemetry_payload)
    assert running_gateway.process.poll() is None


def test_gateway_rejects_authenticated_non_json_payload_and_processes_valid_packet(
    running_gateway, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Validation acceptance test: non-JSON plaintext must not be accepted as telemetry."""
    invalid_packet = _encrypt_plaintext(b'{"device_id":', test_key, fixed_nonce)
    valid_packet = legacy_device.encrypt_payload(telemetry_payload, test_key)
    _send_and_close(running_gateway.port, invalid_packet)
    _send_and_close(running_gateway.port, valid_packet)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(telemetry_payload)
    assert running_gateway.process.poll() is None


def test_gateway_rejects_wrong_telemetry_schema_and_processes_valid_packet(
    running_gateway, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Validation acceptance test: JSON missing required telemetry fields must be rejected."""
    wrong_schema = {"device_id": "sensor-node-01", "timestamp": 1_726_478_400}
    invalid_packet = _encrypt_plaintext(
        json.dumps(wrong_schema).encode("utf-8"), test_key, fixed_nonce
    )
    valid_packet = legacy_device.encrypt_payload(telemetry_payload, test_key)
    _send_and_close(running_gateway.port, invalid_packet)
    _send_and_close(running_gateway.port, valid_packet)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(telemetry_payload)
    assert running_gateway.process.poll() is None


def test_gateway_rejects_replayed_packet_and_processes_new_valid_packet(
    running_gateway, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Security acceptance test: replayed packets must not be processed a second time."""
    first_packet = legacy_device.encrypt_payload(telemetry_payload, test_key)
    next_payload = {**telemetry_payload, "timestamp": 1_726_478_401}
    next_packet = _encrypt_plaintext(
        json.dumps(next_payload).encode("utf-8"), test_key, bytes(range(1, 13))
    )
    _send_and_close(running_gateway.port, first_packet)

    first_received = running_gateway.wait_for_line("Received from device: ")
    assert first_received == "Received from device: " + json.dumps(telemetry_payload)

    _send_and_close(running_gateway.port, first_packet)
    _send_and_close(running_gateway.port, next_packet)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(next_payload)
    assert running_gateway.process.poll() is None


def test_gateway_decrypts_large_packet_received_across_multiple_chunks(
    running_gateway, test_key, fixed_nonce
) -> None:
    """Robustness integration test: detects failure to accumulate data beyond one recv(1024) chunk."""
    # Updated to include required telemetry fields so it passes schema validation after hardening
    payload = {
        "device_id": "sensor-node-01",
        "timestamp": 1_726_478_400,
        "temperature": 21.8,
        "humidity": 55.4,
        "status": "OK",
        "samples": "x" * 5_000,
    }
    packet = legacy_device.encrypt_payload(payload, test_key)
    _send_and_close(running_gateway.port, packet)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(payload)


def test_legacy_device_main_propagates_connection_refused_error(monkeypatch) -> None:
    """Negative integration test: detects any hidden fallback when the configured gateway is unavailable."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unavailable_endpoint:
        unavailable_endpoint.bind(("127.0.0.1", 0))
        unavailable_port = unavailable_endpoint.getsockname()[1]
        monkeypatch.setattr(legacy_device, "GATEWAY_PORT", unavailable_port)

        with pytest.raises(ConnectionRefusedError):
            legacy_device.main()


def test_gateway_startup_propagates_bind_failure(monkeypatch) -> None:
    """Negative integration test: detects any hidden fallback when the configured listen port is occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied_listener:
        occupied_listener.bind(("127.0.0.1", 0))
        occupied_listener.listen()
        monkeypatch.setattr(edge_gateway, "LISTEN_PORT", occupied_listener.getsockname()[1])

        with pytest.raises(OSError):
            edge_gateway.start_gateway()
