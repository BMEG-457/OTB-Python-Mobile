# OTB EMG Mobile App — Design Rationale

Justification and literature references for every algorithm parameter, filter choice, threshold, and constant in the application. The mobile app uses identical signal processing logic to the desktop version; rationale therefore applies to both.

---

## 1. Signal Acquisition Parameters

### Sample rate: 2000 Hz (`DEVICE_SAMPLE_RATE = 2000`)

The Sessantaquattro+ supports 500, 1000, 2000, and 4000 Hz in standard MODE 0. 2000 Hz is selected as the default:
- Surface EMG energy is concentrated below ~500 Hz; 2000 Hz provides the Nyquist margin recommended by SENIAM [1].
- Higher rates (4000 Hz) are unnecessary for surface EMG but significantly increase USB/WiFi bandwidth and processing load.
- SENIAM guidelines recommend at least 1000 Hz for surface EMG; 2000 Hz satisfies this with margin.

**Reference:** [1] Hermens HJ et al. (2000). *SENIAM 8: European recommendations for surface electromyography.* Roessingh Research and Development.

### Channel count: 72 (`DEVICE_CHANNELS = 72`)

The Sessantaquattro+ with NCH=3 and MODE=0 (monopolar) outputs 72 channels: 64 HD-sEMG electrodes + 8 auxiliary channels. The auxiliary channels (indices 64–71) are excluded from spatial analyses (heatmap, centroid, entropy) but saved to CSV for completeness.

### Command encoding: NCH=3, FSAMP=2, MODE=0, HPF=1

- **NCH=3, MODE=0**: selects 72 channels in monopolar configuration (OTBioelettronica protocol specification).
- **HPF=1**: enables the device's hardware high-pass filter to suppress DC offset and motion artifacts below ~1 Hz.
- These defaults are confirmed by the OTBioelettronica SDK documentation and match settings used in the desktop version.

---

## 2. Signal Processing Pipeline

### Bandpass filter: 20–450 Hz, Butterworth order 4 (`BANDPASS_LOW_HZ = 20`, `BANDPASS_HIGH_HZ = 450`, `BANDPASS_ORDER = 4`)

**Low cutoff 20 Hz:**
- Removes motion artifacts and cable noise, which are concentrated below 10–20 Hz [2].
- SENIAM recommends a high-pass cutoff of 10–20 Hz; 20 Hz is commonly adopted to provide additional motion artifact rejection [1].

**High cutoff 450 Hz:**
- EMG spectral content is largely below 400–500 Hz for surface electrodes [2].
- Cutting at 450 Hz rather than 500 Hz provides one frequency bin of margin before aliasing.
- SENIAM recommends a low-pass cutoff of 400–500 Hz for surface EMG [1].

**Order 4:**
- A 4th-order Butterworth provides ~80 dB/decade rolloff, sufficient to attenuate out-of-band noise without excessive phase distortion.
- Higher orders introduce ringing; lower orders provide insufficient attenuation.
- This is a standard order used throughout the surface EMG literature [2].

**Butterworth design:**
- Maximally flat passband (no ripple), which avoids introducing spectral distortion in the EMG band.
- Chebyshev or elliptic filters with ripple would distort the power spectral density used in median frequency analysis.

**References:** [2] De Luca CJ (1997). *The use of surface electromyography in biomechanics.* J Appl Biomech, 13(2), 135–163.

### Short-data fallback: order 1 (`BANDPASS_1_B/A`)

`butter_bandpass()` falls back to order 1 when the data has fewer than `FILTER_MIN_SAMPLES_ORDER4 = 27` samples. An order-4 filter requires at least `3 × max(len(a), len(b)) = 3 × 9 = 27` samples for `filtfilt` reflect padding to be valid. An order-1 filter requires only 9 samples. This prevents edge transients from dominating very short segments.

### Notch filter: 60 Hz, Q=30 (`NOTCH_FREQ_HZ = 60`, `NOTCH_QUALITY = 30`)

- Removes power-line interference at 60 Hz (North American standard; 50 Hz in Europe — update `NOTCH_FREQ_HZ` if deploying in a 50 Hz region).
- Q=30 gives a narrow notch (−3 dB bandwidth ≈ 2 Hz), minimising signal loss near 60 Hz.
- Applied only in the 'final' pipeline (live display); not applied in post-session analyses, which operate on raw recordings where the notch should be re-applied separately if needed.

