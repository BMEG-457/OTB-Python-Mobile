"""Post-session data analysis screen."""

import csv
import os
import threading
from datetime import datetime

import numpy as np

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.metrics import sp

from app.core import config as CFG
from app.processing.features import (
    compute_tkeo_activation_timing,
    compute_burst_duration,
    compute_fatigue,
    compute_bilateral_symmetry,
    compute_centroid_shift,
    compute_spatial_nonuniformity,
)


def _load_csv(filepath):
    """Load a recording CSV into (timestamps, data) arrays.

    Returns:
        (timestamps: np.ndarray shape (N,), data: np.ndarray shape (channels, N))
        or (None, None) on failure.
    """
    try:
        with open(filepath, newline='') as f:
            reader = csv.reader(f)
            headers = next(reader)
            rows = [list(map(float, row)) for row in reader]

        if not rows:
            return None, None

        arr = np.array(rows)
        timestamps = arr[:, 0]
        data = arr[:, 1:].T  # (channels, samples)
        return timestamps, data

    except Exception as e:
        print(f"[DataAnalysis] CSV load error: {e}")
        return None, None


def _estimated_fs(timestamps):
    """Estimate sample rate from timestamps."""
    fallback = float(CFG.DEVICE_SAMPLE_RATE)
    if len(timestamps) < 2:
        return fallback
    dt = np.diff(timestamps)
    dt = dt[dt > 0]
    return float(1.0 / np.median(dt)) if len(dt) > 0 else fallback


