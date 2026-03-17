"""Unit tests for the processing layer: filters and basic features.

Replaces the Phase 8.2 smoke-test script with proper unittest.TestCase classes.
Run with:
    python -m unittest tests.test_processing
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import numpy as np

from app.processing.filters import butter_bandpass, notch, rectify
from app.processing.features import rms, mav, integrated_emg
from app.core import config as CFG

_CHANNELS = CFG.DEVICE_CHANNELS   # 72
_SAMPLES  = 128
_FS       = CFG.DEVICE_SAMPLE_RATE


class TestFilterPipeline(unittest.TestCase):
    """End-to-end pipeline shape and property checks (72 ch, 128 samples)."""

    def setUp(self):
        rng = np.random.default_rng(0)
        self.data = rng.standard_normal((_CHANNELS, _SAMPLES)).astype(np.float32)

    def test_bandpass_shape(self):
        out = butter_bandpass(self.data)
        self.assertEqual(out.shape, (_CHANNELS, _SAMPLES))

    def test_notch_shape(self):
        filtered = butter_bandpass(self.data)
        out = notch(filtered)
        self.assertEqual(out.shape, (_CHANNELS, _SAMPLES))

    def test_rectify_shape(self):
        out = rectify(self.data)
        self.assertEqual(out.shape, (_CHANNELS, _SAMPLES))

    def test_rectify_non_negative(self):
        out = rectify(self.data)
        self.assertTrue(np.all(out >= 0))

    def test_full_pipeline_shape(self):
        filtered  = butter_bandpass(self.data)
        notched   = notch(filtered)
        rectified = rectify(notched)
        self.assertEqual(rectified.shape, (_CHANNELS, _SAMPLES))

    def test_full_pipeline_non_negative(self):
        filtered  = butter_bandpass(self.data)
        notched   = notch(filtered)
        rectified = rectify(notched)
        self.assertTrue(np.all(rectified >= 0))


class TestBasicFeaturesOnPipelineOutput(unittest.TestCase):
    """Feature shapes on realistic pipeline output (72 ch input)."""

    def setUp(self):
        rng  = np.random.default_rng(1)
        data = rng.standard_normal((_CHANNELS, _SAMPLES)).astype(np.float32)
        self.processed = rectify(butter_bandpass(data))

    def test_rms_shape(self):
        self.assertEqual(rms(self.processed).shape, (_CHANNELS, 1))

    def test_mav_shape(self):
        self.assertEqual(mav(self.processed).shape, (_CHANNELS, 1))

    def test_integrated_emg_shape(self):
        self.assertEqual(integrated_emg(self.processed).shape, (_CHANNELS, 1))

    def test_rms_non_negative(self):
        self.assertTrue(np.all(rms(self.processed) >= 0))

    def test_mav_non_negative(self):
        self.assertTrue(np.all(mav(self.processed) >= 0))

    def test_integrated_emg_non_negative(self):
        self.assertTrue(np.all(integrated_emg(self.processed) >= 0))


if __name__ == '__main__':
    unittest.main()
