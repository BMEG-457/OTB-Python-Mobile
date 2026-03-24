"""Tests for autosave buffer in RecordingManager."""

import csv
import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from app.core import config as CFG
from app.managers.recording_manager import RecordingManager


class _TempDirMixin:
    """Mixin that patches get_recordings_dir to use a temp directory."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch(
            'app.managers.recording_manager.get_recordings_dir',
            return_value=self._tmpdir,
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        # Clean up temp files
        for f in os.listdir(self._tmpdir):
            os.remove(os.path.join(self._tmpdir, f))
        os.rmdir(self._tmpdir)


class TestAutosaveFileCreation(_TempDirMixin, unittest.TestCase):
    """Verify autosave temp file is created on start_recording."""

    def test_autosave_file_created(self):
        rm = RecordingManager()
        rm.start_recording()
        self.assertIsNotNone(rm._autosave_path)
        self.assertTrue(os.path.exists(rm._autosave_path))
        self.assertTrue(os.path.basename(rm._autosave_path).startswith('_autosave_'))
        rm._close_autosave(delete=True)

    def test_autosave_has_header(self):
        rm = RecordingManager()
        rm.start_recording()
        path = rm._autosave_path
        rm._close_autosave()
        with open(path, newline='') as f:
            reader = csv.reader(f)
            header = next(reader)
        self.assertEqual(header[0], 'Timestamp')
        self.assertEqual(len(header), CFG.HDSEMG_CHANNELS + 1)
        os.remove(path)


class TestAutosaveWriteThrough(_TempDirMixin, unittest.TestCase):
    """Verify data is written to disk as it arrives."""

    def _make_packet(self, n_channels=72, n_samples=10, value=100.0):
        return np.full((n_channels, n_samples), value, dtype=np.float32)

    def test_data_written_to_autosave(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', self._make_packet())
        path = rm._autosave_path
        rm._close_autosave()

        with open(path, newline='') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        self.assertEqual(len(rows), 10)  # 10 samples
        # Each row should have timestamp + 64 channels
        self.assertEqual(len(rows[0]), CFG.HDSEMG_CHANNELS + 1)
        os.remove(path)

    def test_sample_count_tracks_correctly(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', self._make_packet(n_samples=5))
        rm.on_data_for_recording('raw', self._make_packet(n_samples=3))
        self.assertEqual(rm._sample_count, 8)
        self.assertEqual(len(rm.recording_data), 8)
        rm._close_autosave(delete=True)

    def test_non_raw_stages_ignored(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('filtered', self._make_packet())
        rm.on_data_for_recording('final', self._make_packet())
        self.assertEqual(rm._sample_count, 0)
        rm._close_autosave(delete=True)


class TestAutosaveSave(_TempDirMixin, unittest.TestCase):
    """Verify save renames autosave to final file."""

    def _make_packet(self, n_channels=72, n_samples=5, value=50.0):
        return np.full((n_channels, n_samples), value, dtype=np.float32)

    def test_save_renames_autosave(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', self._make_packet())
        rm.stop_recording()
        success, message, filename = rm.save_recording_to_csv()
        self.assertTrue(success)
        self.assertIsNotNone(filename)
        self.assertTrue(os.path.exists(filename))
        self.assertTrue(os.path.basename(filename).startswith('recording_'))
        # Autosave should be gone
        autosaves = [f for f in os.listdir(self._tmpdir) if f.startswith('_autosave_')]
        self.assertEqual(len(autosaves), 0)

    def test_save_csv_content_correct(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.on_data_for_recording('raw', self._make_packet(value=42.0))
        rm.stop_recording()
        success, _, filename = rm.save_recording_to_csv()
        self.assertTrue(success)
        with open(filename, newline='') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        self.assertEqual(header[0], 'Timestamp')
        self.assertEqual(len(rows), 5)
        # Check a channel value
        self.assertAlmostEqual(float(rows[0][1]), 42.0, places=1)

    def test_save_with_no_data(self):
        rm = RecordingManager()
        rm.start_recording()
        rm.stop_recording()
        success, message, filename = rm.save_recording_to_csv()
        self.assertFalse(success)
        self.assertIsNone(filename)


class TestAutosaveOverflow(_TempDirMixin, unittest.TestCase):
    """Verify overflow still works with autosave."""

    def test_overflow_stops_at_max(self):
        overflow_called = []
        rm = RecordingManager(
            max_samples=10,
            on_overflow=lambda: overflow_called.append(True),
        )
        rm.start_recording()
        data = np.ones((72, 20), dtype=np.float32)
        rm.on_data_for_recording('raw', data)
        self.assertEqual(rm._sample_count, 10)
        self.assertTrue(overflow_called)
        rm._close_autosave(delete=True)


class TestOrphanRecovery(_TempDirMixin, unittest.TestCase):
    """Verify orphaned autosave detection and recovery."""

    def test_find_orphaned_autosaves(self):
        # Create a fake orphaned autosave
        orphan = os.path.join(self._tmpdir, '_autosave_20260101_120000.csv')
        with open(orphan, 'w') as f:
            f.write('Timestamp,Channel_1\n0.0,100\n')
        with patch('app.managers.recording_manager.get_recordings_dir',
                   return_value=self._tmpdir):
            found = RecordingManager.find_orphaned_autosaves()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0], '_autosave_20260101_120000.csv')

    def test_recover_autosave(self):
        orphan_name = '_autosave_20260101_120000.csv'
        orphan = os.path.join(self._tmpdir, orphan_name)
        with open(orphan, 'w') as f:
            f.write('Timestamp,Channel_1\n0.0,100\n')
        with patch('app.managers.recording_manager.get_recordings_dir',
                   return_value=self._tmpdir):
            recovered = RecordingManager.recover_autosave(orphan_name)
        self.assertTrue(os.path.exists(recovered))
        self.assertTrue(os.path.basename(recovered).startswith('recovered_'))
        self.assertFalse(os.path.exists(orphan))

    def test_no_orphans_when_clean(self):
        with patch('app.managers.recording_manager.get_recordings_dir',
                   return_value=self._tmpdir):
            found = RecordingManager.find_orphaned_autosaves()
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
