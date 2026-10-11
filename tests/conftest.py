"""Shared pytest fixtures for the legacy device/gateway tests."""

from __future__ import annotations

import queue
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = PROJECT_ROOT / "src"
# FIX: insert BOTH project root and src/ so `import pqc_utils` and `import src.pqc_utils` both work in CI
# Previously only src/ was in path, so fallback `from src.pqc_utils import ...` inside edge_gateway failed with No module named 'src'
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SOURCE_DIRECTORY))

import edge_gateway  # noqa: E402
import legacy_device  # noqa: E402


class GatewayProcess:
    """A gateway subprocess whose stdout can be awaited line-by-line."""

    def __init__(self, process: subprocess.Popen[str], port: int) -> None:
        self.process = process
        self.port = port
        self._lines: queue.Queue[str] = queue.Queue()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._lines.put(line.rstrip("\n"))

    def wait_for_line(self, expected_prefix: str, timeout: float = 3.0) -> str:
        """Return the next output line starting with ``expected_prefix``."""
        try:
            while True:
                line = self._lines.get(timeout=timeout)
                if line.startswith(expected_prefix):
                    return line
        except queue.Empty as error:
            exit_status = self.process.poll()
            raise AssertionError(
                f"Gateway did not emit output beginning {expected_prefix!r}; "
                f"process exit status: {exit_status!r}"
            ) from error

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.process.stdout is not None:
            self.process.stdout.close()
        self._reader.join(timeout=3)

@pytest.fixture
def test_key() -> bytes:
    """The AES-128 key used by both existing production modules."""
    return b"legacy_secret_16"


@pytest.fixture
def telemetry_payload() -> dict[str, object]:
    """A time-independent, JSON-serializable telemetry payload."""
    return {
        "device_id": "sensor-node-01",
        "timestamp": 1_726_478_400,
        "temperature": 21.8,
        "humidity": 55.4,
        "status": "OK",
    }


@pytest.fixture
def fixed_nonce(monkeypatch: pytest.MonkeyPatch) -> bytes:
    """Make encryption packet layout deterministic for tests that need it."""
    nonce = bytes(range(12))
    monkeypatch.setattr(legacy_device.os, "urandom", lambda size: nonce)
    return nonce


@pytest.fixture
def available_loopback_port() -> Iterator[int]:
    """Reserve then release an ephemeral loopback port for one gateway process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    yield port


@pytest.fixture
def running_gateway(available_loopback_port: int) -> Iterator[GatewayProcess]:
    """Start the unmodified gateway code on an isolated loopback port."""
    launcher = (
        "import edge_gateway; "
        f"edge_gateway.LISTEN_PORT = {available_loopback_port}; "
        "edge_gateway.start_gateway()"
    )
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", launcher],
        cwd=SOURCE_DIRECTORY,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    gateway = GatewayProcess(process, available_loopback_port)
    try:
        gateway.wait_for_line("Edge Gateway listening for legacy devices")
        yield gateway
    finally:
        gateway.stop()
