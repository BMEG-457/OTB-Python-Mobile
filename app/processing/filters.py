"""Live-streaming signal filters.

Uses pre-computed Butterworth coefficients from app.core.config so that scipy
is not required at runtime.  To change cutoffs or sample rate, update config.py
(run scripts/compute_filter_coeffs.py to regenerate coefficients).
"""

import numpy as np
from app.processing.iir_filter import filtfilt, StatefulIIRFilter
from app.core import config as CFG


def butter_bandpass(data, low=None, high=None, fs=None, order=None):
    """Bandpass filter using pre-computed coefficients from config.

    Arguments low, high, fs, order are accepted for API compatibility but are
    ignored — the filter is fixed to CFG.BANDPASS_LOW_HZ / BANDPASS_HIGH_HZ at
    CFG.DEVICE_SAMPLE_RATE.  Edit config.py to change these parameters.
    """
    n = data.shape[-1]
    if n < CFG.FILTER_MIN_SAMPLES_ORDER4:
        if n >= CFG.FILTER_MIN_SAMPLES_ORDER1:
            b = np.array(CFG.BANDPASS_1_B)
            a = np.array(CFG.BANDPASS_1_A)
        else:
            return data
    else:
        b = np.array(CFG.BANDPASS_4_B)
        a = np.array(CFG.BANDPASS_4_A)
    return filtfilt(b, a, data)


def notch(data, freq=None, fs=None, quality=None):
    """Notch filter using pre-computed coefficients from config.

    Arguments are accepted for API compatibility but ignored — the filter is
    fixed to CFG.NOTCH_FREQ_HZ / NOTCH_QUALITY at CFG.DEVICE_SAMPLE_RATE.
    """
    if data.shape[-1] < CFG.NOTCH_MIN_SAMPLES:
        return data
    b = np.array(CFG.NOTCH_60_B)
    a = np.array(CFG.NOTCH_60_A)
    return filtfilt(b, a, data)


def rectify(data):
    return np.abs(data)


# ---------------------------------------------------------------------------
# Stateful causal filters for live streaming
# ---------------------------------------------------------------------------
# Separate instances per pipeline to avoid shared-state corruption.

_live_bp_filtered = None
_live_bp_final = None
_live_notch_final = None


def init_live_filters(n_channels):
    """Create stateful filter instances for live streaming. Call once before streaming."""
    global _live_bp_filtered, _live_bp_final, _live_notch_final

    b_bp = np.array(CFG.BANDPASS_4_B)
    a_bp = np.array(CFG.BANDPASS_4_A)
    _live_bp_filtered = StatefulIIRFilter(b_bp, a_bp, n_channels)
    _live_bp_final    = StatefulIIRFilter(b_bp, a_bp, n_channels)

    b_n = np.array(CFG.NOTCH_60_B)
    a_n = np.array(CFG.NOTCH_60_A)
    _live_notch_final = StatefulIIRFilter(b_n, a_n, n_channels)


def reset_live_filters():
    """Zero filter state for a fresh streaming session."""
    if _live_bp_filtered is not None:
        _live_bp_filtered.reset()
    if _live_bp_final is not None:
        _live_bp_final.reset()
    if _live_notch_final is not None:
        _live_notch_final.reset()
