# OTB EMG Mobile App — Overview

Android port of the OTB desktop EMG application, built with Kivy and NumPy. Connects to the Sessantaquattro+ 64-channel HD-sEMG device over WiFi for real-time muscle activation monitoring and post-session feature analysis.

---

## Documentation Index

| Document | Audience | Contents |
|---|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | App user | Hardware setup, connecting, streaming, calibration, recording, analysis, session history, troubleshooting |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Developer | Architecture, screen interface, communication protocol, signal processing, threading, widgets, safety monitoring, build system |
| [DESIGN_RATIONALE.md](DESIGN_RATIONALE.md) | Developer / researcher | Justification and literature references for every algorithm, filter parameter, threshold, and constant |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Developer | WSL2 setup, all build commands, ADB install, emulator mode, all modifications made to enable Android packaging |
| [ifu.md](ifu.md) | Clinician / operator | Instructions for Use: electrode placement (SENIAM), session protocol, skin care, safety, disposal |

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
    data_receiver.py            DataReceiverThread: recv loop, pipeline dispatch, disconnect detection
  managers/
    recording_manager.py        CSV recording with autosave, metadata sidecars, session history
    streaming_controller.py     Receiver thread lifecycle + Kivy Clock UI tick
    session_history.py          Longitudinal session summaries (JSON persistence)
  processing/
    iir_filter.py               Pure-numpy lfilter, filtfilt, find_peaks, resample_signal
    filters.py                  Bandpass / notch / rectify wrappers; stateful live filters
    features.py                 TKEO, burst, bilateral symmetry, fatigue, centroid, entropy
    pipeline.py                 Named pipeline registry
    live_metrics.py             Real-time rolling RMS, median frequency, fatigue flags
  ui/
    screens/
      selection_screen.py       Mode selector (Live Data / Data Analysis / Session History)
      live_data_screen.py       Live streaming, calibration, recording (basic/advanced modes)
      data_analysis_screen.py   Post-session CSV analysis and export
      analysis_plot_screen.py   Static signal viewer with filter controls
      longitudinal_screen.py    Session history viewer with trend charts
    widgets/
      emg_plot_widget.py        Single-channel rolling Kivy canvas plot
      multi_track_plot.py       N-track stacked Kivy canvas plot
      heatmap_widget.py         8x8 electrode activation heatmap (with gridlines and labels)
      calibration_popup.py      Three-phase timed calibration dialog (rest, MVC, verification)
      crosstalk_popup.py        Crosstalk verification during plantar flexion
      session_metadata_popup.py Session metadata entry form (subject, muscle, exercise)
      seniam_guide_popup.py     SENIAM electrode placement guide
      trend_plot_widget.py      Canvas-based line+marker trend chart
scripts/
  compute_filter_coeffs.py      Offline coefficient generator (requires scipy, desktop only)
tests/
  test_networking.py            TCP socket smoke test
  test_processing.py            Filter pipeline smoke test
  test_autosave.py              Autosave write-through and crash recovery
  test_calibration_verification.py  3-phase calibration and concentration check
  test_crosstalk.py             Crosstalk threshold evaluation
  test_disconnect_detection.py  Socket timeout and disconnect warning
  test_latency_monitor.py       Rolling latency window and threshold
buildozer.spec                  Android build configuration
```

---

## Key Design Points

- **No scipy at runtime.** Filter coefficients are pre-computed offline at 2000 Hz and stored in `config.json`. `iir_filter.py` provides pure-numpy replacements for `lfilter`, `filtfilt`, `find_peaks`, and `resample_signal`.
- **Receiver thread runs once.** `streaming_controller.py` toggles a `running` flag to pause/resume. The thread is never restarted — only started once per app session.
- **Pending-data pattern.** Data arrives at 16 Hz; UI renders at 30 fps. `_on_data()` writes to `_pending_data`; `_ui_tick()` reads and clears it. Last-packet-wins — no queue buildup.
- **Kivy Clock for thread safety.** All widget updates from background threads go through `Clock.schedule_once(fn, 0)`.
- **Configuration-driven.** All magic numbers live in `config.json`. Never hardcode a threshold or frequency directly in source.
- **Adapter channel remapping.** `config.json ["adapter"]["type"]` selects the ribbon cable. `config.py` loads the built-in channel map preset and derives `DEAD_CHANNELS` — the frozenset of logical channel indices that are always zero for the given adapter. The receiver thread applies the map after cropping to 64 channels and re-zeros dead channels after the filter pipeline to prevent IIR transients.
- **Dead-channel awareness.** `DEAD_CHANNELS` is consumed by the heatmap (distinct purple-grey fill + × overlay), calibration (dead channels excluded from RMS, baseline, and concentration calculations), and the recording sidecar JSON (`dead_channels`, `active_channel_count` fields).
- **Basic / Advanced modes.** The selection screen offers Basic (clinical) and Advanced (researcher) modes for live data. Basic mode hides channel selectors, time window, and view mode controls for a streamlined clinical workflow.
- **Safety monitoring.** Real-time disconnect warnings and latency tracking run alongside the data pipeline. Alerts surface in the UI without interrupting streaming.
- **Autosave crash recovery.** Recordings are written through to a temp CSV during capture. On crash, orphaned autosave files are detected and recovered on next launch.
- **Longitudinal tracking.** Session summaries (metrics + metadata) are appended to a JSON history file and visualized in the Session History screen.
