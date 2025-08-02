from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal
from serial.tools import list_ports
import serial
import json
import threading
import time


class SerialBackend(QObject):
    # Define signals for serial data and connection status changes
    send_output = pyqtSignal(str)
    connection_changed = pyqtSignal(bool, str)

    def __init__(self, view=None, port="", baudrate=9600, databits=8, stopbits=1, parity='N'):
        super().__init__()
        self.view = view
        self.ui = None  # Reference to UI for connection updates
        self.serial_port = None
        self.running = False
        self.read_thread = None

        # Default serial parameters
        self.port = port
        self.baudrate = baudrate
        self.databits = databits
        self.stopbits = stopbits
        self.parity = parity

    def set_view(self, view):
        """Set the web view for terminal output"""
        self.view = view
        # Inject initial port list if view is available
        if self.view:
            self.refresh_ports()

    @pyqtSlot(str)
    def write_data(self, data):
        """Write data to the serial port"""
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.write(data.encode())
            except Exception as e:
                print(f"Error writing to serial port: {e}")
                self._write_to_terminal(f"\r\nError writing to serial port: {e}\r\n")
                self.connection_changed.emit(False, f"Write error: {e}")

    @pyqtSlot()
    def disconnect(self):
        """Disconnect from the serial port"""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.running = False
                if self.read_thread:
                    self.read_thread.join(timeout=1.0)
                self.serial_port.close()
                print("Disconnected from serial port")
                self._write_to_terminal("\r\nDisconnected\r\n")
                self._update_connection_status(False)
                self.connection_changed.emit(False, "Disconnected")
        except Exception as e:
            print(f"Error disconnecting: {e}")
            self._write_to_terminal(f"\r\nError disconnecting: {e}\r\n")

    @pyqtSlot(str, int, int, float, str)
    def connect_with_params(self, port, baud, databits, stopbits, parity):
        """Connect to the serial port with specific parameters"""
        print(
            f"Connecting with explicit params: Port={port}, Baud={baud}, DataBits={databits}, StopBits={stopbits}, Parity={parity}")

        # Save parameters
        self.port = port
        self.baudrate = baud
        self.databits = databits
        self.stopbits = stopbits
        self.parity = parity

        # Connect
        self.connect()

    @pyqtSlot()
    def connect(self):
        """Connect to the serial port"""
        try:
            # Disconnect first if already connected
            if self.serial_port and self.serial_port.is_open:
                self.disconnect()

            print(f"Connecting with port={self.port}, baudrate={self.baudrate}")

            # Create and configure serial port
            self.serial_port = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.databits,
                stopbits=self.stopbits,
                parity=self.parity,
                timeout=0.1
            )

            if self.serial_port.is_open:
                print(f"Connected to... {self.port}")
                self._write_to_terminal(f"\r\nConnected to {self.port}\r\n")
                self._update_connection_status(True)
                self.connection_changed.emit(True, f"Connected to {self.port}")

                # Start reading thread
                self.running = True
                self.read_thread = threading.Thread(target=self.read_serial)
                self.read_thread.daemon = True
                self.read_thread.start()
            else:
                self._write_to_terminal("\r\nFailed to connect\r\n")
                self.connection_changed.emit(False, "Failed to connect")
        except Exception as e:
            print(f"Error connecting to serial port: {e}")
            self._write_to_terminal(f"\r\nError connecting: {e}\r\n")
            self._update_connection_status(False)
            self.connection_changed.emit(False, f"Error: {e}")

    def read_serial(self):
        """Read data from the serial port in a separate thread"""
        while self.running and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    if data:
                        # Send decoded data to terminal
                        decoded_data = data.decode('utf-8', errors='replace')
                        self.send_output.emit(decoded_data)
                        self._write_to_terminal(decoded_data)
            except Exception as e:
                print(f"Error reading from serial port: {e}")
                self._write_to_terminal(f"\r\nError reading: {e}\r\n")
                self.connection_changed.emit(False, f"Read error: {e}")
                self.running = False
                break
            time.sleep(0.01)  # Small delay to prevent CPU hogging

    def _write_to_terminal(self, data):
        """Write data to the terminal using JavaScript"""
        if self.view:
            # Escape special characters for JavaScript
            escaped_data = data.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace("'",
                                                                                                        "\\'").replace(
                '"', '\\"')
            # Send data to terminal
            self.view.page().runJavaScript(f"handle_output('{escaped_data}');")

    def _update_connection_status(self, is_connected):
        """Update UI connection status"""
        if self.view:
            self.view.page().runJavaScript(f"window.updateUIConnected({str(is_connected).lower()});")

    @pyqtSlot()
    def refresh_ports(self):
        """Refresh the list of available ports"""
        if not self.view:
            return

        try:
            ports_list = []
            for port in list_ports.comports():
                if "Bluetooth" not in port.description:
                    ports_list.append({
                        "name": port.name,
                        "description": port.description
                    })

            # Convert to JSON and inject into the HTML
            ports_json = json.dumps(ports_list)
            js_code = f"""
            (function() {{
                const portsSelect = document.getElementById('port-select');
                const ports = {ports_json};

                // Clear existing options
                portsSelect.innerHTML = '';

                // Add new options
                ports.forEach(port => {{
                    const option = document.createElement('option');
                    option.value = port.name;
                    option.text = `${{port.name}} - ${{port.description}}`;
                    portsSelect.appendChild(option);
                }});

                console.log("Ports refreshed:", ports.length, "ports found");
            }})();
            """

            self.view.page().runJavaScript(js_code)
            self._write_to_terminal("\r\nPorts refreshed\r\n")
        except Exception as e:
            print(f"Error refreshing ports: {e}")
            self._write_to_terminal(f"\r\nError refreshing ports: {e}\r\n")