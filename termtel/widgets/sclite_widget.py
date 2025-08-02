import sys
import os
from pathlib import Path
from typing import Dict, Optional, Callable
import yaml

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QFormLayout, QLineEdit, QSpinBox, QCheckBox,
                             QPushButton, QTextEdit, QSplitter, QFileDialog,
                             QComboBox, QLabel, QFrame, QGroupBox, QTabWidget)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QProcess, QUrl
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtSvg import QSvgWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView


class NetworkDiscoveryWorker(QThread):
    """Worker thread for network discovery"""
    progress_update = pyqtSignal(str)
    discovery_complete = pyqtSignal(bool, str, str)  # success flag, message, svg_path

    def __init__(self, config: Dict):
        super().__init__()
        self.config = config
        self.cancelled = False

    def run(self):
        try:
            # Get output directory and map name from config
            output_dir = Path(self.config.get('output_dir', './output'))
            map_name = self.config.get('map_name', 'network_map')

            # Create output directory if it doesn't exist
            output_dir.mkdir(parents=True, exist_ok=True)

            # Full path to the SVG file that will be generated
            svg_path = output_dir / f"{map_name}.svg"

            # Filter for valid DiscoveryConfig parameters
            from secure_cartography.network_discovery import DiscoveryConfig, NetworkDiscovery
            valid_params = set(DiscoveryConfig.__dataclass_fields__.keys())
            filtered_config = {k: v for k, v in self.config.items() if k in valid_params}

            # Create config object and discovery instance
            config = DiscoveryConfig(**filtered_config)
            discovery = NetworkDiscovery(config)

            # Set up progress callback
            def update_progress(stats):
                if stats.get('status') == 'success':
                    self.progress_update.emit(f"Discovered device: {stats.get('ip', 'unknown')}")
                elif stats.get('status') == 'failed':
                    self.progress_update.emit(f"Failed to connect to: {stats.get('ip', 'unknown')}")
                elif stats.get('status') == 'unreachable':
                    self.progress_update.emit(f"Unreachable host: {stats.get('ip', 'unknown')}")

                # Check for cancellation
                if self.cancelled:
                    return False  # Signal to stop discovery
                return True  # Continue discovery

            # Set the progress callback
            discovery.set_progress_callback(update_progress)

            # Run discovery
            self.progress_update.emit(f"Starting network discovery from {config.seed_ip}")
            self.progress_update.emit(f"Output will be saved to {config.output_dir}")

            network_map = discovery.crawl()

            # Check if discovery was cancelled
            if self.cancelled:
                self.discovery_complete.emit(False, "Discovery cancelled by user.", "")
                return

            # Show results
            stats = discovery.get_discovery_stats()
            self.progress_update.emit("\nDiscovery complete!")
            self.progress_update.emit(f"Devices discovered: {stats['devices_discovered']}")
            self.progress_update.emit(f"Devices failed: {stats['devices_failed']}")
            self.progress_update.emit(f"Unreachable hosts: {stats['unreachable_hosts']}")

            # Show output files
            self.progress_update.emit(f"\nOutput files created in {config.output_dir}:")
            self.progress_update.emit(f" - {config.map_name}.json")
            self.progress_update.emit(f" - {config.map_name}.graphml")
            self.progress_update.emit(f" - {config.map_name}.drawio")
            self.progress_update.emit(f" - {config.map_name}.svg")

            self.discovery_complete.emit(True, "Discovery completed successfully", str(svg_path))

        except Exception as e:
            self.progress_update.emit(f"Error during discovery: {str(e)}")
            self.discovery_complete.emit(False, str(e), "")

    def cancel(self):
        self.cancelled = True
        # The actual cancellation is handled in the update_progress callback

