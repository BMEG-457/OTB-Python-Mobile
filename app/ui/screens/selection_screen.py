from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
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
            size_hint=(1, 0.20),
            background_color=CFG.BTN_LIVE_MODE,
        )
        btn_live.bind(on_press=self._go_live)
        layout.add_widget(btn_live)

        btn_analysis = Button(
            text='Data Analysis',
            font_size=sp(20),
            size_hint=(1, 0.20),
            background_color=CFG.BTN_ANALYSIS_MODE,
        )
        btn_analysis.bind(on_press=self._go_analysis)
        layout.add_widget(btn_analysis)

        btn_history = Button(
            text='Session History',
            font_size=sp(20),
            size_hint=(1, 0.20),
            background_color=(0.5, 0.35, 0.7, 1.0),
        )
        btn_history.bind(on_press=self._go_history)
        layout.add_widget(btn_history)

        self.add_widget(layout)

    def _go_live(self, instance):
        content = BoxLayout(orientation='vertical', padding=20, spacing=16)

        content.add_widget(Label(
            text='Select a viewing mode:',
            font_size=sp(18),
            size_hint=(1, 0.3),
        ))

        btn_basic = Button(
            text='Basic (Clinical)',
            font_size=sp(18),
            size_hint=(1, 0.35),
            background_color=CFG.BTN_LIVE_MODE,
        )
        btn_advanced = Button(
            text='Advanced (Researcher)',
            font_size=sp(18),
            size_hint=(1, 0.35),
            background_color=CFG.BTN_ANALYSIS_MODE,
        )

        content.add_widget(btn_basic)
        content.add_widget(btn_advanced)

        popup = Popup(
            title='Live Data Mode',
            content=content,
            size_hint=(0.7, 0.45),
            auto_dismiss=True,
        )

        def on_basic(inst):
            popup.dismiss()
            self.manager.get_screen('live_data').set_mode('basic')
            self.manager.current = 'live_data'

        def on_advanced(inst):
            popup.dismiss()
            self.manager.get_screen('live_data').set_mode('advanced')
            self.manager.current = 'live_data'

        btn_basic.bind(on_press=on_basic)
        btn_advanced.bind(on_press=on_advanced)
        popup.open()

    def _go_analysis(self, instance):
        self.manager.current = 'data_analysis'

    def _go_history(self, instance):
        self.manager.current = 'longitudinal'
