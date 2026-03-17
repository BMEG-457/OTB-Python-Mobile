"""Unit tests for app/managers/recording_manager.py.

Tests recording state machine, data capture (64 channels, relative timestamps),
overflow handling, and CSV export structure.
Run with:
    python -m unittest tests.test_recording_manager
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import tempfile
import unittest
import numpy as np
from unittest.mock import patch

from app.managers.recording_manager import RecordingManager
from app.core import config as CFG

_NCH = CFG.DEVICE_CHANNELS       # 72 total
_HDC = CFG.HDSEMG_CHANNELS       # 64 HD channels saved to CSV


def _make_data(nch=_NCH, samples=125):
    return np.random.randn(nch, samples).astype(np.float32)


class TestRecordingState(unittest.TestCase):

    def test_initial_state_not_recording(self):
        rm = RecordingManager()
        self.assertFalse(rm.is_recording)

    def test_start_recording_sets_flag(self):
        rm = RecordingManager()
        rm.start_recording()
        self.assertTrue(rm.is_recording)

    def test_start_recording_clears_previous_data(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data())
        rm.stop_recording()
        rm.start_recording()
        self.assertEqual(len(rm.recording_data), 0)

    def test_stop_recording_clears_flag(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.stop_recording()
        self.assertFalse(rm.is_recording)

    def test_start_returns_true(self):
        rm = RecordingManager()
        self.assertTrue(rm.start_recording())

    def test_stop_returns_true(self):
        rm = RecordingManager()
        rm.start_recording()
        self.assertTrue(rm.stop_recording())


class TestDataCapture(unittest.TestCase):

    def test_ignores_non_raw_stages(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('filtered', _make_data())
        rm.on_data_for_recording('rectified', _make_data())
        rm.on_data_for_recording('final', _make_data())
        self.assertEqual(len(rm.recording_data), 0)

    def test_ignores_data_when_not_recording(self):
        rm = RecordingManager()
        rm.on_data_for_recording('raw', _make_data())
        self.assertEqual(len(rm.recording_data), 0)

    def test_captures_correct_sample_count(self):
        rm = RecordingManager()
        rm.start_recording()
        data = _make_data(samples=50)
        rm.on_data_for_recording('raw', data)
        self.assertEqual(len(rm.recording_data), 50)

    def test_captures_64_channels_only(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=10))
        _, ch_data = rm.recording_data[0]
        self.assertEqual(len(ch_data), _HDC)

    def test_timestamps_are_non_negative(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=20))
        for ts, _ in rm.recording_data:
            self.assertGreaterEqual(ts, 0.0)

    def test_timestamps_are_relative_not_epoch(self):
        # Elapsed time for a quick test should be well under 1 second
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=10))
        ts, _ = rm.recording_data[0]
        self.assertLess(ts, 5.0)

    def test_channel_data_matches_first_64_channels(self):
        rm = RecordingManager()
        rm.start_recording()
        data = np.arange(_NCH * 1).reshape(_NCH, 1).astype(np.float32)
        rm.on_data_for_recording('raw', data)
        _, ch_data = rm.recording_data[0]
        np.testing.assert_array_equal(ch_data, data[:_HDC, 0])

    def test_multiple_calls_accumulate(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=30))
        rm.on_data_for_recording('raw', _make_data(samples=20))
        self.assertEqual(len(rm.recording_data), 50)


class TestOverflow(unittest.TestCase):

    def test_overflow_callback_called(self):
        triggered = []
        rm = RecordingManager(max_samples=5, on_overflow=lambda: triggered.append(1))
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=10))
        self.assertGreater(len(triggered), 0)

    def test_overflow_stops_accumulation_at_max(self):
        rm = RecordingManager(max_samples=10)
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=100))
        self.assertLessEqual(len(rm.recording_data), 10)

    def test_no_overflow_callback_when_none(self):
        # Should not raise even without a callback
        rm = RecordingManager(max_samples=5, on_overflow=None)
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=20))

    def test_already_full_does_not_add_more(self):
        rm = RecordingManager(max_samples=5)
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=10))
        count_after_first = len(rm.recording_data)
        rm.on_data_for_recording('raw', _make_data(samples=10))
        self.assertEqual(len(rm.recording_data), count_after_first)


class TestCSVSave(unittest.TestCase):

    def _record_and_save(self, samples=50):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=samples))
        rm.stop_recording()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('app.managers.recording_manager.get_recordings_dir', return_value=tmpdir):
                success, msg, filepath = rm.save_recording_to_csv()
        return success, msg, filepath, rm

    def test_save_returns_success(self):
        success, _, _, _ = self._record_and_save()
        self.assertTrue(success)

    def test_save_returns_filename(self):
        _, _, filepath, _ = self._record_and_save()
        self.assertIsNotNone(filepath)
        self.assertTrue(filepath.endswith('.csv'))

    def test_save_clears_recording_data(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=10))
        rm.stop_recording()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('app.managers.recording_manager.get_recordings_dir', return_value=tmpdir):
                rm.save_recording_to_csv()
        self.assertEqual(len(rm.recording_data), 0)

    def test_save_no_data_returns_failure(self):
        rm = RecordingManager()
        success, msg, filepath = rm.save_recording_to_csv()
        self.assertFalse(success)
        self.assertIsNone(filepath)

    def test_csv_has_correct_header(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=5))
        rm.stop_recording()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('app.managers.recording_manager.get_recordings_dir', return_value=tmpdir):
                _, _, filepath = rm.save_recording_to_csv()
            with open(filepath, newline='') as f:
                reader = csv.reader(f)
                header = next(reader)
        self.assertEqual(header[0], 'Timestamp')
        self.assertEqual(len(header), _HDC + 1)

    def test_csv_row_count_matches_samples(self):
        n = 30
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=n))
        rm.stop_recording()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('app.managers.recording_manager.get_recordings_dir', return_value=tmpdir):
                _, _, filepath = rm.save_recording_to_csv()
            with open(filepath, newline='') as f:
                rows = list(csv.reader(f))
        # First row is header
        self.assertEqual(len(rows) - 1, n)


class TestGetRecordingInfo(unittest.TestCase):

    def test_info_not_recording(self):
        rm = RecordingManager()
        info = rm.get_recording_info()
        self.assertFalse(info['is_recording'])
        self.assertEqual(info['num_samples'], 0)

    def test_info_while_recording(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=10))
        info = rm.get_recording_info()
        self.assertTrue(info['is_recording'])
        self.assertEqual(info['num_samples'], 10)
        self.assertIsNotNone(info['duration'])

    def test_clear_recording_data_empties_buffer(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', _make_data(samples=10))
        rm.clear_recording_data()
        self.assertEqual(len(rm.recording_data), 0)


if __name__ == '__main__':
    unittest.main()
