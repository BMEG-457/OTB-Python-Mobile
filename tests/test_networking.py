"""Phase 8.3 — networking smoke test.

Starts the TCP server and connects a fake client to verify the socket
handshake works correctly without needing the real device.

Run from mobile app/:
    python tests/test_networking.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import socket
import threading
import time
from unittest.mock import patch

from app.core.device import SessantaquattroPlus


def fake_device_client(host, port, delay=0.3):
    """Simulate the Sessantaquattro+ connecting after a short delay."""
    time.sleep(delay)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((host, port))
        print(f"[FakeDevice] Connected to {host}:{port}")
        time.sleep(0.1)
    finally:
        s.close()
        print("[FakeDevice] Disconnected")


device = SessantaquattroPlus(host='127.0.0.1', port=45454)

# Patch the network check so we don't need to be on the device's WiFi
with patch.object(device, 'is_connected_to_device_network', return_value=True):
    # Start the fake device client in background
    client_thread = threading.Thread(
        target=fake_device_client,
        args=('127.0.0.1', 45454),
        daemon=True,
    )
    client_thread.start()

    # start_server() should accept the fake client within 5 seconds
    try:
        device.start_server(connection_timeout=5)
        print("Server accepted connection OK")
    except ConnectionError as e:
        print(f"FAILED: {e}")
        sys.exit(1)
    finally:
        device.stop_server()

print("Networking test PASSED")
