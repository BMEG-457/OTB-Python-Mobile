# OTB EMG Mobile App — Deployment Guide

Complete instructions for building the APK from source, installing it on Android, debugging, and running in emulator mode. All commands are listed explicitly.

---

## 1. Prerequisites

### System requirements

- Windows 11 with WSL2 (Ubuntu) installed
- Android phone with USB debugging enabled (see section 4)
- USB cable for initial APK transfer
- Phone on the same WiFi as the Sessantaquattro+ device during live streaming

### Why WSL2

Buildozer (the Python→APK tool) requires a Linux environment. WSL2 provides a full Linux kernel on Windows without a separate VM. The build runs entirely inside WSL2; ADB deployment uses the Windows ADB binary because WSL2 cannot access USB devices directly.

---

## 2. WSL2 Build Environment Setup

Run all commands in a WSL2 Ubuntu terminal unless noted.

### Install system packages

```bash
sudo apt update && sudo apt install -y \
    python3 python3-pip python3-venv git \
    zip unzip openjdk-17-jdk autoconf libtool pkg-config \
    zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake \
    libffi-dev libssl-dev pipx cython3
```

After installing pipx, add it to PATH:

```bash
pipx ensurepath
source ~/.bashrc
```

### Install Buildozer and its Python dependencies

```bash
pipx install buildozer
pipx inject buildozer setuptools appdirs colorama jinja2 "sh>=1.10,<2.0" build toml packaging
```

Verify installation:

```bash
buildozer --version
```

---

## 3. Project Symlink (Critical — Paths with Spaces)

The Buildozer / python-for-android toolchain rejects any path that contains a space character. The Windows filesystem path to this project is:

```
C:\Users\Nicholas\Documents\Code\Python\BMEG_457\OTB-Python-Mobile
```

which maps to:

```
/mnt/c/Users/Nicholas/Documents/Code/Python/BMEG_457/OTB-Python-Mobile
```

This path contains no spaces, so a symlink at the home directory is convenient but not strictly required. If your Windows username contains a space (e.g. `Nicholas Santoso`), the WSL path would be `/mnt/c/Users/Nicholas Santoso/...` — in that case a symlink is mandatory.

### Create the symlink (recommended regardless)

```bash
ln -sf "/mnt/c/Users/Nicholas/Documents/Code/Python/BMEG_457/OTB-Python-Mobile" ~/otb-mobile
```

All subsequent build commands use `~/otb-mobile` for clarity.

### buildozer.spec: redirect build artifacts to Linux filesystem

The `build_dir` in `buildozer.spec` is set to a native Linux path to avoid the cross-filesystem slowdown of `/mnt/c/...` access and to prevent any spaces from the Windows path entering p4a's internal variables:

```ini
[buildozer]
build_dir = /home/fettuccinifelix/.buildozer/otb-mobile
```

**Replace `fettuccinifelix` with your WSL username.** This directory is created automatically on first build.

---

## 4. Building the APK

### Required environment variable

Buildozer runs `pip install` inside a pipx virtual environment. Without `VIRTUAL_ENV=1`, pip adds the `--user` flag which fails inside a venv. Setting this variable tells Buildozer to omit the flag (checked at `android.py` line 720 in the buildozer pipx venv):

```python
# android.py in buildozer venv — no patching needed; this is handled at runtime:
if "VIRTUAL_ENV" in os.environ or "CONDA_PREFIX" in os.environ:
    options = []
```

### Full clean build (use after any structural change)

```bash
cd ~/otb-mobile
VIRTUAL_ENV=1 buildozer android clean
VIRTUAL_ENV=1 buildozer android debug
```

Always clean when:
- Source files are added or removed
- `buildozer.spec` changes
- `requirements` changes
- A previous build produced an incomplete APK

### Incremental build (for source-only changes)

```bash
cd ~/otb-mobile
VIRTUAL_ENV=1 buildozer android debug
```

Buildozer re-copies source files and repackages without recompiling dependencies. Faster, but may use stale cached artifacts if the directory structure changed.

### APK output location

```
~/otb-mobile/bin/otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk
```

