# OTB EMG Mobile Application — Detailed Architecture Overview

This document describes the Android application in `mobile_app/`. It is written for a reader with no prior context, but assumes familiarity with Python and basic signal processing concepts. Readers already familiar with the desktop version (`BMEG 457 scripts/`) will find a "Key differences from desktop" note in each relevant section.

---

## Table of Contents

1. [What This Application Does](#1-what-this-application-does)
2. [Why Android? Why Kivy?](#2-why-android-why-kivy)
3. [Build System](#3-build-system)
4. [Project Structure](#4-project-structure)
5. [Application Entry Point](#5-application-entry-point)
6. [Screen Navigation](#6-screen-navigation)
7. [Device Communication Protocol](#7-device-communication-protocol)
8. [Live Data Pipeline](#8-live-data-pipeline)
9. [Threading Model and UI Safety](#9-threading-model-and-ui-safety)
10. [Signal Processing — Pre-computed Coefficients](#10-signal-processing--pre-computed-coefficients)
11. [Pure-numpy IIR Filter Implementation](#11-pure-numpy-iir-filter-implementation)
12. [Calibration](#12-calibration)
13. [Visualization Widgets](#13-visualization-widgets)
14. [HD-sEMG View Modes and Aggregation](#14-hd-semg-view-modes-and-aggregation)
15. [Recording](#15-recording)
16. [File Storage and Android Permissions](#16-file-storage-and-android-permissions)
17. [Data Analysis Mode](#17-data-analysis-mode)
18. [Feature Extraction Algorithms](#18-feature-extraction-algorithms)
19. [HD-sEMG Spatial Analyses](#19-hd-semg-spatial-analyses)
20. [Dependency Rationale and What Was Removed](#20-dependency-rationale-and-what-was-removed)
21. [Glossary](#21-glossary)
22. [References](#22-references)

---

## 1. What This Application Does

This is an Android port of the OTB EMG desktop application. It connects wirelessly to the OTB Sessantaquattro+ high-density surface EMG (HD-sEMG) device, streams and visualizes 64-channel EMG data in real time, and runs post-hoc feature extraction on recorded sessions.

### What is EMG?

Electromyography (EMG) measures the electrical activity produced by skeletal muscles during contraction. Surface electrodes placed on the skin pick up the summed electrical potential from many individual motor units (a motor unit = one motor neuron + all the muscle fibers it controls). The raw signal is a broadband noise-like waveform whose amplitude increases with contraction force and whose frequency content shifts with fatigue.

High-density surface EMG (HD-sEMG) uses an 8×8 grid of 64 electrodes placed close together, allowing visualization of the spatial distribution of muscle activation across the skin surface — revealing motor unit territories, propagation directions, and fatigue-related spatial shifts.

The application has two operating modes:

- **Live Data Mode** (`LiveDataScreen`): Real-time streaming, visualization, and recording of 64-channel HD-sEMG data.
- **Data Analysis Mode** (`DataAnalysisScreen`): Post-hoc analysis of previously recorded CSV files.

---

## 2. Why Android? Why Kivy?

### Why Android?

The motivation is clinical portability. A researcher or clinician studying muscle function often needs data collection at the point of care or in a gym/sports facility, not at a desktop workstation. A tablet running the same acquisition and analysis software eliminates the need for a laptop.

### Why Kivy?

[Kivy](https://kivy.org/) is a Python UI framework that targets both desktop and mobile (Android, iOS) from a single codebase. It is the only mature Python option with an established toolchain ([Buildozer](https://github.com/kivy/buildozer) + [python-for-android](https://github.com/kivy/python-for-android)) for building standalone Android APKs from Python source.

The alternative would be rewriting the application in Kotlin/Java (Android native) or using a cross-platform framework like Flutter or React Native, which would require discarding the existing Python signal processing code and re-implementing all algorithms.

**Key differences from desktop**: The desktop app uses PyQt5 + pyqtgraph. Neither can target Android. Kivy replaces both: it handles UI layout and also provides the canvas API used for real-time EMG plot rendering.

---

## 3. Build System

### Buildozer

[Buildozer](https://github.com/kivy/buildozer) is a command-line tool that automates the Android build process: it downloads the Android NDK/SDK, compiles Python + dependencies into native ARM code using python-for-android (p4a), and packages everything into an APK. The configuration lives in `buildozer.spec`.

```
mobile_app/
└── buildozer.spec     Main build configuration
```

Key settings in `buildozer.spec`:

| Setting | Value | Why |
|---|---|---|
| `requirements` | `python3,kivy==2.3.0,numpy` | Minimal set; scipy and matplotlib removed (see §20) |
| `android.permissions` | `INTERNET,MANAGE_EXTERNAL_STORAGE` | TCP WiFi + public file access |
| `android.api` | 33 (Android 13) | Targets modern devices |
| `android.minapi` | 21 (Android 5.0) | Broad device compatibility |
| `android.archs` | `arm64-v8a, armeabi-v7a` | Covers all current Android phones/tablets |
| `orientation` | `landscape` | Wider screen real estate for multi-track plots |

**Build command** (in WSL with symlink at `~/otb-mobile`):
```bash
cd ~/otb-mobile && VIRTUAL_ENV=1 buildozer android debug 2>&1 | tee ~/build.log
```

`VIRTUAL_ENV=1` suppresses buildozer's attempt to install packages with `--user`, which fails inside a pipx-managed environment.

### python-for-android (p4a)

p4a cross-compiles Python and each dependency to ARM binary code. Dependencies that require Fortran (scipy) or C extensions without an existing p4a "recipe" cannot be compiled. This constraint drove the removal of scipy and matplotlib (§20).

---

## 4. Project Structure

```
mobile_app/
├── main.py                          App entry point (OTBApp Kivy App class)
├── buildozer.spec                   Android build configuration
├── scripts/
│   └── compute_filter_coeffs.py    Utility: regenerate IIR coefficients for config.py
├── tests/                           Standalone scripts for validating algorithms
└── app/
    ├── core/
    │   ├── config.py               All tunable parameters + pre-computed filter coefficients
    │   ├── device.py               SessantaquattroPlus — TCP protocol
    │   └── paths.py                Android-aware data directory resolution
    ├── data/
    │   └── data_receiver.py        DataReceiverThread — background TCP reader (threading.Thread) [planned, not yet created]
    ├── managers/
    │   ├── recording_manager.py    Accumulates raw samples and writes CSV files
    │   └── streaming_controller.py Manages thread state and Kivy Clock tick
    ├── processing/
    │   ├── iir_filter.py           Pure-numpy IIR filter, zero-phase, peak detection, resampling
    │   ├── filters.py              Bandpass, notch, rectify (uses pre-computed coefficients)
    │   ├── features.py             Post-hoc EMG feature extraction (6 analyses)
    │   ├── pipeline.py             ProcessingPipeline registry (same pattern as desktop)
    │   └── transforms.py           FFT transform
    └── ui/
        ├── screens/
        │   ├── selection_screen.py     Mode selection (entry screen)
        │   ├── live_data_screen.py     Live streaming, calibration, recording
        │   └── data_analysis_screen.py Post-hoc analysis of CSV recordings
        └── widgets/
            ├── emg_plot_widget.py       Single-channel rolling EMG plot (Kivy canvas)
            ├── multi_track_plot.py      Stacked N-track rolling plot (Kivy canvas)
            ├── heatmap_widget.py        8×8 HD-EMG activation heatmap (Kivy canvas)
            └── calibration_popup.py     Two-phase calibration popup with progress bar
```

---

## 5. Application Entry Point

`main.py` defines `OTBApp`, a subclass of `kivy.app.App`. Kivy's framework calls `build()` once at startup to construct the widget tree.

```python
class OTBApp(App):
    def build(self):
        self.device = SessantaquattroPlus()   # No socket yet
        sm = ScreenManager()
        sm.add_widget(SelectionScreen(name='selection'))
        sm.add_widget(LiveDataScreen(name='live_data', device=self.device))
        sm.add_widget(DataAnalysisScreen(name='data_analysis'))
        return sm                              # Root widget
```

`ScreenManager` is a Kivy container that holds multiple `Screen` objects and transitions between them. Only one screen is active and visible at a time. Navigation is performed by setting `sm.current = 'screen_name'`.

**Android permission check**: `on_start()` runs after the UI is first rendered. On Android, it checks whether `MANAGE_EXTERNAL_STORAGE` has been granted (required for writing to `/sdcard/Documents/` — see §16). If not, a popup guides the user to grant it in Settings.

**Cleanup**: `on_stop()` is called when the app is closed or backgrounded. It calls `device.stop_server()` to close the TCP socket, preventing the device from remaining blocked waiting for data.

**Key differences from desktop**: The desktop creates three independent `QWidget` windows and switches between them by showing/hiding. The mobile app uses Kivy's `ScreenManager`, which is the idiomatic Kivy pattern for multi-screen navigation.

---

## 6. Screen Navigation

```
SelectionScreen ('selection')
    ├── Live Data Viewing → LiveDataScreen ('live_data')
    └── Data Analysis     → DataAnalysisScreen ('data_analysis')

LiveDataScreen
    └── Back → SelectionScreen

DataAnalysisScreen
    └── Back → SelectionScreen
```

`ScreenManager` animates transitions with a slide effect by default. Navigation is always initiated from within each screen by setting `self.manager.current = 'target_name'`.

---

## 7. Device Communication Protocol

The protocol is identical to the desktop app. The mobile app is the TCP server; the device is the TCP client.

### Connection Sequence

1. Android phone/tablet opens TCP server on `0.0.0.0:45454`
2. The phone's WiFi must be connected to the device's access point (SSID `192.168.1.x` subnet)
3. Device connects to phone as TCP client
4. Phone sends a 2-byte configuration command
5. Device begins streaming data packets

### Network Check

Before attempting `start_server()`, `is_connected_to_device_network()` opens a UDP socket, connects to `8.8.8.8:80` (doesn't actually send data — just causes the OS to resolve which interface would be used), reads the local IP, and checks if it starts with `192.168.1`. A 2-second socket timeout prevents hanging on that check. If the check fails, `LiveDataScreen` shows an error immediately without waiting 15 seconds for the connection timeout.

**Why check the network before opening the server?** Without this check, a user who forgets to switch WiFi would wait the full `DEVICE_CONNECT_TIMEOUT = 15` seconds before getting an error. The quick UDP trick gives instant feedback at negligible cost.

### Command Encoding

A 16-bit integer packed as 2 big-endian bytes encodes all configuration parameters:

```
Bit  0     : GO    — 1 = start streaming
Bit  1     : REC   — SD card recording (unused by this app)
Bits 2–3   : TRIG  — trigger mode
Bits 4–5   : EXTEN — extension factor
Bit  6     : HPF   — hardware high-pass filter (1 = 10.5 Hz enabled)
Bit  7     : HRES  — ADC resolution (0 = 16-bit)
Bits 8–10  : MODE  — working mode (0 = monopolar)
Bits 11–12 : NCH   — channel count selector (3 = 72 ch in monopolar mode)
Bits 13–14 : FSAMP — sampling frequency (2 = 2000 Hz)
```

Defaults: `FSAMP=2` (2000 Hz), `NCH=3` (72 channels — 64 EMG + 8 auxiliary), `MODE=0` (monopolar), `HPF=1`, `GO=1`. These are defined as constants in `app/core/config.py` (`DEVICE_FSAMP`, `DEVICE_NCH`, etc.) so they appear in one place.

### Packet Format

At 2000 Hz with 72 channels: each packet = `72 × 2 × 125 = 18000 bytes`. The device sends 16 packets per second. Each sample is a **big-endian signed 16-bit integer** (range: −32768 to +32767). Packets are interleaved: all channels for sample 0, then all channels for sample 1, etc. After unpacking, the array is reshaped to `(nchannels, n_samples)`.

---

## 8. Live Data Pipeline

```
Device (WiFi TCP)
    │  18000 bytes/packet × 16 packets/sec = 2000 Hz × 72 channels
    ▼
DataReceiverThread  (daemon threading.Thread — never restarted)
    │
    │  1. socket.recv() accumulates bytes
    │  2. Extract complete packets from byte buffer
    │  3. struct.unpack() → (nchannels, n_samples) numpy array
    │
    ├── on_stage('raw',       data)   → RecordingManager.on_data_for_recording
    │                                 → CalibrationPopup._collect_sample (during calib)
    │
    ├── filtered  = Pipeline('filtered').run(data)   [bandpass only]
    ├── on_stage('filtered',  filtered)
    │
    ├── rectified = Pipeline('rectified').run(filtered)  [abs]
    ├── on_stage('rectified', rectified)
    │
    ├── processed = Pipeline('final').run(data)  [bandpass + notch + rectify]
    ├── on_stage('final',     processed)
    │                                 → LiveDataScreen._on_data()
    │                                       → self._pending_data = data
    │
    └── (receiver loops forever — running flag only controls track feeding)

Kivy Clock.schedule_interval(ui_tick, 1/60)   ← 60 fps
    └── LiveDataScreen._ui_tick(dt)
          reads self._pending_data (clears it)
          → _render_plot_panel(data)  OR  _render_heatmap_panel(data)
```

### Pending-data Pattern

The receiver thread calls `on_stage('final', data)` approximately 16 times per second (one call per packet). The 60fps UI tick runs about 4× more often than data arrives. The `_pending_data` field bridges the two:

- `_on_data()` (receiver thread): sets `self._pending_data = data.copy()`
- `_ui_tick()` (Kivy main thread): reads and clears `_pending_data`; if `None`, returns immediately

This prevents stacked redraws when the receiver sends multiple packets before the UI can render. Only the most recent packet is rendered per frame.

**Key differences from desktop**: The desktop uses `QTimer` + `Track.buffer.feed()` and the timer reads from buffers. The mobile decouples update (storing to `_pending_data`) from render (reading in `_ui_tick`). Both achieve the same result — 60fps rendering of data arriving at 16 Hz.

---

## 9. Threading Model and UI Safety

### The Problem

Python's `threading.Thread` does not integrate with Kivy's event system. Any code running on a background thread that touches a Kivy widget (Label, Button, Canvas, etc.) will cause a crash or unpredictable behavior, because Kivy's widget tree is not thread-safe.

### The Solution: Clock.schedule_once

The rule: **never touch a Kivy widget from a non-main thread.** Instead, use:

```python
Clock.schedule_once(lambda dt: widget.text = 'new value', 0)
```

`Clock.schedule_once(fn, 0)` schedules `fn` to run on the Kivy main thread on the next frame. The `0` delay means "as soon as possible on the main thread."

In the receiver thread, callbacks that update UI are wrapped:

```python
on_error=lambda msg: Clock.schedule_once(
    lambda dt: self._on_receiver_error(msg), 0
),
```

The `_pending_data` pattern (§8) avoids this entirely for the critical high-frequency data path: the receiver thread writes to a plain Python attribute (not a Kivy object), and the Kivy Clock tick reads from it on the main thread.

### TCP Connection Threading

`_start_stream()` spawns a short-lived daemon thread to call `device.start_server()`. This is necessary because `server_socket.accept()` blocks for up to 15 seconds. Running this on the Kivy main thread would freeze the entire UI. When the connection succeeds or fails, `Clock.schedule_once` fires `_on_connected` or `_on_connect_error` on the main thread.

**Key differences from desktop**: The desktop uses `QThread` + `pyqtSignal` for both the receiver thread and thread-safe UI updates. On Android, Qt is unavailable. The `threading.Thread` + `Clock.schedule_once` pattern is the Kivy equivalent and achieves the same thread-safety guarantee.

---

## 10. Signal Processing — Pre-computed Coefficients

### The Problem

The desktop app uses `scipy.signal.butter()` to compute Butterworth IIR filter coefficients at runtime. Scipy requires Fortran extensions that python-for-android cannot compile for ARM. Scipy cannot be included in the Android build.

### The Solution

Filter coefficients are computed **once** on a desktop machine using `scripts/compute_filter_coeffs.py`, then **hard-coded** as Python lists in `app/core/config.py`. At runtime on Android, the app reads these constants directly — no scipy import needed.

```python
# In config.py — generated by scripts/compute_filter_coeffs.py at 2000 Hz
BANDPASS_4_B = [0.05851270857137603, 0.0, -0.23405083428550413, ...]
BANDPASS_4_A = [1.0, -4.309368933349023, 7.9319108380991485,   ...]
```

**How to update**: If the device sample rate or filter cutoffs change, run `scripts/compute_filter_coeffs.py` on a machine with scipy installed and paste the output into `config.py`.

**Filters defined**:

| Constant | Type | Parameters | Used for |
|---|---|---|---|
| `BANDPASS_4_B/A` | Butterworth bandpass, order 4 | 20–450 Hz @ 2000 Hz | Live streaming, features |
| `BANDPASS_1_B/A` | Butterworth bandpass, order 1 | 20–450 Hz @ 2000 Hz | Short-data fallback |
| `LOWPASS_10_4_B/A` | Butterworth lowpass, order 4 | 10 Hz @ 2000 Hz | TKEO envelope smoothing |
| `NOTCH_60_B/A` | Butterworth bandstop, order 2 | 57–63 Hz @ 2000 Hz | 60 Hz power line removal |

The order-1 bandpass fallback activates when the packet has fewer than 27 samples (= 3 × max(len(b), len(a)) for order 4). A further fallback returns the data unfiltered if fewer than 9 samples arrive. These thresholds are set so `filtfilt`'s reflection padding never causes an index error.

**Why 20–450 Hz?** EMG signal energy is concentrated in this range. Below 20 Hz, motion artifact and low-frequency drift dominate. Above 450 Hz, EMG amplitude falls off sharply and approaches the Nyquist limit of 1000 Hz (at 2000 Hz sampling). [De Luca et al., 2010; Hermens et al., 2000]

**Why a 60 Hz notch?** North American power line frequency induces electromagnetic interference in unshielded electrode cables. The notch filter has Q=30, producing a −3 dB bandwidth of 2 Hz (59–61 Hz) — narrow enough to minimally affect EMG content.

---

## 11. Pure-numpy IIR Filter Implementation

`app/processing/iir_filter.py` implements the following functions purely in numpy, replacing scipy equivalents:

### `lfilter(b, a, x)` — Causal IIR filter

Implements the Direct Form II Transposed structure. For a filter of order M, the state vector `z` has M elements. Each input sample `x[i]` updates all state elements simultaneously using the precomputed `b` and `a` coefficients. Supports both 1-D signals and 2-D arrays of shape `(channels, samples)`.

This is mathematically equivalent to `scipy.signal.lfilter(b, a, x)`.

### `filtfilt(b, a, x)` — Zero-phase IIR filter

Applies `lfilter` in the forward direction, then in the reverse direction. The double application cancels phase distortion: each frequency component arrives at the output with zero time shift relative to the input.

Edge effects (transients at the signal boundaries) are reduced by **reflect-padding**: the signal is extended at both ends using its own reflection before filtering, then the padded portions are discarded afterward. Pad length = 3 × max(len(a), len(b)), matching scipy's default.

If the signal is too short for padding (≤ pad length), the function falls back to causal `lfilter` only.

**Why zero-phase filtering?** A causal filter (forward-only) introduces phase delay: each frequency shifts by a different time offset, which skews the apparent timing of EMG features. For post-hoc analyses (TKEO onset detection, fatigue, burst timing), timing accuracy matters. Zero-phase filtering eliminates this source of error. [Oppenheim & Schafer, 2009]

### `find_peaks(x, height=None, distance=None)` — Local maximum detection

Finds all strict local maxima satisfying the `height` criterion. If `distance` is specified, suppresses nearby peaks by greedily keeping the tallest peak within each `distance`-sample neighborhood. This matches the interface of `scipy.signal.find_peaks` for the subset of parameters used by the TKEO algorithm.

### `resample_signal(x, num)` — Linear-interpolation resampling

Resamples a 1-D signal from its original length to `num` samples using `numpy.interp`. This is simpler than scipy's FFT-based resampling but adequate for RMS-based bilateral symmetry analysis, where sub-sample accuracy is not required.

---

## 12. Calibration

Calibration collects a reference EMG amplitude for each channel during two postures — rest and maximum voluntary contraction (MVC) — then derives a detection threshold.

### Procedure

`CalibrationPopup` runs a two-phase timed protocol driven by a Kivy Clock interval:

1. **Rest phase** (`CALIBRATION_REST_DURATION = 3.0` s): Subject relaxes completely. The popup registers `_collect_sample` as a callback via `LiveDataScreen._register_calibration_callback`. On each incoming `raw` stage packet, the full `(channels, samples)` array is appended to `_rest_samples`.

2. **MVC phase** (`CALIBRATION_MVC_DURATION = 3.0` s): Subject contracts maximally. Same collection runs, appending to `_mvc_samples`.

3. **Computation**: `_compute_rms` concatenates all packets along the samples axis (`np.concatenate(sample_list, axis=1)`) and computes per-channel RMS:

```
baseline_rms[ch] = sqrt(mean(rest_data[ch] ** 2))
mvc_rms[ch]      = sqrt(mean(mvc_data[ch] ** 2))
threshold[ch]    = baseline_rms[ch] + 0.3 * (mvc_rms[ch] - baseline_rms[ch])
```

The threshold is placed at 30% of the range between rest and MVC, configured by `CALIBRATION_THRESHOLD_FRAC = 0.3`.

**Key differences from desktop**: The desktop uses a statistical threshold (`baseline_mean + 3·baseline_std`) and a 99th-percentile MVC estimate with spatial interpolation for bad channels. The mobile app uses a simpler proportional threshold and does not include spatial interpolation. The mobile calibration collects raw (not filtered) data, which includes motion artifact; the desktop collects filtered data.

### Contraction Indicator

After calibration, `LiveDataScreen._on_data()` checks channel 0's per-packet RMS against `threshold[0]` on every incoming `final` stage packet. The contraction label in the top bar turns green with "Contraction" if the threshold is exceeded, red with "No Contraction" otherwise.

---

## 13. Visualization Widgets

All three visualization widgets render to Kivy's `canvas` — the retained-mode 2D drawing API. Canvas instructions (`Color`, `Line`, `Rectangle`) are persistent objects that update the GPU display list when their properties change. This avoids the CPU overhead of recreating draw calls from scratch on every frame.

### EMGPlotWidget — Single-channel rolling plot

Displays a rolling window of one EMG channel (default: channel 0) over the last `PLOT_DISPLAY_SAMPLES = 4000` samples (~2 seconds at 2000 Hz).

**Buffer**: A 1-D numpy array of length 4000. On each `update(data)`, new samples are rolled in using `np.roll(buffer, -n)` followed by `buffer[-n:] = new_samples`. `render()` downsamples by `PLOT_DOWNSAMPLE = 4`, reducing the 4000-element buffer to 1000 screen points — enough for a smooth curve on a tablet display without over-rendering.

**Drawing**: The signal is linearly mapped to 80% of the widget height with 10% top/bottom padding. The `x` coordinates are computed as `np.arange(n) * (width / (n-1))`, spreading points uniformly across the widget. The resulting `(x, y)` pairs are interleaved into a flat list and assigned to `self._line.points` — Kivy's canvas then renders the polyline on the next frame.

**Why downsample for rendering?** At 2000 Hz with a 2-second buffer, there are 4000 data points. A 10-inch tablet at 1920px wide has 1920 physical pixels; rendering 4000 polyline vertices (many off-screen or sub-pixel) wastes GPU bandwidth. Downsampling to 1000 points still provides sub-pixel resolution at the display density without perceptible quality loss. [Tuan et al. generally discuss display rendering limits]

### MultiTrackPlotWidget — Stacked N-track plot

Vertically stacks N independent rolling plots in a single widget. Each track has its own 4000-sample buffer and color from `CFG.MULTI_TRACK_COLORS`. All tracks share the widget's width; each track gets `height / N` pixels of vertical space.

**Pre-allocation**: All `N` `Color` and `Line` canvas instructions are created in `__init__`. During `render()`, only the `.points` and `.r/g/b/a` properties are updated — no new Python objects are created. This is critical on Android where garbage collection pauses can cause visible frame drops.

### HeatmapWidget — 8×8 activation grid

Displays 64 colored rectangles arranged in an 8×8 grid. Each cell's color is linearly interpolated between `HEATMAP_COLD_RGB = (0.12, 0.12, 0.12)` (dark gray, inactive) and `HEATMAP_HOT_RGB = (0.0, 0.90, 0.40)` (bright green, fully active) based on the normalized RMS value of that channel.

**Pre-allocation**: 64 `(Color, Rectangle)` pairs are created once in `__init__`. `update(normalized_rms)` only changes `Color.r/g/b/a` properties. `_update_layout()` (called on resize) recomputes cell positions and sizes.

**Channel-to-grid mapping**: `channel_idx = col * 8 + (7 - row)`, placing channel 0 at bottom-left in column-major order. Row 0 is the topmost visual row (grid coordinates), row 7 the bottom.

**Key differences from desktop**: The desktop uses pyqtgraph's `ImageItem` with a viridis colormap. The mobile uses Kivy canvas rectangles with a custom cold→hot linear interpolation. The desktop shows per-channel numeric labels on the grid; the mobile does not (screen space is at a premium).

---

## 14. HD-sEMG View Modes and Aggregation

The live plot tab cycles through four view modes, selected by a "View:" button:

| Mode | Tracks | Aggregation |
|---|---|---|
| Single Ch0 | 1 | Raw channel 0 data |
| Rows (8) | 8 | Mean across all 8 columns for each row |
| Cols (8) | 8 | Mean across all 8 rows for each column |
| Clusters (16) | 16 | Mean of 2×2 electrode sub-blocks |

### Row aggregation

For each row `r` (0–7, bottom to top), the 8 channel indices are:
```python
ch_indices = [col * 8 + (7 - row) for col in range(8)]
```
The 8-element signals are averaged, producing one representative waveform per anatomical row of the electrode grid.

### Column aggregation

For each column `c` (0–7, left to right):
```python
ch_indices = [col * 8 + r for r in range(8)]
```

### Cluster aggregation

The 8×8 grid is divided into 16 non-overlapping 2×2 sub-blocks (a 4×4 arrangement of 2×2 clusters). Each sub-block's 4 channels are averaged. This reduces 64 channels to 16, preserving coarse spatial structure while remaining displayable on a phone screen.

**Rationale**: Displaying all 64 channels simultaneously on a mobile screen is illegible. Aggregation provides physiologically meaningful spatial groupings: rows correspond to muscle fiber orientation in some muscles; columns span the muscle belly transversely; 2×2 clusters capture regional activation patterns. The user can switch between modes to explore different spatial perspectives of the same data.

---

## 15. Recording

`RecordingManager` accumulates incoming `raw` stage data (not filtered, preserving the original ADC values) in memory and writes a timestamped CSV on stop.

**Why raw stage?** Post-hoc analysis should always start from unmodified data. Recording the filtered signal would irreversibly bake in filter parameters, preventing future reanalysis with different settings.

**CSV format**: One row per sample (not per packet), columns: `Timestamp, Channel_1, Channel_2, ..., Channel_72`. The timestamp is wall-clock time in seconds since recording start (`time.time() - recording_start_time`). All 72 channels (including auxiliary) are saved.

**Why per-sample rows?** Both the mobile and desktop apps record per-sample rows, preserving the full 2000 Hz temporal resolution needed for feature extraction.

**Save in background**: CSV writing is done in a daemon thread (`threading.Thread(target=save).start()`) to prevent the Kivy UI from freezing during the file I/O. When done, `Clock.schedule_once` fires `_on_save_done` on the main thread to restore button state.

**File location**: `get_recordings_dir()` → `get_data_dir()/'recordings/'` → `/sdcard/Documents/OTB_EMG/recordings/` on Android (see §16).

---

## 16. File Storage and Android Permissions

### Storage Path

On Android (API 30+), the public external storage path `/sdcard/Documents/OTB_EMG/` is used instead of the app's private data directory (`app.user_data_dir`). The difference matters:

- **Private** (`app.user_data_dir`): Only accessible via `adb pull`. Deleted when the app is uninstalled. Not visible in any file manager.
- **Public** (`/sdcard/Documents/OTB_EMG/`): Visible in any file manager app (Files, Solid Explorer, etc.). Accessible via USB file transfer without `adb`. Persists after app uninstall.

For clinical data collection, the public path is essential: researchers need to transfer recordings to a computer via USB without installing Android Debug Bridge.

### MANAGE_EXTERNAL_STORAGE Permission

Writing to `/sdcard/Documents/` on Android 11+ (API 30+) requires `MANAGE_EXTERNAL_STORAGE` — the "All files access" special permission, not granted automatically at install time. The app prompts the user on first launch via `_show_storage_permission_dialog()`, which opens a popup with a link to the system settings screen where this permission can be granted.

This permission is declared in `buildozer.spec`:
```
android.permissions = INTERNET,MANAGE_EXTERNAL_STORAGE
```

`INTERNET` is required for the TCP socket connection to the device.

If the permission is denied or not yet granted, `paths.py` falls back to `app.user_data_dir` (private storage), and recordings remain accessible but not via USB file transfer.

### File Chooser in Analysis Mode

Android's standard `FileChooserListView` (available in Kivy) proved unreliable for targeting specific directories. Instead, `DataAnalysisScreen._show_file_chooser()` calls `os.listdir(get_recordings_dir())` directly and builds a scrollable list of `Button` widgets. Files are sorted by modification time (newest first) so the most recent recording is at the top.

---

## 17. Data Analysis Mode

`DataAnalysisScreen` supports loading one or two CSV recording files and running six feature analyses. It has no live connection to the device.

### File Loading

Loading is done in a daemon thread to avoid blocking the UI. `_load_csv()` reads the CSV with Python's `csv.reader`, converts all rows to floats, extracts column 0 as timestamps and columns 1+ as channel data (transposed to `(channels, samples)`).

**Sample rate estimation**: `_estimated_fs(timestamps)` computes `1 / median(diff(timestamps))` from the monotonically increasing timestamp differences. This is robust to occasional duplicate or missing timestamps.

### Analysis Runners

Each analysis runs in a daemon thread (to avoid blocking the UI during computation), then reports results as text via `Clock.schedule_once(lambda dt: self._set_results(text), 0)`. No plots are generated in the analysis screen — all results are numeric text, keeping the implementation simple on a constrained display.

**Bilateral symmetry** is the only analysis requiring two files (File 1 and File 2). All other analyses use File 1, channel 0 only.

**HD-sEMG-specific analyses** (Centroid Shift, Spatial Non-Uniformity) require exactly 64 channels. If the loaded file has fewer, a clear error message is shown.

---

## 18. Feature Extraction Algorithms

The mobile app implements all six feature analyses in `app/processing/features.py`. All use pre-computed filter coefficients from `config.py` and the pure-numpy IIR implementation from `iir_filter.py`. The first four analyses are identical in algorithm to the desktop; the last two are mobile-only additions.

### Common Timestamp Preprocessing (`_preprocess_timestamps`)

All analyses apply the same preprocessing to timestamps before any filtering:

1. Remove samples where timestamp or signal is NaN
2. If all timestamps are duplicated (CSV was recorded at packet resolution — one timestamp per 125-sample packet), linearly interpolate to assign a unique timestamp to each sample
3. Discard non-monotonically increasing timestamps
4. Estimate sample rate: `fs = 1 / median(diff(cleaned_ts))`

### 18.1 TKEO Activation Timing

The **Teager-Kaiser Energy Operator (TKEO)** detects muscle activation onset. For a discrete signal x[n]:

```
Ψ(x[n]) = x[n]² − x[n−1] · x[n+1]
```

The TKEO is sensitive to changes in both amplitude and instantaneous frequency, making it more reactive to EMG onset than simple amplitude thresholding [Kaiser, 1990; Solnik et al., 2010].

**Pipeline**:
1. Bandpass filter: 20–450 Hz (pre-computed coefficients, zero-phase)
2. Compute TKEO point-by-point
3. Rectify (`abs`)
4. Smooth: 10 Hz lowpass (pre-computed LOWPASS_10_4 coefficients, zero-phase)
5. Baseline: mean and std of first 0.5 s of smoothed envelope
6. Detection threshold: `max(baseline_mean + 8·baseline_std, max_envelope / 4)`
7. Find peaks above threshold, minimum separation 0.5 s (`iir_filter.find_peaks`)
8. Backtrack from each peak to find true onset: walk backward until envelope drops below `baseline_mean + 3·baseline_std`

**Parameter rationale**:
- `k_threshold = 8`: High multiplier reduces false positives from noise [Bonato et al., 1998]
- `backtrack_k = 3`: Lower threshold finds the earlier onset crossing for precise timing
- `min_peak_distance = 0.5 s`: Prevents detecting the same burst twice

### 18.2 Burst Duration

Uses the same TKEO pipeline but detects threshold crossings (`onset_threshold = baseline_mean + 3·baseline_std`) to find both burst onset and offset. Bursts shorter than 50 ms or whose peak TKEO value does not exceed the detection threshold are discarded.

The 50 ms minimum duration prevents counting noise transients; the minimum physiologically meaningful voluntary burst is typically ≥100 ms [De Luca, 1997].

### 18.3 Bilateral Symmetry Index

Compares muscle activation amplitude between two channels (typically left and right limb) using the Robinson Symmetry Index [Robinson et al., 1987]:

```
SI = (RMS₁ − RMS₂) / (RMS₁ + RMS₂)
```

Range: [−1, +1]. Zero = symmetric. Positive = signal 1 dominant.

Computed in a sliding window (250 ms window, 50 ms step). Both signals are first trimmed to their overlapping duration and resampled to the lower of the two sample rates via `iir_filter.resample_signal` (linear interpolation).

### 18.4 Fatigue Detection

Two complementary indicators, computed in sliding windows (500 ms window, 100 ms step):

**RMS increase** (`threshold = 31.7%`): During sustained contraction, the central nervous system recruits additional motor units as existing ones fatigue, increasing total EMG amplitude [De Luca, 1984]. Fatigue is flagged when RMS exceeds baseline by 31.7% for ≥3 consecutive windows (300 ms sustained).

**Median frequency (MF) decline** (`threshold = −0.89 Hz/s`): Accumulation of metabolic byproducts reduces muscle fiber membrane conduction velocity, compressing the EMG power spectrum toward lower frequencies [Lindstrom et al., 1977; Merletti & Roy, 1996]. MF is computed via Hamming-windowed FFT. Fatigue is flagged when a sliding 10-window linear regression of MF values yields a slope ≤ −0.89 Hz/s.

The 10-window regression is more robust than a point-to-point derivative because it requires a sustained declining trend rather than a single negative step, which reduces false positives from FFT transients at burst onset.

---

## 19. HD-sEMG Spatial Analyses

These two analyses are unique to the mobile app and require all 64 HD-sEMG channels. They quantify how activation is distributed across the electrode array over time.

### 19.1 Activation Centroid Shift

Tracks the spatial center-of-mass of muscle activation over time. In each sliding window, each channel's RMS is computed. The centroid is the weighted mean of electrode positions:

```
centroid_x = Σ(col_position[ch] · RMS[ch]) / Σ(RMS[ch])
centroid_y = Σ(row_position[ch] · RMS[ch]) / Σ(RMS[ch])
```

where `col_position[ch] = ch // 8` and `row_position[ch] = 7 - (ch % 8)`, placing channel 0 at `(col=0, row=7)` (bottom-left).

**Interpretation**: A shift in the centroid over time indicates that the spatial distribution of muscle activation is changing — a known indicator of motor unit substitution during fatigue, where fatigued motor units are replaced by fresh ones in different locations [Farina et al., 2002].

Reports:
- Initial centroid position (in electrode-units, 0–7)
- Total displacement from initial centroid to final position
- Mean drift rate (electrode-units per second)

### 19.2 Spatial Non-Uniformity

Quantifies how unevenly activation is distributed across the 64-electrode grid over time. Three metrics are computed in each sliding window:

**Coefficient of Variation (CV)**: `std(rms) / mean(rms)` across all active channels. Higher CV = more spatially uneven activation.

**Shannon Entropy** of the normalized RMS distribution:
```
H = -Σ(p[ch] · log₂(p[ch]))
```
where `p[ch] = rms[ch] / Σ(rms)`. Maximum entropy (most uniform distribution) = log₂(64) = 6.0 bits. Lower entropy = more concentrated, less uniform activation.

**Activation Fraction**: The proportion of channels exceeding a threshold (either the calibrated per-channel threshold, or the 25th percentile of RMS values across channels if not calibrated). Represents what fraction of the electrode array is meaningfully active.

**Interpretation**: Increasing spatial uniformity (entropy rising, CV falling) over a sustained contraction suggests motor unit substitution — spatial redistribution of the neural drive as fatigue progresses [Farina et al., 2002]. Decreasing activation fraction with sustained effort may indicate muscle compartment fatigue.

**Reference**: Shannon entropy applied to motor unit population distributions is discussed in Farina et al. (2002).

---

## 20. Dependency Rationale and What Was Removed

| Library | Desktop | Mobile | Reason for change |
|---|---|---|---|
| PyQt5 | Yes | No | Qt does not target Android |
| pyqtgraph | Yes | No | Depends on PyQt5/OpenGL; no p4a recipe |
| scipy | Yes | No | Requires Fortran compiler (LAPACK/BLAS); no p4a recipe |
| matplotlib | No | No | No p4a recipe; would be very slow on mobile |
| Kivy | No | Yes | Designed for Android; has a p4a recipe |
| numpy | Yes | Yes | Has a p4a recipe; all math uses numpy directly |

### scipy Replacement

| scipy function | Mobile replacement | Location |
|---|---|---|
| `scipy.signal.butter()` | Pre-computed coefficients in `config.py` | `app/core/config.py` |
| `scipy.signal.filtfilt()` | Pure-numpy `filtfilt()` (Direct Form II) | `app/processing/iir_filter.py` |
| `scipy.signal.lfilter()` | Pure-numpy `lfilter()` | `app/processing/iir_filter.py` |
| `scipy.signal.find_peaks()` | Pure-numpy `find_peaks()` | `app/processing/iir_filter.py` |
| `scipy.signal.resample()` | Linear-interpolation `resample_signal()` | `app/processing/iir_filter.py` |
| `scipy.fft.rfft()` | `numpy.fft.rfft()` | `app/processing/features.py` |
| `scipy.fft.rfftfreq()` | `numpy.fft.rfftfreq()` | `app/processing/features.py` |

### matplotlib Replacement

The desktop uses pyqtgraph for all plots. The mobile uses custom Kivy canvas widgets (`EMGPlotWidget`, `MultiTrackPlotWidget`, `HeatmapWidget`). These are lower-level than a full charting library but are sufficient for the rolling time-series and heatmap displays needed here, and impose zero additional dependencies.

---

## 21. Glossary

| Term | Definition |
|---|---|
| ADC | Analog-to-Digital Converter. Converts voltage to integer. 16-bit: range −32768 to +32767. |
| APK | Android Package. The distributable file format for Android apps. |
| Buildozer | Command-line tool that builds Android APKs from Kivy Python apps using python-for-android. |
| Butterworth filter | Filter with maximally flat (ripple-free) passband response. |
| Canvas | Kivy's retained-mode 2D drawing API. Instructions (`Color`, `Line`, `Rectangle`) persist and are redrawn each frame. |
| `Clock.schedule_once` | Kivy function to run a callback on the main (UI) thread at the next frame. Used to bridge background threads and Kivy widgets. |
| Direct Form II Transposed | An IIR filter implementation structure that minimizes numerical precision issues by using a transposed signal flow graph. |
| filtfilt | Zero-phase forward+backward IIR filtering. Non-causal; requires the full signal. |
| HD-sEMG | High-density surface EMG. 8×8 grid of 64 electrodes capturing spatial muscle activation. |
| Motor unit substitution | Replacement of fatigued motor units by fresh ones in different locations during sustained contraction. |
| MVC | Maximum Voluntary Contraction. The maximum force a subject can produce; used as normalization reference. |
| NDK | Android Native Development Kit. Used to compile C/Fortran extensions for ARM. |
| p4a | python-for-android. Cross-compiles Python and dependencies to ARM binary code. |
| Packet | One chunk of TCP data from the device. At 2000 Hz, 72 channels: 18000 bytes, 125 samples, 16 packets/sec. |
| Pending-data pattern | `_on_data()` stores latest data to `_pending_data`; 60fps tick reads and clears it. Prevents stacked redraws. |
| `ScreenManager` | Kivy container for multiple `Screen` objects; shows one at a time with transitions. |
| TKEO | Teager-Kaiser Energy Operator: Ψ(x[n]) = x[n]² − x[n−1]·x[n+1]. Amplifies energy changes for onset detection. |
| Zero-phase filter | Filter with no phase distortion; achieved via filtfilt. All frequencies pass through with zero time shift. |

---

## 22. References

- Bonato, P., D'Alessio, T., & Knaflitz, M. (1998). A statistical method for the measurement of muscle activation intervals from surface myoelectric signal during gait. *IEEE Transactions on Biomedical Engineering*, 45(3), 287–299.
- De Luca, C.J. (1984). Myoelectrical manifestations of localized muscular fatigue in humans. *Critical Reviews in Biomedical Engineering*, 11(4), 251–279.
- De Luca, C.J. (1997). The use of surface electromyography in biomechanics. *Journal of Applied Biomechanics*, 13(2), 135–163.
- De Luca, C.J., Gilmore, L.D., Kuznetsov, M., & Roy, S.H. (2010). Filtering the surface EMG signal: Movement artifact and baseline noise contamination. *Journal of Biomechanics*, 43(8), 1573–1579.
- Farina, D., Cescon, C., & Merletti, R. (2002). Influence of anatomical, physical, and detection-system parameters on surface EMG. *Biological Cybernetics*, 86(6), 445–456.
- Hermens, H.J., Freriks, B., Disselhorst-Klug, C., & Rau, G. (2000). Development of recommendations for SENIAM surface electromyography sensors and sensor placement procedures. *Journal of Electromyography and Kinesiology*, 10(5), 361–374.
- Kaiser, J.F. (1990). On a simple algorithm to calculate the 'energy' of a signal. *Proceedings of ICASSP*, 381–384.
- Lindstrom, L., Kadefors, R., & Petersen, I. (1977). An electromyographic index for localized muscle fatigue. *Journal of Applied Physiology*, 43(4), 750–754.
- Merletti, R., & Roy, S.H. (1996). Myoelectric and mechanical manifestations of muscle fatigue in voluntary contractions. *Journal of Orthopaedic and Sports Physical Therapy*, 24(6), 342–353.
- Oppenheim, A.V., & Schafer, R.W. (2009). *Discrete-Time Signal Processing* (3rd ed.). Pearson. [Reference for Direct Form II Transposed structure and zero-phase filtering.]
- Robinson, R.O., Herzog, W., & Nigg, B.M. (1987). Use of force platform variables to quantify the effects of chiropractic manipulation on gait symmetry. *Journal of Manipulative and Physiological Therapeutics*, 10(4), 172–176.
- Solnik, S., Rider, P., Steinweg, K., DeVita, P., & Hortobágyi, T. (2010). Teager-Kaiser energy operator signal conditioning improves EMG onset detection. *European Journal of Applied Physiology*, 110(3), 489–498.
