"""Unit tests for app/data/data_receiver.py.

Tests packet parsing, stage dispatch logic, and socket lifecycle.
No real device or Kivy required.
Run with:
    python -m unittest tests.test_data_receiver
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import struct
import threading
import unittest
import numpy as np
from unittest.mock import MagicMock, patch, call

from app.processing.pipeline import clear_pipelines
from app.data.data_receiver import DataReceiverThread
from app.core import config as CFG

_NCH  = CFG.DEVICE_CHANNELS       # 72
_FREQ = CFG.DEVICE_SAMPLE_RATE    # 2000
_SPP  = _FREQ // CFG.PACKET_SIZE_DIVISOR  # samples per packet (typically 125)


def _make_device(nch=_NCH, freq=_FREQ):
    dev = MagicMock()
    dev.nchannels = nch
    dev.frequency  = freq
    return dev


def _make_packet(nch=_NCH, spp=_SPP, amplitude=100):
    """Return raw bytes for one correctly-sized EMG packet."""
    rng   = np.random.default_rng(0)
    ints  = rng.integers(-amplitude, amplitude, nch * spp, dtype=np.int16)
    return struct.pack(f'>{nch * spp}h', *ints)


def _run_thread_with_single_packet(packet_bytes, running=True, extra_callbacks=None):
    """
    Helper: spin up DataReceiverThread, feed one packet, then EOF.
    Returns (stages_received, errors_received).
    """
    stages  = []
    errors  = []

    sock = MagicMock()
    # First recv returns packet, second returns b'' (EOF)
    sock.recv.side_effect = [packet_bytes, b'']

    dev = _make_device()

    def on_stage(name, data):
        stages.append((name, data.copy()))

    def on_error(msg):
        errors.append(msg)

    thread = DataReceiverThread(
        device=dev,
        client_socket=sock,
        on_stage=on_stage,
        on_error=on_error,
        on_status=lambda msg: None,
    )
    thread.running = running
    thread.start()
    thread.join(timeout=5)

    return stages, errors


class TestPacketParsing(unittest.TestCase):

    def setUp(self):
        clear_pipelines()

    def test_raw_always_emitted(self):
        pkt = _make_packet()
        stages, _ = _run_thread_with_single_packet(pkt, running=False)
        names = [s[0] for s in stages]
        self.assertIn('raw', names)

    def test_raw_shape_correct(self):
        pkt = _make_packet()
        stages, _ = _run_thread_with_single_packet(pkt, running=False)
        raw_data = next(d for n, d in stages if n == 'raw')
        self.assertEqual(raw_data.shape, (_NCH, _SPP))

    def test_raw_dtype_float32(self):
        pkt = _make_packet()
        stages, _ = _run_thread_with_single_packet(pkt, running=False)
        raw_data = next(d for n, d in stages if n == 'raw')
        self.assertEqual(raw_data.dtype, np.float32)

    def test_values_decoded_correctly(self):
        # Build a packet where every sample = 1000
        val   = 1000
        ints  = [val] * (_NCH * _SPP)
        pkt   = struct.pack(f'>{_NCH * _SPP}h', *ints)
        stages, _ = _run_thread_with_single_packet(pkt, running=False)
        raw_data = next(d for n, d in stages if n == 'raw')
        np.testing.assert_allclose(raw_data, val)

    def test_negative_values_decoded_correctly(self):
        val   = -512
        ints  = [val] * (_NCH * _SPP)
        pkt   = struct.pack(f'>{_NCH * _SPP}h', *ints)
        stages, _ = _run_thread_with_single_packet(pkt, running=False)
        raw_data = next(d for n, d in stages if n == 'raw')
        np.testing.assert_allclose(raw_data, val)


class TestStageDispatch(unittest.TestCase):

    def setUp(self):
        clear_pipelines()

    def test_filtered_rectified_final_emitted_when_running(self):
        pkt    = _make_packet()
        stages, _ = _run_thread_with_single_packet(pkt, running=True)
        names  = [s[0] for s in stages]
        self.assertIn('filtered', names)
        self.assertIn('rectified', names)
        self.assertIn('final',    names)

    def test_filtered_rectified_final_not_emitted_when_paused(self):
        pkt    = _make_packet()
        stages, _ = _run_thread_with_single_packet(pkt, running=False)
        names  = [s[0] for s in stages]
        self.assertNotIn('filtered',  names)
        self.assertNotIn('rectified', names)
        self.assertNotIn('final',     names)

    def test_raw_emitted_even_when_paused(self):
        pkt    = _make_packet()
        stages, _ = _run_thread_with_single_packet(pkt, running=False)
        names  = [s[0] for s in stages]
        self.assertIn('raw', names)

    def test_stage_order_is_raw_filtered_rectified_final(self):
        pkt    = _make_packet()
        stages, _ = _run_thread_with_single_packet(pkt, running=True)
        names  = [s[0] for s in stages]
        expected = ['raw', 'filtered', 'rectified', 'final']
        self.assertEqual(names[:4], expected)


class TestErrorHandling(unittest.TestCase):

    def setUp(self):
        clear_pipelines()

    def test_eof_triggers_error_callback(self):
        sock = MagicMock()
        sock.recv.return_value = b''   # immediate EOF
        dev  = _make_device()

        errors = []
        thread = DataReceiverThread(
            device=dev,
            client_socket=sock,
            on_stage=lambda n, d: None,
            on_error=lambda m: errors.append(m),
            on_status=lambda m: None,
        )
        thread.start()
        thread.join(timeout=5)
        self.assertGreater(len(errors), 0)

    def test_socket_timeout_does_not_call_error(self):
        import socket as _socket
        sock = MagicMock()
        # Two timeouts, then EOF to exit
        sock.recv.side_effect = [
            _socket.timeout(),
            _socket.timeout(),
            b'',
        ]
        dev    = _make_device()
        errors = []
        thread = DataReceiverThread(
            device=dev,
            client_socket=sock,
            on_stage=lambda n, d: None,
            on_error=lambda m: errors.append(m),
            on_status=lambda m: None,
        )
        thread.start()
        thread.join(timeout=5)
        # Error should be EOF, not timeout
        for msg in errors:
            self.assertNotIn('timeout', msg.lower())

    def test_stop_closes_socket(self):
        sock   = MagicMock()
        sock.recv.side_effect = [b'']  # fast exit
        dev    = _make_device()
        thread = DataReceiverThread(
            device=dev,
            client_socket=sock,
            on_stage=lambda n, d: None,
            on_error=lambda m: None,
            on_status=lambda m: None,
        )
        thread.stop()
        sock.close.assert_called()

    def test_stop_sets_running_false(self):
        sock = MagicMock()
        sock.recv.return_value = b''
        dev  = _make_device()
        thread = DataReceiverThread(
            device=dev,
            client_socket=sock,
            on_stage=lambda n, d: None,
            on_error=lambda m: None,
            on_status=lambda m: None,
        )
        thread.running = True
        thread.stop()
        self.assertFalse(thread.running)


class TestMultiPacketAccumulation(unittest.TestCase):
    """Verify the byte-buffer correctly reassembles split packets."""

    def setUp(self):
        clear_pipelines()

    def test_split_packet_reassembled(self):
        """If recv returns half a packet then the rest, one stage emit should result."""
        pkt   = _make_packet()
        half  = len(pkt) // 2

        sock  = MagicMock()
        sock.recv.side_effect = [pkt[:half], pkt[half:], b'']

        dev    = _make_device()
        stages = []
        thread = DataReceiverThread(
            device=dev,
            client_socket=sock,
            on_stage=lambda n, d: stages.append(n),
            on_error=lambda m: None,
            on_status=lambda m: None,
        )
        thread.running = False
        thread.start()
        thread.join(timeout=5)

        self.assertEqual(stages.count('raw'), 1)

    def test_two_full_packets_emit_raw_twice(self):
        pkt   = _make_packet()
        sock  = MagicMock()
        # Both packets arrive in a single large recv chunk
        sock.recv.side_effect = [pkt + pkt, b'']

        dev    = _make_device()
        stages = []
        thread = DataReceiverThread(
            device=dev,
            client_socket=sock,
            on_stage=lambda n, d: stages.append(n),
            on_error=lambda m: None,
            on_status=lambda m: None,
        )
        thread.running = False
        thread.start()
        thread.join(timeout=5)

        self.assertEqual(stages.count('raw'), 2)


if __name__ == '__main__':
    unittest.main()
