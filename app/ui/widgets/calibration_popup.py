"""Calibration popup widget."""

import numpy as np
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.metrics import sp
from app.core import config as CFG


class CalibrationPopup(Popup):
    """Two-phase calibration popup: rest, then MVC.

    Phase 1 (Rest): Collects baseline EMG at rest.
    Phase 2 (MVC): Collects maximum voluntary contraction. The MVC data is
        also used for activation pattern verification — no separate phase needed.

    Calls on_complete with (baseline_rms, threshold, mvc_rms) as numpy arrays
    of shape (n_channels,) when both phases are done.

    Args:
        on_complete: callable(baseline_rms, threshold, mvc_rms).
        on_sample_connect: callable(callback) — registers a function to receive
            (stage, data) pairs from the data receiver during calibration.
        on_sample_disconnect: callable(callback) — unregisters the callback.
    """

    def __init__(self, on_complete, on_sample_connect, on_sample_disconnect, **kwargs):
        super().__init__(**kwargs)
        self.title = 'Calibration'
        self.size_hint = (0.85, 0.55)
        self.auto_dismiss = False

        self.on_complete = on_complete
        self.on_sample_connect = on_sample_connect
        self.on_sample_disconnect = on_sample_disconnect

        self._rest_samples = []
        self._mvc_samples = []
        self._current_phase = None  # 'rest' | 'mvc'
        self._current_phase = None  # 'rest' | 'mvc'

        # Build content
        layout = BoxLayout(orientation='vertical', padding=16, spacing=12)
        self.status_label = Label(
            text='Preparing...', font_size=sp(20), size_hint=(1, 0.3), halign='center'
        )
        self.instruction_label = Label(
            text='', font_size=sp(16), color=(0.8, 0.8, 0.8, 1), size_hint=(1, 0.3), halign='center'
        )
        self.progress = ProgressBar(max=100, value=0, size_hint=(1, 0.2))
        layout.add_widget(self.status_label)
        layout.add_widget(self.instruction_label)
        layout.add_widget(self.progress)
        self.content = layout

        self._progress_event = None

    def start(self):
        """Open popup and begin the rest phase."""
        self.open()
        self._start_rest_phase()

    def _start_rest_phase(self):
        self._current_phase = 'rest'
        self._rest_samples = []
        self.status_label.text = 'Phase 1 of 2: Rest'
        self.status_label.text = 'Phase 1 of 2: Rest'
        self.instruction_label.text = 'Relax your muscle completely.'
        self.progress.value = 0
        self.on_sample_connect(self._collect_sample)
        self._schedule_progress(CFG.CALIBRATION_REST_DURATION, self._start_mvc_phase)

    def _start_mvc_phase(self, dt=None):
        self._current_phase = 'mvc'
        self._mvc_samples = []
        self.status_label.text = 'Phase 2 of 2: MVC'
        self.status_label.text = 'Phase 2 of 2: MVC'
        self.instruction_label.text = 'Contract as hard as you can!'
        self.progress.value = 0
        self._schedule_progress(CFG.CALIBRATION_MVC_DURATION, self._evaluate_and_finish)

    def _evaluate_and_finish(self, dt=None):
        """Verify activation pattern using MVC data, then finish."""
        if not self._mvc_samples:
            self.instruction_label.text = 'No MVC data received.'
            Clock.schedule_once(lambda dt: self._finish(), CFG.CALIBRATION_DISMISS_DELAY)
            return

        all_data = np.concatenate(self._mvc_samples, axis=1)
        all_data = np.concatenate(self._mvc_samples, axis=1)
        hd_channels = min(all_data.shape[0], CFG.HDSEMG_CHANNELS)
        hd_data = all_data[:hd_channels]
        rms_per_ch = np.sqrt(np.mean(hd_data ** 2, axis=1))

        concentration = self.compute_concentration(rms_per_ch)

        if concentration > CFG.CALIBRATION_VERIFY_ACTIVE_FRAC:
            self.status_label.text = 'Calibration: PASS'
            self.status_label.text = 'Calibration: PASS'
            self.status_label.color = (0.2, 0.9, 0.2, 1)
            self.instruction_label.text = 'Activation pattern looks good!'
        else:
            self.status_label.text = 'Calibration: WARNING'
            self.status_label.text = 'Calibration: WARNING'
            self.status_label.color = (1.0, 0.6, 0.1, 1)
            self.instruction_label.text = 'Diffuse activation — check electrode placement'

        Clock.schedule_once(lambda dt: self._finish(), CFG.CALIBRATION_DISMISS_DELAY)

    @staticmethod
    def compute_concentration(rms_per_ch):
        """Compute spatial concentration: fraction of total RMS in the top quarter of channels.

        Dead channels (always-zero adapter pins) are excluded so they don't
        inflate the denominator or dilute the concentration score.

        Returns a value in [0, 1]. Higher means more concentrated activation.
        """
        active_mask = np.array([i not in CFG.DEAD_CHANNELS
                                for i in range(len(rms_per_ch))], dtype=bool)
        active_rms = rms_per_ch[active_mask]
        n = len(active_rms)
        sorted_rms = np.sort(active_rms)[::-1]
        top_quarter = sorted_rms[:max(1, n // 4)].sum()
        total = sorted_rms.sum()
        return float(top_quarter / total) if total > 0 else 0.0

    def _finish(self, dt=None):
        self.on_sample_disconnect(self._collect_sample)
        self._current_phase = None

        baseline_rms = self._compute_rms(self._rest_samples)
        mvc_rms = self._compute_rms(self._mvc_samples)

        if baseline_rms is None or mvc_rms is None:
            self.status_label.text = 'Calibration failed — no data received.'
            Clock.schedule_once(lambda dt: self.dismiss(), CFG.CALIBRATION_DISMISS_DELAY)
            return

        # Threshold between baseline and MVC (fraction set in config)
        threshold = baseline_rms + (mvc_rms - baseline_rms) * CFG.CALIBRATION_THRESHOLD_FRAC

        self.dismiss()
        self.on_complete(baseline_rms, threshold, mvc_rms)

    def _collect_sample(self, stage, data):
        """Receive data from the receiver during calibration."""
        if stage != 'raw':
            return
        if self._current_phase == 'rest':
            self._rest_samples.append(data.copy())
        elif self._current_phase == 'mvc':
            self._mvc_samples.append(data.copy())

    def _compute_rms(self, sample_list):
        if not sample_list:
            return None
        # Each element: (channels, samples). Stack along samples axis.
        stacked = np.concatenate(sample_list, axis=1)  # (channels, total_samples)
        rms = np.sqrt(np.mean(stacked ** 2, axis=1))   # (channels,)
        # Zero dead channels so they don't skew threshold or baseline estimates
        for ch in CFG.DEAD_CHANNELS:
            if ch < len(rms):
                rms[ch] = 0.0
        return rms

    def _schedule_progress(self, duration, next_fn):
        """Animate the progress bar over duration seconds, then call next_fn."""
        start = [0.0]
        tick = 1.0 / CFG.CALIBRATION_PROGRESS_FPS

        if self._progress_event is not None:
            self._progress_event.cancel()

        def update(dt):
            start[0] += dt
            self.progress.value = min(100, (start[0] / duration) * 100)
            if start[0] >= duration:
                self._progress_event.cancel()
                self._progress_event = None
                next_fn()

        self._progress_event = Clock.schedule_interval(update, tick)
