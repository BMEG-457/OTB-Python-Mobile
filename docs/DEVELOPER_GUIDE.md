# OTB EMG Mobile App — Developer Guide

Technical reference for anyone adding features, fixing bugs, or porting the app further. Assumes familiarity with Python, Android basics, and signal processing concepts.

---

## 1. Project Structure

```
OTB-Python-Mobile/
├── main.py                     App entry point; OTBApp(kivy.App)
├── buildozer.spec              Android build config (Buildozer + python-for-android)
├── app/
│   ├── core/
│   │   ├── config.py           Module-level constants loaded from config.json
│   │   ├── config.json         All tuneable params + pre-computed filter coefficients
│   │   ├── device.py           SessantaquattroPlus: TCP server, command encoding, battery
│   │   └── paths.py            get_data_dir() / get_recordings_dir() — Android-aware
│   ├── data/
│   │   └── data_receiver.py    DataReceiverThread: recv loop, pipeline dispatch
│   ├── managers/
│   │   ├── recording_manager.py    RecordingManager: accumulate + async CSV write
│   │   └── streaming_controller.py StreamingController: thread flag + Clock schedule
│   ├── processing/
│   │   ├── iir_filter.py       lfilter, filtfilt, find_peaks, resample_signal, StatefulIIRFilter
│   │   ├── filters.py          butter_bandpass, notch, rectify; init/reset live filters
│   │   ├── features.py         TKEO, burst, bilateral, fatigue, centroid, entropy
│   │   ├── pipeline.py         Named pipeline registry
│   │   └── transforms.py       FFT helpers
│   └── ui/
│       ├── screens/
│       │   ├── selection_screen.py       Entry: Live Data | Data Analysis buttons
│       │   ├── live_data_screen.py       Live streaming screen (746 lines)
│       │   ├── data_analysis_screen.py   Offline analysis screen (857 lines)
│       │   └── analysis_plot_screen.py   Analysis result plot screen
│       └── widgets/
│           ├── emg_plot_widget.py        Single-channel Kivy canvas plot
│           ├── multi_track_plot.py       N-track stacked canvas plot
│           ├── heatmap_widget.py         8×8 electrode heatmap
│           └── calibration_popup.py      Two-phase timed calibration popup
├── scripts/
│   └── compute_filter_coeffs.py   Offline scipy-based coefficient generator
└── tests/
    ├── test_networking.py    TCP smoke test (no device needed)
    └── test_processing.py    Filter pipeline smoke test
```

---

## 2. Entry Point (`main.py`)

`OTBApp.build()` creates one `SessantaquattroPlus` instance and a `ScreenManager` with four screens. The device object is passed into `LiveDataScreen` at construction; all other screens are device-independent.

```python
class OTBApp(App):
    def build(self):
        emulator = EMULATOR_BUILD or os.getenv("SESSANTAQUATTRO_EMULATOR") == "1"
        self.device = SessantaquattroPlus(emulator_mode=emulator)
        sm = ScreenManager()
        sm.add_widget(SelectionScreen(name='selection'))
        sm.add_widget(LiveDataScreen(name='live_data', device=self.device))
        sm.add_widget(DataAnalysisScreen(name='data_analysis'))
        sm.add_widget(AnalysisPlotScreen(name='analysis_plot'))
        return sm

    def on_start(self):
        # Android only: request WRITE_EXTERNAL_STORAGE at runtime
        if _is_android():
            Clock.schedule_once(lambda dt: self._check_storage_permission(), 0.5)

    def on_stop(self):
        self.device.stop_server()
```

**Emulator mode** is active when `config.json ["build"]["emulator_build"]` is `true` or when the environment variable `SESSANTAQUATTRO_EMULATOR=1` is set. In emulator mode the network IP check is skipped.

---

## 3. Configuration System

`app/core/config.py` reads `config.json` at import time and exposes every value as a `SCREAMING_SNAKE_CASE` module constant. Source code imports `from app.core import config as CFG` and references `CFG.DEVICE_SAMPLE_RATE`, `CFG.BANDPASS_4_B`, etc.

