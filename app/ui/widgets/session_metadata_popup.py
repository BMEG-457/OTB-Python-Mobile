"""Session metadata entry popup for recording sessions."""

from datetime import date

from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.metrics import sp
from app.core import config as CFG


class SessionMetadataPopup(Popup):
    """Popup form for entering session metadata before recording.

    Args:
        on_confirm: callable(metadata_dict) — called with form data on confirm.
    """

    def __init__(self, on_confirm, **kwargs):
        super().__init__(**kwargs)
        self.title = 'Session Metadata'
        self.size_hint = (0.85, 0.7)
        self.auto_dismiss = False
        self._on_confirm = on_confirm

        layout = BoxLayout(orientation='vertical', padding=12, spacing=8)

        # Date
        row_date = BoxLayout(orientation='horizontal', size_hint=(1, None), height=44)
        row_date.add_widget(Label(text='Date:', size_hint=(0.35, 1), font_size=sp(15)))
        self._inp_date = TextInput(
            text=date.today().isoformat(), multiline=False,
            size_hint=(0.65, 1), font_size=sp(15),
        )
        row_date.add_widget(self._inp_date)
        layout.add_widget(row_date)

        # Subject / Patient ID
        row_subject = BoxLayout(orientation='horizontal', size_hint=(1, None), height=44)
        row_subject.add_widget(Label(text='Subject ID:', size_hint=(0.35, 1), font_size=sp(15)))
        self._inp_subject = TextInput(
            text='', multiline=False, hint_text='e.g. P001',
            size_hint=(0.65, 1), font_size=sp(15),
        )
        row_subject.add_widget(self._inp_subject)
        layout.add_widget(row_subject)

        # Muscle Group
        row_muscle = BoxLayout(orientation='horizontal', size_hint=(1, None), height=44)
        row_muscle.add_widget(Label(text='Muscle Group:', size_hint=(0.35, 1), font_size=sp(15)))
        self._spn_muscle = Spinner(
            text=CFG.SESSION_MUSCLE_GROUPS[0],
            values=CFG.SESSION_MUSCLE_GROUPS,
            size_hint=(0.65, 1), font_size=sp(15),
        )
        row_muscle.add_widget(self._spn_muscle)
        layout.add_widget(row_muscle)

        # Exercise Type
        row_exercise = BoxLayout(orientation='horizontal', size_hint=(1, None), height=44)
        row_exercise.add_widget(Label(text='Exercise:', size_hint=(0.35, 1), font_size=sp(15)))
        self._spn_exercise = Spinner(
            text=CFG.SESSION_EXERCISE_TYPES[0],
            values=CFG.SESSION_EXERCISE_TYPES,
            size_hint=(0.65, 1), font_size=sp(15),
        )
        row_exercise.add_widget(self._spn_exercise)
        layout.add_widget(row_exercise)

        # Notes
        row_notes_label = BoxLayout(size_hint=(1, None), height=28)
        row_notes_label.add_widget(Label(text='Notes:', font_size=sp(15), halign='left'))
        layout.add_widget(row_notes_label)
        self._inp_notes = TextInput(
            text='', multiline=True, hint_text='Optional notes...',
            size_hint=(1, 1), font_size=sp(14),
        )
        layout.add_widget(self._inp_notes)

        # Buttons
        btn_row = BoxLayout(orientation='horizontal', size_hint=(1, None), height=50, spacing=12)
        btn_cancel = Button(text='Cancel', font_size=sp(16))
        btn_cancel.bind(on_press=lambda inst: self.dismiss())
        btn_confirm = Button(
            text='Start Recording', font_size=sp(16),
            background_color=(0.1, 0.6, 0.3, 1.0),
        )
        btn_confirm.bind(on_press=self._on_confirm_press)
        btn_row.add_widget(btn_cancel)
        btn_row.add_widget(btn_confirm)
        layout.add_widget(btn_row)

        self.content = layout

    def _on_confirm_press(self, instance):
        metadata = {
            'date': self._inp_date.text.strip(),
            'subject_id': self._inp_subject.text.strip(),
            'muscle_group': self._spn_muscle.text,
            'exercise_type': self._spn_exercise.text,
            'notes': self._inp_notes.text.strip(),
        }
        self.dismiss()
        self._on_confirm(metadata)
