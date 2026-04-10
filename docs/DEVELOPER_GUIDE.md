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
│   │   └── data_receiver.py    DataReceiverThread: recv loop, pipeline dispatch, disconnect detection
│   ├── managers/
│   │   ├── recording_manager.py    RecordingManager: autosave, metadata sidecars, session history
│   │   ├── streaming_controller.py StreamingController: thread flag + Clock schedule
│   │   └── session_history.py      SessionHistoryManager: JSON persistence of session summaries
│   ├── processing/
│   │   ├── iir_filter.py       lfilter, filtfilt, find_peaks, resample_signal, StatefulIIRFilter
│   │   ├── filters.py          butter_bandpass, notch, rectify; init/reset live filters
│   │   ├── features.py         TKEO, burst, bilateral, fatigue, centroid, entropy
│   │   ├── pipeline.py         Named pipeline registry
│   │   ├── transforms.py       FFT helpers
│   │   └── live_metrics.py     Real-time rolling RMS, median frequency, fatigue flags
│   └── ui/
│       ├── screens/
│       │   ├── selection_screen.py       Entry: Live Data | Data Analysis | Session History
│       │   ├── live_data_screen.py       Live streaming screen (basic/advanced modes)
│       │   ├── data_analysis_screen.py   Offline analysis screen
│       │   ├── analysis_plot_screen.py   Analysis result plot screen
│       │   └── longitudinal_screen.py    Session history viewer with trend charts
│       └── widgets/
│           ├── emg_plot_widget.py        Single-channel Kivy canvas plot
│           ├── multi_track_plot.py       N-track stacked canvas plot
│           ├── heatmap_widget.py         8×8 electrode heatmap (gridlines, labels, highlight)
│           ├── calibration_popup.py      Three-phase timed calibration popup
│           ├── crosstalk_popup.py        Crosstalk verification popup
│           ├── session_metadata_popup.py Session metadata entry form
│           ├── seniam_guide_popup.py     SENIAM electrode placement guide
│           └── trend_plot_widget.py      Canvas-based line+marker trend chart
├── scripts/
│   └── compute_filter_coeffs.py   Offline scipy-based coefficient generator
└── tests/
    ├── test_iir_filter.py          Pure-numpy IIR filter implementations
    ├── test_filters.py             butter_bandpass, notch, rectify, live filters
    ├── test_features.py            Basic EMG features and all post-session analyses
    ├── test_pipeline.py            ProcessingPipeline and registry
    ├── test_device.py              Command encoding, channel/frequency lookup, network check
    ├── test_recording_manager.py   Recording state, data capture, overflow, CSV export
    ├── test_data_receiver.py       Packet parsing, stage dispatch, socket lifecycle
    ├── test_networking.py          TCP server/client handshake (no device needed)
    ├── test_processing.py          End-to-end filter + feature pipeline (no device needed)
    ├── test_autosave.py            Autosave write-through and crash recovery
    ├── test_calibration_verification.py  3-phase calibration and concentration check
    ├── test_crosstalk.py           Crosstalk threshold evaluation
    ├── test_disconnect_detection.py Socket timeout and disconnect warning
    └── test_latency_monitor.py     Rolling latency window and threshold
