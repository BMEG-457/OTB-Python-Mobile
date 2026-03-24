"""Detect ADC rail clipping in raw EMG data."""

import numpy as np
from app.core import config as CFG


class ClippingDetector:
    """Detects channels where samples hit the ADC rail value.

    Check raw (pre-filter) data since filtering attenuates rail values.
    """

    def __init__(self):
        self._rail = CFG.ADC_RAIL_VALUE
        self._threshold = CFG.CLIPPING_FRACTION_THRESHOLD

    def check(self, raw_data):
        """Check for clipping in raw packet data.

        Args:
            raw_data: np.ndarray shape (channels, samples), raw int values as float32.

        Returns:
            list of channel indices that are clipping, or empty list.
        """
        n_samples = raw_data.shape[1]
        if n_samples == 0:
            return []
        clipping_mask = np.abs(raw_data) >= self._rail
        clipping_fraction = clipping_mask.sum(axis=1) / n_samples
        clipping_channels = np.where(clipping_fraction > self._threshold)[0]
        return clipping_channels.tolist()
