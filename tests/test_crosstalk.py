"""Tests for crosstalk verification logic."""

import unittest
import numpy as np

from app.core import config as CFG


class TestCrosstalkConfig(unittest.TestCase):
    """Verify crosstalk config values are loaded."""

    def test_crosstalk_duration(self):
        self.assertEqual(CFG.CROSSTALK_DURATION, 3.0)

    def test_crosstalk_threshold_k(self):
        self.assertEqual(CFG.CROSSTALK_THRESHOLD_K, 3.0)


class TestCrosstalkEvaluation(unittest.TestCase):
    """Test the crosstalk evaluation logic used by CrosstalkVerificationPopup."""

    @staticmethod
    def _evaluate_crosstalk(test_rms, baseline_rms, threshold_k):
        """Replicate the evaluation logic from CrosstalkVerificationPopup."""
        threshold = baseline_rms + threshold_k * baseline_rms
        return np.where(test_rms > threshold)[0].tolist()

    def test_no_crosstalk_clean(self):
        """RMS during plantar flexion near baseline — no channels flagged."""
        baseline = np.ones(64) * 10.0
        test_rms = np.ones(64) * 12.0  # slightly above baseline, well below 4x
        flagged = self._evaluate_crosstalk(test_rms, baseline, threshold_k=3.0)
        self.assertEqual(flagged, [])

    def test_crosstalk_detected(self):
        """RMS far above baseline on some channels — those get flagged."""
        baseline = np.ones(64) * 10.0
        test_rms = np.ones(64) * 12.0
        # Channels 5, 10 have very high activation during plantar flexion
        test_rms[5] = 100.0
        test_rms[10] = 80.0
        flagged = self._evaluate_crosstalk(test_rms, baseline, threshold_k=3.0)
        # Threshold = 10 + 3*10 = 40. Channels 5 (100) and 10 (80) exceed.
        self.assertIn(5, flagged)
        self.assertIn(10, flagged)
        self.assertEqual(len(flagged), 2)

    def test_threshold_boundary_below(self):
        """RMS exactly at threshold should NOT be flagged (strictly greater)."""
        baseline = np.ones(64) * 10.0
        test_rms = np.ones(64) * 10.0
        # Threshold = 10 + 3*10 = 40. Set channel 0 to exactly 40.
        test_rms[0] = 40.0
        flagged = self._evaluate_crosstalk(test_rms, baseline, threshold_k=3.0)
        self.assertNotIn(0, flagged)

    def test_threshold_boundary_above(self):
        """RMS just above threshold should be flagged."""
        baseline = np.ones(64) * 10.0
        test_rms = np.ones(64) * 10.0
        test_rms[0] = 40.1
        flagged = self._evaluate_crosstalk(test_rms, baseline, threshold_k=3.0)
        self.assertIn(0, flagged)

    def test_all_channels_crosstalk(self):
        """All channels above threshold — all flagged."""
        baseline = np.ones(64) * 5.0
        test_rms = np.ones(64) * 100.0
        flagged = self._evaluate_crosstalk(test_rms, baseline, threshold_k=3.0)
        self.assertEqual(len(flagged), 64)

    def test_zero_baseline(self):
        """Zero baseline — any non-zero test RMS should be flagged."""
        baseline = np.zeros(64)
        test_rms = np.ones(64) * 0.1
        flagged = self._evaluate_crosstalk(test_rms, baseline, threshold_k=3.0)
        # Threshold = 0 + 3*0 = 0. Any test_rms > 0 flagged.
        self.assertEqual(len(flagged), 64)

    def test_custom_threshold_k(self):
        """Different threshold_k should change sensitivity."""
        baseline = np.ones(64) * 10.0
        test_rms = np.ones(64) * 10.0
        test_rms[3] = 35.0  # baseline + 2.5*baseline

        # With k=3: threshold=40, not flagged
        flagged_strict = self._evaluate_crosstalk(test_rms, baseline, threshold_k=3.0)
        self.assertNotIn(3, flagged_strict)

        # With k=2: threshold=30, flagged
        flagged_relaxed = self._evaluate_crosstalk(test_rms, baseline, threshold_k=2.0)
        self.assertIn(3, flagged_relaxed)


if __name__ == '__main__':
    unittest.main()
