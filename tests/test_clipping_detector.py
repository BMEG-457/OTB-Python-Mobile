"""Tests for ADC rail clipping detection."""

import unittest
import numpy as np

from app.core import config as CFG
from app.processing.clipping_detector import ClippingDetector


class TestClippingDetectorConfig(unittest.TestCase):
    """Verify clipping config values are loaded."""

    def test_adc_rail_value(self):
        self.assertEqual(CFG.ADC_RAIL_VALUE, 32767)

    def test_clipping_fraction_threshold(self):
        self.assertAlmostEqual(CFG.CLIPPING_FRACTION_THRESHOLD, 0.01)


class TestClippingDetector(unittest.TestCase):
    """Test ClippingDetector.check() with synthetic data."""

    def setUp(self):
        self.detector = ClippingDetector()

    def test_normal_data_no_clipping(self):
        """Values well below rail should not trigger clipping."""
        data = np.random.randn(64, 125).astype(np.float32) * 1000
        result = self.detector.check(data)
        self.assertEqual(result, [])

    def test_all_channels_at_rail(self):
        """All channels saturated should all be flagged."""
        data = np.full((64, 125), 32767, dtype=np.float32)
        result = self.detector.check(data)
        self.assertEqual(len(result), 64)

    def test_single_channel_clipping(self):
        """Only the saturated channel should be flagged."""
        data = np.random.randn(64, 100).astype(np.float32) * 100
        # Set channel 5 to rail for all samples
        data[5, :] = 32767
        result = self.detector.check(data)
        self.assertIn(5, result)
        # Other channels should not be flagged
        for ch in result:
            if ch != 5:
                self.fail(f'Unexpected channel {ch} flagged')

    def test_negative_rail_detected(self):
        """Clipping at -32767 should also be detected."""
        data = np.random.randn(64, 100).astype(np.float32) * 100
        data[10, :] = -32767
        result = self.detector.check(data)
        self.assertIn(10, result)

    def test_below_threshold_not_flagged(self):
        """If only a tiny fraction of samples clip, should not flag."""
        data = np.random.randn(64, 1000).astype(np.float32) * 100
        # Set channel 3: only 5 out of 1000 samples at rail (0.5% < 1% threshold)
        data[3, :5] = 32767
        result = self.detector.check(data)
        self.assertNotIn(3, result)

    def test_above_threshold_flagged(self):
        """If >1% of samples clip, channel should be flagged."""
        data = np.random.randn(64, 100).astype(np.float32) * 100
        # Set channel 7: 5 out of 100 samples at rail (5% > 1% threshold)
        data[7, :5] = 32767
        result = self.detector.check(data)
        self.assertIn(7, result)

    def test_empty_samples(self):
        """Zero-width data should return empty list."""
        data = np.zeros((64, 0), dtype=np.float32)
        result = self.detector.check(data)
        self.assertEqual(result, [])

    def test_returns_sorted_indices(self):
        """Returned channel indices should be in ascending order."""
        data = np.full((64, 100), 32767, dtype=np.float32)
        result = self.detector.check(data)
        self.assertEqual(result, sorted(result))


if __name__ == '__main__':
    unittest.main()
