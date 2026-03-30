# AD2x32SP Adapter: Dead Channel Investigation Report

**Date:** 2026-03-28
**Branch:** `clinical_feedback`
**Investigator:** Nicholas Santoso

---

## Background

The original ad1x64sp ribbon cable (64-channel, 8×8 grid) broke. The ad2x32sp adapter
(dual 32-channel, two 8×4 arrays) was substituted to interface with the OTB
Sessantaquattro+ biosignal amplifier. The two 32-channel arrays are placed side-by-side
to simulate the original 64-channel 8×8 grid.

**Device configuration:**

| Parameter | Value | Meaning |
|-----------|-------|---------|
| FSAMP | 2 | 2000 Hz |
| NCH | 3 | 64 bioelectrical + 8 AUX = 72 channels |
| MODE | 0 | Monopolar |
| HPF | 1 | High-pass filter active |
| HRES | 0 | 16-bit resolution |

---

## Observed Issue

During press-testing of the 32-channel electrode arrays, channels 5–12 on both arrays
showed **zero signal** on the heatmap regardless of how firmly the electrode was
pressed. Channels 1–4 and 13–32 on both arrays showed clear signal.

---

## Investigation Steps

### Step 1: Confirm It Is Not a Contact / Hardware Fault

The electrode arrays and cables were swapped out for brand-new units. The identical
pattern persisted: channels 5–12 dead on **both** arrays simultaneously. Random hardware
failure cannot produce a perfectly symmetric failure across two independent cables.

### Step 2: Add Debug Logging

`[DEBUG-MAP]` logging was added to `app/data/data_receiver.py` to log:
- All 72 raw channels with RMS above a threshold
- All channels in 0–63 that had zero or near-zero RMS

```
[DEBUG-MAP] ALL72 ACTIVE: ch52=9260, ch64=21301 ...
[DEBUG-MAP] ZERO in 0-63: [0..31, 36, 37, 38, 39, 40, 41, 42, 43]
```

### Step 3: Palm-Press Test — Left Array Only

With a full palm pressed firmly on the left array (connected to IN2, raw channels 32–63):

**Active channels:** 32–35, 44–63
**Zero channels in 32–63:** 36, 37, 38, 39, 40, 41, 42, 43

### Step 4: Palm-Press Test — Both Arrays Simultaneously

With palms pressed on both arrays:

**Right array (IN1, raw 0–31):**
- Active: 0–3, 13–31
- Zero: **4, 5, 6, 7, 8, 9, 10, 11** (offsets 4–11 within block)

**Left array (IN2, raw 32–63):**
- Active: 32–35, 44–63
- Zero: **36, 37, 38, 39, 40, 41, 42, 43** (offsets 4–11 within block)

The dead channels are **identical in offset position** within each 32-channel block,
symmetric across both adapters.

### Step 5: Full Software Audit

Every stage of the data pipeline was reviewed:

| Component | File | Verdict |
|-----------|------|---------|
| Command byte construction | `app/core/device.py` | Correct — matches MATLAB exactly (0x5841) |
| TCP receive & decode | `app/data/data_receiver.py` | Correct — big-endian int16, reshape/transpose matches MATLAB |
| Channel crop | `app/data/data_receiver.py` | Correct — `raw[:64]` keeps EMG, discards AUX |
| Adapter channel map | `app/core/config.py` | Correct — all 64 indices mapped once, no duplicates |
| Filters | `app/processing/` | Not the cause — zeros appear in raw data before any filtering |
| Tests | `tests/` | Pass — decoding, channel ordering verified |

**The debug log captures the raw data before the channel map and before any filtering.
Zeros at this stage mean the device itself is sending zeros.**

### Step 6: OTB Reference Script Test

The official OTB Bioelettronica sample Python script provided with the device was run
with identical settings (FSAMP=2, NCH=3, MODE=0, HPF=1). **The same channels produced
zero signal**, confirming this is not an application-level bug.

### Step 7: Protocol Document Review

The Sessantaquattro+ TCP Communication Protocol v2.1 was reviewed. It confirms:

- NCH=3, MODE=0: streams 72 channels (64 bioelectrical + 8 AUX/accessory)
- No adapter-specific channel layout is documented
- The firmware does not change its data format based on which adapter is connected

---

## Root Cause Conclusion

The Sessantaquattro+ firmware always streams 72 channels regardless of adapter type.
The 64 bioelectrical slots correspond to the device's physical input pins. When the
ad2x32sp adapter is plugged in, its connector physically contacts only **24 of the 32
available device input pins** per connector. The 8 unconnected pins (raw data offsets
4–11 within each 32-channel block) receive no electrode signal. With HPF=1 active,
floating/unconnected inputs produce exactly zero (the HPF removes any DC drift).

This is a **physical characteristic of the ad2x32sp adapter connector pinout**, not a
firmware bug, software bug, or hardware defect.

---

## Impact: Active Channel Count

