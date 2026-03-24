"""Unit tests for app/processing/filters.py.

Tests bandpass, notch, rectify wrappers and stateful live filter management.
Run with:
    python -m unittest tests.test_filters
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import numpy as np

from app.processing import filters
from app.core import config as CFG

_NCH    = 8
_LONG   = 300   # well above FILTER_MIN_SAMPLES_ORDER4 (27)
_SHORT  = 15    # between FILTER_MIN_SAMPLES_ORDER1 (9) and order-4 threshold (27)
_TINY   = 4     # below FILTER_MIN_SAMPLES_ORDER1 (9)


class TestButterbandpass(unittest.TestCase):

    def test_shape_preserved_long_data(self):
        x = np.random.randn(_NCH, _LONG)
        y = filters.butter_bandpass(x)
        self.assertEqual(y.shape, x.shape)

    def test_shape_preserved_short_data_order1_fallback(self):
        # Between 9 and 27 samples → order-1 fallback
        x = np.random.randn(_NCH, _SHORT)
        y = filters.butter_bandpass(x)
        self.assertEqual(y.shape, x.shape)

    def test_too_short_returns_original(self):
        # Fewer than FILTER_MIN_SAMPLES_ORDER1 samples → passthrough
        x = np.random.randn(_NCH, _TINY)
        y = filters.butter_bandpass(x)
        np.testing.assert_array_equal(y, x)

    def test_passband_preserved(self):
        # 100 Hz sine well inside 20–450 Hz passband
        fs = CFG.DEVICE_SAMPLE_RATE
        t  = np.linspace(0, 1, fs, endpoint=False)
        x  = np.tile(np.sin(2 * np.pi * 100 * t), (_NCH, 1))
        y  = filters.butter_bandpass(x)
        self.assertGreater(np.max(np.abs(y)), 0.5)

    def test_stopband_attenuated(self):
        # 5 Hz sine below 20 Hz cutoff — should be significantly attenuated
        fs = CFG.DEVICE_SAMPLE_RATE
        t  = np.linspace(0, 1, fs, endpoint=False)
        x  = np.tile(np.sin(2 * np.pi * 5 * t), (_NCH, 1))
        y  = filters.butter_bandpass(x)
        self.assertLess(np.max(np.abs(y)), 0.15)

    def test_accepts_legacy_kwargs(self):
        # Arguments low, high, fs, order are accepted but ignored
        x = np.random.randn(4, _LONG)
        y = filters.butter_bandpass(x, low=10, high=500, fs=1000, order=2)
        self.assertEqual(y.shape, x.shape)


class TestNotch(unittest.TestCase):

    def test_shape_preserved(self):
        x = np.random.randn(_NCH, _LONG)
        y = filters.notch(x)
        self.assertEqual(y.shape, x.shape)

    def test_too_short_returns_original(self):
        x = np.random.randn(_NCH, 10)   # below NOTCH_MIN_SAMPLES (15)
        y = filters.notch(x)
        np.testing.assert_array_equal(y, x)

    def test_notch_frequency_attenuated(self):
        # 60 Hz sine should be attenuated — check steady-state region (trim edges)
        fs = CFG.DEVICE_SAMPLE_RATE
        t  = np.linspace(0, 1, fs, endpoint=False)
        x  = np.tile(np.sin(2 * np.pi * 60 * t), (4, 1))
        y  = filters.notch(x)
        # Trim edge transients (first/last 200 samples) for steady-state check
        y_mid = y[:, 200:-200]
        self.assertLess(np.max(np.abs(y_mid)), 0.15)

    def test_accepts_legacy_kwargs(self):
        x = np.random.randn(4, _LONG)
        y = filters.notch(x, freq=60, fs=2000, quality=30)
        self.assertEqual(y.shape, x.shape)


class TestRectify(unittest.TestCase):

    def test_output_non_negative(self):
        x = np.random.randn(_NCH, 200)
        y = filters.rectify(x)
        self.assertTrue(np.all(y >= 0))

    def test_shape_preserved(self):
        x = np.random.randn(_NCH, 200)
        y = filters.rectify(x)
        self.assertEqual(y.shape, x.shape)

    def test_known_values(self):
        x = np.array([[-1.0, 2.0, -3.0]])
        y = filters.rectify(x)
        np.testing.assert_array_equal(y, [[1.0, 2.0, 3.0]])


class TestLiveFilters(unittest.TestCase):

    def setUp(self):
        filters.init_live_filters(CFG.DEVICE_CHANNELS)

    def test_init_creates_filter_instances(self):
        self.assertIsNotNone(filters._live_bp_filtered)
        self.assertIsNotNone(filters._live_bp_final)
        self.assertIsNotNone(filters._live_notch_final)

    def test_live_bp_output_shape(self):
        x = np.random.randn(CFG.DEVICE_CHANNELS, 125).astype(np.float64)
        y = filters._live_bp_filtered(x)
        self.assertEqual(y.shape, x.shape)

    def test_reset_zeroes_state(self):
        # Filter some data to build state, reset, then compare output
        # to a fresh filter on the same input — they should match.
        filters.init_live_filters(CFG.DEVICE_CHANNELS)
        x = np.random.randn(CFG.DEVICE_CHANNELS, 125).astype(np.float64)
        filters._live_bp_filtered(x)   # build up state

        filters.reset_live_filters()
        y_after_reset = filters._live_bp_filtered(x)

        filters.init_live_filters(CFG.DEVICE_CHANNELS)
        y_fresh = filters._live_bp_filtered(x)

        np.testing.assert_allclose(y_after_reset, y_fresh, atol=1e-8)

    def test_separate_instances_do_not_share_state(self):
        # Filtering through _live_bp_filtered should not affect _live_bp_final
        x = np.random.randn(CFG.DEVICE_CHANNELS, 125).astype(np.float64)
        _ = filters._live_bp_filtered(x)
        # _live_bp_final should produce identical output to a fresh filter
        filters.init_live_filters(CFG.DEVICE_CHANNELS)
        y_via_final    = filters._live_bp_final(x)
        y_via_filtered = filters._live_bp_filtered(x)
        # Both fresh — should match for the same input
        np.testing.assert_allclose(y_via_final, y_via_filtered, atol=1e-8)


if __name__ == '__main__':
    unittest.main()
