import json
import sys

from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QPushButton,
                             QProgressBar, QLabel, QFileDialog, QApplication, QMainWindow)
import logicmonitor_sdk
from logicmonitor_sdk import Device
from logicmonitor_sdk.rest import ApiException
import yaml
import re
import ssl
import certifi
import os
from collections import defaultdict
from termtel.themes2 import LayeredHUDFrame, ThemeLibrary


class DownloadThread(QThread):
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    save_file_signal = pyqtSignal(object)

    def __init__(self, company, access_id, access_key, cert_path=None):
        QThread.__init__(self)
        self.company = company
        self.access_id = access_id
        self.access_key = access_key
        self.cert_path = cert_path

    def add_zscaler_cert(self):
        """Add Zscaler certificate to the certifi SSL trust store"""
        if not self.cert_path or not os.path.exists(self.cert_path):
            return

        with open(self.cert_path, 'rb') as cert_file:
            cert_data = cert_file.read()

        cafile = certifi.where()
        with open(cafile, 'ab') as certifi_file:
            certifi_file.write(b'\n')
            certifi_file.write(cert_data)

    def is_valid_IP_Address(self, sample_str):
        """Validate IP address format"""
        if not sample_str:
            return False
        match_obj = re.search(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", sample_str)
        if match_obj is None:
            return False
        return all(int(value) <= 255 for value in match_obj.groups())

    def extract_geo_site(self, properties):
        """Extract geo site from system properties"""
        for prop in properties:
            if prop['name'] == 'system.groups':
                groups = prop['value'].split(',')
                geo_groups = [g for g in groups if 'Network by Geo' in g]
                if geo_groups:
                    return geo_groups[0].split('/')[-1]
        return None

    def run(self):
        try:
            self.status_signal.emit("Configuring LogicMonitor API")

            # Add certificate if provided
            if self.cert_path:
                self.add_zscaler_cert()

            # Configure LogicMonitor API
            configuration = logicmonitor_sdk.Configuration()
            configuration.company = self.company
            configuration.access_id = self.access_id
            configuration.access_key = self.access_key

            # Create API instance
            api_instance = logicmonitor_sdk.LMApi(logicmonitor_sdk.ApiClient(configuration))

            self.status_signal.emit("Downloading devices")
            devices_by_site = defaultdict(list)
            total_devices = 0
            processed_devices = 0

            # First pass to count total devices
            for x in range(0, 3):
                try:
                    response = api_instance.get_device_list(offset=x * 1000, size=1000)
                    total_devices += len(response.items)
                except ApiException:
                    break

            # Second pass to process devices
            for x in range(0, 3):
                try:
                    response = api_instance.get_device_list(offset=x * 1000, size=1000)
                    self.status_signal.emit(f"Processing batch {x + 1}")

                    for device in response.items:
                        device_dict = device.to_dict()
                        if self.is_valid_IP_Address(device_dict.get('name')):
                            geo_site = self.extract_geo_site(device_dict.get('system_properties', []))
                            if not geo_site:
                                geo_site = "Ungrouped Devices"

                            # Create session object
                            session = {
                                'DeviceType': 'Network',  # Default type
                                'Model': '',
                                'SerialNumber': '',
                                'SoftwareVersion': '',
                                'Vendor': '',
                                'credsid': '1',
                                'display_name': device_dict.get('display_name', ''),
                                'host': device_dict.get('name', ''),
                                'port': '22'
                            }

                            # Extract additional properties
                            for prop in device_dict.get('auto_properties', []):
                                if prop['name'] == 'auto.endpoint.model':
                                    session['Model'] = prop['value']
                                elif prop['name'] == 'auto.endpoint.serial_number':
                                    session['SerialNumber'] = prop['value']
                                elif prop['name'] == 'auto.entphysical.softwarerev':
                                    session['SoftwareVersion'] = prop['value']
                                elif prop['name'] == 'auto.endpoint.manufacturer':
                                    session['Vendor'] = prop['value']

                            devices_by_site[geo_site].append(session)

                        processed_devices += 1
                        progress = (processed_devices * 100) // total_devices
                        self.progress_signal.emit(progress)

                except ApiException:
                    break

            # Convert to final format and sort
            uglypty_list = []
            for site_name, sessions in sorted(devices_by_site.items()):
                folder_dict = {
                    'folder_name': site_name,
                    'sessions': sorted(sessions, key=lambda x: x['display_name'].lower())
                }
                uglypty_list.append(folder_dict)

            # Save successful settings
            settings = {
                "company": self.company,
                "access_id": self.access_id,
                "access_key": self.access_key,
                "cert_path": self.cert_path
            }
            try:
                with open("logicmonitor_settings.json", "w") as f:
                    json.dump(settings, f)
            except Exception as e:
                print(f"Failed to save LogicMonitor settings: {e}")

            self.save_file_signal.emit(uglypty_list)
            self.status_signal.emit("Download Complete")
            self.progress_signal.emit(100)

        except Exception as e:
            print("An error occurred:", e)
            self.status_signal.emit(f"Error: {str(e)}")


def create_default_settings():
    default_settings = {
        "company": "yourcompany",
        "access_id": "",
        "access_key": "",
        "cert_path": ""
    }
    with open("logicmonitor_settings.json", "w") as f:
        json.dump(default_settings, f)


class LMDownloader(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent

        # Get theme from parent window
        self.theme = parent.theme if hasattr(parent, 'theme') else 'cyberpunk'

        # Initialize window properties
        self.setWindowTitle('LogicMonitor Import')
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

        # Set defaults
        self.default_company = "yourcompany"
        self.default_access_id = "your_id_here"
        self.default_access_key = "your long key here"
        self.default_cert_path = ""

        # Create main frame with parent's theme
        self.main_frame = LayeredHUDFrame(
            self,
            theme_manager=parent.theme_manager,
            theme_name=self.theme
        )

        # Initialize UI
        self.initUI()

        # Load saved settings after UI is created
        self.load_settings()

        # Apply parent's theme
        if hasattr(parent, 'theme_manager'):
            parent.theme_manager.apply_theme(self, self.theme)

    def load_settings(self):
        """Load settings from JSON file if it exists"""
        try:
            if os.path.exists("logicmonitor_settings.json"):
                with open("logicmonitor_settings.json", "r") as f:
                    settings = json.load(f)

                # Update the input fields with saved values
                self.companyField.setText(settings.get("company", self.default_company))
                self.accessIdField.setText(settings.get("access_id", self.default_access_id))
                self.accessKeyField.setText(settings.get("access_key", self.default_access_key))
                self.certPathField.setText(settings.get("cert_path", self.default_cert_path))

                print("Settings loaded successfully")
            else:
                print("No settings file found, using defaults")

        except Exception as e:
            print(f"Failed to load settings: {e}")
            # If loading fails, keep the defaults that are already set

    def save_settings(self):
        """Save current field values to JSON file"""
        try:
            settings = {
                "company": self.companyField.text(),
                "access_id": self.accessIdField.text(),
                "access_key": self.accessKeyField.text(),
                "cert_path": self.certPathField.text()
            }

            with open("logicmonitor_settings.json", "w") as f:
                json.dump(settings, f, indent=2)

            print("Settings saved successfully")

        except Exception as e:
            print(f"Failed to save settings: {e}")

    def closeEvent(self, event):
        """Override close event to auto-save settings"""
        self.save_settings()
        event.accept()  # Allow the widget to close

    def initUI(self):
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_frame)

        # Content layout inside the frame
        layout = QVBoxLayout()
        self.main_frame.content_layout.addLayout(layout)

        # Title label
        title_label = QLabel("LogicMonitor Session Import")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Company input
        self.companyField = QLineEdit(self)
        self.companyField.setPlaceholderText('Enter your LogicMonitor company name')
        self.companyField.setText(self.default_company)  # This will be overridden by load_settings()
        layout.addWidget(self.companyField)

        # Access ID input
        self.accessIdField = QLineEdit(self)
        self.accessIdField.setPlaceholderText('Enter your Access ID')
        self.accessIdField.setText(self.default_access_id)  # This will be overridden by load_settings()
        layout.addWidget(self.accessIdField)

        # Access Key input
        self.accessKeyField = QLineEdit(self)
        self.accessKeyField.setPlaceholderText('Enter your Access Key')
        self.accessKeyField.setText(self.default_access_key)  # This will be overridden by load_settings()
        self.accessKeyField.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.accessKeyField)

        # Certificate Path input
        self.certPathField = QLineEdit(self)
        self.certPathField.setPlaceholderText('Enter path to Zscaler certificate (optional)')
        self.certPathField.setText(self.default_cert_path)  # This will be overridden by load_settings()
        layout.addWidget(self.certPathField)

        # Download button
        self.downloadButton = QPushButton('Download', self)
        self.downloadButton.clicked.connect(self.startDownloadThread)
        layout.addWidget(self.downloadButton)

        # Progress bar
        self.progress = QProgressBar(self)
        layout.addWidget(self.progress)

        # Status label
        self.statusLabel = QLabel('Status: Waiting', self)
        self.statusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.statusLabel)

        # Add spacing at the bottom
        layout.addStretch()

        # Set minimum size
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

    def update_theme(self, theme_name: str):
        """Update the widget's theme."""
        if hasattr(self, 'main_frame'):
            self.main_frame.set_theme(theme_name)

        # Get theme colors
        colors = self.parent.theme_manager.get_colors(theme_name)

        # Update progress bar style
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {colors['border']};
                border-radius: 0px;
                background-color: {colors['darker_bg']};
                color: {colors['text']};
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {colors['primary']};
            }}
        """)

        # Update button style
        self.downloadButton.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['primary']};
                color: {colors['background']};
                border: none;
                padding: 8px;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: {colors['button_hover']};
            }}
            QPushButton:pressed {{
                background-color: {colors['button_pressed']};
            }}
        """)

    def startDownloadThread(self):
        # Save settings before starting download
        self.save_settings()

        self.downloadButton.setEnabled(False)
        self.downloadThread = DownloadThread(
            self.companyField.text(),
            self.accessIdField.text(),
            self.accessKeyField.text(),
            self.certPathField.text() if self.certPathField.text() else None
        )
        self.downloadThread.progress_signal.connect(self.updateProgressBar)
        self.downloadThread.status_signal.connect(self.updateStatusLabel)
        self.downloadThread.save_file_signal.connect(self.showSaveFileDialog)
        self.downloadThread.finished.connect(lambda: self.downloadButton.setEnabled(True))
        self.downloadThread.start()

    def showSaveFileDialog(self, uglypty_list):
        filePath, _ = QFileDialog.getSaveFileName(
            self, "Save File", "", "YAML Files (*.yaml);;All Files (*)")
        if filePath:
            if not filePath.endswith('.yaml'):
                filePath += '.yaml'
            with open(filePath, "w") as f:
                yaml.dump(uglypty_list, f, default_flow_style=False)
            self.statusLabel.setText(f"Saved to {filePath}")

    def updateProgressBar(self, value):
        self.progress.setValue(value)

    def updateStatusLabel(self, text):
        self.statusLabel.setText(f"Status: {text}")
class ParentWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Initialize theme system
        self.theme_manager = ThemeLibrary()
        self.theme = 'cyberpunk'  # Default theme

        # Setup the window
        self.setWindowTitle('LogicMonitor Import Test')
        self.setGeometry(100, 100, 600, 400)

        # Create central widget with LayeredHUDFrame
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Main layout
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create the frame
        self.main_frame = LayeredHUDFrame(self, theme_manager=self.theme_manager, theme_name=self.theme)
        self.layout.addWidget(self.main_frame)

        # Import and create the LogicMonitor widget
        # from lmdialog import App
        self.lm_widget = LMDownloader(parent=self)
        self.main_frame.content_layout.addWidget(self.lm_widget)

        # Apply initial theme
        self.theme_manager.apply_theme(self, self.theme)

        # Set window flags for a modern look
        # self.setWindowFlags(Qt.WindowType.Window |
        #                     Qt.WindowType.FramelessWindowHint)

    def mousePressEvent(self, event):
        """Enable window dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        """Handle window dragging"""
        if hasattr(self, 'drag_pos'):
            new_pos = event.globalPosition().toPoint()
            self.move(self.pos() + new_pos - self.drag_pos)
            self.drag_pos = new_pos

    def mouseReleaseEvent(self, event):
        """Clean up after window dragging"""
        if hasattr(self, 'drag_pos'):
            del self.drag_pos


def main():
    app = QApplication(sys.argv)

    # Set application-wide style
    app.setStyle('Fusion')

    # Create and show the main window
    window = ParentWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()