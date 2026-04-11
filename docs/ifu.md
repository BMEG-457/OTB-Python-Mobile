# Instructions for Use (IFU)

**OTB EMG Application — HD-sEMG Acquisition System**
**Device:** OTB Sessantaquattro+ with HD-sEMG Textile Electrode Array
**Target Muscle:** Tibialis Anterior (TA)
**Intended User:** Trained researchers and clinicians familiar with surface electromyography. Not intended for unsupervised use by laypersons.
**Training Requirement:** Operators should be familiar with surface EMG electrode placement per SENIAM guidelines and with the OT Bioelettronica Sessantaquattro+ user manual prior to use. New operators should complete at least one supervised practice session before recording study data.

---

## 0. Background and Key Terms

Operators new to surface electromyography should read this section before proceeding. Definitions are provided in plain language so a participant or assistant unfamiliar with EMG can follow the rest of the document.

- **Surface electromyography (sEMG):** A non-invasive technique for measuring the electrical activity produced by skeletal muscles using electrodes placed on the skin. The signal reflects how strongly and how often muscle fibers are being activated.
- **HD-sEMG (high-density sEMG):** A variant of sEMG that uses a closely spaced grid of many electrodes (in this system, sixty-four arranged in an eight by eight pattern) instead of two or three. This allows the activity of the muscle to be mapped spatially across its surface.
- **Tibialis anterior (TA):** The long muscle on the front of the shin. It lifts the foot upward at the ankle and is the target muscle for this system.
- **Dorsiflexion:** The motion of pulling the toes and foot upward toward the shin. This action contracts the tibialis anterior.
- **Plantar flexion:** The opposite motion: pointing the toes downward, away from the shin. This contracts the calf muscles (gastrocnemius and soleus), not the tibialis anterior. It is used in this system to check for crosstalk.
- **Crosstalk:** Unwanted signal picked up from a nearby muscle. If the electrode array picks up signal from the calf when the participant points their toes downward, those channels are flagged as contaminated.
- **MVC (maximum voluntary contraction):** The strongest contraction a participant can produce voluntarily. Other contractions are expressed as a percentage of MVC (for example, fifty percent MVC).
- **RMS (root mean square):** A mathematical measure of the overall amplitude of the EMG signal over a short window of time. Higher RMS generally means stronger muscle activation.
- **Median frequency (MF):** The frequency that splits the EMG signal's frequency content in half. As a muscle fatigues, the median frequency tends to decrease, which is why it is used as a fatigue indicator.
- **TKEO (Teager-Kaiser Energy Operator):** A signal processing method used to detect the precise moment a muscle turns on or off.
- **Calibration:** A short routine performed at the start of each session in which the participant rests, then performs a maximum contraction, then a verification contraction. This sets the reference values used by the rest of the session.
- **Channel:** One electrode contact. This system has sixty-four channels arranged in an eight by eight grid; four corner channels are excluded by design due to retention tab placement, leaving sixty active.

---

## 1. Electrode Placement (SENIAM Protocol)

### Anatomical Landmarks
- **Fibula head:** Bony prominence on the lateral side of the knee
- **Medial malleolus:** Bony prominence on the inner ankle

### Electrode Location
Place the HD-sEMG electrode array at **one third of the distance** from the tip of the fibula to the tip of the medial malleolus, on the **anterolateral surface** of the lower leg over the tibialis anterior muscle belly.

### Electrode Orientation
Align the electrode array **parallel to the muscle fibers**, along the line between the fibula head and the medial malleolus. The long axis of the grid should follow the proximal-to-distal direction of the muscle fibers.

### HD-sEMG Array Positioning
1. Identify the TA muscle belly by asking the participant to dorsiflex the ankle (pull toes toward shin). The muscle belly should be palpable.
2. Center the eight by eight electrode grid over the most prominent part of the muscle belly.
3. Secure the electrode sleeve with the **hook-and-loop fasteners** using even, moderate pressure. The fit should be firm enough for consistent skin contact but not so tight as to restrict blood flow.
4. After running calibration (see Section 2), verify that the calibration check passes and that most channels are active. Four corner channels are excluded by design; additional inactive channels indicate poor skin contact and the array should be repositioned.

### Reference Electrode
Place the reference electrode on an electrically neutral site (e.g., tibial tuberosity) per the Sessantaquattro+ device manual.

---

## 2. Session Duration

