"""Streaming controller for managing live data viewing."""

from kivy.clock import Clock
from app.core import config as CFG


class StreamingController:
    """Manages streaming state and receiver thread interactions.

    Replaces the PyQt5 QTimer-based desktop version. Uses Kivy's Clock for
    the UI update loop and plain callbacks for status updates.

    Args:
        update_callback: Function called every UI update tick (receives dt arg).
        receiver_thread: DataReceiverThread instance.
        on_status: Optional callback for status string updates.
    """

    def __init__(self, update_callback, receiver_thread, on_status=None):
        self.update_callback = update_callback
        self.receiver_thread = receiver_thread
        self.on_status = on_status
        self.is_streaming = False
        self.is_paused = False
        self._clock_event = None

    def start_streaming(self):
        """Start live streaming."""
        print("[STREAMING] start_streaming() called")
        self.is_streaming = True
        self.is_paused = False

        if self.receiver_thread is None:
            self._emit_status("ERROR: Receiver not initialized")
            return False

        if self.receiver_thread.is_alive():
            # Thread is alive (may be paused) — resume by setting running=True
            print("[STREAMING] Receiver thread alive, resuming")
            self.receiver_thread.running = True
        else:
            # Thread has not been started yet — start it
            print("[STREAMING] Starting receiver thread")
            self.receiver_thread.running = True
            try:
                self.receiver_thread.start()
                print("[STREAMING] Receiver thread started successfully")
            except RuntimeError as e:
                # threading.Thread can only be started once
                print(f"[STREAMING] ERROR: Cannot restart thread: {e}")
                self._emit_status("ERROR: Cannot restart. Please restart the app.")
                return False

        # Start Kivy Clock for UI update loop
        # Data arrives at 16 pkt/s; 30fps gives ~2 render chances per packet.
        # 60fps wastes most ticks on empty reads and starves the event loop.
        self._clock_event = Clock.schedule_interval(self.update_callback, 1 / CFG.RENDER_FPS)
        self._emit_status("Streaming...")
        print("[STREAMING] Clock started at 30fps")
        return True

    def stop_streaming(self):
        """Stop live streaming (pause — receiver thread stays alive)."""
        print("[STREAMING] stop_streaming() called")
        self.is_streaming = False
        self.is_paused = True

        if self._clock_event is not None:
            self._clock_event.cancel()
            self._clock_event = None

        if self.receiver_thread is not None:
            self.receiver_thread.running = False
            print("[STREAMING] Receiver thread paused (remains in socket recv loop)")

        self._emit_status("Stream stopped")
        return True

    def toggle_streaming(self):
        """Toggle streaming state on/off."""
        if self.is_streaming:
            return self.stop_streaming()
        return self.start_streaming()

    def get_streaming_state(self):
        return {
            'is_streaming': self.is_streaming,
            'is_paused': self.is_paused,
        }

    def _emit_status(self, message):
        if self.on_status:
            self.on_status(message)
