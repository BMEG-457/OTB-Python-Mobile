"""Tests for latency monitoring in DataReceiverThread and LiveDataScreen."""

import time
import unittest

from app.core import config as CFG


class TestLatencyRollingWindow(unittest.TestCase):
    """Test the rolling-window latency computation used by LiveDataScreen._ui_tick."""

    @staticmethod
    def _compute_avg(window, new_value, max_size):
        """Replicate the rolling-window logic from _ui_tick."""
        window.append(new_value)
        if len(window) > max_size:
            window.pop(0)
        return sum(window) / len(window)

    def test_single_sample(self):
        window = []
        avg = self._compute_avg(window, 50.0, CFG.LATENCY_ROLLING_WINDOW)
        self.assertAlmostEqual(avg, 50.0)

    def test_window_fills_and_rolls(self):
        window = []
        max_size = 5
        for i in range(10):
            avg = self._compute_avg(window, 10.0, max_size)
        # Window should contain exactly max_size items
        self.assertEqual(len(window), max_size)
        # All values are 10.0 so avg should be 10.0
        self.assertAlmostEqual(avg, 10.0)

    def test_rolling_average_tracks_recent(self):
        window = []
        max_size = 3
        # Fill with 100s
        for _ in range(3):
            self._compute_avg(window, 100.0, max_size)
        # Now push 10s — old 100s should roll off
        for _ in range(3):
            avg = self._compute_avg(window, 10.0, max_size)
        self.assertAlmostEqual(avg, 10.0)

    def test_threshold_crossing(self):
        """Values above threshold should be detected."""
        window = []
        max_size = CFG.LATENCY_ROLLING_WINDOW
        threshold = CFG.LATENCY_WARNING_MS  # 100

        # All samples below threshold
        for _ in range(max_size):
            avg = self._compute_avg(window, 50.0, max_size)
        self.assertLessEqual(avg, threshold)

        # Push values above threshold — avg should eventually exceed
        window.clear()
        for _ in range(max_size):
            avg = self._compute_avg(window, 150.0, max_size)
        self.assertGreater(avg, threshold)

    def test_empty_window_first_packet(self):
        """First packet into an empty window should work."""
        window = []
        avg = self._compute_avg(window, 42.0, 10)
        self.assertEqual(len(window), 1)
        self.assertAlmostEqual(avg, 42.0)


class TestReceiverTimestamp(unittest.TestCase):
    """Test that DataReceiverThread exposes _pending_recv_time."""

    def test_initial_recv_time_is_none(self):
        """_pending_recv_time starts as None before any packet."""
        from unittest.mock import MagicMock
        from app.data.data_receiver import DataReceiverThread

        device = MagicMock()
        device.nchannels = 72
        device.frequency = 2000
        sock = MagicMock()
        sock.settimeout = MagicMock()

        thread = DataReceiverThread(
            device=device,
            client_socket=sock,
            on_stage=MagicMock(),
            on_error=MagicMock(),
            on_status=MagicMock(),
        )
        self.assertIsNone(thread._pending_recv_time)


class TestConfigValues(unittest.TestCase):
    """Verify safety config values are loaded correctly."""

    def test_latency_warning_ms(self):
        self.assertEqual(CFG.LATENCY_WARNING_MS, 100)

    def test_latency_rolling_window(self):
        self.assertEqual(CFG.LATENCY_ROLLING_WINDOW, 10)


if __name__ == '__main__':
    unittest.main()
