"""Real-time rolling-window EMG metrics for live streaming."""

import numpy as np
from app.core import config as CFG


class LiveMetricsComputer:
    """Stateful rolling-window metrics for a single channel.

    Maintains a circular buffer of recent samples. Every ``step_size``
    new samples, computes RMS, median frequency, and fatigue flags.

    Usage::

        mc = LiveMetricsComputer()
        mc.set_baseline(baseline_rms)   # after calibration
        result = mc.update(samples_1d)  # returns dict or None
    """

    def __init__(self):
        fs = CFG.DEVICE_SAMPLE_RATE
        self._fs = fs
        self._window_size = int(CFG.FEATURE_WINDOW_DURATION * fs)   # 1000
        self._step_size = int(CFG.FEATURE_STEP_DURATION * fs)       # 200

        # Circular buffer
        self._buf = np.zeros(self._window_size)
        self._buf_idx = 0       # next write position
        self._samples_total = 0  # total samples received (for step gating)
        self._samples_since_step = 0

        # Calibration baseline
        self._baseline_rms = None

        # Median frequency slope tracking (last N windows)
        self._mf_history_max = 10
        self._mf_history = []

    def set_baseline(self, rms_value):
        """Set calibration baseline RMS for fatigue detection."""
        self._baseline_rms = rms_value

    def reset(self):
        """Reset all state for a new streaming session."""
        self._buf[:] = 0.0
        self._buf_idx = 0
        self._samples_total = 0
        self._samples_since_step = 0
        self._baseline_rms = None
        self._mf_history.clear()

    def update(self, samples):
        """Feed new samples (1-D array) and return metrics when ready.

        Returns:
            dict with keys 'rms', 'median_freq', 'fatigue_rms', 'fatigue_mf'
            when a new step boundary is crossed, else None.
        """
        n = len(samples)
        ws = self._window_size

        # Write into circular buffer
        end = self._buf_idx + n
        if n >= ws:
            self._buf[:] = samples[-ws:]
            self._buf_idx = 0
        elif end <= ws:
            self._buf[self._buf_idx:end] = samples
            self._buf_idx = end % ws
        else:
            split = ws - self._buf_idx
            self._buf[self._buf_idx:] = samples[:split]
            self._buf[:n - split] = samples[split:]
            self._buf_idx = n - split

        self._samples_total += n
        self._samples_since_step += n

        # Only compute on step boundaries, and only after buffer is full
        if self._samples_since_step < self._step_size:
            return None
        self._samples_since_step = 0

        if self._samples_total < ws:
            return None

        # Linearise buffer
        idx = self._buf_idx
        if idx == 0:
            window = self._buf
        else:
            window = np.concatenate([self._buf[idx:], self._buf[:idx]])

        # RMS
        rms_val = float(np.sqrt(np.mean(window ** 2)))

        # Median frequency
        windowed = window * np.hamming(ws)
        spectrum = np.abs(np.fft.rfft(windowed)) ** 2
        freqs = np.fft.rfftfreq(ws, 1.0 / self._fs)
        cumsum = np.cumsum(spectrum)
        total = cumsum[-1]
        mf = float(freqs[np.searchsorted(cumsum, total / 2)]) if total > 0 else 0.0

        # Track MF history for slope
        self._mf_history.append(mf)
        if len(self._mf_history) > self._mf_history_max:
            self._mf_history.pop(0)

        # Fatigue flags
        fatigue_rms = False
        fatigue_mf = False

        if self._baseline_rms is not None and self._baseline_rms > 0:
            drop = (self._baseline_rms - rms_val) / self._baseline_rms
            if drop > CFG.FEATURE_FATIGUE_RMS_THRESHOLD:
                fatigue_rms = True

        if len(self._mf_history) >= 3:
            xs = np.arange(len(self._mf_history), dtype=float)
            slope = np.polyfit(xs, self._mf_history, 1)[0]
            if slope < CFG.FEATURE_FATIGUE_MF_THRESHOLD:
                fatigue_mf = True

        return {
            'rms': rms_val,
            'median_freq': mf,
            'fatigue_rms': fatigue_rms,
            'fatigue_mf': fatigue_mf,
        }
