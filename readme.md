# OTB EMG Mobile App

Android port of the OTB desktop EMG application (BMEG 457). Connects to the Sessantaquattro+ 64-channel HD-sEMG device over WiFi for real-time muscle activation monitoring and post-session feature analysis.

Built with Kivy and NumPy — no scipy at runtime.

---

## Modes

- **Live Data** — stream and visualize 64-channel HD-sEMG in real time, calibrate against baseline/MVC, record sessions to CSV
- **Data Analysis** — load recorded CSV files and run TKEO activation timing, burst duration, fatigue detection, bilateral symmetry, centroid shift, and spatial non-uniformity analyses

---

## Quick Start

### Install the pre-built APK

```powershell
cd C:\platform-tools
.\adb install -r "path\to\otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk"
```

A pre-built debug APK is in `bin/`.

### Build from source (WSL2)

```bash
ln -sf "/mnt/c/Users/Nicholas/Documents/Code/Python/BMEG_457/OTB-Python-Mobile" ~/otb-mobile
cd ~/otb-mobile
VIRTUAL_ENV=1 buildozer android debug
```

See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for full WSL2 setup, ADB instructions, and emulator mode.

### Run on desktop (for development)

```bash
set SESSANTAQUATTRO_EMULATOR=1
python main.py
```

---

## Requirements

Runtime: `python3`, `kivy==2.3.0`, `numpy`

Build (WSL2): `buildozer`, `openjdk-17-jdk`, `cython3`

---

## Documentation

| Document | Contents |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | App usage: connect, stream, calibrate, record, analyse |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Architecture, screen interface, signal processing, threading, widgets |
| [docs/DESIGN_RATIONALE.md](docs/DESIGN_RATIONALE.md) | Justification and references for all algorithms, filters, and constants |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | WSL2 build setup, ADB commands, all Android-specific code modifications |
| [docs/MOBILE_APP_OVERVIEW.md](docs/MOBILE_APP_OVERVIEW.md) | High-level architecture index |

---

## Project Structure

```
main.py                 Entry point (Kivy App, ScreenManager)
buildozer.spec          Android build config
app/
  core/                 Config, device TCP protocol, path resolution
  data/                 DataReceiverThread (TCP recv loop, pipeline dispatch)
  managers/             RecordingManager, StreamingController
  processing/           iir_filter.py, filters.py, features.py, pipeline.py
  ui/screens/           SelectionScreen, LiveDataScreen, DataAnalysisScreen, AnalysisPlotScreen
  ui/widgets/           EMGPlotWidget, MultiTrackPlotWidget, HeatmapWidget, CalibrationPopup
scripts/                compute_filter_coeffs.py (offline, desktop only)
tests/                  test_iir_filter.py, test_filters.py, test_features.py,
                        test_pipeline.py, test_device.py, test_recording_manager.py,
                        test_data_receiver.py, test_networking.py, test_processing.py
bin/                    Pre-built APK
docs/                   All documentation
```

---

## Tests

```bash
# Run full suite (no device or Kivy required)
python -m unittest discover tests

# Run individual modules
python -m unittest tests.test_iir_filter
python -m unittest tests.test_filters
python -m unittest tests.test_features
python -m unittest tests.test_pipeline
python -m unittest tests.test_device
python -m unittest tests.test_recording_manager
python -m unittest tests.test_data_receiver
python -m unittest tests.test_networking
python -m unittest tests.test_processing
```