| Connector | Raw indices | Dead | Active |
|-----------|-------------|------|--------|
| IN1 (right array) | 0–31 | 4–11 | 0–3, 12–31 → **24 channels** |
| IN2 (left array) | 32–63 | 36–43 | 32–35, 44–63 → **24 channels** |
| **Total** | | **16 dead** | **48 active** |

The ad2x32sp adapter provides **48 active channels** from a possible 64. The 16
dead heatmap cells (corresponding to adapter channels 5–12 on each array) will
always display as zero.

---

## Adapter Channel → Logical Grid Mapping

The channel map (hardcoded as the `ad2x32sp` preset in `app/core/config.py`) maps
raw data indices to logical 8×8 grid positions. The 48 working channels map as follows:

**Right adapter (adapter ch 1–32 → logical 1–32, descending):**

| Adapter ch | Raw index | Logical ch | Grid position |
|-----------|-----------|------------|---------------|
| 1–4 | 20–23 | 32–29 | Active |
| 5–12 | 4–11 | 28–21 | **DEAD** |
| 13–32 | 24–31, 0–3, 12–19 | 20–1 | Active |

**Left adapter (adapter ch 1–32 → logical 33–64, descending):**

| Adapter ch | Raw index | Logical ch | Grid position |
|-----------|-----------|------------|---------------|
| 1–4 | 52–55 | 64–61 | Active |
| 5–12 | 36–43 | 60–53 | **DEAD** |
| 13–32 | 56–63, 32–35, 44–51 | 52–33 | Active |

---

## Implemented Mitigations

The following software changes were made to accommodate the 48-channel limitation:

### 1. `DEAD_CHANNELS` constant — `app/core/config.py`
A `frozenset` of 0-based logical channel indices that map to dead raw offsets is
derived automatically from the channel map. For `ad2x32sp` this contains 16 indices.
All other modules consume `CFG.DEAD_CHANNELS` as the single source of truth.

```python
_ADAPTER_DEAD_RAW = {
    'ad2x32sp': frozenset(range(4, 12)) | frozenset(range(36, 44)),
}
DEAD_CHANNELS = frozenset(
    i for i, raw in enumerate(ADAPTER_CHANNEL_MAP) if raw in _dead_raw
)
```

`ADAPTER_HEATMAP_MODE` is also derived — `None` for ad1x64sp, or the value of
`"heatmap_mode"` in config.json for ad2x32sp (`"removed"` / `"raw"` / `"demo"`).

### 2. Heatmap dead-cell rendering — `app/ui/widgets/heatmap_widget.py`
Three rendering modes are available via `config.json ["adapter"]["heatmap_mode"]`:

| Mode | Appearance | Use case |
|------|-----------|----------|
| `removed` | Dark purple-grey + × + em-dash label | Clinical — dead cells clearly marked |
| `raw` | Live cell at value 0 (always cold) | Transparent — no visual distinction |
| `demo` | Coloured at mean of active channels | Demonstrations — visually complete grid |

None of these modes are visible when `ADAPTER_TYPE` is `ad1x64sp` — `ADAPTER_HEATMAP_MODE`
is `None` and the dead-channel branches in `_redraw_colors` are never reached.

### 3. Calibration exclusion — `app/ui/widgets/calibration_popup.py`
- `_compute_rms()` zeros dead channels in the returned array so baseline, MVC, and
  threshold values are not influenced by always-zero channels.
- `compute_concentration()` builds an active-channel mask and operates only on the
  48 working channels when evaluating spatial concentration.

### 4. Recording metadata — `app/managers/recording_manager.py`
The JSON sidecar now includes:
```json
"adapter_type": "ad2x32sp",
"dead_channels": [20, 21, 22, 23, 24, 25, 26, 27, 52, 53, 54, 55, 56, 57, 58, 59],
"active_channel_count": 48
```

### 5. Pipeline dead-channel zeroing — `app/data/data_receiver.py`
After the final filter pipeline, dead channel rows are clamped to zero to prevent
IIR filter transients on always-zero inputs from producing small non-zero artefacts.
The `[DEBUG-MAP]` logging was removed.

---

## Remaining Limitation

The 16 dead heatmap cells cannot be recovered in software. If full 64-channel coverage
is required, replace the ad2x32sp with an ad1x64sp ribbon cable and set
`"type": "ad1x64sp"` in `config.json`.

---

## Configuration State (as of this report)

**`app/core/config.json`:**
```json
"adapter": {
  "type": "ad2x32sp",
  "channel_map": null
}
```

**`app/core/config.py` — built-in preset:**
```python
'ad2x32sp': [
    19, 18, 17, 16, 15, 14, 13, 12,
     3,  2,  1,  0, 31, 30, 29, 28,
    27, 26, 25, 24, 11, 10,  9,  8,
     7,  6,  5,  4, 23, 22, 21, 20,
    51, 50, 49, 48, 47, 46, 45, 44,
    35, 34, 33, 32, 63, 62, 61, 60,
    59, 58, 57, 56, 43, 42, 41, 40,
    39, 38, 37, 36, 55, 54, 53, 52,
]
```
