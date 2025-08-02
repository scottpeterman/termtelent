"""
Enhanced NAPALM Connection Dialog with Session Picker Integration
Combines credential management with session selection for seamless workflow
"""
import json
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
import yaml

import napalm
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTextEdit, QMessageBox, QTabWidget,
    QScrollArea, QGroupBox, QCheckBox, QSpinBox, QProgressBar,
    QSplitter, QFrame, QTreeWidget, QTreeWidgetItem, QDialog, QFormLayout,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QPalette, QColor, QTextCharFormat, QSyntaxHighlighter, QIcon

logger = logging.getLogger('termtel.napalm_widget')


class SessionPickerWidget(QWidget):
    """Embedded session picker widget for connection dialog"""

    session_selected = pyqtSignal(dict)  # Emits selected session data

    def __init__(self, session_file_path=None, parent=None):
        super().__init__(parent)
        self.session_file_path = session_file_path
        self.sessions_data = []
        self.parent_dialog = parent

        self._setup_ui()
        if session_file_path:
            self._load_sessions()

    def _setup_ui(self):
        """Setup the session picker UI"""
        layout = QVBoxLayout(self)

        # Header with session file info
        header_layout = QHBoxLayout()

        self.session_file_label = QLabel("No session file loaded")
        self.session_file_label.setStyleSheet("font-size: 10px; color: #888888;")
        header_layout.addWidget(self.session_file_label)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse_session_file)
        self.browse_button.setMaximumWidth(80)
        header_layout.addWidget(self.browse_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._load_sessions)
        self.refresh_button.setMaximumWidth(80)
        header_layout.addWidget(self.refresh_button)

        layout.addLayout(header_layout)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search sessions by name or host...")
        self.search_box.textChanged.connect(self._filter_sessions)
        layout.addWidget(self.search_box)

        # Session list
        self.session_list = QListWidget()
        self.session_list.itemSelectionChanged.connect(self._on_session_selected)
        self.session_list.itemDoubleClicked.connect(self._select_session)
        layout.addWidget(self.session_list)

        # Quick info area
        self.info_label = QLabel("Select a session to see details...")
        self.info_label.setStyleSheet("font-size: 10px; padding: 5px; background-color: #2a2a2a; border-radius: 3px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

    def set_session_file(self, file_path):
        """Set the session file path and load sessions"""
        self.session_file_path = file_path
        self._load_sessions()

    def _browse_session_file(self):
        """Browse for session file"""
        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Session File", "",
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )

        if file_path:
            self.set_session_file(file_path)

    def _load_sessions(self):
        """Load sessions from the YAML file"""
        if not self.session_file_path:
            self.session_file_label.setText("No session file selected")
            return

        try:
            session_path = Path(self.session_file_path)
            if not session_path.exists():
                self.session_file_label.setText(f"File not found: {session_path.name}")
                return

            with open(session_path, 'r', encoding='utf-8') as f:
                self.sessions_data = yaml.safe_load(f) or []

            self.session_file_label.setText(f"Loaded: {session_path.name}")
            self._populate_session_list()

        except Exception as e:
            self.session_file_label.setText(f"Error loading: {str(e)}")
            logger.error(f"Failed to load sessions: {e}")

    def _populate_session_list(self, filter_text=""):
        """Populate the session list widget"""
        self.session_list.clear()

        for folder in self.sessions_data:
            folder_name = folder.get('folder_name', 'Unknown')
            sessions = folder.get('sessions', [])

            for session in sessions:
                display_name = session.get('display_name', 'Unknown')
                host = session.get('host', 'Unknown')
                device_type = session.get('DeviceType', 'Unknown')
                vendor = session.get('Vendor', '')

                # Apply filter
                if filter_text and filter_text.lower() not in display_name.lower() and \
                        filter_text.lower() not in host.lower() and \
                        filter_text.lower() not in vendor.lower():
                    continue

                # Create list item
                item_text = f"{display_name} ({host})"
                if vendor:
                    item_text += f" - {vendor}"

                item = QListWidgetItem(item_text)

                # Store session data with the item
                session_data = {
                    'folder': folder_name,
                    'display_name': display_name,
                    'host': host,
                    'port': session.get('port', '22'),
                    'device_type': device_type,
                    'vendor': vendor,
                    'model': session.get('Model', ''),
                    'credsid': session.get('credsid', ''),
                    'full_session': session
                }
                item.setData(Qt.ItemDataRole.UserRole, session_data)

                # Add tooltip
                tooltip = f"Host: {host}\nType: {device_type}\nVendor: {vendor}\nFolder: {folder_name}"
                item.setToolTip(tooltip)

                self.session_list.addItem(item)

    def _filter_sessions(self, text):
        """Filter sessions based on search text"""
        self._populate_session_list(text)

    def _on_session_selected(self):
        """Handle session selection"""
        current_item = self.session_list.currentItem()
        if not current_item:
            self.info_label.setText("Select a session to see details...")
            return

        # Get session data
        session_data = current_item.data(Qt.ItemDataRole.UserRole)

        # Update info display with driver mapping preview
        info_text = f"""📁 {session_data['folder']} | 🌐 {session_data['host']}:{session_data['port']}
🔧 {session_data['device_type']} | 🏢 {session_data['vendor']} {session_data['model']}
🔑 Creds ID: {session_data['credsid'] or 'None'}

🔀 Will map to NAPALM driver: {self._preview_driver_mapping(session_data)}"""

        self.info_label.setText(info_text)

    def _preview_driver_mapping(self, session_data):
        """Preview what NAPALM driver this session will map to"""
        device_type = session_data.get('device_type', '').lower()
        vendor = session_data.get('vendor', '').lower()

        # Same mapping logic as _populate_from_session
        driver_mapping = {
            'cisco_ios': 'ios', 'cisco_xe': 'ios', 'cisco_xr': 'iosxr', 'cisco_nxos': 'nxos',
            'cisco_asa': 'ios', 'ios': 'ios', 'iosxr': 'iosxr', 'nxos': 'nxos', 'nexus': 'nxos',
            'arista_eos': 'eos', 'arista': 'eos', 'eos': 'eos',
            'juniper': 'junos', 'juniper_junos': 'junos', 'junos': 'junos', 'srx': 'junos', 'mx': 'junos', 'ex': 'junos',
            'hp_procurve': 'procurve', 'hp_comware': 'procurve', 'hpe_procurve': 'procurve', 'procurve': 'procurve',
            'huawei': 'huawei', 'huawei_vrp': 'huawei', 'vrp': 'huawei',
            'fortinet': 'fortios', 'fortios': 'fortios', 'fortigate': 'fortios',
            'paloalto_panos': 'panos', 'palo_alto': 'panos', 'panos': 'panos', 'pa': 'panos',
            'aruba_cx': 'aruba_cx', 'aruba': 'aruba_cx'
        }

        napalm_driver = driver_mapping.get(device_type)

        if not napalm_driver and vendor:
            vendor_mapping = {
                'cisco': 'ios', 'arista': 'eos', 'juniper': 'junos', 'hp': 'procurve', 'hpe': 'procurve',
                'huawei': 'huawei', 'fortinet': 'fortios', 'palo alto': 'panos', 'paloalto': 'panos', 'aruba': 'aruba_cx'
            }
            napalm_driver = vendor_mapping.get(vendor, 'ios')

        return napalm_driver or 'ios'

    def _select_session(self):
        """Select the current session and emit signal"""
        current_item = self.session_list.currentItem()
        if not current_item:
            return

        session_data = current_item.data(Qt.ItemDataRole.UserRole)
        self.session_selected.emit(session_data)

    def get_selected_session(self):
        """Get currently selected session data"""
        current_item = self.session_list.currentItem()
        if current_item:
            return current_item.data(Qt.ItemDataRole.UserRole)
        return None


