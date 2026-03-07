import struct
import numpy as np
import time
import socket
import threading 
from app.processing.pipeline import ProcessingPipeline, get_pipeline


class DataReceiverThread(threading.Thread):

    def __init__(self, device, client_socket, tracks,  on_data=None, on_stage_output=None, on_status=None, on_error=None):
        super().__init__(daemon=True)
        self.device = device
        self.client_socket = client_socket
        self.tracks = tracks
        self.running = False  # Start False, will be set True by streaming_controller
        self.packet_count = 0
        self.last_time = time.time()
        self.fps = 0
        
        # Processing pipelines for multi-stage output
        self.processor = get_pipeline('final')

        self.on_data = on_data
        self.on_stage_output = on_stage_output
        self.on_status = on_status
        self.on_error = on_error
        
        # Set socket timeout to prevent infinite blocking
        try:
            self.client_socket.settimeout(5.0)  # 5 second timeout
            print("[RECEIVER] Socket timeout set to 5 seconds")
        except Exception as e:
            print(f"[RECEIVER] WARNING: Could not set socket timeout: {e}")

    def run(self):
        # Calculate expected packet size
        expected_bytes = self.device.nchannels * 2 * (self.device.frequency // 16)
        print(f"[RECEIVER] Thread run() started")
        print(f"[RECEIVER] Device config: {self.device.nchannels} channels at {self.device.frequency}Hz")
        print(f"[RECEIVER] Expecting {expected_bytes} bytes per packet ({self.device.nchannels} channels)")
        print(f"[RECEIVER] Initial running state: {self.running}")

        # Buffer to accumulate incomplete packets
        buffer = b''
        
        # Keep thread alive indefinitely - only exit on error or explicit stop
        thread_alive = True
        
        while thread_alive:
            try:
                # Receive data (may be partial) - request more to avoid multiple small reads
                chunk = self.client_socket.recv(expected_bytes * 2)
                
                if not chunk:
                    print("[RECEIVER] Socket closed by remote end")
                    if self.on_error:
                        self.on_error("Connection closed by device")
                    break
                
                buffer += chunk
                
                # Process all complete packets in the buffer
                while len(buffer) >= expected_bytes:
                    # Extract one complete packet
                    data = buffer[:expected_bytes]
                    buffer = buffer[expected_bytes:]
                    
                    # Unpack as big-endian signed shorts (16-bit)
                    unpacked_data = struct.unpack(f'>{len(data) // 2}h', data)
                    reshaped_data = np.array(unpacked_data).reshape((-1, self.device.nchannels)).T
                    
                    # Filtered stage with fallback
                    if self.on_stage_output:
                        self.on_stage_output('raw', reshaped_data.copy())
                    try:
                        filtered = get_pipeline('filtered').run(reshaped_data)
                        if self.on_stage_output:
                            self.on_stage_output('filtered', filtered.copy())
                    except Exception:
                        filtered = reshaped_data
                    
                    # Rectified stage with fallback
                    try:
                        rectified = get_pipeline('rectified').run(filtered)
                        if self.on_stage_output:
                            self.on_stage_output('rectified', rectified.copy())
                    except Exception:
                        rectified = filtered
                    
                    # Final processed data with fallback
                    try:
                        processed = self.processor.run(reshaped_data)
                    except Exception:
                        processed = rectified
                    
                    # Emit final stage
                    if self.on_stage_output:
                        self.on_stage_output('final', processed.copy())
                    
                    # Only feed tracks and emit signals when streaming is active
                    if self.running:
                        # Feed tracks with processed data
                        idx = 0
                        for track in self.tracks:
                            track.feed(processed[idx:idx + track.num_channels])
                            idx += track.num_channels
                        
                        if self.on_data:
                            self.on_data(processed)
                    
                    # Update packet count and FPS
                    self.packet_count += 1
                    if self.packet_count == 1:
                        print(f"[RECEIVER] First packet processed successfully!")
                    
                    if self.packet_count % 100 == 0:
                        now = time.time()
                        elapsed = now - self.last_time
                        self.fps = 100 / elapsed if elapsed > 0 else 0
                        self.last_time = now

                        if self.running and self.on_status:
                            self.on_status(
                            f"Data rate: {self.fps:.1f} packets/s | Channels: {self.device.nchannels}"
                            )
                    print(f"[RECEIVER] Packet #{self.packet_count}: {self.fps:.1f} packets/s")
            
            except socket.timeout:
                # Socket timeout - normal when paused (running=False)
                if self.running:
                    print("[RECEIVER] Socket timeout while streaming - no data in 5 seconds")
                # Don't exit - continue loop to allow pause/resume
                continue
                
            except Exception as e:
                print(f"[RECEIVER] Error: {type(e).__name__}: {e}")
                if self.on_error:
                    self.on_error(f"Error: {e}")
                import traceback
                traceback.print_exc()
                thread_alive = False
                break
        
        print(f"[RECEIVER] Thread run() exiting - total packets received: {self.packet_count}")
        
        # Log any remaining buffer data
        if buffer:
            print(f"[RECEIVER] WARNING: {len(buffer)} bytes left in buffer on exit")

    def stop(self):
        """Completely stop the receiver thread (called on window close)."""
        print("[RECEIVER] stop() called - thread will exit on next iteration")
        self.running = False
        # Close socket to force recv() to return and allow thread to exit cleanly
        try:
            self.client_socket.close()
        except Exception as e:
            print(f"[RECEIVER] Error closing socket in stop(): {e}")