**Never hardcode tuneable values in source files.** Always add them to `config.json` and reference via `CFG`.

Key config sections:

| Section | Key constants |
|---|---|
| `device` | `DEVICE_SAMPLE_RATE` (2000), `DEVICE_CHANNELS` (72), `DEVICE_PORT` (45454), `DEVICE_CONNECT_TIMEOUT` (15 s) |
| `filter` | `BANDPASS_LOW_HZ` (20), `BANDPASS_HIGH_HZ` (450), `NOTCH_FREQ_HZ` (60), `NOTCH_QUALITY` (30) |
| `filter_coefficients` | `BANDPASS_4_B/A`, `BANDPASS_1_B/A`, `LOWPASS_10_4_B/A`, `NOTCH_60_B/A` |
| `calibration` | `CALIBRATION_REST_DURATION` (3.0 s), `CALIBRATION_MVC_DURATION` (3.0 s), `CALIBRATION_THRESHOLD_FRAC` (0.3) |
| `features` | `FEATURE_K_THRESHOLD` (8.0), `FEATURE_BACKTRACK_K` (3.0), `FEATURE_FATIGUE_RMS_THRESHOLD` (0.317), etc. |
| `ui` | `RENDER_FPS` (30), `HEATMAP_BUFFER_SAMPLES` (100), `BATTERY_POLL_INTERVAL` (30 s) |
| `recording` | `RECORDING_MAX_SAMPLES` (1,000,000) |

---

## 4. Device Communication Protocol

### Network topology

The phone acts as a **TCP server**; the Sessantaquattro+ device is the **client**. This is the inverse of the typical client-server pattern and matches the OTBioelettronica protocol specification.

```
Phone (server, 0.0.0.0:45454)
  ← device connects →
Phone sends 2-byte command
  ← device streams data packets →
```

### Network check

Before binding the server socket, `device.is_connected_to_device_network()` uses a UDP trick to discover the phone's local IP without actually sending data:

```python
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))          # no actual packet sent
local_ip = s.getsockname()[0]        # reveals the routed interface IP
```

The check passes if `local_ip` starts with `"192.168.1"`. In emulator mode the check is skipped.

### Command encoding (16-bit big-endian)

`device.create_command()` builds a 16-bit integer by OR-ing bitfield values:

| Field | Bits | Default | Meaning |
|---|---|---|---|
| GO | 0 | 1 | Start acquisition |
| REC | 1 | 0 | Internal device recording |
| TRIG | 2 | 0 | External trigger |
| EXTEN | 4 | 0 | Extension module |
| HPF | 6 | 1 | Hardware high-pass filter enabled |
| HRES | 7 | 0 | High resolution mode |
| MODE | 8–10 | 0 | 0 = monopolar, 1 = bipolar |
| NCH | 11–12 | 3 | Channel count selector (3 = 72 ch in monopolar) |
| FSAMP | 13–15 | 2 | Sample rate selector (2 = 2000 Hz in MODE 0) |

The encoded command is sent as 2 bytes, big-endian, signed: `command.to_bytes(2, byteorder='big', signed=True)`.

### Data packets

Each packet contains 125 samples across 72 channels:

```
Packet size = 72 channels × 2 bytes/sample × 125 samples = 18,000 bytes
Packet rate = 2000 Hz / 125 samples = 16 packets/second
```

Samples are big-endian signed 16-bit integers (ADC output). `DataReceiverThread` unpacks and reshapes each packet to `(72, 125)` using:

```python
raw = np.frombuffer(buf, dtype='>i2').reshape(72, 125).astype(np.float32)
```

### Battery query

Battery level is read via HTTP GET to `http://192.168.1.1/`. The response HTML is parsed with a regex for `Battery Level: </td><td>NN%`. This is independent of the TCP stream and runs in a daemon thread every 30 seconds.

---

## 5. Live Data Pipeline

### Data flow

