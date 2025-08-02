"""
Embeddable Telemetry Widget - Phase 1 Refactor
Converts EnhancedTelemetryMainWindow into a reusable QWidget component
"""

import sys
import time
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSplitter, QComboBox, QTextEdit,
                             QMessageBox, QProgressDialog, QProgressBar,
                             QFrame)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal

from termtel.termtelwidgets.enhanced_cpu_widget import PlatformAgnosticCPUWidget
from termtel.termtelwidgets.enhanced_log_widget import SimplifiedLogWidget
# Import all telemetry components
from termtel.termtelwidgets.normalized_widgets import (EnhancedNeighborWidget, ConnectionStatusWidget, FixedRouteWidget)
from termtel.termtelwidgets.threaded_telemetry import ThreadedTelemetryController
from termtel.termtelwidgets.netmiko_controller import EnhancedPlatformAwareTelemetryController

# Import the Platform Configuration UI from separate file

PLATFORM_UI_AVAILABLE = True


class TelemetryWidget(QWidget):
    """
    Embeddable Telemetry Widget - Core telemetry functionality as a QWidget
    Can be embedded in any PyQt6 application or used standalone
    """

    # Widget-level signals for parent integration
    device_connected = pyqtSignal(str, str, object)  # hostname, ip, device_info
    device_disconnected = pyqtSignal(str, str)  # hostname, ip
    device_error = pyqtSignal(str, str, str)  # hostname, ip, error_msg
    telemetry_data_updated = pyqtSignal(str, dict)  # device_id, telemetry_snapshot
    widget_status_changed = pyqtSignal(str)  # status_message

    def __init__(self, shared_services=None, device_config=None, parent=None):
        """
        Initialize Telemetry Widget

        Args:
            shared_services: Optional shared services (theme_manager, credential_manager, etc.)
            device_config: Optional pre-configured device connection info
            parent: Parent widget
        """
        super().__init__(parent)

        # Configuration
        self.shared_services = shared_services
        self.device_config = device_config
        self.parent_app = parent

        # Theme state tracking
        self.current_theme = None
        self.theme_change_in_progress = False

        # Initialize theme system
        self._init_theme_system()

        # Create enhanced controller with netmiko support
        self._init_controller()

        # Setup UI
        self._setup_widget_ui()
        self._connect_signals()

        # Connect to parent theme signals if available
        self._connect_parent_theme_signals()

        # Apply initial theme
        self._apply_initial_theme()

        # Status tracking
        self.connection_status = "disconnected"
        self.last_data_update = None

        # Auto-connect if device config provided
        if self.device_config:
            QTimer.singleShot(1000, self._auto_connect)
        try:
            self.credential_manager = parent.cred_manager

        except:
            print("parent creds manager not found")
            self.credential_manager = None
        if self.credential_manager:
            print(f"Cred manager initialized: {self.credential_manager.is_initialized}")
            print(f"Cred manager unlocked: {self.credential_manager.is_unlocked()}")

        # if shared_services:
        #     # Try different attribute names that might contain the credential manager
        #     for attr_name in ['credential_manager', 'cred_manager', 'credentials']:
        #         if hasattr(shared_services, attr_name):
        #             self.credential_manager = getattr(shared_services, attr_name)
        #             print(f" Found credential manager at shared_services.{attr_name}")
        #             break

    def cleanup(self):
        """Enhanced cleanup"""
        print(" TelemetryWidget cleanup called")

        # Cleanup controller
        if hasattr(self.controller, 'cleanup'):
            self.controller.cleanup()

        print(" TelemetryWidget cleanup completed")

    def _init_theme_system(self):
        """Initialize theme system - use shared or create own"""
        try:
            if self.shared_services and hasattr(self.shared_services, 'theme_manager'):
                self.theme_library = self.shared_services.theme_manager
                self.available_themes = self.theme_library.get_theme_names()
                print(" Using shared theme manager")
            else:
                # Use main theme system instead of termtelwidgets themes
                from termtel.themes3 import ThemeLibrary
                self.theme_library = ThemeLibrary()
                self.available_themes = self.theme_library.get_theme_names()
                print(" Created main theme library")
        except ImportError:
            print("Warning: Main theme library not available, using fallback")
            self.theme_library = None
            self.available_themes = ["cyberpunk"]

    def _connect_parent_theme_signals(self):
        """Connect to parent application's theme change signals"""
        # Skip signal connection for now - we'll handle theme changes directly
        # from the setup.py safe_switch_theme function
        print("Theme changes will be handled directly by parent application")

    @pyqtSlot(str)
    def _on_parent_theme_changed(self, theme_name):
        """
        Handle theme change signal from parent application
        This is the key method that prevents crashes
        """
        print(f" Received theme change from parent: {theme_name}")

        # Prevent recursive theme changes
        if self.theme_change_in_progress:
            print(" Theme change already in progress, skipping")
            return

        self.theme_change_in_progress = True

        try:
            # Apply theme safely to this widget
            self._apply_theme_safe(theme_name)

            # Update internal theme combo if it exists
            if hasattr(self, 'theme_combo'):
                # Temporarily disconnect to prevent recursion
                self.theme_combo.currentTextChanged.disconnect()
                self.theme_combo.setCurrentText(theme_name)
                self.theme_combo.currentTextChanged.connect(self._on_theme_changed)

        except Exception as e:
            print(f" Error applying parent theme: {e}")
        finally:
            self.theme_change_in_progress = False

    def _apply_theme_safe(self, theme_name: str):
        """
        Safely apply theme to all components including threaded ones
        """
        print(f" Applying theme safely: {theme_name}")

        # Store current theme
        self.current_theme = theme_name

        # Apply to main widget
        if self.theme_library:
            try:
                self.theme_library.apply_theme(self, theme_name)
            except Exception as e:
                print(f" Error applying theme to main widget: {e}")

        # Apply to controller (threaded components)
        try:
            if hasattr(self.controller, 'set_theme'):
                self.controller.set_theme(theme_name)
            elif hasattr(self.controller, 'change_theme'):
                self.controller.change_theme(theme_name)
        except Exception as e:
            print(f" Error applying theme to controller: {e}")

        # Apply to individual widgets that might have their own theme handling
        self._apply_theme_to_child_widgets(theme_name)

    def _apply_theme_to_child_widgets(self, theme_name: str):
        """Apply theme to child widgets that have their own theme methods"""
        theme_aware_widgets = [
            'neighbor_widget',
            'arp_widget',
            'cpu_widget',
            'route_widget',
            'log_widget',
            'connection_status_widget'
        ]

        for widget_name in theme_aware_widgets:
            if hasattr(self, widget_name):
                widget = getattr(self, widget_name)

                # Try different theme method signatures
                try:
                    if hasattr(widget, 'apply_theme'):
                        widget.apply_theme(theme_name)
                    elif hasattr(widget, 'set_theme'):
                        widget.set_theme(theme_name)
                    elif hasattr(widget, 'change_theme'):
                        widget.change_theme(theme_name)
                    elif self.theme_library:
                        # Fallback: apply theme directly
                        self.theme_library.apply_theme(widget, theme_name)
                except Exception as e:
                    print(f" Could not apply theme to {widget_name}: {e}")

    # Public API for parent applications to safely change themes
    def set_theme_from_parent(self, theme_name: str):
        """
        Public API for parent applications to change widget theme
        Use this instead of direct theme library calls
        """
        print(f" Theme change requested from parent API: {theme_name}")
        self._on_parent_theme_changed(theme_name)

    def get_current_theme(self):
        """Get the currently applied theme name"""
        return self.current_theme

    def _init_controller(self):
        """Initialize telemetry controller"""
        try:
            original_controller = EnhancedPlatformAwareTelemetryController(self.theme_library)
            self.controller = ThreadedTelemetryController(original_controller)
            print(" Telemetry controller initialized")
        except ImportError:
            print("Error: Enhanced controller not available")
            raise ImportError("Required telemetry controller not available")

    def _setup_widget_ui(self):
        """Setup the widget UI layout"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)  # Smaller margins for embedded use

        # Left panel - Controls and status (smaller for embedded use)
        left_panel = self._create_control_panel()
        left_panel.setFixedWidth(280)  # Smaller than standalone version
        main_layout.addWidget(left_panel)
        left_panel.setVisible(False)
        # Right panel - Telemetry widgets
        right_panel = self._create_telemetry_panel()
        main_layout.addWidget(right_panel)

    def _create_control_panel(self):
        """Create compact control panel for embedded use"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)  # Tighter spacing

        # Widget header
        header = self._create_widget_header()
        layout.addWidget(header)

        # Theme selector (optional for embedded use)
        if not self.shared_services or not hasattr(self.shared_services, 'theme_manager'):
            theme_section = self._create_theme_section()
            layout.addWidget(theme_section)

        # Platform management (compact version)
        if PLATFORM_UI_AVAILABLE:
            platform_section = self._create_compact_platform_section()
            layout.addWidget(platform_section)

        # Connection section
        connection_section = self._create_connection_section()
        layout.addWidget(connection_section)

        # Connection status widget
        self._create_status_widget(layout)

        # Control buttons
        controls_section = self._create_controls_section()
        layout.addWidget(controls_section)

        layout.addStretch()
        return panel

    def _create_widget_header(self):
        """Create widget header with title and status"""
        header = QFrame()
        header.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(8, 8, 8, 8)

        # Title
        title = QLabel("NETWORK TELEMETRY")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #00ffff;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Device info (populated when connected)
        self.device_info_label = QLabel("No device connected")
        self.device_info_label.setStyleSheet("font-size: 10px; color: #888888;")
        self.device_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.device_info_label.setWordWrap(True)
        layout.addWidget(self.device_info_label)

        return header

    def _create_theme_section(self):
        """Create theme selection section (for standalone use)"""
        section = QWidget()
        layout = QVBoxLayout(section)

        title = QLabel("THEME")
        title.setStyleSheet("font-weight: bold; font-size: 11px; padding: 3px;")
        layout.addWidget(title)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(self.available_themes)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        layout.addWidget(self.theme_combo)

        return section

    def _create_compact_platform_section(self):
        """Create compact platform management section"""
        section = QWidget()
        layout = QVBoxLayout(section)

        title = QLabel("PLATFORMS")
        title.setStyleSheet("font-weight: bold; font-size: 11px; padding: 3px;")
        layout.addWidget(title)

        # Platform count info
        self.platform_info_label = QLabel("Loading...")
        self.platform_info_label.setStyleSheet("font-size: 9px; color: #888888; padding: 3px;")
        layout.addWidget(self.platform_info_label)

        # Compact buttons
        button_layout = QHBoxLayout()

        manage_btn = QPushButton("Manage")
        manage_btn.setMaximumHeight(25)
        manage_btn.clicked.connect(self._open_platform_manager)
        button_layout.addWidget(manage_btn)

        reload_btn = QPushButton("Reload")
        reload_btn.setMaximumHeight(25)
        reload_btn.clicked.connect(self._reload_platform_configurations)
        button_layout.addWidget(reload_btn)

        layout.addLayout(button_layout)
        self._update_platform_info()

        return section

    def _create_connection_section(self):
        """Create connection controls section"""
        section = QWidget()
        layout = QVBoxLayout(section)

        title = QLabel("CONNECTION")
        title.setStyleSheet("font-weight: bold; font-size: 11px; padding: 3px;")
        layout.addWidget(title)

        # Connection buttons

        return section

    def _create_status_widget(self, layout):
        """Create connection status widget"""
        try:
            from termtel.termtelwidgets.normalized_widgets import ConnectionStatusWidget
            self.connection_status_widget = ConnectionStatusWidget(self.controller, self.theme_library)
            self.connection_status_widget.setMaximumHeight(180)  # Compact for embedding
            layout.addWidget(self.connection_status_widget)
        except ImportError:
            # Fallback simple status display
            self.connection_status_widget = QTextEdit()
            self.connection_status_widget.setMaximumHeight(150)
            self.connection_status_widget.setReadOnly(True)
            self.connection_status_widget.setPlainText("Connection Status: Disconnected")
            layout.addWidget(self.connection_status_widget)

    def _create_controls_section(self):
        """Create data control buttons section"""
        section = QWidget()
        layout = QVBoxLayout(section)

        title = QLabel("DATA CONTROLS")
        title.setStyleSheet("font-weight: bold; font-size: 11px; padding: 3px;")
        layout.addWidget(title)

        # Compact control buttons
        self.refresh_button = QPushButton("Refresh All")
        self.refresh_button.setMaximumHeight(25)
        self.refresh_button.clicked.connect(self._refresh_all_data)
        self.refresh_button.setEnabled(False)
        layout.addWidget(self.refresh_button)

        self.auto_refresh_button = QPushButton("Auto-Refresh")
        self.auto_refresh_button.setMaximumHeight(25)
        self.auto_refresh_button.clicked.connect(self._toggle_auto_refresh)
        self.auto_refresh_button.setEnabled(False)
        layout.addWidget(self.auto_refresh_button)

        # Compact status
        self.data_status_label = QLabel("Last Update: Never")
        self.data_status_label.setStyleSheet("font-size: 9px; color: #888888; padding: 3px;")
        layout.addWidget(self.data_status_label)

        return section

    def _create_telemetry_panel(self):
        """Create right panel with telemetry widgets"""
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top row - Neighbors and ARP
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        try:
            from termtel.termtelwidgets.normalized_widgets import EnhancedNeighborWidget, EnhancedArpWidget
            self.neighbor_widget = EnhancedNeighborWidget(self.controller, self.theme_library)
            self.arp_widget = EnhancedArpWidget(self.controller, self.theme_library)
        except ImportError:
            # Fallback widgets
            self.neighbor_widget = QTextEdit()
            self.neighbor_widget.setPlainText("Neighbor Widget (Enhanced version not available)")
            self.arp_widget = QTextEdit()
            self.arp_widget.setPlainText("ARP Widget (Enhanced version not available)")

        # Create connection buttons
        self.connect_button = QPushButton("Connect")
        self.connect_button.setMaximumHeight(28)
        self.connect_button.clicked.connect(self._show_connection_dialog)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setMaximumHeight(28)
        self.disconnect_button.clicked.connect(self._disconnect_device)
        self.disconnect_button.setEnabled(False)

        top_splitter.addWidget(self.neighbor_widget)
        top_splitter.addWidget(self.arp_widget)
        splitter.addWidget(top_splitter)

        # Middle row - CPU/System and Route table
        middle_splitter = QSplitter(Qt.Orientation.Horizontal)

        # CPU widget
        self._create_cpu_widget(middle_splitter)

        # Route table widget
        self._create_route_widget(middle_splitter)

        splitter.addWidget(middle_splitter)

        # Bottom row - Logs
        self._create_log_widget(splitter)

        # Create connection button row at the bottom
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(5, 5, 5, 5)
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.disconnect_button)
        button_layout.addStretch()  # Push buttons to the left

        splitter.addWidget(button_row)

        return splitter

    def _create_cpu_widget(self, parent_splitter):
        """Create CPU/system metrics widget"""
        try:
            # from enhanced_cpu_widget import PlatformAgnosticCPUWidget
            self.cpu_widget = PlatformAgnosticCPUWidget(self.controller, self.theme_library)
            print(" Using PlatformAgnosticCPUWidget")
        except ImportError:
            try:
                from enhanced_cpu_widget import SimplifiedCPUWidget
                self.cpu_widget = SimplifiedCPUWidget(self.controller, self.theme_library)
                print(" Using SimplifiedCPUWidget")
            except ImportError:
                self.cpu_widget = self._create_simple_cpu_widget()
                print(" Using fallback CPU widget")

        parent_splitter.addWidget(self.cpu_widget)

    def _create_route_widget(self, parent_splitter):
        """Create route table widget"""
        try:
            # from normalized_widgets import FixedRouteWidget
            self.route_widget = FixedRouteWidget(self.controller, self.theme_library)
            print(" Using FixedRouteWidget")
        except ImportError:
            try:
                from normalized_widgets import EnhancedRouteWidget
                self.route_widget = EnhancedRouteWidget(self.controller, self.theme_library)
                print(" Using EnhancedRouteWidget")
            except ImportError:
                self.route_widget = QTextEdit()
                self.route_widget.setPlainText("Route Widget (Enhanced version not available)")
                print(" Using fallback route widget")

        parent_splitter.addWidget(self.route_widget)

    def _create_log_widget(self, parent_splitter):
        """Create log viewer widget"""
        try:
            # from enhanced_log_widget import SimplifiedLogWidget
            self.log_widget = SimplifiedLogWidget(self.controller, self.theme_library)
            print(" Using SimplifiedLogWidget")
        except ImportError:
            self.log_widget = QTextEdit()
            self.log_widget.setMaximumHeight(120)  # Compact for embedding
            self.log_widget.setPlainText("System logs will appear here...")
            print(" Using fallback log widget")

        parent_splitter.addWidget(self.log_widget)

    def _create_simple_cpu_widget(self):
        """Create simple fallback CPU widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("CPU/MEMORY")
        title.setStyleSheet("font-weight: bold; text-align: center;")
        layout.addWidget(title)

        content = QTextEdit()
        content.setPlainText("CPU and memory data will appear here...")
        content.setMaximumHeight(150)
        layout.addWidget(content)

        return widget

    def _connect_signals(self):
        """Connect controller signals to widget updates"""
        # Connection status signals
        self.controller.connection_status_changed.connect(self._on_connection_status_changed)
        self.controller.device_info_updated.connect(self._on_device_info_updated)

        # Data update signals
        self.controller.normalized_neighbors_ready.connect(self._on_data_updated)
        self.controller.normalized_arp_ready.connect(self._on_data_updated)
        self.controller.normalized_routes_ready.connect(self._on_data_updated)

        # Raw output signals
        self.controller.raw_log_output.connect(self._on_log_output)
        if hasattr(self.controller, 'connection_error_occurred'):
            self.controller.connection_error_occurred.connect(self._on_connection_error_occurred)
            print(" Connected to enhanced error signal")
        else:
            print(" Enhanced error signal not available")

    def _apply_initial_theme(self):
        """Apply initial theme"""
        if self.available_themes:
            initial_theme = "cyberpunk" if "cyberpunk" in self.available_themes else self.available_themes[0]
            self._apply_theme_safe(initial_theme)

    # ===== CONNECTION METHODS =====

    def _auto_connect(self):
        """Auto-connect using provided device config"""
        if self.device_config:
            print(f" Auto-connecting to {self.device_config.get('hostname', 'Unknown')}")
            # TODO: Implement auto-connection logic
            pass

    def _show_connection_dialog(self):
        """Show connection dialog - FIXED to store dialog reference properly"""
        try:
            from termtel.termtelwidgets.connection_dialog import DeviceConnectionDialog
            print(" Creating connection dialog...")

            # Store dialog reference BEFORE connecting signals
            self.active_connection_dialog = DeviceConnectionDialog(self.theme_library, parent=self.parent_app)

            print(f" Dialog created: {self.active_connection_dialog}")

            # Connect the signal
            self.active_connection_dialog.connection_requested.connect(self._handle_connection_request)

            print(f" Signal connected, showing modal dialog...")
            result = self.active_connection_dialog.exec()
            print(f" Dialog closed with result: {result}")

            # Clear reference when dialog is closed
            self.active_connection_dialog = None

        except ImportError as e:
            print(f"Import error: {e}")
            QMessageBox.information(self, "Connection", "Connection dialog not available.")

    @pyqtSlot(str, str, str, object)
    def _handle_connection_request(self, hostname, ip_address, platform, credentials):
        """Handle connection request from dialog - FIXED with proper dialog storage"""
        print(f" Connection requested: {hostname} ({ip_address}) - {platform}")

        # CRITICAL: Get dialog reference from the sender (the dialog that emitted the signal)
        dialog = self.sender()  # This is the actual dialog object

        print(f" Dialog from sender: {dialog}")
        print(f" Active dialog reference: {getattr(self, 'active_connection_dialog', None)}")

        # Also store in backup attributes for threaded access
        self._connection_dialog = dialog
        self._connection_hostname = hostname
        self._connection_ip = ip_address

        print(f" Stored dialog reference: {self._connection_dialog is not None}")

        try:
            # Update UI immediately
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(False)
            self.device_info_label.setText(f"Connecting to {hostname}...")

            # Start the worker thread
            success = self.controller.connect_to_device(hostname, ip_address, platform, credentials)

            if success:
                print(f" Worker thread started for {hostname}")
                self.widget_status_changed.emit(f"Connecting to {hostname}")

                # Set up connection timeout
                if not hasattr(self, 'connection_timeout_timer'):
                    self.connection_timeout_timer = QTimer()
                    self.connection_timeout_timer.setSingleShot(True)
                    self.connection_timeout_timer.timeout.connect(self._handle_connection_timeout)

                self.connection_timeout_timer.start(30000)  # 30 second timeout
                return success
            else:
                self._handle_immediate_connection_failure("Failed to start connection")
                return False

        except Exception as e:
            print(f" Connection error: {e}")
            self._handle_immediate_connection_failure(f"Connection error: {str(e)}")
            return False

    def _handle_immediate_connection_failure(self, error_msg):
        """Handle immediate connection failures"""
        print(f" Immediate connection failure: {error_msg}")

        dialog = getattr(self, '_connection_dialog', None)
        hostname = getattr(self, '_connection_hostname', 'Unknown')
        ip_address = getattr(self, '_connection_ip', '')

        print(f" Immediate failure - Dialog available: {dialog is not None}")

        if dialog and hasattr(dialog, 'handle_connection_failure'):
            print(f" Calling dialog.handle_connection_failure for immediate failure")
            dialog.handle_connection_failure(hostname, ip_address, error_msg)
        else:
            print(f" No dialog reference, showing fallback error message")
            QMessageBox.critical(self, "Connection Error", error_msg)

        self._reset_connection_ui()
        self._clear_connection_monitoring()

    def _handle_connection_timeout(self):
        """Handle connection timeout"""
        print("⏰ Connection timeout")

        dialog = getattr(self, '_connection_dialog', None)
        hostname = getattr(self, '_connection_hostname', 'Unknown')
        ip_address = getattr(self, '_connection_ip', '')

        print(f" Timeout - Dialog available: {dialog is not None}")

        if dialog and hasattr(dialog, 'handle_connection_failure'):
            print(f" Calling dialog.handle_connection_failure for timeout")
            dialog.handle_connection_failure(hostname, ip_address, "Connection timeout after 30 seconds")
        else:
            print(f" No dialog reference for timeout")
            QMessageBox.critical(self, "Connection Timeout", "Connection attempt timed out after 30 seconds")

        self._reset_connection_ui()
        self._clear_connection_monitoring()

    @pyqtSlot(str, str, str)  # NEW SLOT
    def _on_connection_error_occurred(self, device_ip, hostname, error_message):
        """Handle detailed connection error - NEW METHOD"""
        print(f" DETAILED ERROR: {hostname} ({device_ip}) -> {error_message}")

        # Stop timeout timer
        if hasattr(self, 'connection_timeout_timer'):
            self.connection_timeout_timer.stop()

        # Reset UI
        self._reset_connection_ui()

        # Get stored dialog
        dialog = getattr(self, '_connection_dialog', None)

        print(f" Error handler - Dialog available: {dialog is not None}")

        if dialog and hasattr(dialog, 'handle_connection_failure'):
            print(f" Calling dialog.handle_connection_failure with detailed error")
            dialog.handle_connection_failure(hostname, device_ip, error_message)
        else:
            print(f" No dialog reference, showing fallback error message")
            QMessageBox.critical(self, "Connection Failed", f"Failed to connect to {hostname}:\n\n{error_message}")

        # Emit error signal
        self.device_error.emit(hostname, device_ip, error_message)

        # Clear connection monitoring
        self._clear_connection_monitoring()

    def _disconnect_device(self):
        """Disconnect from current device"""
        print(f" Disconnect requested")

        if hasattr(self.controller, 'disconnect_from_device'):
            self.controller.disconnect_from_device()

        self._reset_connection_ui()
        self.device_info_label.setText("No device connected")

        # Emit widget-level signal
        self.widget_status_changed.emit("Disconnected")
        print(f" Disconnection completed")

    def _reset_connection_ui(self):
        """Reset UI to disconnected state"""
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.auto_refresh_button.setEnabled(False)
        self.connection_status = "disconnected"

    # ===== DATA COLLECTION METHODS =====

    def _refresh_all_data(self):
        """Refresh all telemetry data"""
        print(f" Manual refresh requested")

        if hasattr(self.controller, 'collect_telemetry_data'):
            self.controller.collect_telemetry_data()

            timestamp = time.strftime("%H:%M:%S")
            self.data_status_label.setText(f"Refresh: {timestamp}")

            # Emit widget-level signal
            self.widget_status_changed.emit("Refreshing data...")

    def _toggle_auto_refresh(self):
        """Toggle automatic data refresh"""
        print(f" Auto-refresh toggle clicked")

        if hasattr(self.controller, 'worker_thread') and self.controller.worker_thread:
            worker = self.controller.worker_thread

            if worker.auto_collect:
                self.controller.stop_auto_refresh()
                self.auto_refresh_button.setText("Start Auto")
                self.data_status_label.setText("Auto-refresh: Stopped")
                print(f" Auto-refresh stopped")
            else:
                self.controller.start_auto_refresh(30)
                self.auto_refresh_button.setText("Stop Auto")
                self.data_status_label.setText("Auto-refresh: 30s")
                print(f" Auto-refresh started")

    # ===== SIGNAL HANDLERS =====

    @pyqtSlot(str, str)
    def _on_connection_status_changed(self, device_ip, status):
        """Handle connection status changes - FIXED success handling"""
        print(f" Connection status: '{device_ip}' -> '{status}'")

        self.connection_status = status

        if status == "connected":
            print(f" Connection successful to {device_ip}")

            # Stop timeout timer
            if hasattr(self, 'connection_timeout_timer'):
                self.connection_timeout_timer.stop()

            # Update UI
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.auto_refresh_button.setEnabled(True)

            dialog = getattr(self, '_connection_dialog', None)
            hostname = getattr(self, '_connection_hostname', 'Unknown')
            dialog.accept()
            print(f" Success handler - Dialog available: {dialog is not None}")
            print(f" Success handler - Dialog type: {type(dialog) if dialog else 'None'}")

            if dialog and hasattr(dialog, 'handle_connection_success'):
                print(f" Calling dialog.handle_connection_success('{hostname}', '{device_ip}')")
                try:
                    dialog.handle_connection_success(hostname, device_ip)
                    print(f" Success handler called successfully")
                except Exception as e:
                    print(f" Error calling success handler: {e}")
            else:
                print(f" No dialog reference or method for success feedback")
                print(f"    Dialog: {dialog}")
                print(f"    Has method: {hasattr(dialog, 'handle_connection_success') if dialog else False}")

            # Emit widget-level signals
            if hasattr(self, 'current_hostname'):
                self.device_connected.emit(self.current_hostname, device_ip, None)
            self.widget_status_changed.emit(f"Connected to {device_ip}")

            # Clear monitoring
            self._clear_connection_monitoring()

        elif "failed" in status:
            print(f" Connection failed to {device_ip}")

            # Stop timeout timer
            if hasattr(self, 'connection_timeout_timer'):
                self.connection_timeout_timer.stop()

            # Reset UI
            self._reset_connection_ui()

            # Get stored dialog and call failure handler
            dialog = getattr(self, '_connection_dialog', None)
            hostname = getattr(self, '_connection_hostname', 'Unknown')

            print(f" Failure handler - Dialog available: {dialog is not None}")

            if dialog and hasattr(dialog, 'handle_connection_failure'):
                print(f" Calling dialog.handle_connection_failure")
                dialog.handle_connection_failure(hostname, device_ip,
                                                 "Connection failed - check credentials and network connectivity")
            else:
                print(f" No dialog reference for failure feedback")
                print(f"status: {status}")
                QMessageBox.critical(self, f"Connection Failed", f"{status}")

            # Emit error signal
            self.device_error.emit("", device_ip, "Connection failed")

            # Clear monitoring
            self._clear_connection_monitoring()

        elif status == "disconnected":
            self._reset_connection_ui()
            if hasattr(self, 'current_hostname'):
                self.device_disconnected.emit(self.current_hostname, device_ip)

    def _clear_connection_monitoring(self):
        """Clear connection monitoring state - ENHANCED"""
        print(f" Clearing connection monitoring state")

        if hasattr(self, 'connection_timeout_timer'):
            self.connection_timeout_timer.stop()

        # Clear all dialog references
        self._connection_dialog = None
        self._connection_hostname = None
        self._connection_ip = None

    @pyqtSlot(object)
    def _on_device_info_updated(self, device_info):
        """Handle device info updates"""
        print(f" Device info updated: {device_info.hostname}")

        # Update device info display
        info_text = f"{device_info.hostname}\n{device_info.platform}\n{device_info.version}"
        self.device_info_label.setText(info_text)

        # Store for signal emission
        self.current_hostname = device_info.hostname

        # Emit widget-level signal
        self.device_connected.emit(device_info.hostname, device_info.ip_address, device_info)

    @pyqtSlot(list)
    def _on_data_updated(self, data):
        """Handle data updates from worker thread"""
        self.last_data_update = time.time()
        timestamp = time.strftime("%H:%M:%S")
        self.data_status_label.setText(f"Updated: {timestamp}")

        # Create telemetry snapshot
        if hasattr(self, 'current_hostname'):
            snapshot = self._create_telemetry_snapshot()
            self.telemetry_data_updated.emit(self.current_hostname, snapshot)

    @pyqtSlot(object)
    def _on_log_output(self, raw_output):
        """Handle log output updates"""
        timestamp = time.strftime("%H:%M:%S")
        if hasattr(self.log_widget, 'append'):
            log_entry = f"[{timestamp}] {raw_output.platform}: {raw_output.output[:100]}..."
            self.log_widget.append(log_entry)

    # ===== PLATFORM MANAGEMENT =====

    def _open_platform_manager(self):
        """Open platform configuration manager"""
        if not PLATFORM_UI_AVAILABLE:
            QMessageBox.warning(self, "Feature Not Available",
                                "Platform Configuration UI is not available.")
            return
        # TODO: Implement platform manager integration

    def _reload_platform_configurations(self):
        """Reload platform configurations"""
        try:
            from platform_config_manager import PlatformConfigManager
            self.controller.platform_config = PlatformConfigManager('config/platforms')
            self._update_platform_info()
            self.widget_status_changed.emit("Platform configurations reloaded")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reload: {str(e)}")

    def _update_platform_info(self):
        """Update platform information display"""
        try:
            platforms = self.controller.platform_config.get_available_platforms()
            self.platform_info_label.setText(f"{len(platforms)} platforms")
        except:
            self.platform_info_label.setText("Error loading")

    # ===== THEME METHODS =====

    def _on_theme_changed(self, theme_name: str):
        """
        Handle theme selection change from internal combo box
        """
        # Prevent recursive changes
        if self.theme_change_in_progress:
            return

        print(f" Internal theme change requested: {theme_name}")

        # Apply theme to this widget
        self._apply_theme_safe(theme_name)

    def _apply_theme(self, theme_name: str):
        """
        Legacy theme application method - now redirects to safe version
        """
        self._apply_theme_safe(theme_name)

    # ===== UTILITY METHODS =====

    def _create_telemetry_snapshot(self):
        """Create current telemetry data snapshot"""
        snapshot = {
            'timestamp': time.time(),
            'connection_status': self.connection_status,
            'last_update': self.last_data_update,
            # TODO: Add actual telemetry data
        }
        return snapshot

    # ===== PUBLIC API METHODS FOR EMBEDDING =====

    def connect_to_device_programmatic(self, hostname, ip_address, platform, credentials):
        """
        Programmatic connection method for embedding
        Returns immediately, connection happens asynchronously
        """
        return self._handle_connection_request(hostname, ip_address, platform, credentials)

    def get_connection_status(self):
        """Get current connection status"""
        return self.connection_status

    def get_device_info(self):
        """Get current device information"""
        return getattr(self, 'device_info', None)

    def set_theme_programmatic(self, theme_name):
        """Set theme programmatically (for embedding)"""
        self._apply_theme_safe(theme_name)

    def get_telemetry_snapshot(self):
        """Get current telemetry data snapshot"""
        return self._create_telemetry_snapshot()