import numpy as np
from app.processing.filters import butter_bandpass, notch, rectify
from app.processing.features import rms, mav

# Simulate 72 channels, 128 samples at 2048 Hz
fake_data = np.random.randn(72, 128).astype(np.float32)

filtered = butter_bandpass(fake_data, 20, 450, 2048)
notched = notch(filtered, 60, 2048)
rect = rectify(notched)
rms_val = rms(rect)

print("Processing pipeline OK")
print(f"RMS shape: {rms_val.shape}")  # should be (72, 1)
