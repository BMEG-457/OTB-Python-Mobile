import socket

class SessantaquattroPlus:
    def __init__(self, host="0.0.0.0", port=45454):
        self.host = host
        self.port = port
        self.nchannels = 72
        self.frequency = 2000
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
        """
        Create command byte for Sessantaquattro+
        
        FSAMP: Sampling frequency (0=500Hz, 1=1kHz, 2=2kHz, 3=4kHz)
        NCH: Number of channels (0=8, 1=16, 2=32, 3=64)
        MODE: Working mode (0=Monopolar, 1=Bipolar, 2=Differential, etc.)
        HRES: High resolution (0=16bit, 1=24bit)
        HPF: High pass filter (0=DC, 1=10.5Hz)
        EXTEN: Extension factor (not used in standard)
        TRIG: Trigger mode (0=GO/STOP bit, 1=internal, 2=external, 3=button)
        REC: Recording on SD (0=stop, 1=rec)
        GO: Data transfer (0=stop, 1=go) - CRITICAL!
        """
        self.nchannels = self.get_num_channels(NCH, MODE)
        self.frequency = self.get_sampling_frequency(FSAMP, MODE)

        Command = 0
        Command = Command + GO           # Bit 0 - MUST BE 1 to start!
        Command = Command + (REC << 1)   # Bit 1
        Command = Command + (TRIG << 2)  # Bits 2-3
        Command = Command + (EXTEN << 4) # Bits 4-5
        Command = Command + (HPF << 6)   # Bit 6
        Command = Command + (HRES << 7)  # Bit 7
        Command = Command + (MODE << 8)  # Bits 8-10
        Command = Command + (NCH << 11)  # Bits 11-12
        Command = Command + (FSAMP << 13) # Bits 13-14

        binary_command = format(Command, '016b')
        print(f"Command Configuration:")
        print(f"  Channels: {self.nchannels} (NCH={NCH}, MODE={MODE})")
        print(f"  Frequency: {self.frequency} Hz (FSAMP={FSAMP})")
        print(f"  Resolution: {'24-bit' if HRES else '16-bit'}")
        print(f"  HPF: {'ON (10.5Hz)' if HPF else 'OFF (DC)'}")
        print(f"  GO bit: {GO} {'(STARTED)' if GO else '(STOPPED!)'}")
        print(f"  Binary: {binary_command}")
        print(f"  Decimal: {Command}")
        
        return Command
    

    def is_connected_to_device_network(self, device_network_prefix="192.168.1"):
        """Check if connected to the device's WiFi network"""
        try:
            # Get the actual IP being used for network communication
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Doesn't actually send data
            local_ip = s.getsockname()[0]
            s.close()
            
            print(f"Current IP: {local_ip}")
            
            if not local_ip.startswith(device_network_prefix):
                print(f"ERROR: Not connected to device network (expected {device_network_prefix}x)")
                return False
            
            return True
        except Exception as e:
            print(f"Error checking network: {e}")
            return False
        
    def start_server(self, connection_timeout=10):
        # Pre-flight checks
        if not self.is_connected_to_device_network():
            raise ConnectionError(
                "Please connect to the Sessantaquattroplus device's WiFi network first")
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Set a timeout for accept() to prevent indefinite hanging
            self.server_socket.settimeout(connection_timeout)
            
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            print(f"Server listening on {self.host}:{self.port}...")
            print(f"Waiting for Sessantaquattro+ to connect...")
            
            try:
                self.client_socket, addr = self.server_socket.accept()
                # Remove timeout for ongoing communication
                self.client_socket.settimeout(None)
                print(f"Connection accepted from {addr}")
                return self.client_socket
                
            except socket.timeout:
                self.server_socket.close()
                raise ConnectionError(
                    f"Device did not connect within {connection_timeout} seconds.\n"
                    "Make sure:\n"
                    "1. You're connected to the device's WiFi\n"
                    "2. The device is powered on and in pairing mode\n"
                    "3. No firewall is blocking the connection"
                )
                
        except socket.error as e:
            if self.server_socket:
                self.server_socket.close()
            raise ConnectionError(f"Server error: {e}")
            
    def send_command(self, command):
        """Send command to start data acquisition"""
        try:
            self.client_socket.send(command.to_bytes(2, byteorder='big', signed=True))
            print(f"Command sent successfully")
        except Exception as e:
            print(f"Socket Error sending command: {e}")
            raise ConnectionError("No active device connection.")

    def stop_server(self):
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()
        import socket

