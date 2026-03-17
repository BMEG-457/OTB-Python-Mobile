"""Unit tests for TCP server/client handshake in app/core/device.py.

Verifies the socket accept handshake using a local loopback fake client.
No real device or WiFi required.
Run with:
    python -m unittest tests.test_networking
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import socket
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from app.core.device import SessantaquattroPlus

_HOST = '127.0.0.1'
_PORT = 45460   # offset from default to avoid conflicts with other tests


def _fake_client(host, port, delay=0.1):
    """Connect to host:port after a short delay, then disconnect."""
    time.sleep(delay)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((host, port))
    finally:
        s.close()


class TestTCPHandshake(unittest.TestCase):

    def setUp(self):
        self.dev = SessantaquattroPlus(host=_HOST, port=_PORT)

    def tearDown(self):
        self.dev.stop_server()

    def test_server_accepts_client_connection(self):
        """start_server() should return without error when a client connects."""
        t = threading.Thread(
            target=_fake_client, args=(_HOST, _PORT), daemon=True
        )
        with patch.object(self.dev, 'is_connected_to_device_network', return_value=True):
            t.start()
            try:
                self.dev.start_server(connection_timeout=5)
            except ConnectionError as e:
                self.fail(f"start_server raised ConnectionError unexpectedly: {e}")

    def test_client_socket_set_after_connect(self):
        t = threading.Thread(
            target=_fake_client, args=(_HOST, _PORT), daemon=True
        )
        with patch.object(self.dev, 'is_connected_to_device_network', return_value=True):
            t.start()
            self.dev.start_server(connection_timeout=5)
        self.assertIsNotNone(self.dev.client_socket)

    def test_raises_connection_error_when_not_on_wifi(self):
        with patch.object(self.dev, 'is_connected_to_device_network', return_value=False):
            with self.assertRaises(ConnectionError):
                self.dev.start_server(connection_timeout=1)

    def test_raises_connection_error_on_timeout(self):
        # Use a different port so no client ever connects
        dev2 = SessantaquattroPlus(host=_HOST, port=_PORT + 1)
        with patch.object(dev2, 'is_connected_to_device_network', return_value=True):
            with self.assertRaises(ConnectionError):
                dev2.start_server(connection_timeout=1)
        dev2.stop_server()

    def test_stop_server_clears_sockets(self):
        t = threading.Thread(
            target=_fake_client, args=(_HOST, _PORT), daemon=True
        )
        with patch.object(self.dev, 'is_connected_to_device_network', return_value=True):
            t.start()
            self.dev.start_server(connection_timeout=5)
        self.dev.stop_server()
        self.assertIsNone(self.dev.client_socket)
        self.assertIsNone(self.dev.server_socket)


class TestCommandSend(unittest.TestCase):

    def test_send_command_writes_2_bytes(self):
        dev = SessantaquattroPlus(host=_HOST, port=_PORT)
        mock_sock = MagicMock()
        dev.client_socket = mock_sock
        cmd = dev.create_command()
        dev.send_command(cmd)
        mock_sock.send.assert_called_once()
        sent = mock_sock.send.call_args[0][0]
        self.assertEqual(len(sent), 2)

    def test_send_command_raises_on_broken_socket(self):
        dev = SessantaquattroPlus(host=_HOST, port=_PORT)
        mock_sock = MagicMock()
        mock_sock.send.side_effect = OSError("broken pipe")
        dev.client_socket = mock_sock
        with self.assertRaises(Exception):
            dev.send_command(dev.create_command())


if __name__ == '__main__':
    unittest.main()
