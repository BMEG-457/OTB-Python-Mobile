# OTB EMG Mobile App — Overview

Android port of the OTB desktop EMG application, built with Kivy and NumPy. Connects to the Sessantaquattro+ 64-channel HD-sEMG device over WiFi for real-time muscle activation monitoring and post-session feature analysis.

---

## Documentation Index

| Document | Audience | Contents |
|---|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | App user | Hardware setup, connecting, streaming, calibration, recording, analysis, troubleshooting |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Developer | Architecture, screen interface, communication protocol, signal processing, threading, widgets, build system |
| [DESIGN_RATIONALE.md](DESIGN_RATIONALE.md) | Developer / researcher | Justification and literature references for every algorithm, filter parameter, threshold, and constant |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Developer | WSL2 setup, all build commands, ADB install, emulator mode, all modifications made to enable Android packaging |

---

## Quick Architecture Reference

```
main.py                         Kivy App entry; ScreenManager + device instantiation
app/
  core/
    config.py / config.json     All tuneable params + pre-computed filter coefficients
    device.py                   TCP server, device command encoding, battery HTTP query
    paths.py                    Android-aware file path resolution
  data/
    data_receiver.py            DataReceiverThread: recv loop, pipeline dispatch
  managers/
    recording_manager.py        CSV recording accumulation and async write
    streaming_controller.py     Receiver thread lifecycle + Kivy Clock UI tick
  processing/
    iir_filter.py               Pure-numpy lfilter, filtfilt, find_peaks, resample_signal
    filters.py                  Bandpass / notch / rectify wrappers; stateful live filters
    features.py                 TKEO, burst, bilateral symmetry, fatigue, centroid, entropy
    pipeline.py                 Named pipeline registry
  ui/
    screens/
      selection_screen.py       Mode selector (Live Data Viewing / Data Analysis)
      live_data_screen.py       Live streaming, calibration, recording
      data_analysis_screen.py   Post-session CSV analysis and export
      analysis_plot_screen.py   Static signal viewer with filter controls
    widgets/
      emg_plot_widget.py        Single-channel rolling Kivy canvas plot
      multi_track_plot.py       N-track stacked Kivy canvas plot
      heatmap_widget.py         8x8 electrode activation heatmap
      calibration_popup.py      Two-phase timed calibration dialog
scripts/
  compute_filter_coeffs.py      Offline coefficient generator (requires scipy, desktop only)
tests/
  test_networking.py            TCP socket smoke test
  test_processing.py            Filter pipeline smoke test
buildozer.spec                  Android build configuration
```

---

## Key Design Points

- **No scipy at runtime.** Filter coefficients are pre-computed offline at 2000 Hz and stored in `config.json`. `iir_filter.py` provides pure-numpy replacements for `lfilter`, `filtfilt`, `find_peaks`, and `resample_signal`.
- **Receiver thread runs once.** `streaming_controller.py` toggles a `running` flag to pause/resume. The thread is never restarted — only started once per app session.
- **Pending-data pattern.** Data arrives at 16 Hz; UI renders at 30 fps. `_on_data()` writes to `_pending_data`; `_ui_tick()` reads and clears it. Last-packet-wins — no queue buildup.
- **Kivy Clock for thread safety.** All widget updates from background threads go through `Clock.schedule_once(fn, 0)`.
- **Configuration-driven.** All magic numbers live in `config.json`. Never hardcode a threshold or frequency directly in source.
