import sys
import os
import json
from PyQt6.QtCore import QSize, QUrl
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QMainWindow, QGroupBox, QFormLayout, QComboBox,
                             QLineEdit, QMessageBox)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from serial.tools import list_ports

from termtel.widgets.serialcon_widget.Library.serialshell import SerialBackend

class Ui_SerialWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

    def setupUi(self, term):
        self.setWindowTitle("Serial Term")
        layout = QVBoxLayout(self)

        # Connection settings group box
        self.connection_group = QGroupBox("Connection Settings")
        connection_layout = QFormLayout(self.connection_group)

        # Port selection combo box
        self.combox = QComboBox()
        for port in list_ports.comports():
            if "Bluetooth" not in str(port.description):
                self.combox.addItem(port.name)
        connection_layout.addRow("Port", self.combox)

        # Baud rate selection combo box with standard options
        self.baudrate = QComboBox()
        self.baudrate.addItems(["9600", "19200", "38400", "57600", "115200"])
        connection_layout.addRow("Baud Rate", self.baudrate)

        # Data bits input with validation
        self.databits = QLineEdit("8")
        self.databits.setValidator(QIntValidator())
        connection_layout.addRow("Data Bits", self.databits)

        # Stop bits input with validation
        self.stopbits = QLineEdit("1")
        self.stopbits.setValidator(QIntValidator())
        connection_layout.addRow("Stop Bits", self.stopbits)

        # Parity selection combo box with standard options
        self.parity = QComboBox()
        self.parity.addItems(["N", "E", "O", "M", "S"])
        connection_layout.addRow("Parity", self.parity)

        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_to_serial)
        connection_layout.addWidget(self.connect_btn)

        layout.addWidget(self.connection_group)

        # Serial output view
        self.view = QWebEngineView()
        self.backend = SerialBackend(parent=self)
        self.channel = QWebChannel()
        self.channel.registerObject("backend", self.backend)
        self.view.page().setWebChannel(self.channel)

        self.backend.send_output.connect(
            lambda data: self.view.page().runJavaScript(f"window.handle_output({json.dumps(data)})"))

        # Load the terminal HTML

        current_dir = os.path.dirname(__file__)
        parent_dir = os.path.dirname(current_dir)
        terminal_html = os.path.join(parent_dir, 'serialcon_widget', "serialassets", "qtserialcon.html")
        print(f"loading... {terminal_html}")
        self.view.load(QUrl.fromLocalFile(terminal_html))

        layout.addWidget(self.view)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def cleanup(self):
        # Call a method to close the serial port
        self.backend.disconnect()

    def connect_to_serial(self):
        try:
            port = self.combox.currentText()
            baudrate = self.baudrate.currentText()
            databits = int(self.databits.text())
            stopbits = int(self.stopbits.text())
            parity = self.parity.currentText()

            # Update backend with the new settings directly
            self.backend.port = port
            self.backend.baudrate = baudrate
            self.backend.databits = databits
            self.backend.stopbits = stopbits
            self.backend.parity = parity

            self.backend.connect()

            # Hide connection settings after successful connection
            self.connection_group.setVisible(False)
            self.setWindowTitle(f"Serial Term: {port}")
        except Exception as e:
            self.notify("Connection Error", str(e))

    def notify(self, message, info):
        QMessageBox.information(self, message, info)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    mainWin = QMainWindow()
    mainWin.resize(800, 400)

    serial_widget = Ui_SerialWidget(parent=mainWin)
    mainWin.setCentralWidget(serial_widget)
    mainWin.setWindowTitle("PyQt6 - Serial Terminal Widget")
    mainWin.show()

    sys.exit(app.exec())