```
Sessantaquattro+ (TCP)
  → DataReceiverThread.run()  [daemon threading.Thread]
      recv loop accumulates bytes until expected_bytes (18000) available
      struct.unpack big-endian signed 16-bit → reshape (samples, nch).T → (72, 125) float32

      on_stage('raw', raw)          — always emitted (recording needs it even when paused)

      if self.running:              — only when StreamingController.start_streaming() is active
        Pipeline('filtered').run(raw)   → bandpass only   → on_stage('filtered', ...)
        Pipeline('rectified').run(...)  → abs              → on_stage('rectified', ...)
        Pipeline('final').run(raw)      → bandpass + notch + rectify  → on_stage('final', ...)

      on_stage callbacks:
        → recording_manager.on_data_for_recording(stage, data)
        → calibration_extra_callback(stage, data)   [during calibration only]
        → live_data_screen._on_data(stage, data)    [stores to _pending_data on 'final']

      socket.timeout (5 s) during pause: continue loop — keeps thread alive

Kivy Clock.schedule_interval(_ui_tick, 1/30)   [30 fps]
  → LiveDataScreen._ui_tick(dt)
      reads self._pending_data, clears it
      → _render_plot_panel(data)   or   _render_heatmap_panel(data)
```

Note: `Pipeline('final')` runs independently from `raw`, not chained from `Pipeline('rectified')`. Each pipeline is a separate stage sequence.

### Pipeline registry (`pipeline.py`)

```python
get_pipeline('filtered').add_stage(lambda data: filters._live_bp_filtered(data))
get_pipeline('rectified').add_stage(filters.rectify)
get_pipeline('final').add_stage(lambda data: filters._live_bp_final(data))
get_pipeline('final').add_stage(lambda data: filters._live_notch_final(data))
get_pipeline('final').add_stage(filters.rectify)
```

Each pipeline stage receives and returns `np.ndarray` of shape `(n_channels, n_samples)`. Stages are called in order; the output of one feeds the next.

### Pending-data pattern

`_on_data()` runs on the receiver thread. Writing to `self._pending_data` (assignment is atomic in CPython) is the only cross-thread operation. `_ui_tick()` reads and nulls it on the Kivy main thread. This decouples 16 Hz data arrival from 30 fps rendering without locks or queues.

---

## 6. Threading Model

**Rule: never touch a Kivy widget from a non-main thread.**

| Thread | What it does |
|---|---|
| Main (Kivy) | UI construction, `_ui_tick`, all widget updates |
| Receiver (`DataReceiverThread`) | `socket.recv()` loop, pipeline dispatch, writes `_pending_data` — defined in `app/data/data_receiver.py` |
| Connection daemon | `device.start_server()` + `send_command()`; marshals result back via `Clock.schedule_once` |
| Battery daemon | `device.get_battery_level()` HTTP query |
| Save daemon | `recording_manager.save_recording_to_csv()` CSV write |
| Analysis daemon | Each feature analysis function in `data_analysis_screen.py` |

All background-to-UI results use:
```python
Clock.schedule_once(lambda dt: update_ui(result), 0)
```

The receiver thread is **never restarted**. `StreamingController` sets `receiver_thread.running = False` to pause data feeding (the thread blocks in `socket.recv()` but drops packets when `running` is False). A new `DataReceiverThread` is created each time the user presses Start Stream, but `threading.Thread` can only be started once — the old thread must have exited before a new one is created. In practice, once the socket closes the recv loop exits.

---

## 7. Signal Processing

### Filter coefficients

All coefficients are pre-computed offline at 2000 Hz using `scripts/compute_filter_coeffs.py` (which uses scipy) and stored in `config.json`. At runtime only NumPy is required.

| Config key | Filter spec | Used in |
|---|---|---|
| `BANDPASS_4_B/A` | Butterworth order 4, 20–450 Hz bandpass | Live pipeline; all post-session analyses |
| `BANDPASS_1_B/A` | Butterworth order 1, 20–450 Hz bandpass | Short-data fallback in `butter_bandpass` |
| `LOWPASS_10_4_B/A` | Butterworth order 4, 10 Hz lowpass | TKEO envelope smoothing |
| `NOTCH_60_B/A` | Butterworth order 2 notch, 60 Hz, Q=30 | Live pipeline power-line removal |