### Recommended Session Parameters
- **Maximum continuous session:** sixty minutes
- **Rest break:** at least five minutes between recording blocks
- **Typical MVC protocol:** three to five seconds of maximal contraction, repeated three times with sixty-second rest intervals
- **Typical fatigue protocol:** sustained contraction at thirty to fifty percent MVC until task failure or a predefined duration

### Session Workflow
1. Apply electrode array and verify placement (see Section 1). Tap **Guide** in the app for a SENIAM placement reference.
2. Connect to device via the app (tap **Stream**).
3. Run calibration (tap **Calibrate**):
   - Phase 1: Rest baseline (3 s). Remain relaxed.
   - Phase 2: MVC (3 s). Maximum voluntary contraction.
   - Phase 3: Verification (3 s). Dorsiflexion to verify spatial concentration (PASS/WARNING displayed).
4. Optionally run crosstalk verification (tap **Crosstalk**). Perform plantar flexion; flagged channels indicate possible crosstalk from adjacent muscles.
5. Tap **Record**, enter session metadata (date, subject ID, muscle group, exercise type, notes), then tap **Start Recording**.
6. Perform the recording protocol.
7. Tap **Record** again to stop. CSV, metadata sidecar, and session summary are saved automatically.

### Prolonged Use
- **CAUTION:** If the participant reports discomfort, numbness, or skin irritation, stop the session immediately and remove the electrode array.
- For multi-session studies, allow at least twenty-four hours between sessions on the same skin site to prevent irritation.

---

## 3. Skin Care and Safety

### Pre-Session Skin Preparation
1. **Clean** the skin over the TA with an alcohol wipe or mild soap and water.
2. **Allow the skin to dry** completely before applying the electrode array (at least sixty seconds).
3. **Remove excess hair** from the electrode site if necessary using a disposable razor or electric trimmer. Do not use depilatory creams.
4. **Do not apply** lotions, oils, or moisturizers to the electrode site before the session.

### Electrode Array Care
- The HD-sEMG electrode array uses **silver-compound fabric electrodes**. These do not require conductive gel.
- After each session, wipe the electrode contacts with a damp cloth. Do not submerge the array in water.
- Inspect the electrode array for damaged or discolored contacts before each session. Replace if contacts are visibly degraded.

### Skin Safety Warnings
- **WARNING:** Do not use on broken, irritated, or infected skin.
- **WARNING:** Do not use on participants with known silver allergies.
- **WARNING:** Monitor for redness, rash, or irritation during and after use. Discontinue if a skin reaction occurs.
- **WARNING:** Do not use electrode arrays that show visible damage, fraying, or corroded contacts.
- This device is intended for **surface EMG only**. It is non-invasive and does not deliver electrical stimulation.

---

## 4. Pre-Session Battery Check

Battery state is read by the app from the Sessantaquattro+ device's web configuration page. The app retrieves the page over the device WiFi network and parses the battery percentage. The same value can be checked manually in a browser.

### Checking Battery Level
1. Power on the Sessantaquattro+ and connect your mobile device or laptop to the device WiFi network.
2. Open the app and observe the battery indicator in the top bar of the Live Data screen.
3. To verify manually, open a web browser and navigate to the device's configuration page (refer to OTB Sessantaquattro+ device manual for the URL). The battery percentage is displayed on this page.

### Battery Requirements
- **Minimum recommended charge:** twenty percent before starting a session.
- The app displays a **color-coded battery indicator**:
  - **Green:** greater than fifty percent. Adequate for extended sessions.
  - **Orange:** twenty to fifty percent. Adequate for short sessions; consider charging soon.
  - **Red:** less than twenty percent. Charge before starting a new session.
- A fully charged Sessantaquattro+ provides approximately six to eight hours of continuous streaming (refer to OTB device specifications for exact values).

### Charging
- Use only the charger supplied with the Sessantaquattro+ device.
- **CAUTION:** Do not record while charging. Mains coupling may introduce 50/60 Hz power line noise into the EMG signal.

---

## 5. End-of-Life Disposal

### Electronic Components (Sessantaquattro+ Device)
- Dispose of the Sessantaquattro+ device in accordance with local regulations for **Waste Electrical and Electronic Equipment (WEEE)**.
- Do not dispose of the device in general household waste.
- Contact your institution's waste management department or local electronics recycling facility for proper disposal.

### Electrode Array (Textile Component)
- The HD-sEMG electrode sleeve contains silver-compound conductive fabric.
- Dispose of used electrode arrays according to your institution's policy for **biomedical waste** or **electronic textile waste**, as applicable.
- If the electrode array has been in contact with bodily fluids or compromised skin, treat it as biomedical waste per local regulations.

