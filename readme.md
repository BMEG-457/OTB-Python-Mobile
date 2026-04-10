# OTB EMG Mobile App

Android port of the OTB desktop EMG application (BMEG 457). Connects to the Sessantaquattro+ 64-channel HD-sEMG device over WiFi for real-time muscle activation monitoring and post-session feature analysis.

Built with Kivy and NumPy — no scipy at runtime.

---

## Modes

- **Live Data (Basic / Advanced)** — stream and visualize HD-sEMG in real time, calibrate against baseline/MVC with verification, record sessions to CSV with metadata and autosave crash recovery. Basic (clinical) mode offers a simplified UI; Advanced (researcher) mode exposes all controls.
- **Data Analysis** — load recorded CSV files and run TKEO activation timing, burst duration, fatigue detection, bilateral symmetry, centroid shift, and spatial non-uniformity analyses
- **Session History** — view longitudinal trends across recording sessions, filter by subject or muscle group, and track metrics (peak RMS, median frequency, contraction count) over time

## Adapter Support

| Adapter | Channels | Grid | Notes |
|---------|----------|------|-------|
| ad1x64sp | 64 active | 8×8 | Default single cable; no remapping |
| ad2x32sp | 48 active | 8×8 (16 dead) | Dual 32-ch cables side-by-side; 8 device input pins per connector are not contacted by the adapter, leaving raw offsets 4–11 in each 32-ch block permanently zero |

Set `"adapter": {"type": "ad2x32sp"}` in `config.json` to activate the built-in channel map and dead-cell rendering. Dead cells appear as dark purple-grey with a × overlay on the heatmap and are excluded from calibration statistics and recording metadata.

---

## Quick Start

### Install the pre-built APK

```powershell
cd C:\platform-tools
.\adb install -r "path\to\otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk"
```

Install the .apk file from the "releases" tab on github

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
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | App usage: connect, stream, calibrate, record, analyse, session history |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Architecture, screen interface, signal processing, threading, widgets, safety monitoring |
| [docs/DESIGN_RATIONALE.md](docs/DESIGN_RATIONALE.md) | Justification and references for all algorithms, filters, and constants |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | WSL2 build setup, ADB commands, all Android-specific code modifications |
| [docs/MOBILE_APP_OVERVIEW.md](docs/MOBILE_APP_OVERVIEW.md) | High-level architecture index |
| [docs/ifu.md](docs/ifu.md) | Instructions for Use: electrode placement, session protocol, skin care, safety |

---

## CI / CD

Two GitHub Actions workflows are defined in [`.github/workflows/`](.github/workflows/).

### `ci.yml` — runs automatically

Triggered on every push to `main` or `dev` and on every pull request targeting `main`.

- Runs the full unit test suite against Python 3.10, 3.11, and 3.12 in parallel.
- Only requires `numpy` — no Kivy or device hardware needed.
- All jobs must pass before a PR can be merged.

### `build-apk.yml` — manual trigger only

Triggered from the **Actions** tab → **Build APK** → **Run workflow**.

- Patches the local WSL2 `build_dir` path in `buildozer.spec` to a CI-safe path before building.
- Builds inside the official `kivy/buildozer` Docker image (no WSL2 on the runner).
- Caches the Android SDK/NDK between runs (keyed on `buildozer.spec`) — first run takes ~20–40 min; subsequent runs are faster.
- Uploads the resulting APK as a downloadable workflow artifact (retained for 30 days).

---

## Project Structure

```
main.py                 Entry point (Kivy App, ScreenManager)
buildozer.spec          Android build config
.github/workflows/
  ci.yml                Unit tests on push/PR (Python 3.10–3.12)
  build-apk.yml         Manual APK build via Buildozer Docker image
app/
  core/                 Config, device TCP protocol, path resolution
  data/                 DataReceiverThread (TCP recv loop, pipeline dispatch, disconnect detection)
  managers/             RecordingManager (autosave, metadata), StreamingController, SessionHistoryManager
  processing/           iir_filter.py, filters.py, features.py, pipeline.py,
                        live_metrics.py
  ui/screens/           SelectionScreen, LiveDataScreen (basic/advanced modes),
                        DataAnalysisScreen, AnalysisPlotScreen, LongitudinalScreen
  ui/widgets/           EMGPlotWidget, MultiTrackPlotWidget, HeatmapWidget, CalibrationPopup,
                        TrendPlotWidget, SessionMetadataPopup, SENIAMGuidePopup, CrosstalkPopup
scripts/                compute_filter_coeffs.py (offline, desktop only)
tests/                  test_iir_filter.py, test_filters.py, test_features.py,
                        test_pipeline.py, test_device.py, test_recording_manager.py,
                        test_data_receiver.py, test_networking.py, test_processing.py,
                        test_autosave.py, test_calibration_verification.py,
                        test_crosstalk.py,
                        test_disconnect_detection.py, test_latency_monitor.py
bin/                    Pre-built APK
docs/                   All documentation (including IFU)
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
python -m unittest tests.test_autosave
python -m unittest tests.test_calibration_verification
python -m unittest tests.test_crosstalk
python -m unittest tests.test_disconnect_detection
python -m unittest tests.test_latency_monitor
```