To regenerate after changing sample rate or cutoffs:
```bash
python scripts/compute_filter_coeffs.py --fs 4000
# paste the printed b/a arrays into config.json filter_coefficients section
```

### Pure-numpy IIR implementation (`iir_filter.py`)

`lfilter(b, a, x)` — Direct Form II Transposed, causal. Supports 1-D signals and `(channels, samples)` arrays by looping over channels.

`filtfilt(b, a, x)` — Zero-phase forward+backward filter with reflect padding of length `3 × max(len(a), len(b))`. Falls back to causal `lfilter` if the signal is shorter than the pad length.

`find_peaks(x, height, distance)` — Greedy local maximum detection: collects all strict local maxima above `height`, then iterates highest-first and suppresses neighbours within `distance` samples. Returns `(indices, {})` matching scipy's interface.

`resample_signal(x, num)` — Linear interpolation. Adequate for RMS-based analysis; less accurate than scipy's FFT-based resample for high-frequency content.

`StatefulIIRFilter` — Causal IIR filter that maintains state across packets. Used for live streaming (vectorized across channels; Python loop only over the 125 sample dimension per packet). Call `reset()` before a new streaming session to zero the filter state.

### Live filters (`filters.py`)

Three `StatefulIIRFilter` instances are created by `init_live_filters(n_channels)`:

- `_live_bp_filtered` — bandpass for the 'filtered' pipeline
- `_live_bp_final` — bandpass for the 'final' pipeline
- `_live_notch_final` — notch for the 'final' pipeline

Separate instances ensure the two bandpass pipelines do not share state. Call `filters.reset_live_filters()` at the start of each streaming session.

### Post-session filters (`features.py`)

Post-session analyses use `filtfilt` (zero-phase, non-causal). The same coefficient arrays are used, but applied in batch to entire recordings rather than sample-by-sample.

---

## 8. Calibration (`calibration_popup.py`)

The `CalibrationPopup` is a Kivy `Popup` that runs a two-phase protocol driven by `Clock.schedule_interval`:

1. **Rest phase** (3.0 s) — registers `_calibration_extra_callback` via `on_sample_connect`; collects raw stage packets into `_rest_samples`.
2. **MVC phase** (3.0 s) — same callback, collects into `_mvc_samples`.
3. **Computation:**
   ```
   rest_data  = concatenated rest packets (n_channels, n_rest_samples)
   mvc_data   = concatenated mvc packets  (n_channels, n_mvc_samples)
   baseline_rms = sqrt(mean(rest_data²))           shape (n_channels,)
   mvc_rms      = sqrt(mean(mvc_data²))            shape (n_channels,)
   threshold    = baseline_rms + 0.3 × (mvc_rms − baseline_rms)
   ```
4. Emits `on_complete(baseline_rms, threshold, mvc_rms)` to `LiveDataScreen`.

`LiveDataScreen._on_data()` feeds raw packets to the calibration callback directly on the receiver thread (no Clock call). The popup accumulates lists and concatenates at the end to avoid repeated array allocation.

---

## 9. Screen Interface Guide

All screens are `kivy.uix.screenmanager.Screen` subclasses added to a single `ScreenManager`. Navigation is done by setting `self.manager.current = 'screen_name'`.

### SelectionScreen

Minimal screen. Two buttons: "Live Data" → `'live_data'`; "Data Analysis" → `'data_analysis'`.

### LiveDataScreen

Layout (vertical `BoxLayout`):

| Region | Height fraction | Contents |
|---|---|---|
| Top bar | 0.10 | Back, Calibrate, Start Stream, Start Record, contraction label, battery label, status label |
| Tab bar | 0.07 | EMG Plot toggle, Heatmap toggle, Time cycle button, Ch: input, View cycle button |
| Content | 0.78 | FloatLayout with three overlapping panels: `plot_single`, `plot_multi`, `heatmap` |
| Bottom bar | 0.05 | Status/instruction label |

The three content panels are stacked in the FloatLayout; visibility is controlled by setting `widget.opacity = 0` or `1`. Only one is visible at a time.

