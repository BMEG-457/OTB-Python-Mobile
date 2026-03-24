"""Session history manager for longitudinal tracking."""

import json
import os
import tempfile

import numpy as np

from app.core.paths import get_data_dir
from app.core import config as CFG


class SessionHistoryManager:
    """Persists session summaries and provides query helpers.

    Stores a JSON array of session summary dicts in ``session_history.json``
    inside the app data directory.
    """

    FILENAME = 'session_history.json'

    def __init__(self):
        self._dir = get_data_dir()
        self._path = os.path.join(self._dir, self.FILENAME)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_history(self):
        """Load and return the list of session summaries."""
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def append_session(self, summary):
        """Append a session summary and write atomically."""
        history = self.load_history()
        history.append(summary)
        # Trim to max sessions
        max_s = CFG.LONGITUDINAL_MAX_SESSIONS
        if len(history) > max_s:
            history = history[-max_s:]
        self._atomic_write(history)

    def _atomic_write(self, data):
        """Write JSON via temp file + rename for crash safety."""
        os.makedirs(self._dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2)
            # On Windows, target must not exist for os.rename
            if os.path.exists(self._path):
                os.replace(tmp, self._path)
            else:
                os.rename(tmp, self._path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    # ------------------------------------------------------------------
    # Session summary computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_session_summary(recording_data, metadata, calibration_info=None):
        """Compute a summary dict from recorded data and metadata.

        Args:
            recording_data: list of (timestamp, channel_data_1d) tuples.
            metadata: dict from SessionMetadataPopup.
            calibration_info: optional dict with baseline_rms, mvc_rms, threshold.

        Returns:
            dict suitable for JSON serialisation.
        """
        if not recording_data:
            return {**metadata, 'num_samples': 0}

        # Stack into (samples, channels) then transpose to (channels, samples)
        signals = np.array([s for _, s in recording_data])  # (samples, channels)
        signals = signals.T  # (channels, samples)
        n_channels = signals.shape[0]
        n_samples = signals.shape[1]

        # Per-channel RMS and MAV
        ch_rms = np.sqrt(np.mean(signals ** 2, axis=1))  # (channels,)
        ch_mav = np.mean(np.abs(signals), axis=1)

        best_ch = int(np.argmax(ch_mav))
        best_signal = signals[best_ch]

        # Median frequency on best channel
        from app.processing.features import median_frequency_window
        mf = median_frequency_window(best_signal, CFG.DEVICE_SAMPLE_RATE)

        # Simple fatigue detection: compare first-half RMS to second-half RMS
        half = n_samples // 2
        if half > 0:
            rms_first = float(np.sqrt(np.mean(best_signal[:half] ** 2)))
            rms_second = float(np.sqrt(np.mean(best_signal[half:] ** 2)))
            fatigue_detected = rms_second < rms_first * (1 - CFG.FEATURE_FATIGUE_RMS_THRESHOLD)
        else:
            rms_first = rms_second = 0.0
            fatigue_detected = False

        # Contraction count (if calibration threshold available)
        contraction_count = 0
        if calibration_info and calibration_info.get('threshold_means') is not None:
            thresh = calibration_info['threshold_means']
            if best_ch < len(thresh):
                th = thresh[best_ch]
                # Count threshold crossings (rising edge)
                above = (np.abs(best_signal) > th).astype(int)
                crossings = np.diff(above)
                contraction_count = int(np.sum(crossings == 1))

        duration = recording_data[-1][0] if recording_data else 0.0

        summary = {
            'date': metadata.get('date', ''),
            'subject_id': metadata.get('subject_id', ''),
            'muscle_group': metadata.get('muscle_group', ''),
            'exercise_type': metadata.get('exercise_type', ''),
            'notes': metadata.get('notes', ''),
            'num_samples': n_samples,
            'num_channels': n_channels,
            'duration_sec': round(duration, 3),
            'peak_rms': round(float(ch_rms.max()), 4),
            'mean_rms': round(float(ch_rms.mean()), 4),
            'best_channel': best_ch + 1,
            'best_channel_mav': round(float(ch_mav[best_ch]), 4),
            'median_frequency': round(mf, 2),
            'fatigue_detected': fatigue_detected,
            'rms_first_half': round(rms_first, 4),
            'rms_second_half': round(rms_second, 4),
            'contraction_count': contraction_count,
        }
        return summary

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_sessions_for_muscle(self, group):
        """Return sessions matching a muscle group."""
        return [s for s in self.load_history() if s.get('muscle_group') == group]

    def get_sessions_for_subject(self, subject_id):
        """Return sessions matching a subject ID."""
        return [s for s in self.load_history() if s.get('subject_id') == subject_id]
