"""Unit tests for app/core/device.py.

Tests command encoding, channel/frequency lookup, and network check logic.
No real sockets or device hardware required.
Run with:
    python -m unittest tests.test_device
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import patch, MagicMock
import socket

from app.core.device import SessantaquattroPlus


class TestGetNumChannels(unittest.TestCase):

    def setUp(self):
        self.dev = SessantaquattroPlus(host='127.0.0.1', port=45454)

    # MODE=0 (differential)
    def test_nch0_mode0_returns_16(self):
        self.assertEqual(self.dev.get_num_channels(0, 0), 16)

    def test_nch1_mode0_returns_24(self):
        self.assertEqual(self.dev.get_num_channels(1, 0), 24)

    def test_nch2_mode0_returns_40(self):
        self.assertEqual(self.dev.get_num_channels(2, 0), 40)

    def test_nch3_mode0_returns_72(self):
        self.assertEqual(self.dev.get_num_channels(3, 0), 72)

    # MODE=1 (single-ended)
    def test_nch0_mode1_returns_12(self):
        self.assertEqual(self.dev.get_num_channels(0, 1), 12)

    def test_nch1_mode1_returns_16(self):
        self.assertEqual(self.dev.get_num_channels(1, 1), 16)

    def test_nch2_mode1_returns_24(self):
        self.assertEqual(self.dev.get_num_channels(2, 1), 24)

    def test_nch3_mode1_returns_40(self):
        self.assertEqual(self.dev.get_num_channels(3, 1), 40)

    def test_unknown_nch_returns_72(self):
        self.assertEqual(self.dev.get_num_channels(99, 0), 72)


class TestGetSamplingFrequency(unittest.TestCase):

    def setUp(self):
        self.dev = SessantaquattroPlus(host='127.0.0.1', port=45454)

    # MODE=3 (HD-sEMG high-rate)
    def test_mode3_fsamp0_returns_2000(self):
        self.assertEqual(self.dev.get_sampling_frequency(0, 3), 2000)

    def test_mode3_fsamp1_returns_4000(self):
        self.assertEqual(self.dev.get_sampling_frequency(1, 3), 4000)

    def test_mode3_fsamp2_returns_8000(self):
        self.assertEqual(self.dev.get_sampling_frequency(2, 3), 8000)

    def test_mode3_fsamp3_returns_16000(self):
        self.assertEqual(self.dev.get_sampling_frequency(3, 3), 16000)

    # Non-MODE=3
    def test_mode0_fsamp0_returns_500(self):
        self.assertEqual(self.dev.get_sampling_frequency(0, 0), 500)

    def test_mode0_fsamp2_returns_2000(self):
        self.assertEqual(self.dev.get_sampling_frequency(2, 0), 2000)

    def test_unknown_fsamp_returns_2000(self):
        self.assertEqual(self.dev.get_sampling_frequency(99, 0), 2000)


class TestCreateCommand(unittest.TestCase):

    def setUp(self):
        self.dev = SessantaquattroPlus(host='127.0.0.1', port=45454)

    def test_returns_int(self):
        cmd = self.dev.create_command()
        self.assertIsInstance(cmd, int)

    def test_default_command_sets_nchannels(self):
        # Default: NCH=3, MODE=0 → 72 channels
        self.dev.create_command()
        self.assertEqual(self.dev.nchannels, 72)

    def test_default_command_sets_frequency(self):
        # Default: FSAMP=2, MODE=0 → 2000 Hz
        self.dev.create_command()
        self.assertEqual(self.dev.frequency, 2000)

    def test_go_bit_set(self):
        # GO=1 → bit 0 of command should be 1
        cmd = self.dev.create_command(GO=1)
        self.assertEqual(cmd & 0x1, 1)

    def test_go_bit_clear(self):
        cmd = self.dev.create_command(GO=0)
        self.assertEqual(cmd & 0x1, 0)

    def test_rec_bit_position(self):
        # REC=1 → bit 1
        cmd_rec = self.dev.create_command(GO=0, REC=1)
        self.assertEqual((cmd_rec >> 1) & 0x1, 1)

    def test_fits_in_16_bits(self):
        cmd = self.dev.create_command()
        self.assertLessEqual(cmd, 0xFFFF)
        self.assertGreaterEqual(cmd, 0)

    def test_command_encodes_to_2_bytes(self):
        cmd = self.dev.create_command()
        encoded = cmd.to_bytes(2, byteorder='big', signed=True)
        self.assertEqual(len(encoded), 2)


class TestNetworkCheck(unittest.TestCase):

    def setUp(self):
        self.dev = SessantaquattroPlus(host='127.0.0.1', port=45454)

    def test_emulator_mode_returns_true(self):
        dev = SessantaquattroPlus(emulator_mode=True)
        self.assertTrue(dev.is_connected_to_device_network())

    def test_returns_false_when_ip_wrong_prefix(self):
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ('10.0.0.5', 0)
        with patch('socket.socket', return_value=mock_socket):
            result = self.dev.is_connected_to_device_network("192.168.1")
        self.assertFalse(result)

    def test_returns_true_when_ip_matches_prefix(self):
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ('192.168.1.50', 0)
        with patch('socket.socket', return_value=mock_socket):
            result = self.dev.is_connected_to_device_network("192.168.1")
        self.assertTrue(result)

    def test_returns_false_on_socket_exception(self):
        with patch('socket.socket', side_effect=OSError("no network")):
            result = self.dev.is_connected_to_device_network()
        self.assertFalse(result)


class TestSendCommand(unittest.TestCase):

    def test_sends_2_byte_big_endian(self):
        dev = SessantaquattroPlus(host='127.0.0.1', port=45454)
        mock_sock = MagicMock()
        dev.client_socket = mock_sock

        cmd = dev.create_command()
        dev.send_command(cmd)

        mock_sock.send.assert_called_once()
        sent_bytes = mock_sock.send.call_args[0][0]
        self.assertEqual(len(sent_bytes), 2)

    def test_send_raises_on_socket_error(self):
        dev = SessantaquattroPlus(host='127.0.0.1', port=45454)
        mock_sock = MagicMock()
        mock_sock.send.side_effect = OSError("broken pipe")
        dev.client_socket = mock_sock

        cmd = dev.create_command()
        with self.assertRaises(Exception):
            dev.send_command(cmd)


class TestStartServer(unittest.TestCase):

    def test_raises_connection_error_when_not_on_device_network(self):
        dev = SessantaquattroPlus(host='127.0.0.1', port=45454)
        with patch.object(dev, 'is_connected_to_device_network', return_value=False):
            with self.assertRaises(ConnectionError):
                dev.start_server()

    def test_raises_connection_error_on_timeout(self):
        dev = SessantaquattroPlus(host='127.0.0.1', port=45455)
        mock_server = MagicMock()
        mock_server.accept.side_effect = socket.timeout()
        with patch.object(dev, 'is_connected_to_device_network', return_value=True):
            with patch('socket.socket', return_value=mock_server):
                with self.assertRaises(ConnectionError):
                    dev.start_server(connection_timeout=1)


if __name__ == '__main__':
    unittest.main()