The same file also appears at:

```
C:\Users\Nicholas\Documents\Code\Python\BMEG_457\OTB-Python-Mobile\bin\otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk
```

(The `bin/` directory in the repo already contains a pre-built APK.)

---

## 5. Android Device Setup

### Enable Developer Options

On the phone: **Settings > About Phone > tap Build Number 7 times**. A toast message confirms "You are now a developer."

### Enable USB Debugging

**Settings > Developer Options > USB Debugging → enable**

### Install ADB on Windows

1. Download [Android platform-tools](https://developer.android.com/tools/releases/platform-tools).
2. Extract to `C:\platform-tools`.
3. Connect phone via USB; accept the debugging authorization prompt on the phone.

ADB is run from PowerShell (not WSL2) because WSL2 cannot access USB devices.

---

## 6. Installing the APK

From **PowerShell** (not WSL2):

```powershell
cd C:\platform-tools
.\adb devices
```

Expected output: the phone's serial number listed as `device`.

```powershell
.\adb install -r "C:\Users\Nicholas\Documents\Code\Python\BMEG_457\OTB-Python-Mobile\bin\otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk"
```

`-r` replaces any existing installation.

### Uninstall

```powershell
.\adb uninstall org.bmeg457.otbemgapp
```

---

## 7. Viewing Crash Logs

Run this **before** launching the app on the phone so logcat is already capturing:

```powershell
cd C:\platform-tools
.\adb logcat -c
.\adb logcat -s python:*
```

Then launch the app. Python tracebacks appear in the terminal. Common errors:

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'app.xxx'` | Source directory not packaged | Clean build: `VIRTUAL_ENV=1 buildozer android clean && buildozer android debug` |
| `ImportError` for a library | Missing entry in `requirements` | Add library to `buildozer.spec requirements` |
| `NameError` | Typo or missing import in Python source | Fix in source; incremental rebuild |
| App launches then immediately closes | Python exception at startup | Check logcat for the full traceback |

---

## 8. Storage Permission (First Launch)

On first launch the app requests `WRITE_EXTERNAL_STORAGE`. The system dialog appears ~0.5 s after app start.

- Tap **Allow**: a popup informs the user to restart the app for GID changes to take effect.
- Tap **Deny**: a popup instructs the user to grant permission manually via Settings > Apps > OTB EMG App > Permissions > Storage > Allow.

After permission is granted and the app is restarted, recordings save to:
```
/sdcard/Android/data/org.bmeg457.otbemgapp/files/OTB_EMG/recordings/
```

Visible in file manager as: **Phone > Android > data > org.bmeg457.otbemgapp > files > OTB_EMG > recordings**

---

## 9. Emulator Mode (Testing Without Hardware)

Emulator mode bypasses the `192.168.1.x` WiFi check and allows a Python emulator script to act as the device.

### Enable emulator mode

In `app/core/config.json`:

```json
"build": {
    "emulator_build": true
}
```

Alternatively, set the environment variable: `SESSANTAQUATTRO_EMULATOR=1`.

**Important:** set `emulator_build` back to `false` before building a production APK.

### Desktop testing (no phone needed)

In Windows CMD or PowerShell:

```cmd
set SESSANTAQUATTRO_EMULATOR=1
python main.py
```

Press **Start Stream** in the app, then within 10 seconds (the connect timeout):

```cmd
python emulator.py
```

The emulator connects to the app's TCP server and sends synthetic data.

### Android emulator testing

1. Set `emulator_build: true` in `config.json`.
2. Clean build and install (see sections 4 and 6).
3. Connect phone and PC to the same WiFi network.
4. On the phone: **Settings > WiFi > tap the network > IP address** — note the phone IP.
5. Open the app on the phone, tap **Live Data**, press **Start Stream**.
6. Within 10 seconds, on PC:
   ```bash
   python emulator.py --host <phone-ip>
   ```
7. The emulator connects to the phone and streams synthetic data.

---

## 10. Modifications Made to Enable Android Packaging

This section documents every change made to the codebase specifically to allow Buildozer to produce a working APK. Changes are relative to the original desktop architecture.

### 10.1 Dependency removal: scipy, matplotlib, kivy_matplotlib_widget

**Why removed:** scipy has no python-for-android recipe compatible with modern NDK (r25b+) without a Fortran compiler. matplotlib depends on scipy indirectly. kivy_matplotlib_widget depends on matplotlib.

**How removed:**
- `buildozer.spec requirements` changed from `python3,kivy==2.3.0,numpy,scipy,matplotlib,kivy_matplotlib_widget` to `python3,kivy==2.3.0,numpy`.
- All `import scipy` statements removed from `filters.py` and `features.py`.
- All `import matplotlib` and `import kivy_matplotlib_widget` statements removed from widget files.

### 10.2 New file: `app/processing/iir_filter.py`

Pure-numpy replacements for the four scipy functions used at runtime:

| scipy function | iir_filter.py replacement | Notes |
|---|---|---|
| `scipy.signal.lfilter` | `lfilter(b, a, x)` | Direct Form II Transposed |
| `scipy.signal.filtfilt` | `filtfilt(b, a, x)` | Reflect padding, same length as scipy default |
| `scipy.signal.find_peaks` | `find_peaks(x, height, distance)` | Returns `(indices, {})` — same interface |
| `scipy.signal.resample` | `resample_signal(x, num)` | Linear interpolation (not FFT-based) |

Also provides `StatefulIIRFilter` class for live streaming with persistent state across packets.

### 10.3 New file: `scripts/compute_filter_coeffs.py`

Offline script (desktop only, not included in APK) that uses `scipy.signal.butter` and `scipy.signal.iirnotch` to compute filter coefficients and prints them for pasting into `config.json`. Run whenever the sample rate or filter cutoffs change:

```bash
python scripts/compute_filter_coeffs.py --fs 2000
```

### 10.4 Changed file: `app/core/config.py`

Expanded from device-only constants to include all tuneable parameters and pre-computed filter coefficients. The pre-computed Butterworth b/a arrays (computed at 2000 Hz) are stored in `config.json` and loaded as `BANDPASS_4_B/A`, `BANDPASS_1_B/A`, `LOWPASS_10_4_B/A`, `NOTCH_60_B/A`.

### 10.5 Changed file: `app/processing/filters.py`

- Removed `from scipy.signal import butter, lfilter, filtfilt, iirnotch`.
- Added `from app.processing.iir_filter import lfilter, filtfilt, StatefulIIRFilter`.
- `butter_bandpass()` and `notch()` now use pre-computed coefficients from `CFG.BANDPASS_4_B/A` and `CFG.NOTCH_60_B/A` instead of calling `scipy.signal.butter` at runtime.
- Added `init_live_filters(n_channels)` and `reset_live_filters()` to manage three `StatefulIIRFilter` instances used in the live pipeline.

### 10.6 Changed file: `app/processing/features.py`

- Removed `from scipy.signal import butter, filtfilt, find_peaks, resample` and `from scipy.fft import rfft, rfftfreq`.
- Added `from app.processing.iir_filter import filtfilt, find_peaks, resample_signal`.
- All FFT calls changed from `scipy.fft.rfft` / `scipy.fft.rfftfreq` to `numpy.fft.rfft` / `numpy.fft.rfftfreq`.
- Filter coefficient generation changed from `butter(...)` calls to reading `CFG.BANDPASS_4_B/A` and `CFG.LOWPASS_10_4_B/A`.
- A rate-mismatch warning is emitted if the detected sample rate differs >10% from `CFG.DEVICE_SAMPLE_RATE`.

### 10.7 Changed file: `app/ui/widgets/emg_plot_widget.py`

- Removed `matplotlib` and `kivy_matplotlib_widget` imports.
- Replaced the matplotlib Figure/Axes rendering with a pure Kivy canvas `Line` instruction.
- Buffer management (circular append) and downsampling implemented in NumPy.

### 10.8 Changed file: `app/ui/widgets/multi_track_plot.py`

- Replaced matplotlib subplot stacking with a custom Kivy canvas layout.
- Pre-allocates one `Color` + one `Line` canvas instruction per track at widget construction to avoid repeated object creation during 30 fps rendering (important for Android GC).

### 10.9 Changed file: `app/ui/widgets/heatmap_widget.py`

- Replaced matplotlib `imshow` with 64 Kivy `(Color, Rectangle)` canvas pairs.
- Color interpolation from cold to hot implemented in pure Python / NumPy.

### 10.10 Changed file: `app/ui/widgets/calibration_popup.py`

- Calibration phase durations and threshold fraction changed from hardcoded values to `CFG.CALIBRATION_REST_DURATION`, `CFG.CALIBRATION_MVC_DURATION`, `CFG.CALIBRATION_THRESHOLD_FRAC`.

### 10.11 Changed file: `app/ui/screens/live_data_screen.py`

- Pipeline setup changed to use config-derived device command parameters (`CFG.DEVICE_FSAMP`, `CFG.DEVICE_NCH`, etc.) instead of hardcoded values.
- Device command parameters read from `CFG` rather than hardcoded.

### 10.12 `buildozer.spec`: API level 28, legacy storage

```ini
android.api = 28
android.minapi = 21
```

Targeting API 28 (Android 9) gives the app "legacy storage" behaviour automatically on Android 10 (`requestLegacyExternalStorage` is implied, avoiding buildozer's manifest attribute injection mechanism). This allows writing to `/sdcard/Documents/OTB_EMG/` without Scoped Storage restrictions.

### 10.13 `buildozer.spec`: landscape orientation

```ini
orientation = landscape
```

Forces landscape on Android to match the widescreen plot layout.

### 10.14 `main.py`: runtime storage permission

`on_start()` schedules `_check_storage_permission()` 0.5 s after launch. This requests `WRITE_EXTERNAL_STORAGE` and `READ_EXTERNAL_STORAGE` at runtime (required on Android 9/10). If the user denies, a dialog explains how to grant it manually.

### 10.15 `app/core/paths.py`: Android-aware path resolution

Three-tier fallback for `get_recordings_dir()`:
1. `jnius` → `Context.getExternalFilesDir()` (external app-private, no special permission needed after Android 11)
2. Direct POSIX path (works on most devices without jnius)
3. Kivy `App.user_data_dir` (app-private, always available, not visible in file manager)

This was added because the desktop version used a simple `~/` path expansion that does not work on Android.

---

## 11. NDK Notes

### NDK r21e (archived, no longer required)

NDK r21e was downloaded during an earlier phase of development when scipy was still in `requirements`. scipy's build system requires gfortran, which NDK r21e provides but NDK r25b+ removed.

**scipy has since been removed from requirements.** NDK r21e is kept on disk for reference but is not used.

```bash
# Downloaded but not needed:
# cd ~ && wget https://dl.google.com/android/repository/android-ndk-r21e-linux-x86_64.zip
# unzip android-ndk-r21e-linux-x86_64.zip
```

Buildozer downloads NDK r25b (or the version matching its p4a release) automatically on first build.

---

## 12. Common Build Errors and Fixes

| Error message | Cause | Fix |
|---|---|---|
| `externally-managed-environment` | pip refuses global install (Python 3.11+) | Use `pipx install buildozer` |
| `No module named 'distutils'` | Python 3.12 removed distutils | `pipx inject buildozer setuptools` |
| `Cython not found` | p4a needs Cython to compile extensions | `pipx inject buildozer cython` and `sudo apt install cython3` |
| `Cannot perform --user install` | pip inside pipx venv rejects --user flag | Set `VIRTUAL_ENV=1` before buildozer command |
| `storage dir path cannot contain spaces` | p4a internal path handling | Symlink project to `~/otb-mobile`; set `build_dir` in `buildozer.spec` to a no-space Linux path |
| `LEGACY_NDK not found` / gfortran missing | scipy requires NDK r21e | scipy has been removed; this error should not occur |
| `ModuleNotFoundError` on phone | Source files not bundled | Do a full clean build |
| APK installs but crashes immediately | Python error at startup | Run `adb logcat -s python:*` before launch; check traceback |
