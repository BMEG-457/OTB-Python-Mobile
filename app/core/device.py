import re
import socket
import urllib.request

from app.core import config as CFG


class SessantaquattroPlus:
    def __init__(self, host=None, port=None, emulator_mode=False):
        self.host = host if host is not None else CFG.DEVICE_HOST
        self.port = port if port is not None else CFG.DEVICE_PORT
        self.emulator_mode = emulator_mode
        self.nchannels = CFG.DEVICE_CHANNELS
        self.frequency = CFG.DEVICE_SAMPLE_RATE
        self.server_socket = None
        self.client_socket = None

    def get_num_channels(self, NCH, MODE):
        if NCH == 0:
            return 12 if MODE == 1 else 16
        elif NCH == 1:
            return 16 if MODE == 1 else 24
        elif NCH == 2:
            return 24 if MODE == 1 else 40
        elif NCH == 3:
            return 40 if MODE == 1 else 72
        return 72

    def get_sampling_frequency(self, FSAMP, MODE):
        if MODE == 3:
            frequencies = {0: 2000, 1: 4000, 2: 8000, 3: 16000}
        else:
            frequencies = {0: 500, 1: 1000, 2: 2000, 3: 4000}
        return frequencies.get(FSAMP, 2000)

    def create_command(self, FSAMP=2, NCH=3, MODE=0, HRES=0, HPF=1, EXTEN=0, TRIG=0, REC=0, GO=1):
        """Create command byte for Sessantaquattro+."""
        self.nchannels = self.get_num_channels(NCH, MODE)
        self.frequency = self.get_sampling_frequency(FSAMP, MODE)

        Command = 0
        Command = Command + GO
        Command = Command + (REC << 1)
        Command = Command + (TRIG << 2)
        Command = Command + (EXTEN << 4)
        Command = Command + (HPF << 6)
        Command = Command + (HRES << 7)
        Command = Command + (MODE << 8)
        Command = Command + (NCH << 11)
        Command = Command + (FSAMP << 13)

        print(f"Command: {self.nchannels} ch @ {self.frequency} Hz, binary={format(Command, '016b')}")
        return Command

    def is_connected_to_device_network(self, device_network_prefix="192.168.1"):
        """Check if connected to the device's WiFi network."""
        if self.emulator_mode:
            print("Emulator mode — skipping network check")
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(CFG.NETWORK_CHECK_TIMEOUT)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            print(f"Current IP: {local_ip}")
            if not local_ip.startswith(device_network_prefix):
                return False
            return True
        except Exception as e:
            print(f"Error checking network: {e}")
            return False

    def start_server(self, connection_timeout=10):
        """Start TCP server and wait for device to connect.

        Raises:
            ConnectionError: if not on the device network or device times out.
            OSError: on socket bind/listen errors.
        """
        if not self.is_connected_to_device_network():
            raise ConnectionError(
                "Not connected to the Sessantaquattro+ WiFi network. "
                "Connect to the device's network and try again."
            )

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.settimeout(connection_timeout)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            print(f"Server listening on {self.host}:{self.port}...")

            try:
                self.client_socket, addr = self.server_socket.accept()
                self.client_socket.settimeout(None)
                print(f"Connection accepted from {addr}")
            except socket.timeout:
                self.server_socket.close()
                raise ConnectionError(
                    f"Device did not connect within {connection_timeout} seconds. "
                    "Ensure the device is powered on and in pairing mode."
                )

        except ConnectionError:
            raise
        except socket.error as e:
            if self.server_socket:
                self.server_socket.close()
            raise OSError(f"Server socket error: {e}") from e

    def get_battery_level(self):
        """Query battery via the device's HTTP status page. Returns 0-100 or None."""
        url = f"http://{CFG.DEVICE_GATEWAY_IP}/"
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=3) as resp:
                html = resp.read().decode('utf-8', errors='replace')
            match = re.search(r'Battery\s*Level:\s*</td>\s*<td>\s*(\d+)%', html)
            if match:
                level = int(match.group(1))
                print(f"[BATTERY] HTTP query: {level}%")
                return level
            print("[BATTERY] Could not parse battery level from HTML")
            return None
        except Exception as e:
            print(f"[BATTERY] HTTP query failed: {e}")
            return None

    def send_command(self, command):
        """Send command to start data acquisition."""
        try:
            self.client_socket.send(command.to_bytes(2, byteorder='big', signed=True))
            print("Command sent successfully")
        except Exception as e:
            print(f"Error sending command: {e}")
            raise

    def stop_server(self):
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()
        self.client_socket = None
        self.server_socket = None
