import sys
import os
import json
from PyQt6.QtCore import QSize, QUrl, pyqtSlot, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QMainWindow,
    QDialog, QFormLayout, QComboBox, QLineEdit, QDialogButtonBox,
    QMessageBox, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineScript
from serial.tools import list_ports

# Import the updated SerialBackend
try:
    from serialshell import SerialBackend
except ImportError:
    # Try to import from the Library subdirectory
    try:
        from .Library.serialshell import SerialBackend
    except ImportError:
        # If both fail, use a relative import
        from Library.serialshell import SerialBackend


class Ui_SerialWidget(QWidget):
    """
    A QWidget that provides a serial console interface using xterm.js
    """

    def __init__(self, port=None, baudrate=9600, databits=8, stopbits=1, parity='N',
                 theme_library=None, current_theme="default", parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate
        self.databits = databits
        self.stopbits = stopbits
        self.parity = parity
        self.parent = parent
        self.theme_library = theme_library
        self.current_theme = current_theme
        self.setupUi(self)

    def setupUi(self, term):
        # Create backend
        self.backend = SerialBackend(
            port=self.port,
            baudrate=self.baudrate,
            databits=self.databits,
            stopbits=self.stopbits,
            parity=self.parity
        )
        self.backend.ui = self

        # Set up WebChannel for communication with JS
        self.channel = QWebChannel()
        self.channel.registerObject("backend", self.backend)

        self.backend.connection_changed.connect(self.on_connection_changed)

        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Status bar
        self.status_bar = QFrame()
        self.status_bar.setStyleSheet("background-color: #1a1a1a; color: #cccccc;")
        self.status_bar.setFrameShape(QFrame.Shape.StyledPanel)
        self.status_bar.setMaximumHeight(30)

        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(5, 2, 5, 2)

        self.status_label = QLabel("Disconnected")
        status_layout.addWidget(self.status_label)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setMaximumWidth(100)
        self.connect_btn.clicked.connect(self.show_connection_dialog)
        status_layout.addWidget(self.connect_btn)

        layout.addWidget(self.status_bar)

        # Web view for terminal
        self.view = QWebEngineView()
        self.view.page().setWebChannel(self.channel)

        # Connect signals
        self.backend.send_output.connect(
            lambda data: self.view.page().runJavaScript(f"window.handle_output({json.dumps(data)})"))
        # self.backend.connection_changed.connect(self.handle_connection_change)
        # self.backend.error_occurred.connect(self.handle_error)

        # Load the HTML file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        terminal_html = os.path.join(current_dir, "qtserialcon.html")

        print(f"Loading terminal HTML from: {terminal_html}")
        self.view.load(QUrl.fromLocalFile(terminal_html))

        # When page is loaded, apply theme
        self.view.loadFinished.connect(self.on_page_loaded)

        layout.addWidget(self.view)
        self.setLayout(layout)



    @pyqtSlot(str, int, int, float, str)
    def handle_form_connection(self, port, baudrate, databits, stopbits, parity):
        """Handle connection request from the HTML form"""
        print(
            f"Connection request from form: Port={port}, Baud={baudrate}, DataBits={databits}, StopBits={stopbits}, Parity={parity}")

        try:
            # Update backend settings
            self.backend.port = port
            self.backend.baudrate = baudrate
            self.backend.databits = databits
            self.backend.stopbits = stopbits
            self.backend.parity = parity

            # Try to connect
            self.backend.connect()

            # Update UI to show connected state
            self.view.page().runJavaScript("window.updateUIConnected(true)")
        except Exception as e:
            print(f"Connection error: {e}")
            self.notify("Connection error", str(e))

            # Update UI to show disconnected state
            self.view.page().runJavaScript("window.updateUIConnected(false)")

    @pyqtSlot()
    def handle_form_disconnection(self):
        """Handle disconnection request from the HTML form"""
        try:
            # Disconnect
            self.backend.disconnect()

            # Update UI to show disconnected state
            self.view.page().runJavaScript("window.updateUIConnected(false)")
        except Exception as e:
            print(f"Disconnection error: {e}")
            self.notify("Disconnection error", str(e))

    def on_connection_changed(self, connected, info):
        """Handle connection status changes"""
        # Update the HTML UI
        self.view.page().runJavaScript(f"window.updateConnectButton({str(connected).lower()})")

        # Update the Python UI if needed
        if hasattr(self, 'status_label'):
            if connected:
                self.status_label.setText(f"{info}")
                if hasattr(self, 'connect_btn'):
                    self.connect_btn.setText("Disconnect")
                    self.connect_btn.clicked.disconnect()
                    self.connect_btn.clicked.connect(self.backend.disconnect)
            else:
                self.status_label.setText(f"{info}")
                if hasattr(self, 'connect_btn'):
                    self.connect_btn.setText("Connect")
                    self.connect_btn.clicked.disconnect()
                    self.connect_btn.clicked.connect(self.show_connection_dialog)


    def inject_ports_list(self):
        """Inject the list of available ports into the HTML dropdown"""
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
            }})();
            """

            self.view.page().runJavaScript(js_code)
        except Exception as e:
            print(f"Error injecting ports list: {e}")


    def on_page_loaded(self, success):
        """Called when the HTML page is loaded"""
        if success:
            print("Terminal page loaded successfully")

            # Inject ports list into the HTML dropdown
            self.inject_ports_list()
            QTimer.singleShot(100, self.inject_ports_list)

            # Apply theme after a short delay to ensure JS is ready
            QTimer.singleShot(500, self.apply_current_theme)
        else:
            print("Failed to load terminal page")


    def apply_current_theme(self):
        """Apply the current theme to the terminal"""
        if not self.theme_library:
            return

        try:
            # Get theme from theme library
            theme = self.theme_library.get_theme(self.current_theme)
            if not theme:
                print(f"Theme '{self.current_theme}' not found, using default")
                return

            # Generate terminal theme JS
            js_code = self.theme_library.generate_terminal_js(theme)

            # Execute the JS in the web view
            self.view.page().runJavaScript(js_code, lambda result: print(f"Theme applied: {result}"))
        except Exception as e:
            print(f"Error applying theme: {e}")

    def handle_connection_change(self, connected, info):
        """Handle connection status changes"""
        if connected:
            self.status_label.setText(f"{info}")
            self.connect_btn.setText("Disconnect")
            self.connect_btn.clicked.disconnect()
            self.connect_btn.setEnabled(True)
            self.connect_btn.clicked.connect(self.backend.disconnect)
        else:
            self.status_label.setText(f"{info}")
            self.connect_btn.setText("Connect")
            self.connect_btn.clicked.disconnect()
            self.connect_btn.clicked.connect(self.show_connection_dialog)

    def handle_error(self, error_msg):
        """Handle errors from the backend"""
        print(f"Error: {error_msg}")
        self.notify("Error", error_msg)

    def set_theme(self, theme_name):
        """Set the current theme"""
        self.current_theme = theme_name
        self.apply_current_theme()

    def show_connection_dialog(self):
        """Show the connection dialog"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Connect to Serial Port")

        form = QFormLayout()

        # Port selection
        combox = QComboBox()
        try:
            for port in list_ports.comports():
                if "Bluetooth" not in port.description:
                    combox.addItem(f"{port.name} - {port.description}", port.name)
        except Exception as e:
            print(f"Error listing ports: {e}")

        # Set default port if available
        if self.port and combox.count() > 0:
            index = combox.findData(self.port)
            if index >= 0:
                combox.setCurrentIndex(index)

        form.addRow("Port", combox)

        # Baud rate
        baudbox = QComboBox()
        baud_rates = ["9600", "19200", "38400", "57600", "115200"]
        for rate in baud_rates:
            baudbox.addItem(rate)

        # Set default baud rate
        if str(self.baudrate) in baud_rates:
            baudbox.setCurrentText(str(self.baudrate))

        form.addRow("Baud Rate", baudbox)

        # Data bits
        databits = QComboBox()
        for bits in ["5", "6", "7", "8"]:
            databits.addItem(bits)
        databits.setCurrentText(str(self.databits))
        form.addRow("Data Bits", databits)

        # Stop bits
        stopbits = QComboBox()
        for bits in ["1", "1.5", "2"]:
            stopbits.addItem(bits)
        stopbits.setCurrentText(str(self.stopbits))
        form.addRow("Stop Bits", stopbits)

        # Parity
        parity = QComboBox()
        parity_options = {
            "N": "None",
            "E": "Even",
            "O": "Odd",
            "M": "Mark",
            "S": "Space"
        }
        for code, name in parity_options.items():
            parity.addItem(name, code)

        # Set default parity
        index = parity.findData(self.parity)
        if index >= 0:
            parity.setCurrentIndex(index)

        form.addRow("Parity", parity)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(button_box)
        dialog.setLayout(layout)

        # Show dialog
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            # Get selected port (extract port name from data)
            self.backend.port = combox.currentData()
            self.backend.baudrate = int(baudbox.currentText())
            self.backend.databits = int(databits.currentText())

            # Handle stop bits (could be float)
            stop_text = stopbits.currentText()
            self.backend.stopbits = float(stop_text) if stop_text == "1.5" else int(stop_text)

            # Get parity code
            self.backend.parity = parity.currentData()

            # Try to connect
            try:
                self.backend.connect()
            except Exception as e:
                print(f"Connection error: {e}")
                self.notify("Connection error", str(e))

    def notify(self, message, info):
        """Show a notification dialog"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(info)
        msg.setWindowTitle(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()


class SerialWidgetWrapper(QWidget):
    """
    A wrapper widget that handles creating the serial widget and showing
    the connection dialog.
    """

    def __init__(self, theme_library=None, current_theme="default", parent=None):
        super().__init__(parent)
        self.parent = parent
        self.theme_library = theme_library
        self.current_theme = current_theme

        # Create layout
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Create the serial widget with theme support
        self.serial_widget = Ui_SerialWidget(
            theme_library=self.theme_library,
            current_theme=self.current_theme,
            parent=self
        )

        # Show the connection dialog on initialization
        QTimer.singleShot(100, self.serial_widget.show_connection_dialog)

        # Add widget to layout
        self.layout.addWidget(self.serial_widget)
        self.setLayout(self.layout)

    def set_theme(self, theme_name):
        """Set the current theme for the terminal"""
        self.current_theme = theme_name
        if hasattr(self, 'serial_widget') and self.serial_widget:
            self.serial_widget.set_theme(theme_name)

    def connect_to_port(self, port, baudrate=9600, databits=8, stopbits=1, parity='N'):
        """Programmatically connect to a specific port"""
        if hasattr(self, 'serial_widget') and self.serial_widget:
            self.serial_widget.port = port
            self.serial_widget.baudrate = baudrate
            self.serial_widget.databits = databits
            self.serial_widget.stopbits = stopbits
            self.serial_widget.parity = parity

            # Update backend settings
            self.serial_widget.backend.port = port
            self.serial_widget.backend.baudrate = baudrate
            self.serial_widget.backend.databits = databits
            self.serial_widget.backend.stopbits = stopbits
            self.serial_widget.backend.parity = parity

            # Connect
            self.serial_widget.backend.connect()

    def disconnect(self):
        """Disconnect from the current port"""
        if hasattr(self, 'serial_widget') and self.serial_widget:
            self.serial_widget.backend.disconnect()


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)

        mainWin = QMainWindow()
        mainWin.resize(800, 600)

        # If theme library is available, use it
        theme_library = None
        try:
            # Try to import the theme library
            from themes import ThemeLibrary

            theme_library = ThemeLibrary()
            current_theme = "cyberpunk"  # Default theme
        except ImportError:
            print("Theme library not available, using default theme")
            current_theme = "default"

        # Use the wrapper with theme support
        wrapper = SerialWidgetWrapper(
            theme_library=theme_library,
            current_theme=current_theme,
            parent=mainWin
        )

        mainWin.setCentralWidget(wrapper)
        mainWin.show()
        mainWin.setWindowTitle("Serial Terminal")

        sys.exit(app.exec())
    except Exception as e:
        print(f"Exception in main: {e}")