class DataAnalysisScreen(Screen):
    """Offline post-session analysis screen.

    Equivalent to the desktop's DataAnalysisWindow. Allows loading one or two
    CSV recording files and running all feature analyses from features.py.
    Results are displayed as scrollable text; plots open in separate popups.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Loaded recording state
        self._file1 = None
        self._ts1 = None
        self._data1 = None
        self._file2 = None
        self._ts2 = None
        self._data2 = None

        self._pending_bilateral = False
        self._feature_store = {}

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = BoxLayout(orientation='vertical')

        # Top bar
        top_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.08), padding=4, spacing=4)
        btn_back = Button(text='Back', size_hint=(0.1, 1), font_size=sp(16))
        btn_back.bind(on_press=lambda x: setattr(self.manager, 'current', 'selection'))
        top_bar.add_widget(btn_back)
        top_bar.add_widget(Label(text='Data Analysis', font_size=sp(22), bold=True, size_hint=(0.6, 1)))
        root.add_widget(top_bar)

        # File load bar
        file_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.08), padding=4, spacing=4)

        btn_load1 = Button(text='Load File 1', size_hint=(0.18, 1), font_size=sp(15))
        btn_load1.bind(on_press=lambda x: self._show_file_chooser(1))
        self.file1_label = Label(text='No file loaded', size_hint=(0.35, 1), font_size=sp(14),
                                 color=(0.7, 0.7, 0.7, 1), shorten=True,
                                 shorten_from='right')
        self.file1_label.bind(size=lambda inst, val: setattr(inst, 'text_size', (inst.width, None)))
        self.file2_label = Label(text='File 2: not loaded (bilateral symmetry)',
                                 size_hint=(0.35, 1), font_size=sp(14), color=(0.7, 0.7, 0.7, 1),
                                 shorten=True, shorten_from='right')
        self.file2_label.bind(size=lambda inst, val: setattr(inst, 'text_size', (inst.width, None)))
        btn_plot = Button(text='Plot Data', size_hint=(0.12, 1), font_size=sp(15))
        btn_plot.bind(on_press=self._show_plot)

        file_bar.add_widget(btn_load1)
        file_bar.add_widget(self.file1_label)
        file_bar.add_widget(self.file2_label)
        file_bar.add_widget(btn_plot)
        root.add_widget(file_bar)

        # Channel selector
        ch_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.075), padding=4, spacing=4)
        ch_bar.add_widget(Label(text='Channel:', size_hint=(0.15, 1), font_size=sp(15)))
        self.channel_input = TextInput(text='1', size_hint=(0.12, 1), font_size=sp(15),
                                       input_filter='int', multiline=False, halign='center')
        ch_bar.add_widget(self.channel_input)
        ch_bar.add_widget(Label(size_hint=(0.58, 1)))  # spacer
        btn_export = Button(text='Export', size_hint=(0.15, 1), font_size=sp(15))
        btn_export.bind(on_press=self._on_export_results)
        ch_bar.add_widget(btn_export)
        root.add_widget(ch_bar)

        # Analysis buttons
        btn_grid = GridLayout(cols=3, size_hint=(1, 0.12), padding=4, spacing=4)
        analyses = [
            ('Activation Timing', self._run_tkeo),
            ('Burst Duration', self._run_burst),
            ('Fatigue', self._run_fatigue),
            ('Bilateral Symmetry', self._run_bilateral),
            ('Centroid Shift', self._run_centroid),
            ('Spatial Uniformity', self._run_spatial),
        ]
        for label, handler in analyses:
            btn = Button(text=label, font_size=sp(15))
            btn.bind(on_press=handler)
            btn_grid.add_widget(btn)
        root.add_widget(btn_grid)

        # Results area (scrollable)
        scroll = ScrollView(size_hint=(1, 0.645))
        self.results_label = Label(
            text='Load a recording file and run an analysis.',
            font_size=sp(15),
            halign='left',
            valign='top',
            size_hint_y=None,
        )
        self.results_label.bind(
            texture_size=lambda inst, val: setattr(inst, 'size', val),
            width=lambda inst, w: setattr(inst, 'text_size', (w, None)),
        )
        scroll.add_widget(self.results_label)
        root.add_widget(scroll)

        self.add_widget(root)

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _show_file_chooser(self, slot):
        """Navigable file browser popup starting at /sdcard/Documents.

        Shows subdirectories and CSV files.  Tap a directory to enter it;
        tap a CSV to select it.  A '[..] Up' row returns to the parent.
        """
        # Test actual readability — os.path.isdir can succeed even when
        # os.listdir is denied (different syscalls, different permission checks).
        # user_data_dir (private internal storage) is always accessible and is
        # where recordings fall back to if external storage permission is not
        # yet in effect (requires app restart after grant).
        package = CFG.ANDROID_PACKAGE_NAME

        # Try Android API first — may succeed where direct POSIX access is blocked.
        _jnius_ext = None
        try:
            from jnius import autoclass as _ac
            _ext = _ac('org.kivy.android.PythonActivity').mActivity.getExternalFilesDir(None)
            if _ext is not None:
                _jnius_ext = _ext.getAbsolutePath()
        except Exception:
            pass

        try:
            from kivy.app import App as _App
            _udd = _App.get_running_app().user_data_dir
        except Exception:
            _udd = None

        start_dir = None
        for candidate in filter(None, (
            _jnius_ext,
            f'/storage/emulated/0/Android/data/{package}/files',
            '/storage/emulated/0/Documents',
            '/sdcard/Documents',
            '/storage/emulated/0',
            '/sdcard',
            _udd,
        )):
            try:
                os.listdir(candidate)
                start_dir = candidate
                break
            except Exception:
                continue

        content = BoxLayout(orientation='vertical', spacing=4, padding=4)

        if start_dir is None:
            # No accessible path found — storage permission not yet in effect.
            # User must close and reopen the app after granting permission.
            content = BoxLayout(orientation='vertical', padding=16, spacing=12)
            content.add_widget(Label(
                text=(
                    'Storage not accessible.\n\n'
                    'If you just granted the storage permission,\n'
                    'close and reopen the app for it to take effect.\n\n'
                    'Recordings are saved to:\n'
                    'Android > data > org.bmeg457.otbemgapp\n'
                    '> files > OTB_EMG > recordings'
                ),
                font_size=sp(15), halign='center', valign='middle',
                size_hint=(1, 0.88),
            ))
            btn_cancel2 = Button(text='OK', font_size=sp(16), size_hint=(1, 0.12))
            popup2 = Popup(
                title='Storage unavailable', content=content,
                size_hint=(0.85, 0.55),
            )
            btn_cancel2.bind(on_press=lambda x: popup2.dismiss())
            content.add_widget(btn_cancel2)
            popup2.open()
            return

        path_label = Label(
            text=start_dir, font_size=sp(12), size_hint=(1, None), height=sp(28),
            halign='left', color=(0.5, 0.75, 1, 1),
        )
        path_label.bind(size=lambda inst, _: setattr(inst, 'text_size', (inst.width, None)))
        content.add_widget(path_label)

        scroll = ScrollView(size_hint=(1, 0.82))
        file_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=2)
        file_list.bind(minimum_height=file_list.setter('height'))
        scroll.add_widget(file_list)
        content.add_widget(scroll)

        btn_cancel = Button(text='Cancel', font_size=sp(16), size_hint=(1, 0.1))
        content.add_widget(btn_cancel)

        popup = Popup(title=f'Select File {slot}', content=content, size_hint=(0.92, 0.92))
        btn_cancel.bind(on_press=lambda x: popup.dismiss())

        def populate(directory, scroll_to_name=None):
            file_list.clear_widgets()
            path_label.text = directory
            scroll_target = None

            # Up-one-level row
            parent = os.path.dirname(directory)
            if parent and parent != directory:
                up_btn = Button(
                    text='[..] Up', font_size=sp(15),
                    size_hint_y=None, height=sp(48),
                    background_color=(0.25, 0.30, 0.45, 1),
                )
                up_btn.bind(on_press=lambda x, p=parent, d=os.path.basename(directory):
                            populate(p, scroll_to_name=d))
                file_list.add_widget(up_btn)

            try:
                entries = sorted(os.listdir(directory))
            except Exception as e:
                file_list.add_widget(Label(
                    text=f'Cannot read folder:\n{e}',
                    font_size=sp(14), size_hint_y=None, height=sp(60),
                ))
                return

            dirs = [e for e in entries if os.path.isdir(os.path.join(directory, e))
                    and not e.startswith('.')]
            csvs = [e for e in entries if e.lower().endswith('.csv')]

            for d in dirs:
                dpath = os.path.join(directory, d)
                btn = Button(
                    text=f'[{d}/]', font_size=sp(15),
                    size_hint_y=None, height=sp(48),
                    background_color=(0.22, 0.32, 0.50, 1),
                )
                btn.bind(on_press=lambda x, p=dpath: populate(p))
                file_list.add_widget(btn)
                if d == scroll_to_name:
                    scroll_target = btn

            if scroll_target is not None:
                from kivy.clock import Clock
                def do_scroll(dt):
                    scroll.scroll_to(scroll_target)
                Clock.schedule_once(do_scroll, 0)

            for fname in csvs:
                fpath = os.path.join(directory, fname)
                btn = Button(
                    text=fname, font_size=sp(14),
                    size_hint_y=None, height=sp(48),
                )
                btn.bind(on_press=lambda x, p=fpath: (self._load_file(slot, p), popup.dismiss()))
                file_list.add_widget(btn)

            if not dirs and not csvs:
                file_list.add_widget(Label(
                    text='No folders or CSV files here.',
                    font_size=sp(14), size_hint_y=None, height=sp(48),
                    halign='center',
                ))

        populate(start_dir)
        popup.open()

    def _load_file(self, slot, path):
        """Load a CSV file into slot 1 or 2."""
        name = os.path.basename(path)
        self._set_results(f'Loading {name}...')

        def load():
            ts, data = _load_csv(path)
            Clock.schedule_once(lambda dt: self._on_file_loaded(slot, path, name, ts, data), 0)

        threading.Thread(target=load, daemon=True).start()

    def _on_file_loaded(self, slot, path, name, ts, data):
        if ts is None:
            self._set_results(f'Failed to load {name}. Check file format.')
            return

        if slot == 1:
            self._file1, self._ts1, self._data1 = path, ts, data
            self._feature_store = {}
            self.file1_label.text = f'{name} ({data.shape[0]} ch, {data.shape[1]} samples)'
        else:
            self._file2, self._ts2, self._data2 = path, ts, data
            self.file2_label.text = f'File 2: {name} ({data.shape[0]} ch, {data.shape[1]} samples)'

        self._set_results(f'Loaded {name} into slot {slot}.')

        if slot == 2 and self._pending_bilateral:
            self._pending_bilateral = False
            self._do_run_bilateral()

    # ------------------------------------------------------------------
    # Analysis runners
    # ------------------------------------------------------------------

    def _require_file1(self):
        if self._data1 is None:
            self._set_results('Load a recording file first.')
            return False
        return True

    def _selected_channel(self, data=None):
        """Return 0-based channel index from the channel input, or None if invalid."""
        if data is None:
            data = self._data1
        try:
            ch = int(self.channel_input.text) - 1
        except (ValueError, TypeError):
            return None
        if data is None or ch < 0 or ch >= data.shape[0]:
            return None
        return ch

    def _store_feature(self, type_key, ch_idx, result, meta=None):
        """Accumulate a feature result, replacing any prior entry for the same channel."""
        if type_key not in self._feature_store:
            self._feature_store[type_key] = {'results': [], 'meta': {}}
        results = self._feature_store[type_key]['results']
        self._feature_store[type_key]['results'] = [
            (ci, r) for ci, r in results if ci != ch_idx
        ]
        self._feature_store[type_key]['results'].append((ch_idx, result))
        if meta is not None:
            self._feature_store[type_key]['meta'] = meta

    def _run_tkeo(self, instance):
        if not self._require_file1():
            return
        ch_idx = self._selected_channel()
        if ch_idx is None:
            self._set_results(f'Invalid channel number. Enter 1–{self._data1.shape[0]}.')
            return
        ch_num = ch_idx + 1
        self._set_results('Running activation timing analysis...')

        def run():
            ch = self._data1[ch_idx]
            fs = _estimated_fs(self._ts1)
            result = compute_tkeo_activation_timing(ch, self._ts1, fs)
            if result is None:
                text = 'Activation timing: analysis failed (check data quality).'
            else:
                self._store_feature('tkeo', ch_idx, result)
                n = len(result.onset_times)
                times = ', '.join(f'{t:.2f}s' for t in result.onset_times[:10])
                suffix = '...' if n > 10 else ''
                text = (
                    f'Activation Timing (TKEO) — Channel {ch_num}\n'
                    f'  Onsets detected: {n}\n'
                    f'  Detection threshold: {result.detection_threshold:.4f}\n'
                    f'  Sample rate: {result.sample_rate:.0f} Hz\n'
                    f'  Onset times: {times}{suffix}'
                )
            Clock.schedule_once(lambda dt: self._set_results(text), 0)

        threading.Thread(target=run, daemon=True).start()

    def _run_burst(self, instance):
        if not self._require_file1():
            return
        ch_idx = self._selected_channel()
        if ch_idx is None:
            self._set_results(f'Invalid channel number. Enter 1–{self._data1.shape[0]}.')
            return
        ch_num = ch_idx + 1
        self._set_results('Running burst duration analysis...')

        def run():
            ch = self._data1[ch_idx]
            fs = _estimated_fs(self._ts1)
            result = compute_burst_duration(ch, self._ts1, fs)
            if result is None:
                text = 'Burst duration: analysis failed.'
            else:
                self._store_feature('burst', ch_idx, result)
                text = (
                    f'Burst Duration — Channel {ch_num}\n'
                    f'  Bursts detected: {result.num_bursts}\n'
                    f'  Average duration: {result.avg_duration:.3f} s\n'
                    f'  Std deviation: {result.std_duration:.3f} s'
                )
                if result.num_bursts > 0:
                    durs = ', '.join(f'{d:.3f}s' for d in result.burst_durations[:8])
                    text += f'\n  Individual durations: {durs}'
            Clock.schedule_once(lambda dt: self._set_results(text), 0)

        threading.Thread(target=run, daemon=True).start()

    def _run_fatigue(self, instance):
        if not self._require_file1():
            return
        ch_idx = self._selected_channel()
        if ch_idx is None:
            self._set_results(f'Invalid channel number. Enter 1–{self._data1.shape[0]}.')
            return
        ch_num = ch_idx + 1
        self._set_results('Running fatigue analysis...')

        def run():
            ch = self._data1[ch_idx]
            fs = _estimated_fs(self._ts1)
            result = compute_fatigue(ch, self._ts1, fs)
            if result is None:
                text = 'Fatigue: analysis failed.'
            else:
                self._store_feature('fatigue', ch_idx, result)
                rms_onset = (
                    f'{result.time_to_rms_fatigue[0]:.2f} s'
                    if result.time_to_rms_fatigue is not None else 'Not detected'
                )
                mf_onset = (
                    f'{result.time_to_mf_fatigue[0]:.2f} s'
                    if result.time_to_mf_fatigue is not None else 'Not detected'
                )
                text = (
                    f'Fatigue Analysis — Channel {ch_num}\n'
                    f'  Baseline RMS: {result.baseline_rms:.4f}\n'
                    f'  RMS fatigue onset: {rms_onset}\n'
                    f'    (threshold: +{result.rms_threshold*100:.1f}% increase)\n'
                    f'  Median frequency fatigue onset: {mf_onset}\n'
                    f'    (threshold: {result.mf_threshold:.2f} Hz/s decline)'
                )
            Clock.schedule_once(lambda dt: self._set_results(text), 0)

        threading.Thread(target=run, daemon=True).start()

    def _run_bilateral(self, instance):
        if self._data1 is None:
            self._set_results('Load File 1 first.')
            return
        ch_idx = self._selected_channel()
        if ch_idx is None:
            self._set_results(f'Invalid channel number. Enter 1–{self._data1.shape[0]}.')
            return
        if self._data2 is None:
            self._pending_bilateral = True
            self._show_file_chooser(2)
            return
        self._do_run_bilateral()

    def _do_run_bilateral(self):
        ch_idx = self._selected_channel()
        if ch_idx is None:
            self._set_results(f'Invalid channel number. Enter 1–{self._data1.shape[0]}.')
            return

        # For HD-EMG (64-channel, 8x8 grid) data, compare against the positional
        # mirror across the vertical axis so that anatomically symmetric muscles are
        # paired correctly (e.g. ch 8 on the left leg → ch 1 on the right leg).
        n_ch_1 = self._data1.shape[0]
        n_ch_2 = self._data2.shape[0]
        hd_channels = CFG.HDSEMG_CHANNELS   # 64
        hd_cols     = CFG.HDSEMG_GRID_COLS  # 8
        if n_ch_1 == hd_channels and n_ch_2 == hd_channels:
            # Grid is column-major, bottom-to-top: ch1 is bottom-left, ch8 is
            # top-left, ch9 is bottom of next column, ch57 is bottom-right.
            col = ch_idx // hd_cols   # 0 = leftmost column
            row = ch_idx % hd_cols    # 0 = bottom row
            mirror_col = (hd_cols - 1) - col
            ch_idx_2 = mirror_col * hd_cols + row
            mirror_note = f' (mirror ch {ch_idx_2 + 1} in File 2)'
        else:
            ch_idx_2 = ch_idx
            mirror_note = ''

        if ch_idx_2 >= n_ch_2:
            self._set_results(f'Mirror channel {ch_idx_2 + 1} out of range for File 2 ({n_ch_2} channels).')
            return
        ch_num = ch_idx + 1
        self._set_results('Running bilateral symmetry analysis...')

        def run():
            ch1 = self._data1[ch_idx]
            ch2 = self._data2[ch_idx_2]
            fs1 = _estimated_fs(self._ts1)
            fs2 = _estimated_fs(self._ts2)
            result = compute_bilateral_symmetry(ch1, self._ts1, fs1, ch2, self._ts2, fs2)
            if result is None:
                text = 'Bilateral symmetry: analysis failed.'
            else:
                self._feature_store['bilateral'] = {
                    'results': [(0, result)],
                    'meta': {
                        'file1': os.path.basename(self._file1) if self._file1 else '',
                        'file2': os.path.basename(self._file2) if self._file2 else '',
                        'ch1_idx': ch_idx, 'ch2_idx': ch_idx_2,
                    },
                }
                text = (
                    f'Bilateral Symmetry Index — Ch {ch_num} (File 1){mirror_note}\n'
                    f'  Mean SI: {result.mean_si:.4f}  '
                    f'(0 = symmetric, +1 = file1 dominant, -1 = file2 dominant)\n'
                    f'  Std SI: {result.std_si:.4f}\n'
                    f'  Max asymmetry: {result.max_asymmetry:.4f}\n'
                    f'  File 1 overall RMS: {result.rms_file1:.4f}\n'
                    f'  File 2 overall RMS: {result.rms_file2:.4f}\n'
                    f'  Overlap duration: {result.overlap_duration:.2f} s'
                )
            Clock.schedule_once(lambda dt: self._set_results(text), 0)

        threading.Thread(target=run, daemon=True).start()

    def _run_centroid(self, instance):
        if not self._require_file1():
            return
        if self._data1.shape[0] < 64:
            self._set_results(
                f'Centroid shift requires 64-channel HD-EMG data. '
                f'File has {self._data1.shape[0]} channels.'
            )
            return
        self._set_results('Running centroid shift analysis...')

        def run():
            fs = _estimated_fs(self._ts1)
            result = compute_centroid_shift(self._data1[:64], self._ts1, fs)
            if result is None:
                text = 'Centroid shift: analysis failed.'
            else:
                self._feature_store['centroid'] = {
                    'results': [(0, result)], 'meta': {},
                }
                text = (
                    f'Centroid Shift (HD-EMG 8x8 grid)\n'
                    f'  Initial centroid: ({result.initial_centroid[0]:.2f}, '
                    f'{result.initial_centroid[1]:.2f})\n'
                    f'  Total shift: {result.total_shift:.3f} electrode-units\n'
                    f'  Mean drift rate: {result.mean_drift_rate:.4f} electrode-units/s\n'
                    f'  Windows analyzed: {len(result.times)}'
                )
            Clock.schedule_once(lambda dt: self._set_results(text), 0)

        threading.Thread(target=run, daemon=True).start()

    def _run_spatial(self, instance):
        if not self._require_file1():
            return
        if self._data1.shape[0] < 64:
            self._set_results(
                f'Spatial non-uniformity requires 64-channel HD-EMG data. '
                f'File has {self._data1.shape[0]} channels.'
            )
            return
        self._set_results('Running spatial non-uniformity analysis...')

        def run():
            fs = _estimated_fs(self._ts1)
            result = compute_spatial_nonuniformity(self._data1[:64], self._ts1, fs)
            if result is None:
                text = 'Spatial non-uniformity: analysis failed.'
            else:
                self._feature_store['spatial'] = {
                    'results': [(0, result)], 'meta': {},
                }
                text = (
                    f'Spatial Non-Uniformity (HD-EMG 8x8 grid)\n'
                    f'  Threshold source: {result.threshold_source}\n'
                    f'  Mean CV (coefficient of variation): {np.mean(result.cv):.4f}\n'
                    f'    Higher = more spatially uneven activation\n'
                    f'  Mean Shannon entropy: {np.mean(result.entropy):.4f} bits '
                    f'(max 6.0 for 64 channels)\n'
                    f'    Higher = more uniform distribution\n'
                    f'  Mean activation fraction: {np.mean(result.activation_fraction):.3f} '
                    f'({np.mean(result.activation_fraction)*100:.1f}% of channels active)\n'
                    f'  Windows analyzed: {len(result.times)}'
                )
            Clock.schedule_once(lambda dt: self._set_results(text), 0)

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export_results(self, _):
        """Export processed signal and feature analysis results to CSV."""
        if self._data1 is None:
            self._set_results('Load a recording file first.')
            return

        src_dir = os.path.dirname(self._file1)
        base_name = os.path.splitext(os.path.basename(self._file1))[0]
        out_path = os.path.join(src_dir, f'{base_name}_export.csv')

        try:
            with open(out_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                self._write_export_metadata(w)
                headers, rows = self._build_export_table()
                if headers:
                    w.writerow(headers)
                    w.writerows(rows)
                else:
                    w.writerow(['# No analyses have been run'])
            self._set_results(f'Export saved to:\n{out_path}')
        except Exception as e:
            self._set_results(f'Export failed: {e}')

    def _write_export_metadata(self, w):
        """Write comment rows with file info and feature summaries."""
        ts = self._ts1
        base_time = ts[0]
        fs = _estimated_fs(ts)

        w.writerow(['# OTB-EMG Analysis Export'])
        w.writerow([f'# Source: {os.path.basename(self._file1)}'])
        w.writerow([f'# Exported: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
        w.writerow([f'# Channels: {self._data1.shape[0]}'])
        w.writerow([f'# Sample rate: {fs:.1f} Hz'])
        w.writerow([f'# Duration: {ts[-1] - ts[0]:.3f} s'])
        w.writerow([])

        # Filter state from the plot screen (if available)
        try:
            plot_screen = self.manager.get_screen('analysis_plot')
            w.writerow([f'# Bandpass: {plot_screen._filt_bandpass}'])
            w.writerow([f'# Notch: {plot_screen._filt_notch}'])
            w.writerow([f'# Rectified: {plot_screen._filt_rectify}'])
            w.writerow([f'# Envelope: {plot_screen._filt_envelope}'])
        except Exception:
            pass

        if 'tkeo' in self._feature_store:
            for ch_idx, result in self._feature_store['tkeo']['results']:
                w.writerow([
                    f'# TKEO Ch{ch_idx + 1}: onsets={len(result.onset_times)}, '
                    f'detect_thresh={result.detection_threshold:.8f}, '
                    f'backtrack_thresh={result.backtrack_threshold:.8f}'
                ])

        if 'burst' in self._feature_store:
            for ch_idx, result in self._feature_store['burst']['results']:
                w.writerow([
                    f'# Burst Ch{ch_idx + 1}: bursts={result.num_bursts}, '
                    f'avg_duration={result.avg_duration:.4f}s, '
                    f'std_duration={result.std_duration:.4f}s'
                ])

        if 'bilateral' in self._feature_store:
            meta = self._feature_store['bilateral']['meta']
            _, result = self._feature_store['bilateral']['results'][0]
            w.writerow([
                f'# Bilateral: file1={meta.get("file1", "")}/Ch{meta.get("ch1_idx", 0) + 1} '
                f'vs file2={meta.get("file2", "")}/Ch{meta.get("ch2_idx", 0) + 1}, '
                f'overlap={result.overlap_duration:.3f}s, '
                f'mean_SI={result.mean_si:+.6f}, std_SI={result.std_si:.6f}, '
                f'max_asym={result.max_asymmetry:.6f}, '
                f'RMS1={result.rms_file1:.8f}, RMS2={result.rms_file2:.8f}'
            ])

        if 'fatigue' in self._feature_store:
            for ch_idx, result in self._feature_store['fatigue']['results']:
                rms_onset = (
                    f'{result.time_to_rms_fatigue[0] - base_time:.3f}s'
                    if result.time_to_rms_fatigue is not None and len(result.time_to_rms_fatigue) > 0
                    else 'not detected'
                )
                mf_onset = (
                    f'{result.time_to_mf_fatigue[0] - base_time:.3f}s'
                    if result.time_to_mf_fatigue is not None and len(result.time_to_mf_fatigue) > 0
                    else 'not detected'
                )
                w.writerow([
                    f'# Fatigue Ch{ch_idx + 1}: baseline_rms={result.baseline_rms:.8f}, '
                    f'rms_onset={rms_onset}, mf_onset={mf_onset}'
                ])

        if 'spatial' in self._feature_store:
            _, result = self._feature_store['spatial']['results'][0]
            w.writerow([
                f'# Spatial: threshold_source={result.threshold_source}, '
                f'mean_cv={float(result.cv.mean()):.6f}, '
                f'mean_entropy={float(result.entropy.mean()):.6f} bits, '
                f'mean_activation_frac={float(result.activation_fraction.mean()):.6f}'
            ])

        if 'centroid' in self._feature_store:
            _, result = self._feature_store['centroid']['results'][0]
            cx0, cy0 = result.initial_centroid
            w.writerow([
                f'# Centroid: initial=({cx0:.4f},{cy0:.4f}), '
                f'total_shift={result.total_shift:.6f} electrode-units, '
                f'mean_drift={result.mean_drift_rate:.6f} electrode-units/s'
            ])

        w.writerow([])

    def _build_export_table(self):
        """Build columnar export table. Returns (headers, rows)."""
        ts = self._ts1
        base_time = ts[0]
        headers = []
        columns = []

        # Signal columns — selected channel
        ch_idx = self._selected_channel()
        if ch_idx is not None:
            headers.append('time_s')
            columns.append([round(float(t), 6) for t in ts])
            headers.append(f'Ch{ch_idx + 1}_EMG')
            columns.append([round(float(v), 8) for v in self._data1[ch_idx]])

        # TKEO columns
        if 'tkeo' in self._feature_store:
            for ci, result in self._feature_store['tkeo']['results']:
                env_base = result.timestamps[0]
                headers += [
                    f'TKEO_Ch{ci + 1}_env_time_s',
                    f'TKEO_Ch{ci + 1}_envelope',
                    f'TKEO_Ch{ci + 1}_onset_num',
                    f'TKEO_Ch{ci + 1}_onset_time_s',
                ]
                columns.append([round(float(t) - env_base, 6) for t in result.timestamps])
                columns.append([round(float(v), 10) for v in result.tkeo_envelope])
                columns.append(list(range(1, len(result.onset_times) + 1)))
                columns.append([round(float(t) - base_time, 6) for t in result.onset_times])

        # Burst columns
        if 'burst' in self._feature_store:
            for ci, result in self._feature_store['burst']['results']:
                headers += [
                    f'Burst_Ch{ci + 1}_num',
                    f'Burst_Ch{ci + 1}_duration_s',
                ]
                columns.append(list(range(1, len(result.burst_durations) + 1)))
                columns.append([round(float(d), 6) for d in result.burst_durations])

        # Bilateral columns
        if 'bilateral' in self._feature_store:
            _, result = self._feature_store['bilateral']['results'][0]
            si_base = result.timestamps[0]
            headers += ['Bilateral_time_s', 'Bilateral_SI']
            columns.append([round(float(t) - si_base, 6) for t in result.timestamps])
            columns.append([round(float(v), 8) for v in result.symmetry_index])

        # Fatigue columns
        if 'fatigue' in self._feature_store:
            for ci, result in self._feature_store['fatigue']['results']:
                headers += [
                    f'Fatigue_Ch{ci + 1}_time_s',
                    f'Fatigue_Ch{ci + 1}_RMS',
                    f'Fatigue_Ch{ci + 1}_MF_Hz',
                ]
                columns.append([round(float(t) - base_time, 6) for t in result.rms_times])
                columns.append([round(float(r), 8) for r in result.rms_values])
                columns.append([round(float(m), 4) for m in result.mf_values])

        # Spatial columns
        if 'spatial' in self._feature_store:
            _, result = self._feature_store['spatial']['results'][0]
            headers += [
                'Spatial_time_s', 'Spatial_CV',
                'Spatial_entropy_bits', 'Spatial_activation_frac',
            ]
            columns.append([round(float(t) - base_time, 6) for t in result.times])
            columns.append([round(float(c), 6) for c in result.cv])
            columns.append([round(float(e), 6) for e in result.entropy])
            columns.append([round(float(a), 6) for a in result.activation_fraction])

        # Centroid columns
        if 'centroid' in self._feature_store:
            _, result = self._feature_store['centroid']['results'][0]
            headers += [
                'Centroid_time_s', 'Centroid_col',
                'Centroid_row', 'Centroid_disp',
            ]
            columns.append([round(float(t) - base_time, 6) for t in result.times])
            columns.append([round(float(x), 6) for x in result.centroid_x])
            columns.append([round(float(y), 6) for y in result.centroid_y])
            columns.append([round(float(d), 6) for d in result.displacement])

        if not columns:
            return headers, []

        max_rows = max(len(col) for col in columns)
        rows = []
        for i in range(max_rows):
            rows.append([col[i] if i < len(col) else '' for col in columns])

        return headers, rows

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_plot(self, _):
        if self._data1 is None:
            self._set_results('Load a file first to plot.')
            return
        plot_screen = self.manager.get_screen('analysis_plot')
        # Only reload data if the file changed
        if plot_screen._data is not self._data1:
            plot_screen.set_data(self._data1, self._ts1,
                                 filename=os.path.basename(self._file1))
        self.manager.current = 'analysis_plot'

    def _set_results(self, text):
        self.results_label.text = text
        self.results_label.text_size = (self.results_label.width, None)
