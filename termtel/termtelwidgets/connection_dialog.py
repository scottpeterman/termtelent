"""
Device Connection Dialog for Netmiko Connections
Provides UI for entering device credentials and connection parameters
WITH credential integration AND dynamic platform loading from platforms.json
FIXED: Removed problematic status box and improved layout
"""
import json
import os
import logging

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QSpinBox, QComboBox, QPushButton,
                             QLabel, QCheckBox, QGroupBox, QTabWidget, QWidget, QMessageBox, QFileDialog)
from PyQt6.QtCore import pyqtSignal, QThread, pyqtSlot
from termtel.termtelwidgets.session_picker import SessionPickerDialog

logger = logging.getLogger(__name__)


class ConnectionTestThread(QThread):
    """Thread for testing device connections without blocking UI"""

    connection_result = pyqtSignal(bool, str)  # success, message

    def __init__(self, controller, hostname, ip_address, platform, credentials):
        super().__init__()
        self.controller = controller
        self.hostname = hostname
        self.ip_address = ip_address
        self.platform = platform
        self.credentials = credentials

    def run(self):
        """Test connection in separate thread"""
        try:
            success = self.controller.connect_to_device(
                self.hostname,
                self.ip_address,
                self.platform,
                self.credentials
            )

            if success:
                self.connection_result.emit(True, f"Successfully connected to {self.hostname}")
            else:
                self.connection_result.emit(False, f"Failed to connect to {self.hostname}")

        except Exception as e:
            self.connection_result.emit(False, f"Connection error: {str(e)}")


