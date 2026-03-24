"""Kivy entry point for the OTB EMG Android app."""

import os

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.metrics import sp
from kivy.clock import Clock

from app.core.config import EMULATOR_BUILD
from app.core.device import SessantaquattroPlus
from app.ui.screens.selection_screen import SelectionScreen
from app.ui.screens.live_data_screen import LiveDataScreen
from app.ui.screens.data_analysis_screen import DataAnalysisScreen
from app.ui.screens.analysis_plot_screen import AnalysisPlotScreen
from app.ui.screens.longitudinal_screen import LongitudinalScreen


def _is_android():
    try:
        import android  # noqa: F401
        return True
    except ImportError:
        return False


class OTBApp(App):
    def build(self):
        emulator = EMULATOR_BUILD or os.getenv("SESSANTAQUATTRO_EMULATOR") == "1"
        self.device = SessantaquattroPlus(emulator_mode=emulator)

        sm = ScreenManager()
        sm.add_widget(SelectionScreen(name='selection'))
        sm.add_widget(LiveDataScreen(name='live_data', device=self.device))
        sm.add_widget(DataAnalysisScreen(name='data_analysis'))
        sm.add_widget(AnalysisPlotScreen(name='analysis_plot'))
        sm.add_widget(LongitudinalScreen(name='longitudinal'))

        return sm

    def on_start(self):
        """Request WRITE_EXTERNAL_STORAGE on Android 9/10 if not already granted."""
        if _is_android():
            Clock.schedule_once(lambda dt: self._check_storage_permission(), 0.5)

    def _check_storage_permission(self):
        """Use android.permissions to request runtime storage access.

        On Android 9/10 (e.g. Huawei P30 Pro), WRITE_EXTERNAL_STORAGE is a
        standard runtime permission shown as a system dialog.  MANAGE_EXTERNAL_STORAGE
        (API 30+) is intentionally not used because it does not exist on Android 10.
        """
        try:
            from android.permissions import request_permissions, check_permission, Permission
            if not check_permission(Permission.WRITE_EXTERNAL_STORAGE):
                request_permissions(
                    [Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE],
                    callback=self._on_permission_result,
                )
            else:
                print("[PERMISSIONS] WRITE_EXTERNAL_STORAGE already granted")
        except Exception as e:
            # android.permissions not available (desktop or unexpected environment)
            print(f"[PERMISSIONS] android.permissions unavailable: {e}")

    def _on_permission_result(self, permissions, grants):
        """Callback from request_permissions."""
        if not all(grants):
            print("[PERMISSIONS] Storage permission denied — showing instructions")
            self._show_storage_denied_dialog()
        else:
            print("[PERMISSIONS] Storage permission granted — restart required")
            self._show_restart_dialog()

    def _show_restart_dialog(self):
        """Storage permission was just granted; GID update requires a restart."""
        content = BoxLayout(orientation='vertical', padding=16, spacing=12)
        content.add_widget(Label(
            text=(
                'Storage permission granted.\n\n'
                'Please close and reopen the app for\n'
                'file access to take full effect.\n\n'
                'Recordings will save to:\n'
                'Phone > Android > data >\n'
                'org.bmeg457.otbemgapp > files > OTB_EMG'
            ),
            font_size=sp(15),
            halign='center',
            valign='middle',
            size_hint=(1, 1),
        ))
        popup = Popup(
            title='Restart Required',
            content=content,
            size_hint=(0.82, 0.55),
        )
        popup.open()

    def _show_storage_denied_dialog(self):
        """Shown only if the user tapped Deny on the system permission dialog."""
        content = BoxLayout(orientation='vertical', padding=16, spacing=12)
        content.add_widget(Label(
            text=(
                'Storage permission denied\n\n'
                'OTB EMG cannot save recordings without storage access.\n\n'
                'Grant it manually:\n'
                'Settings > Apps > OTB EMG App\n'
                '> Permissions > Storage > Allow'
            ),
            font_size=sp(15),
            halign='center',
            valign='middle',
            size_hint=(1, 1),
        ))
        popup = Popup(
            title='Permission Denied',
            content=content,
            size_hint=(0.82, 0.5),
        )
        popup.open()

    def on_stop(self):
        """Clean up device connection when the app closes."""
        try:
            self.device.stop_server()
        except Exception:
            pass


if __name__ == '__main__':
    OTBApp().run()
