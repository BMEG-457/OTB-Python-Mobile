# Mobile App Build Context

## Environment

- **Platform:** WSL2 (Ubuntu) on Windows 11
- **Project path in WSL:** `/mnt/c/Users/Nicholas/Documents/Code/Python/BMEG_457/OTB-mobile/OTB-Python-App/mobile_app/`
- **Symlink (no spaces):** `~/otb-mobile` → project path (required — p4a rejects paths with spaces)
- **Build dir (no spaces):** `/home/fettuccinifelix/.buildozer/otb-mobile` (set in `buildozer.spec`)
- **Build command:** `cd ~/otb-mobile && VIRTUAL_ENV=1 buildozer android debug`
- **APK output:** `~/otb-mobile/bin/otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk`

---

## Buildozer Setup (WSL)

### Installed tools

```bash
sudo apt install -y python3 python3-pip python3-venv git \
    zip unzip openjdk-17-jdk autoconf libtool pkg-config \
    zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake \
    libffi-dev libssl-dev pipx cython3

pipx ensurepath && source ~/.bashrc
pipx install buildozer
pipx inject buildozer setuptools appdirs colorama jinja2 "sh>=1.10,<2.0" build toml packaging
```

### Required env vars

| Variable | Value | Reason |
|---|---|---|
| `VIRTUAL_ENV=1` | any non-empty string | Stops buildozer from passing `--user` to pip inside its venv (see android.py line 720) |
| `LEGACY_NDK=~/android-ndk-r21e` | path to NDK r21e | scipy/numpy need gfortran; r25b dropped it. **Now removed from requirements — no longer needed.** |

### NDK r21e (kept on disk, not currently needed)

```bash
cd ~ && wget https://dl.google.com/android/repository/android-ndk-r21e-linux-x86_64.zip
unzip android-ndk-r21e-linux-x86_64.zip
```

---

## Errors Encountered & Fixes

| Error | Fix |
|---|---|
| `externally-managed-environment` on `pip3 install buildozer` | Use `pipx install buildozer` |
| `No module named 'distutils'` (Python 3.12 removed it) | `pipx inject buildozer setuptools` |
| `# Cython not found` | `pipx inject buildozer cython` (also `sudo apt install cython3` for system Python) |
| `Cannot perform --user install` in pipx venv | `pipx inject buildozer appdirs colorama jinja2 ...` + set `VIRTUAL_ENV=1` |
| `storage dir path cannot contain spaces` | Symlink project to `~/otb-mobile` + set `build_dir` in `buildozer.spec` to a Linux-native path with no spaces |
| `LEGACY_NDK not found` / gfortran missing | Download NDK r21e; **now moot — scipy removed** |

### The `--user` flag patch (for reference)

The flag is at line 720 of `android.py` in the buildozer pipx venv:
```python
options = ["--user"]
if "VIRTUAL_ENV" in os.environ or "CONDA_PREFIX" in os.environ:
    options = []
```
Setting `VIRTUAL_ENV=1` makes buildozer drop the `--user` flag automatically — no source patching needed.

---

## Dependency Removal (scipy / matplotlib / kivy_matplotlib_widget)

These were removed to avoid the Android gfortran/NDK requirement.

### `buildozer.spec` requirements (after)

```ini
requirements = python3,kivy==2.3.0,numpy
```

### New files created

| File | Purpose |
|---|---|
| `app/processing/iir_filter.py` | Pure-numpy `lfilter`, `filtfilt`, `find_peaks`, `resample_signal` |
| `scripts/compute_filter_coeffs.py` | Offline script to regenerate filter coefficients via scipy |

### Files changed

| File | What changed |
|---|---|
| `app/core/config.py` | Expanded: all tunable params + pre-computed Butterworth b/a arrays |
| `app/processing/filters.py` | Removed scipy; uses config coefficients + `iir_filter.filtfilt` |
| `app/processing/features.py` | Removed `scipy.signal` and `scipy.fft`; uses `iir_filter` + `np.fft` + config |
| `app/ui/widgets/emg_plot_widget.py` | Replaced matplotlib + `kivy_matplotlib_widget` with pure Kivy canvas |
| `app/ui/widgets/calibration_popup.py` | Durations and threshold fraction now read from config |
| `app/ui/screens/live_data_screen.py` | Pipeline setup and device command params now read from config |

### Filter coefficient design

Pre-computed at **DEVICE_SAMPLE_RATE = 2000 Hz** (FSAMP=2, MODE=0):