### Software and Data
- Before disposing of the mobile device or transferring ownership, ensure all recorded EMG data files are securely deleted or transferred.
- Recorded data is stored locally on the device in the application's data directory. Uninstalling the app removes the associated data.

---

## 6. App Navigation and Features

### Home Screen
When the app launches, the home screen presents three modes:
- **Live Data Viewing:** real-time EMG acquisition and display.
- **Data Analysis:** offline review and feature analysis of saved recordings.
- **Session History:** longitudinal trend chart across past sessions.

### Live Data Mode
Tapping **Live Data Viewing** prompts a mode selection:
- **Basic (Clinical):** simplified view showing only the Auto MAV signal. View mode cycling, time window, and channel selector controls are hidden.
- **Advanced (Researcher):** full controls exposed, including multiple view modes and the channel selector.

#### Top Bar Controls

| Button     | Function                                                          |
|------------|-------------------------------------------------------------------|
| Back       | Return to home screen                                             |
| Calibrate  | Run the three-phase calibration (enabled after streaming starts)  |
| Guide      | Open SENIAM electrode placement reference popup                   |
| Crosstalk  | Run crosstalk verification (enabled after calibration)            |
| Stream     | Connect to device and start/stop data streaming                   |
| Record     | Start/stop a recording (enabled after calibration)                |

A battery indicator and contraction indicator are shown in the top bar. A red disconnect banner appears if the device connection is lost.

#### Tabs and View Modes (Advanced Mode)
- **EMG Plot tab:** waveform display of the current view mode.
- **Heatmap tab:** eight by eight spatial RMS heatmap normalized to MVC, updated in real time.

In Advanced mode, the **View** button cycles through:
- **Single Ch1:** raw waveform for a single selectable channel.
- **Auto MAV:** mean absolute value envelope of the highest-activity channel.
- **Rows (8):** mean waveform across each of the eight electrode rows.
- **Cols (8):** mean waveform across each of the eight electrode columns.
- **Clusters:** mean waveform of two by two electrode clusters (sixteen traces in a four by four arrangement).

The **Time** button cycles the visible time window duration. In Single Ch1 mode, left and right channel selector arrows appear to step through channels.

---

## 7. Data Analysis Mode

Used for offline review of saved recordings.

1. Tap **Load File 1** and navigate the file browser to select a recording CSV.
2. Optionally tap **Load File 2** for a second recording (required for bilateral symmetry analysis).
3. Enter the channel number to analyse in the **Channel** field.
4. Tap **Plot Data** to open a waveform plot popup for the loaded file.
5. Run any of the six feature analyses using the analysis buttons.

| Analysis            | Description                                                                                                                              |
|---------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| Activation Timing   | TKEO-based onset and offset detection                                                                                                    |
| Burst Duration      | Duration of each detected muscle burst                                                                                                   |
| Fatigue             | RMS and median frequency trends over time. Thresholds are configurable per participant and should be calibrated, not treated as universal cutoffs |
| Bilateral Symmetry  | Amplitude symmetry between File 1 and File 2                                                                                             |
| Centroid Shift      | Shift in spatial activation centroid across the HD-sEMG grid                                                                             |
| Spatial Uniformity  | Non-uniformity index across the eight by eight electrode array                                                                           |

Results appear in the scrollable text area. Tap **Export** to save results as a text file.

---

## 8. Session History Mode

Displays a longitudinal trend chart and a list of all saved sessions.

- Use the **Subject**, **Muscle Group**, and **Exercise Type** filters to narrow the session list.
- The trend chart plots one of three metrics over time. Switch between **Peak RMS**, **Mean MF** (median frequency), and **Contractions** using the metric selector buttons.
- Tap any session card in the list to view its stored summary values.

---

## Revision History

| Version | Date       | Description                                                                                                                             |
|---------|------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| 1.0     | 2026-03-23 | Initial release                                                                                                                         |
| 1.1     | 2026-03-24 | Updated session workflow for 3-phase calibration, crosstalk verification, metadata entry, and SENIAM guide                              |
| 1.2     | 2026-04-11 | Added intended user, training requirement, and background/key terms section. Added software IFU sections (App Navigation, Data Analysis, Session History). Reworded battery check to reflect web config + parsing implementation. Reworded array positioning verification to reference the calibration check. Editorial pass: removed em dashes, "subject" → "participant" in safety contexts, spelled out numbers below ten, "Velcro" → "hook-and-loop fasteners". |