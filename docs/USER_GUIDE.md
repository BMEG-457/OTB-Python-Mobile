# OTB EMG Mobile App — User Guide

This guide covers everything needed to operate the app from installation through recording and post-session analysis.

---

## What the App Does

The app has two independent modes:

- **Live Data** — connect to the Sessantaquattro+ device over WiFi, stream real-time EMG signals, calibrate against baseline and MVC, and record sessions to CSV.
- **Data Analysis** — load previously recorded CSV files and run feature analyses offline, without any device present.

EMG (electromyography) measures the electrical activity produced by skeletal muscles during contraction. The Sessantaquattro+ captures HD-sEMG: a high-density 8×8 grid of 64 surface electrodes that provides spatial muscle activation maps.

---

## Hardware Requirements

- Sessantaquattro+ HD-sEMG device (OTBioelettronica)
- 8×8 electrode array connected to the device
- Android phone (Android 5.0 / API 21 or newer; landscape orientation)
- WiFi network broadcast by the device (SSID typically "Sessantaquattro+")

---

## Installation

1. Enable Developer Options on the phone: **Settings > About Phone > tap Build Number 7 times**.
2. Enable **USB Debugging** in Developer Options.
3. Connect phone via USB to the computer.
4. From PowerShell:
   ```powershell
   cd C:\platform-tools
   .\adb install -r "path\to\otbemgapp-0.1-arm64-v8a_armeabi-v7a-debug.apk"
   ```
5. On first launch the app will request storage permission — tap **Allow** and restart the app.

Recordings are saved to: **Phone storage > Android > data > org.bmeg457.otbemgapp > files > OTB_EMG > recordings**

---

## Starting the App

The **Selection Screen** appears on launch. Tap either button:

| Button | Mode |
|---|---|
| **Live Data Viewing** | Real-time streaming, calibration, recording |
| **Data Analysis** | Offline analysis of saved CSV files |

Tap **Back** on any screen to return to the selection screen.

---

## Live Data Mode

### 1. Connect to the Device Network

Before pressing Stream, connect the phone to the Sessantaquattro+ WiFi network (the device broadcasts its own SSID). The app checks that the phone's IP starts with `192.168.1` before attempting to connect. If the network check fails, the status bar shows "No device network".

### 2. Start Streaming

Tap **Start Stream**. The app opens a TCP server on port 45454 and waits up to 15 seconds for the device to connect. Once connected:
- The button changes to **Stop Stream**
- The **Calibrate** button becomes enabled
- Live EMG data appears in the plot or heatmap

To stop streaming, tap **Stop Stream**.

### 3. Calibration

Calibration establishes the resting baseline and maximum voluntary contraction (MVC) reference values needed for normalized heatmap display and contraction detection.

**Procedure:**
1. Tap **Calibrate** (streaming must be active).
2. A popup appears. Remain relaxed — the app collects 3 seconds of resting EMG.
3. When prompted, perform a maximum voluntary contraction and hold for 3 seconds.
4. The popup dismisses automatically. The **Start Record** button becomes enabled.

Calibration results are not saved to disk on the mobile app. They are held in memory for the current session. Repeat calibration after restarting streaming.

**Contraction Indicator:**
After calibration, the indicator in the top bar updates in real-time:
- **Contraction** (green) — channel 1 RMS exceeds the threshold
- **No Contraction** (red) — channel 1 RMS is below threshold

### 4. View Modes (EMG Plot Tab)

Tap **View** in the tab bar to cycle through display modes:

| Mode | Tracks | Description |
|---|---|---|
| Single Ch1 | 1 | Single channel rolling waveform. Enter a channel number (1–64) in the Ch: field. |
| Rows (8) | 8 | Per-row mean across all 8 columns of the electrode grid |
| Cols (8) | 8 | Per-column mean across all 8 rows |
| Clusters | 16 | Mean of 2×2 electrode sub-blocks (4×4 arrangement) |

Tap **Time** to cycle the plot time window: 2 s, 4 s, or 8 s.

### 5. Heatmap Tab