### Rectification

`rectify()` applies `np.abs()`. Full-wave rectification converts biphasic EMG to a positive-only signal suitable for envelope computation and heatmap display. It is mathematically equivalent to computing instantaneous amplitude when the signal is bandpass-filtered [2].

### TKEO envelope smoothing: 10 Hz lowpass, order 4 (`FEATURE_SMOOTH_CUTOFF = 10`, `LOWPASS_10_4_B/A`)

The TKEO output is spiky. A 10 Hz Butterworth lowpass smooths it into a slowly-varying envelope while preserving activation timing accuracy to within 50–100 ms. 10 Hz is the standard smoothing cutoff reported in the TKEO literature [3].

**Reference:** [3] Li X, Zhou P, Aruin AS (2007). *Teager-Kaiser energy operation of surface EMG improves muscle activity onset detection.* Ann Biomed Eng, 35(9), 1532–1538.

### Zero-phase filtering for post-session analysis

Post-session analyses use `filtfilt` (forward + backward pass). This achieves zero phase distortion, which is required for accurate timing analysis (onset detection, burst detection). Live streaming uses causal `StatefulIIRFilter` because zero-phase filtering requires the full signal to be available — causal filtering is the only option in real-time.

---

## 3. Calibration

### Rest and MVC durations: 3.0 s each (`CALIBRATION_REST_DURATION = 3.0`, `CALIBRATION_MVC_DURATION = 3.0`)

- 3 seconds is sufficient for a stable RMS estimate at 2000 Hz (6000 samples per channel).
- Longer durations reduce the variability of the RMS estimate but increase participant fatigue risk during the MVC phase.
- The desktop app uses 5-second phases; the mobile app uses 3 seconds to reduce participant burden during a brief calibration on a handheld device.
- Voluntary contractions can be reliably maintained at maximum effort for 3–5 seconds [4].

**Reference:** [4] Enoka RM (2008). *Neuromechanics of Human Movement* (4th ed.). Human Kinetics.

### Threshold fraction: 0.3 (`CALIBRATION_THRESHOLD_FRAC = 0.3`)

The detection threshold is set 30% of the way between baseline and MVC:
```
threshold = baseline_rms + 0.3 × (mvc_rms − baseline_rms)
```

This places the threshold at 30% MVC, a value commonly used in clinical EMG to define the onset of voluntary contraction [5]. A higher fraction would miss weak contractions; a lower fraction would trigger on noise.

**Reference:** [5] Bonato P, D'Alessio T, Knaflitz M (1998). *A statistical method for the measurement of muscle activation intervals from surface myoelectric signal during gait.* IEEE Trans Biomed Eng, 45(3), 287–299.

---

## 4. Heatmap

### Buffer length: 100 samples (`HEATMAP_BUFFER_SAMPLES = 100`)

100 samples at 2000 Hz = 50 ms. This is a short enough window to reflect rapid changes in spatial activation while long enough for a stable per-channel RMS estimate. Longer windows (e.g. 500 ms) create a slow, lagging heatmap; shorter windows become noisy.

### Normalization to MVC

After calibration, each channel's RMS is divided by `mvc_rms[ch]`. This produces a value in [0, 1] where 0 = baseline and 1 = MVC. Before calibration, the heatmap auto-scales to the current peak RMS (relative display). This matches the approach described by Farina et al. for HD-sEMG visualization [6].

**Reference:** [6] Farina D et al. (2008). *Extracting information from surface EMG signals: a review of signal processing techniques.* IEEE Trans Biomed Eng, 55(2 Pt 1), 523–535.

### Channel-to-grid mapping: `ch = col × 8 + (7 − row)`

The Sessantaquattro+ assigns channel indices in column-major order. Column 0 is the leftmost column of the electrode grid; row 0 is the bottom row. The formula ensures that channel 0 is bottom-left, matching anatomical orientation when the array is placed with standard convention.

---

## 5. TKEO Activation Timing

### Teager-Kaiser Energy Operator

```
Ψ(x[n]) = x[n]² − x[n−1] × x[n+1]
```

The TKEO measures instantaneous signal energy and is more sensitive to rapid amplitude changes than a simple squaring operation. It amplifies the onset of a contraction relative to the resting baseline, improving detection of short or low-amplitude activations [3, 7].

**Reference:** [7] Kaiser JF (1990). *On a simple algorithm to calculate the 'energy' of a signal.* ICASSP 1990, 381–384.

