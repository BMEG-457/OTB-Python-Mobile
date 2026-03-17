"""Pure-numpy IIR filtering and signal utilities.

Replaces scipy.signal.filtfilt, find_peaks, and resample so that scipy is not
required at runtime on Android.

Functions
---------
lfilter(b, a, x)         — causal Direct-Form-II-Transposed IIR filter
filtfilt(b, a, x)        — zero-phase (forward + backward) IIR filter
find_peaks(x, ...)       — local-maximum detection with height/distance pruning
resample_signal(x, num)  — linear-interpolation resampling to num samples
"""

import numpy as np


# ---------------------------------------------------------------------------
# Causal IIR filter
# ---------------------------------------------------------------------------

def lfilter(b, a, x):
    """Apply IIR filter (causal, forward direction).

    Uses the Direct Form II Transposed structure.
    Supports 1-D signals and 2-D arrays of shape (channels, samples).

    Parameters
    ----------
    b, a : array-like
        Numerator / denominator polynomial coefficients.
    x : np.ndarray, shape (n,) or (channels, n)

    Returns
    -------
    np.ndarray, same shape as x.
    """
    b = np.asarray(b, dtype=float)
    a = np.asarray(a, dtype=float)
    if a[0] != 1.0:
        b = b / a[0]
        a = a / a[0]

    M = max(len(b), len(a)) - 1
    b = np.r_[b, np.zeros(max(0, M + 1 - len(b)))]
    a = np.r_[a, np.zeros(max(0, M + 1 - len(a)))]

    if x.ndim == 1:
        return _lfilter_1d(b, a, x, M)

    result = np.empty_like(x)
    for i in range(x.shape[0]):
        result[i] = _lfilter_1d(b, a, x[i], M)
    return result


def _lfilter_1d(b, a, x, M):
    n = len(x)
    y = np.zeros(n)
    if M == 0:
        y[:] = b[0] * x
        return y
    z = np.zeros(M)
    b0 = b[0]
    b_tail = b[1:M + 1]
    a_tail = a[1:M + 1]
    for i in range(n):
        yi = b0 * x[i] + z[0]
        z[:-1] = b_tail[:-1] * x[i] - a_tail[:-1] * yi + z[1:]
        z[-1] = b_tail[-1] * x[i] - a_tail[-1] * yi
        y[i] = yi
    return y


# ---------------------------------------------------------------------------
# Zero-phase filter
# ---------------------------------------------------------------------------

def filtfilt(b, a, x):
    """Zero-phase IIR filter: forward lfilter then backward lfilter.

    Uses reflect padding (length = 3 * max(len(a), len(b))) to reduce
    edge transients, matching scipy.signal.filtfilt's default behaviour.
    Falls back to causal lfilter for signals too short to pad.

    Supports 1-D signals and 2-D arrays of shape (channels, samples).
    """
    b = np.asarray(b, dtype=float)
    a = np.asarray(a, dtype=float)
    padlen = 3 * max(len(a), len(b))

    if x.ndim == 1:
        return _filtfilt_1d(b, a, x, padlen)

    result = np.empty_like(x)
    for i in range(x.shape[0]):
        result[i] = _filtfilt_1d(b, a, x[i], padlen)
    return result


def _filtfilt_1d(b, a, x, padlen):
    n = len(x)
    if n <= padlen:
        # Signal too short for reflection padding — apply causal filter only.
        return lfilter(b, a, x)

    # Reflect-pad both ends
    ext = np.r_[x[padlen:0:-1], x, x[-2:-padlen - 2:-1]]
    y = lfilter(b, a, ext)
    y = lfilter(b, a, y[::-1])[::-1]
    return y[padlen:-padlen]


# ---------------------------------------------------------------------------
# Peak detection
# ---------------------------------------------------------------------------

def find_peaks(x, height=None, distance=None):
    """Find indices of local maxima in a 1-D signal.

    Parameters
    ----------
    x        : 1-D array-like
    height   : float, optional — minimum peak value
    distance : int, optional   — minimum samples between peaks (keeps tallest)

    Returns
    -------
    (indices, {}) — tuple matching scipy.signal.find_peaks's interface.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)

    # Collect all strict local maxima that satisfy the height criterion
    candidates = [
        i for i in range(1, n - 1)
        if x[i] > x[i - 1] and x[i] >= x[i + 1]
        and (height is None or x[i] >= height)
    ]

    if not candidates or distance is None:
        return np.array(candidates, dtype=int), {}

    candidates = np.array(candidates, dtype=int)

    # Greedily keep tallest peak, suppress neighbours within `distance` samples
    order = np.argsort(x[candidates])[::-1]   # highest first
    sorted_cands = candidates[order]
    keep = np.ones(len(sorted_cands), dtype=bool)

    for i in range(len(sorted_cands)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(sorted_cands)):
            if keep[j] and abs(int(sorted_cands[i]) - int(sorted_cands[j])) < distance:
                keep[j] = False

    return np.sort(sorted_cands[keep]), {}


# ---------------------------------------------------------------------------
# Stateful causal IIR filter (live streaming)
# ---------------------------------------------------------------------------

class StatefulIIRFilter:
    """Causal IIR filter that maintains state across calls.

    Vectorized across channels: at each sample step, all channels are processed
    simultaneously using numpy array operations.  The Python loop is only over
    the sample dimension (typically 125 per packet), not over channels.

    Usage
    -----
    filt = StatefulIIRFilter(b, a, n_channels=72)
    out  = filt(data)   # data shape (n_channels, n_samples)
    # state persists — next call continues from where this one left off
    filt.reset()        # zero state for a fresh streaming session
    """

    def __init__(self, b, a, n_channels):
        b = np.asarray(b, dtype=np.float64)
        a = np.asarray(a, dtype=np.float64)
        if a[0] != 1.0:
            b = b / a[0]
            a = a / a[0]

        M = max(len(b), len(a)) - 1
        self.b = np.r_[b, np.zeros(max(0, M + 1 - len(b)))]
        self.a = np.r_[a, np.zeros(max(0, M + 1 - len(a)))]
        self.M = M
        self.n_channels = n_channels
        self._z = np.zeros((n_channels, M), dtype=np.float64)

    def __call__(self, data):
        """Filter data of shape (n_channels, n_samples). Returns same shape."""
        n_samples = data.shape[1]
        b = self.b
        a = self.a
        M = self.M
        z = self._z
        out = np.empty_like(data, dtype=np.float32)

        for i in range(n_samples):
            x_i = data[:, i].astype(np.float64)
            y_i = b[0] * x_i + z[:, 0]
            for j in range(M - 1):
                z[:, j] = b[j + 1] * x_i - a[j + 1] * y_i + z[:, j + 1]
            z[:, M - 1] = b[M] * x_i - a[M] * y_i
            out[:, i] = y_i

        return out

    def reset(self):
        """Zero filter state for a fresh streaming session."""
        self._z[:] = 0.0


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------

def resample_signal(x, num):
    """Resample a 1-D signal to `num` samples via linear interpolation.

    Simpler than scipy.signal.resample (FFT-based), but adequate for
    RMS-based analyses where sub-sample accuracy is not critical.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n == num:
        return x.copy()
    x_old = np.linspace(0.0, 1.0, n)
    x_new = np.linspace(0.0, 1.0, num)
    return np.interp(x_new, x_old, x)