class NapalmConnectionDialog(QDialog):
    """Enhanced NAPALM connection dialog with session picker and credential management"""

    connection_configured = pyqtSignal(dict)  # connection_params

    def __init__(self, parent=None, theme_library=None, current_params=None):
        super().__init__(parent)
        self.theme_library = theme_library
        self.parent_widget = parent
        self.current_params = current_params or {}

        # Get session file path from parent hierarchy
        self.session_file_path = None
        if parent and hasattr(parent, 'parent_window'):
            if hasattr(parent.parent_window, 'session_file_with_path'):
                self.session_file_path = str(parent.parent_window.session_file_with_path)
        elif parent and hasattr(parent, 'session_file_with_path'):
            self.session_file_path = str(parent.session_file_with_path)

        # Get credential manager from parent
        self.credential_manager = None
        if parent and hasattr(parent, 'parent_window'):
            parent_window = parent.parent_window
            if hasattr(parent_window, 'cred_manager'):
                self.credential_manager = parent_window.cred_manager
        elif parent and hasattr(parent, 'cred_manager'):
            self.credential_manager = parent.cred_manager

        self.setWindowTitle("Configure NAPALM Connection")
        self.setModal(True)
        self.setFixedSize(800, 700)  # Wider to accommodate session picker

        # Store connection test thread
        self.test_thread = None
        self.saved_credentials = []

        self._setup_ui()
        self._load_saved_credentials()
        self._populate_defaults()

        # Apply theme if available
        if theme_library and parent:
            current_theme = getattr(parent, 'current_theme', 'cyberpunk')
            if hasattr(parent, 'parent_window'):
                current_theme = getattr(parent.parent_window, 'theme', current_theme)

            theme_library.apply_theme(self, current_theme)
            self._apply_theme_to_children(current_theme)

    def _setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout(self)

        # Tab widget for different sections
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Session Picker tab (new)
        session_tab = QWidget()
        self.tab_widget.addTab(session_tab, "📂 Sessions")
        self._setup_session_tab(session_tab)

        # Connection tab
        conn_tab = QWidget()
        self.tab_widget.addTab(conn_tab, "🔗 Connection")
        self._setup_connection_tab(conn_tab)

        # Advanced tab
        advanced_tab = QWidget()
        self.tab_widget.addTab(advanced_tab, "⚙️ Advanced")
        self._setup_advanced_tab(advanced_tab)

        # Test results tab
        results_tab = QWidget()
        self.tab_widget.addTab(results_tab, "🧪 Test Results")
        self._setup_results_tab(results_tab)

        # Button layout
        button_layout = QHBoxLayout()

        self.use_session_button = QPushButton("Use Selected Session")
        self.use_session_button.clicked.connect(self._use_selected_session)
        self.use_session_button.setEnabled(False)
        button_layout.addWidget(self.use_session_button)

        button_layout.addStretch()

        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._test_connection)
        button_layout.addWidget(self.test_button)

        self.apply_button = QPushButton("Apply & Close")
        self.apply_button.clicked.connect(self._apply_configuration)
        self.apply_button.setDefault(True)
        button_layout.addWidget(self.apply_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def _setup_session_tab(self, tab_widget):
        """Setup session picker tab"""
        layout = QVBoxLayout(tab_widget)

        # Description
        desc = QLabel("Select an existing session to automatically populate connection details:")
        desc.setStyleSheet("font-size: 12px; padding: 5px; color: #00ff88;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Session picker widget
        self.session_picker = SessionPickerWidget(self.session_file_path, self)
        self.session_picker.session_selected.connect(self._on_session_picker_selection)
        layout.addWidget(self.session_picker)

        # Auto-detect session file if not provided
        if not self.session_file_path:
            self._auto_detect_session_file()

    def _auto_detect_session_file(self):
        """Try to auto-detect session file from parent app"""
        # Common session file locations for TerminalTelemetry
        possible_paths = [
            Path.home() / "Documents" / "TerminalTelemetry" / "sessions.yaml",
            Path.home() / "TerminalTelemetry" / "sessions.yaml",
            Path.cwd() / "sessions.yaml",
            Path.cwd() / "data" / "sessions.yaml"
        ]

        for path in possible_paths:
            if path.exists():
                self.session_picker.set_session_file(str(path))
                break

    def _on_session_picker_selection(self, session_data):
        """Handle session selection from picker"""
        self.use_session_button.setEnabled(True)

        # Optionally auto-populate fields immediately
        auto_populate = QMessageBox.question(
            self, "Auto-populate Fields",
            f"Automatically populate connection fields with data from '{session_data['display_name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if auto_populate == QMessageBox.StandardButton.Yes:
            self._populate_from_session(session_data)

    def _use_selected_session(self):
        """Use the selected session to populate connection fields"""
        session_data = self.session_picker.get_selected_session()
        if session_data:
            self._populate_from_session(session_data)
        else:
            QMessageBox.warning(self, "No Selection", "Please select a session first.")

    def _populate_from_session(self, session_data):
        """Populate connection fields from session data"""
        # Map session data to NAPALM connection fields
        self.hostname_edit.setText(session_data.get('host', ''))

        # Enhanced device type to NAPALM driver mapping
        device_type = session_data.get('device_type', '').lower()
        vendor = session_data.get('vendor', '').lower()

        # More comprehensive mapping including vendor info
        driver_mapping = {
            # Cisco devices
            'cisco_ios': 'ios',
            'cisco_xe': 'ios',
            'cisco_xr': 'iosxr',
            'cisco_nxos': 'nxos',
            'cisco_asa': 'ios',  # ASA uses IOS driver
            'ios': 'ios',
            'iosxr': 'iosxr',
            'nxos': 'nxos',
            'nexus': 'nxos',

            # Arista devices
            'arista_eos': 'eos',
            'arista': 'eos',
            'eos': 'eos',

            # Juniper devices
            'juniper': 'junos',
            'juniper_junos': 'junos',
            'junos': 'junos',
            'srx': 'junos',
            'mx': 'junos',
            'ex': 'junos',

            # HP/HPE devices
            'hp_procurve': 'procurve',
            'hp_comware': 'procurve',
            'hpe_procurve': 'procurve',
            'procurve': 'procurve',

            # Huawei devices
            'huawei': 'huawei',
            'huawei_vrp': 'huawei',
            'vrp': 'huawei',

            # Fortinet devices
            'fortinet': 'fortios',
            'fortios': 'fortios',
            'fortigate': 'fortios',

            # Palo Alto devices
            'paloalto_panos': 'panos',
            'palo_alto': 'panos',
            'panos': 'panos',
            'pa': 'panos',

            # Aruba devices
            'aruba_cx': 'aruba_cx',
            'aruba': 'aruba_cx'
        }

        # Try device_type first, then fallback to vendor-based mapping
        napalm_driver = driver_mapping.get(device_type)

        if not napalm_driver and vendor:
            # Vendor-based fallback mapping
            vendor_mapping = {
                'cisco': 'ios',
                'arista': 'eos',
                'juniper': 'junos',
                'hp': 'procurve',
                'hpe': 'procurve',
                'huawei': 'huawei',
                'fortinet': 'fortios',
                'palo alto': 'panos',
                'paloalto': 'panos',
                'aruba': 'aruba_cx'
            }
            napalm_driver = vendor_mapping.get(vendor, 'ios')

        # Final fallback
        if not napalm_driver:
            napalm_driver = 'ios'

        # Debug logging
        logger.info(f"Session mapping: device_type='{device_type}', vendor='{vendor}' -> driver='{napalm_driver}'")

        # Set driver in combo box
        driver_set = False
        for i in range(self.driver_combo.count()):
            if self.driver_combo.itemData(i) == napalm_driver:
                self.driver_combo.setCurrentIndex(i)
                driver_set = True
                break

        if not driver_set:
            logger.warning(f"Could not find NAPALM driver '{napalm_driver}' in combo box")
            # Show available drivers for debugging
            available_drivers = [self.driver_combo.itemData(i) for i in range(self.driver_combo.count())]
            logger.info(f"Available drivers: {available_drivers}")

        # Set port if different from default
        port = session_data.get('port', '22')
        if port != '22':
            self.port_spin.setValue(int(port))

        # Try to match credentials using credsid
        credsid = session_data.get('credsid')
        if credsid and self.credential_manager:
            self._try_match_credentials(credsid)

        # Switch to connection tab to show populated fields
        self.tab_widget.setCurrentIndex(1)

        # Show detailed success message with mapping info
        QMessageBox.information(
            self, "Session Applied",
            f"Connection fields populated from session '{session_data['display_name']}'.\n\n"
            f"Mapping details:\n"
            f"• Device Type: {session_data.get('device_type', 'Unknown')}\n"
            f"• Vendor: {session_data.get('vendor', 'Unknown')}\n" 
            f"• NAPALM Driver: {napalm_driver}\n"
            f"• Driver Set: {'✓' if driver_set else '✗'}\n\n"
            f"You may need to select appropriate credentials."
        )

    def _try_match_credentials(self, credsid):
        """Try to match credentials based on credential ID"""
        if not hasattr(self, 'credentials_combo'):
            return

        # Look for matching credential by ID or display name
        for i in range(self.credentials_combo.count()):
            cred_data = self.credentials_combo.itemData(i)
            if cred_data and (
                cred_data.get('id') == credsid or
                cred_data.get('display_name') == credsid or
                credsid.lower() in cred_data.get('display_name', '').lower()
            ):
                self.credentials_combo.setCurrentIndex(i)
                break

    def _setup_connection_tab(self, tab_widget):
        """Setup connection parameters tab"""
        layout = QVBoxLayout(tab_widget)

        # Saved credentials section (if available)
        if self.credential_manager:
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
        self.hostname_edit.setPlaceholderText("192.168.1.1 or device.example.com")
        device_layout.addRow("Hostname/IP:", self.hostname_edit)

        # NAPALM driver selection
        self.driver_combo = QComboBox()
        self._populate_drivers()
        device_layout.addRow("NAPALM Driver:", self.driver_combo)

        layout.addWidget(device_group)

        # Credentials group
        creds_group = QGroupBox("Authentication")
        creds_layout = QFormLayout(creds_group)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("admin")
        creds_layout.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("password")
        creds_layout.addRow("Password:", self.password_edit)

        self.show_passwords = QCheckBox("Show passwords")
        self.show_passwords.toggled.connect(self._toggle_password_visibility)
        creds_layout.addRow("", self.show_passwords)

        layout.addWidget(creds_group)

        layout.addStretch()

    def _setup_advanced_tab(self, tab_widget):
        """Setup advanced connection parameters tab"""
        layout = QVBoxLayout(tab_widget)

        # Connection parameters group
        conn_group = QGroupBox("Connection Parameters")
        conn_layout = QFormLayout(conn_group)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" seconds")
        conn_layout.addRow("Timeout:", self.timeout_spin)

        layout.addWidget(conn_group)

        # Driver-specific options group
        driver_group = QGroupBox("Driver-Specific Options")
        driver_layout = QFormLayout(driver_group)

        self.transport_combo = QComboBox()
        self.transport_combo.addItems(["ssh", "http", "https"])
        self.transport_combo.setCurrentText("ssh")
        driver_layout.addRow("Transport:", self.transport_combo)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        driver_layout.addRow("Port:", self.port_spin)

        layout.addWidget(driver_group)

        # Options group
        options_group = QGroupBox("Additional Options")
        options_layout = QFormLayout(options_group)

        self.verify_ssl = QCheckBox("Verify SSL certificates")
        self.verify_ssl.setChecked(True)
        options_layout.addRow("SSL Verification:", self.verify_ssl)

        layout.addWidget(options_group)

        layout.addStretch()

    def _setup_results_tab(self, tab_widget):
        """Setup test results display tab"""
        layout = QVBoxLayout(tab_widget)

        results_group = QGroupBox("Connection Test Results")
        results_layout = QVBoxLayout(results_group)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setFont(QFont("Consolas", 10))
        self.results_text.setPlaceholderText("Run connection test to see results here...")
        results_layout.addWidget(self.results_text)

        layout.addWidget(results_group)

    def _populate_drivers(self):
        """Populate NAPALM driver dropdown"""
        drivers = {
            "ios": "Cisco IOS",
            "iosxr": "Cisco IOS-XR",
            "nxos": "Cisco NX-OS",
            "nxos_ssh": "Cisco NX-OS (SSH)",
            "eos": "Arista EOS",
            "junos": "Juniper JunOS",
            "huawei": "Huawei VRP",
            "procurve": "HP ProCurve",
            "aruba_cx": "Aruba CX",
            "fortios": "Fortinet FortiOS",
            "panos": "Palo Alto PAN-OS"
        }

        for driver_key, display_name in drivers.items():
            self.driver_combo.addItem(f"{driver_key} - {display_name}", driver_key)

    def _load_saved_credentials(self):
        """Load saved credentials from credential manager"""
        if not self.credential_manager:
            if hasattr(self, 'credentials_combo'):
                self.credentials_combo.setEnabled(False)
                self.credentials_combo.clear()
                self.credentials_combo.addItem("-- No credential manager --", None)
            return

        try:
            if not self.credential_manager.is_initialized:
                if hasattr(self, 'credentials_combo'):
                    self.credentials_combo.setEnabled(False)
                    self.credentials_combo.clear()
                    self.credentials_combo.addItem("-- Credentials not initialized --", None)
                return

            if not self.credential_manager.is_unlocked():
                if hasattr(self, 'credentials_combo'):
                    self.credentials_combo.setEnabled(True)
                    self.credentials_combo.clear()
                    self.credentials_combo.addItem("-- Credentials locked --", None)
                return

            # Load credentials
            creds_path = self.credential_manager.config_dir / "credentials.yaml"
            if not creds_path.exists():
                if hasattr(self, 'credentials_combo'):
                    self.credentials_combo.clear()
                    self.credentials_combo.addItem("-- No saved credentials --", None)
                return

            self.saved_credentials = self.credential_manager.load_credentials(creds_path)

            if len(self.saved_credentials) > 0 and hasattr(self, 'credentials_combo'):
                self.credentials_combo.clear()
                self.credentials_combo.addItem("-- Manual Entry --", None)

                for cred in self.saved_credentials:
                    display_name = cred.get('display_name', cred.get('username', 'Unknown'))
                    self.credentials_combo.addItem(display_name, cred)

                self.credentials_combo.setEnabled(True)

        except Exception as e:
            logger.error(f"Failed to load saved credentials: {e}")
            if hasattr(self, 'credentials_combo'):
                self.credentials_combo.setEnabled(False)
                self.credentials_combo.clear()
                self.credentials_combo.addItem(f"-- Error loading credentials --", None)

    def _on_credential_selected(self, index):
        """Handle credential selection from dropdown"""
        if not hasattr(self, 'credentials_combo'):
            return

        cred_data = self.credentials_combo.itemData(index)

        if cred_data is None:
            # Manual entry selected
            self.username_edit.clear()
            self.password_edit.clear()
            self.username_edit.setEnabled(True)
            self.password_edit.setEnabled(True)
            self.show_passwords.setEnabled(True)
        else:
            # Saved credential selected
            self.username_edit.setText(cred_data.get('username', ''))
            self.password_edit.setText(cred_data.get('password', ''))

            # Disable editing when using saved credentials
            self.username_edit.setEnabled(False)
            self.password_edit.setEnabled(False)
            self.show_passwords.setEnabled(False)

    def _populate_defaults(self):
        """Populate with current parameters or defaults"""
        if self.current_params:
            self.hostname_edit.setText(self.current_params.get('hostname', ''))

            # Set driver
            driver = self.current_params.get('driver', 'ios')
            index = self.driver_combo.findData(driver)
            if index >= 0:
                self.driver_combo.setCurrentIndex(index)

            self.username_edit.setText(self.current_params.get('username', ''))
            # Don't populate password for security

            # Advanced parameters
            self.timeout_spin.setValue(self.current_params.get('timeout', 30))
            self.port_spin.setValue(self.current_params.get('port', 22))

            transport = self.current_params.get('transport', 'ssh')
            transport_index = self.transport_combo.findText(transport)
            if transport_index >= 0:
                self.transport_combo.setCurrentIndex(transport_index)

    def _toggle_password_visibility(self, checked):
        """Toggle password field visibility"""
        echo_mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.password_edit.setEchoMode(echo_mode)

    def _validate_inputs(self) -> tuple[bool, str]:
        """Validate user inputs"""
        if not self.hostname_edit.text().strip():
            return False, "Hostname/IP is required"

        if not self.username_edit.text().strip():
            return False, "Username is required"

        if not self.password_edit.text():
            return False, "Password is required"

        return True, "Valid"

    def _get_connection_params(self) -> Dict[str, Any]:
        """Get connection parameters from form"""
        params = {
            'hostname': self.hostname_edit.text().strip(),
            'username': self.username_edit.text().strip(),
            'password': self.password_edit.text(),
            'driver': self.driver_combo.currentData(),
            'timeout': self.timeout_spin.value(),
            'port': self.port_spin.value(),
            'transport': self.transport_combo.currentText(),
            'verify_ssl': self.verify_ssl.isChecked()
        }

        return params

    def _test_connection(self):
        """Test NAPALM connection"""
        valid, message = self._validate_inputs()
        if not valid:
            QMessageBox.warning(self, "Validation Error", message)
            return

        # Clear previous results
        self.results_text.clear()
        self.results_text.append("Testing connection...\n")

        # Disable buttons during test
        self.test_button.setEnabled(False)
        self.apply_button.setEnabled(False)

        # Start connection test in thread
        params = self._get_connection_params()
        self.test_thread = NapalmConnectionTestThread(params)
        self.test_thread.connection_result.connect(self._handle_test_result)
        self.test_thread.start()

    @pyqtSlot(bool, str, object)
    def _handle_test_result(self, success, message, facts_data):
        """Handle connection test result"""
        self.test_button.setEnabled(True)
        self.apply_button.setEnabled(True)

        if success:
            self.results_text.append(f"✓ {message}\n")

            if facts_data:
                self.results_text.append("Device Facts:")
                self.results_text.append("-" * 40)

                # Display key facts in a readable format
                key_facts = ['hostname', 'vendor', 'model', 'os_version', 'serial_number', 'uptime']
                for fact in key_facts:
                    if fact in facts_data:
                        value = facts_data[fact]
                        if fact == 'uptime':
                            # Convert uptime to readable format
                            if isinstance(value, (int, float)):
                                hours = int(value // 3600)
                                minutes = int((value % 3600) // 60)
                                value = f"{hours}h {minutes}m"
                        self.results_text.append(f"{fact.replace('_', ' ').title()}: {value}")

                self.results_text.append("\nFull facts data available in NAPALM widget after applying configuration.")

            # Switch to results tab to show success
            self.tab_widget.setCurrentIndex(3)

        else:
            self.results_text.append(f"✗ {message}")

            # Add troubleshooting hints
            if "authentication" in message.lower():
                self.results_text.append("\nTroubleshooting:")
                self.results_text.append("• Check username and password")
                self.results_text.append("• Verify device allows SSH access")
                self.results_text.append("• Check if account is locked/disabled")
            elif "connection" in message.lower() or "timeout" in message.lower():
                self.results_text.append("\nTroubleshooting:")
                self.results_text.append("• Verify hostname/IP address is reachable")
                self.results_text.append("• Check network connectivity")
                self.results_text.append("• Verify SSH port (usually 22)")
                self.results_text.append("• Check firewall rules")
            elif "driver" in message.lower():
                self.results_text.append("\nTroubleshooting:")
                self.results_text.append("• Try a different NAPALM driver")
                self.results_text.append("• Verify device platform compatibility")

            # Switch to results tab to show error
            self.tab_widget.setCurrentIndex(3)

        self.test_thread = None

    def _apply_configuration(self):
        """Apply configuration and close dialog"""
        valid, message = self._validate_inputs()
        if not valid:
            QMessageBox.warning(self, "Validation Error", message)
            return

        # Emit configuration
        params = self._get_connection_params()
        self.connection_configured.emit(params)

        self.accept()

    def _apply_theme_to_children(self, theme_name):
        """Apply theme to all child widgets"""
        if not self.theme_library:
            return

        try:
            # Apply theme to all child widgets
            for child in self.findChildren(QWidget):
                if child != self:
                    self.theme_library.apply_theme(child, theme_name)

            # Apply cyberpunk styling if needed
            if theme_name == "cyberpunk":
                self._apply_cyberpunk_styling()

        except Exception as e:
            logger.warning(f"Error applying theme to dialog children: {e}")

    def _apply_cyberpunk_styling(self):
        """Apply cyberpunk styling to form elements"""
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
        """

        combo_style = """
            QComboBox {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 6px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 20px;
                margin: 2px;
            }
            QComboBox:hover {
                border-color: #00ff88;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                selection-background-color: #00ffff;
                selection-color: #000000;
                color: #ffffff;
            }
        """

        button_style = """
            QPushButton {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 6px;
                padding: 10px 20px;
                color: #00ffff;
                font-weight: bold;
                font-size: 13px;
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
        """

        # Apply styles
        for line_edit in self.findChildren(QLineEdit):
            line_edit.setStyleSheet(input_style)

        for combo_box in self.findChildren(QComboBox):
            combo_box.setStyleSheet(combo_style)

        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)


class NapalmConnectionTestThread(QThread):
    """Thread for testing NAPALM connections without blocking UI"""

    connection_result = pyqtSignal(bool, str, object)  # success, message, facts_data

    def __init__(self, connection_params):
        super().__init__()
        self.connection_params = connection_params

    def run(self):
        """Test NAPALM connection in separate thread"""
        try:
            # Get driver
            driver_name = self.connection_params['driver']
            driver = napalm.get_network_driver(driver_name)

            # Prepare connection options
            driver_opts = {
                'hostname': self.connection_params['hostname'],
                'username': self.connection_params['username'],
                'password': self.connection_params['password']
            }

            # Add platform-specific options
            if driver_name == 'eos':
                driver_opts['optional_args'] = {'transport': 'ssh'}

            # Add timeout if specified
            if 'timeout' in self.connection_params:
                driver_opts['timeout'] = self.connection_params['timeout']

            # Create device connection
            device = driver(**driver_opts)

            # Open connection and get facts
            device.open()
            facts = device.get_facts()
            device.close()

            self.connection_result.emit(True, "Connection successful", facts)

        except Exception as e:
            self.connection_result.emit(False, f"Connection failed: {str(e)}", None)