**View modes** are defined in `_VIEW_MODES` (module-level list of `(label, n_tracks, agg_fn)` tuples). Cycling calls `_rebuild_multi_track()` when the track count changes, which creates a new `MultiTrackPlotWidget` and replaces the old one.

**Changing number of view modes:** add an entry to `_VIEW_MODES` and implement an aggregation function `fn(data) -> (n_tracks, samples)` where `data` is `(≥64, samples)`.

### DataAnalysisScreen

Layout:
- Top bar: Back, title
- File bar: Load File 1 button, File 1 status label, File 2 status label, Plot Data button
- Channel bar: Channel number input (1-based), Export button
- Analysis grid: six buttons (3 columns × 2 rows)
- Results: `ScrollView` containing a scrollable `Label`

There is no separate "Load File 2" button. File 2 loads automatically: pressing **Bilateral Symmetry** when no File 2 is loaded opens the file browser for slot 2. Once File 2 is loaded, the analysis runs immediately.

The file browser is a navigable directory popup (`_show_file_chooser`). It starts from the first accessible storage path (jnius external files dir → `/storage/emulated/0/Android/data/...` → `/sdcard/Documents` → Kivy `user_data_dir`) and shows folders and CSV files. Tap a folder to enter; tap a CSV to select and load.

The **Plot Data** button navigates to `AnalysisPlotScreen` passing the currently loaded data. It shows the raw signal as a static scrollable waveform — it is not a feature-analysis result view.

The **Export** button writes all analysis results that have been run in the current session to `<source_filename>_export.csv` in the same directory as the source file. The export includes metadata comment rows and columnar time-series data for each analysis.

All analyses operate on the channel selected in the Channel input. Centroid Shift and Spatial Uniformity use `data1[:64]` and ignore the channel input.

File loading runs in a daemon thread; `_ts1`, `_data1` (and `_ts2`, `_data2` for File 2) are set on completion via `Clock.schedule_once`. Analyses similarly run in daemon threads and post results via `Clock.schedule_once`.

**Adding a new analysis:**
1. Implement the function in `features.py`.
2. Add an entry to the `analyses` list in `DataAnalysisScreen._build_ui()`.
3. Write a `_run_<analysis>()` handler that runs the function in a daemon thread, stores the result in `_feature_store`, and posts result text.

### AnalysisPlotScreen

Displays a static EMG signal from a loaded recording. `DataAnalysisScreen._show_plot()` calls `plot_screen.set_data(data, timestamps, filename)` then sets `manager.current = 'analysis_plot'`. The screen provides a `StaticEMGPlotWidget` (Kivy canvas line rendering) with on-screen controls for channel selection, bandpass filter, notch filter, rectify, and envelope. It is a signal inspector, not a feature-analysis result viewer.

---

## 10. Visualization Widgets

All widgets use Kivy's `canvas` API directly — no matplotlib or pyqtgraph.

### EMGPlotWidget (`emg_plot_widget.py`)

Single-channel rolling waveform. Buffer is `display_samples` long (default 4000 = 2 s at 2000 Hz) implemented as a circular buffer with a write pointer (no `np.roll` allocation). On `render()`, the buffer is linearised, downsampled by `downsample` (default 4 → 1000 rendered points), scaled to a peak-hold y-axis range (expands to accommodate new extremes, never shrinks), and assigned to a single `canvas.Line` instruction. Call `reset_scale()` at stream start to clear the peak-hold range.

### MultiTrackPlotWidget (`multi_track_plot.py`)

N independent rolling plots stacked vertically. Pre-allocates one `Color` + one `Line` canvas instruction per track at construction. `update_track(i, samples)` and `render()` update `.points` and `Color.rgba` without creating new canvas objects — critical for avoiding Android garbage collection pauses.

### HeatmapWidget (`heatmap_widget.py`)

8×8 grid of 64 `(Color, Rectangle)` pairs. `update(normalized_rms)` takes a `(64,)` array with values in `[0, 1]` and linearly interpolates each channel's color between `HEATMAP_COLD_RGB = (0.12, 0.12, 0.12)` and `HEATMAP_HOT_RGB = (0.0, 0.90, 0.40)`.

