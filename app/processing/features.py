"""EMG feature extraction and analysis functions.

Provides basic EMG features (RMS, MAV, integrated EMG) and post-session
analysis: TKEO-based activation timing, burst duration, bilateral symmetry,
and fatigue detection.
"""

from scipy.signal import butter, filtfilt, find_peaks, resample
from scipy.fft import rfft, rfftfreq
from dataclasses import dataclass
from typing import Optional
import numpy as np

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

# takes in collection of arrays
def averaged_channels(data): 
    return np.mean(data, axis=0, keepdims=True).T


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


@dataclass
class BurstDurationResult:
    """Results from burst duration analysis."""
    num_bursts: int
    avg_duration: float
    std_duration: float
    burst_durations: np.ndarray


def compute_tkeo_activation_timing(
    raw_signal: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    bandpass_low: float = 20.0,
    bandpass_high: float = 450.0,
    smooth_cutoff: float = 10.0,
    baseline_duration: float = 0.5,
    k_threshold: float = 8.0,
    amplitude_divisor: float = 4.0,
    min_peak_distance_sec: float = 0.5,
    backtrack_k: float = 3.0,
) -> Optional[TKEOResult]:
    """Detect muscle activation onsets using the Teager-Kaiser Energy Operator (TKEO).

    Takes raw single-channel EMG data, applies full preprocessing pipeline
    (timestamp cleanup, bandpass filter, TKEO, smoothing), and detects onsets
    via statistical thresholding with backtracking.

    Parameters:
        raw_signal: 1D raw EMG signal
        timestamps: 1D timestamp array (same length as raw_signal)
        sample_rate: Estimated sample rate in Hz (used as fallback)
        bandpass_low: Bandpass filter low cutoff (Hz)
        bandpass_high: Bandpass filter high cutoff (Hz)
        smooth_cutoff: Lowpass cutoff for TKEO envelope smoothing (Hz)
        baseline_duration: Duration of quiet baseline period at start (seconds)
        k_threshold: Multiplier for baseline std in detection threshold
        amplitude_divisor: Divisor for amplitude-based threshold (max/divisor)
        min_peak_distance_sec: Minimum distance between detected peaks (seconds)
        backtrack_k: Multiplier for baseline std in backtrack threshold

    Returns:
        TKEOResult with envelope, onset times, and thresholds, or None on failure.
    """
    try:
        signal = raw_signal.copy()
        ts = timestamps.copy()

        # --- Timestamp preprocessing ---
        # Remove NaN entries
        mask = ~(np.isnan(ts) | np.isnan(signal))
        ts = ts[mask]
        signal = signal[mask]

        if len(ts) < 30:
            return None

        # Interpolate duplicated timestamps
        unique, counts = np.unique(ts, return_counts=True)
        if len(set(counts)) == 1 and counts[0] > 1:
            n_repeats = counts[0]
            new_ts = []
            for i in range(len(unique) - 1):
                interp = np.linspace(unique[i], unique[i + 1], n_repeats, endpoint=False)
                new_ts.extend(interp)
            last_interval = unique[-1] - unique[-2] if len(unique) > 1 else 1.0
            last_group = np.linspace(unique[-1], unique[-1] + last_interval, n_repeats, endpoint=False)
            new_ts.extend(last_group)
            ts = np.array(new_ts)

        # Enforce strictly increasing timestamps
        inc_mask = np.diff(ts, prepend=ts[0]) > 0
        ts = ts[inc_mask]
        signal = signal[inc_mask]

        if len(ts) < 30 or np.all(np.diff(ts) == 0):
            return None

        # Re-estimate sample rate from cleaned timestamps
        dt = np.diff(ts)
        dt = dt[dt > 0]
        if len(dt) == 0 or np.median(dt) == 0:
            return None
        fs = 1.0 / np.median(np.diff(ts))

        # --- Bandpass filter (20-450 Hz) ---
        nyq = 0.5 * fs
        if bandpass_high >= nyq:
            bandpass_high = nyq * 0.95
        b, a = butter(4, [bandpass_low / nyq, bandpass_high / nyq], btype='band')
        filtered = filtfilt(b, a, signal)

        # --- Compute TKEO ---
        tkeo = np.zeros(len(filtered))
        tkeo[1:-1] = filtered[1:-1] ** 2 - filtered[:-2] * filtered[2:]
        tkeo[0] = tkeo[1]
        tkeo[-1] = tkeo[-2]

        # --- Rectify ---
        tkeo_rect = np.abs(tkeo)

        # --- Smooth with lowpass filter ---
        b_lp, a_lp = butter(4, smooth_cutoff / nyq, btype='low')
        envelope = filtfilt(b_lp, a_lp, tkeo_rect)

        # --- Baseline from first baseline_duration seconds ---
        baseline_mask = ts <= (ts[0] + baseline_duration)
        baseline_data = envelope[baseline_mask]
        if len(baseline_data) == 0:
            baseline_data = envelope[:int(fs * baseline_duration)]
        baseline_mean = np.mean(baseline_data)
        baseline_std = np.std(baseline_data)

        # --- Detection threshold ---
        stat_threshold = baseline_mean + k_threshold * baseline_std
        amp_threshold = np.max(envelope) / amplitude_divisor
        final_threshold = max(stat_threshold, amp_threshold)

        # --- Find peaks above threshold ---
        min_dist_samples = int(min_peak_distance_sec * fs)
        peak_indices, _ = find_peaks(envelope, height=final_threshold, distance=min_dist_samples)

        # --- Backtrack to find true onset ---
        onset_threshold_low = baseline_mean + backtrack_k * baseline_std
        onset_indices = []
        for peak_idx in peak_indices:
            i = peak_idx
            while i > 0 and envelope[i] > onset_threshold_low:
                i -= 1
            onset_indices.append(i)

        # Deduplicate: multiple peaks can backtrack to the same onset
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


