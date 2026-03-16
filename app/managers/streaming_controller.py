"""Streaming controller for managing live data viewing."""

from kivy.clock import Clock
from app.core.config import Config


class StreamingController:
    """Manages streaming state and receiver thread interactions."""
    
    # Signals for status updates
    # status_update = QtCore.pyqtSignal(str)
    
    self._clock_event = Clock.schedule_interval(self.update_callback, 1/60)

    # To stop:
    self._clock_event.cancel()
    
    def __init__(self, timer, receiver_thread):
        super().__init__()
        self.timer = timer
        self.receiver_thread = receiver_thread
        self.is_streaming = False
        self.is_paused = False
    
    def start_streaming(self):
        """Start live streaming without recording."""
        print("[STREAMING] start_streaming() called")
        self.is_streaming = True
        self.is_paused = False
        
        if self.receiver_thread is not None:
            # Check if thread is running (alive) vs finished (dead)
            if self.receiver_thread.isRunning():
                # Thread is alive (might be paused) - just set running=True to resume
                print("[STREAMING] Receiver thread is alive, resuming (setting running=True)")
                self.receiver_thread.running = True
            else:
                # Thread has finished - check if it exited due to error or normal stop
                print("[STREAMING] Receiver thread not running, attempting to start...")
                self.receiver_thread.running = True
                try:
                    self.receiver_thread.start()  # Try to start the QThread
                    print("[STREAMING] Receiver thread started successfully")
                except RuntimeError as e:
                    # Thread already finished and can't be restarted
                    print(f"[STREAMING] ERROR: Cannot restart finished thread: {e}")
                    print("[STREAMING] Need to recreate receiver thread (not implemented yet)")
                    self.status_update.emit("ERROR: Cannot restart. Please restart the application.")
                    return False
        else:
            print("[STREAMING] ERROR: receiver_thread is None!")
            self.status_update.emit("ERROR: Receiver not initialized")
            return False
            
        self.timer.start(Config.UPDATE_RATE)  # Start timer with configured update rate
        self.status_update.emit("Streaming...")
        print(f"[STREAMING] Timer started with {Config.UPDATE_RATE}ms interval")
        return True
    
    def stop_streaming(self):
        """Stop live streaming."""
        print("[STREAMING] stop_streaming() called")
        self.is_streaming = False
        self.is_paused = True
        self.timer.stop()
        
        if self.receiver_thread is not None:
            print("[STREAMING] Pausing receiver thread (setting running=False)...")
            self.receiver_thread.running = False
            # Don't wait() for thread to exit - let it stay alive in recv() call
            # This allows it to be restarted by setting running=True again
            print("[STREAMING] Receiver thread paused (will remain in socket recv loop)")
        
        self.status_update.emit("Stream stopped")
        print("[STREAMING] Live streaming stopped")
        return True
    
    def toggle_streaming(self):
        """Toggle streaming state on/off."""
        if self.is_streaming:
            return self.stop_streaming()
        else:
            return self.start_streaming()
    
    def pause_streaming(self):
        """Pause streaming temporarily."""
        self.is_paused = True
        self.timer.stop()
        return True
    
    def resume_streaming(self):
        """Resume paused streaming."""
        self.is_paused = False
        self.timer.start()
        return True
    
    def get_streaming_state(self):
        """Get current streaming state.
        
        Returns:
            dict: Dictionary with streaming status information
        """
        return {
            'is_streaming': self.is_streaming,
            'is_paused': self.is_paused
        }
