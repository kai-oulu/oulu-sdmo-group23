"""Real loopback TCP integration tests for the gateway's core message flow."""

import json
import socket

import legacy_device


def test_legacy_device_main_sends_telemetry_to_gateway_over_tcp(
    monkeypatch, running_gateway, fixed_nonce
) -> None:
    """Integration test: checks client/gateway interoperability and detects connection/send failures."""
    monkeypatch.setattr(legacy_device, "GATEWAY_PORT", running_gateway.port)
    monkeypatch.setattr(legacy_device.time, "time", lambda: 1_726_478_400)

    legacy_device.main()

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == (
        "Received from device: "
        + json.dumps(
            {
                "device_id": "sensor-node-01",
                "timestamp": 1_726_478_400,
                "temperature": 21.8,
                "humidity": 55.4,
                "status": "OK",
            }
        )
    )


def test_gateway_reassembles_fragmented_tcp_packet(
    running_gateway, telemetry_payload, test_key, fixed_nonce
) -> None:
    """Robustness integration test: checks TCP reassembly and detects chunk-boundary assumptions."""
    packet = legacy_device.encrypt_payload(telemetry_payload, test_key)

    with socket.create_connection(("127.0.0.1", running_gateway.port), timeout=3) as client:
        client.sendall(packet[:1])
        client.sendall(packet[1:13])
        client.sendall(packet[13:])
        client.shutdown(socket.SHUT_WR)

    received = running_gateway.wait_for_line("Received from device: ")
    assert received == "Received from device: " + json.dumps(telemetry_payload)