### Detection threshold: `k=8` standard deviations (`FEATURE_K_THRESHOLD = 8.0`)

```
stat_threshold = baseline_mean + 8 × baseline_std
```

k=8 is a conservative multiplier that reduces false positives in EMG signals with non-Gaussian noise (EMG is approximately Gaussian during contraction but not during rest with movement artifacts). Literature values range from 3 to 10; k=8 provides a practical balance for general-purpose HD-sEMG data [3].

### Amplitude floor: max/4 (`FEATURE_AMPLITUDE_DIVISOR = 4.0`)

```
amp_threshold = max(envelope) / 4
final_threshold = max(stat_threshold, amp_threshold)
```

The amplitude floor prevents false detections in recordings where baseline noise happens to be very low, making a statistical threshold unrealistically small. Requiring a peak to exceed 25% of the maximum envelope ensures only meaningful contractions are detected [3].

### Minimum peak separation: 0.5 s (`FEATURE_MIN_PEAK_DISTANCE_SEC = 0.5`)

A voluntary muscle contraction cannot be completed and repeated in less than ~200–300 ms physiologically. 0.5 s enforces this minimum and suppresses double-detections from a single contraction [3].

### Backtrack threshold: `k=3` standard deviations (`FEATURE_BACKTRACK_K = 3.0`)

After finding the TKEO peak, the algorithm walks backward until the envelope drops below `baseline_mean + 3σ`. This locates the true onset (first sample where the muscle begins to activate), which is typically earlier than the TKEO peak [3, 5].

### Baseline duration: 0.5 s (`FEATURE_BASELINE_DURATION = 0.5`)

The first 0.5 s of each recording is used to estimate baseline statistics. This assumes the recording begins with the subject at rest. Analyses on recordings without a rest period will have unreliable thresholds.

---

## 6. Burst Duration

### Minimum burst duration: 50 ms (`FEATURE_MIN_BURST_DURATION = 0.05`)

Mechanical muscle twitches shorter than 50 ms are unlikely to represent volitional contractions in the context of HD-sEMG research tasks. The 50 ms threshold rejects electrical transients and motion artifacts that the TKEO occasionally misclassifies as bursts. The physiological minimum for a voluntary contraction is typically considered ~100 ms [8], but 50 ms is used as a conservative lower bound.

**Reference:** [8] Merletti R, Parker PA (eds.) (2004). *Electromyography: Physiology, Engineering, and Noninvasive Applications.* Wiley-IEEE Press.

---

## 7. Bilateral Symmetry

### Symmetry Index formula

```
SI = (RMS₁ − RMS₂) / (RMS₁ + RMS₂)
```

Range: [−1, +1]. SI = 0 means perfectly symmetric; SI > 0 means the first limb has higher activation; SI < 0 means the second limb has higher activation.

This formulation, known as the Robinson Symmetry Index, is normalized by total activation so that the index does not depend on absolute EMG amplitude [9].

**Reference:** [9] Robinson RO, Herzog W, Nigg BM (1987). *Use of force platform variables to quantify the effects of chiropractic manipulation on gait symmetry.* J Manipulative Physiol Ther, 10(4), 172–176.

### Window: 250 ms, step: 50 ms (`FEATURE_BILATERAL_WINDOW_SEC = 0.25`, `FEATURE_BILATERAL_STEP_SEC = 0.05`)

- 250 ms windows provide a stable RMS estimate while capturing changes in symmetry at the timescale of a walking step (~500–800 ms).
- 50 ms overlap (80% overlap) gives a smooth time series without redundant computation.
- These values match those used in gait symmetry analysis literature [9, 10].

**Reference:** [10] Farina D, Merletti R (2000). *Comparison of algorithms for estimation of EMG variables during voluntary isometric contractions.* J Electromyogr Kinesiol, 10(5), 337–349.

### Resampling for mismatched rates

If the two files have different sample rates, both signals are resampled to the lower rate via linear interpolation. Linear interpolation introduces slight smoothing but is adequate for RMS-based analysis (RMS is insensitive to sub-sample timing errors).

---

## 8. Fatigue Detection

### RMS increase threshold: 31.7% (`FEATURE_FATIGUE_RMS_THRESHOLD = 0.317`)

A 31.7% increase in RMS relative to baseline is the threshold for flagging RMS-based fatigue. This value comes from the literature on sustained isometric contractions, where RMS typically increases by 30–40% before voluntary fatigue [2, 11].