class SessantaquattroPlus:
    def __init__(self, host="0.0.0.0", port=45454):
        self.host = host
        self.port = port
        self.nchannels = 72
        self.frequency = 2000
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
        """
        Create command byte for Sessantaquattro+
        
        FSAMP: Sampling frequency (0=500Hz, 1=1kHz, 2=2kHz, 3=4kHz)
        NCH: Number of channels (0=8, 1=16, 2=32, 3=64)
        MODE: Working mode (0=Monopolar, 1=Bipolar, 2=Differential, etc.)
        HRES: High resolution (0=16bit, 1=24bit)
        HPF: High pass filter (0=DC, 1=10.5Hz)
        EXTEN: Extension factor (not used in standard)
        TRIG: Trigger mode (0=GO/STOP bit, 1=internal, 2=external, 3=button)
        REC: Recording on SD (0=stop, 1=rec)
        GO: Data transfer (0=stop, 1=go) - CRITICAL!
        """
        self.nchannels = self.get_num_channels(NCH, MODE)
        self.frequency = self.get_sampling_frequency(FSAMP, MODE)

        Command = 0
        Command = Command + GO           # Bit 0 - MUST BE 1 to start!
        Command = Command + (REC << 1)   # Bit 1
        Command = Command + (TRIG << 2)  # Bits 2-3
        Command = Command + (EXTEN << 4) # Bits 4-5
        Command = Command + (HPF << 6)   # Bit 6
        Command = Command + (HRES << 7)  # Bit 7
        Command = Command + (MODE << 8)  # Bits 8-10
        Command = Command + (NCH << 11)  # Bits 11-12
        Command = Command + (FSAMP << 13) # Bits 13-14

        binary_command = format(Command, '016b')
        print(f"Command Configuration:")
        print(f"  Channels: {self.nchannels} (NCH={NCH}, MODE={MODE})")
        print(f"  Frequency: {self.frequency} Hz (FSAMP={FSAMP})")
        print(f"  Resolution: {'24-bit' if HRES else '16-bit'}")
        print(f"  HPF: {'ON (10.5Hz)' if HPF else 'OFF (DC)'}")
        print(f"  GO bit: {GO} {'(STARTED)' if GO else '(STOPPED!)'}")
        print(f"  Binary: {binary_command}")
        print(f"  Decimal: {Command}")
        
        return Command
    

    def is_connected_to_device_network(self, device_network_prefix="192.168.1"):
        """Check if connected to the device's WiFi network"""
        try:
            # Get the actual IP being used for network communication
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Doesn't actually send data
            local_ip = s.getsockname()[0]
            s.close()
            
            print(f"Current IP: {local_ip}")
            
            if not local_ip.startswith(device_network_prefix):
                print(f"ERROR: Not connected to device network (expected {device_network_prefix}x)")
                return False
            
            return True
        except Exception as e:
            print(f"Error checking network: {e}")
            return False
        
    def start_server(self, connection_timeout=10):
        # Pre-flight checks
        if not self.is_connected_to_device_network():
            raise ConnectionError(
                "Please connect to the Sessantaquattroplus device's WiFi network first")
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Set a timeout for accept() to prevent indefinite hanging
            self.server_socket.settimeout(connection_timeout)
            
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            print(f"Server listening on {self.host}:{self.port}...")
            print(f"Waiting for Sessantaquattro+ to connect...")
            
            try:
                self.client_socket, addr = self.server_socket.accept()
                # Remove timeout for ongoing communication
                self.client_socket.settimeout(None)
                print(f"Connection accepted from {addr}")
                return self.client_socket
                
            except socket.timeout:
                self.server_socket.close()
                raise ConnectionError(
                    f"Device did not connect within {connection_timeout} seconds.\n"
                    "Make sure:\n"
                    "1. You're connected to the device's WiFi\n"
                    "2. The device is powered on and in pairing mode\n"
                    "3. No firewall is blocking the connection"
                )
                
        except socket.error as e:
            if self.server_socket:
                self.server_socket.close()
            raise ConnectionError(f"Server error: {e}")
            
    def send_command(self, command):
        """Send command to start data acquisition"""
        try:
            self.client_socket.send(command.to_bytes(2, byteorder='big', signed=True))
            print(f"Command sent successfully")
        except Exception as e:
            print(f"Error sending command: {e}")
            raise ConnectionError("No active device connection.")

    def stop_server(self):
        try:
            if self.client_socket:
                self.client_socket.close()
            if self.server_socket:
                self.server_socket.close()
        except Exception as e:
            print(f"Error closing sockets: {e}")
