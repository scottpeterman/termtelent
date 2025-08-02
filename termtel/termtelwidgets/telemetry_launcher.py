"""
Minimal Standalone Launcher for Telemetry Widget
Simple QMainWindow wrapper to launch the TelemetryWidget as a standalone app
"""

import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                             QMenuBar, QStatusBar, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QAction

from termtel.termtelwidgets.telemetry_widget import TelemetryWidget


class TelemetryLauncher(QMainWindow):
    """
    Minimal launcher window for standalone telemetry widget
    Provides basic window structure while keeping all functionality in the widget
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Network Telemetry - Standalone")
        self.setGeometry(100, 100, 1600, 900)

        # Setup minimal UI
        self._setup_menu_bar()
        self._setup_main_widget()
        self._setup_status_bar()

        print(" Telemetry Launcher initialized")

    def _setup_menu_bar(self):
        """Setup minimal menu bar"""
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("File")

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Help Menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_main_widget(self):
        """Setup the main telemetry widget"""
        # Create central widget container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Simple layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)  # No margins for full widget usage

        # Create and add telemetry widget
        self.telemetry_widget = TelemetryWidget(parent=self)

        # Connect to widget signals for status updates
        self.telemetry_widget.device_connected.connect(self._on_device_connected)
        self.telemetry_widget.device_disconnected.connect(self._on_device_disconnected)
        self.telemetry_widget.device_error.connect(self._on_device_error)
        self.telemetry_widget.widget_status_changed.connect(self._on_status_changed)

        layout.addWidget(self.telemetry_widget)

        print(" Telemetry widget embedded in launcher")

    def _setup_status_bar(self):
        """Setup status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Initial status
        self.status_bar.showMessage("Ready - No device connected")

    # ===== SIGNAL HANDLERS =====

    @pyqtSlot(str, str, object)
    def _on_device_connected(self, hostname, ip_address, device_info):
        """Handle device connection from widget"""
        print(f" Launcher: Device connected - {hostname} ({ip_address})")
        self.status_bar.showMessage(f"Connected to {hostname} ({ip_address})")

        # Update window title
        self.setWindowTitle(f"Network Telemetry - {hostname}")

    @pyqtSlot(str, str)
    def _on_device_disconnected(self, hostname, ip_address):
        """Handle device disconnection from widget"""
        print(f" Launcher: Device disconnected - {hostname}")
        self.status_bar.showMessage("Disconnected")

        # Reset window title
        self.setWindowTitle("Network Telemetry - Standalone")

    @pyqtSlot(str, str, str)
    def _on_device_error(self, hostname, ip_address, error_msg):
        """Handle device errors from widget"""
        print(f" Launcher: Device error - {hostname}: {error_msg}")
        self.status_bar.showMessage(f"Error: {error_msg}")

    @pyqtSlot(str)
    def _on_status_changed(self, status_message):
        """Handle general status changes from widget"""
        print(f" Launcher: Status - {status_message}")
        self.status_bar.showMessage(status_message, 3000)  # Show for 3 seconds

    # ===== MENU ACTIONS =====

    def _show_about(self):
        """Show about dialog"""
        about_text = """
Network Telemetry Widget - Standalone Launcher

This is a minimal launcher for the embeddable TelemetryWidget.

Features:
• SSH-only network device monitoring
• Multi-vendor platform support
• Template-driven data parsing
• Real-time telemetry collection
• Theme support
• Zero infrastructure requirements

The TelemetryWidget can be embedded in any PyQt6 application
or used standalone with this launcher.

Built with PyQt6 and Python
        """

        QMessageBox.about(self, "About Network Telemetry", about_text.strip())

    # ===== CLEANUP =====

    def closeEvent(self, event):
        """Handle application close"""
        print(" Launcher: Closing application")

        # Ensure telemetry widget is properly disconnected
        if hasattr(self.telemetry_widget, 'connection_status'):
            if self.telemetry_widget.connection_status == "connected":
                print(" Launcher: Disconnecting device before close")
                self.telemetry_widget._disconnect_device()

        event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Check for required dependencies
    missing_deps = []

    try:
        import netmiko
    except ImportError:
        missing_deps.append("netmiko")

    try:
        import textfsm
        from ntc_templates.parse import parse_output
    except ImportError:
        missing_deps.append("textfsm/ntc-templates")

    if missing_deps:
        print(f"Warning: Missing dependencies: {', '.join(missing_deps)}")
        print("Install with: pip install netmiko textfsm ntc-templates")
        print("Running with limited functionality...")

    # Create and show launcher window
    launcher = TelemetryLauncher()
    launcher.show()

    print(" Telemetry Launcher started")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()