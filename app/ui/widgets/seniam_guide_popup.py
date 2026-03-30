"""SENIAM electrode placement guide popup."""

from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.metrics import sp


_GUIDE_TEXT = (
    "[b]Tibialis Anterior — SENIAM Recommendations[/b]\n\n"
    "[b]Electrode Location:[/b]\n"
    "Place at 1/3 of the distance from the tip of the fibula "
    "to the medial condyle of the tibia.\n\n"
    "[b]Electrode Orientation:[/b]\n"
    "Along the line between the tip of the fibula and the "
    "medial condyle of the tibia.\n\n"
    "[b]Skin Preparation:[/b]\n"
    "1. Clean skin with alcohol wipe\n"
    "2. Allow skin to dry completely\n"
    "3. Ensure no lotions or oils on skin\n"
    "4. Shave hair if necessary for contact\n\n"
    "[b]HD-EMG Array Positioning:[/b]\n"
    "1. Center the 8x8 grid over the muscle belly\n"
    "2. Align columns parallel to the muscle fibers\n"
    "3. Secure sleeve with even pressure — avoid gaps\n"
    "4. Verify electrode-skin contact across all channels\n\n"
    "[b]Pre-Session Checklist:[/b]\n"
    "- Electrode array positioned per above\n"
    "- Sleeve secured with even pressure\n"
    "- No discomfort reported by subject\n"
    "- Device WiFi connected\n"
    "- Battery level adequate (>20%)\n"
    "- Baseline recording taken at rest\n"
    "- Calibration completed (rest + MVC)"
)


class SENIAMGuidePopup(Popup):
    """Popup displaying SENIAM electrode placement guide for tibialis anterior."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = 'Electrode Placement Guide'
        self.size_hint = (0.9, 0.85)

        layout = BoxLayout(orientation='vertical', padding=12, spacing=8)

        scroll = ScrollView(size_hint=(1, 0.88))
        content = BoxLayout(
            orientation='vertical', size_hint_y=None, spacing=8, padding=8
        )
        content.bind(minimum_height=content.setter('height'))

        lbl = Label(
            text=_GUIDE_TEXT, markup=True, font_size=sp(15),
            halign='left', valign='top', size_hint_y=None,
        )
        lbl.bind(
            texture_size=lambda inst, val: setattr(inst, 'size', val),
            width=lambda inst, w: setattr(inst, 'text_size', (w - 16, None)),
        )
        content.add_widget(lbl)

        scroll.add_widget(content)
        layout.add_widget(scroll)

        btn_close = Button(text='Close', size_hint=(1, 0.12), font_size=sp(16))
        btn_close.bind(on_press=lambda x: self.dismiss())
        layout.add_widget(btn_close)

        self.content = layout