| Config key | Filter | Use |
|---|---|---|
| `BANDPASS_4_B/A` | butter(4, [20, 450] Hz, band) | Live pipeline + post-session analysis |
| `BANDPASS_1_B/A` | butter(1, [20, 450] Hz, band) | Short-data fallback in `butter_bandpass` |
| `LOWPASS_10_4_B/A` | butter(4, 10 Hz, low) | TKEO envelope smoothing |
| `NOTCH_60_B/A` | butter(2, 60 Hz notch, Q=30) | Power-line notch in live pipeline |

To regenerate for a different sample rate:
```bash
python scripts/compute_filter_coeffs.py --fs 4000
# paste output into config.py FILTER COEFFICIENTS section
```

### Key design notes

- `iir_filter.filtfilt` uses reflect padding (length = `3 * max(len(a), len(b))`), matching scipy's default
- `iir_filter.find_peaks` returns `(indices, {})` matching scipy's interface
- `iir_filter.resample_signal` uses linear interpolation (vs scipy's FFT-based) — adequate for RMS-based bilateral symmetry analysis
- `filters.butter_bandpass` and `filters.notch` accept the old argument signatures but ignore them (uses config); callers do not need updating
- `features.py` warns at runtime if the detected sample rate differs >10% from `CFG.DEVICE_SAMPLE_RATE`

---

## Build Commands

### Full clean build

```bash
cd ~/otb-mobile
VIRTUAL_ENV=1 buildozer android clean
VIRTUAL_ENV=1 buildozer android debug
```

Always do a clean build after adding/removing source files or changing `buildozer.spec`.

### Incremental rebuild

```bash
cd ~/otb-mobile
VIRTUAL_ENV=1 buildozer android debug
```

Buildozer re-copies source files and repackages. Faster than clean build but may use stale
cached artifacts if directory structure changed.

### buildozer.spec key settings

```ini
[app]
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
requirements = python3,kivy==2.3.0,numpy
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
android.api = 28
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
orientation = landscape

[buildozer]
log_level = 2
warn_on_root = 1
build_dir = /home/fettuccinifelix/.buildozer/otb-mobile
```

The `build_dir` line is critical: it puts all build artifacts on the native Linux filesystem,
avoiding the spaces-in-path error from `/mnt/c/Users/Nicholas Santoso/...` and improving
build speed vs cross-filesystem `/mnt/c/` access.

---

## Install & Debug on Android

### ADB setup

ADB in WSL cannot see USB devices. Use Windows ADB instead:

1. Download [platform-tools](https://developer.android.com/tools/releases/platform-tools) and extract to `C:\platform-tools`
2. Enable Developer Options on phone: **Settings > About Phone > tap Build Number 7 times**
3. Enable **USB Debugging** in Developer Options
4. Connect phone via USB, accept the debugging prompt

### Install APK

From PowerShell:

```powershell
cd C:\platform-tools
.\adb devices                    # verify phone is listed
.\adb install -r "C:\Users\Nicholas Santoso\Documents\Code\Python\BMEG-457\OTB-mobile\OTB-Python-App\mobile_app\bin\otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk"
```

### View crash logs

```powershell
cd C:\platform-tools
.\adb logcat -c; .\adb logcat -s python:*
```

Run this **before** launching the app on the phone. The Python traceback will appear in the
terminal. Common crash causes:

| Error | Cause |
|---|---|
| `ModuleNotFoundError: No module named 'app.xxx'` | Source directory not packaged — do a clean build |
| `ImportError` | Missing dependency in `requirements` |
| `NameError` | Typo or missing import in Python source |

### Uninstall

```powershell
.\adb uninstall org.bmeg457.otbemgapp
```

---

## Emulator Mode (for testing without hardware)

### Build flag

Set `EMULATOR_BUILD = True` in `app/core/config.py` before building to skip the
192.168.1.x WiFi network check. Revert to `False` for production builds.

### Desktop testing

```bash
# Windows CMD
set SESSANTAQUATTRO_EMULATOR=1
python main.py
# Press Stream, then within 10 seconds:
python emulator.py
```

### Android testing

1. Set `EMULATOR_BUILD = True` in `app/core/config.py`
2. Clean build and install:
   ```bash
   cd ~/otb-mobile
   VIRTUAL_ENV=1 buildozer android clean
   VIRTUAL_ENV=1 buildozer android debug
   ```
   ```powershell
   cd C:\platform-tools
   .\adb install -r "C:\Users\Nicholas Santoso\Documents\Code\Python\BMEG-457\OTB-mobile\OTB-Python-App\mobile_app\bin\otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk"
   ```
3. Connect phone and PC to the same WiFi network
4. Find phone's IP: **Settings > WiFi > tap network > IP address**
5. Open app on phone > **Live Data** > press **Stream**
6. Within 10 seconds, run on PC:
   ```bash
   python emulator.py --host <phone-ip>
   ```
7. Emulator connects, phone displays live streaming data
