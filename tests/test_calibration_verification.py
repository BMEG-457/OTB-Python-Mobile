"""Tests for the calibration verification phase logic."""

import unittest
import numpy as np

from app.core import config as CFG


class TestCalibrationVerifyConfig(unittest.TestCase):
    """Verify calibration verification config values are loaded."""

    def test_verify_duration(self):
        self.assertEqual(CFG.CALIBRATION_VERIFY_DURATION, 3.0)

    def test_verify_active_fraction(self):
        self.assertEqual(CFG.CALIBRATION_VERIFY_ACTIVE_FRAC, 0.25)


class TestVerificationConcentration(unittest.TestCase):
    """Test the spatial concentration logic used in _evaluate_verification.

    Replicates CalibrationPopup.compute_concentration without Kivy import.
    """

    @staticmethod
    def _compute_concentration(rms_per_ch):
        """Replicate CalibrationPopup.compute_concentration."""
        n = len(rms_per_ch)
        sorted_rms = np.sort(rms_per_ch)[::-1]
        top_quarter = sorted_rms[:max(1, n // 4)].sum()
        total = sorted_rms.sum()
        return float(top_quarter / total) if total > 0 else 0.0

    def test_concentrated_activation_passes(self):
        """If a few channels have most of the energy, concentration should be high."""
        rms = np.zeros(64)
        rms[:16] = 100.0
        rms[16:] = 1.0
        concentration = self._compute_concentration(rms)
        self.assertGreater(concentration, CFG.CALIBRATION_VERIFY_ACTIVE_FRAC)

    def test_diffuse_activation_fails(self):
        """If all channels have equal RMS, concentration = 0.25 (not > threshold)."""
        rms = np.ones(64) * 50.0
        concentration = self._compute_concentration(rms)
        self.assertAlmostEqual(concentration, 0.25, places=2)
        self.assertFalse(concentration > CFG.CALIBRATION_VERIFY_ACTIVE_FRAC)

    def test_single_channel_dominant(self):
        """If one channel dominates, concentration should be very high."""
        rms = np.ones(64)
        rms[0] = 1000.0
        concentration = self._compute_concentration(rms)
        self.assertGreater(concentration, 0.9)

    def test_zero_rms_returns_zero(self):
        """All-zero data should return 0 concentration."""
        rms = np.zeros(64)
        concentration = self._compute_concentration(rms)
        self.assertEqual(concentration, 0.0)

    def test_quarter_active(self):
        """Exactly top quarter active with rest zero — concentration = 1.0."""
        rms = np.zeros(64)
        rms[:16] = 50.0
        concentration = self._compute_concentration(rms)
        self.assertAlmostEqual(concentration, 1.0)

    def test_half_active_moderate(self):
        """Half channels active — concentration should be ~0.5."""
        rms = np.zeros(64)
        rms[:32] = 50.0
        concentration = self._compute_concentration(rms)
        self.assertAlmostEqual(concentration, 0.5)


class TestVerifyPhaseRouting(unittest.TestCase):
    """Verify sample routing for the verify phase."""

    def test_collect_sample_routes_to_verify(self):
        """Data should be routed to verify list when phase='verify'."""
        verify_samples = []
        phase = 'verify'
        data = np.random.randn(72, 10).astype(np.float32)

        # Replicate _collect_sample dispatch
        if phase == 'verify':
            verify_samples.append(data.copy())

        self.assertEqual(len(verify_samples), 1)
        np.testing.assert_array_equal(verify_samples[0], data)


if __name__ == '__main__':
    unittest.main()
