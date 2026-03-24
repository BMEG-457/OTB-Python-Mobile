"""Live data viewing screen."""

import threading
import time
import numpy as np

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.metrics import dp, sp

from app.data.data_receiver import DataReceiverThread
from app.managers.recording_manager import RecordingManager
from app.managers.streaming_controller import StreamingController
from app.processing.pipeline import get_pipeline
from app.processing import filters
from app.processing.iir_filter import StatefulIIRFilter
from app.processing.live_metrics import LiveMetricsComputer
from app.processing.clipping_detector import ClippingDetector
from app.ui.widgets.emg_plot_widget import EMGPlotWidget
from app.ui.widgets.multi_track_plot import MultiTrackPlotWidget
from app.ui.widgets.heatmap_widget import HeatmapWidget
from app.ui.widgets.calibration_popup import CalibrationPopup
from app.ui.widgets.session_metadata_popup import SessionMetadataPopup
from app.ui.widgets.seniam_guide_popup import SENIAMGuidePopup
from app.ui.widgets.crosstalk_popup import CrosstalkVerificationPopup
from app.core import config as CFG


# ---------------------------------------------------------------------------
# HD-EMG aggregation helpers
# channel_idx = col * 8 + (7 - row) — columns 0-7, rows 0-7, bottom-left = ch0
# Channels 0-63 = HD-EMG array; 64-71 = AUX (excluded from spatial views)
# ---------------------------------------------------------------------------

def _row_aggregates(data):
    """Mean across columns for each row. data (≥64, S) → (8, S)."""
    result = []
    for row in range(8):
        ch_indices = [col * 8 + (7 - row) for col in range(8)]
        result.append(data[ch_indices].mean(axis=0))
    return np.array(result)


def _col_aggregates(data):
    """Mean across rows for each column. data (≥64, S) → (8, S)."""
    result = []
    for col in range(8):
        ch_indices = [col * 8 + r for r in range(8)]
        result.append(data[ch_indices].mean(axis=0))
    return np.array(result)


def _cluster_aggregates(data):
    """Mean of 2x2 electrode clusters. data (≥64, S) → (16, S), 4x4 arrangement."""
    result = []
    for cr in range(4):       # cluster row
        for cc in range(4):   # cluster col
            ch_indices = []
            for dr in range(2):
                for dc in range(2):
                    row = cr * 2 + dr
                    col = cc * 2 + dc
                    ch_indices.append(col * 8 + (7 - row))
            result.append(data[ch_indices].mean(axis=0))
    return np.array(result)


# View mode definitions: (label, num_tracks, aggregation_fn_or_sentinel)
# 'auto_mav' sentinel in 3rd position triggers auto-channel MAV envelope view
_VIEW_MODES_BASIC = [
    ('Auto MAV', 1, 'auto_mav'),
]

_VIEW_MODES_ADVANCED = [
    ('Single Ch1', 1,  None),
    ('Auto MAV',   1,  'auto_mav'),
    ('Rows (8)',   8,  _row_aggregates),
    ('Cols (8)',   8,  _col_aggregates),
    ('Clusters',   16, _cluster_aggregates),
]