Tap **Heatmap** to switch to the 8×8 spatial activation map. Each cell represents one electrode. Colors range from dark gray (no activation) to bright green (activation at or above MVC). Before calibration, the heatmap auto-scales to the current peak RMS across all channels.

Electrode-to-grid mapping: column-major, bottom-left = channel 0. Channel index = col × 8 + (7 − row).

### 6. Battery Status

The **Battery** label in the top bar shows the device battery percentage, queried via HTTP every 30 seconds. Colors: green (>50%), orange (20–50%), red (≤20%). "--" means no battery response was received.

### 7. Recording

Recording requires calibration to be complete first.

1. Tap **Start Record** — the button turns orange and status shows "Recording...".
2. Perform the desired activity.
3. Tap **Stop Record** — the app saves a timestamped CSV in the background. The button shows "Saving..." and re-enables when complete.

**CSV format:** one row per sample; columns: `Timestamp, Channel_1, Channel_2, ..., Channel_64`. Only the 64 HD-EMG channels are saved (auxiliary channels 65–72 are excluded). Timestamps are seconds elapsed since the start of the recording.

**Storage location:** `Android > data > org.bmeg457.otbemgapp > files > OTB_EMG > recordings`

**Maximum recording length:** 1,000,000 samples (~500 seconds at 2000 Hz). Recording stops automatically if this limit is reached.

---

## Data Analysis Mode

Data Analysis is independent of the device. No WiFi or connection is required.

### Loading Files

1. Tap **Load File 1** — a navigable directory browser opens starting from the recordings folder.
2. Tap a folder name to enter it; tap a CSV filename to load it. The file loads in the background; status updates when complete.
3. Select the channel to analyse using the **Channel:** number input (default: channel 1).
4. For bilateral symmetry analysis, load File 1 first, then press **Bilateral Symmetry** — the file browser opens automatically to select File 2.

### Running Analyses

Each analysis button runs in a background thread. Results appear as scrollable text when complete.

| Button | Inputs | Description |
|---|---|---|
| **Activation Timing** | File 1, selected channel | Detects muscle activation onset times using the Teager-Kaiser Energy Operator |
| **Burst Duration** | File 1, selected channel | Measures the duration of each EMG burst |
| **Fatigue** | File 1, selected channel | Detects fatigue from RMS increase and median frequency decline over time |
| **Bilateral Symmetry** | File 1 + File 2, selected channel | Computes symmetry index between two limbs over sliding windows |
| **Centroid Shift** | File 1 (64 ch) | Tracks the weighted activation centroid of the 8×8 grid over time |
| **Spatial Uniformity** | File 1 (64 ch) | Reports coefficient of variation, Shannon entropy, and activation fraction |

Centroid Shift and Spatial Uniformity require at least 64 channels. Files with more than 64 channels use the first 64.

### Viewing the Raw Signal

Tap **Plot Data** to open the Analysis Plot Screen, which shows the loaded recording as a scrollable static waveform. Use the on-screen controls to select a channel, apply bandpass, notch, rectify, or envelope filters, and scrub through the recording.

### Exporting Results

Tap **Export** to save all analysis results (TKEO, burst, fatigue, bilateral, centroid, spatial) that have been run in the current session to a CSV file. The file is saved in the same directory as the source recording, named `<source_filename>_export.csv`.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| "No device network" on Stream press | Phone not on Sessantaquattro+ WiFi | Connect phone to device SSID before streaming |
| "Device did not connect within 15 seconds" | Device not powered on or not in pairing mode | Power on device; retry Stream |
| Stream starts but no data appears | WiFi interference or packet loss | Move closer to device; retry |
| Heatmap is dark / no color | Not calibrated | Perform calibration first |
| Recordings not visible in file manager | Storage permission denied | Settings > Apps > OTB EMG App > Permissions > Storage > Allow, then restart app |
| "Max samples reached" during recording | Recording exceeded 1,000,000 samples | File is saved; start a new recording |
| Analysis returns no result | Recording too short or corrupted | Recording must have at least 30 valid samples per channel |
| Bilateral Symmetry file browser doesn't open | File 1 not loaded | Load File 1 first, then press Bilateral Symmetry |
| App crashes on launch | Storage permission not yet granted | Grant permission and restart |
