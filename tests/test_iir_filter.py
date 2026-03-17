"""Unit tests for app/processing/iir_filter.py.

Tests the pure-numpy IIR filter implementations that replace scipy at runtime.
Run with:
    python -m unittest tests.test_iir_filter
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import numpy as np

from app.processing.iir_filter import (
    lfilter, filtfilt, find_peaks, resample_signal, StatefulIIRFilter
)
from app.core import config as CFG

# Simple 1st-order lowpass for use in structural tests: y[n] = 0.5*x[n] + 0.5*y[n-1]
_B1 = [0.5]
_A1 = [1.0, -0.5]

# 4th-order bandpass from config — used for signal-quality tests
_BP_B = CFG.BANDPASS_4_B
_BP_A = CFG.BANDPASS_4_A


class TestLFilter(unittest.TestCase):

    def test_1d_output_shape(self):
        x = np.ones(100)
        y = lfilter(_B1, _A1, x)
        self.assertEqual(y.shape, x.shape)

    def test_2d_output_shape(self):
        x = np.random.randn(8, 200).astype(np.float32)
        y = lfilter(_B1, _A1, x)
        self.assertEqual(y.shape, x.shape)

    def test_dc_step_response(self):
        # Step input → output should converge toward 1.0 (DC gain = 0.5/(1-0.5) = 1)
        x = np.ones(200)
        y = lfilter(_B1, _A1, x)
        self.assertAlmostEqual(float(y[-1]), 1.0, places=3)

    def test_zero_input_zero_output(self):
        x = np.zeros(50)
        y = lfilter(_B1, _A1, x)
        np.testing.assert_array_equal(y, x)

    def test_normalized_leading_coefficient(self):
        # Coefficients with a[0] != 1 should be normalised automatically
        b = [1.0, 0.0]
        a = [2.0, -1.0]   # equiv to [1, -0.5] after normalisation
        x = np.ones(100)
        y = lfilter(b, a, x)
        self.assertEqual(y.shape, x.shape)

    def test_2d_channels_processed_independently(self):
        # Channel 0 = all ones, channel 1 = all zeros → different outputs
        x = np.zeros((2, 100))
        x[0, :] = 1.0
        y = lfilter(_B1, _A1, x)
        self.assertGreater(float(y[0, -1]), 0.9)   # converged toward 1
        self.assertAlmostEqual(float(y[1, -1]), 0.0, places=6)


class TestFiltFilt(unittest.TestCase):

    def test_output_shape_1d(self):
        x = np.random.randn(500)
        y = filtfilt(_BP_B, _BP_A, x)
        self.assertEqual(y.shape, x.shape)

    def test_output_shape_2d(self):
        x = np.random.randn(8, 500)
        y = filtfilt(_BP_B, _BP_A, x)
        self.assertEqual(y.shape, x.shape)

    def test_zero_phase_symmetry(self):
        # A symmetric signal filtered with filtfilt should remain symmetric
        n = 500
        t = np.linspace(0, 1, n)
        x = np.sin(2 * np.pi * 100 * t)
        # Mirror x around its centre
        x_sym = np.concatenate([x, x[::-1]])
        mid = len(x_sym) // 2
        y = filtfilt(_BP_B, _BP_A, x_sym)
        # The output should also be (approximately) symmetric around the midpoint
        np.testing.assert_allclose(y[:mid], y[mid:][::-1], atol=1e-4)

    def test_passband_signal_preserved(self):
        # A 100 Hz sine (inside 20-450 Hz passband) should pass with amplitude > 0.5
        fs = CFG.DEVICE_SAMPLE_RATE
        t = np.linspace(0, 1, fs, endpoint=False)
        x = np.sin(2 * np.pi * 100 * t)
        y = filtfilt(_BP_B, _BP_A, x)
        self.assertGreater(np.max(np.abs(y)), 0.5)

    def test_stopband_signal_attenuated(self):
        # A 5 Hz sine (below 20 Hz cutoff) should be heavily attenuated
        fs = CFG.DEVICE_SAMPLE_RATE
        t = np.linspace(0, 1, fs, endpoint=False)
        x = np.sin(2 * np.pi * 5 * t)
        y = filtfilt(_BP_B, _BP_A, x)
        self.assertLess(np.max(np.abs(y)), 0.1)

    def test_short_signal_falls_back_to_causal(self):
        # Signal shorter than padlen → causal lfilter fallback, no crash
        x = np.ones(5)
        y = filtfilt(_B1, _A1, x)
        self.assertEqual(y.shape, x.shape)


class TestFindPeaks(unittest.TestCase):

    def test_detects_single_peak(self):
        x = np.array([0.0, 0.5, 1.0, 0.5, 0.0])
        indices, _ = find_peaks(x)
        self.assertIn(2, indices)

    def test_height_filter(self):
        x = np.array([0.0, 0.3, 0.0, 0.0, 0.8, 0.0])
        indices, _ = find_peaks(x, height=0.5)
        self.assertNotIn(1, indices)
        self.assertIn(4, indices)

    def test_distance_keeps_tallest(self):
        # Two peaks within distance → only the taller survives
        x = np.array([0.0, 0.6, 0.0, 0.0, 1.0, 0.0, 0.0])
        indices, _ = find_peaks(x, distance=4)
        self.assertEqual(len(indices), 1)
        self.assertIn(4, indices)

    def test_distance_keeps_both_when_separated(self):
        x = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0])
        indices, _ = find_peaks(x, distance=3)
        self.assertEqual(len(indices), 2)

    def test_empty_signal(self):
        indices, props = find_peaks(np.zeros(10))
        self.assertEqual(len(indices), 0)
        self.assertEqual(props, {})

    def test_no_peaks(self):
        indices, _ = find_peaks(np.array([1.0, 0.5, 0.0]))
        self.assertEqual(len(indices), 0)

    def test_returns_sorted_indices(self):
        x = np.array([0, 1, 0, 0, 1, 0, 0, 1, 0], dtype=float)
        indices, _ = find_peaks(x)
        self.assertEqual(list(indices), sorted(indices))


class TestResampleSignal(unittest.TestCase):

    def test_upsample_length(self):
        x = np.linspace(0, 1, 100)
        y = resample_signal(x, 200)
        self.assertEqual(len(y), 200)

    def test_downsample_length(self):
        x = np.linspace(0, 1, 200)
        y = resample_signal(x, 50)
        self.assertEqual(len(y), 50)

    def test_same_length_returns_copy(self):
        x = np.array([1.0, 2.0, 3.0])
        y = resample_signal(x, 3)
        np.testing.assert_array_equal(y, x)

    def test_endpoints_preserved(self):
        x = np.linspace(0, 10, 100)
        y = resample_signal(x, 50)
        self.assertAlmostEqual(y[0],  0.0, places=5)
        self.assertAlmostEqual(y[-1], 10.0, places=5)


class TestStatefulIIRFilter(unittest.TestCase):

    def test_output_shape(self):
        filt = StatefulIIRFilter(_BP_B, _BP_A, n_channels=8)
        x = np.random.randn(8, 125).astype(np.float64)
        y = filt(x)
        self.assertEqual(y.shape, x.shape)

    def test_state_persists_across_calls(self):
        # Split a signal and filter it in two chunks vs. in one pass
        filt_chunked = StatefulIIRFilter(_B1, _A1, n_channels=1)
        filt_single  = StatefulIIRFilter(_B1, _A1, n_channels=1)
        x = np.random.randn(1, 200).astype(np.float64)
        y_single = filt_single(x)
        y_chunk  = np.concatenate([filt_chunked(x[:, :100]),
                                   filt_chunked(x[:, 100:])], axis=1)
        np.testing.assert_allclose(y_chunk, y_single, atol=1e-5)

    def test_reset_clears_state(self):
        filt = StatefulIIRFilter(_B1, _A1, n_channels=1)
        x = np.ones((1, 100), dtype=np.float64)
        # Filter once to build up state
        filt(x)
        # Reset then filter again — should match a fresh filter from zero
        filt.reset()
        y_after_reset = filt(x)
        filt2 = StatefulIIRFilter(_B1, _A1, n_channels=1)
        y_fresh = filt2(x)
        np.testing.assert_allclose(y_after_reset, y_fresh, atol=1e-10)

    def test_multi_channel_independence(self):
        filt = StatefulIIRFilter(_B1, _A1, n_channels=4)
        x = np.zeros((4, 100), dtype=np.float64)
        x[0, :] = 1.0   # only channel 0 active
        y = filt(x)
        # Channels 1–3 should remain at zero
        np.testing.assert_allclose(y[1:], 0.0, atol=1e-10)
        self.assertGreater(float(y[0, -1]), 0.9)  # channel 0 converged to 1


if __name__ == '__main__':
    unittest.main()
