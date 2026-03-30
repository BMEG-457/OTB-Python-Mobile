# OTB EMG Mobile App — User Guide

This guide covers everything needed to operate the app from installation through recording and post-session analysis.

---

## What the App Does

The app has three independent modes:

- **Live Data** — connect to the Sessantaquattro+ device over WiFi, stream real-time EMG signals, calibrate against baseline and MVC with verification, and record sessions to CSV with metadata. Available in **Basic (Clinical)** mode for streamlined operation or **Advanced (Researcher)** mode with full controls.
- **Data Analysis** — load previously recorded CSV files and run feature analyses offline, without any device present.
- **Session History** — view longitudinal trends across past recording sessions, filter by subject or muscle group, and track metrics (peak RMS, median frequency, contraction count) over time.

EMG (electromyography) measures the electrical activity produced by skeletal muscles during contraction. The Sessantaquattro+ captures HD-sEMG: a high-density 8×8 grid of 64 surface electrodes that provides spatial muscle activation maps.

---

## Hardware Requirements

- Sessantaquattro+ HD-sEMG device (OTBioelettronica)
- Ribbon cable adapter: **ad1x64sp** (64-ch, 8×8 grid, all channels active) or **ad2x32sp** (dual 32-ch, 8×8 grid, 48 of 64 channels active)
- Electrode array(s) matched to the adapter
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

The **Selection Screen** appears on launch. Tap one of the three buttons:

| Button | Mode |
|---|---|
| **Live Data Viewing** | Real-time streaming, calibration, recording. Opens a popup to choose **Basic (Clinical)** or **Advanced (Researcher)** mode. |
| **Data Analysis** | Offline analysis of saved CSV files |
| **Session History** | Longitudinal session tracking and trend visualization |

**Basic vs. Advanced mode:** Basic mode hides the channel selector, time window, and view mode controls — ideal for clinical workflows where only the auto-MAV envelope is needed. Advanced mode exposes all controls (view modes, channel selection, time window cycling).

Tap **Back** on any screen to return to the selection screen.

---

## Live Data Mode

### 1. Connect to the Device Network

Before pressing Stream, connect the phone to the Sessantaquattro+ WiFi network (the device broadcasts its own SSID). The app checks that the phone's IP starts with `192.168.1` before attempting to connect. If the network check fails, the status bar shows "No device network".

### 2. Start Streaming

Tap **Stream**. The app opens a TCP server on port 45454 and waits up to 15 seconds for the device to connect. Once connected:
- The button changes color to indicate active streaming
- The **Calibrate** button becomes enabled
- Live EMG data appears in the plot or heatmap

To stop streaming, tap **Stream** again.

### 3. Calibration

Calibration establishes the resting baseline, maximum voluntary contraction (MVC) reference values, and verifies electrode placement quality. These are needed for normalized heatmap display and contraction detection.

**Procedure:**
1. Tap **Calibrate** (streaming must be active).
2. **Phase 1 — Rest** (3 s): A popup appears. Remain relaxed — the app collects resting EMG.
3. **Phase 2 — MVC** (3 s): When prompted, perform a maximum voluntary contraction and hold.
4. **Phase 3 — Verification** (3 s): When prompted, perform a dorsiflexion. The app checks spatial concentration of activation to verify electrode placement.
   - **PASS** (green) — activation is spatially concentrated, indicating good electrode placement.
   - **WARNING** (orange) — activation is diffuse, suggesting the electrode array may need repositioning.
5. The popup dismisses automatically. The **Record** button becomes enabled.

Calibration results are not saved to disk on the mobile app. They are held in memory for the current session. Repeat calibration after restarting streaming.

**Electrode Placement Guide:** Tap the **Guide** button to open a scrollable SENIAM electrode placement reference for the tibialis anterior.

**Crosstalk Verification:** After calibration, tap the **Crosstalk** button to verify that the TA electrode array does not pick up gastrocnemius activity. The popup prompts you to perform plantar flexion (push toes down) — channels that exceed the crosstalk threshold are flagged.

**Contraction Indicator:**
After calibration, the "Contraction" label in the top bar changes color in real-time:
- **Green** — channel 1 RMS exceeds the threshold (contraction detected)
- **Red** — channel 1 RMS is below threshold (no contraction)

**Real-time Metrics:**
After calibration, the top bar also displays live RMS and median frequency for the monitored channel. Fatigue flags appear if RMS drops or median frequency declines beyond configured thresholds.

### 4. View Modes (EMG Plot Tab)

In **Advanced mode**, tap **View** in the tab bar to cycle through display modes:

| Mode | Tracks | Description |
|---|---|---|
| Auto MAV | 1 | Automatic channel selection — displays MAV envelope of the highest-activity channel |
| Single Ch1 | 1 | Single channel rolling waveform. Enter a channel number (1–64) in the Ch: field. |
| Rows (8) | 8 | Per-row mean across all 8 columns of the electrode grid |
| Cols (8) | 8 | Per-column mean across all 8 rows |
| Clusters | 16 | Mean of 2×2 electrode sub-blocks (4×4 arrangement) |

In **Basic mode**, only the Auto MAV view is available. The view and channel selection controls are hidden.

Tap **Time** to cycle the plot time window: 2 s, 4 s, or 8 s (Advanced mode only).

### 5. Heatmap Tab

Tap **Heatmap** to switch to the 8×8 spatial activation map. Each cell represents one electrode and displays its channel number (1–64). Grid lines separate the rows and columns. Colors range from dark gray (no activation) to bright green (activation at or above MVC). Before calibration, the heatmap is inactive and displays no color. After calibration, colors are scaled relative to the calibration MVC values.

