"""Longitudinal session history screen."""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.metrics import sp

from app.managers.session_history import SessionHistoryManager
from app.ui.widgets.trend_plot_widget import TrendPlotWidget


class LongitudinalScreen(Screen):
    """Session history with trend chart and session list.

    Layout:
        Top bar    [0.08] — Back + title
        Filter bar [0.07] — Subject, Muscle Group, and Exercise Type filters
        Chart      [0.45] — TrendPlotWidget
        Metric sel [0.07] — Peak RMS / Mean MF / Contractions buttons
        Session list[0.33] — ScrollView with session cards
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._history_mgr = SessionHistoryManager()
        self._sessions = []
        self._metric = 'peak_rms'
        self._build_ui()

    def on_enter(self):
        self._refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = BoxLayout(orientation='vertical')

        # Top bar
        top = BoxLayout(orientation='horizontal', size_hint=(1, 0.08), padding=4, spacing=4)
        btn_back = Button(text='Back', size_hint=(0.15, 1), font_size=sp(15))
        btn_back.bind(on_press=self._go_back)
        top.add_widget(btn_back)
        top.add_widget(Label(
            text='Session History', font_size=sp(20), bold=True, size_hint=(0.85, 1),
        ))
        root.add_widget(top)

        # Filter bar
        filt = BoxLayout(orientation='horizontal', size_hint=(1, 0.07), padding=4, spacing=8)
        filt.add_widget(Label(text='Subject:', size_hint=(0.10, 1), font_size=sp(14)))
        self._spn_subject = Spinner(
            text='All', values=['All'], size_hint=(0.18, 1), font_size=sp(14),
        )
        self._spn_subject.bind(text=lambda *a: self._apply_filter())
        filt.add_widget(self._spn_subject)

        filt.add_widget(Label(text='Muscle:', size_hint=(0.10, 1), font_size=sp(14)))
        self._spn_muscle = Spinner(
            text='All', values=['All'], size_hint=(0.20, 1), font_size=sp(14),
        )
        self._spn_muscle.bind(text=lambda *a: self._apply_filter())
        filt.add_widget(self._spn_muscle)

        filt.add_widget(Label(text='Exercise:', size_hint=(0.10, 1), font_size=sp(14)))
        self._spn_exercise = Spinner(
            text='All', values=['All'], size_hint=(0.20, 1), font_size=sp(14),
        )
        self._spn_exercise.bind(text=lambda *a: self._apply_filter())
        filt.add_widget(self._spn_exercise)

        btn_refresh = Button(text='Refresh', size_hint=(0.12, 1), font_size=sp(14))
        btn_refresh.bind(on_press=lambda inst: self._refresh())
        filt.add_widget(btn_refresh)

        root.add_widget(filt)

        # Trend chart
        self._chart = TrendPlotWidget(size_hint=(1, 0.40))
        root.add_widget(self._chart)

        # Metric selector
        metric_bar = BoxLayout(orientation='horizontal', size_hint=(1, 0.07), padding=4, spacing=4)
        for label, key in [('Peak RMS', 'peak_rms'), ('Median Freq', 'median_frequency'),
                           ('Contractions', 'contraction_count')]:
            btn = Button(text=label, font_size=sp(14), size_hint=(1, 1))
            btn.bind(on_press=lambda inst, k=key: self._set_metric(k))
            metric_bar.add_widget(btn)
        root.add_widget(metric_bar)

        # Session list
        scroll = ScrollView(size_hint=(1, 0.33))
        self._session_grid = GridLayout(
            cols=1, spacing=16, padding=12, size_hint_y=None,
        )
        self._session_grid.bind(minimum_height=self._session_grid.setter('height'))
        scroll.add_widget(self._session_grid)
        root.add_widget(scroll)

        self.add_widget(root)

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------

    def _go_back(self, instance):
        self.manager.current = 'selection'

    def _refresh(self):
        all_sessions = self._history_mgr.load_history()

        # Populate filter spinners
        subjects = sorted({s.get('subject_id', '') for s in all_sessions if s.get('subject_id')})
        muscles = sorted({s.get('muscle_group', '') for s in all_sessions if s.get('muscle_group')})
        exercises = sorted({s.get('exercise_type', '') for s in all_sessions if s.get('exercise_type')})
        self._spn_subject.values = ['All'] + subjects
        self._spn_muscle.values = ['All'] + muscles
        self._spn_exercise.values = ['All'] + exercises

        self._all_sessions = all_sessions
        self._apply_filter()

    def _apply_filter(self):
        sessions = self._all_sessions if hasattr(self, '_all_sessions') else []
        subj = self._spn_subject.text
        musc = self._spn_muscle.text
        exer = self._spn_exercise.text
        if subj != 'All':
            sessions = [s for s in sessions if s.get('subject_id') == subj]
        if musc != 'All':
            sessions = [s for s in sessions if s.get('muscle_group') == musc]
        if exer != 'All':
            sessions = [s for s in sessions if s.get('exercise_type') == exer]
        self._sessions = sessions
        self._update_chart()
        self._update_session_list()

    def _set_metric(self, key):
        self._metric = key
        self._update_chart()

    def _update_chart(self):
        dates = [s.get('date', '?') for s in self._sessions]
        values = [float(s.get(self._metric, 0)) for s in self._sessions]
        label_map = {
            'peak_rms': 'Peak RMS',
            'median_frequency': 'Median Freq (Hz)',
            'contraction_count': 'Contractions',
        }
        self._chart.set_data(dates, values, label_map.get(self._metric, self._metric))

    def _update_session_list(self):
        self._session_grid.clear_widgets()
        for s in reversed(self._sessions):  # newest first
            card = BoxLayout(
                orientation='vertical', size_hint_y=None, height=180,
                padding=8, spacing=10,
            )
            line1 = (
                f"{s.get('date', '?')}  |  {s.get('muscle_group', '?')}  |  "
                f"{s.get('exercise_type', '?')}"
            )
            line2 = (
                f"RMS: {s.get('peak_rms', 0):.3f}  |  "
                f"MF: {s.get('median_frequency', 0):.1f} Hz  |  "
                f"Contractions: {s.get('contraction_count', 0)}"
            )
            line3 = f"Subject: {s.get('subject_id', '--')}  |  Duration: {s.get('duration_sec', 0):.1f}s"
            line4 = f"File: {s.get('recording_file', '--')}"
            card.add_widget(Label(text=line1, font_size=sp(14), size_hint_y=None, height=30,
                                  color=(0.9, 0.9, 0.9, 1), halign='left'))
            card.add_widget(Label(text=line2, font_size=sp(13), size_hint_y=None, height=30,
                                  color=(0.7, 0.85, 1.0, 1), halign='left'))
            card.add_widget(Label(text=line3, font_size=sp(12), size_hint_y=None, height=26,
                                  color=(0.6, 0.6, 0.6, 1), halign='left'))
            card.add_widget(Label(text=line4, font_size=sp(11), size_hint_y=None, height=26,
                                  color=(0.45, 0.45, 0.45, 1), halign='left'))
            self._session_grid.add_widget(card)
