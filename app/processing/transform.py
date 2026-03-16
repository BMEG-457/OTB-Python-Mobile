"""Signal transforms for EMG analysis.

This module provides frequency-domain transforms for EMG signal analysis.
Currently contains minimal implementation with FFT transform.

Future expansion may include:
- STFT (Short-Time Fourier Transform)
- Wavelet transforms
- Hilbert envelope extraction

Note: These functions are available but not yet integrated into the main UI.
"""

import numpy as np


def fft_transform(data):
    """Compute FFT magnitude spectrum.

    Args:
        data: Input array of shape (channels, samples)

    Returns:
        FFT magnitude array of shape (channels, freq_bins)
    """
    return np.abs(np.fft.rfft(data, axis=1))
