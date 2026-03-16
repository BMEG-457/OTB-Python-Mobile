"""Recording manager for handling EMG data recording and CSV export."""

import csv
from datetime import datetime
import os
import time

from app.core.paths import get_recordings_dir


class RecordingManager:
    """Manages recording state and CSV export for EMG data."""
    
    # Signal emitted when recording should stop due to overflow
    def __init__(self, max_samples=1_000_000, on_overflow=None, on_status=None):
      self.on_overflow = on_overflow   # function to call on overflow
      self.on_status = on_status       # function to call with status strings
    # Signal emitted when recording status changes
    # status_update = QtCore.pyqtSignal(str)
    
    def __init__(self, max_samples=1000000):
        super().__init__()
        self.recording_data = []  # List of (timestamp, channel_data) tuples
        self.recording_start_time = None
        self.max_recording_samples = max_samples
        self.is_recording = False
    
    def start_recording(self):
        """Start recording data."""
        self.recording_data = []
        self.recording_start_time = time.time()
        self.is_recording = True
        print("[RECORDING] Recording started - waiting for data...")
        print(f"[RECORDING] is_recording flag set to: {self.is_recording}")
        return True
    
    def stop_recording(self):
        """Stop recording data."""
        print(f"[RECORDING] Recording stopped - collected {len(self.recording_data)} samples")
        self.is_recording = False
        return True
    
    def on_data_for_recording(self, stage_name, data):
        """Capture data from the receiver thread for recording.
        
        Args:
            stage_name: Name of the processing stage ('raw', 'filtered', 'rectified', or 'final')
            data: numpy array of shape (channels, samples)
        """
        # Debug: Log every call to see if signal is firing
        if len(self.recording_data) == 0 and self.is_recording:
            print(f"[RECORDING] on_data_for_recording called: stage={stage_name}, is_recording={self.is_recording}, data.shape={data.shape}")
        
        # Record 'raw' stage data (unprocessed, most reliable)
        # Changed from 'final' because processing pipeline may fail on small packets
        if stage_name != 'raw':
            return
        
        if not self.is_recording:
            return
        
        try:
            # Check for overflow protection
            if len(self.recording_data) >= self.max_recording_samples:
                # Stop recording and warn user
                if self.on_overflow: self.on_overflow()
                return
            
            # data shape: (channels, samples)
            # Store each sample with timestamp
            num_samples = data.shape[1]
            current_time = time.time()
            
            # Log first sample received
            if len(self.recording_data) == 0:
                print(f"[RECORDING] First data received! Shape: {data.shape}, samples: {num_samples}")
            
            for sample_idx in range(num_samples):
                # Calculate relative timestamp (seconds since recording start)
                timestamp = current_time - self.recording_start_time
                
                # Get all channels for this sample
                sample_data = data[:, sample_idx].copy()
                
                # Store as tuple: (timestamp, channel_data_array)
                self.recording_data.append((timestamp, sample_data))
                
                # Re-check overflow for each sample
                if len(self.recording_data) >= self.max_recording_samples:
                    self.overflow_stop_requested.emit()
                    break
                    
        except Exception as e:
            print(f"Error collecting recording data: {e}")
    
    def save_recording_to_csv(self):
        """Save recorded data to CSV file.
        
        Returns:
            tuple: (success: bool, message: str, filename: str or None)
        """
        if not self.recording_data:
            return False, "No data recorded", None
        
        try:
            # Create recordings directory if it doesn't exist
            recordings_dir = app/core/paths.py
            os.makedirs(recordings_dir, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(recordings_dir, f"recording_{timestamp_str}.csv")
            
            # Determine number of channels from first sample
            num_channels = len(self.recording_data[0][1])
            
            # Write CSV file
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header: Timestamp, Channel_1, Channel_2, ..., Channel_N
                header = ['Timestamp'] + [f'Channel_{i+1}' for i in range(num_channels)]
                writer.writerow(header)
                
                # Write data rows
                for timestamp, channel_data in self.recording_data:
                    row = [timestamp] + channel_data.tolist()
                    writer.writerow(row)
            
            num_samples = len(self.recording_data)
            message = f"Recording saved: {filename} ({num_samples} samples)"
            print(message)
            
            # Clear recording data to free memory
            self.recording_data = []
            self.recording_start_time = None
            
            return True, message, filename
            
        except Exception as e:
            error_msg = f"Error saving recording: {e}"
            print(error_msg)
            return False, error_msg, None
    
    def clear_recording_data(self):
        """Clear all recorded data from memory."""
        self.recording_data = []
        self.recording_start_time = None
    
    def get_recording_info(self):
        """Get information about current recording.
        
        Returns:
            dict: Information about recording (num_samples, duration, is_recording)
        """
        num_samples = len(self.recording_data)
        duration = None
        if self.recording_start_time is not None:
            duration = time.time() - self.recording_start_time
        
        return {
            'num_samples': num_samples,
            'duration': duration,
            'is_recording': self.is_recording,
            'max_samples': self.max_recording_samples
        }