def compute_burst_duration(
    raw_signal: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    bandpass_low: float = 20.0,
    bandpass_high: float = 450.0,
    smooth_cutoff: float = 10.0,
    baseline_duration: float = 0.5,
    k_threshold: float = 8.0,
    amplitude_divisor: float = 4.0,
    backtrack_k: float = 3.0,
    min_burst_duration: float = 0.05,
) -> Optional[BurstDurationResult]:
    """Detect EMG bursts via TKEO and compute their duration statistics.

    Uses the same TKEO-based detection pipeline as activation timings to
    identify burst onsets and offsets, then computes duration statistics.

    Parameters:
        raw_signal: 1D raw EMG signal
        timestamps: 1D timestamp array (same length as raw_signal)
        sample_rate: Estimated sample rate in Hz (used as fallback)
        bandpass_low: Bandpass filter low cutoff (Hz)
        bandpass_high: Bandpass filter high cutoff (Hz)
        smooth_cutoff: Lowpass cutoff for TKEO envelope smoothing (Hz)
        baseline_duration: Duration of quiet baseline period at start (seconds)
        k_threshold: Multiplier for baseline std in detection threshold
        amplitude_divisor: Divisor for amplitude-based threshold (max/divisor)
        backtrack_k: Multiplier for baseline std in backtrack threshold
        min_burst_duration: Minimum burst duration in seconds (shorter bursts are discarded)

    Returns:
        BurstDurationResult with burst count, average duration, std, and individual durations,
        or None on failure.
    """
    try:
        signal = raw_signal.copy()
        ts = timestamps.copy()

        # --- Timestamp preprocessing (same as TKEO) ---
        mask = ~(np.isnan(ts) | np.isnan(signal))
        ts = ts[mask]
        signal = signal[mask]

        if len(ts) < 30:
            return None

        # Interpolate duplicated timestamps
        unique, counts = np.unique(ts, return_counts=True)
        if len(set(counts)) == 1 and counts[0] > 1:
            n_repeats = counts[0]
            new_ts = []
            for i in range(len(unique) - 1):
                interp = np.linspace(unique[i], unique[i + 1], n_repeats, endpoint=False)
                new_ts.extend(interp)
            last_interval = unique[-1] - unique[-2] if len(unique) > 1 else 1.0
            last_group = np.linspace(unique[-1], unique[-1] + last_interval, n_repeats, endpoint=False)
            new_ts.extend(last_group)
            ts = np.array(new_ts)

        # Enforce strictly increasing timestamps
        inc_mask = np.diff(ts, prepend=ts[0]) > 0
        ts = ts[inc_mask]
        signal = signal[inc_mask]

        if len(ts) < 30 or np.all(np.diff(ts) == 0):
            return None

        # Re-estimate sample rate from cleaned timestamps
        dt = np.diff(ts)
        dt = dt[dt > 0]
        if len(dt) == 0 or np.median(dt) == 0:
            return None
        fs = 1.0 / np.median(np.diff(ts))

        # --- Bandpass filter ---
        nyq = 0.5 * fs
        if bandpass_high >= nyq:
            bandpass_high = nyq * 0.95
        b, a = butter(4, [bandpass_low / nyq, bandpass_high / nyq], btype='band')
        filtered = filtfilt(b, a, signal)

        # --- Compute TKEO ---
        tkeo = np.zeros(len(filtered))
        tkeo[1:-1] = filtered[1:-1] ** 2 - filtered[:-2] * filtered[2:]
        tkeo[0] = tkeo[1]
        tkeo[-1] = tkeo[-2]

        # --- Rectify and smooth ---
        tkeo_rect = np.abs(tkeo)
        b_lp, a_lp = butter(4, smooth_cutoff / nyq, btype='low')
        envelope = filtfilt(b_lp, a_lp, tkeo_rect)

        # --- Baseline from first baseline_duration seconds ---
        baseline_mask = ts <= (ts[0] + baseline_duration)
        baseline_env = envelope[baseline_mask]
        if len(baseline_env) == 0:
            baseline_env = envelope[:int(fs * baseline_duration)]

        baseline_mean = np.mean(baseline_env)
        baseline_std = np.std(baseline_env)

        # --- Detection threshold (same as activation timings) ---
        stat_threshold = baseline_mean + k_threshold * baseline_std
        amp_threshold = np.max(envelope) / amplitude_divisor
        thresh = max(stat_threshold, amp_threshold)

        # --- Backtrack threshold for onset/offset detection ---
        onset_threshold = baseline_mean + backtrack_k * baseline_std

        # --- Detect burst onsets and offsets using backtrack threshold ---
        above = envelope > onset_threshold
        onsets = np.where(np.diff(above.astype(int)) == 1)[0] + 1
        offsets = np.where(np.diff(above.astype(int)) == -1)[0] + 1

        # Handle edge cases (burst at start or end)
        if above[0]:
            onsets = np.insert(onsets, 0, 0)
        if above[-1]:
            offsets = np.append(offsets, len(envelope) - 1)

        # Pair onsets and offsets
        n_pairs = min(len(onsets), len(offsets))
        if n_pairs == 0:
            return BurstDurationResult(
                num_bursts=0,
                avg_duration=0.0,
                std_duration=0.0,
                burst_durations=np.array([]),
            )

        # Only keep bursts whose peak exceeds the detection threshold
        valid_durations = []
        for i in range(n_pairs):
            burst_env = envelope[onsets[i]:offsets[i]]
            if len(burst_env) > 0 and np.max(burst_env) >= thresh:
                dur = ts[offsets[i]] - ts[onsets[i]]
                if dur > min_burst_duration:
                    valid_durations.append(dur)

        burst_durations = np.array(valid_durations)
        num_bursts = len(burst_durations)
        avg_duration = float(np.mean(burst_durations)) if num_bursts > 0 else 0.0
        std_duration = float(np.std(burst_durations)) if num_bursts > 0 else 0.0

        return BurstDurationResult(
            num_bursts=num_bursts,
            avg_duration=avg_duration,
            std_duration=std_duration,
            burst_durations=burst_durations,
        )

    except Exception as e:
        print(f"[Features] Burst duration computation failed: {e}")
        return None


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
    window_sec: float = 0.25,
    step_sec: float = 0.05,
) -> Optional[BilateralSymmetryResult]:
    """Compute bilateral symmetry index between two EMG signals.

    Aligns both signals to t=0, resamples to a common sample rate if needed,
    and computes a sliding-window RMS-based symmetry index.

    SI = (RMS_1 - RMS_2) / (RMS_1 + RMS_2)
    Range: [-1, 1]. 0 = symmetric, +ve = signal 1 dominant, -ve = signal 2 dominant.
    """
    try:
        # Convert both to relative time starting at 0
        rel_ts_1 = timestamps_1 - timestamps_1[0]
        rel_ts_2 = timestamps_2 - timestamps_2[0]

        duration_1 = rel_ts_1[-1]
        duration_2 = rel_ts_2[-1]

        # Only compare the overlapping portion
        overlap_duration = min(duration_1, duration_2)
        if overlap_duration <= 0:
            return None

        # Trim both signals to overlap
        sig_1 = signal_1[rel_ts_1 <= overlap_duration].copy()
        sig_2 = signal_2[rel_ts_2 <= overlap_duration].copy()

        # Resample to common rate (lower of the two)
        analysis_rate = min(sample_rate_1, sample_rate_2)
        target_samples = int(overlap_duration * analysis_rate)
        if target_samples < 10:
            return None

        if len(sig_1) != target_samples:
            sig_1 = resample(sig_1, target_samples)
        if len(sig_2) != target_samples:
            sig_2 = resample(sig_2, target_samples)

        common_ts = np.linspace(0, overlap_duration, target_samples, endpoint=False)

        # Sliding-window RMS symmetry index
        window_samples = max(1, int(window_sec * analysis_rate))
        step_samples = max(1, int(step_sec * analysis_rate))

        si_values = []
        si_times = []

        for start in range(0, len(sig_1) - window_samples + 1, step_samples):
            end = start + window_samples
            rms_1 = np.sqrt(np.mean(sig_1[start:end] ** 2))
            rms_2 = np.sqrt(np.mean(sig_2[start:end] ** 2))

            denom = rms_1 + rms_2
            si = (rms_1 - rms_2) / denom if denom > 0 else 0.0

            si_values.append(si)
            center = min(start + window_samples // 2, len(common_ts) - 1)
            si_times.append(common_ts[center])

        si_array = np.array(si_values)
        si_timestamps = np.array(si_times)

        if len(si_array) == 0:
            return None

        overall_rms_1 = np.sqrt(np.mean(sig_1 ** 2))
        overall_rms_2 = np.sqrt(np.mean(sig_2 ** 2))

        output_rate = 1.0 / np.mean(np.diff(si_timestamps)) if len(si_timestamps) > 1 else 1.0 / step_sec

        return BilateralSymmetryResult(
            timestamps=si_timestamps,
            symmetry_index=si_array,
            sample_rate=output_rate,
            mean_si=float(np.mean(si_array)),
            std_si=float(np.std(si_array)),
            max_asymmetry=float(np.max(np.abs(si_array))),
            rms_file1=float(overall_rms_1),
            rms_file2=float(overall_rms_2),
            window_duration=window_sec,
            overlap_duration=float(overlap_duration),
            file1_sample_rate=sample_rate_1,
            file2_sample_rate=sample_rate_2,
            analysis_sample_rate=analysis_rate,
        )

    except Exception as e:
        print(f"[Features] Bilateral symmetry computation failed: {e}")
        return None


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
    """Calculate RMS in sliding windows."""
    n_samples = len(data)
    rms_values = []
    window_indices = []

    for start in range(0, n_samples - window_size + 1, step_size):
        end = start + window_size
        rms_val = np.sqrt(np.mean(data[start:end] ** 2))
        rms_values.append(rms_val)
        window_indices.append((start + end) // 2)

    return np.array(rms_values), np.array(window_indices)


def _calculate_median_frequency(data, fs, window_size, step_size):
    """Calculate median frequency in sliding windows using FFT with Hamming windowing."""
    n_samples = len(data)
    mf_values = []
    window_indices = []
    hamming = np.hamming(window_size)

    for start in range(0, n_samples - window_size + 1, step_size):
        end = start + window_size
        windowed_data = data[start:end] * hamming

        fft_vals = np.abs(rfft(windowed_data))
        freqs = rfftfreq(window_size, 1 / fs)

        cumsum = np.cumsum(fft_vals)
        total_power = cumsum[-1]

        if total_power > 0:
            median_idx = np.where(cumsum >= total_power / 2)[0]
            mf_values.append(freqs[median_idx[0]] if len(median_idx) > 0 else 0.0)
        else:
            mf_values.append(0.0)

        window_indices.append((start + end) // 2)

    return np.array(mf_values), np.array(window_indices)


def compute_fatigue(
    raw_signal: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    bandpass_low: float = 20.0,
    bandpass_high: float = 450.0,
    baseline_duration: float = 0.5,
    rms_threshold: float = 0.317,
    mf_threshold: float = -0.89,
    window_duration: float = 0.5,
    step_duration: float = 0.1,
) -> Optional[FatigueResult]:
    """Detect muscle fatigue based on RMS increase and median frequency decline.

    Monitors two complementary fatigue indicators:
    - RMS increases as fatigue progresses (increased motor unit recruitment, ~20-30%)
    - Median frequency decreases (slowing of muscle fiber conduction velocity)

    Parameters:
        raw_signal: 1D raw EMG signal
        timestamps: 1D timestamp array (same length as raw_signal)
        sample_rate: Estimated sample rate in Hz (used as fallback)
        bandpass_low: Bandpass filter low cutoff (Hz)
        bandpass_high: Bandpass filter high cutoff (Hz)
        baseline_duration: Duration of baseline period at start for RMS reference (seconds)
        rms_threshold: Fractional RMS increase to flag fatigue (default 0.317 = 31.7%)
        mf_threshold: Median frequency decline rate in Hz/sec (default -0.89)
        window_duration: Sliding window size in seconds
        step_duration: Sliding window step size in seconds

    Returns:
        FatigueResult with RMS/MF time series and fatigue onset points, or None on failure.
    """
    try:
        signal = raw_signal.copy()
        ts = timestamps.copy()

        # --- Timestamp preprocessing (same as other compute functions) ---
        mask = ~(np.isnan(ts) | np.isnan(signal))
        ts = ts[mask]
        signal = signal[mask]

        if len(ts) < 30:
            return None

        unique, counts = np.unique(ts, return_counts=True)
        if len(set(counts)) == 1 and counts[0] > 1:
            n_repeats = counts[0]
            new_ts = []
            for i in range(len(unique) - 1):
                interp = np.linspace(unique[i], unique[i + 1], n_repeats, endpoint=False)
                new_ts.extend(interp)
            last_interval = unique[-1] - unique[-2] if len(unique) > 1 else 1.0
            last_group = np.linspace(unique[-1], unique[-1] + last_interval, n_repeats, endpoint=False)
            new_ts.extend(last_group)
            ts = np.array(new_ts)

        inc_mask = np.diff(ts, prepend=ts[0]) > 0
        ts = ts[inc_mask]
        signal = signal[inc_mask]

        if len(ts) < 30 or np.all(np.diff(ts) == 0):
            return None

        dt = np.diff(ts)
        dt = dt[dt > 0]
        if len(dt) == 0 or np.median(dt) == 0:
            return None
        fs = 1.0 / np.median(np.diff(ts))

        # --- Bandpass filter ---
        nyq = 0.5 * fs
        if bandpass_high >= nyq:
            bandpass_high = nyq * 0.95
        b, a = butter(4, [bandpass_low / nyq, bandpass_high / nyq], btype='band')
        filtered = filtfilt(b, a, signal)

        # Rectified signal for RMS analysis
        rectified = np.abs(filtered)

        window_size = int(window_duration * fs)
        step_size = int(step_duration * fs)

        if window_size < 2 or step_size < 1:
            return None

        # --- Calculate sliding-window RMS ---
        rms_values, rms_indices = _calculate_sliding_rms(rectified, window_size, step_size)
        if len(rms_values) == 0:
            return None
        rms_times = ts[rms_indices]

        # Baseline RMS from first baseline_duration seconds
        baseline_end_idx = np.searchsorted(rms_times, ts[0] + baseline_duration)
        if baseline_end_idx < 1:
            baseline_end_idx = 1
        baseline_rms_val = float(np.mean(rms_values[:baseline_end_idx]))

        # RMS fatigue: percentage increase from baseline exceeds threshold
        if baseline_rms_val > 0:
            rms_change = (rms_values - baseline_rms_val) / baseline_rms_val
            rms_fatigue_mask = rms_change >= rms_threshold
            time_to_rms_fatigue = rms_times[rms_fatigue_mask] if np.any(rms_fatigue_mask) else None
        else:
            time_to_rms_fatigue = None

        # --- Calculate sliding-window median frequency ---
        mf_values, mf_indices = _calculate_median_frequency(filtered, fs, window_size, step_size)
        if len(mf_values) == 0:
            return None
        mf_times = ts[mf_indices]

        # MF fatigue: rate of decline exceeds threshold (Hz/sec)
        mf_rate = np.zeros_like(mf_values)
        if len(mf_values) > 1:
            dt_mf = np.diff(mf_times)
            dmf = np.diff(mf_values)
            # Avoid division by zero
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


@dataclass
class CentroidShiftResult:
    """Results from HD-EMG activation centroid shift analysis."""
    times: np.ndarray           # center timestamp of each window
    centroid_x: np.ndarray      # column centroid over time (0–7)
    centroid_y: np.ndarray      # row centroid over time (0–7)
    displacement: np.ndarray    # Euclidean distance from initial centroid (electrode-units)
    initial_centroid: tuple     # (cx0, cy0) — centroid at start of recording
    total_shift: float          # displacement at the final window
    mean_drift_rate: float      # total_shift / recording_duration (electrode-units/s)
    sample_rate: float


def compute_centroid_shift(
    data_64ch: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    window_duration: float = 0.5,
    step_duration: float = 0.1,
) -> Optional[CentroidShiftResult]:
    """Track the weighted activation centroid of the HD-EMG 8x8 grid over time.

    For each sliding window, computes per-channel RMS and treats it as a spatial
    weight on the 8x8 electrode grid. The centroid (column, row) is the
    RMS-weighted center of the grid. Displacement measures how far the centroid
    has shifted from its initial position, indicating fatigue-driven spatial
    redistribution of motor unit recruitment.

    Channel-to-grid mapping: channel_idx = col * 8 + (7 - row)
    Bottom-left = channel 0, column-major order.

    Parameters:
        data_64ch: Multi-channel EMG data, shape (64, n_samples)
        timestamps: 1D timestamp array (same length as n_samples)
        sample_rate: Estimated sample rate in Hz (used as fallback)
        window_duration: Sliding window size in seconds
        step_duration: Sliding window step size in seconds

    Returns:
        CentroidShiftResult with centroid time series and displacement, or None on failure.
    """
    try:
        if data_64ch.shape[0] != 64:
            return None

        ts = timestamps.copy()

        # --- Timestamp preprocessing ---
        # Remove samples where timestamp is NaN or any channel has NaN
        nan_mask = np.isnan(ts) | np.any(np.isnan(data_64ch), axis=0)
        ts = ts[~nan_mask]
        data = data_64ch[:, ~nan_mask]

        if len(ts) < 30:
            return None

        # Interpolate duplicated timestamps (same pattern as other compute functions)
        unique, counts = np.unique(ts, return_counts=True)
        if len(set(counts)) == 1 and counts[0] > 1:
            n_repeats = counts[0]
            new_ts = []
            for i in range(len(unique) - 1):
                interp = np.linspace(unique[i], unique[i + 1], n_repeats, endpoint=False)
                new_ts.extend(interp)
            last_interval = unique[-1] - unique[-2] if len(unique) > 1 else 1.0
            last_group = np.linspace(unique[-1], unique[-1] + last_interval, n_repeats, endpoint=False)
            new_ts.extend(last_group)
            ts = np.array(new_ts)

        # Enforce strictly increasing timestamps
        inc_mask = np.diff(ts, prepend=ts[0]) > 0
        ts = ts[inc_mask]
        data = data[:, inc_mask]

        if len(ts) < 30 or np.all(np.diff(ts) == 0):
            return None

        dt = np.diff(ts)
        dt = dt[dt > 0]
        if len(dt) == 0 or np.median(dt) == 0:
            return None
        fs = 1.0 / np.median(np.diff(ts))

        window_size = int(window_duration * fs)
        step_size = int(step_duration * fs)
        if window_size < 2 or step_size < 1:
            return None

        # Precompute grid column/row for each channel index.
        # channel_idx = col * 8 + (7 - row)  →  col = ch // 8, row = 7 - (ch % 8)
        ch_cols = np.array([ch // 8 for ch in range(64)], dtype=float)
        ch_rows = np.array([7 - (ch % 8) for ch in range(64)], dtype=float)

        centroid_x_list = []
        centroid_y_list = []
        time_list = []

        n_samples = data.shape[1]
        for start in range(0, n_samples - window_size + 1, step_size):
            end = start + window_size
            window = data[:, start:end]

            # Per-channel RMS as spatial weights
            w = np.sqrt(np.mean(window ** 2, axis=1))  # shape (64,)
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
        output_rate = 1.0 / np.mean(np.diff(times)) if len(times) > 1 else 1.0 / step_duration

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


@dataclass
class SpatialNonUniformityResult:
    """Results from HD-EMG spatial non-uniformity and activation area analysis."""
    times: np.ndarray               # center timestamp of each window
    cv: np.ndarray                  # coefficient of variation per window (std/mean of channel RMS)
    entropy: np.ndarray             # Shannon spatial entropy per window (bits; max=6 for 64 channels)
    activation_fraction: np.ndarray # fraction of channels active per window (0–1)
    threshold_source: str           # 'calibration' | 'auto'
    sample_rate: float


def compute_spatial_nonuniformity(
    data_64ch: np.ndarray,
    timestamps: np.ndarray,
    sample_rate: float,
    threshold_per_channel: Optional[np.ndarray] = None,
    window_duration: float = 0.5,
    step_duration: float = 0.1,
) -> Optional[SpatialNonUniformityResult]:
    """Track spatial activation non-uniformity and active area of the HD-EMG 8x8 grid over time.

    For each sliding window, computes three spatial metrics from per-channel RMS:
    - Coefficient of Variation (CV): std/mean of the 64-channel RMS distribution.
      Higher CV = more spatially uneven activation.
    - Shannon spatial entropy: -sum(p * log2(p)) where p = normalized per-channel RMS.
      Higher entropy = more uniform distribution (max 6 bits for 64 channels).
    - Activation fraction: fraction of channels whose RMS exceeds a threshold.
      Uses calibration thresholds if provided, otherwise falls back to window mean.

    Parameters:
        data_64ch: Multi-channel EMG data, shape (64, n_samples)
        timestamps: 1D timestamp array (same length as n_samples)
        sample_rate: Estimated sample rate in Hz (used as fallback)
        threshold_per_channel: Per-channel RMS thresholds from calibration, shape (64,).
            If None, uses per-window mean as the active/inactive threshold.
        window_duration: Sliding window size in seconds
        step_duration: Sliding window step size in seconds

    Returns:
        SpatialNonUniformityResult with CV, entropy, and activation fraction time series,
        or None on failure.
    """
    try:
        if data_64ch.shape[0] != 64:
            return None

        ts = timestamps.copy()

        # --- Timestamp preprocessing (same pattern as other compute functions) ---
        nan_mask = np.isnan(ts) | np.any(np.isnan(data_64ch), axis=0)
        ts = ts[~nan_mask]
        data = data_64ch[:, ~nan_mask]

        if len(ts) < 30:
            return None

        unique, counts = np.unique(ts, return_counts=True)
        if len(set(counts)) == 1 and counts[0] > 1:
            n_repeats = counts[0]
            new_ts = []
            for i in range(len(unique) - 1):
                interp = np.linspace(unique[i], unique[i + 1], n_repeats, endpoint=False)
                new_ts.extend(interp)
            last_interval = unique[-1] - unique[-2] if len(unique) > 1 else 1.0
            last_group = np.linspace(unique[-1], unique[-1] + last_interval, n_repeats, endpoint=False)
            new_ts.extend(last_group)
            ts = np.array(new_ts)

        inc_mask = np.diff(ts, prepend=ts[0]) > 0
        ts = ts[inc_mask]
        data = data[:, inc_mask]

        if len(ts) < 30 or np.all(np.diff(ts) == 0):
            return None

        dt = np.diff(ts)
        dt = dt[dt > 0]
        if len(dt) == 0 or np.median(dt) == 0:
            return None
        fs = 1.0 / np.median(np.diff(ts))

        window_size = int(window_duration * fs)
        step_size = int(step_duration * fs)
        if window_size < 2 or step_size < 1:
            return None

        threshold_source = 'calibration' if threshold_per_channel is not None else 'auto'
        eps = 1e-12  # small constant to avoid log(0)

        cv_list = []
        entropy_list = []
        activation_list = []
        time_list = []

        n_samples = data.shape[1]
        for start in range(0, n_samples - window_size + 1, step_size):
            end = start + window_size
            window = data[:, start:end]

            # Per-channel RMS
            w = np.sqrt(np.mean(window ** 2, axis=1))  # shape (64,)
            total_w = float(np.sum(w))
            if total_w == 0:
                continue

            # Coefficient of variation
            mean_w = float(np.mean(w))
            cv = float(np.std(w) / mean_w) if mean_w > 0 else 0.0

            # Shannon spatial entropy (bits)
            p = w / total_w
            entropy = float(-np.sum(p * np.log2(p + eps)))

            # Activation area
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
        output_rate = 1.0 / np.mean(np.diff(times)) if len(times) > 1 else 1.0 / step_duration

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

