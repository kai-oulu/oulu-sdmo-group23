"""Core deterministic unit tests for the legacy device and edge gateway."""

import json

import edge_gateway
import legacy_device


def test_generate_telemetry_returns_expected_schema_and_values(monkeypatch) -> None:
    """Unit test: fixes the emitted telemetry contract and detects changed fields or values."""
    monkeypatch.setattr(legacy_device.time, "time", lambda: 1_726_478_400.9)

    telemetry = legacy_device.generate_telemetry()

    assert telemetry == {
        "device_id": "sensor-node-01",
        "timestamp": 1_726_478_400,
        "temperature": 21.8,
        "humidity": 55.4,
        "status": "OK",
    }


def test_encrypt_then_decrypt_round_trips_telemetry_as_json_text(
    telemetry_payload, test_key, fixed_nonce
) -> None:
    """Unit test: verifies endpoint crypto interoperability and detects wire-format drift."""
    packet = legacy_device.encrypt_payload(telemetry_payload, test_key)

    decrypted_text = edge_gateway.decrypt_payload(packet, test_key)

    assert decrypted_text == json.dumps(telemetry_payload)


def test_encrypt_payload_prepends_generated_12_byte_nonce(
    telemetry_payload, test_key, fixed_nonce
) -> None:
    """Unit test: verifies packet nonce placement and detects incompatible packet framing."""
    packet = legacy_device.encrypt_payload(telemetry_payload, test_key)

    assert packet[:12] == fixed_nonce
    assert len(packet) > 12


def test_encrypt_then_decrypt_round_trips_empty_dictionary(test_key, fixed_nonce) -> None:
    """Unit edge-case test: supports a minimal JSON object and detects empty-object regressions."""
    packet = legacy_device.encrypt_payload({}, test_key)

    assert edge_gateway.decrypt_payload(packet, test_key) == "{}"


def test_encrypt_then_decrypt_round_trips_unicode_payload(test_key, fixed_nonce) -> None:
    """Unit edge-case test: verifies JSON/UTF-8 handling and detects text encoding corruption."""
    payload = {"device_id": "sensor-node-åäö", "status": "正常"}
    packet = legacy_device.encrypt_payload(payload, test_key)

    assert edge_gateway.decrypt_payload(packet, test_key) == json.dumps(payload)
