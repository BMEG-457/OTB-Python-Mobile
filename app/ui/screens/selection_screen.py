from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.metrics import sp
from app.core import config as CFG


class SelectionScreen(Screen):
    """Entry screen: choose between Live Data and Data Analysis modes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(orientation='vertical', padding=60, spacing=24)

        layout.add_widget(Label(
            text='OTB EMG',
            font_size=sp(36),
            bold=True,
            size_hint=(1, 0.25),
        ))
        layout.add_widget(Label(
            text='Select a mode to continue',
            font_size=sp(18),
            color=(0.7, 0.7, 0.7, 1),
            size_hint=(1, 0.15),
        ))

        btn_live = Button(
            text='Live Data Viewing',
            font_size=sp(20),
            size_hint=(1, 0.25),
            background_color=CFG.BTN_LIVE_MODE,
        )
        btn_live.bind(on_press=self._go_live)
        layout.add_widget(btn_live)

        btn_analysis = Button(
            text='Data Analysis',
            font_size=sp(20),
            size_hint=(1, 0.25),
            background_color=CFG.BTN_ANALYSIS_MODE,
        )
        btn_analysis.bind(on_press=self._go_analysis)
        layout.add_widget(btn_analysis)

        self.add_widget(layout)

    def _go_live(self, instance):
        self.manager.current = 'live_data'

    def _go_analysis(self, instance):
        self.manager.current = 'data_analysis'
