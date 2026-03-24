"""Unit tests for app/processing/features.py.

Tests basic EMG features and all post-session analysis functions.
All tests run without device hardware or Kivy.
Run with:
    python -m unittest tests.test_features
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import numpy as np

from app.processing.features import (
    rms, mav, integrated_emg, median_frequency_window,
    compute_tkeo_activation_timing,
    compute_burst_duration,
    compute_bilateral_symmetry,
    compute_fatigue,
    compute_centroid_shift,
    compute_spatial_nonuniformity,
    _preprocess_timestamps,
)
from app.core import config as CFG

_FS = CFG.DEVICE_SAMPLE_RATE   # 2000 Hz


def _sine_signal(freq_hz, duration_s, fs=_FS, amplitude=1.0, noise=0.01, seed=0):
    """Return (signal, timestamps) for a sine burst preceded by baseline noise."""
    rng = np.random.default_rng(seed)
    n   = int(duration_s * fs)
    t   = np.arange(n) / fs
    sig = rng.normal(0, noise, n)
    sig += amplitude * np.sin(2 * np.pi * freq_hz * t)
    return sig, t


def _activation_signal(onset_s=0.7, offset_s=1.4, total_s=2.0, fs=_FS, seed=0):
    """Baseline noise with a clear sine burst between onset_s and offset_s."""
    rng   = np.random.default_rng(seed)
    n     = int(total_s * fs)
    t     = np.arange(n) / fs
    sig   = rng.normal(0, 0.01, n)
    on_i  = int(onset_s  * fs)
    off_i = int(offset_s * fs)
    sig[on_i:off_i] += np.sin(2 * np.pi * 100 * t[on_i:off_i]) * 1.0
    return sig, t


# ---------------------------------------------------------------------------
# Basic features
# ---------------------------------------------------------------------------

class TestBasicFeatures(unittest.TestCase):

    def setUp(self):
        self.data = np.random.randn(8, 200).astype(np.float32)

    def test_rms_shape(self):
        self.assertEqual(rms(self.data).shape, (8, 1))

    def test_rms_known_value(self):
        # RMS of a constant array of value c = c
        data = np.full((4, 100), 3.0)
        result = rms(data)
        np.testing.assert_allclose(result, 3.0, atol=1e-5)

    def test_mav_shape(self):
        self.assertEqual(mav(self.data).shape, (8, 1))

    def test_mav_known_value(self):
        data = np.array([[-1.0, 2.0, -3.0, 4.0]])
        result = mav(data)
        self.assertAlmostEqual(float(result[0, 0]), 2.5, places=5)

    def test_integrated_emg_shape(self):
        self.assertEqual(integrated_emg(self.data).shape, (8, 1))

    def test_integrated_emg_known_value(self):
        data = np.ones((2, 5))
        result = integrated_emg(data)
        np.testing.assert_allclose(result, 5.0, atol=1e-5)

    def test_median_frequency_localization(self):
        # Sine at 100 Hz → median frequency should be near 100 Hz
        fs  = _FS
        t   = np.linspace(0, 1, fs, endpoint=False)
        sig = np.sin(2 * np.pi * 100 * t)
        mf  = median_frequency_window(sig, fs)
        self.assertAlmostEqual(mf, 100.0, delta=5.0)


# ---------------------------------------------------------------------------
# Timestamp preprocessing
# ---------------------------------------------------------------------------

class TestPreprocessTimestamps(unittest.TestCase):

    def test_removes_nan(self):
        # Need >=30 valid samples after NaN removal for _preprocess_timestamps
        sig = np.arange(40, dtype=float)
        ts  = np.linspace(0, 1, 40)
        sig[5] = np.nan   # inject one NaN
        s2, t2 = _preprocess_timestamps(sig, ts)
        self.assertIsNotNone(s2)
        self.assertFalse(np.any(np.isnan(s2)))
        self.assertFalse(np.any(np.isnan(t2)))

    def test_too_short_returns_none(self):
        sig = np.ones(10)
        ts  = np.linspace(0, 1, 10)
        s2, t2 = _preprocess_timestamps(sig, ts)
        self.assertIsNone(s2)
        self.assertIsNone(t2)

    def test_enforces_monotonicity(self):
        sig = np.ones(50)
        ts  = np.concatenate([np.linspace(0, 0.5, 40), np.linspace(0.3, 1.0, 10)])
        s2, t2 = _preprocess_timestamps(sig, ts)
        if t2 is not None:
            self.assertTrue(np.all(np.diff(t2) > 0))


# ---------------------------------------------------------------------------
# TKEO activation timing
# ---------------------------------------------------------------------------

class TestTKEOActivationTiming(unittest.TestCase):

    def test_detects_known_onset(self):
        sig, t = _activation_signal(onset_s=0.7)
        result = compute_tkeo_activation_timing(sig, t, _FS)
        self.assertIsNotNone(result)
        self.assertGreater(len(result.onset_times), 0)
        # Detected onset should be within 0.3 s of the true onset
        self.assertTrue(any(abs(ot - 0.7) < 0.3 for ot in result.onset_times))

    def test_returns_none_on_too_short_signal(self):
        sig = np.random.randn(10)
        ts  = np.linspace(0, 0.01, 10)
        result = compute_tkeo_activation_timing(sig, ts, _FS)
        self.assertIsNone(result)

    def test_result_fields_present(self):
        sig, t = _activation_signal()
        result = compute_tkeo_activation_timing(sig, t, _FS)
        self.assertIsNotNone(result)
        self.assertTrue(hasattr(result, 'onset_times'))
        self.assertTrue(hasattr(result, 'tkeo_envelope'))
        self.assertTrue(hasattr(result, 'detection_threshold'))
        self.assertTrue(hasattr(result, 'backtrack_threshold'))

    def test_no_false_positives_on_pure_noise(self):
        # Low-amplitude white noise should produce no activations
        rng = np.random.default_rng(42)
        sig = rng.normal(0, 0.001, int(2 * _FS))
        t   = np.arange(len(sig)) / _FS
        result = compute_tkeo_activation_timing(sig, t, _FS)
        if result is not None:
            self.assertEqual(len(result.onset_times), 0)


# ---------------------------------------------------------------------------
# Burst duration
# ---------------------------------------------------------------------------

class TestBurstDuration(unittest.TestCase):

    def test_detects_burst(self):
        sig, t = _activation_signal(onset_s=0.7, offset_s=1.4)
        result = compute_burst_duration(sig, t, _FS)
        self.assertIsNotNone(result)
        self.assertGreater(result.num_bursts, 0)

    def test_burst_duration_positive(self):
        sig, t = _activation_signal()
        result = compute_burst_duration(sig, t, _FS)
        if result and result.num_bursts > 0:
            self.assertGreater(result.avg_duration, 0)
            self.assertTrue(np.all(result.burst_durations > CFG.FEATURE_MIN_BURST_DURATION))

    def test_returns_none_on_too_short(self):
        sig = np.random.randn(5)
        ts  = np.linspace(0, 0.005, 5)
        result = compute_burst_duration(sig, ts, _FS)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Bilateral symmetry
# ---------------------------------------------------------------------------

class TestBilateralSymmetry(unittest.TestCase):

    def _make_pair(self, amp1=1.0, amp2=1.0, n=1000, fs=200):
        t   = np.arange(n) / fs
        s1  = amp1 * np.sin(2 * np.pi * 10 * t)
        s2  = amp2 * np.sin(2 * np.pi * 10 * t)
        return s1, t, fs, s2, t, fs

    def test_symmetric_signals_si_near_zero(self):
        s1, t, fs, s2, *_ = self._make_pair(amp1=1.0, amp2=1.0)
        result = compute_bilateral_symmetry(s1, t, fs, s2, t, fs)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.mean_si, 0.0, places=4)

    def test_asymmetric_signals_si_nonzero(self):
        s1, t, fs, s2, *_ = self._make_pair(amp1=1.0, amp2=0.2)
        result = compute_bilateral_symmetry(s1, t, fs, s2, t, fs)
        self.assertIsNotNone(result)
        self.assertGreater(result.mean_si, 0.3)

    def test_si_bounded(self):
        s1, t, fs, s2, *_ = self._make_pair(amp1=1.0, amp2=0.5)
        result = compute_bilateral_symmetry(s1, t, fs, s2, t, fs)
        self.assertIsNotNone(result)
        self.assertTrue(np.all(result.symmetry_index >= -1.0))
        self.assertTrue(np.all(result.symmetry_index <=  1.0))

    def test_result_fields(self):
        s1, t, fs, s2, *_ = self._make_pair()
        result = compute_bilateral_symmetry(s1, t, fs, s2, t, fs)
        self.assertIsNotNone(result)
        for field in ('mean_si', 'std_si', 'max_asymmetry', 'rms_file1', 'rms_file2'):
            self.assertTrue(hasattr(result, field))


# ---------------------------------------------------------------------------
# Fatigue detection
# ---------------------------------------------------------------------------

class TestFatigue(unittest.TestCase):

    def test_returns_result_on_valid_signal(self):
        sig, t = _sine_signal(100, 4.0)
        result = compute_fatigue(sig, t, _FS)
        self.assertIsNotNone(result)

    def test_result_fields(self):
        sig, t = _sine_signal(100, 4.0)
        result = compute_fatigue(sig, t, _FS)
        self.assertIsNotNone(result)
        for field in ('rms_times', 'rms_values', 'mf_times', 'mf_values',
                      'baseline_rms', 'rms_threshold', 'mf_threshold'):
            self.assertTrue(hasattr(result, field))

    def test_rms_values_non_negative(self):
        sig, t = _sine_signal(100, 4.0)
        result = compute_fatigue(sig, t, _FS)
        if result is not None:
            self.assertTrue(np.all(result.rms_values >= 0))

    def test_returns_none_on_too_short(self):
        sig = np.random.randn(20)
        ts  = np.linspace(0, 0.01, 20)
        result = compute_fatigue(sig, ts, _FS)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Centroid shift
# ---------------------------------------------------------------------------

class TestCentroidShift(unittest.TestCase):

    def _make_64ch_data(self, n=2000, seed=0):
        rng  = np.random.default_rng(seed)
        data = rng.normal(0, 1.0, (64, n)).astype(np.float64)
        ts   = np.arange(n) / _FS
        return data, ts

    def test_returns_none_for_wrong_channel_count(self):
        data = np.random.randn(32, 2000)
        ts   = np.arange(2000) / _FS
        result = compute_centroid_shift(data, ts, _FS)
        self.assertIsNone(result)

    def test_returns_result_for_64_channels(self):
        data, ts = self._make_64ch_data()
        result = compute_centroid_shift(data, ts, _FS)
        self.assertIsNotNone(result)

    def test_centroid_within_grid_bounds(self):
        data, ts = self._make_64ch_data()
        result = compute_centroid_shift(data, ts, _FS)
        if result is not None:
            # Grid is 8 cols (0–7) × 8 rows (0–7)
            self.assertTrue(np.all(result.centroid_x >= 0))
            self.assertTrue(np.all(result.centroid_x <= 7))
            self.assertTrue(np.all(result.centroid_y >= 0))
            self.assertTrue(np.all(result.centroid_y <= 7))

    def test_displacement_non_negative(self):
        data, ts = self._make_64ch_data()
        result = compute_centroid_shift(data, ts, _FS)
        if result is not None:
            self.assertTrue(np.all(result.displacement >= 0))


# ---------------------------------------------------------------------------
# Spatial non-uniformity
# ---------------------------------------------------------------------------

class TestSpatialNonUniformity(unittest.TestCase):

    def _make_64ch_data(self, n=2000, seed=1):
        rng  = np.random.default_rng(seed)
        data = np.abs(rng.normal(0, 1.0, (64, n)))
        ts   = np.arange(n) / _FS
        return data, ts

    def test_returns_none_for_wrong_channel_count(self):
        data = np.random.randn(32, 2000)
        ts   = np.arange(2000) / _FS
        result = compute_spatial_nonuniformity(data, ts, _FS)
        self.assertIsNone(result)

    def test_returns_result_for_64_channels(self):
        data, ts = self._make_64ch_data()
        result = compute_spatial_nonuniformity(data, ts, _FS)
        self.assertIsNotNone(result)

    def test_cv_non_negative(self):
        data, ts = self._make_64ch_data()
        result = compute_spatial_nonuniformity(data, ts, _FS)
        if result is not None:
            self.assertTrue(np.all(result.cv >= 0))

    def test_entropy_bounded(self):
        data, ts = self._make_64ch_data()
        result = compute_spatial_nonuniformity(data, ts, _FS)
        if result is not None:
            # Shannon entropy for 64 channels is at most log2(64) = 6 bits
            self.assertTrue(np.all(result.entropy >= 0))
            self.assertTrue(np.all(result.entropy <= 6.01))

    def test_activation_fraction_bounded(self):
        data, ts = self._make_64ch_data()
        result = compute_spatial_nonuniformity(data, ts, _FS)
        if result is not None:
            self.assertTrue(np.all(result.activation_fraction >= 0))
            self.assertTrue(np.all(result.activation_fraction <= 1))

    def test_uniform_activation_high_entropy(self):
        # All channels equal → maximum entropy (all weight equal)
        n    = 2000
        data = np.ones((64, n))
        ts   = np.arange(n) / _FS
        result = compute_spatial_nonuniformity(data, ts, _FS)
        if result is not None:
            # Entropy should be near log2(64) = 6
            self.assertGreater(np.mean(result.entropy), 5.5)

    def test_focal_activation_low_entropy(self):
        # Only channel 0 active → entropy near zero
        n    = 2000
        data = np.zeros((64, n))
        data[0, :] = 1.0
        ts   = np.arange(n) / _FS
        result = compute_spatial_nonuniformity(data, ts, _FS)
        if result is not None:
            self.assertLess(np.mean(result.entropy), 1.0)


if __name__ == '__main__':
    unittest.main()