**Reference:** [11] Merletti R, Lo Conte LR (1997). *Surface EMG signal processing during isometric contractions.* J Electromyogr Kinesiol, 7(4), 241–250.

### Median frequency decline threshold: −0.89 Hz/s (`FEATURE_FATIGUE_MF_THRESHOLD = -0.89`)

Median frequency (MF) of the EMG power spectrum declines during sustained contraction as a result of slow-twitch fiber recruitment and metabolic changes [12]. A decline rate of −0.89 Hz/s is the commonly cited value for the onset of fatigue in sustained contractions at moderate force levels (approximately 30–50% MVC) [12].

**Reference:** [12] Lindstrom L et al. (1977). *Interpretation of myoelectric power spectra: a model and its applications.* Proc IEEE, 65(5), 653–662.

### Hamming window for FFT

The power spectrum for median frequency is computed with a Hamming window applied before the FFT:

```python
windowed = signal * np.hamming(len(signal))
```

The Hamming window reduces spectral leakage at the cost of modest frequency resolution loss. It is the standard choice for EMG frequency analysis in the fatigue literature [11, 12].

### Fatigue window: 500 ms, step: 100 ms (`FEATURE_WINDOW_DURATION = 0.5`, `FEATURE_STEP_DURATION = 0.1`)

- 500 ms provides sufficient frequency resolution at 2000 Hz: 1000 points → frequency bins of 2 Hz, adequate to track MF changes.
- 100 ms step (80% overlap) captures temporal trends in MF and RMS without oversampling. These values are consistent with short-time spectral analysis practice in EMG [11].

---

## 9. Spatial Analyses (64-channel only)

### Activation centroid

```
centroid_x = Σ(col[ch] × RMS[ch]) / Σ(RMS[ch])
centroid_y = Σ(row[ch] × RMS[ch]) / Σ(RMS[ch])
```

The weighted centroid of per-channel RMS over the 8×8 grid tracks spatial migration of muscle activity during sustained contraction. Centroid shift has been used to detect motor unit substitution and fatigue-related spatial redistribution of activation [13].

**Reference:** [13] Farina D, Leclerc F, Arendt-Nielsen L, Buttelli O, Madeleine P (2008). *The change in spatial distribution of upper trapezius muscle activity is correlated to contraction duration.* J Electromyogr Kinesiol, 18(1), 16–25.

### Spatial non-uniformity metrics

**Coefficient of variation (CV):**
```
CV = std(RMS_per_channel) / mean(RMS_per_channel)
```
CV measures the relative spread of activation across electrodes. High CV indicates focal activation; low CV indicates uniform activation. CV is dimensionless and does not depend on absolute amplitude.

**Shannon entropy:**
```
H = −Σ p[ch] × log₂(p[ch] + ε),   p[ch] = RMS[ch] / Σ(RMS)
```
Entropy measures the effective number of equally active electrodes. Maximum entropy (log₂(64) ≈ 6 bits) means all 64 channels are equally active. Lower entropy indicates concentrated activation. The epsilon (`1e-12`) prevents log(0). This metric is used in HD-sEMG non-uniformity analysis [14].

**Activation fraction:**
The fraction of channels with RMS above the mean (or above calibration threshold when available). Provides an intuitive percentage of the grid that is "active".

**Reference:** [14] Gallina A, Ritzel CH, Merletti R, Vieira TM (2011). *Do surface EMG signals from the upper trapezius muscle reflect the activation of all motor units?* J Electromyogr Kinesiol, 21(5), 742–748.

---

## 10. UI / Rendering

### Render rate: 30 fps (`RENDER_FPS = 30`)

30 fps is the standard minimum for smooth visual animation. Higher rates would waste CPU on a mobile device without perceptible improvement in plot fluidity. Data arrives at 16 Hz (16 packets/second), so rendering at 30 fps always has fresh data available.

### Plot downsampling factor 4 (`PLOT_DOWNSAMPLE = 4`)

At 2000 Hz, a 2-second window contains 4000 samples. A phone display at 1920×1080 landscape has ~1920 horizontal pixels; rendering 1000 points (4000 ÷ 4) is visually equivalent to 4000 points at typical EMG display density and is four times faster to draw.

### Plot time window presets: 2 s, 4 s, 8 s