A white ellipse highlight can mark the currently selected or auto-detected channel.

Electrode-to-grid mapping: column-major, bottom-left = channel 0. Channel index = col × 8 + (7 − row).

**Dead channels (ad2x32sp adapter only):** When using the dual 32-channel adapter, 16 of the 64 grid cells are permanently inactive — the adapter connector does not make contact with those device input pins. Dead channels are excluded from calibration calculations regardless of display mode. The appearance of dead cells on the heatmap depends on the `heatmap_mode` setting in `config.json`:

| Mode | Dead cell appearance |
|------|----------------------|
| `removed` (default) | Dark purple-grey fill, × overlay, em-dash (—) label — clearly marked as inactive |
| `raw` | Rendered like a live cell at value 0 — always dark/cold, normal channel number label |
| `demo` | Coloured at the mean activation of all working channels — visually fills in the gaps for demonstrations |

This is a hardware limitation of the ad2x32sp adapter; switching to the ad1x64sp cable restores all 64 channels.

### 6. Battery Status

The **Battery** label in the top bar shows the device battery percentage, queried via HTTP every 30 seconds. Colors: green (>50%), orange (20–50%), red (≤20%). "--" means no battery response was received.

### 7. Recording

Recording requires calibration to be complete first.

1. Tap **Record** — a metadata form appears. Enter the session date, subject ID, muscle group, exercise type, and optional notes. Tap **Start Recording** to begin.
2. The button turns red and status shows "Recording...". An autosave file is written in real time for crash recovery.
3. Perform the desired activity.
4. Tap **Record** again to stop — the app saves a timestamped CSV and a JSON metadata sidecar in the background. Session summary metrics are appended to the longitudinal history. The button shows "Saving..." and re-enables when complete.

**CSV format:** one row per sample; columns: `Timestamp, Channel_1, Channel_2, ..., Channel_64`. Only the 64 HD-EMG channels are saved (auxiliary channels 65–72 are excluded). Timestamps are seconds elapsed since the start of the recording.

**Metadata sidecar:** A `<recording_name>_meta.json` file is saved alongside each CSV, containing the entered metadata, computed summary statistics (RMS, MAV, median frequency, fatigue flags, contraction count), and adapter information (`adapter_type`, `dead_channels`, `active_channel_count`). When using the ad2x32sp adapter, `active_channel_count` will be 48 and `dead_channels` will list the 16 logical channel indices (0-based) that are permanently inactive.

**Crash recovery:** If the app crashes during recording, the autosave file is detected on next launch and automatically recovered.

**Storage location:** `Android > data > org.bmeg457.otbemgapp > files > OTB_EMG > recordings`

**Maximum recording length:** 1,000,000 samples (~500 seconds at 2000 Hz). Recording stops automatically if this limit is reached.

### 8. Safety Alerts

The app monitors signal quality and connection health in real time during streaming:

- **Clipping detection** — if any channel's signal is saturating the ADC (samples at the rail value), a warning appears. This indicates the signal amplitude is too high; check electrode contact or reduce gain.
- **Disconnect warning** — if no data packets arrive for more than 5 seconds, a disconnect warning appears. Check device power and WiFi connection.
- **Latency warning** — if processing latency exceeds 100 ms, a warning appears. This may indicate the device is under heavy load.

---

## Session History Mode

Session History displays longitudinal trends across all recorded sessions.

1. Tap **Session History** on the selection screen.
2. The screen loads all saved session summaries.
3. Use the **Subject** and **Muscle** spinners at the top to filter sessions.
4. The trend chart shows the selected metric across sessions. Tap the metric buttons below the chart to switch between:
   - **Peak RMS** — maximum RMS value across channels
   - **Median Freq** — median frequency of the best channel
   - **Contractions** — number of detected contractions
5. Below the chart, a scrollable list shows individual session cards with date, muscle group, exercise type, subject ID, duration, and metrics.

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
| Heatmap is dark / no color | Not calibrated | Perform calibration first; heatmap is inactive pre-calibration |
| Clipping warning appears | Signal amplitude saturating ADC | Check electrode contact; ensure array is properly secured |
| Disconnect warning appears | No data for >5 seconds | Check device power and WiFi; move closer to device |
| Verification phase shows WARNING | Diffuse activation during dorsiflexion | Reposition electrode array over muscle belly; re-run calibration |
| Crosstalk check shows WARNING | TA array picking up gastrocnemius | Reposition array; ensure it is centered over TA, not overlapping adjacent muscles |
| Recordings not visible in file manager | Storage permission denied | Settings > Apps > OTB EMG App > Permissions > Storage > Allow, then restart app |
| "Max samples reached" during recording | Recording exceeded 1,000,000 samples | File is saved; start a new recording |
| Autosave recovery message on launch | Previous session crashed during recording | The recovered file is saved; check recordings folder |
| Analysis returns no result | Recording too short or corrupted | Recording must have at least 30 valid samples per channel |
| Bilateral Symmetry file browser doesn't open | File 1 not loaded | Load File 1 first, then press Bilateral Symmetry |
| Session History is empty | No recordings with metadata saved yet | Record a session with metadata to populate history |
| App crashes on launch | Storage permission not yet granted | Grant permission and restart |
| 16 heatmap cells show × and never respond | Using ad2x32sp adapter | Expected — those 16 device input pins are not contacted by the adapter; 48 of 64 channels are active |
| Calibration threshold seems too low | Dead channels pulling down MVC estimate | Dead channels are excluded from calibration automatically; ensure `"type": "ad2x32sp"` is set in config.json |
