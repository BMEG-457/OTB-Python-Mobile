"""Background receiver thread for live EMG data over TCP.

Mirrors the desktop DataReceiverThread but uses threading.Thread instead of
QThread, and delivers data via callbacks instead of Qt signals.

Thread lifecycle matches the desktop pattern: the thread starts once and stays
alive in a socket.recv() loop indefinitely. Streaming is paused/resumed by
toggling self.running — the thread never needs to be restarted.
"""

import threading
import time
import socket
import numpy as np

from app.processing.pipeline import get_pipeline
from app.core import config as CFG

# Packet sizing — matches desktop Config defaults
_PACKET_SIZE_DIVISOR = CFG.PACKET_SIZE_DIVISOR
_SOCKET_TIMEOUT      = CFG.SOCKET_TIMEOUT
_FPS_LOG_INTERVAL    = CFG.FPS_LOG_INTERVAL


class DataReceiverThread(threading.Thread):
    """Background thread that receives EMG packets from the device TCP socket.

    Args:
        device:        SessantaquattroPlus instance (provides nchannels, frequency).
        client_socket: Connected TCP socket to the device.
        on_stage:      Callback(stage: str, data: np.ndarray) — called for each
                       pipeline stage ('raw', 'filtered', 'rectified', 'final').
                       'raw' is always called; others only when self.running=True.
        on_error:      Callback(msg: str) — called on unrecoverable socket error.
        on_status:     Callback(msg: str) — called periodically with packet rate.
    """

    def __init__(self, device, client_socket, on_stage, on_error, on_status):
        super().__init__(daemon=True)
        self.device        = device
        self.client_socket = client_socket
        self.on_stage      = on_stage
        self.on_error      = on_error
        self.on_status     = on_status
        self.running       = False  # set True by StreamingController.start_streaming()

        self._packet_count = 0
        self._last_time    = time.time()
        self._pipeline_total_ms = 0.0  # debug: accumulated pipeline time
        self._pending_recv_time = None  # timestamp of most recent packet receipt

        self._last_packet_time   = time.time()
        self._disconnect_warned  = False
        self.on_disconnect       = None  # optional callback(elapsed_sec)

        # Pre-compute adapter channel map as numpy array for fast fancy indexing
        self._channel_map = (np.array(CFG.ADAPTER_CHANNEL_MAP, dtype=np.intp)
                             if CFG.ADAPTER_CHANNEL_MAP is not None else None)
        # Pre-compute dead channel index array for fast zeroing after pipeline
        self._dead_mask = (np.array(sorted(CFG.DEAD_CHANNELS), dtype=np.intp)
                           if CFG.DEAD_CHANNELS else None)

        try:
            self.client_socket.settimeout(_SOCKET_TIMEOUT)
        except Exception as e:
            print(f"[RECEIVER] WARNING: Could not set socket timeout: {e}")

    def run(self):
        nch            = self.device.nchannels
        freq           = self.device.frequency
        samples_per_pkt = freq // _PACKET_SIZE_DIVISOR
        expected_bytes  = nch * 2 * samples_per_pkt
        print(f"[RECEIVER] Starting — {nch} ch @ {freq} Hz, "
              f"{samples_per_pkt} samples/pkt, {expected_bytes} bytes/pkt, "
              f"adapter={CFG.ADAPTER_TYPE}"
              f"{' (remap active)' if self._channel_map is not None else ''}")

        buf = b''

        while True:
            try:
                chunk = self.client_socket.recv(expected_bytes * 2)

                if not chunk:
                    print("[RECEIVER] Socket closed by remote end")
                    self.on_error("Connection closed by device")
                    break

                buf += chunk

                while len(buf) >= expected_bytes:
                    pkt_bytes = buf[:expected_bytes]
                    buf       = buf[expected_bytes:]

                    # Zero-copy decode: big-endian int16 → float32 (no Python tuple)
                    all_ch = (np.frombuffer(pkt_bytes, dtype='>i2')
                              .astype(np.float32)
                              .reshape(samples_per_pkt, nch)
                              .T)  # shape (nchannels, samples_per_pkt)

                    raw = all_ch[:CFG.HDSEMG_CHANNELS]  # keep only HD-sEMG channels

                    # Adapter remap: reorder channels to match logical 8×8 grid
                    if self._channel_map is not None:
                        raw = raw[self._channel_map]

                    self._pending_recv_time = time.time()

                    # Raw stage — always emitted (recording needs it regardless of running)
                    self.on_stage('raw', raw)

                    # Final stage only when actively streaming
                    # ('filtered' and 'rectified' stages removed — nothing consumes them)
                    if self.running:
                        t0 = time.time()
                        try:
                            final = get_pipeline('final').run(raw)
                        except Exception:
                            final = raw
                        # Re-zero dead channels: filter state on always-zero inputs
                        # can produce tiny non-zero transients; clamp them out.
                        if self._dead_mask is not None:
                            final[self._dead_mask, :] = 0.0
                        self._pipeline_total_ms += (time.time() - t0) * 1000
                        self.on_stage('final', final)

                    self._packet_count += 1
                    self._last_packet_time = time.time()
                    self._disconnect_warned = False
                    if self._packet_count == 1:
                        print("[RECEIVER] First packet processed successfully")

                    if self._packet_count % _FPS_LOG_INTERVAL == 0:
                        now     = time.time()
                        elapsed = now - self._last_time
                        rate    = _FPS_LOG_INTERVAL / elapsed if elapsed > 0 else 0
                        self._last_time = now
                        if self.running:
                            avg_pipe = self._pipeline_total_ms / _FPS_LOG_INTERVAL
                            print(f"[DEBUG] receiver: {rate:.1f} pkt/s "
                                  f"avg_pipeline={avg_pipe:.2f}ms")
                            self._pipeline_total_ms = 0.0
                            self.on_status(
                                f"{rate:.1f} pkt/s | {nch} ch"
                            )

            except socket.timeout:
                if self.running and not self._disconnect_warned:
                    elapsed = time.time() - self._last_packet_time
                    if elapsed > CFG.DISCONNECT_WARNING_SEC:
                        self._disconnect_warned = True
                        if self.on_disconnect:
                            self.on_disconnect(elapsed)
                continue

            except Exception as e:
                print(f"[RECEIVER] Error: {type(e).__name__}: {e}")
                self.on_error(f"Receiver error: {e}")
                break

        print(f"[RECEIVER] Thread exiting — {self._packet_count} packets received")

    def stop(self):
        """Terminate the thread by closing the socket (forces recv to return)."""
        self.running = False
        try:
            self.client_socket.close()
        except Exception:
            pass