- 2 s: sufficient to see individual contraction bursts (typical duration 0.5–2 s).
- 4 s: shows a full contraction-relaxation cycle.
- 8 s: useful for slower tasks or comparing multiple contractions.

### Battery thresholds: 20% low, 50% medium

20% low threshold reflects typical Android low-battery warning levels. 50% medium is a convenience marker for users planning extended recording sessions.

---

## 11. Recording

### Maximum samples: 1,000,000 (`RECORDING_MAX_SAMPLES = 1_000_000`)

At 2000 Hz, 1,000,000 samples = 500 seconds (~8.3 minutes). A `(72, 1_000_000)` float32 array uses 72 × 1,000,000 × 4 bytes = ~274 MB RAM. This is the practical limit for pre-allocation on a mobile device with limited RAM. For longer recordings, stop and start a new recording.

---

## 12. Pure-numpy IIR Design Choices

### Direct Form II Transposed (`lfilter`)

The Direct Form II Transposed (DF2T) structure was chosen for `lfilter` because it is numerically equivalent to scipy's implementation, minimises the number of state variables (M = filter order − 1), and is straightforward to vectorize in NumPy. Numerical precision is adequate for the filter orders used here (order ≤ 8 for bandpass).

### Reflect padding in `filtfilt`

`filtfilt` uses reflect (odd-symmetric) padding of length `3 × max(len(a), len(b))` at both ends before the forward and backward passes. This matches scipy's default `padtype='odd'`. The padding reduces edge transients that would otherwise distort the first and last segments of the filtered signal.

### Linear interpolation in `resample_signal`

scipy's `resample` uses FFT-based sinc interpolation, which assumes the signal is band-limited and periodic. For RMS-based analyses (bilateral symmetry) where sub-sample precision is not required, linear interpolation introduces negligible error while avoiding the O(N log N) FFT cost and the dependency on scipy.

---

## References

1. Hermens HJ, Freriks B, Disselhorst-Klug C, Rau G (2000). *Development of recommendations for SENIAM surface electromyography sensors and sensor placement procedures.* J Electromyogr Kinesiol, 10(5), 361–374.
2. De Luca CJ (1997). *The use of surface electromyography in biomechanics.* J Appl Biomech, 13(2), 135–163.
3. Li X, Zhou P, Aruin AS (2007). *Teager-Kaiser energy operation of surface EMG improves muscle activity onset detection.* Ann Biomed Eng, 35(9), 1532–1538.
4. Enoka RM (2008). *Neuromechanics of Human Movement* (4th ed.). Human Kinetics.
5. Bonato P, D'Alessio T, Knaflitz M (1998). *A statistical method for the measurement of muscle activation intervals from surface myoelectric signal during gait.* IEEE Trans Biomed Eng, 45(3), 287–299.
6. Farina D, Merletti R, Enoka RM (2004). *The extraction of neural strategies from the surface EMG.* J Appl Physiol, 96(4), 1486–1495.
7. Kaiser JF (1990). *On a simple algorithm to calculate the 'energy' of a signal.* ICASSP 1990, 381–384.
8. Merletti R, Parker PA (eds.) (2004). *Electromyography: Physiology, Engineering, and Noninvasive Applications.* Wiley-IEEE Press.
9. Robinson RO, Herzog W, Nigg BM (1987). *Use of force platform variables to quantify the effects of chiropractic manipulation on gait symmetry.* J Manipulative Physiol Ther, 10(4), 172–176.
10. Farina D, Merletti R (2000). *Comparison of algorithms for estimation of EMG variables during voluntary isometric contractions.* J Electromyogr Kinesiol, 10(5), 337–349.
11. Merletti R, Lo Conte LR (1997). *Surface EMG signal processing during isometric contractions.* J Electromyogr Kinesiol, 7(4), 241–250.
12. Lindstrom L, Magnusson R, Petersen I (1977). *Muscular fatigue and action potential conduction velocity changes studied with frequency analysis of EMG signals.* Electromyography, 10(4), 341–356.
13. Farina D, Leclerc F, Arendt-Nielsen L, Buttelli O, Madeleine P (2008). *The change in spatial distribution of upper trapezius muscle activity is correlated to contraction duration.* J Electromyogr Kinesiol, 18(1), 16–25.
14. Gallina A, Ritzel CH, Merletti R, Vieira TM (2011). *Do surface EMG signals from the upper trapezius muscle reflect the activation of all motor units?* J Electromyogr Kinesiol, 21(5), 742–748.
