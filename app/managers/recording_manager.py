"""Recording manager for handling EMG data recording and CSV export."""

import csv
from datetime import datetime
import json
import os
import time

from app.core.paths import get_recordings_dir
from app.core import config as CFG


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

    def set_metadata(self, metadata):
        """Set session metadata dict to be saved alongside the recording."""
        self.session_metadata = metadata

    def start_recording(self):
        """Start recording data."""
        self.recording_data = []
        self.recording_start_time = time.time()
        self.is_recording = True
        print("[RECORDING] Recording started — waiting for data...")
        return True

    def stop_recording(self):
        """Stop recording data."""
        print(f"[RECORDING] Recording stopped — collected {len(self.recording_data)} samples")
        self.is_recording = False
        return True

    def on_data_for_recording(self, stage_name, data):
        """Capture raw stage data from the receiver thread.

        Args:
            stage_name: Processing stage name ('raw', 'filtered', 'rectified', 'final').
            data: numpy array of shape (channels, samples).
        """
        if stage_name != 'raw':
            return

        if not self.is_recording:
            return

        try:
            if len(self.recording_data) >= self.max_recording_samples:
                if self.on_overflow:
                    self.on_overflow()
                return

            num_samples = data.shape[1]
            current_time = time.time()

            if len(self.recording_data) == 0:
                print(f"[RECORDING] First data received! Shape: {data.shape}, samples: {num_samples}")

            for sample_idx in range(num_samples):
                timestamp = current_time - self.recording_start_time
                sample_data = data[:CFG.HDSEMG_CHANNELS, sample_idx].copy()
                self.recording_data.append((timestamp, sample_data))

                if len(self.recording_data) >= self.max_recording_samples:
                    if self.on_overflow:
                        self.on_overflow()
                    break

        except Exception as e:
            print(f"[RECORDING] Error collecting data: {e}")

    def save_recording_to_csv(self):
        """Save recorded data to CSV file.

        Returns:
            tuple: (success: bool, message: str, filename: str or None)
        """
        if not self.recording_data:
            return False, "No data recorded", None

        try:
            recordings_dir = get_recordings_dir()
            os.makedirs(recordings_dir, exist_ok=True)

            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(recordings_dir, f"recording_{timestamp_str}.csv")

            num_channels = len(self.recording_data[0][1])

            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                header = ['Timestamp'] + [f'Channel_{i+1}' for i in range(num_channels)]
                writer.writerow(header)
                for timestamp, channel_data in self.recording_data:
                    row = [timestamp] + channel_data.tolist()
                    writer.writerow(row)

            num_samples = len(self.recording_data)

            # Save JSON sidecar with metadata if available
            if self.session_metadata is not None:
                duration = self.recording_data[-1][0] if num_samples > 0 else 0.0
                sidecar = {
                    **self.session_metadata,
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
                self.session_metadata = None

            message = f"Recording saved: {filename} ({num_samples} samples)"
            print(message)

            self.recording_data = []
            self.recording_start_time = None

            return True, message, filename

        except Exception as e:
            error_msg = f"Error saving recording: {e}"
            print(error_msg)
            return False, error_msg, None

    def clear_recording_data(self):
        """Clear all recorded data from memory."""
        self.recording_data = []
        self.recording_start_time = None

    def get_recording_info(self):
        """Return dict with recording status information."""
        duration = None
        if self.recording_start_time is not None:
            duration = time.time() - self.recording_start_time
        return {
            'num_samples': len(self.recording_data),
            'duration': duration,
            'is_recording': self.is_recording,
            'max_samples': self.max_recording_samples,
        }