```

---

## 2. Entry Point (`main.py`)

`OTBApp.build()` creates one `SessantaquattroPlus` instance and a `ScreenManager` with five screens. The device object is passed into `LiveDataScreen` at construction; all other screens are device-independent.

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
        sm.add_widget(LongitudinalScreen(name='longitudinal'))
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
| `adapter` | `ADAPTER_TYPE` (`"ad1x64sp"` or `"ad2x32sp"`), `ADAPTER_CHANNEL_MAP` (64-element list or `None`), `DEAD_CHANNELS` (frozenset of always-zero logical indices) |
| `filter` | `BANDPASS_LOW_HZ` (20), `BANDPASS_HIGH_HZ` (450), `NOTCH_FREQ_HZ` (60), `NOTCH_QUALITY` (30) |
| `filter_coefficients` | `BANDPASS_4_B/A`, `BANDPASS_1_B/A`, `LOWPASS_10_4_B/A`, `NOTCH_60_B/A` |
| `calibration` | `CALIBRATION_REST_DURATION` (3.0 s), `CALIBRATION_MVC_DURATION` (3.0 s), `CALIBRATION_THRESHOLD_FRAC` (0.3), `CROSSTALK_DURATION` (3.0 s), `CROSSTALK_THRESHOLD_K` (3.0), `CALIBRATION_VERIFY_DURATION` (3.0 s), `CALIBRATION_VERIFY_ACTIVE_FRAC` (0.25) |
| `features` | `FEATURE_K_THRESHOLD` (8.0), `FEATURE_BACKTRACK_K` (3.0), `FEATURE_FATIGUE_RMS_THRESHOLD` (0.317), etc. |
| `ui` | `RENDER_FPS` (30), `HEATMAP_BUFFER_SAMPLES` (100), `BATTERY_POLL_INTERVAL` (30 s), `BTN_STREAM_ACTIVE`, `BTN_RECORD_ACTIVE` |
| `recording` | `RECORDING_MAX_SAMPLES` (1,000,000) |
| `session` | `SESSION_MUSCLE_GROUPS` (list), `SESSION_EXERCISE_TYPES` (list) |
| `longitudinal` | `LONGITUDINAL_MAX_SESSIONS` (200) |
| `safety` | `LATENCY_WARNING_MS` (100), `LATENCY_ROLLING_WINDOW` (10), `DISCONNECT_WARNING_SEC` (5), `ADC_RAIL_VALUE` (32767) |

### Adapter configuration

The `adapter` section of `config.json` controls ribbon cable channel remapping:

```json
"adapter": {
  "type": "ad1x64sp",
  "heatmap_mode": "demo",
  "channel_map": null
}
```

| Field | Value | Effect |
|---|---|---|
| `type` | `"ad1x64sp"` | No remap; all 64 channels used as-is; `heatmap_mode` ignored |
| `type` | `"ad2x32sp"` | Loads built-in 64-element preset; derives `DEAD_CHANNELS`; `heatmap_mode` active |
| `channel_map` | `null` | Use built-in preset for the selected type |
| `channel_map` | `[…]` | 64-element override list (takes priority over preset) |
| `heatmap_mode` | `"removed"` | Dead cells: dark purple-grey + × overlay + em-dash label (default) |
| `heatmap_mode` | `"raw"` | Dead cells: rendered like live cells (always cold since device sends 0) |
| `heatmap_mode` | `"demo"` | Dead cells: coloured at the mean RMS of all active channels |

`DEAD_CHANNELS` is a `frozenset` of 0-based logical channel indices that always output zero for the active adapter. For `ad2x32sp`, this is the 16 channels whose raw data indices fall in offsets 4–11 of each 32-channel device block (raw indices 4–11 and 36–43). These correspond to device input pins that the ad2x32sp connector does not make contact with.

`ADAPTER_HEATMAP_MODE` is `None` when `DEAD_CHANNELS` is empty (i.e. `ad1x64sp`); all three heatmap mode branches in `HeatmapWidget` are unreachable when the dead channel set is empty.

**Adding a new adapter preset:** add an entry to `_ADAPTER_PRESETS` in `config.py` (64-element list, `map[logical_idx] = raw_idx`) and a corresponding entry in `_ADAPTER_DEAD_RAW` (frozenset of raw indices that are always zero). Set `"type"` in `config.json` to activate it.

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
all_ch = (np.frombuffer(pkt_bytes, dtype='>i2')
          .astype(np.float32)
          .reshape(samples_per_pkt, nch)   # (125, 72)
          .T)                              # → (72, 125): (channels, samples)
raw = all_ch[:CFG.HDSEMG_CHANNELS]        # crop to 64 HD-EMG channels
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
      np.frombuffer big-endian int16 → reshape (samples, nch).T → (72, 125) float32

      crop to 64 HD-EMG channels: all_ch[:64]
      adapter remap (if ADAPTER_CHANNEL_MAP set): raw = raw[channel_map]

      on_stage('raw', raw)          — always emitted (recording needs it even when paused)

      if self.running:              — only when StreamingController.start_streaming() is active
        Pipeline('final').run(raw)  → bandpass + notch + rectify
        dead channels re-zeroed     → final[dead_mask, :] = 0.0  (prevents IIR transients)
        on_stage('final', final)

      on_stage callbacks:
        → recording_manager.on_data_for_recording(stage, data)
        → calibration_extra_callback(stage, data)   [during calibration only]
        → live_data_screen._on_data(stage, data)    [appends to _pending_packets on 'final']

      socket.timeout (5 s) during pause: continue loop — keeps thread alive

Kivy Clock.schedule_interval(_ui_tick, 1/30)   [30 fps]
  → LiveDataScreen._ui_tick(dt)
      swaps self._pending_packets with [], concatenates all accumulated packets
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

`_on_data()` runs on the receiver thread and appends each `final`-stage packet to `self._pending_packets` (a Python list). `_ui_tick()` runs on the Kivy main thread: it atomically replaces the list with a new empty list, then concatenates all accumulated packets along the sample axis. This decouples 16 Hz data arrival from 30 fps rendering: multiple packets accumulate between ticks and are concatenated into one array for rendering, without locks or queues. The list swap (`self._pending_packets = []`) is atomic in CPython.

---

## 6. Threading Model

**Rule: never touch a Kivy widget from a non-main thread.**

| Thread | What it does |
|---|---|
| Main (Kivy) | UI construction, `_ui_tick`, all widget updates, safety alert rendering |
| Receiver (`DataReceiverThread`) | `socket.recv()` loop, pipeline dispatch, appends to `_pending_packets`, disconnect detection — defined in `app/data/data_receiver.py` |
| Connection daemon | `device.start_server()` + `send_command()`; marshals result back via `Clock.schedule_once` |
| Battery daemon | `device.get_battery_level()` HTTP query |
| Save daemon | `recording_manager.save_recording_to_csv()` CSV write + metadata sidecar + session history |
| Analysis daemon | Each feature analysis function in `data_analysis_screen.py` |

All background-to-UI results use:
```python
Clock.schedule_once(lambda dt: update_ui(result), 0)
```

A new `DataReceiverThread` is created each time the user presses Stream (in `_on_connected`). Pressing Stream again to stop calls `_stop_stream()`, which:
1. Calls `StreamingController.stop_streaming()` → sets `receiver_thread.running = False` and cancels the Kivy clock.
2. Calls `receiver_thread.stop()` → sets `_stopping = True`, calls `socket.shutdown(SHUT_RDWR)` (required on Android/Linux to immediately interrupt a blocking `recv()`), then `socket.close()`. The thread exits its recv loop cleanly without triggering `on_error`.
3. Calls `device.stop_server()` → closes and nulls the server and client sockets.

`threading.Thread` can only be started once; the terminated thread is discarded and a new instance is created on the next Stream press.

---

## 7. Signal Processing

### Filter coefficients

All coefficients are pre-computed offline at 2000 Hz using `scripts/compute_filter_coeffs.py` (which uses scipy) and stored in `config.json`. At runtime only NumPy is required.

| Config key | Filter spec | Used in |
|---|---|---|
| `BANDPASS_4_B/A` | Butterworth order 4, 20–450 Hz bandpass | Live pipeline; all post-session analyses |
| `BANDPASS_1_B/A` | Butterworth order 1, 20–450 Hz bandpass | Short-data fallback in `butter_bandpass` |
| `LOWPASS_10_4_B/A` | Butterworth order 4, 10 Hz lowpass | TKEO envelope smoothing (post-session, via `filtfilt`); Auto MAV live display envelope (`_envelope_filter` in `LiveDataScreen`, via `StatefulIIRFilter`) |
| `NOTCH_60_B/A` | Butterworth order 2 notch, 60 Hz, Q=30 | Live pipeline power-line removal |

To regenerate after changing sample rate or cutoffs:
```bash
python scripts/compute_filter_coeffs.py --fs 4000
# paste the printed b/a arrays into config.json filter_coefficients section
```

### Pure-numpy IIR implementation (`iir_filter.py`)

`lfilter(b, a, x)` — Direct Form II Transposed, causal. Supports 1-D signals and `(channels, samples)` arrays by looping over channels.

`filtfilt(b, a, x)` — Zero-phase forward+backward filter with mirror padding of length `3 × (max(len(a), len(b)) - 1)`. Uses `_lfilter_zi()` to compute initial conditions for steady-state output and `_lfilter_ic()` to apply the filter with initial conditions. Falls back to causal `lfilter` if the signal is shorter than the minimum pad length.

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

Note: timestamp preprocessing in `_preprocess_timestamps` now uses `np.maximum.accumulate()` to ensure strict monotonicity, fixing a bug where non-monotonic sequences could pass through.

### Real-time metrics (`live_metrics.py`)

`LiveMetricsComputer` maintains a circular buffer (configurable window, default 1000 samples) and computes metrics at `FEATURE_STEP_DURATION` boundaries (200 samples = 100 ms steps):
- **RMS** on the current window
- **Median frequency** via FFT + cumulative sum search
- **Fatigue flags**: `fatigue_rms` (RMS drops below baseline threshold) and `fatigue_mf` (median frequency slope < `FEATURE_FATIGUE_MF_THRESHOLD` over last 10 windows)

Call `set_baseline(rms)` after calibration. `update(samples)` returns a metrics dict or `None` if no boundary was crossed.

---

## 8. Calibration (`calibration_popup.py`)

The `CalibrationPopup` is a Kivy `Popup` that runs a two-phase protocol driven by `Clock.schedule_interval`:

1. **Rest phase** (3.0 s) — registers `_collect_sample` via `on_sample_connect`; collects raw stage packets into `_rest_samples`.
2. **MVC phase** (3.0 s) — same callback, collects into `_mvc_samples`. After collection, `_evaluate_and_finish` evaluates spatial concentration of activation via `compute_concentration()` on the MVC data. Result is PASS (green) if activation is spatially concentrated, WARNING (orange) if diffuse.
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

### Crosstalk Verification (`crosstalk_popup.py`)

`CrosstalkVerificationPopup` is an optional post-calibration check. The subject performs plantar flexion (antagonist movement) for `CROSSTALK_DURATION` seconds. The popup computes per-channel RMS during the test and compares to the rest-phase baseline. Channels where `test_rms > baseline_rms + CROSSTALK_THRESHOLD_K × baseline_rms` are flagged. Result: PASS (no flagged channels) or WARNING (lists flagged channels).

---

## 9. Screen Interface Guide

All screens are `kivy.uix.screenmanager.Screen` subclasses added to a single `ScreenManager`. Navigation is done by setting `self.manager.current = 'screen_name'`.

### SelectionScreen

Three buttons: "Live Data Viewing" → mode popup → `'live_data'`; "Data Analysis" → `'data_analysis'`; "Session History" → `'longitudinal'`.

The "Live Data Viewing" button opens a popup with two choices: **Basic (Clinical)** and **Advanced (Researcher)**. The selected mode calls `LiveDataScreen.set_mode(mode)` before navigating.

### LiveDataScreen

Layout (vertical `BoxLayout`):

| Region | Height fraction | Contents |
|---|---|---|
| Top bar | 0.10 | Back, Guide, Calibrate, Crosstalk, Stream, Record, contraction label, battery label, latency label, status label |
| Disconnect banner | 0.05 | Red warning text (hidden when connected) |
| Tab bar | 0.07 | EMG Plot toggle, Heatmap toggle, Time cycle button, Ch: input, View cycle button (Advanced mode only) |
| Content | 0.70 | FloatLayout with three overlapping panels: `plot_single`, `plot_multi`, `heatmap` |
| Metrics bar | 0.08 | RMS, median frequency, contraction indicator, active channel |
| Bottom bar | 0.05 | Status/instruction label |

The three content panels are stacked in the FloatLayout; visibility is controlled by setting `widget.opacity = 0` or `1`. Only one is visible at a time.

**Basic / Advanced modes:** `set_mode(mode)` switches between `'basic'` and `'advanced'`. `_apply_mode()` hides/shows UI controls accordingly. Basic mode uses `_VIEW_MODES_BASIC` (Auto MAV only); Advanced mode uses `_VIEW_MODES_ADVANCED` (Auto MAV + all multi-track views).

**View modes** are defined in `_VIEW_MODES_BASIC` and `_VIEW_MODES_ADVANCED` (module-level lists of `(label, n_tracks, agg_fn)` tuples). The `'auto_mav'` sentinel triggers automatic channel selection based on highest activity. Cycling calls `_rebuild_multi_track()` when the track count changes.

**Safety monitoring:** Two real-time monitors run during streaming:
- `_latency_window` (rolling deque) — tracks processing latency, warns if >100 ms
- `DataReceiverThread.on_disconnect` callback — fires if no packet for >5 seconds

**Real-time metrics:** `_metrics_computer` (`LiveMetricsComputer`) computes rolling RMS, median frequency, and fatigue flags. Results are stored in `_pending_metrics` and rendered each UI tick.

**Session metadata:** On record start, `SessionMetadataPopup` collects date, subject ID, muscle group, exercise type, and notes. Metadata is passed to `RecordingManager.set_metadata()`.

**Crash recovery:** `on_enter()` checks for orphaned autosave files and auto-recovers them.

**Changing number of view modes:** add an entry to `_VIEW_MODES_ADVANCED` and implement an aggregation function `fn(data) -> (n_tracks, samples)` where `data` is `(≥64, samples)`.

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

### LongitudinalScreen

Session history viewer with trend visualization.

Layout:
- Top bar (8%): Back button + "Session History" title
- Filter bar (7%): Subject and Muscle `Spinner` widgets + Refresh button
- Trend chart (45%): `TrendPlotWidget` showing selected metric vs. session
- Metric selector (7%): Buttons for Peak RMS / Median Freq / Contractions
- Session list (33%): `ScrollView` with session cards

Data is loaded from `SessionHistoryManager` on screen enter. The filter spinners are populated from unique values in the history. `_apply_filter()` filters sessions by subject and muscle group and updates the chart and list. `_set_metric(metric_key)` switches the trend plot metric.

Session cards display: date, muscle group, exercise type, subject ID, duration, and metric values.

---

## 10. Visualization Widgets

All widgets use Kivy's `canvas` API directly — no matplotlib or pyqtgraph.

### EMGPlotWidget (`emg_plot_widget.py`)

Single-channel rolling waveform. Buffer is `display_samples` long (default 4000 = 2 s at 2000 Hz) implemented as a circular buffer with a write pointer (no `np.roll` allocation). On `render()`, the buffer is linearised from a display-aligned read pointer (`_display_read`), downsampled by `downsample` (default 4 → 1000 rendered points), scaled to a peak-hold y-axis range (expands to accommodate new extremes, never shrinks), and assigned to a single `canvas.Line` instruction. Call `reset_scale()` at stream start to clear the peak-hold range.

The display read pointer advances in downsample-aligned steps only (`_samples_pending` tracks remainder samples). This ensures averaged display points maintain consistent y-values as they scroll left.

### MultiTrackPlotWidget (`multi_track_plot.py`)

N independent rolling plots stacked vertically. Pre-allocates one `Color` + one `Line` canvas instruction per track at construction. `update_track(i, samples)` and `render()` update `.points` and `Color.rgba` without creating new canvas objects — critical for avoiding Android garbage collection pauses.

Each track maintains its own display-aligned read pointer (`_display_reads[idx]`) and pending sample counter. Downsampling uses block-average decimation (reshape + mean) instead of naive skip, providing anti-aliased rendering.

### HeatmapWidget (`heatmap_widget.py`)

8×8 grid of 64 `(Color, Rectangle)` pairs with grid lines, channel number labels, and optional channel highlight. `update(normalized_rms)` takes a `(64,)` array with values in `[0, 1]` and linearly interpolates each channel's color between `HEATMAP_COLD_RGB = (0.12, 0.12, 0.12)` and `HEATMAP_HOT_RGB = (0.0, 0.90, 0.40)`.

Grid lines (dark gray) separate rows and columns. Each cell displays its 1-based channel number using `CoreLabel` textures (dynamically sized based on cell dimensions). `set_highlight(channel_idx)` draws a white ellipse outline on the specified cell; `clear_highlight()` removes it.

The heatmap is inactive (no color updates) before calibration. After calibration, colors are scaled relative to calibration MVC values.

Channel-to-grid mapping:
```python
channel_idx = col * 8 + (7 - row)   # col, row in 0..7; bottom-left = channel 0
```

### CalibrationPopup (`calibration_popup.py`)

Kivy `Popup` with a progress bar driven by `Clock.schedule_interval`. Three phases share the same timer logic; only the target sample list and prompt text change between phases. Phase 3 (verification) evaluates spatial concentration via `compute_concentration()`.

### CrosstalkVerificationPopup (`crosstalk_popup.py`)

Post-calibration popup that prompts plantar flexion and compares per-channel RMS to the rest-phase baseline. Channels exceeding `baseline + CROSSTALK_THRESHOLD_K × baseline` are flagged. Emits `on_complete(passed, flagged_channels)`.

### SessionMetadataPopup (`session_metadata_popup.py`)

Modal form collecting date, subject ID, muscle group (`Spinner`), exercise type (`Spinner`), and notes. Spinner options are populated from `CFG.SESSION_MUSCLE_GROUPS` and `CFG.SESSION_EXERCISE_TYPES`. Emits `on_confirm(metadata_dict)`.

### SENIAMGuidePopup (`seniam_guide_popup.py`)

Scrollable popup displaying SENIAM electrode placement guidelines for the tibialis anterior, including anatomical landmarks, array positioning, skin preparation, and a pre-session checklist.

### TrendPlotWidget (`trend_plot_widget.py`)

Canvas-based line+marker chart. `set_data(x_labels, y_values, y_label)` draws connected data points with circular markers, 3 horizontal grid lines, Y-axis min/mid/max labels, smart X-axis label sampling, and a rotated Y-axis title. Auto-scales with padding. Shows an empty-state label when no data is provided.

---

## 11. Recording (`recording_manager.py`)

`RecordingManager` accumulates raw stage data as a Python list of `(timestamp, channel_data)` tuples, where `timestamp` is seconds elapsed since `recording_start_time` and `channel_data` is a `(64,)` float32 array (first `HDSEMG_CHANNELS` channels only — auxiliary channels excluded). When recording stops, `save_recording_to_csv()` writes a timestamped CSV in a daemon thread.

**Autosave write-through:** On `start_recording()`, a temp CSV file (`_autosave_YYYYMMDD_HHMMSS.csv`) is opened and samples are written in real time. On normal save, the autosave file is renamed to the final filename. If autosave file creation fails, recording falls back to in-memory-only mode.

**Session metadata:** `set_metadata(metadata)` stores a metadata dict before recording. On save, a JSON sidecar file (`<recording_name>_meta.json`) is written alongside the CSV with the metadata and computed summary statistics. The session summary is also appended to the longitudinal history via `SessionHistoryManager`.

**Crash recovery:** `find_orphaned_autosaves()` (static) discovers `_autosave_*.csv` files in the recordings directory. `recover_autosave(filename)` renames them to permanent recordings.

**CSV filename format:** `recording_YYYYMMDD_HHMMSS.csv`

**Overflow callback:** if the list length reaches `RECORDING_MAX_SAMPLES` (1,000,000 samples), `on_overflow()` is called. `LiveDataScreen` uses this to auto-stop recording and show a message.

### Session History (`session_history.py`)

`SessionHistoryManager` persists a JSON array of session summaries in `session_history.json`. Each summary is computed by `compute_session_summary(data, metadata)` and includes per-channel RMS/MAV, best channel, median frequency, fatigue flags, and contraction count. Writes use atomic temp-file + rename for crash safety. Query helpers: `get_sessions_for_muscle(muscle)`, `get_sessions_for_subject(subject_id)`. History is trimmed to `LONGITUDINAL_MAX_SESSIONS` entries.

---

## 12. File Paths (`paths.py`)

`get_recordings_dir()` uses a priority chain on Android:
1. `jnius` → `Context.getExternalFilesDir()` → `<sdcard>/Android/data/org.bmeg457.otbemgapp/files/OTB_EMG/recordings/`
2. Direct POSIX path: `/sdcard/Android/data/org.bmeg457.otbemgapp/files/OTB_EMG/recordings/`
3. Kivy `App.user_data_dir` private directory (last resort — not visible in file manager)

On desktop (non-Android): `~/OTB_EMG_Data/recordings/`

---

## 13. Testing

The test suite uses the standard `unittest` framework and runs without device hardware or Kivy.

### Run all tests

```bash
python -m unittest discover tests
```

### Run an individual module

```bash
python -m unittest tests.test_iir_filter
python -m unittest tests.test_filters
python -m unittest tests.test_features
python -m unittest tests.test_pipeline
python -m unittest tests.test_device
python -m unittest tests.test_recording_manager
python -m unittest tests.test_data_receiver
python -m unittest tests.test_networking
python -m unittest tests.test_processing
python -m unittest tests.test_autosave
python -m unittest tests.test_calibration_verification
python -m unittest tests.test_crosstalk
python -m unittest tests.test_disconnect_detection
python -m unittest tests.test_latency_monitor
```

### Test coverage summary

| File | Classes | What is tested |
|---|---|---|
| `test_iir_filter.py` | 5 | `lfilter`, `filtfilt` (with initial conditions), `find_peaks`, `resample_signal`, `StatefulIIRFilter` |
| `test_filters.py` | 4 | `butter_bandpass`, `notch`, `rectify`, live filter init/reset/isolation |
| `test_features.py` | 8 | `rms`, `mav`, `integrated_emg`, `median_frequency_window`, `_preprocess_timestamps` (monotonicity fix), TKEO, burst, bilateral symmetry, fatigue, centroid shift, spatial non-uniformity |
| `test_pipeline.py` | 2 | `ProcessingPipeline` stage execution, named registry isolation |
| `test_device.py` | 5 | Channel/frequency lookup, command bit encoding, network check, `send_command`, `start_server` |
| `test_recording_manager.py` | 5 | State machine, 64-channel capture, relative timestamps, overflow, CSV header and row count, metadata sidecars, session history integration |
| `test_data_receiver.py` | 4 | Packet byte decoding, stage dispatch gated by `running`, timeout survival, split-packet reassembly, disconnect detection |
| `test_networking.py` | 2 | Loopback TCP handshake, connection timeout, `stop_server` cleanup |
| `test_processing.py` | 2 | Full filter pipeline shape/non-negativity on 72-channel data |
| `test_autosave.py` | — | Autosave file creation, write-through integrity, crash recovery workflows, file rotation on overflow |
| `test_calibration_verification.py` | — | 3-phase calibration flow, concentration computation, PASS/WARNING logic |
| `test_crosstalk.py` | — | Crosstalk threshold evaluation, flagged channel detection, multiple baseline scenarios |
| `test_disconnect_detection.py` | — | Socket timeout → disconnect warning, latency thresholding, callback invocation |
| `test_latency_monitor.py` | — | Rolling window latency computation, warning threshold logic |

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
| Autosave | Write-through temp CSV created during recording for crash recovery |
| Buildozer | Build tool that invokes python-for-android (p4a) to create APKs |
| Canvas | Kivy's low-level drawing API; `Color`, `Line`, `Rectangle` instructions |
| Clipping | ADC rail saturation — signal exceeds ±32767 range |
| Clock | Kivy's event scheduler; `Clock.schedule_once` and `schedule_interval` run on the main thread |
| Crosstalk | Unintended pickup of signals from adjacent muscles |
| HD-sEMG | High-density surface electromyography; an 8×8 grid of 64 surface electrodes |
| MAV | Mean absolute value of EMG signal amplitude |
| MVC | Maximum voluntary contraction; used as 100% activation reference |
| NDK | Android Native Development Kit; needed to cross-compile C extensions |
| p4a | python-for-android; cross-compiles Python + deps to ARM |
| Pipeline | Named ordered list of processing functions applied to data |
| SENIAM | Surface Electromyography for the Non-Invasive Assessment of Muscles; European guidelines for electrode placement |
| Sidecar | JSON metadata file saved alongside a recording CSV |
| TKEO | Teager-Kaiser Energy Operator; Ψ(x[n]) = x[n]² − x[n-1]·x[n+1] |
| StatefulIIRFilter | `iir_filter.py` class that maintains filter state across packets for live streaming |
| WSL2 | Windows Subsystem for Linux version 2; Linux kernel inside Windows |
