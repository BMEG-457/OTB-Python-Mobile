"""Tests for disconnection notification in DataReceiverThread."""

import time
import unittest
from unittest.mock import MagicMock

from app.core import config as CFG
from app.data.data_receiver import DataReceiverThread


class TestDisconnectFields(unittest.TestCase):
    """Verify DataReceiverThread exposes disconnect-related fields."""

    def _make_thread(self):
        device = MagicMock()
        device.nchannels = 72
        device.frequency = 2000
        sock = MagicMock()
        sock.settimeout = MagicMock()
        return DataReceiverThread(
            device=device,
            client_socket=sock,
            on_stage=MagicMock(),
            on_error=MagicMock(),
            on_status=MagicMock(),
        )

    def test_initial_disconnect_warned_is_false(self):
        thread = self._make_thread()
        self.assertFalse(thread._disconnect_warned)

    def test_initial_on_disconnect_is_none(self):
        thread = self._make_thread()
        self.assertIsNone(thread.on_disconnect)

    def test_last_packet_time_initialized(self):
        thread = self._make_thread()
        self.assertIsNotNone(thread._last_packet_time)
        self.assertIsInstance(thread._last_packet_time, float)


class TestDisconnectConfigValue(unittest.TestCase):
    """Verify disconnect warning config is loaded correctly."""

    def test_disconnect_warning_sec(self):
        self.assertEqual(CFG.DISCONNECT_WARNING_SEC, 5)


class TestDisconnectLogic(unittest.TestCase):
    """Test the disconnect detection logic extracted from the socket.timeout handler."""

    @staticmethod
    def _simulate_timeout_check(running, disconnect_warned, last_packet_time,
                                 disconnect_sec, on_disconnect=None):
        """Replicate the disconnect detection logic from the socket.timeout handler."""
        fired = False
        if running and not disconnect_warned:
            elapsed = time.time() - last_packet_time
            if elapsed > disconnect_sec:
                disconnect_warned = True
                fired = True
                if on_disconnect:
                    on_disconnect(elapsed)
        return disconnect_warned, fired

    def test_fires_after_threshold(self):
        """Disconnect callback fires when elapsed > threshold."""
        callback = MagicMock()
        last_packet = time.time() - 6  # 6 seconds ago
        warned, fired = self._simulate_timeout_check(
            running=True, disconnect_warned=False,
            last_packet_time=last_packet, disconnect_sec=5,
            on_disconnect=callback,
        )
        self.assertTrue(warned)
        self.assertTrue(fired)
        callback.assert_called_once()
        elapsed_arg = callback.call_args[0][0]
        self.assertGreater(elapsed_arg, 5)

    def test_does_not_fire_when_not_running(self):
        """Disconnect callback should NOT fire when running=False."""
        callback = MagicMock()
        last_packet = time.time() - 10
        warned, fired = self._simulate_timeout_check(
            running=False, disconnect_warned=False,
            last_packet_time=last_packet, disconnect_sec=5,
            on_disconnect=callback,
        )
        self.assertFalse(warned)
        self.assertFalse(fired)
        callback.assert_not_called()

    def test_does_not_fire_twice(self):
        """Once warned, should not fire again until reset."""
        callback = MagicMock()
        last_packet = time.time() - 10
        warned, fired = self._simulate_timeout_check(
            running=True, disconnect_warned=True,
            last_packet_time=last_packet, disconnect_sec=5,
            on_disconnect=callback,
        )
        self.assertTrue(warned)
        self.assertFalse(fired)
        callback.assert_not_called()

    def test_does_not_fire_below_threshold(self):
        """No warning if elapsed time is below threshold."""
        callback = MagicMock()
        last_packet = time.time() - 2  # only 2 seconds ago
        warned, fired = self._simulate_timeout_check(
            running=True, disconnect_warned=False,
            last_packet_time=last_packet, disconnect_sec=5,
            on_disconnect=callback,
        )
        self.assertFalse(warned)
        self.assertFalse(fired)
        callback.assert_not_called()

    def test_fires_without_callback(self):
        """Logic works even if on_disconnect is None (no crash)."""
        warned, fired = self._simulate_timeout_check(
            running=True, disconnect_warned=False,
            last_packet_time=time.time() - 10, disconnect_sec=5,
            on_disconnect=None,
        )
        self.assertTrue(warned)
        self.assertTrue(fired)


if __name__ == '__main__':
    unittest.main()
