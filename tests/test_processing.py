"""Phase 8.2 — processing layer smoke test.

Run from mobile app/:
    python tests/test_processing.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from app.processing.filters import butter_bandpass, notch, rectify
from app.processing.features import rms, mav, integrated_emg

# Simulate 72 channels, 128 samples (one packet at 2000 Hz / 16 packets/sec)
CHANNELS = 72
SAMPLES = 128
FS = 2000

fake_data = np.random.randn(CHANNELS, SAMPLES).astype(np.float32)

# --- Filter pipeline ---
filtered = butter_bandpass(fake_data, 20, 450, FS)
assert filtered.shape == (CHANNELS, SAMPLES), f"Expected {(CHANNELS, SAMPLES)}, got {filtered.shape}"

notched = notch(filtered, 60, FS)
assert notched.shape == (CHANNELS, SAMPLES)

rect = rectify(notched)
assert rect.shape == (CHANNELS, SAMPLES)
assert np.all(rect >= 0), "rectify() should return non-negative values"

# --- Basic features ---
rms_val = rms(rect)
assert rms_val.shape == (CHANNELS, 1), f"Expected ({CHANNELS}, 1), got {rms_val.shape}"

mav_val = mav(rect)
assert mav_val.shape == (CHANNELS, 1)

iemg_val = integrated_emg(rect)
assert iemg_val.shape == (CHANNELS, 1)

print("Processing pipeline OK")
print(f"  Input shape:  {fake_data.shape}")
print(f"  RMS shape:    {rms_val.shape}")
print(f"  MAV shape:    {mav_val.shape}")
print(f"  IEMG shape:   {iemg_val.shape}")
print(f"  RMS[0]:       {rms_val[0, 0]:.6f}")