class SecureCartographyLiteWidget(QWidget):
    """PyQt6 widget for a simplified Secure Cartography interface"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.discovery_worker = None
        self.setup_ui()

    def setup_ui(self):
        # Main layout
        main_layout = QVBoxLayout(self)

        # Create splitter for form and output areas
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # Create form widget (top half)
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)

        # Network Settings Group
        network_group = QGroupBox("Network Settings")
        network_layout = QFormLayout()

        # Seed IP
        self.seed_ip = QLineEdit()
        self.seed_ip.setPlaceholderText("e.g., 192.168.1.1")
        network_layout.addRow("Seed IP:", self.seed_ip)

        # Domain Name
        self.domain_name = QLineEdit()
        self.domain_name.setPlaceholderText("e.g., example.local")
        network_layout.addRow("Domain Name:", self.domain_name)

        # Exclude String
        self.exclude_string = QLineEdit()
        self.exclude_string.setPlaceholderText("e.g., 192.168.5,10.0.0")
        network_layout.addRow("Exclude IPs:", self.exclude_string)

        # Timeout
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 300)
        self.timeout.setValue(30)
        self.timeout.setSuffix(" seconds")
        network_layout.addRow("Timeout:", self.timeout)

        # Max Devices
        self.max_devices = QSpinBox()
        self.max_devices.setRange(1, 1000)
        self.max_devices.setValue(100)
        self.max_devices.setSuffix(" devices")
        network_layout.addRow("Max Devices:", self.max_devices)

        # Finalize network group
        network_group.setLayout(network_layout)
        form_layout.addWidget(network_group)

        # Authentication Group
        auth_group = QGroupBox("Authentication")
        auth_layout = QFormLayout()

        # Primary Credentials
        self.username = QLineEdit()
        self.username.setPlaceholderText("Primary username")
        auth_layout.addRow("Username:", self.username)

        self.password = QLineEdit()
        self.password.setPlaceholderText("Primary password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        auth_layout.addRow("Password:", self.password)

        # Alternate Credentials
        self.alt_username = QLineEdit()
        self.alt_username.setPlaceholderText("Alternate username (optional)")
        auth_layout.addRow("Alt Username:", self.alt_username)

        self.alt_password = QLineEdit()
        self.alt_password.setPlaceholderText("Alternate password (optional)")
        self.alt_password.setEchoMode(QLineEdit.EchoMode.Password)
        auth_layout.addRow("Alt Password:", self.alt_password)

        # Finalize auth group
        auth_group.setLayout(auth_layout)
        form_layout.addWidget(auth_group)

        # Output Group
        output_group = QGroupBox("Output Settings")
        output_layout = QFormLayout()

        # Output Directory
        self.output_dir_layout = QHBoxLayout()
        self.output_dir = QLineEdit()
        self.output_dir.setText(str(Path('./output').resolve()))
        self.output_dir_layout.addWidget(self.output_dir)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_output_dir)
        self.output_dir_layout.addWidget(self.browse_btn)

        output_layout.addRow("Output Directory:", self.output_dir_layout)

        # Map Name
        self.map_name = QLineEdit("network_map")
        output_layout.addRow("Map Name:", self.map_name)

        # Layout Algorithm
        self.layout_algo = QComboBox()
        self.layout_algo.addItems(["kk", "spring", "circular", "random"])
        output_layout.addRow("Layout Algorithm:", self.layout_algo)

        # Debug Info
        self.save_debug = QCheckBox()
        output_layout.addRow("Save Debug Info:", self.save_debug)

        # Finalize output group
        output_group.setLayout(output_layout)
        form_layout.addWidget(output_group)

        # Action Buttons
        button_layout = QHBoxLayout()

        # Load Config Button
        self.load_config_btn = QPushButton("Load Config...")
        self.load_config_btn.clicked.connect(self.load_config)
        button_layout.addWidget(self.load_config_btn)

        # Add stretch to push run/cancel to the right
        button_layout.addStretch()

        # Run Button
        self.run_btn = QPushButton("Run Discovery")
        self.run_btn.clicked.connect(self.run_discovery)
        button_layout.addWidget(self.run_btn)

        # Cancel Button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_discovery)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)

        form_layout.addLayout(button_layout)

        # Add form widget to splitter
        self.splitter.addWidget(form_widget)

        # Create output widget with tabs (bottom half)
        self.output_tabs = QTabWidget()

        # Output Tab
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)

        # Output Text Area
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.output_text.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, monospace;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
            }
        """)
        output_layout.addWidget(self.output_text)
        self.output_tabs.addTab(output_widget, "Output")

        # Map Tab
        map_widget = QWidget()
        map_layout = QVBoxLayout(map_widget)

        # Create SVG widget for map preview
        self.map_view = QSvgWidget()
        self.map_view.setMinimumSize(400, 300)
        map_layout.addWidget(self.map_view)

        # Add SVG widget to map tab
        self.output_tabs.addTab(map_widget, "Map")

        # Add tabs to splitter
        self.splitter.addWidget(self.output_tabs)

        # Add splitter to main layout
        main_layout.addWidget(self.splitter)

        # Set initial splitter sizes
        self.splitter.setSizes([500, 300])

        # Set widget title
        self.setWindowTitle("Secure Cartography Lite")

        # Set minimum size
        self.setMinimumSize(700, 700)

    def browse_output_dir(self):
        """Open directory browser dialog"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            self.output_dir.text())

        if directory:
            self.output_dir.setText(directory)

    def load_config(self):
        """Load configuration from YAML file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Configuration File", "",
            "YAML Files (*.yaml *.yml);;All Files (*)")

        if not file_path:
            return

        try:
            with open(file_path, 'r') as f:
                config = yaml.safe_load(f)

            if not config:
                self.append_output("Error: Empty configuration file")
                return

            # Apply loaded configuration to UI
            self._apply_config_to_ui(config)
            self.append_output(f"Configuration loaded from {file_path}")

        except Exception as e:
            self.append_output(f"Error loading configuration: {str(e)}")

    def _apply_config_to_ui(self, config):
        """Apply configuration dict to UI elements"""
        # Network settings
        if 'seed_ip' in config:
            self.seed_ip.setText(config['seed_ip'])
        if 'domain_name' in config:
            self.domain_name.setText(config['domain_name'])
        if 'exclude_string' in config:
            self.exclude_string.setText(config['exclude_string'])
        if 'timeout' in config:
            self.timeout.setValue(config['timeout'])
        if 'max_devices' in config:
            self.max_devices.setValue(config['max_devices'])

        # Authentication settings
        if 'username' in config:
            self.username.setText(config['username'])
        if 'password' in config:
            self.password.setText(config['password'])
        if 'alternate_username' in config:
            self.alt_username.setText(config['alternate_username'])
        if 'alternate_password' in config:
            self.alt_password.setText(config['alternate_password'])

        # Output settings
        if 'output_dir' in config:
            self.output_dir.setText(str(config['output_dir']))
        if 'map_name' in config:
            self.map_name.setText(config['map_name'])
        if 'layout_algo' in config:
            index = self.layout_algo.findText(config['layout_algo'])
            if index >= 0:
                self.layout_algo.setCurrentIndex(index)
        if 'save_debug_info' in config:
            self.save_debug.setChecked(config['save_debug_info'])

    def get_form_values(self) -> Dict:
        """Get current form values as a dictionary"""
        return {
            # Network settings
            'seed_ip': self.seed_ip.text(),
            'domain_name': self.domain_name.text(),
            'exclude_string': self.exclude_string.text(),
            'timeout': self.timeout.value(),
            'max_devices': self.max_devices.value(),

            # Authentication settings
            'username': self.username.text(),
            'password': self.password.text(),
            'alternate_username': self.alt_username.text(),
            'alternate_password': self.alt_password.text(),

            # Output settings
            'output_dir': self.output_dir.text(),
            'map_name': self.map_name.text(),
            'layout_algo': self.layout_algo.currentText(),
            'save_debug_info': self.save_debug.isChecked()
        }

    def validate_config(self) -> bool:
        """Validate form values, return False and show errors if invalid"""
        config = self.get_form_values()
        errors = []

        # Check required fields
        if not config['seed_ip']:
            errors.append("Seed IP is required")
        if not config['username']:
            errors.append("Username is required")
        if not config['password']:
            errors.append("Password is required")

        if errors:
            self.append_output("VALIDATION ERRORS:")
            for error in errors:
                self.append_output(f"- {error}")
            return False

        return True

    def run_discovery(self):
        """Run network discovery with current configuration"""
        if not self.validate_config():
            return

        # Get configuration
        config = self.get_form_values()

        # Clear output
        self.output_text.clear()
        self.append_output("Starting network discovery...")

        # Switch to output tab
        self.output_tabs.setCurrentIndex(0)

        # Update UI
        self.run_btn.setEnabled(False)
        self.load_config_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        # Create and start worker
        self.discovery_worker = NetworkDiscoveryWorker(config)
        self.discovery_worker.progress_update.connect(self.append_output)
        self.discovery_worker.discovery_complete.connect(self.discovery_finished)
        self.discovery_worker.start()

    def cancel_discovery(self):
        """Cancel ongoing discovery"""
        if self.discovery_worker and self.discovery_worker.isRunning():
            self.append_output("Cancelling discovery...")
            self.discovery_worker.cancel()

    def discovery_finished(self, success: bool, message: str, svg_path: str):
        """Handle discovery completion"""
        if success:
            self.append_output("\nDISCOVERY COMPLETED SUCCESSFULLY")
            config = self.get_form_values()
            output_path = Path(config['output_dir'])
            map_name = config['map_name']

            # Display output file information
            self.append_output(f"\nOutput files created in {output_path}:")
            self.append_output(f" - {map_name}.svg")

            # Load SVG into map view
            if svg_path and Path(svg_path).exists():
                self.map_view.load(svg_path)
                self.append_output(f"\nMap preview available in the Map tab")

                # Switch to map tab
                self.output_tabs.setCurrentIndex(1)
            else:
                self.append_output(f"\nWarning: SVG file not found at {svg_path}")
        else:
            self.append_output(f"\nDISCOVERY FAILED: {message}")

        # Update UI
        self.run_btn.setEnabled(True)
        self.load_config_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def append_output(self, text: str):
        """Append text to output area and scroll to bottom"""
        cursor = self.output_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.output_text.setTextCursor(cursor)
        self.output_text.ensureCursorVisible()


# Stand-alone test function
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # For consistent cross-platform look

    widget = SecureCartographyLiteWidget()
    widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()