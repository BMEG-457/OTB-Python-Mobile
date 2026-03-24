"""Crosstalk verification popup.

Instructs the subject to perform plantar flexion (push toes down) while
monitoring the TA electrode array. If significant activation appears on
the TA channels during plantar flexion, this indicates possible crosstalk
from the gastrocnemius.

Requires baseline_rms from a prior calibration rest phase.
"""

import time
import numpy as np
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.metrics import sp
from app.core import config as CFG


class CrosstalkVerificationPopup(Popup):
    """Crosstalk verification: plantar flexion test.

    Args:
        baseline_rms: np.ndarray (n_channels,) from calibration rest phase.
        on_complete: callable(passed: bool, flagged_channels: list).
        on_sample_connect: callable(callback) — registers sample callback.
        on_sample_disconnect: callable(callback) — unregisters sample callback.
    """

    def __init__(self, baseline_rms, on_complete,
                 on_sample_connect, on_sample_disconnect, **kwargs):
        super().__init__(**kwargs)
        self.title = 'Crosstalk Verification'
        self.size_hint = (0.85, 0.55)
        self.auto_dismiss = False

        self._baseline_rms = baseline_rms
        self._on_complete = on_complete
        self._on_sample_connect = on_sample_connect
        self._on_sample_disconnect = on_sample_disconnect
        self._samples = []
        self._callback = None
        self._start_time = None
        self._tick_event = None

        layout = BoxLayout(orientation='vertical', padding=16, spacing=12)
        self.status_label = Label(
            text='Crosstalk Test', font_size=sp(20),
            size_hint=(1, 0.3), halign='center',
        )
        self.instruction_label = Label(
            text='', font_size=sp(16),
            color=(0.8, 0.8, 0.8, 1), size_hint=(1, 0.3),
        )
        self.progress = ProgressBar(max=100, value=0, size_hint=(1, 0.2))
        self.result_label = Label(
            text='', font_size=sp(16), size_hint=(1, 0.2),
        )
        layout.add_widget(self.status_label)
        layout.add_widget(self.instruction_label)
        layout.add_widget(self.progress)
        layout.add_widget(self.result_label)
        self.content = layout

    def start(self):
        """Open popup and begin the plantar flexion test."""
        self.open()
        self.instruction_label.text = 'Perform PLANTAR FLEXION (push toes down)...'
        self._callback = lambda stage, data: self._collect(stage, data)
        self._on_sample_connect(self._callback)
        self._start_time = time.time()
        self._tick_event = Clock.schedule_interval(self._tick, 1.0 / 30)

    def _collect(self, stage, data):
        if stage == 'raw':
            self._samples.append(data.copy())

    def _tick(self, dt):
        elapsed = time.time() - self._start_time
        self.progress.value = min(100, 100 * elapsed / CFG.CROSSTALK_DURATION)
        if elapsed >= CFG.CROSSTALK_DURATION:
            self._tick_event.cancel()
            self._on_sample_disconnect(self._callback)
            self._evaluate()

    def _evaluate(self):
        if not self._samples:
            self.result_label.text = 'No data — cannot evaluate'
            Clock.schedule_once(lambda dt: self._done(False, []), 2.0)
            return

        all_data = np.concatenate(self._samples, axis=1)
        hd_channels = min(all_data.shape[0], CFG.HDSEMG_CHANNELS)
        hd = all_data[:hd_channels]
        test_rms = np.sqrt(np.mean(hd ** 2, axis=1))
        baseline = self._baseline_rms[:hd_channels]

        # Flag channels where RMS during plantar flexion >> baseline
        threshold = baseline + CFG.CROSSTALK_THRESHOLD_K * baseline
        flagged = np.where(test_rms > threshold)[0].tolist()

        if not flagged:
            self.status_label.text = 'PASS'
            self.status_label.color = (0.2, 0.9, 0.2, 1)
            self.result_label.text = 'No crosstalk detected on TA channels'
        else:
            ch_str = ', '.join(str(c + 1) for c in flagged[:8])
            self.status_label.text = 'WARNING'
            self.status_label.color = (1.0, 0.6, 0.1, 1)
            self.result_label.text = f'Possible crosstalk on Ch: {ch_str}'

        passed = len(flagged) == 0
        Clock.schedule_once(lambda dt: self._done(passed, flagged), 2.5)

    def _done(self, passed, flagged):
        self.dismiss()
        self._on_complete(passed, flagged)

    @staticmethod
    def evaluate_crosstalk(test_rms, baseline_rms, threshold_k):
        """Evaluate crosstalk from RMS arrays (testable without Kivy).

        Args:
            test_rms: per-channel RMS during plantar flexion.
            baseline_rms: per-channel RMS from calibration rest.
            threshold_k: multiplier for baseline to set the threshold.

        Returns:
            list of flagged channel indices.
        """
        threshold = baseline_rms + threshold_k * baseline_rms
        return np.where(test_rms > threshold)[0].tolist()
