"""EMG feature extraction and analysis functions.

Provides basic EMG features (RMS, MAV, integrated EMG) and post-session
analysis: TKEO-based activation timing, burst duration, bilateral symmetry,
and fatigue detection.

Filter coefficients are pre-computed for CFG.DEVICE_SAMPLE_RATE (2000 Hz).
If your recording was made at a different sample rate, update config.py and
re-run scripts/compute_filter_coeffs.py.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np

from app.processing.iir_filter import filtfilt, find_peaks, resample_signal
from app.core import config as CFG


# ---------------------------------------------------------------------------
# Basic features
# ---------------------------------------------------------------------------

def rms(data):
    return np.sqrt(np.mean(data**2, axis=1, keepdims=True))


def median_frequency_window(signal, fs):
    """Compute median frequency of a 1D signal using Hamming-windowed FFT."""
    windowed = signal * np.hamming(len(signal))
    spectrum = np.abs(np.fft.rfft(windowed)) ** 2
    freqs = np.fft.rfftfreq(len(signal), 1.0 / fs)
    cumsum = np.cumsum(spectrum)
    return float(freqs[np.searchsorted(cumsum, cumsum[-1] / 2)])


def integrated_emg(data):
    return np.sum(np.abs(data), axis=1, keepdims=True)


def mav(data):
    return np.mean(np.abs(data), axis=1, keepdims=True)


def averaged_channels(data):
    return np.mean(data, axis=0, keepdims=True).T


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _warn_rate_mismatch(fs):
    """Warn if estimated sample rate differs significantly from config rate."""
    if abs(fs - CFG.DEVICE_SAMPLE_RATE) / CFG.DEVICE_SAMPLE_RATE > 0.1:
        print(
            f"[Features] Warning: estimated fs={fs:.1f} Hz differs >10% from "
            f"config DEVICE_SAMPLE_RATE={CFG.DEVICE_SAMPLE_RATE} Hz. "
            "Pre-computed filter coefficients may not be optimal."
        )


def _bandpass_coeffs():
    return np.array(CFG.BANDPASS_4_B), np.array(CFG.BANDPASS_4_A)


def _lowpass_coeffs():
    return np.array(CFG.LOWPASS_10_4_B), np.array(CFG.LOWPASS_10_4_A)


def _preprocess_timestamps(signal, ts):
    """Clean NaNs, interpolate duplicate timestamps, enforce monotonicity.

    Returns (signal, ts) or (None, None) if signal is too short.
    """
    mask = ~(np.isnan(ts) | np.isnan(signal))
    ts = ts[mask]
    signal = signal[mask]

    if len(ts) < 30:
        return None, None

    unique, counts = np.unique(ts, return_counts=True)
    if len(set(counts)) == 1 and counts[0] > 1:
        n_repeats = counts[0]
        new_ts = []
        for i in range(len(unique) - 1):
            new_ts.extend(np.linspace(unique[i], unique[i + 1], n_repeats, endpoint=False))
        last_interval = unique[-1] - unique[-2] if len(unique) > 1 else 1.0
        new_ts.extend(np.linspace(unique[-1], unique[-1] + last_interval, n_repeats, endpoint=False))
        ts = np.array(new_ts)

    inc_mask = np.diff(ts, prepend=ts[0]) > 0
    ts = ts[inc_mask]
    signal = signal[inc_mask]

    if len(ts) < 30 or np.all(np.diff(ts) == 0):
        return None, None

    return signal, ts


def _estimate_fs(ts):
    dt = np.diff(ts)
    dt = dt[dt > 0]
    if len(dt) == 0 or np.median(dt) == 0:
        return None
    return 1.0 / np.median(dt)


# ---------------------------------------------------------------------------
# TKEO activation timing
# ---------------------------------------------------------------------------

@dataclass
class TKEOResult:
    """Results from TKEO-based activation timing detection."""
    timestamps: np.ndarray
    tkeo_envelope: np.ndarray
    onset_times: np.ndarray
    onset_indices: np.ndarray
    detection_threshold: float
    backtrack_threshold: float
    sample_rate: float


def compute_tkeo_activation_timing(
    raw_signal: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    bandpass_low: float = CFG.FEATURE_BANDPASS_LOW,
    bandpass_high: float = CFG.FEATURE_BANDPASS_HIGH,
    smooth_cutoff: float = CFG.FEATURE_SMOOTH_CUTOFF,
    baseline_duration: float = CFG.FEATURE_BASELINE_DURATION,
    k_threshold: float = CFG.FEATURE_K_THRESHOLD,
    amplitude_divisor: float = CFG.FEATURE_AMPLITUDE_DIVISOR,
    min_peak_distance_sec: float = CFG.FEATURE_MIN_PEAK_DISTANCE_SEC,
    backtrack_k: float = CFG.FEATURE_BACKTRACK_K,
) -> Optional[TKEOResult]:
    """Detect muscle activation onsets using the Teager-Kaiser Energy Operator (TKEO).

    Takes raw single-channel EMG data, applies full preprocessing pipeline
    (timestamp cleanup, bandpass filter, TKEO, smoothing), and detects onsets
    via statistical thresholding with backtracking.

    Note: bandpass_low, bandpass_high, smooth_cutoff are accepted for
    API compatibility.  Filtering uses pre-computed coefficients from config
    (see config.BANDPASS_4_* and config.LOWPASS_10_4_*).

    Returns TKEOResult or None on failure.
    """
    try:
        signal, ts = _preprocess_timestamps(raw_signal.copy(), timestamps.copy())
        if signal is None:
            return None

        fs = _estimate_fs(ts)
        if fs is None:
            return None
        _warn_rate_mismatch(fs)

        # Bandpass filter
        b, a = _bandpass_coeffs()
        filtered = filtfilt(b, a, signal)

        # TKEO
        tkeo = np.zeros(len(filtered))
        tkeo[1:-1] = filtered[1:-1] ** 2 - filtered[:-2] * filtered[2:]
        tkeo[0] = tkeo[1]
        tkeo[-1] = tkeo[-2]

        # Smooth TKEO envelope with lowpass
        b_lp, a_lp = _lowpass_coeffs()
        envelope = filtfilt(b_lp, a_lp, np.abs(tkeo))

        # Baseline statistics
        baseline_mask = ts <= (ts[0] + baseline_duration)
        baseline_data = envelope[baseline_mask]
        if len(baseline_data) == 0:
            baseline_data = envelope[:int(fs * baseline_duration)]
        baseline_mean = np.mean(baseline_data)
        baseline_std = np.std(baseline_data)

        # Detection threshold
        stat_threshold = baseline_mean + k_threshold * baseline_std
        amp_threshold = np.max(envelope) / amplitude_divisor
        final_threshold = max(stat_threshold, amp_threshold)

        # Find peaks
        min_dist_samples = int(min_peak_distance_sec * fs)
        peak_indices, _ = find_peaks(envelope, height=final_threshold, distance=min_dist_samples)

        # Backtrack to true onset
        onset_threshold_low = baseline_mean + backtrack_k * baseline_std
        onset_indices = []
        for peak_idx in peak_indices:
            i = peak_idx
            while i > 0 and envelope[i] > onset_threshold_low:
                i -= 1
            onset_indices.append(i)

        onset_indices = np.unique(np.array(onset_indices))
        onset_times = ts[onset_indices] if len(onset_indices) > 0 else np.array([])

        return TKEOResult(
            timestamps=ts,
            tkeo_envelope=envelope,
            onset_times=onset_times,
            onset_indices=onset_indices,
            detection_threshold=final_threshold,
            backtrack_threshold=onset_threshold_low,
            sample_rate=fs,
        )

    except Exception as e:
        print(f"[Features] TKEO activation timing failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Burst duration
# ---------------------------------------------------------------------------

@dataclass
class BurstDurationResult:
    """Results from burst duration analysis."""
    num_bursts: int
    avg_duration: float
    std_duration: float
    burst_durations: np.ndarray


def compute_burst_duration(
    raw_signal: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    bandpass_low: float = CFG.FEATURE_BANDPASS_LOW,
    bandpass_high: float = CFG.FEATURE_BANDPASS_HIGH,
    smooth_cutoff: float = CFG.FEATURE_SMOOTH_CUTOFF,
    baseline_duration: float = CFG.FEATURE_BASELINE_DURATION,
    k_threshold: float = CFG.FEATURE_K_THRESHOLD,
    amplitude_divisor: float = CFG.FEATURE_AMPLITUDE_DIVISOR,
    backtrack_k: float = CFG.FEATURE_BACKTRACK_K,
    min_burst_duration: float = CFG.FEATURE_MIN_BURST_DURATION,
) -> Optional[BurstDurationResult]:
    """Detect EMG bursts via TKEO and compute their duration statistics.

    Returns BurstDurationResult or None on failure.
    """
    try:
        signal, ts = _preprocess_timestamps(raw_signal.copy(), timestamps.copy())
        if signal is None:
            return None

        fs = _estimate_fs(ts)
        if fs is None:
            return None
        _warn_rate_mismatch(fs)

        b, a = _bandpass_coeffs()
        filtered = filtfilt(b, a, signal)

        tkeo = np.zeros(len(filtered))
        tkeo[1:-1] = filtered[1:-1] ** 2 - filtered[:-2] * filtered[2:]
        tkeo[0] = tkeo[1]
        tkeo[-1] = tkeo[-2]

        b_lp, a_lp = _lowpass_coeffs()
        envelope = filtfilt(b_lp, a_lp, np.abs(tkeo))

        baseline_mask = ts <= (ts[0] + baseline_duration)
        baseline_env = envelope[baseline_mask]
        if len(baseline_env) == 0:
            baseline_env = envelope[:int(fs * baseline_duration)]
        baseline_mean = np.mean(baseline_env)
        baseline_std = np.std(baseline_env)

        stat_threshold = baseline_mean + k_threshold * baseline_std
        amp_threshold = np.max(envelope) / amplitude_divisor
        thresh = max(stat_threshold, amp_threshold)
        onset_threshold = baseline_mean + backtrack_k * baseline_std

        above = envelope > onset_threshold
        onsets  = np.where(np.diff(above.astype(int)) ==  1)[0] + 1
        offsets = np.where(np.diff(above.astype(int)) == -1)[0] + 1

        if above[0]:
            onsets = np.insert(onsets, 0, 0)
        if above[-1]:
            offsets = np.append(offsets, len(envelope) - 1)

        n_pairs = min(len(onsets), len(offsets))
        if n_pairs == 0:
            return BurstDurationResult(num_bursts=0, avg_duration=0.0,
                                       std_duration=0.0, burst_durations=np.array([]))

        valid_durations = []
        for i in range(n_pairs):
            burst_env = envelope[onsets[i]:offsets[i]]
            if len(burst_env) > 0 and np.max(burst_env) >= thresh:
                dur = ts[offsets[i]] - ts[onsets[i]]
                if dur > min_burst_duration:
                    valid_durations.append(dur)

        burst_durations = np.array(valid_durations)
        num_bursts = len(burst_durations)
        return BurstDurationResult(
            num_bursts=num_bursts,
            avg_duration=float(np.mean(burst_durations)) if num_bursts > 0 else 0.0,
            std_duration=float(np.std(burst_durations)) if num_bursts > 0 else 0.0,
            burst_durations=burst_durations,
        )

    except Exception as e:
        print(f"[Features] Burst duration computation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Bilateral symmetry
# ---------------------------------------------------------------------------

@dataclass
class BilateralSymmetryResult:
    """Results from bilateral symmetry analysis."""
    timestamps: np.ndarray
    symmetry_index: np.ndarray
    sample_rate: float
    mean_si: float
    std_si: float
    max_asymmetry: float
    rms_file1: float
    rms_file2: float
    window_duration: float
    overlap_duration: float
    file1_sample_rate: float
    file2_sample_rate: float
    analysis_sample_rate: float


def compute_bilateral_symmetry(
    signal_1: np.ndarray,
    timestamps_1: np.ndarray,
    sample_rate_1: float,
    signal_2: np.ndarray,
    timestamps_2: np.ndarray,
    sample_rate_2: float,
    window_sec: float = CFG.FEATURE_BILATERAL_WINDOW_SEC,
    step_sec: float = CFG.FEATURE_BILATERAL_STEP_SEC,
) -> Optional[BilateralSymmetryResult]:
    """Compute bilateral symmetry index between two EMG signals.

    SI = (RMS_1 - RMS_2) / (RMS_1 + RMS_2).  Range [-1, 1]; 0 = symmetric.
    """
    try:
        rel_ts_1 = timestamps_1 - timestamps_1[0]
        rel_ts_2 = timestamps_2 - timestamps_2[0]

        overlap_duration = min(rel_ts_1[-1], rel_ts_2[-1])
        if overlap_duration <= 0:
            return None

        sig_1 = signal_1[rel_ts_1 <= overlap_duration].copy()
        sig_2 = signal_2[rel_ts_2 <= overlap_duration].copy()

        analysis_rate = min(sample_rate_1, sample_rate_2)
        target_samples = int(overlap_duration * analysis_rate)
        if target_samples < 10:
            return None

        if len(sig_1) != target_samples:
            sig_1 = resample_signal(sig_1, target_samples)
        if len(sig_2) != target_samples:
            sig_2 = resample_signal(sig_2, target_samples)

        common_ts = np.linspace(0, overlap_duration, target_samples, endpoint=False)
        window_samples = max(1, int(window_sec * analysis_rate))
        step_samples   = max(1, int(step_sec   * analysis_rate))

        si_values = []
        si_times  = []
        for start in range(0, len(sig_1) - window_samples + 1, step_samples):
            end   = start + window_samples
            rms_1 = np.sqrt(np.mean(sig_1[start:end] ** 2))
            rms_2 = np.sqrt(np.mean(sig_2[start:end] ** 2))
            denom = rms_1 + rms_2
            si_values.append((rms_1 - rms_2) / denom if denom > 0 else 0.0)
            center = min(start + window_samples // 2, len(common_ts) - 1)
            si_times.append(common_ts[center])

        si_array      = np.array(si_values)
        si_timestamps = np.array(si_times)
        if len(si_array) == 0:
            return None

        output_rate = (1.0 / np.mean(np.diff(si_timestamps))
                       if len(si_timestamps) > 1 else 1.0 / step_sec)

        return BilateralSymmetryResult(
            timestamps=si_timestamps,
            symmetry_index=si_array,
            sample_rate=output_rate,
            mean_si=float(np.mean(si_array)),
            std_si=float(np.std(si_array)),
            max_asymmetry=float(np.max(np.abs(si_array))),
            rms_file1=float(np.sqrt(np.mean(sig_1 ** 2))),
            rms_file2=float(np.sqrt(np.mean(sig_2 ** 2))),
            window_duration=window_sec,
            overlap_duration=float(overlap_duration),
            file1_sample_rate=sample_rate_1,
            file2_sample_rate=sample_rate_2,
            analysis_sample_rate=analysis_rate,
        )

    except Exception as e:
        print(f"[Features] Bilateral symmetry computation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Fatigue
# ---------------------------------------------------------------------------

@dataclass
class FatigueResult:
    """Results from fatigue detection analysis."""
    rms_times: np.ndarray
    rms_values: np.ndarray
    mf_times: np.ndarray
    mf_values: np.ndarray
    time_to_rms_fatigue: Optional[np.ndarray]
    time_to_mf_fatigue: Optional[np.ndarray]
    baseline_rms: float
    rms_threshold: float
    mf_threshold: float
    sample_rate: float


def _calculate_sliding_rms(data, window_size, step_size):
    n_samples = len(data)
    rms_values      = []
    window_indices  = []
    for start in range(0, n_samples - window_size + 1, step_size):
        end = start + window_size
        rms_values.append(np.sqrt(np.mean(data[start:end] ** 2)))
        window_indices.append((start + end) // 2)
    return np.array(rms_values), np.array(window_indices)


def _calculate_median_frequency(data, fs, window_size, step_size):
    """Sliding-window median frequency using Hamming-windowed FFT."""
    n_samples = len(data)
    mf_values      = []
    window_indices = []
    hamming = np.hamming(window_size)

    for start in range(0, n_samples - window_size + 1, step_size):
        end = start + window_size
        windowed_data = data[start:end] * hamming
        fft_vals = np.abs(np.fft.rfft(windowed_data))
        freqs    = np.fft.rfftfreq(window_size, 1 / fs)
        cumsum   = np.cumsum(fft_vals)
        total    = cumsum[-1]
        if total > 0:
            idx = np.where(cumsum >= total / 2)[0]
            mf_values.append(freqs[idx[0]] if len(idx) > 0 else 0.0)
        else:
            mf_values.append(0.0)
        window_indices.append((start + end) // 2)

    return np.array(mf_values), np.array(window_indices)


def compute_fatigue(
    raw_signal: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    bandpass_low: float = CFG.FEATURE_BANDPASS_LOW,
    bandpass_high: float = CFG.FEATURE_BANDPASS_HIGH,
    baseline_duration: float = CFG.FEATURE_BASELINE_DURATION,
    rms_threshold: float = CFG.FEATURE_FATIGUE_RMS_THRESHOLD,
    mf_threshold: float = CFG.FEATURE_FATIGUE_MF_THRESHOLD,
    window_duration: float = CFG.FEATURE_WINDOW_DURATION,
    step_duration: float = CFG.FEATURE_STEP_DURATION,
) -> Optional[FatigueResult]:
    """Detect muscle fatigue from RMS increase and median frequency decline.

    Returns FatigueResult or None on failure.
    """
    try:
        signal, ts = _preprocess_timestamps(raw_signal.copy(), timestamps.copy())
        if signal is None:
            return None

        fs = _estimate_fs(ts)
        if fs is None:
            return None
        _warn_rate_mismatch(fs)

        b, a = _bandpass_coeffs()
        filtered = filtfilt(b, a, signal)

        window_size = int(window_duration * fs)
        step_size   = int(step_duration   * fs)
        if window_size < 2 or step_size < 1:
            return None

        rms_values, rms_indices = _calculate_sliding_rms(np.abs(filtered), window_size, step_size)
        if len(rms_values) == 0:
            return None
        rms_times = ts[rms_indices]

        baseline_end_idx = np.searchsorted(rms_times, ts[0] + baseline_duration)
        if baseline_end_idx < 1:
            baseline_end_idx = 1
        baseline_rms_val = float(np.mean(rms_values[:baseline_end_idx]))

        if baseline_rms_val > 0:
            rms_change = (rms_values - baseline_rms_val) / baseline_rms_val
            rms_fatigue_mask = rms_change >= rms_threshold
            time_to_rms_fatigue = rms_times[rms_fatigue_mask] if np.any(rms_fatigue_mask) else None
        else:
            time_to_rms_fatigue = None

        mf_values, mf_indices = _calculate_median_frequency(filtered, fs, window_size, step_size)
        if len(mf_values) == 0:
            return None
        mf_times = ts[mf_indices]

        mf_rate = np.zeros_like(mf_values)
        if len(mf_values) > 1:
            dt_mf = np.diff(mf_times)
            dmf   = np.diff(mf_values)
            valid = dt_mf > 0
            mf_rate[1:][valid] = dmf[valid] / dt_mf[valid]

        mf_fatigue_mask = mf_rate <= mf_threshold
        time_to_mf_fatigue = mf_times[mf_fatigue_mask] if np.any(mf_fatigue_mask) else None

        return FatigueResult(
            rms_times=rms_times,
            rms_values=rms_values,
            mf_times=mf_times,
            mf_values=mf_values,
            time_to_rms_fatigue=time_to_rms_fatigue,
            time_to_mf_fatigue=time_to_mf_fatigue,
            baseline_rms=baseline_rms_val,
            rms_threshold=rms_threshold,
            mf_threshold=mf_threshold,
            sample_rate=fs,
        )

    except Exception as e:
        print(f"[Features] Fatigue computation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Centroid shift
# ---------------------------------------------------------------------------

@dataclass
class CentroidShiftResult:
    times: np.ndarray
    centroid_x: np.ndarray
    centroid_y: np.ndarray
    displacement: np.ndarray
    initial_centroid: tuple
    total_shift: float
    mean_drift_rate: float
    sample_rate: float


def _preprocess_timestamps_2d(data_64ch, ts):
    """Like _preprocess_timestamps but for (64, n_samples) data."""
    nan_mask = np.isnan(ts) | np.any(np.isnan(data_64ch), axis=0)
    ts   = ts[~nan_mask]
    data = data_64ch[:, ~nan_mask]

    if len(ts) < 30:
        return None, None

    unique, counts = np.unique(ts, return_counts=True)
    if len(set(counts)) == 1 and counts[0] > 1:
        n_repeats = counts[0]
        new_ts = []
        for i in range(len(unique) - 1):
            new_ts.extend(np.linspace(unique[i], unique[i + 1], n_repeats, endpoint=False))
        last_interval = unique[-1] - unique[-2] if len(unique) > 1 else 1.0
        new_ts.extend(np.linspace(unique[-1], unique[-1] + last_interval, n_repeats, endpoint=False))
        ts = np.array(new_ts)

    inc_mask = np.diff(ts, prepend=ts[0]) > 0
    ts   = ts[inc_mask]
    data = data[:, inc_mask]

    if len(ts) < 30 or np.all(np.diff(ts) == 0):
        return None, None

    return data, ts


def compute_centroid_shift(
    data_64ch: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    window_duration: float = CFG.FEATURE_WINDOW_DURATION,
    step_duration: float = CFG.FEATURE_STEP_DURATION,
) -> Optional[CentroidShiftResult]:
    """Track the weighted activation centroid of the HD-EMG 8×8 grid over time."""
    try:
        if data_64ch.shape[0] != 64:
            return None

        data, ts = _preprocess_timestamps_2d(data_64ch, timestamps.copy())
        if data is None:
            return None

        fs = _estimate_fs(ts)
        if fs is None:
            return None

        window_size = int(window_duration * fs)
        step_size   = int(step_duration   * fs)
        if window_size < 2 or step_size < 1:
            return None

        ch_cols = np.array([ch // 8 for ch in range(64)], dtype=float)
        ch_rows = np.array([7 - (ch % 8) for ch in range(64)], dtype=float)

        centroid_x_list = []
        centroid_y_list = []
        time_list = []

        n_samples = data.shape[1]
        for start in range(0, n_samples - window_size + 1, step_size):
            end = start + window_size
            w = np.sqrt(np.mean(data[:, start:end] ** 2, axis=1))
            total_w = float(np.sum(w))
            if total_w == 0:
                continue
            centroid_x_list.append(float(np.dot(ch_cols, w) / total_w))
            centroid_y_list.append(float(np.dot(ch_rows, w) / total_w))
            center_idx = min((start + end) // 2, len(ts) - 1)
            time_list.append(ts[center_idx])

        if len(centroid_x_list) == 0:
            return None

        centroid_x = np.array(centroid_x_list)
        centroid_y = np.array(centroid_y_list)
        times = np.array(time_list)

        cx0, cy0 = centroid_x[0], centroid_y[0]
        displacement = np.sqrt((centroid_x - cx0) ** 2 + (centroid_y - cy0) ** 2)
        recording_duration = float(ts[-1] - ts[0])
        total_shift = float(displacement[-1])
        mean_drift_rate = total_shift / recording_duration if recording_duration > 0 else 0.0
        output_rate = (1.0 / np.mean(np.diff(times))
                       if len(times) > 1 else 1.0 / step_duration)

        return CentroidShiftResult(
            times=times,
            centroid_x=centroid_x,
            centroid_y=centroid_y,
            displacement=displacement,
            initial_centroid=(cx0, cy0),
            total_shift=total_shift,
            mean_drift_rate=mean_drift_rate,
            sample_rate=output_rate,
        )

    except Exception as e:
        print(f"[Features] Centroid shift computation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Spatial non-uniformity
# ---------------------------------------------------------------------------

@dataclass
class SpatialNonUniformityResult:
    times: np.ndarray
    cv: np.ndarray
    entropy: np.ndarray
    activation_fraction: np.ndarray
    threshold_source: str
    sample_rate: float


def compute_spatial_nonuniformity(
    data_64ch: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    threshold_per_channel: Optional[np.ndarray] = None,
    window_duration: float = CFG.FEATURE_WINDOW_DURATION,
    step_duration: float = CFG.FEATURE_STEP_DURATION,
) -> Optional[SpatialNonUniformityResult]:
    """Track spatial activation non-uniformity of the HD-EMG 8×8 grid over time."""
    try:
        if data_64ch.shape[0] != 64:
            return None

        data, ts = _preprocess_timestamps_2d(data_64ch, timestamps.copy())
        if data is None:
            return None

        fs = _estimate_fs(ts)
        if fs is None:
            return None

        window_size = int(window_duration * fs)
        step_size   = int(step_duration   * fs)
        if window_size < 2 or step_size < 1:
            return None

        threshold_source = 'calibration' if threshold_per_channel is not None else 'auto'
        eps = 1e-12

        cv_list         = []
        entropy_list    = []
        activation_list = []
        time_list       = []

        n_samples = data.shape[1]
        for start in range(0, n_samples - window_size + 1, step_size):
            end = start + window_size
            w = np.sqrt(np.mean(data[:, start:end] ** 2, axis=1))
            total_w = float(np.sum(w))
            if total_w == 0:
                continue

            mean_w = float(np.mean(w))
            cv = float(np.std(w) / mean_w) if mean_w > 0 else 0.0
            p = w / total_w
            entropy = float(-np.sum(p * np.log2(p + eps)))

            if threshold_per_channel is not None:
                active = float(np.sum(w > threshold_per_channel)) / 64.0
            else:
                active = float(np.sum(w > mean_w)) / 64.0

            cv_list.append(cv)
            entropy_list.append(entropy)
            activation_list.append(active)
            center_idx = min((start + end) // 2, len(ts) - 1)
            time_list.append(ts[center_idx])

        if len(cv_list) == 0:
            return None

        times = np.array(time_list)
        output_rate = (1.0 / np.mean(np.diff(times))
                       if len(times) > 1 else 1.0 / step_duration)

        return SpatialNonUniformityResult(
            times=times,
            cv=np.array(cv_list),
            entropy=np.array(entropy_list),
            activation_fraction=np.array(activation_list),
            threshold_source=threshold_source,
            sample_rate=output_rate,
        )

    except Exception as e:
        print(f"[Features] Spatial non-uniformity computation failed: {e}")
        return None