class DeviceConnectionDialog(QDialog):
    """Dialog for entering device connection parameters with dynamic platform loading"""

    connection_requested = pyqtSignal(str, str, str, object)  # hostname, ip, platform, credentials

    def __init__(self, theme_library=None, credential_manager=None, controller=None, parent=None):
        super().__init__(parent)
        self.theme_library = theme_library
        self.controller = controller

        # Store parent reference for theme access (don't override the built-in parent)
        self.parent_widget = parent

        # adds search next
        self.session_file = str(self.parent_widget.session_file_with_path)

        # NEW: Get credential manager
        self.credential_manager = None
        if credential_manager and hasattr(credential_manager, 'parent_app'):
            try:
                self.credential_manager = credential_manager.parent_app.cred_manager
                print(f" Got credential manager: {type(self.credential_manager)}")
            except Exception as e:
                print(f" Error getting credential manager: {e}")
                self.credential_manager = None

        self.setWindowTitle("Connect to Network Device")
        self.setModal(True)
        # FIXED: Increased height to accommodate better spacing
        height = 650 if self.credential_manager else 600
        self.setFixedSize(520, height)

        # Store connection test thread
        self.test_thread = None

        # NEW: Store loaded credentials and platforms
        self.saved_credentials = []
        self.available_platforms = {}  # Will store platform_id -> platform_definition

        self._setup_ui()
        self._load_available_platforms()  # NEW: Load platforms dynamically
        self._populate_defaults()

        # Load saved credentials
        self.load_test_settings()

        # Apply theme if available
        if theme_library:
            # Get current theme from parent widget
            current_theme = "cyberpunk"  # fallback default

            if self.parent_widget and hasattr(self.parent_widget, 'theme'):
                current_theme = self.parent_widget.theme
                print(f" Found theme from parent.theme: {current_theme}")
            elif parent and hasattr(parent, 'current_theme'):
                current_theme = parent.current_theme
                print(f" Found theme from parent.current_theme: {current_theme}")
            elif parent and hasattr(parent, 'controller') and hasattr(parent.controller, 'current_theme'):
                current_theme = parent.controller.current_theme
                print(f" Found theme from parent.controller.current_theme: {current_theme}")
            else:
                print(f" No theme found, using default: {current_theme}")

            print(f"Applying theme '{current_theme}' to connection dialog")
            theme_library.apply_theme(self, current_theme)

            # Use the ORIGINAL working method for theme application
            self._apply_theme_to_children(current_theme)

    def _load_available_platforms(self):
        """NEW: Load available platforms from platform configuration manager"""
        self.available_platforms = {}

        try:
            # Method 1: Try to get platforms from controller
            if self.controller and hasattr(self.controller, 'platform_config'):
                platform_config = self.controller.platform_config
                platform_names = platform_config.get_available_platforms()

                print(f" Found {len(platform_names)} platforms from controller")

                for platform_name in platform_names:
                    platform_def = platform_config.get_platform(platform_name)
                    if platform_def:
                        self.available_platforms[platform_name] = platform_def

            # Method 2: Fallback - create our own platform config manager
            elif not self.available_platforms:
                print(" Creating fallback platform config manager...")

                try:
                    from termtel.termtelwidgets.platform_config_manager import PlatformConfigManager
                    platform_config = PlatformConfigManager()
                    platform_names = platform_config.get_available_platforms()

                    print(f" Fallback loaded {len(platform_names)} platforms")

                    for platform_name in platform_names:
                        platform_def = platform_config.get_platform(platform_name)
                        if platform_def:
                            self.available_platforms[platform_name] = platform_def

                except Exception as e:
                    print(f" Error creating fallback platform config: {e}")

            # Method 3: Last resort - hardcoded fallback
            if not self.available_platforms:
                print(" Using hardcoded platform fallback")
                self.available_platforms = {
                    'cisco_ios_xe': type('Platform', (), {'display_name': 'Cisco IOS XE', 'description': 'Cisco IOS XE devices'})(),
                    'cisco_ios': type('Platform', (), {'display_name': 'Cisco IOS', 'description': 'Cisco IOS devices'})(),
                    'cisco_nxos': type('Platform', (), {'display_name': 'Cisco NX-OS', 'description': 'Cisco Nexus switches'})(),
                    'arista_eos': type('Platform', (), {'display_name': 'Arista EOS', 'description': 'Arista switches'})(),
                    'hp_procurve': type('Platform', (), {'display_name': 'HP ProCurve', 'description': 'HP ProCurve switches'})(),
                    'juniper_junos': type('Platform', (), {'display_name': 'Juniper JunOS', 'description': 'Juniper devices'})(),
                    'linux': type('Platform', (), {'display_name': 'Linux', 'description': 'Linux servers'})(),
                    'aruba_aos_s': type('Platform', (), {'display_name': 'Aruba AOS-S', 'description': 'Aruba AOS-S switches'})(),
                    'aruba_aos_cx': type('Platform', (), {'display_name': 'Aruba AOS-CX', 'description': 'Aruba AOS-CX switches'})(),
                }

            print(f" Available platforms: {list(self.available_platforms.keys())}")

        except Exception as e:
            print(f" Error loading platforms: {e}")
            # Minimal fallback
            self.available_platforms = {
                'cisco_ios_xe': type('Platform', (), {'display_name': 'Cisco IOS XE', 'description': 'Cisco IOS XE devices'})()
            }

    def _populate_platform_combo(self):
        """NEW: Populate platform combo box with loaded platforms"""
        self.platform_combo.clear()

        # Sort platforms by display name for better UX
        sorted_platforms = sorted(
            self.available_platforms.items(),
            key=lambda x: getattr(x[1], 'display_name', x[0])
        )

        for platform_id, platform_def in sorted_platforms:
            display_name = getattr(platform_def, 'display_name', platform_id)
            description = getattr(platform_def, 'description', '')

            # Create rich display text
            if description:
                combo_text = f"{display_name} - {description}"
            else:
                combo_text = display_name

            # Add to combo with platform_id as data
            self.platform_combo.addItem(combo_text, platform_id)

        print(f" Populated platform combo with {self.platform_combo.count()} platforms")

    def _on_platform_changed(self, index):
        """NEW: Handle platform selection change to show platform info"""
        platform_id = self.platform_combo.itemData(index)
        if not platform_id or platform_id not in self.available_platforms:
            return

        platform_def = self.available_platforms[platform_id]

        # Update tooltip with platform information
        description = getattr(platform_def, 'description', 'No description available')
        self.platform_combo.setToolTip(f"{platform_def.display_name}: {description}")

        # Optionally update netmiko settings based on platform
        if hasattr(platform_def, 'netmiko'):
            netmiko_config = platform_def.netmiko

            # Update timeout values to match platform defaults
            if hasattr(netmiko_config, 'timeout'):
                self.timeout_spin.setValue(netmiko_config.timeout)
            if hasattr(netmiko_config, 'auth_timeout'):
                self.auth_timeout_spin.setValue(netmiko_config.auth_timeout)
            if hasattr(netmiko_config, 'fast_cli'):
                self.fast_cli_check.setChecked(netmiko_config.fast_cli)

    def _get_selected_platform_id(self) -> str:
        """NEW: Get the selected platform ID (not display name)"""
        current_index = self.platform_combo.currentIndex()
        if current_index >= 0:
            return self.platform_combo.itemData(current_index)
        return 'cisco_ios_xe'  # fallback

    def _load_saved_credentials(self):
        """Load saved credentials from credential manager"""
        if not self.parent_widget.cred_manager:
            logger.info("No credential manager available")
            if hasattr(self, 'credentials_combo'):
                self.credentials_combo.setEnabled(False)
                self.credentials_combo.clear()
                self.credentials_combo.addItem("-- No credential manager --", None)
            return

        try:
            if not self.parent_widget.cred_manager.is_initialized:
                print(" Credential manager not initialized")
                if hasattr(self, 'credentials_combo'):
                    self.credentials_combo.setEnabled(False)
                    self.credentials_combo.clear()
                    self.credentials_combo.addItem("-- Credentials not initialized --", None)
                return

            if not self.parent_widget.cred_manager.is_unlocked():
                print(" Credential manager not unlocked")
                if hasattr(self, 'credentials_combo'):
                    self.credentials_combo.setEnabled(True)
                    self.credentials_combo.clear()
                    self.credentials_combo.addItem("-- Credentials locked --", None)
                return

            # Load credentials from file
            creds_path = self.parent_widget.cred_manager.config_dir / "credentials.yaml"
            if not creds_path.exists():
                print(" No credentials file found")
                if hasattr(self, 'credentials_combo'):
                    self.credentials_combo.clear()
                    self.credentials_combo.addItem("-- No saved credentials --", None)
                return

            self.saved_credentials = self.parent_widget.cred_manager.load_credentials(creds_path)
            print(f" Loaded {len(self.saved_credentials)} credentials")

            # Populate the combo box
            if len(self.saved_credentials) > 0:
                self.credentials_combo.clear()
                self.credentials_combo.addItem("-- Manual Entry --", None)

                for cred in self.saved_credentials:
                    display_name = cred.get('display_name', cred.get('username', 'Unknown'))
                    self.credentials_combo.addItem(display_name, cred)

                self.credentials_combo.setEnabled(True)
                print(f" Combo box populated with {self.credentials_combo.count()} items")

        except Exception as e:
            logger.error(f"Failed to load saved credentials: {e}")
            if hasattr(self, 'credentials_combo'):
                self.credentials_combo.setEnabled(False)
                self.credentials_combo.clear()
                self.credentials_combo.addItem(f"-- Error: {str(e)[:30]}... --", None)

    def _on_credential_selected(self, index):
        """Handle credential selection from dropdown"""
        if not hasattr(self, 'credentials_combo'):
            return

        cred_data = self.credentials_combo.itemData(index)

        if cred_data is None:
            # Manual entry selected - clear fields and enable editing
            self.username_edit.clear()
            self.password_edit.clear()
            self.username_edit.setEnabled(True)
            self.password_edit.setEnabled(True)
            self.show_passwords.setEnabled(True)
        else:
            # Saved credential selected - populate fields
            self.username_edit.setText(cred_data.get('username', ''))
            self.password_edit.setText(cred_data.get('password', ''))

            # Disable editing when using saved credentials
            self.username_edit.setEnabled(False)
            self.password_edit.setEnabled(False)
            self.show_passwords.setEnabled(False)

    def _open_credential_manager(self):
        """Open the credential manager dialog"""
        if not self.credential_manager:
            QMessageBox.information(
                self,
                "Credential Manager",
                "No credential manager available. Please configure credentials manually."
            )
            return

        try:
            from termtel.credential_manager import CredentialManagerDialog

            cred_dialog = CredentialManagerDialog(self)
            if hasattr(cred_dialog, 'credentials_updated'):
                cred_dialog.credentials_updated.connect(self._load_saved_credentials)
            cred_dialog.exec()

        except ImportError as e:
            logger.error(f"Could not import credential manager: {e}")
            QMessageBox.warning(
                self,
                "Import Error",
                "Could not open credential manager. Please check your installation."
            )

    def load_test_settings(self):
        """Load test settings from testui_ui file if it exists"""
        try:
            if os.path.exists('testui_ui.json'):
                with open('testui_ui.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    defaults = data.get('default', {})

                    self.hostname_edit.setText(defaults.get('hostname', '').strip())
                    self.ip_edit.setText(defaults.get('ip_address', '').strip())

                    # NEW: Set platform by ID, not display name
                    platform_id = defaults.get('platform', 'cisco_ios_xe').strip()
                    platform_index = self.platform_combo.findData(platform_id)
                    if platform_index >= 0:
                        self.platform_combo.setCurrentIndex(platform_index)
                    else:
                        # Fallback to text search if data search fails
                        text_index = self.platform_combo.findText(platform_id, match_flags=2)  # MatchContains
                        if text_index >= 0:
                            self.platform_combo.setCurrentIndex(text_index)

                    # Only populate username/password if no saved credentials
                    if not self.saved_credentials:
                        self.username_edit.setText(defaults.get('username', '').strip())
                        self.password_edit.setText(defaults.get('password', '').strip())

                    self.secret_edit.setText(defaults.get('secret', '').strip())
                    self.port_spin.setValue(defaults.get('port', 22))
                    self.timeout_spin.setValue(defaults.get('timeout', 10))
                    self.auth_timeout_spin.setValue(defaults.get('auth_timeout', 10))
                    self.fast_cli_check.setChecked(defaults.get('fast_cli', False))
                    self.verbose_check.setChecked(defaults.get('verbose', False))
        except:
            pass  # Silently fail if file doesn't exist or can't be read

    def _setup_ui(self):
        """Setup the dialog UI - FIXED: Removed problematic status box"""
        layout = QVBoxLayout(self)
        # FIXED: Remove any status display that was causing the crowded box at top

        # Tab widget for different connection types
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Basic connection tab
        basic_tab = QWidget()
        self.tab_widget.addTab(basic_tab, "Basic Connection")
        self._setup_basic_tab(basic_tab)
        self._load_saved_credentials()

        # Advanced settings tab
        advanced_tab = QWidget()
        self.tab_widget.addTab(advanced_tab, "Advanced Settings")
        self._setup_advanced_tab(advanced_tab)

        # Button layout
        button_layout = QHBoxLayout()

        # Credential management button (only if credential manager available)
        if self.credential_manager:
            self.manage_creds_button = QPushButton("Manage Credentials...")
            self.manage_creds_button.clicked.connect(self._open_credential_manager)
            button_layout.addWidget(self.manage_creds_button)

        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._test_connection)
        button_layout.addWidget(self.test_button)
        self.test_button.setVisible(False)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._connect_device)
        self.connect_button.setDefault(True)
        button_layout.addWidget(self.connect_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def _setup_basic_tab(self, tab_widget):
        """Setup basic connection parameters tab"""
        layout = QVBoxLayout(tab_widget)

        if self.credential_manager or hasattr(self, 'parent_widget') and hasattr(self.parent_widget, 'cred_manager'):
            creds_group = QGroupBox("Saved Credentials")
            creds_layout = QFormLayout(creds_group)

            self.credentials_combo = QComboBox()
            self.credentials_combo.currentIndexChanged.connect(self._on_credential_selected)
            creds_layout.addRow("Saved Credentials:", self.credentials_combo)

            layout.addWidget(creds_group)

        # Device information group
        device_group = QGroupBox("Device Information")
        device_layout = QFormLayout(device_group)

        self.hostname_edit = QLineEdit()
        self.hostname_edit.setPlaceholderText("Device hostname")
        device_layout.addRow("Hostname:", self.hostname_edit)

        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("192.168.1.1")
        device_layout.addRow("IP Address:", self.ip_edit)

        # NEW: Dynamic platform combo (will be populated by _populate_platform_combo)
        self.platform_combo = QComboBox()
        self.platform_combo.currentIndexChanged.connect(self._on_platform_changed)
        device_layout.addRow("Platform:", self.platform_combo)

        # ADD SESSION LINK HERE - Create session selection row
        if hasattr(self, 'session_file') and self.session_file:
            session_widget = QWidget()
            session_layout = QHBoxLayout(session_widget)
            session_layout.setContentsMargins(0, 0, 0, 0)

            # EXISTING: Current session file button
            self.session_link = QPushButton("Select from Current Sessions...")
            self.session_link.setFlat(True)
            self.session_link.setStyleSheet("""
                QPushButton {
                    border: none;
                    color: #00ffff;
                    text-decoration: underline;
                    text-align: left;
                    padding: 2px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    color: #00ff88;
                }
                QPushButton:pressed {
                    color: #ffffff;
                }
            """)
            self.session_link.clicked.connect(self._open_session_picker)
            session_layout.addWidget(self.session_link)

            # NEW: Add separator
            separator = QLabel(" | ")
            separator.setStyleSheet("color: #666666; font-size: 11px;")
            session_layout.addWidget(separator)

            # NEW: Browse button for different session file
            self.browse_sessions_button = QPushButton("Browse File...")
            self.browse_sessions_button.setFlat(True)
            self.browse_sessions_button.setStyleSheet("""
                QPushButton {
                    border: none;
                    color: #00ffff;
                    text-decoration: underline;
                    text-align: left;
                    padding: 2px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    color: #00ff88;
                }
                QPushButton:pressed {
                    color: #ffffff;
                }
            """)
            self.browse_sessions_button.clicked.connect(self._browse_session_file)
            session_layout.addWidget(self.browse_sessions_button)

            session_layout.addStretch()
            device_layout.addRow("Quick Fill:", session_widget)

        layout.addWidget(device_group)

        # Credentials group
        creds_group = QGroupBox("Credentials")
        creds_layout = QFormLayout(creds_group)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("admin")
        creds_layout.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("password")
        creds_layout.addRow("Password:", self.password_edit)

        self.secret_edit = QLineEdit()
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_edit.setPlaceholderText("enable password (optional)")
        creds_layout.addRow("Enable Secret:", self.secret_edit)

        self.show_passwords = QCheckBox("Show passwords")
        self.show_passwords.toggled.connect(self._toggle_password_visibility)
        creds_layout.addRow("", self.show_passwords)

        layout.addWidget(creds_group)

        layout.addStretch()

    def _browse_session_file(self):
        """Browse for a different session file"""
        try:
            # Get the directory of the current session file as starting point
            current_dir = os.path.dirname(self.session_file) if self.session_file else os.getcwd()

            # Open file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Session File",
                current_dir,
                "Session Files (*.json *.yaml *.yml);;All Files (*.*)"
            )

            if file_path:
                # Temporarily store the new session file path
                self._browse_session_file_path = file_path
                self._open_session_picker_from_file(file_path)

        except Exception as e:
            QMessageBox.warning(self, "File Browser Error",
                                f"Could not browse for session file: {str(e)}")

    def _open_session_picker_from_file(self, session_file_path):
        """Open session picker with a specific file"""
        try:
            session_dialog = SessionPickerDialog(
                session_file_path,  # Use the browsed file instead
                self.theme_library,
                self.parent_widget
            )
            session_dialog.session_selected.connect(self._populate_from_session)
            session_dialog.exec()

        except Exception as e:
            QMessageBox.warning(self, "Session Picker Error",
                                f"Could not open session picker with file '{session_file_path}': {str(e)}")
    def _setup_advanced_tab(self, tab_widget):
        """Setup advanced connection parameters tab"""
        layout = QVBoxLayout(tab_widget)

        # Connection parameters group
        conn_group = QGroupBox("Connection Parameters")
        conn_layout = QFormLayout(conn_group)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        conn_layout.addRow("Port:", self.port_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(10)
        self.timeout_spin.setSuffix(" seconds")
        conn_layout.addRow("Timeout:", self.timeout_spin)

        self.auth_timeout_spin = QSpinBox()
        self.auth_timeout_spin.setRange(5, 60)
        self.auth_timeout_spin.setValue(10)
        self.auth_timeout_spin.setSuffix(" seconds")
        conn_layout.addRow("Auth Timeout:", self.auth_timeout_spin)

        layout.addWidget(conn_group)

        # Netmiko options group
        netmiko_group = QGroupBox("Netmiko Options")
        netmiko_layout = QFormLayout(netmiko_group)

        self.fast_cli_check = QCheckBox()
        self.fast_cli_check.setChecked(False)
        self.fast_cli_check.setToolTip("Enable fast CLI mode (not supported by all devices)")
        netmiko_layout.addRow("Fast CLI:", self.fast_cli_check)

        self.verbose_check = QCheckBox()
        self.verbose_check.setChecked(False)
        self.verbose_check.setToolTip("Enable verbose logging")
        netmiko_layout.addRow("Verbose:", self.verbose_check)

        layout.addWidget(netmiko_group)

        layout.addStretch()

    def _populate_defaults(self):
        """Populate default values"""
        self.hostname_edit.setText("")
        self.ip_edit.setText("")

        # NEW: Populate platform combo dynamically
        self._populate_platform_combo()

        # Set default platform to cisco_ios_xe if available
        default_platform_index = self.platform_combo.findData('cisco_ios_xe')
        if default_platform_index >= 0:
            self.platform_combo.setCurrentIndex(default_platform_index)

        self.username_edit.setText("")
        self.password_edit.setText("")

    def _toggle_password_visibility(self, checked):
        """Toggle password field visibility"""
        echo_mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.password_edit.setEchoMode(echo_mode)
        self.secret_edit.setEchoMode(echo_mode)

    def _validate_inputs(self) -> tuple[bool, str]:
        """Validate user inputs"""
        if not self.hostname_edit.text().strip():
            return False, "Hostname is required"

        if not self.ip_edit.text().strip():
            return False, "IP address is required"

        # Basic IP validation
        ip_parts = self.ip_edit.text().strip().split('.')
        if len(ip_parts) != 4:
            return False, "Invalid IP address format"

        try:
            for part in ip_parts:
                num = int(part)
                if not 0 <= num <= 255:
                    return False, "Invalid IP address range"
        except ValueError:
            return False, "Invalid IP address format"

        if not self.username_edit.text().strip():
            return False, "Username is required"

        if not self.password_edit.text():
            return False, "Password is required"

        return True, "Valid"

    def _get_credentials(self):
        """Get credentials object from form inputs"""
        try:
            from termtel.termtelwidgets.netmiko_controller import ConnectionCredentials
        except ImportError:
            # Fallback: create a simple credentials object
            class ConnectionCredentials:
                def __init__(self, username, password, secret="", port=22, timeout=10, auth_timeout=10):
                    self.username = username
                    self.password = password
                    self.secret = secret
                    self.port = port
                    self.timeout = timeout
                    self.auth_timeout = auth_timeout

        return ConnectionCredentials(
            username=self.username_edit.text().strip(),
            password=self.password_edit.text(),
            secret=self.secret_edit.text(),
            port=self.port_spin.value(),
            timeout=self.timeout_spin.value(),
            auth_timeout=self.auth_timeout_spin.value()
        )

    def _test_connection(self):
        """Test connection without connecting"""
        valid, message = self._validate_inputs()
        if not valid:
            QMessageBox.warning(self, "Validation Error", message)
            return

        # Disable buttons during test
        self.test_button.setEnabled(False)
        self.connect_button.setEnabled(False)

        # Create a temporary controller for testing
        from termtel.termtelwidgets.netmiko_controller import EnhancedPlatformAwareTelemetryController
        temp_controller = EnhancedPlatformAwareTelemetryController()

        # Start connection test in thread
        self.test_thread = ConnectionTestThread(
            temp_controller,
            self.hostname_edit.text().strip(),
            self.ip_edit.text().strip(),
            self._get_selected_platform_id(),  # NEW: Use platform ID instead of display name
            self._get_credentials()
        )

        self.test_thread.connection_result.connect(self._handle_test_result)
        self.test_thread.start()

    @pyqtSlot(bool, str)
    def _handle_test_result(self, success, message):
        """Handle connection test result"""
        self.test_button.setEnabled(True)
        self.connect_button.setEnabled(True)

        if success:
            QMessageBox.information(self, "Connection Test", "Connection test successful!")
        else:
            QMessageBox.warning(self, "Connection Test", f"Connection test failed: {message}")

        self.test_thread = None

    def _connect_device(self):
        """Connect to device and close dialog"""
        # Validate inputs first
        valid, message = self._validate_inputs()
        if not valid:
            QMessageBox.warning(self, "Validation Error", message)
            return

        # NEW: Emit connection request signal with platform ID
        self.connection_requested.emit(
            self.hostname_edit.text().strip(),
            self.ip_edit.text().strip(),
            self._get_selected_platform_id(),  # NEW: Use platform ID
            self._get_credentials()
        )

        self.accept()

    def _apply_theme_to_children(self, theme_name):
        """Apply theme to all child widgets - RESTORED ORIGINAL WORKING VERSION"""
        if not self.theme_library:
            return

        try:
            # Apply theme to all child widgets
            for child in self.findChildren(QWidget):
                if child != self:  # Don't reapply to self
                    self.theme_library.apply_theme(child, theme_name)

            # Special styling for form elements to match cyberpunk theme
            # ONLY apply custom styling if theme is actually cyberpunk
            if theme_name == "cyberpunk":
                self._apply_cyberpunk_styling()

        except Exception as e:
            print(f"Error applying theme to dialog children: {e}")

    def _apply_cyberpunk_styling(self):
        """Apply specific cyberpunk styling to form elements with proper spacing"""
        # Enhanced styling for input fields with better spacing
        input_style = """
            QLineEdit {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 6px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 20px;
                margin: 2px;
            }
            QLineEdit:focus {
                border-color: #00ff88;
                background-color: #222222;
            }
            QLineEdit:disabled {
                background-color: #0a0a0a;
                border-color: #004444;
                color: #888888;
            }
            QLineEdit::placeholder {
                color: #666666;
            }
        """

        # Enhanced styling for combo boxes with better spacing
        combo_style = """
            QComboBox {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 6px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 13px;
                min-width: 120px;
                min-height: 20px;
                margin: 2px;
            }
            QComboBox:hover {
                border-color: #00ff88;
            }
            QComboBox::drop-down {
                border: none;
                background: #00ffff;
                width: 24px;
                border-radius: 4px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 6px solid #000000;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                selection-background-color: #00ffff;
                selection-color: #000000;
                color: #ffffff;
                padding: 4px;
            }
        """

        # Enhanced styling for buttons with better spacing
        button_style = """
            QPushButton {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 6px;
                padding: 10px 20px;
                color: #00ffff;
                font-weight: bold;
                font-size: 13px;
                min-height: 16px;
                margin: 4px;
            }
            QPushButton:hover {
                background-color: #00ffff;
                color: #000000;
            }
            QPushButton:pressed {
                background-color: #00ff88;
                border-color: #00ff88;
            }
            QPushButton:default {
                border-color: #00ff88;
                color: #00ff88;
            }
            QPushButton:flat {
                border: none;
                padding: 4px 8px;
                margin: 2px;
            }
        """

        # Enhanced styling for spinboxes with better spacing
        spinbox_style = """
            QSpinBox {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 6px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 20px;
                margin: 2px;
            }
            QSpinBox:focus {
                border-color: #00ff88;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #00ffff;
                border: none;
                width: 20px;
                border-radius: 3px;
            }
            QSpinBox::up-arrow, QSpinBox::down-arrow {
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
            }
            QSpinBox::up-arrow {
                border-bottom: 4px solid #000000;
            }
            QSpinBox::down-arrow {
                border-top: 4px solid #000000;
            }
        """

        # Enhanced styling for checkboxes with better spacing
        checkbox_style = """
            QCheckBox {
                color: #ffffff;
                font-size: 13px;
                padding: 4px;
                margin: 2px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #00ffff;
                border-radius: 4px;
                background-color: #1a1a1a;
                margin: 2px;
            }
            QCheckBox::indicator:checked {
                background-color: #00ffff;
                image: none;
            }
            QCheckBox:disabled {
                color: #666666;
            }
            QCheckBox::indicator:disabled {
                border-color: #444444;
                background-color: #0a0a0a;
            }
        """

        # Add better spacing for group boxes and form layouts
        groupbox_style = """
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #00ffff;
                border: 2px solid #00ffff;
                border-radius: 8px;
                margin: 8px 4px;
                padding: 16px 8px 8px 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px 0 8px;
                background-color: #0a0a0a;
            }
        """

        # Apply all styles
        for line_edit in self.findChildren(QLineEdit):
            line_edit.setStyleSheet(input_style)

        for combo_box in self.findChildren(QComboBox):
            combo_box.setStyleSheet(combo_style)

        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)

        for spinbox in self.findChildren(QSpinBox):
            spinbox.setStyleSheet(spinbox_style)

        for checkbox in self.findChildren(QCheckBox):
            checkbox.setStyleSheet(checkbox_style)

        for groupbox in self.findChildren(QGroupBox):
            groupbox.setStyleSheet(groupbox_style)

        # Add spacing to form layouts
        for form_layout in self.findChildren(QFormLayout):
            form_layout.setVerticalSpacing(12)
            form_layout.setHorizontalSpacing(8)
            form_layout.setContentsMargins(12, 12, 12, 12)

        # Add spacing to main layouts
        for layout in self.findChildren(QVBoxLayout):
            layout.setSpacing(8)
            layout.setContentsMargins(8, 8, 8, 8)

    def _open_session_picker(self):
        """Open the session picker dialog"""
        try:
            session_dialog = SessionPickerDialog(
                self.session_file,
                self.theme_library,
                self.parent_widget
            )
            session_dialog.session_selected.connect(self._populate_from_session)
            session_dialog.exec()

        except Exception as e:
            QMessageBox.warning(self, "Session Picker Error",
                                f"Could not open session picker: {str(e)}")

    def _populate_from_session(self, session_data):
        """Populate connection form from selected session"""
        try:
            # Populate basic fields
            self.hostname_edit.setText(session_data['display_name'])
            self.ip_edit.setText(session_data['host'])

            # Map device type to platform
            device_type = session_data['device_type'].lower()
            platform_mapping = {
                'cisco_ios': 'cisco_ios',
                'cisco_ios_xe': 'cisco_ios_xe',
                'cisco_nxos': 'cisco_nxos',
                'linux': 'linux',
                'arista_eos': 'arista_eos',
                'aruba_aos_s': 'aruba_aos_s',
                'aruba_aos_cx': 'aruba_aos_cx',
                'hp_procurve': 'hp_procurve',
                'juniper_junos': 'juniper_junos',
            }

            platform_id = platform_mapping.get(device_type, 'cisco_ios_xe')

            # NEW: Set platform by data (platform ID) instead of text
            platform_index = self.platform_combo.findData(platform_id)
            if platform_index >= 0:
                self.platform_combo.setCurrentIndex(platform_index)

            # Set port if different from default
            try:
                port_value = int(session_data['port'])
                if port_value != 22:
                    self.port_spin.setValue(port_value)
            except (ValueError, KeyError):
                pass  # Keep default port

        except Exception as e:
            QMessageBox.warning(self, "Population Error",
                                f"Could not populate all fields: {str(e)}")