Channel-to-grid mapping:
```python
channel_idx = col * 8 + (7 - row)   # col, row in 0..7; bottom-left = channel 0
```

### CalibrationPopup (`calibration_popup.py`)

Kivy `Popup` with a progress bar driven by `Clock.schedule_interval`. Two phases share the same timer logic; only the target sample list and prompt text change between phases.

---

## 11. Recording (`recording_manager.py`)

`RecordingManager` accumulates raw stage data as a Python list of `(timestamp, channel_data)` tuples, where `timestamp` is seconds elapsed since `recording_start_time` and `channel_data` is a `(64,)` float32 array (first `HDSEMG_CHANNELS` channels only — auxiliary channels excluded). When recording stops, `save_recording_to_csv()` writes a timestamped CSV in a daemon thread.

**CSV filename format:** `recording_YYYYMMDD_HHMMSS.csv`

**Overflow callback:** if the list length reaches `RECORDING_MAX_SAMPLES` (1,000,000 samples), `on_overflow()` is called. `LiveDataScreen` uses this to auto-stop recording and show a message.

---

## 12. File Paths (`paths.py`)

`get_recordings_dir()` uses a priority chain on Android:
1. `jnius` → `Context.getExternalFilesDir()` → `<sdcard>/Android/data/org.bmeg457.otbemgapp/files/OTB_EMG/recordings/`
2. Direct POSIX path: `/sdcard/Android/data/org.bmeg457.otbemgapp/files/OTB_EMG/recordings/`
3. Kivy `App.user_data_dir` private directory (last resort — not visible in file manager)

On desktop (non-Android): `~/OTB_EMG_Data/recordings/`

---

## 13. Testing

No automated test framework. Two standalone smoke tests:

```bash
python tests/test_networking.py    # TCP socket round-trip without hardware
python tests/test_processing.py    # filter pipeline shape + non-negativity checks
```

Run directly with `python`, not via pytest.

---

## 14. Adding a New Screen

1. Create `app/ui/screens/my_screen.py` with a class inheriting `kivy.uix.screenmanager.Screen`.
2. In `main.py`, import and add: `sm.add_widget(MyScreen(name='my_screen'))`.
3. Navigate to it with `self.manager.current = 'my_screen'`.
4. Add a "Back" button that sets `self.manager.current` to the appropriate previous screen.

---

## 15. Dependency Rationale

| Library | Runtime | Why |
|---|---|---|
| `kivy==2.3.0` | Yes | Cross-platform Python UI framework; only mature option for Python→APK |
| `numpy` | Yes | Array processing; no Fortran extensions → builds cleanly with p4a |
| `scipy` | No (offline only) | Required for `butter()` coefficient generation; has no p4a recipe with modern NDK |
| `matplotlib` | No | Has no p4a recipe; replaced by Kivy canvas widgets |
| `kivy_matplotlib_widget` | No | Removed with matplotlib |

---

## 16. Glossary

| Term | Definition |
|---|---|
| ADC | Analog-to-digital converter; converts muscle voltage to 16-bit integer |
| APK | Android application package |
| Buildozer | Build tool that invokes python-for-android (p4a) to create APKs |
| Canvas | Kivy's low-level drawing API; `Color`, `Line`, `Rectangle` instructions |
| Clock | Kivy's event scheduler; `Clock.schedule_once` and `schedule_interval` run on the main thread |
| HD-sEMG | High-density surface electromyography; an 8×8 grid of 64 surface electrodes |
| MVC | Maximum voluntary contraction; used as 100% activation reference |
| NDK | Android Native Development Kit; needed to cross-compile C extensions |
| p4a | python-for-android; cross-compiles Python + deps to ARM |
| Pipeline | Named ordered list of processing functions applied to data |
| TKEO | Teager-Kaiser Energy Operator; Ψ(x[n]) = x[n]² − x[n-1]·x[n+1] |
| StatefulIIRFilter | `iir_filter.py` class that maintains filter state across packets for live streaming |
| WSL2 | Windows Subsystem for Linux version 2; Linux kernel inside Windows |
