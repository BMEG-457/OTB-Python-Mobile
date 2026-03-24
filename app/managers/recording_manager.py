"""Recording manager for handling EMG data recording and CSV export."""

import csv
from datetime import datetime
import json
import os
import time

from app.core.paths import get_recordings_dir
from app.core import config as CFG
from app.managers.session_history import SessionHistoryManager


class RecordingManager:
    """Manages recording state and CSV export for EMG data.

    Replaces the PyQt5 QObject-based desktop version. Instead of pyqtSignal,
    this class calls Python callbacks directly.

    Callbacks:
        on_overflow() — called when the sample buffer hits max_samples.
        on_status(message: str) — called for recording status updates.
    """

    def __init__(self, max_samples=None, on_overflow=None, on_status=None):
        self.recording_data = []
        self.recording_start_time = None
        self.max_recording_samples = max_samples if max_samples is not None else CFG.RECORDING_MAX_SAMPLES
        self.is_recording = False
        self.on_overflow = on_overflow
        self.on_status = on_status
        self.session_metadata = None
        self._session_history = SessionHistoryManager()

        # Autosave state
        self._autosave_file = None
        self._autosave_writer = None
        self._autosave_path = None
        self._sample_count = 0

    def set_metadata(self, metadata):
        """Set session metadata dict to be saved alongside the recording."""
        self.session_metadata = metadata

    def start_recording(self):
        """Start recording data with write-through autosave."""
        self.recording_data = []
        self.recording_start_time = time.time()
        self.is_recording = True
        self._sample_count = 0

        # Open autosave temp file for crash recovery
        try:
            recordings_dir = get_recordings_dir()
            os.makedirs(recordings_dir, exist_ok=True)
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._autosave_path = os.path.join(recordings_dir, f"_autosave_{ts_str}.csv")
            self._autosave_file = open(self._autosave_path, 'w', newline='')
            self._autosave_writer = csv.writer(self._autosave_file)
            header = ['Timestamp'] + [f'Channel_{i+1}' for i in range(CFG.HDSEMG_CHANNELS)]
            self._autosave_writer.writerow(header)
            self._autosave_file.flush()
        except Exception as e:
            print(f"[RECORDING] WARNING: Could not open autosave file: {e}")
            self._autosave_file = None
            self._autosave_writer = None
            self._autosave_path = None

        print("[RECORDING] Recording started with autosave — waiting for data...")
        return True

    def stop_recording(self):
        """Stop recording data."""
        print(f"[RECORDING] Recording stopped — {self._sample_count} samples on disk")
        self.is_recording = False
        return True

    def on_data_for_recording(self, stage_name, data):
        """Capture raw stage data from the receiver thread.

        Data is both kept in memory (for session summary) and written through
        to the autosave CSV on disk (for crash recovery with ≤5s data loss).

        Args:
            stage_name: Processing stage name ('raw', 'filtered', 'rectified', 'final').
            data: numpy array of shape (channels, samples).
        """
        if stage_name != 'raw':
            return

        if not self.is_recording:
            return

        try:
            if self._sample_count >= self.max_recording_samples:
                if self.on_overflow:
                    self.on_overflow()
                return

            num_samples = data.shape[1]
            current_time = time.time()

            if self._sample_count == 0:
                print(f"[RECORDING] First data received! Shape: {data.shape}, samples: {num_samples}")

            for sample_idx in range(num_samples):
                timestamp = current_time - self.recording_start_time
                sample_data = data[:CFG.HDSEMG_CHANNELS, sample_idx].copy()
                self.recording_data.append((timestamp, sample_data))
                self._sample_count += 1

                # Write through to autosave file
                if self._autosave_writer is not None:
                    self._autosave_writer.writerow(
                        [timestamp] + sample_data.tolist()
                    )

                if self._sample_count >= self.max_recording_samples:
                    if self.on_overflow:
                        self.on_overflow()
                    break

            # Flush to disk periodically (OS buffering handles the rest)
            if self._autosave_file is not None:
                self._autosave_file.flush()

        except Exception as e:
            print(f"[RECORDING] Error collecting data: {e}")

    def save_recording_to_csv(self):
        """Save recorded data to CSV file.

        If an autosave file exists, it is closed and renamed to the final
        filename. Otherwise falls back to writing from the in-memory buffer.

        Returns:
            tuple: (success: bool, message: str, filename: str or None)
        """
        if self._sample_count == 0 and not self.recording_data:
            self._close_autosave(delete=True)
            return False, "No data recorded", None

        try:
            recordings_dir = get_recordings_dir()
            os.makedirs(recordings_dir, exist_ok=True)

            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(recordings_dir, f"recording_{timestamp_str}.csv")

            # Close autosave file and rename to final path
            if self._autosave_file is not None:
                self._autosave_file.close()
                self._autosave_file = None

            if self._autosave_path and os.path.exists(self._autosave_path):
                os.rename(self._autosave_path, filename)
                self._autosave_path = None
            else:
                # Fallback: write from in-memory buffer
                num_channels = len(self.recording_data[0][1])
                with open(filename, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    header = ['Timestamp'] + [f'Channel_{i+1}' for i in range(num_channels)]
                    writer.writerow(header)
                    for timestamp, channel_data in self.recording_data:
                        row = [timestamp] + channel_data.tolist()
                        writer.writerow(row)

            num_samples = self._sample_count or len(self.recording_data)
            num_channels = CFG.HDSEMG_CHANNELS

            # Save JSON sidecar and session summary if metadata available
            metadata = self.session_metadata
            if metadata is not None:
                duration = self.recording_data[-1][0] if self.recording_data else 0.0
                sidecar = {
                    **metadata,
                    'recording_file': os.path.basename(filename),
                    'num_samples': num_samples,
                    'num_channels': num_channels,
                    'sample_rate': CFG.DEVICE_SAMPLE_RATE,
                    'duration_sec': round(duration, 3),
                    'saved_at': datetime.now().isoformat(),
                }
                meta_filename = filename.replace('.csv', '_meta.json')
                with open(meta_filename, 'w') as mf:
                    json.dump(sidecar, mf, indent=2)

                # Compute and append session summary for longitudinal tracking
                cal_info = metadata.get('calibration')
                try:
                    summary = SessionHistoryManager.compute_session_summary(
                        self.recording_data, metadata, cal_info
                    )
                    self._session_history.append_session(summary)
                except Exception as e:
                    print(f"[RECORDING] Session summary error: {e}")

                self.session_metadata = None

            message = f"Recording saved: {filename} ({num_samples} samples)"
            print(message)

            self.recording_data = []
            self.recording_start_time = None
            self._sample_count = 0

            return True, message, filename

        except Exception as e:
            error_msg = f"Error saving recording: {e}"
            print(error_msg)
            return False, error_msg, None

    def _close_autosave(self, delete=False):
        """Close the autosave file handle and optionally delete the temp file."""
        if self._autosave_file is not None:
            self._autosave_file.close()
            self._autosave_file = None
        self._autosave_writer = None
        if delete and self._autosave_path and os.path.exists(self._autosave_path):
            os.remove(self._autosave_path)
        self._autosave_path = None

    def clear_recording_data(self):
        """Clear all recorded data from memory and close autosave."""
        self._close_autosave(delete=True)
        self.recording_data = []
        self.recording_start_time = None
        self._sample_count = 0

    def get_recording_info(self):
        """Return dict with recording status information."""
        duration = None
        if self.recording_start_time is not None:
            duration = time.time() - self.recording_start_time
        return {
            'num_samples': self._sample_count,
            'duration': duration,
            'is_recording': self.is_recording,
            'max_samples': self.max_recording_samples,
        }

    @staticmethod
    def find_orphaned_autosaves():
        """Find autosave files left behind by a crash."""
        recordings_dir = get_recordings_dir()
        if not os.path.exists(recordings_dir):
            return []
        return [f for f in os.listdir(recordings_dir)
                if f.startswith('_autosave_') and f.endswith('.csv')]

    @staticmethod
    def recover_autosave(filename):
        """Rename an orphaned autosave to a recovered recording file.

        Returns:
            Path to the recovered file.
        """
        recordings_dir = get_recordings_dir()
        src = os.path.join(recordings_dir, filename)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(recordings_dir, f"recovered_{ts_str}.csv")
        os.rename(src, dst)
        return dst