# Updated ConnectionManager class
class ConnectionManager:
    """Helper class for managing device connections in main window"""

    def __init__(self, parent_window, controller, theme_library=None):
        self.parent_window = parent_window
        self.controller = controller
        self.theme_library = theme_library
        self.connection_dialog = None

    def show_connection_dialog(self):
        """Show connection dialog"""
        self.connection_dialog = DeviceConnectionDialog(
            theme_library=self.theme_library,
            controller=self.controller,  # NEW: Pass controller for platform loading
            parent=self.parent_window
        )

        # Connect signals
        self.connection_dialog.connection_requested.connect(self._handle_connection_request)

        # Show dialog
        result = self.connection_dialog.exec()
        return result

    @pyqtSlot(str, str, str, object)
    def _handle_connection_request(self, hostname, ip_address, platform, credentials):
        """Handle connection request from dialog"""
        print(f"Connection requested: {hostname} ({ip_address}) - {platform}")
        print(f"Credentials: username={credentials.username}, port={credentials.port}")

        try:
            # Connect using the controller
            success = self.controller.connect_to_device(hostname, ip_address, platform, credentials)

            if success:
                print("Connection successful!")
            else:
                print("Connection failed!")

            return success

        except Exception as e:
            print(f"Error in connection request: {e}")
            return False