class LiveDataScreen(Screen):
    """Main live-streaming screen.

    Layout:
        Top bar     [0.10] — Back, Calibrate, Stream, Record, Contraction, Status
        Tab+View bar[0.07] — EMG Plot | Heatmap tabs; View mode cycle button
        Content     [0.78] — active plot panel OR heatmap panel
        Bottom bar  [0.05] — status / instructions
    """

    def __init__(self, device, **kwargs):
        super().__init__(**kwargs)
        self.device = device

        # App state
        self.receiver_thread = None
        self.streaming_controller = None
        self.recording_manager = RecordingManager(
            on_overflow=self._on_recording_overflow,
            on_status=self._on_status_update,
        )
        self.is_calibrated = False
        self.baseline_rms = None
        self.threshold = None
        self.mvc_rms = None

        self._calibration_extra_callback = None

        # Accumulated packets from receiver — list of (channels, samples) arrays
        self._pending_packets = []

        # Contraction state — computed in _ui_tick
        self._contraction_color = CFG.CONTRACTION_INACTIVE

        # Per-channel rolling buffers for heatmap RMS computation
        self._heatmap_buffer = np.zeros((CFG.HDSEMG_CHANNELS, CFG.HEATMAP_BUFFER_SAMPLES))
        self._heatmap_buf_idx = 0

        # Auto MAV channel selection + envelope
        self._auto_mav_channel = 0

        # Latency monitoring
        self._latency_window = []

        # Debug diagnostics (output via print → logcat)
        self._tick_count = 0
        self._last_tick_time = time.time()

        # Clipping detection
        self._clipping_detector = ClippingDetector()
        self._pending_clipping = []

        # Real-time metrics
        self._metrics_computer = LiveMetricsComputer()
        self._pending_metrics = None

        # Mode: 'basic' (clinical) or 'advanced' (researcher)
        self._mode = 'advanced'
        self._view_modes = list(_VIEW_MODES_ADVANCED)

        # View mode index into self._view_modes
        self._view_mode_idx = 0

        # Channel selector state (single-channel mode)
        self._single_channel_idx = 0

        # Time window preset index
        self._time_window_idx = CFG.PLOT_DEFAULT_TIME_IDX

        self._battery_event = None
        self._build_ui()
        self._configure_pipelines()

    def on_enter(self):
        self._start_battery_poll()
        # Recover any autosave files left behind by a previous crash
        orphans = RecordingManager.find_orphaned_autosaves()
        if orphans:
            for f in orphans:
                RecordingManager.recover_autosave(f)
            self._set_bottom(f'Recovered {len(orphans)} recording(s) from previous session.')

    def on_leave(self):
        self._stop_battery_poll()

    # ------------------------------------------------------------------
    # Basic / Advanced mode
    # ------------------------------------------------------------------

    def set_mode(self, mode):
        """Set 'basic' or 'advanced' mode and update UI visibility."""
        self._mode = mode
        if mode == 'basic':
            self._view_modes = list(_VIEW_MODES_BASIC)
        else:
            self._view_modes = list(_VIEW_MODES_ADVANCED)
        self._view_mode_idx = 0
        self._apply_mode()

    def _apply_mode(self):
        """Show/hide UI elements based on current mode."""
        label = self._view_modes[self._view_mode_idx][0]
        self.btn_view_mode.text = f'View: {label}'

        if self._mode == 'basic':
            # Hide channel selector, time window, and view mode cycle button
            self._set_ch_bar_visible(False)
            self.btn_time_window.opacity = 0
            self.btn_time_window.disabled = True
            self.btn_view_mode.opacity = 0
            self.btn_view_mode.disabled = True
        else:
            # Show all controls
            self.btn_time_window.opacity = 1
            self.btn_time_window.disabled = False
            self.btn_view_mode.opacity = 1
            self.btn_view_mode.disabled = False
            self._update_ch_bar_visibility()

        # Ensure correct plot widget is shown
        if self._active_tab == 'plot':
            self._show_active_plot_widget()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = BoxLayout(orientation='vertical', padding=dp(8))

        # ---- Top bar ----
        top_bar = BoxLayout(
            orientation='horizontal', size_hint=(1, 0.10), padding=4, spacing=4
        )

        btn_back = Button(text='Back', size_hint=(0.07, 1), font_size=sp(14))
        btn_back.bind(on_press=self._go_back)
        top_bar.add_widget(btn_back)

        self.btn_calibrate = Button(
            text='Calibrate', size_hint=(0.09, 1), font_size=sp(14)
        )
        self.btn_calibrate.bind(on_press=self._on_calibrate)
        self.btn_calibrate.disabled = True
        top_bar.add_widget(self.btn_calibrate)

        btn_guide = Button(text='Guide', size_hint=(0.07, 1), font_size=sp(14))
        btn_guide.bind(on_press=lambda x: SENIAMGuidePopup().open())
        top_bar.add_widget(btn_guide)

        self.btn_crosstalk = Button(
            text='Crosstalk', size_hint=(0.09, 1), font_size=sp(13)
        )
        self.btn_crosstalk.bind(on_press=self._on_crosstalk)
        self.btn_crosstalk.disabled = True
        top_bar.add_widget(self.btn_crosstalk)

        self.btn_stream = Button(
            text='Stream', size_hint=(0.08, 1),
            font_size=sp(14), background_color=CFG.BTN_STREAM_IDLE
        )
        self.btn_stream.bind(on_press=self._on_toggle_stream)
        top_bar.add_widget(self.btn_stream)

        self.btn_record = Button(
            text='Record', size_hint=(0.08, 1),
            font_size=sp(14), background_color=CFG.BTN_RECORD_IDLE
        )
        self.btn_record.bind(on_press=self._on_toggle_record)
        self.btn_record.disabled = True
        top_bar.add_widget(self.btn_record)

        self.contraction_label = Label(
            text='Contraction', color=CFG.CONTRACTION_INACTIVE,
            size_hint_x=None, width=dp(80), font_size=sp(12),
        )
        top_bar.add_widget(self.contraction_label)

        self.battery_label = Label(
            text='Bat: --', color=(0.5, 0.5, 0.5, 1),
            size_hint_x=None, width=dp(65), font_size=sp(12),
        )
        top_bar.add_widget(self.battery_label)

        self.latency_label = Label(
            text='Lat: --', color=(0.5, 0.5, 0.5, 1),
            size_hint_x=None, width=dp(55), font_size=sp(12),
        )
        top_bar.add_widget(self.latency_label)

        self.status_label = Label(
            text='Not connected', color=(0.7, 0.7, 0.7, 1),
            size_hint_x=None, width=dp(85), font_size=sp(12),
        )
        top_bar.add_widget(self.status_label)

        root.add_widget(top_bar)

        # ---- Disconnect warning banner ----
        self._disconnect_label = Label(
            text='', font_size=sp(18), color=(1, 0.2, 0.2, 1),
            size_hint=(1, 0.05), opacity=0,
        )
        root.add_widget(self._disconnect_label)

        # ---- Tab + View mode bar ----
        tab_bar = BoxLayout(
            orientation='horizontal', size_hint=(1, 0.07), padding=2, spacing=4
        )

        self.btn_tab_plot = ToggleButton(
            text='EMG Plot', group='tab', state='down',
            size_hint=(0.18, 1), font_size=sp(15),
        )
        self.btn_tab_plot.bind(on_press=self._on_tab_plot)
        tab_bar.add_widget(self.btn_tab_plot)

        self.btn_tab_heatmap = ToggleButton(
            text='Heatmap', group='tab', state='normal',
            size_hint=(0.18, 1), font_size=sp(15),
        )
        self.btn_tab_heatmap.bind(on_press=self._on_tab_heatmap)
        tab_bar.add_widget(self.btn_tab_heatmap)

        # Time window cycle button
        preset = CFG.PLOT_TIME_WINDOW_PRESETS[self._time_window_idx]
        self.btn_time_window = Button(
            text=f'Time: {preset["label"]}', size_hint=(0.14, 1), font_size=sp(14),
        )
        self.btn_time_window.bind(on_press=self._on_cycle_time_window)
        tab_bar.add_widget(self.btn_time_window)

        # Channel selector bar (visible only in single-channel view mode)
        self._ch_bar = BoxLayout(orientation='horizontal', size_hint=(0.22, 1), spacing=2)
        ch_label = Label(text='Ch:', size_hint=(0.35, 1), font_size=sp(14))
        self._ch_input = TextInput(
            text=str(self._single_channel_idx + 1),
            input_filter='int', multiline=False,
            size_hint=(0.65, 1), font_size=sp(14),
            halign='center', padding=[4, 4, 4, 4],
        )
        self._ch_input.bind(on_text_validate=self._on_ch_input_submit)
        self._ch_bar.add_widget(ch_label)
        self._ch_bar.add_widget(self._ch_input)
        tab_bar.add_widget(self._ch_bar)

        self.btn_view_mode = Button(
            text=f'View: {self._view_modes[0][0]}', size_hint=(0.28, 1), font_size=sp(14),
        )
        self.btn_view_mode.bind(on_press=self._on_cycle_view)
        tab_bar.add_widget(self.btn_view_mode)

        root.add_widget(tab_bar)

        # ---- Content area (FloatLayout to overlay panels) ----
        self._content = FloatLayout(size_hint=(1, 0.70))

        # Single-channel plot (default view)
        tw = CFG.PLOT_TIME_WINDOW_PRESETS[self._time_window_idx]
        self.plot_single = EMGPlotWidget(
            channel_index=self._single_channel_idx,
            display_samples=tw['display_samples'], downsample=tw['downsample'],
            size_hint=(1, 1), pos_hint={'x': 0, 'y': 0},
        )

        # Multi-track plot — starts with row labels; rebuilt on mode switch
        row_labels  = [f'Row {i}' for i in range(8)]
        self.plot_multi = MultiTrackPlotWidget(
            track_labels=row_labels,
            display_samples=tw['display_samples'], downsample=tw['downsample'],
            size_hint=(1, 1), pos_hint={'x': 0, 'y': 0},
        )
        self.plot_multi.opacity = 0

        # Heatmap
        self.heatmap = HeatmapWidget(
            size_hint=(1, 1), pos_hint={'x': 0, 'y': 0}
        )
        self.heatmap.opacity = 0

        self._content.add_widget(self.plot_single)
        self._content.add_widget(self.plot_multi)
        self._content.add_widget(self.heatmap)

        root.add_widget(self._content)

        # ---- Metrics bar ----
        self._metrics_bar = BoxLayout(
            orientation='horizontal', size_hint=(1, 0.08), padding=4, spacing=8
        )
        self._lbl_rms = Label(
            text='RMS: --', font_size=sp(14), color=(0.8, 0.8, 0.8, 1),
            size_hint=(0.20, 1),
        )
        self._lbl_mf = Label(
            text='MF: -- Hz', font_size=sp(14), color=(0.8, 0.8, 0.8, 1),
            size_hint=(0.20, 1),
        )
        self._lbl_fatigue = Label(
            text='Fatigue: --', font_size=sp(14), color=(0.5, 0.5, 0.5, 1),
            size_hint=(0.20, 1),
        )
        self._lbl_active_ch = Label(
            text='Ch: --', font_size=sp(14), color=(0.8, 0.8, 0.8, 1),
            size_hint=(0.20, 1),
        )
        self._lbl_clipping = Label(
            text='', font_size=sp(14), color=(1, 0.2, 0.2, 1),
            size_hint=(0.20, 1),
        )
        self._metrics_bar.add_widget(self._lbl_rms)
        self._metrics_bar.add_widget(self._lbl_mf)
        self._metrics_bar.add_widget(self._lbl_fatigue)
        self._metrics_bar.add_widget(self._lbl_active_ch)
        self._metrics_bar.add_widget(self._lbl_clipping)
        root.add_widget(self._metrics_bar)

        # ---- Bottom status bar ----
        self.bottom_label = Label(
            text='Press "Stream" to connect to the device.',
            font_size=sp(14), color=(0.6, 0.6, 0.6, 1),
            size_hint=(1, 0.05),
        )
        root.add_widget(self.bottom_label)

        self.add_widget(root)

        # Active tab state ('plot' | 'heatmap')
        self._active_tab = 'plot'

    def _configure_pipelines(self):
        # Stateful causal IIR filters — vectorized across channels, forward-only
        # (no filtfilt). Separate bandpass instances per pipeline to avoid shared state.
        filters.init_live_filters(CFG.HDSEMG_CHANNELS)
        get_pipeline('filtered').add_stage(lambda data: filters._live_bp_filtered(data))
        get_pipeline('rectified').add_stage(filters.rectify)
        get_pipeline('final').add_stage(lambda data: filters._live_bp_final(data))
        get_pipeline('final').add_stage(lambda data: filters._live_notch_final(data))
        get_pipeline('final').add_stage(filters.rectify)

        # Envelope lowpass filter for Auto MAV (all 64 channels to avoid stale state)
        self._envelope_filter = StatefulIIRFilter(
            CFG.LOWPASS_10_4_B, CFG.LOWPASS_10_4_A, n_channels=CFG.HDSEMG_CHANNELS
        )

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def _on_tab_plot(self, instance):
        self._active_tab = 'plot'
        if self._mode != 'basic':
            self.btn_view_mode.opacity = 1
            self.btn_view_mode.disabled = False
            self.btn_time_window.opacity = 1
            self.btn_time_window.disabled = False
        self._update_ch_bar_visibility()
        # Show active plot, hide heatmap
        self._show_active_plot_widget()
        self.heatmap.opacity = 0

    def _on_tab_heatmap(self, instance):
        self._active_tab = 'heatmap'
        self.btn_view_mode.opacity = 0
        self.btn_view_mode.disabled = True
        self.btn_time_window.opacity = 0
        self.btn_time_window.disabled = True
        self._set_ch_bar_visible(False)
        # Hide plot widgets, show heatmap
        self.plot_single.opacity = 0
        self.plot_multi.opacity = 0
        self.heatmap.opacity = 1

    def _show_active_plot_widget(self):
        """Show the correct plot widget for the current view mode."""
        label, n_tracks, _ = self._view_modes[self._view_mode_idx]
        if n_tracks == 1:
            self.plot_single.opacity = 1
            self.plot_multi.opacity = 0
        else:
            self.plot_single.opacity = 0
            self.plot_multi.opacity = 1

    # ------------------------------------------------------------------
    # View mode cycling
    # ------------------------------------------------------------------

    def _on_cycle_view(self, instance):
        self._view_mode_idx = (self._view_mode_idx + 1) % len(self._view_modes)
        label, n_tracks, agg = self._view_modes[self._view_mode_idx]
        self.btn_view_mode.text = f'View: {label}'

        # Restore channel_index when switching from Auto MAV to single-channel
        if n_tracks == 1 and agg is None:
            self.plot_single.channel_index = self._single_channel_idx

        # Rebuild multi-track widget if track count changed
        if n_tracks > 1:
            self._rebuild_multi_track(label, n_tracks)

        self._update_ch_bar_visibility()

        if self._active_tab == 'plot':
            self._show_active_plot_widget()

    def _rebuild_multi_track(self, mode_label, n_tracks):
        """Replace plot_multi with a fresh widget sized for n_tracks."""
        self._content.remove_widget(self.plot_multi)
        if mode_label.startswith('Row'):
            labels = [f'Row {i}' for i in range(n_tracks)]
        elif mode_label.startswith('Col'):
            labels = [f'Col {i}' for i in range(n_tracks)]
        else:
            labels = [f'C{i}' for i in range(n_tracks)]

        tw = CFG.PLOT_TIME_WINDOW_PRESETS[self._time_window_idx]
        self.plot_multi = MultiTrackPlotWidget(
            track_labels=labels,
            display_samples=tw['display_samples'], downsample=tw['downsample'],
            size_hint=(1, 1), pos_hint={'x': 0, 'y': 0},
        )
        self.plot_multi.opacity = 0
        self._content.add_widget(self.plot_multi)

    # ------------------------------------------------------------------
    # Time window cycling
    # ------------------------------------------------------------------

    def _on_cycle_time_window(self, instance):
        presets = CFG.PLOT_TIME_WINDOW_PRESETS
        self._time_window_idx = (self._time_window_idx + 1) % len(presets)
        tw = presets[self._time_window_idx]
        self.btn_time_window.text = f'Time: {tw["label"]}'
        self._rebuild_plot_widgets()

    def _rebuild_plot_widgets(self):
        """Recreate both plot widgets with the current time window preset."""
        tw = CFG.PLOT_TIME_WINDOW_PRESETS[self._time_window_idx]
        ds = tw['display_samples']
        dn = tw['downsample']

        # Rebuild single-channel plot
        self._content.remove_widget(self.plot_single)
        self.plot_single = EMGPlotWidget(
            channel_index=self._single_channel_idx,
            display_samples=ds, downsample=dn,
            size_hint=(1, 1), pos_hint={'x': 0, 'y': 0},
        )
        self._content.add_widget(self.plot_single)

        # Rebuild multi-track plot with current view mode labels
        label, n_tracks, _ = self._view_modes[self._view_mode_idx]
        self._rebuild_multi_track(label, max(n_tracks, 8))

        # Restore correct visibility
        if self._active_tab == 'plot':
            self._show_active_plot_widget()
            self.heatmap.opacity = 0
        else:
            self.plot_single.opacity = 0
            self.plot_multi.opacity = 0

    # ------------------------------------------------------------------
    # Channel selector
    # ------------------------------------------------------------------

    def _on_ch_input_submit(self, instance):
        try:
            val = int(instance.text)
        except ValueError:
            instance.text = str(self._single_channel_idx + 1)
            return
        # clamp to 1..HDSEMG_CHANNELS (64 EMG channels only, no aux)
        val = max(1, min(val, CFG.HDSEMG_CHANNELS))
        self._single_channel_idx = val - 1
        instance.text = str(val)
        self._apply_channel_change()

    def _apply_channel_change(self):
        ch = self._single_channel_idx
        self.plot_single.channel_index = ch
        self.plot_single.reset_scale()
        # Update the Single Ch entry label in advanced view modes
        for i, (label, n, agg) in enumerate(self._view_modes):
            if n == 1 and agg is None:
                self._view_modes[i] = (f'Single Ch{ch + 1}', 1, None)
                if self._view_mode_idx == i:
                    self.btn_view_mode.text = f'View: Single Ch{ch + 1}'
                break

    def _update_ch_bar_visibility(self):
        """Show channel bar only in single-channel view (not Auto MAV)."""
        _, n_tracks, agg = self._view_modes[self._view_mode_idx]
        self._set_ch_bar_visible(n_tracks == 1 and agg != 'auto_mav')

    def _set_ch_bar_visible(self, visible):
        self._ch_bar.opacity = 1 if visible else 0
        self._ch_bar.disabled = not visible
        for child in self._ch_bar.children:
            child.disabled = not visible

    # ------------------------------------------------------------------
    # Battery polling (HTTP, independent of TCP streaming)
    # ------------------------------------------------------------------

    def _start_battery_poll(self):
        self._poll_battery()  # immediate first query
        self._battery_event = Clock.schedule_interval(
            lambda dt: self._poll_battery(), CFG.BATTERY_POLL_INTERVAL
        )

    def _stop_battery_poll(self):
        if hasattr(self, '_battery_event') and self._battery_event:
            self._battery_event.cancel()
            self._battery_event = None

    def _poll_battery(self):
        def query():
            level = self.device.get_battery_level()
            Clock.schedule_once(lambda dt: self._update_battery_display(level), 0)
        threading.Thread(target=query, daemon=True).start()

    def _update_battery_display(self, level):
        if level is None:
            self.battery_label.text = 'Bat: --'
            self.battery_label.color = (0.5, 0.5, 0.5, 1)
        else:
            if level <= CFG.BATTERY_LOW_THRESHOLD:
                color = CFG.BATTERY_LOW_COLOR
            elif level <= CFG.BATTERY_MED_THRESHOLD:
                color = CFG.BATTERY_MED_COLOR
            else:
                color = CFG.BATTERY_OK_COLOR
            self.battery_label.text = f'Bat: {level}%'
            self.battery_label.color = color

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_back(self, instance):
        self._stop_battery_poll()
        if self.streaming_controller and self.streaming_controller.is_streaming:
            self.streaming_controller.stop_streaming()
        self.manager.current = 'selection'

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def _on_toggle_stream(self, instance):
        if self.streaming_controller and self.streaming_controller.is_streaming:
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self):
        # Quick network check on main thread — avoids a 15-second wait on wrong network
        if not self.device.is_connected_to_device_network():
            self._set_status('No device network')
            self._set_bottom(
                'Not connected to the Sessantaquattro+ WiFi. '
                'Connect to the device network and try again.'
            )
            return

        self.btn_stream.disabled = True
        self.btn_stream.text = 'Connecting...'
        self._set_status('Waiting for device...')

        def connect():
            try:
                self.device.start_server(connection_timeout=CFG.DEVICE_CONNECT_TIMEOUT)
                command = self.device.create_command(
                    FSAMP=CFG.DEVICE_FSAMP, NCH=CFG.DEVICE_NCH,
                    MODE=CFG.DEVICE_MODE,   HPF=CFG.DEVICE_HPF, GO=1,
                )
                self.device.send_command(command)
                Clock.schedule_once(self._on_connected, 0)
            except Exception as e:
                err_msg = str(e)
                Clock.schedule_once(lambda dt: self._on_connect_error(err_msg), 0)

        threading.Thread(target=connect, daemon=True).start()

    def _on_connected(self, dt):
        filters.reset_live_filters()
        self._envelope_filter.reset()
        self._metrics_computer.reset()
        self._pending_metrics = None
        self.receiver_thread = DataReceiverThread(
            device=self.device,
            client_socket=self.device.client_socket,
            on_stage=self._on_data,
            on_error=lambda msg: Clock.schedule_once(
                lambda dt: self._on_receiver_error(msg), 0
            ),
            on_status=lambda msg: Clock.schedule_once(
                lambda dt: self._set_status(msg), 0
            ),
        )

        self.receiver_thread.on_disconnect = lambda elapsed: Clock.schedule_once(
            lambda dt: self._on_disconnect_warning(elapsed), 0
        )

        self.streaming_controller = StreamingController(
            update_callback=self._ui_tick,
            receiver_thread=self.receiver_thread,
            on_status=self._set_status,
        )

        self.plot_single.reset_scale()
        self.plot_multi.reset_scale()
        self.streaming_controller.start_streaming()
        self.btn_stream.text = 'Stream'
        self.btn_stream.background_color = CFG.BTN_STREAM_ACTIVE
        self.btn_stream.color = (0.2, 1.0, 0.2, 1.0)
        self.btn_stream.disabled = False
        self.btn_calibrate.disabled = False
        self._set_status('Streaming...')
        self._set_bottom('Connected — receiving data.')

    def _on_connect_error(self, message):
        self.device.stop_server()  # clean up sockets for next attempt
        self.btn_stream.text = 'Stream'
        self.btn_stream.background_color = CFG.BTN_STREAM_IDLE
        self.btn_stream.color = (1, 1, 1, 1)
        self.btn_stream.disabled = False
        self._set_status('Connection failed')
        self._set_bottom(f'Error: {message}')

    def _stop_stream(self):
        if self.streaming_controller:
            self.streaming_controller.stop_streaming()
        self.btn_stream.text = 'Stream'
        self.btn_stream.background_color = CFG.BTN_STREAM_IDLE
        self.btn_stream.color = (1, 1, 1, 1)
        self.btn_calibrate.disabled = True
        self.btn_record.disabled = True
        self._set_status('Stream stopped')

    def _on_receiver_error(self, message):
        self._set_bottom(f'Receiver error: {message}')
        self._stop_stream()

    def _on_disconnect_warning(self, elapsed):
        self._disconnect_label.text = f'SIGNAL LOST - No data for {elapsed:.0f}s'
        self._disconnect_label.opacity = 1

    def _clear_disconnect_warning(self):
        self._disconnect_label.opacity = 0

    # ------------------------------------------------------------------
    # Data callback (receiver thread → stored for 60fps tick)
    # ------------------------------------------------------------------

    def _on_data(self, stage, data):
        """Called by the receiver thread for every processed packet.

        Kept minimal to avoid slowing the receiver thread.  Heavy
        computation (envelope, metrics, contraction) moved to _ui_tick.
        """
        # Recording — forward raw data directly on the receiver thread
        self.recording_manager.on_data_for_recording(stage, data)

        # Clipping detection on raw (pre-filter) data
        if stage == 'raw':
            clipped = self._clipping_detector.check(data)
            if clipped:
                self._pending_clipping = clipped

        # Calibration listener
        if self._calibration_extra_callback is not None:
            self._calibration_extra_callback(stage, data)

        # Accumulate final-stage packets for the UI tick (no overwrite)
        if stage == 'final':
            self._pending_packets.append(data)

    def _ui_tick(self, dt):
        """30fps Kivy Clock tick — drain ALL accumulated packets and render."""
        packets = self._pending_packets
        if not packets:
            return
        self._pending_packets = []

        # Concatenate all accumulated packets along sample axis
        data = np.concatenate(packets, axis=1)

        # Debug diagnostics — log every 30 frames (~1s) to logcat
        self._tick_count += 1
        if self._tick_count % 30 == 0:
            now = time.time()
            avg_dt = (now - self._last_tick_time) * 1000 / 30
            self._last_tick_time = now
            lat = self._latency_window[-1] if self._latency_window else 0
            print(f"[DEBUG] ui_tick: pkts={len(packets)} samples={data.shape[1]} "
                  f"avg_dt={avg_dt:.1f}ms lat={lat:.0f}ms")

        # Clear disconnect warning on data resume
        if self._disconnect_label.opacity > 0:
            self._clear_disconnect_warning()

        # Update latency indicator
        recv_time = self.receiver_thread._pending_recv_time if self.receiver_thread else None
        if recv_time is not None:
            latency_ms = (time.time() - recv_time) * 1000
            self._latency_window.append(latency_ms)
            if len(self._latency_window) > CFG.LATENCY_ROLLING_WINDOW:
                self._latency_window.pop(0)
            avg_lat = sum(self._latency_window) / len(self._latency_window)
            self.latency_label.text = f'Lat: {avg_lat:.0f}ms'
            if avg_lat > CFG.LATENCY_WARNING_MS:
                self.latency_label.color = (1, 0.2, 0.2, 1)
            else:
                self.latency_label.color = (0.3, 1, 0.3, 1)

        # --- Computation moved here from receiver thread ---

        # Auto MAV: envelope + channel selection
        envelope_pending = None
        if data.shape[0] >= CFG.HDSEMG_CHANNELS:
            hd = data[:CFG.HDSEMG_CHANNELS]
            if not self.is_calibrated:
                mav_values = np.mean(np.abs(hd), axis=1)
                self._auto_mav_channel = int(np.argmax(mav_values))
            envelope = self._envelope_filter(np.abs(hd))
            envelope_pending = envelope[self._auto_mav_channel]

        # Metrics computation
        active_ch = self._get_active_channel_index()
        if active_ch < data.shape[0]:
            result = self._metrics_computer.update(data[active_ch])
            if result is not None:
                self._pending_metrics = result

        # Contraction detection
        if self.is_calibrated and self.threshold is not None:
            ch0_rms = float(np.sqrt(np.mean(data[0] ** 2)))
            if ch0_rms > self.threshold[0]:
                self._contraction_color = CFG.CONTRACTION_ACTIVE
            else:
                self._contraction_color = CFG.CONTRACTION_INACTIVE

        # Update contraction label color
        self.contraction_label.color = self._contraction_color

        # Update metrics bar
        m = self._pending_metrics
        if m is not None:
            self._lbl_rms.text = f'RMS: {m["rms"]:.1f}'
            self._lbl_mf.text = f'MF: {m["median_freq"]:.1f} Hz'
            fatigue = m['fatigue_rms'] or m['fatigue_mf']
            self._lbl_fatigue.text = 'Fatigue: YES' if fatigue else 'Fatigue: No'
            self._lbl_fatigue.color = (1, 0.3, 0.3, 1) if fatigue else (0.3, 1, 0.3, 1)
            self._lbl_active_ch.text = f'Ch: {self._get_active_channel_index() + 1}'

        # Update clipping indicator
        if self._pending_clipping:
            ch_str = ', '.join(str(c + 1) for c in self._pending_clipping[:5])
            self._lbl_clipping.text = f'CLIP: Ch {ch_str}'
            self._pending_clipping = []
        else:
            self._lbl_clipping.text = ''

        if self._active_tab == 'plot':
            self._render_plot_panel(data, envelope_pending)
        else:
            self._render_heatmap_panel(data)

    def _render_plot_panel(self, data, envelope_pending=None):
        label, n_tracks, agg_fn = self._view_modes[self._view_mode_idx]
        if agg_fn == 'auto_mav':
            envelope = envelope_pending
            if envelope is not None:
                # Feed envelope as a single-channel (1, samples) array at channel 0
                self.plot_single.channel_index = 0
                self.plot_single.update(envelope[np.newaxis, :])
                self.plot_single.render()
                ch = self._auto_mav_channel
                self.btn_view_mode.text = f'View: Auto MAV: Ch{ch + 1}'
        elif n_tracks == 1:
            self.plot_single.update(data)
            self.plot_single.render()
        else:
            if data.shape[0] < CFG.HDSEMG_CHANNELS:
                return
            aggregated = agg_fn(data)  # (n_tracks, samples)
            for i in range(min(n_tracks, aggregated.shape[0])):
                self.plot_multi.update_track(i, aggregated[i])
            self.plot_multi.render()

    def _render_heatmap_panel(self, data):
        if data.shape[0] < CFG.HDSEMG_CHANNELS:
            return
        if not self.is_calibrated or self.mvc_rms is None:
            return
        # Accumulate samples into rolling buffer, compute per-channel RMS
        hd = data[:CFG.HDSEMG_CHANNELS]
        buf_len = CFG.HEATMAP_BUFFER_SAMPLES
        # When concatenated packets exceed buf_len, keep only the tail
        if hd.shape[1] > buf_len:
            hd = hd[:, -buf_len:]
        n = hd.shape[1]
        # Vectorised circular-buffer write — replaces O(n) Python for-loop
        start = self._heatmap_buf_idx % buf_len
        if start + n <= buf_len:
            self._heatmap_buffer[:, start:start + n] = hd
        else:
            split = buf_len - start
            self._heatmap_buffer[:, start:]    = hd[:, :split]
            self._heatmap_buffer[:, :n - split] = hd[:, split:]
        self._heatmap_buf_idx += n

        rms = np.sqrt(np.mean(self._heatmap_buffer ** 2, axis=1))  # (64,)

        mvc = self.mvc_rms[:CFG.HDSEMG_CHANNELS]
        mvc = np.where(mvc > 0, mvc, 1.0)
        normalized = np.clip(rms / mvc, 0.0, 1.0)

        self.heatmap.update(normalized)

        # Show highlight on auto MAV channel in Basic mode (always) or
        # Advanced mode (only when Auto MAV view is active)
        _, _, agg = self._view_modes[self._view_mode_idx]
        if self._mode == 'basic' or agg == 'auto_mav':
            self.heatmap.set_highlight(self._auto_mav_channel)
        else:
            self.heatmap.clear_highlight()

    def _update_contraction(self, color):
        self.contraction_label.color = color

    def _get_active_channel_index(self):
        """Return the channel index currently being displayed."""
        _, n_tracks, agg = self._view_modes[self._view_mode_idx]
        if agg == 'auto_mav':
            return self._auto_mav_channel
        if n_tracks == 1:
            return self._single_channel_idx
        return 0

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def _on_calibrate(self, instance):
        if not (self.streaming_controller and self.streaming_controller.is_streaming):
            self._set_bottom('Start streaming before calibrating.')
            return

        popup = CalibrationPopup(
            on_complete=self._on_calibration_complete,
            on_sample_connect=self._register_calibration_callback,
            on_sample_disconnect=self._unregister_calibration_callback,
        )
        popup.start()

    def _register_calibration_callback(self, cb):
        self._calibration_extra_callback = cb

    def _unregister_calibration_callback(self, cb):
        self._calibration_extra_callback = None

    def _on_calibration_complete(self, baseline_rms, threshold, mvc_rms):
        self.baseline_rms = baseline_rms
        self.threshold = threshold
        self.mvc_rms = mvc_rms
        self.is_calibrated = True
        # Lock auto MAV channel to the one with highest MAV from calibration
        ref = mvc_rms if mvc_rms is not None else baseline_rms
        if ref is not None:
            self._auto_mav_channel = int(np.argmax(ref[:CFG.HDSEMG_CHANNELS]))
        self.btn_record.disabled = False
        self.btn_crosstalk.disabled = False
        # Pass baseline RMS of active channel to metrics computer
        active_ch = self._get_active_channel_index()
        if baseline_rms is not None and active_ch < len(baseline_rms):
            self._metrics_computer.set_baseline(float(baseline_rms[active_ch]))
        self._set_bottom('Calibration complete.')
        self._set_status('Calibrated')

    # ------------------------------------------------------------------
    # Crosstalk verification
    # ------------------------------------------------------------------

    def _on_crosstalk(self, instance):
        if not self.is_calibrated:
            self._set_bottom('Calibrate first.')
            return
        popup = CrosstalkVerificationPopup(
            baseline_rms=self.baseline_rms,
            on_complete=self._on_crosstalk_complete,
            on_sample_connect=self._register_calibration_callback,
            on_sample_disconnect=self._unregister_calibration_callback,
        )
        popup.start()

    def _on_crosstalk_complete(self, passed, flagged):
        if passed:
            self._set_bottom('Crosstalk check: PASS')
        else:
            ch_str = ', '.join(str(c + 1) for c in flagged[:5])
            self._set_bottom(f'Crosstalk check: WARNING — Ch {ch_str}')

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _on_toggle_record(self, instance):
        if self.recording_manager.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        popup = SessionMetadataPopup(on_confirm=self._on_metadata_confirmed)
        popup.open()

    def _on_metadata_confirmed(self, metadata):
        # Include calibration info if available
        if self.is_calibrated and self.baseline_rms is not None:
            metadata['calibration'] = {
                'baseline_rms': self.baseline_rms.tolist(),
                'mvc_rms': self.mvc_rms.tolist() if self.mvc_rms is not None else None,
                'threshold_means': self.threshold.tolist() if self.threshold is not None else None,
            }
        self.recording_manager.set_metadata(metadata)
        self.recording_manager.start_recording()
        self.btn_record.text = 'Record'
        self.btn_record.background_color = CFG.BTN_RECORD_ACTIVE
        self.btn_record.color = (1.0, 0.2, 0.2, 1.0)
        self._set_status('Recording...')

    def _stop_recording(self):
        self.recording_manager.stop_recording()
        self.btn_record.background_color = CFG.BTN_RECORD_SAVING
        self.btn_record.disabled = True

        def save():
            success, message, filename = self.recording_manager.save_recording_to_csv()
            Clock.schedule_once(lambda dt: self._on_save_done(success, message), 0)

        threading.Thread(target=save, daemon=True).start()

    def _on_save_done(self, success, message):
        self.btn_record.text = 'Record'
        self.btn_record.background_color = CFG.BTN_RECORD_IDLE
        self.btn_record.color = (1, 1, 1, 1)
        self.btn_record.disabled = False
        self._set_status('Saved' if success else 'Save failed')
        self._set_bottom(message)

    def _on_recording_overflow(self):
        Clock.schedule_once(lambda dt: self._stop_recording(), 0)
        Clock.schedule_once(
            lambda dt: self._set_bottom('Recording stopped: max samples reached.'), 0
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, text):
        self.status_label.text = text

    def _set_bottom(self, text):
        self.bottom_label.text = text

    def _on_status_update(self, text):
        Clock.schedule_once(lambda dt: self._set_status(text), 0)
