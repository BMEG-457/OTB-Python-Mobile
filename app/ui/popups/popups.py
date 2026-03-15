from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.properties import ObjectProperty, NumericProperty, StringProperty
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.event import EventDispatcher
import numpy as np

# Assuming Config class is accessible
from app.core.config import Config

class CalibrationPopup(Popup, EventDispatcher):
    """Kivy version of CalibrationDialog using Clock for countdowns."""
    def __init__(self, receiver_thread, rest_duration=5, contraction_duration=5, **kwargs):
        super().__init__(**kwargs)
        self.register_event('on_calibration_complete')
        
        self.receiver_thread = receiver_thread
        self.rest_duration = rest_duration
        self.contraction_duration = contraction_duration
        
        self.rest_rms_values = []
        self.contraction_rms_values = []
        self.remaining_time = 0
        self.current_phase = None
        self.subscription_connected = False

    def on_calibration_complete(self, baseline, threshold, mvc):
        """Event fired when calibration finishes."""
        pass

    def start_calibration(self):
        self.rest_rms_values = []
        self.contraction_rms_values = []
        self.ids.start_button.disabled = True
        
        if not self.subscription_connected and self.receiver_thread is not None:
            # Note: Ensure your receiver uses Kivy properties or Clock-safe triggers
            self.receiver_thread.bind(on_stage_output=self.on_stage_output)
            self.subscription_connected = True
        self.start_rest_phase()

    def start_rest_phase(self):
        self.current_phase = 'rest'
        self.remaining_time = self.rest_duration
        self.ids.phase_label.text = "Phase 1: REST"
        self.ids.phase_label.color = (0, 0.6, 1, 1)
        Clock.schedule_interval(self.tick_countdown, 1)

    def tick_countdown(self, dt):
        self.ids.timer_label.text = f"{self.remaining_time}s"
        if self.remaining_time <= 0:
            Clock.unschedule(self.tick_countdown)
            if self.current_phase == 'rest':
                self.start_contraction_phase()
            else:
                self.compute_threshold_and_close()
            return False
        self.remaining_time -= 1
        return True

    def on_stage_output(self, instance, stage_name, data):
        """Collects RMS data. Logic identical to desktop."""
        if stage_name == 'filtered' and self.current_phase:
            mask = (data > Config.SATURATION_LOW) & (data < Config.SATURATION_HIGH)
            rms = np.zeros(data.shape[0])
            for i in range(data.shape[0]):
                valid = data[i][mask[i]]
                rms[i] = np.sqrt(np.mean(valid**2)) if len(valid) > 0 else 0.0
            
            target_list = self.rest_rms_values if self.current_phase == 'rest' else self.contraction_rms_values
            target_list.append(rms)

    def compute_threshold_and_close(self):
        # Insert the exact NumPy math from your desktop file here
        # After computing baseline_rms, threshold, and mvc_rms:
        self.dispatch('on_calibration_complete', baseline_rms, threshold, mvc_rms)
        self.dismiss()

class ChannelSelectorPopup(Popup):
    def __init__(self, num_channels, selected=None, **kwargs):
        super().__init__(**kwargs)
        self.checkboxes = []
        for i in range(num_channels):
            box = BoxLayout(size_hint_y=None, height='40dp')
            cb = CheckBox(active=(True if selected is None else i in selected))
            box.add_widget(cb)
            box.add_widget(Label(text=f"CH {i+1}"))
            self.ids.container.add_widget(box)
            self.checkboxes.append(cb)

    def get_selected(self):
        return [i for i, cb in enumerate(self.checkboxes) if cb.active]

class TrackVisibilityPopup(Popup):
    def __init__(self, track_titles, selected=None, **kwargs):
        super().__init__(**kwargs)
        self.checkboxes = {}
        for title in track_titles:
            box = BoxLayout(size_hint_y=None, height='40dp')
            cb = CheckBox(active=(True if selected is None else title in selected))
            box.add_widget(cb)
            box.add_widget(Label(text=title))
            self.ids.container.add_widget(box)
            self.checkboxes[title] = cb

class FeatureControlsPopup(Popup):
    options = [100, 200, 500, 1000]
    def __init__(self, current_ms, **kwargs):
        super().__init__(**kwargs)
        self.ids.spinner.text = f"{current_ms} ms"