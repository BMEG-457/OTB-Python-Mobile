"""Static EMG plot screen for post-session data inspection."""

import threading
import numpy as np

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import sp

from app.core import config as CFG
from app.processing.filters import butter_bandpass, notch, rectify
from app.processing.iir_filter import filtfilt

_MAX_DISPLAY_PTS = 2000
_Y_PAD = 0.05  # 5% vertical padding on each side
_MIN_WINDOW = 0.05  # 50ms minimum view window
_DEFAULT_WINDOW = 5.0  # initial view window in seconds
_FILTER_PAD = 100  # extra samples on each side for filter edge effects


class StaticEMGPlotWidget(Widget):
    """Canvas-based renderer for a fixed 1D signal array."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pts_y = None
        self._y_min = 0.0
        self._y_max = 0.0

        with self.canvas:
            Color(*CFG.PLOT_BG_RGBA)
            self._rect = Rectangle(pos=self.pos, size=self.size)
            Color(*CFG.PLOT_LINE_RGBA)
            self._line = Line(points=[], width=1)

        self.bind(pos=self._update_layout, size=self._update_layout)

    def set_y_range(self, y_min, y_max):
        """Set fixed Y-axis range. Call once when the full channel is known."""
        self._y_min = float(y_min)
        self._y_max = float(y_max)

    def set_signal(self, signal_1d):
        """Load a new signal for display. Downsamples to _MAX_DISPLAY_PTS."""
        if signal_1d is None or len(signal_1d) == 0:
            self._pts_y = None
            self._line.points = []
            return

        step = max(1, len(signal_1d) // _MAX_DISPLAY_PTS)
        self._pts_y = signal_1d[::step].copy()
        self._draw()

    def _update_layout(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._draw()

    def _draw(self):
        if self._pts_y is None or self.width == 0 or self.height == 0:
            self._line.points = []
            return

        n = len(self._pts_y)
        span = self._y_max - self._y_min

        # x: evenly spaced across widget width
        xs = self.x + np.linspace(0, self.width, n)

        # y: normalise to widget height with padding
        if span == 0:
            ys = np.full(n, self.y + self.height * 0.5)
        else:
            inner_h = self.height * (1.0 - 2 * _Y_PAD)
            ys = self.y + self.height * _Y_PAD + (self._pts_y - self._y_min) / span * inner_h

        pts = np.empty(2 * n)
        pts[0::2] = xs
        pts[1::2] = ys
        self._line.points = pts.tolist()


class AnalysisPlotScreen(Screen):
    """Screen that displays a static EMG signal from a loaded recording.

    Call set_data() before switching to this screen.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._data = None
        self._ts = None
        self._filename = ''
        self._channel_idx = 0

        # Time navigation state
        self._total_duration = 0.0
        self._view_start = 0.0
        self._view_duration = _DEFAULT_WINDOW
        self._slider_updating = False

        # Filter state
        self._filt_bandpass = False
        self._filt_notch = False
        self._filt_rectify = False
        self._filt_envelope = False

        # Per-channel filtered signal cache
        self._cached_ch_idx = -1
        self._cached_signal = None  # 1D filtered signal for current channel

        self._build_ui()

    def _build_ui(self):
        root = BoxLayout(orientation='vertical')

        # Top bar: back + filename + filters button
        top_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.07), padding=4, spacing=4)
        btn_back = Button(text='Back', size_hint=(0.12, 1), font_size=sp(16))
        btn_back.bind(on_press=lambda x: setattr(self.manager, 'current', 'data_analysis'))
        self._filename_label = Label(
            text='', font_size=sp(16), bold=True,
            size_hint=(0.73, 1), halign='left', valign='middle',
        )
        self._filename_label.bind(
            size=lambda inst, _: setattr(inst, 'text_size', (inst.width, None))
        )
        btn_filters = Button(text='Filters', size_hint=(0.15, 1), font_size=sp(15))
        btn_filters.bind(on_press=lambda x: self._show_filter_popup())
        top_bar.add_widget(btn_back)
        top_bar.add_widget(self._filename_label)
        top_bar.add_widget(btn_filters)
        root.add_widget(top_bar)

        # Channel selection bar
        from kivy.uix.textinput import TextInput
        nav_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.07), padding=4, spacing=4)
        nav_bar.add_widget(Label(text='Channel:', size_hint=(0.2, 1), font_size=sp(15)))
        self._ch_input = TextInput(text='1', size_hint=(0.15, 1), font_size=sp(15),
                                   input_filter='int', multiline=False, halign='center')
        self._ch_input.bind(on_text_validate=self._on_ch_input)
        nav_bar.add_widget(self._ch_input)
        btn_go = Button(text='Go', size_hint=(0.12, 1), font_size=sp(15))
        btn_go.bind(on_press=lambda x: self._on_ch_input())
        nav_bar.add_widget(btn_go)
        self._ch_label = Label(text='', font_size=sp(14), size_hint=(0.25, 1),
                               color=(0.7, 0.7, 0.7, 1))
        nav_bar.add_widget(self._ch_label)
        self._filter_progress = ProgressBar(max=100, value=0, size_hint=(0.28, 1))
        self._filter_progress.opacity = 0
        nav_bar.add_widget(self._filter_progress)
        root.add_widget(nav_bar)

        # Plot area
        self._plot = StaticEMGPlotWidget(size_hint=(1, 0.68))
        root.add_widget(self._plot)

        # Time navigation bar: [<<] [<] [---slider---] [>] [>>]
        time_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.08), padding=4, spacing=4)
        btn_start = Button(text='<<', size_hint=(0.1, 1), font_size=sp(16))
        btn_start.bind(on_press=lambda x: self._go_to_start())
        btn_step_back = Button(text='<', size_hint=(0.1, 1), font_size=sp(16))
        btn_step_back.bind(on_press=lambda x: self._scroll_left())
        self._time_slider = Slider(min=0, max=1, value=0, size_hint=(0.6, 1))
        self._time_slider.bind(value=self._on_slider_changed)
        btn_step_fwd = Button(text='>', size_hint=(0.1, 1), font_size=sp(16))
        btn_step_fwd.bind(on_press=lambda x: self._scroll_right())
        btn_end = Button(text='>>', size_hint=(0.1, 1), font_size=sp(16))
        btn_end.bind(on_press=lambda x: self._go_to_end())
        time_bar.add_widget(btn_start)
        time_bar.add_widget(btn_step_back)
        time_bar.add_widget(self._time_slider)
        time_bar.add_widget(btn_step_fwd)
        time_bar.add_widget(btn_end)
        root.add_widget(time_bar)

        # Info bar: position label + zoom controls
        info_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.07), padding=4, spacing=4)
        self._pos_label = Label(text='0.00s / 0.00s', size_hint=(0.45, 1), font_size=sp(14),
                                halign='left', valign='middle')
        self._pos_label.bind(size=lambda inst, _: setattr(inst, 'text_size', (inst.width, None)))
        btn_zoom_out = Button(text='-', size_hint=(0.1, 1), font_size=sp(18))
        btn_zoom_out.bind(on_press=lambda x: self._zoom_out())
        self._window_label = Label(text='5.0s', size_hint=(0.25, 1), font_size=sp(14))
        btn_zoom_in = Button(text='+', size_hint=(0.1, 1), font_size=sp(18))
        btn_zoom_in.bind(on_press=lambda x: self._zoom_in())
        info_bar.add_widget(self._pos_label)
        info_bar.add_widget(btn_zoom_out)
        info_bar.add_widget(self._window_label)
        info_bar.add_widget(btn_zoom_in)
        root.add_widget(info_bar)

        # Spacer to fill remaining 0.03
        root.add_widget(Widget(size_hint=(1, 0.03)))

        self.add_widget(root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_data(self, data, timestamps, filename=''):
        """Load data for display. Call before switching to this screen.

        Args:
            data: np.ndarray shape (channels, samples)
            timestamps: np.ndarray shape (N,)
            filename: display name shown in the top bar
        """
        self._data = data
        self._ts = timestamps
        self._filename = filename
        self._channel_idx = 0
        self._invalidate_cache()

        # Compute total duration from timestamps
        if timestamps is not None and len(timestamps) > 1:
            self._total_duration = float(timestamps[-1] - timestamps[0])
        else:
            self._total_duration = 0.0

        # Set initial view window
        self._view_start = 0.0
        self._view_duration = min(_DEFAULT_WINDOW, self._total_duration) if self._total_duration > 0 else _DEFAULT_WINDOW
        self._update_display()

    # ------------------------------------------------------------------
    # Filter popup
    # ------------------------------------------------------------------

    def _show_filter_popup(self):
        from kivy.uix.scrollview import ScrollView

        content = BoxLayout(orientation='vertical', padding=8, spacing=8)

        # Scrollable area for filter options
        scroll = ScrollView(size_hint=(1, 1))
        options = BoxLayout(orientation='vertical', size_hint_y=None, spacing=8, padding=4)
        options.bind(minimum_height=options.setter('height'))

        filters = [
            ('_cb_bandpass', self._filt_bandpass,
             f'Bandpass ({CFG.BANDPASS_LOW_HZ:.0f}-{CFG.BANDPASS_HIGH_HZ:.0f} Hz)'),
            ('_cb_notch', self._filt_notch,
             f'Notch ({CFG.NOTCH_FREQ_HZ:.0f} Hz)'),
            ('_cb_rectify', self._filt_rectify, 'Rectify'),
            ('_cb_envelope', self._filt_envelope, 'Envelope (lowpass smoothing)'),
        ]
        for attr, active, label_text in filters:
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=sp(50))
            cb = CheckBox(active=active, size_hint=(0.15, 1))
            setattr(self, attr, cb)
            lbl = Label(text=label_text, font_size=sp(15), halign='left', valign='middle',
                        size_hint=(0.85, 1))
            lbl.bind(size=lambda inst, _: setattr(inst, 'text_size', (inst.width, None)))
            row.add_widget(cb)
            row.add_widget(lbl)
            options.add_widget(row)

        scroll.add_widget(options)
        content.add_widget(scroll)

        # Buttons pinned at bottom
        btn_row = BoxLayout(orientation='horizontal', size_hint=(1, None), height=sp(52), spacing=8)
        btn_apply = Button(text='Apply', font_size=sp(16))
        btn_close = Button(text='Close', font_size=sp(16))
        btn_row.add_widget(btn_apply)
        btn_row.add_widget(btn_close)
        content.add_widget(btn_row)

        popup = Popup(title='Signal Processing', content=content,
                      size_hint=(0.85, 0.8))
        btn_apply.bind(on_press=lambda x: self._on_filter_apply(popup))
        btn_close.bind(on_press=lambda x: popup.dismiss())
        popup.open()

    def _on_filter_apply(self, popup):
        self._filt_bandpass = self._cb_bandpass.active
        self._filt_notch = self._cb_notch.active
        self._filt_rectify = self._cb_rectify.active
        self._filt_envelope = self._cb_envelope.active
        popup.dismiss()
        self._invalidate_cache()
        self._update_display()

    def _invalidate_cache(self):
        self._cached_ch_idx = -1
        self._cached_signal = None

    def _ensure_filtered_signal(self):
        """Ensure filtered signal is cached for the current channel.

        If the cache is valid, calls _update_display immediately.
        If not, kicks off a background thread and returns (display updates when done).
        Returns True if cache is ready, False if filtering in background.
        """
        ch = self._channel_idx
        if self._cached_ch_idx == ch and self._cached_signal is not None:
            return True

        signal = self._data[ch]
        if not (self._filt_bandpass or self._filt_notch
                or self._filt_rectify or self._filt_envelope):
            self._cached_ch_idx = ch
            self._cached_signal = signal
            return True

        # Show progress bar, then filter in background
        self._ch_label.text = 'Applying filters...'
        self._filter_progress.value = 0
        self._filter_progress.opacity = 1

        # Count total filter steps for progress
        steps = []
        if self._filt_bandpass:
            steps.append('bp')
        if self._filt_notch:
            steps.append('notch')
        if self._filt_rectify:
            steps.append('rect')
        if self._filt_envelope:
            steps.append('env')
        total_steps = len(steps)

        do_bp = self._filt_bandpass
        do_notch = self._filt_notch
        do_rect = self._filt_rectify
        do_env = self._filt_envelope

        def set_progress(pct):
            Clock.schedule_once(lambda dt: setattr(self._filter_progress, 'value', pct), 0)

        def run():
            done = 0
            data = signal[np.newaxis, :].copy()
            if do_bp:
                data = butter_bandpass(data)
                done += 1
                set_progress(done / total_steps * 100)
            if do_notch:
                data = notch(data)
                done += 1
                set_progress(done / total_steps * 100)
            if do_rect:
                data = rectify(data)
                done += 1
                set_progress(done / total_steps * 100)
            if do_env:
                if not do_rect:
                    data = rectify(data)
                b = np.array(CFG.LOWPASS_10_4_B)
                a = np.array(CFG.LOWPASS_10_4_A)
                data = filtfilt(b, a, data)
                done += 1
                set_progress(done / total_steps * 100)
            self._cached_ch_idx = ch
            self._cached_signal = data[0]

            def finish(dt):
                self._filter_progress.opacity = 0
                self._update_display()
            Clock.schedule_once(finish, 0)

        threading.Thread(target=run, daemon=True).start()
        return False

    # ------------------------------------------------------------------
    # Time navigation
    # ------------------------------------------------------------------

    def _clamp_position(self):
        if self._total_duration <= 0:
            self._view_start = 0.0
            return
        max_start = max(0, self._total_duration - self._view_duration)
        self._view_start = max(0, min(self._view_start, max_start))

    def _scroll_left(self):
        self._view_start -= self._view_duration * 0.1
        self._clamp_position()
        self._update_display()

    def _scroll_right(self):
        self._view_start += self._view_duration * 0.1
        self._clamp_position()
        self._update_display()

    def _go_to_start(self):
        self._view_start = 0.0
        self._update_display()

    def _go_to_end(self):
        self._view_start = max(0, self._total_duration - self._view_duration)
        self._update_display()

    def _zoom_in(self):
        new_dur = self._view_duration / 2
        if new_dur < _MIN_WINDOW:
            return
        center = self._view_start + self._view_duration / 2
        self._view_duration = new_dur
        self._view_start = center - self._view_duration / 2
        self._clamp_position()
        self._update_display()

    def _zoom_out(self):
        new_dur = self._view_duration * 2
        if self._total_duration > 0:
            new_dur = min(new_dur, self._total_duration)
        center = self._view_start + self._view_duration / 2
        self._view_duration = new_dur
        self._view_start = center - self._view_duration / 2
        self._clamp_position()
        self._update_display()

    def _on_slider_changed(self, instance, value):
        if self._slider_updating or self._total_duration <= 0:
            return
        center = value * self._total_duration
        self._view_start = center - self._view_duration / 2
        self._clamp_position()
        self._update_display(update_slider=False)

    def _get_normalized_position(self):
        if self._total_duration <= 0:
            return 0.0
        center = self._view_start + self._view_duration / 2
        return min(1.0, max(0.0, center / self._total_duration))

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _update_display(self, update_slider=True):
        if self._data is None:
            return

        # Ensure filtered signal is ready; if not, background thread will call us back
        if not self._ensure_filtered_signal():
            return

        n_ch = self._data.shape[0]
        self._filename_label.text = self._filename
        self._ch_label.text = f'Channel {self._channel_idx + 1} / {n_ch}'
        signal = self._cached_signal

        # Fix Y-axis to the full raw channel's range (stable across scrolling)
        raw = self._data[self._channel_idx]
        self._plot.set_y_range(float(raw.min()), float(raw.max()))

        # Slice visible window from the cached filtered signal
        if self._ts is not None and len(self._ts) > 1:
            t0 = float(self._ts[0])
            start_idx = int(np.searchsorted(self._ts, t0 + self._view_start))
            end_idx = int(np.searchsorted(self._ts, t0 + self._view_start + self._view_duration))
            end_idx = min(end_idx, len(signal))
            start_idx = min(start_idx, end_idx)
            visible = signal[start_idx:end_idx]
        else:
            visible = signal

        self._plot.set_signal(visible)

        # Update position label
        self._pos_label.text = f'{self._view_start:.2f}s / {self._total_duration:.2f}s'

        # Update window label
        if self._view_duration >= 1.0:
            self._window_label.text = f'Window: {self._view_duration:.1f}s'
        else:
            self._window_label.text = f'Window: {self._view_duration * 1000:.0f}ms'

        # Sync slider
        if update_slider:
            self._slider_updating = True
            self._time_slider.value = self._get_normalized_position()
            self._slider_updating = False

    # ------------------------------------------------------------------
    # Channel navigation
    # ------------------------------------------------------------------

    def _on_ch_input(self, *_):
        if self._data is None:
            return
        try:
            ch = int(self._ch_input.text) - 1
        except (ValueError, TypeError):
            return
        n_ch = self._data.shape[0]
        if ch < 0 or ch >= n_ch:
            self._ch_label.text = f'Invalid (1-{n_ch})'
            return
        self._channel_idx = ch
        self._update_display()
