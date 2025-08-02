# widgets/unified_credential_manager.py
"""
Enhanced Unified Credential Manager
Manages both terminal session credentials and RapidCMDB network device credentials
with completed import/export and master password reset functionality
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QMenu, QAbstractItemView,
    QWidget, QInputDialog, QFileDialog, QTabWidget, QComboBox, QSpinBox,
    QCheckBox, QTextEdit, QSplitter, QGroupBox, QFormLayout, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot
from PyQt6.QtGui import QAction, QFont
import logging
import uuid
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import yaml
import json

from termtel.helpers.credslib import SecureCredentials

logger = logging.getLogger(__name__)


class MasterPasswordResetDialog(QDialog):
    """Dialog for resetting master password when forgotten"""

    def __init__(self, store_type: str, manager: SecureCredentials, parent=None):
        super().__init__(parent)
        self.store_type = store_type
        self.manager = manager
        self.store_name = "Terminal Session" if store_type == 'session' else "Network Device"
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(f"Reset {self.store_name} Master Password")
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Warning message
        warning_label = QLabel(
            f"⚠️ SECURITY WARNING ⚠️\n\n"
            f"Resetting the master password will:\n"
            f"• DELETE ALL existing {self.store_name.lower()} credentials\n"
            f"• Create a new encrypted credential store\n"
            f"• This action CANNOT be undone\n\n"
            f"If you have a backup, you can restore credentials after reset."
        )
        warning_label.setStyleSheet(
            "color: #d32f2f; font-weight: bold; padding: 10px; background-color: #fff3e0; border: 1px solid #ff9800; border-radius: 4px;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        # Confirmation checkbox
        self.confirm_checkbox = QCheckBox(
            f"I understand that ALL {self.store_name.lower()} credentials will be permanently deleted"
        )
        layout.addWidget(self.confirm_checkbox)

        # New password fields
        password_group = QGroupBox("New Master Password")
        password_layout = QFormLayout(password_group)

        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_input.setMinimumWidth(200)
        password_layout.addRow("New Password:", self.new_password_input)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addRow("Confirm Password:", self.confirm_password_input)

        self.show_passwords_cb = QCheckBox("Show passwords")
        self.show_passwords_cb.toggled.connect(self.toggle_password_visibility)
        password_layout.addRow("", self.show_passwords_cb)

        layout.addWidget(password_group)

        # Password strength indicator
        self.strength_label = QLabel("Password strength will appear here")
        self.strength_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.strength_label)

        self.new_password_input.textChanged.connect(self.update_password_strength)

        # Buttons
        button_layout = QHBoxLayout()

        self.reset_button = QPushButton("Reset Master Password")
        self.reset_button.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; padding: 8px;")
        self.reset_button.clicked.connect(self.perform_reset)
        self.reset_button.setEnabled(False)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(cancel_button)
        button_layout.addStretch()
        button_layout.addWidget(self.reset_button)

        layout.addLayout(button_layout)

        # Enable reset button only when conditions are met
        self.confirm_checkbox.toggled.connect(self.update_reset_button_state)
        self.new_password_input.textChanged.connect(self.update_reset_button_state)
        self.confirm_password_input.textChanged.connect(self.update_reset_button_state)

    def toggle_password_visibility(self, show):
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        self.new_password_input.setEchoMode(mode)
        self.confirm_password_input.setEchoMode(mode)

    def update_password_strength(self, password):
        """Update password strength indicator"""
        if not password:
            self.strength_label.setText("Password strength will appear here")
            return

        score = 0
        feedback = []

        if len(password) >= 8:
            score += 1
        else:
            feedback.append("at least 8 characters")

        if any(c.isupper() for c in password):
            score += 1
        else:
            feedback.append("uppercase letters")

        if any(c.islower() for c in password):
            score += 1
        else:
            feedback.append("lowercase letters")

        if any(c.isdigit() for c in password):
            score += 1
        else:
            feedback.append("numbers")

        if any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            score += 1
        else:
            feedback.append("special characters")

        if score <= 2:
            color = "#d32f2f"
            strength = "Weak"
        elif score <= 3:
            color = "#ff9800"
            strength = "Fair"
        elif score <= 4:
            color = "#4caf50"
            strength = "Good"
        else:
            color = "#2e7d32"
            strength = "Strong"

        if feedback:
            message = f"{strength} - Consider adding: {', '.join(feedback)}"
        else:
            message = f"{strength} password"

        self.strength_label.setText(message)
        self.strength_label.setStyleSheet(f"color: {color}; font-size: 10px;")

    def update_reset_button_state(self):
        """Enable reset button only when all conditions are met"""
        conditions_met = (
                self.confirm_checkbox.isChecked() and
                len(self.new_password_input.text()) >= 8 and
                self.new_password_input.text() == self.confirm_password_input.text()
        )
        self.reset_button.setEnabled(conditions_met)

    def perform_reset(self):
        """Perform the master password reset"""
        new_password = self.new_password_input.text()
        confirm_password = self.confirm_password_input.text()

        if new_password != confirm_password:
            QMessageBox.critical(self, "Password Mismatch", "Passwords do not match!")
            return

        if len(new_password) < 8:
            QMessageBox.critical(self, "Password Too Short", "Password must be at least 8 characters long!")
            return

        # Final confirmation
        reply = QMessageBox.question(
            self,
            "Final Confirmation",
            f"This will permanently delete ALL {self.store_name.lower()} credentials.\n\n"
            f"Are you absolutely sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # Perform the reset
            success = self.manager.reset_credentials(new_password)

            if success:
                QMessageBox.information(
                    self,
                    "Reset Complete",
                    f"{self.store_name} master password has been reset successfully.\n\n"
                    f"All previous credentials have been deleted.\n"
                    f"You can now add new credentials or restore from a backup."
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self,
                    "Reset Failed",
                    f"Failed to reset {self.store_name.lower()} master password.\n"
                    f"Please check the logs for more details."
                )

        except Exception as e:
            logger.error(f"Master password reset failed: {e}")
            QMessageBox.critical(
                self,
                "Reset Error",
                f"An error occurred during reset:\n{str(e)}"
            )


class NetworkCredentialDialog(QDialog):
    """Dialog for adding/editing RapidCMDB network device credentials"""

    def __init__(self, cred_data: Dict = None, parent=None):
        super().__init__(parent)
        self.cred_data = cred_data or {
            'name': '',
            'username': '',
            'password': '',
            'enable_password': '',
            'priority': 999,
            'created': datetime.now().isoformat()
        }
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Network Device Credential")
        self.setModal(True)
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # Form layout for credential fields
        form_layout = QFormLayout()

        # Credential Name
        self.name_input = QLineEdit(self.cred_data.get('name', ''))
        self.name_input.setPlaceholderText("e.g., 'primary', 'backup', 'readonly'")
        form_layout.addRow("Credential Name:", self.name_input)

        # Username
        self.username_input = QLineEdit(self.cred_data.get('username', ''))
        self.username_input.setPlaceholderText("Device username")
        form_layout.addRow("Username:", self.username_input)

        # Password
        self.password_input = QLineEdit(self.cred_data.get('password', ''))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Device password")
        form_layout.addRow("Password:", self.password_input)

        # Enable Password (optional)
        self.enable_password_input = QLineEdit(self.cred_data.get('enable_password', ''))
        self.enable_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.enable_password_input.setPlaceholderText("Enable password (optional)")
        form_layout.addRow("Enable Password:", self.enable_password_input)

        # Priority
        self.priority_input = QSpinBox()
        self.priority_input.setRange(1, 9999)
        self.priority_input.setValue(self.cred_data.get('priority', 999))
        self.priority_input.setToolTip("Lower numbers = higher priority")
        form_layout.addRow("Priority:", self.priority_input)

        layout.addLayout(form_layout)

        # Show password checkbox
        self.show_password_cb = QCheckBox("Show passwords")
        self.show_password_cb.toggled.connect(self.toggle_password_visibility)
        layout.addWidget(self.show_password_cb)

        # Buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

    def toggle_password_visibility(self, show):
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        self.password_input.setEchoMode(mode)
        self.enable_password_input.setEchoMode(mode)

    def get_credential_data(self) -> Dict:
        self.cred_data.update({
            'name': self.name_input.text().strip(),
            'username': self.username_input.text().strip(),
            'password': self.password_input.text(),
            'enable_password': self.enable_password_input.text(),
            'priority': self.priority_input.value(),
            'modified': datetime.now().isoformat()
        })
        return self.cred_data


class SessionCredentialDialog(QDialog):
    """Dialog for adding/editing terminal session credentials"""

    def __init__(self, cred_data: Dict = None, parent=None):
        super().__init__(parent)
        self.cred_data = cred_data or {
            'uuid': str(uuid.uuid4()),
            'display_name': '',
            'username': '',
            'password': ''
        }
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Terminal Session Credential")
        self.setModal(True)
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # Form layout
        form_layout = QFormLayout()

        # Display Name
        self.display_name_input = QLineEdit(self.cred_data.get('display_name', ''))
        self.display_name_input.setPlaceholderText("Friendly name for this credential")
        form_layout.addRow("Display Name:", self.display_name_input)

        # Username
        self.username_input = QLineEdit(self.cred_data.get('username', ''))
        self.username_input.setPlaceholderText("SSH/Telnet username")
        form_layout.addRow("Username:", self.username_input)

        # Password
        self.password_input = QLineEdit(self.cred_data.get('password', ''))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("SSH/Telnet password")
        form_layout.addRow("Password:", self.password_input)

        layout.addLayout(form_layout)

        # Show password checkbox
        self.show_password_cb = QCheckBox("Show password")
        self.show_password_cb.toggled.connect(self.toggle_password_visibility)
        layout.addWidget(self.show_password_cb)

        # Buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

    def toggle_password_visibility(self, show):
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        self.password_input.setEchoMode(mode)

    def get_credential_data(self) -> Dict:
        self.cred_data.update({
            'display_name': self.display_name_input.text().strip(),
            'username': self.username_input.text().strip(),
            'password': self.password_input.text()
        })
        return self.cred_data


class UnifiedCredentialManager(QDialog):
    """Unified credential manager for both network devices and terminal sessions"""

    credentials_updated = pyqtSignal()

    def __init__(self, parent=None, session_cred_manager=None, network_cred_manager=None):
        super().__init__(parent)

        # Use provided credential managers if available, otherwise create new ones
        self.session_cred_manager = parent.cred_manager

        self.network_cred_manager = network_cred_manager or SecureCredentials("rapidcmdb_collector")

        self.setup_ui()
        self.initialize_and_load()

    def setup_ui(self):
        self.setWindowTitle("Credential Manager")
        self.setModal(True)
        self.resize(1000, 600)

        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()

        # Terminal Sessions Tab
        self.session_tab = self.create_session_credentials_tab()
        self.tab_widget.addTab(self.session_tab, "Terminal Sessions")

        # Network Devices Tab
        self.network_tab = self.create_network_credentials_tab()
        self.tab_widget.addTab(self.network_tab, "Network Devices")

        # Migration Tab
        self.migration_tab = self.create_migration_tab()
        # self.tab_widget.addTab(self.migration_tab, "Migration & Security")

        layout.addWidget(self.tab_widget)

        # Bottom buttons
        button_layout = QHBoxLayout()

        # Left side - status
        self.status_label = QLabel("Ready")
        button_layout.addWidget(self.status_label)

        button_layout.addStretch()

        # Right side - close
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

    def create_session_credentials_tab(self) -> QWidget:
        """Create the terminal session credentials tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Toolbar
        toolbar = QHBoxLayout()
        add_session_btn = QPushButton("Add Session Credential")
        add_session_btn.clicked.connect(self.add_session_credential)

        import_session_btn = QPushButton("Import...")
        import_session_btn.clicked.connect(self.import_session_credentials)

        export_session_btn = QPushButton("Export...")
        export_session_btn.clicked.connect(self.export_session_credentials)

        toolbar.addWidget(add_session_btn)
        toolbar.addStretch()
        toolbar.addWidget(import_session_btn)
        toolbar.addWidget(export_session_btn)

        layout.addLayout(toolbar)

        # Session credentials table
        self.session_table = QTableWidget()
        self.session_table.setColumnCount(3)
        self.session_table.setHorizontalHeaderLabels(["Display Name", "Username", "Password"])
        self.session_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.session_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_table.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, 'session')
        )
        layout.addWidget(self.session_table)

        return tab

    def create_network_credentials_tab(self) -> QWidget:
        """Create the network device credentials tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Toolbar
        toolbar = QHBoxLayout()
        add_network_btn = QPushButton("Add Network Credential")
        add_network_btn.clicked.connect(self.add_network_credential)

        import_network_btn = QPushButton("Import Legacy Config...")
        import_network_btn.clicked.connect(self.import_legacy_network_config)

        export_network_btn = QPushButton("Export...")
        export_network_btn.clicked.connect(self.export_network_credentials)

        toolbar.addWidget(add_network_btn)
        toolbar.addStretch()
        toolbar.addWidget(import_network_btn)
        toolbar.addWidget(export_network_btn)

        layout.addLayout(toolbar)

        # Network credentials table
        self.network_table = QTableWidget()
        self.network_table.setColumnCount(5)
        self.network_table.setHorizontalHeaderLabels([
            "Name", "Username", "Priority", "Enable Password", "Created"
        ])
        self.network_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.network_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.network_table.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, 'network')
        )
        layout.addWidget(self.network_table)

        return tab

    def create_migration_tab(self) -> QWidget:
        """Create the migration and security tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Security Status Group
        security_group = QGroupBox("Security Status")
        security_layout = QVBoxLayout(security_group)

        self.security_status = QTextEdit()
        self.security_status.setReadOnly(True)
        self.security_status.setMaximumHeight(150)
        security_layout.addWidget(self.security_status)

        # Update security status
        self.update_security_status()

        layout.addWidget(security_group)

        # Migration Tools Group
        migration_group = QGroupBox("Migration Tools")
        migration_layout = QVBoxLayout(migration_group)

        # Legacy config migration
        legacy_layout = QHBoxLayout()
        legacy_layout.addWidget(QLabel("Legacy collector_config.yaml:"))
        migrate_legacy_btn = QPushButton("Scan & Migrate")
        migrate_legacy_btn.clicked.connect(self.scan_and_migrate_legacy)
        legacy_layout.addWidget(migrate_legacy_btn)
        migration_layout.addLayout(legacy_layout)

        # Reset credentials
        reset_layout = QHBoxLayout()
        reset_layout.addWidget(QLabel("Reset credential stores:"))
        reset_session_btn = QPushButton("Reset Session Credentials")
        reset_session_btn.clicked.connect(lambda: self.reset_credential_store('session'))
        reset_network_btn = QPushButton("Reset Network Credentials")
        reset_network_btn.clicked.connect(lambda: self.reset_credential_store('network'))
        reset_layout.addWidget(reset_session_btn)
        reset_layout.addWidget(reset_network_btn)
        migration_layout.addLayout(reset_layout)

        layout.addWidget(migration_group)

        # Backup & Recovery Group
        backup_group = QGroupBox("Backup & Recovery")
        backup_layout = QVBoxLayout(backup_group)

        backup_btn_layout = QHBoxLayout()
        backup_all_btn = QPushButton("Backup All Credentials")
        backup_all_btn.clicked.connect(self.backup_all_credentials)
        restore_all_btn = QPushButton("Restore All Credentials")
        restore_all_btn.clicked.connect(self.restore_all_credentials)

        backup_btn_layout.addWidget(backup_all_btn)
        backup_btn_layout.addWidget(restore_all_btn)
        backup_layout.addLayout(backup_btn_layout)

        layout.addWidget(backup_group)

        layout.addStretch()

        return tab

    def update_security_status(self):
        """Update the security status display"""
        status_text = []

        # Check session credentials
        if self.session_cred_manager.is_initialized:
            status_text.append("✅ Terminal session credentials: SECURE (encrypted)")
        else:
            status_text.append("⚠️ Terminal session credentials: NOT INITIALIZED")

        # Check network credentials
        if self.network_cred_manager.is_initialized:
            status_text.append("✅ Network device credentials: SECURE (encrypted)")
        else:
            status_text.append("⚠️ Network device credentials: NOT INITIALIZED")

        # Check for legacy files
        legacy_files = self.find_legacy_config_files()
        if legacy_files:
            status_text.append(
                f"🚨 SECURITY RISK: {len(legacy_files)} legacy config files with plaintext passwords found")
            for file in legacy_files:
                status_text.append(f"   - {file}")
        else:
            status_text.append("✅ No legacy plaintext configuration files found")

        self.security_status.setText("\n".join(status_text))

    def find_legacy_config_files(self) -> List[str]:
        """Find legacy configuration files with plaintext passwords"""
        legacy_files = []

        # Common locations and filenames
        search_paths = [Path('.'), Path('rapidcmdb'), Path('..')]
        config_files = ['collector_config.yaml', 'db_collector_config.yaml', 'npcollector_config.yaml',
                        'termtel_credentials.yaml']

        for search_path in search_paths:
            if not search_path.exists():
                continue

            for config_file in config_files:
                config_path = search_path / config_file
                if config_path.exists():
                    try:
                        with open(config_path, 'r') as f:
                            content = yaml.safe_load(f)
                            if content and 'credentials' in content:
                                credentials = content['credentials']
                                if credentials and any('password' in cred for cred in credentials):
                                    legacy_files.append(str(config_path))
                    except Exception:
                        pass

        return legacy_files

    def initialize_and_load(self):
        """Initialize both credential managers and load data"""
        # Only initialize/unlock if the managers aren't already unlocked

        # Initialize session credentials with reset option (only if not already unlocked)
        if not self.session_cred_manager.is_initialized:
            if not self.initialize_credential_store('session'):
                pass  # User can still use network credentials
        elif not self.session_cred_manager.is_unlocked():
            if not self.unlock_credential_store_with_reset('session'):
                pass  # User can still use network credentials

        # Initialize network credentials with reset option (only if not already unlocked)
        if not self.network_cred_manager.is_initialized:
            if not self.initialize_credential_store('network'):
                pass  # User can still use session credentials
        elif not self.network_cred_manager.is_unlocked():
            if not self.unlock_credential_store_with_reset('network'):
                pass  # User can still use session credentials

        # Load data for unlocked stores
        self.load_all_credentials()

    def initialize_credential_store(self, store_type: str) -> bool:
        """Initialize a credential store"""
        manager = self.session_cred_manager if store_type == 'session' else self.network_cred_manager
        store_name = "Terminal Session" if store_type == 'session' else "Network Device"

        reply = QMessageBox.question(
            self,
            f"Initialize {store_name} Credentials",
            f"No {store_name.lower()} credential store found. Create one?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            password, ok = QInputDialog.getText(
                self,
                f"Set {store_name} Master Password",
                f"Enter master password for {store_name.lower()} credentials:",
                QLineEdit.EchoMode.Password
            )

            if ok and password:
                if manager.setup_new_credentials(password):
                    self.status_label.setText(f"{store_name} credentials initialized")
                    return True
                else:
                    QMessageBox.critical(self, "Error", f"Failed to initialize {store_name.lower()} credentials")

        return False

    def unlock_credential_store_with_reset(self, store_type: str) -> bool:
        """Enhanced unlock with reset option for forgotten passwords"""
        manager = self.session_cred_manager if store_type == 'session' else self.network_cred_manager
        store_name = "Terminal Session" if store_type == 'session' else "Network Device"

        attempts = 3
        while attempts > 0:
            password, ok = QInputDialog.getText(
                self,
                f"Unlock {store_name} Credentials",
                f"Enter master password for {store_name.lower()} credentials ({attempts} attempts remaining):",
                QLineEdit.EchoMode.Password
            )

            if not ok:
                return False

            if manager.unlock(password):
                self.status_label.setText(f"{store_name} credentials unlocked")
                return True
            else:
                attempts -= 1
                if attempts > 0:
                    QMessageBox.warning(self, "Invalid Password", f"Invalid password. {attempts} attempts remaining.")
                else:
                    # Offer reset option
                    reply = QMessageBox.question(
                        self,
                        "Master Password Reset",
                        f"Maximum attempts exceeded for {store_name.lower()} credentials.\n\n"
                        f"Would you like to reset the master password?\n"
                        f"⚠️ This will delete all existing credentials!",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        return self.show_master_password_reset(store_type)

        return False

    def show_master_password_reset(self, store_type: str) -> bool:
        """Show master password reset dialog"""
        manager = self.session_cred_manager if store_type == 'session' else self.network_cred_manager

        reset_dialog = MasterPasswordResetDialog(store_type, manager, self)
        if reset_dialog.exec() == QDialog.DialogCode.Accepted:
            # Password was successfully reset
            self.load_all_credentials()
            return True
        return False

    def load_all_credentials(self):
        """Load credentials for all unlocked stores"""
        try:
            if self.session_cred_manager.is_unlocked():
                self.load_session_credentials()
        except Exception as e:
            logger.error(f"Failed to load session credentials: {e}")

        try:
            if self.network_cred_manager.is_unlocked():
                self.load_network_credentials()
        except Exception as e:
            logger.error(f"Failed to load network credentials: {e}")

        # Update security status
        self.update_security_status()

    def load_session_credentials(self):
        """Load terminal session credentials"""
        try:
            creds_path = self.session_cred_manager.config_dir / "credentials.yaml"
            if not creds_path.exists():
                self.session_cred_manager.save_credentials([], creds_path)

            creds_list = self.session_cred_manager.load_credentials(creds_path)

            self.session_table.setRowCount(len(creds_list))
            for row, cred in enumerate(creds_list):
                display_name_item = QTableWidgetItem(cred.get('display_name', ''))
                username_item = QTableWidgetItem(cred.get('username', ''))
                password_item = QTableWidgetItem('********' if cred.get('password') else '')

                display_name_item.setData(Qt.ItemDataRole.UserRole, cred)

                self.session_table.setItem(row, 0, display_name_item)
                self.session_table.setItem(row, 1, username_item)
                self.session_table.setItem(row, 2, password_item)

            self.session_table.resizeColumnsToContents()

        except Exception as e:
            logger.error(f"Failed to load session credentials: {e}")

    def load_network_credentials(self):
        """Load network device credentials"""
        try:
            creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"
            if not creds_path.exists():
                self.network_cred_manager.save_credentials([], creds_path)

            creds_list = self.network_cred_manager.load_credentials(creds_path)

            self.network_table.setRowCount(len(creds_list))
            for row, cred in enumerate(creds_list):
                name_item = QTableWidgetItem(cred.get('name', ''))
                username_item = QTableWidgetItem(cred.get('username', ''))
                priority_item = QTableWidgetItem(str(cred.get('priority', 999)))
                enable_pwd_item = QTableWidgetItem('Yes' if cred.get('enable_password') else 'No')
                created_item = QTableWidgetItem(cred.get('created', '')[:10])  # Date only

                name_item.setData(Qt.ItemDataRole.UserRole, cred)

                self.network_table.setItem(row, 0, name_item)
                self.network_table.setItem(row, 1, username_item)
                self.network_table.setItem(row, 2, priority_item)
                self.network_table.setItem(row, 3, enable_pwd_item)
                self.network_table.setItem(row, 4, created_item)

            self.network_table.resizeColumnsToContents()

        except Exception as e:
            logger.error(f"Failed to load network credentials: {e}")

    def show_context_menu(self, position, table_type):
        """Show context menu for credential entries"""
        table = self.session_table if table_type == 'session' else self.network_table

        menu = QMenu()
        edit_action = QAction("Edit", self)
        delete_action = QAction("Delete", self)

        if table_type == 'session':
            edit_action.triggered.connect(self.edit_session_credential)
            delete_action.triggered.connect(self.delete_session_credential)
        else:
            edit_action.triggered.connect(self.edit_network_credential)
            delete_action.triggered.connect(self.delete_network_credential)

        menu.addAction(edit_action)
        menu.addAction(delete_action)

        menu.exec(table.viewport().mapToGlobal(position))

    def add_session_credential(self):
        """Add new session credential"""
        if not self.session_cred_manager.is_unlocked():
            if not self.unlock_credential_store_with_reset('session'):
                return

        dialog = SessionCredentialDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                cred_data = dialog.get_credential_data()

                creds_path = self.session_cred_manager.config_dir / "credentials.yaml"
                creds_list = self.session_cred_manager.load_credentials(creds_path)
                creds_list.append(cred_data)

                self.session_cred_manager.save_credentials(creds_list, creds_path)
                self.load_session_credentials()
                self.credentials_updated.emit()

            except Exception as e:
                logger.error(f"Failed to add session credential: {e}")
                QMessageBox.critical(self, "Error", f"Failed to add credential: {e}")

    def add_network_credential(self):
        """Add new network credential"""
        if not self.network_cred_manager.is_unlocked():
            if not self.unlock_credential_store_with_reset('network'):
                return

        dialog = NetworkCredentialDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                cred_data = dialog.get_credential_data()

                # Validate required fields
                if not cred_data['name'] or not cred_data['username']:
                    QMessageBox.warning(self, "Validation Error", "Name and Username are required.")
                    return

                creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"
                creds_list = self.network_cred_manager.load_credentials(creds_path)

                # Check for duplicate names
                if any(cred['name'] == cred_data['name'] for cred in creds_list):
                    QMessageBox.warning(self, "Duplicate Name", f"Credential '{cred_data['name']}' already exists.")
                    return

                creds_list.append(cred_data)

                self.network_cred_manager.save_credentials(creds_list, creds_path)
                self.load_network_credentials()
                self.credentials_updated.emit()

            except Exception as e:
                logger.error(f"Failed to add network credential: {e}")
                QMessageBox.critical(self, "Error", f"Failed to add credential: {e}")

    def edit_session_credential(self):
        """Edit selected session credential"""
        current_row = self.session_table.currentRow()
        if current_row >= 0:
            cred_data = self.session_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)

            dialog = SessionCredentialDialog(cred_data, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    updated_cred = dialog.get_credential_data()

                    creds_path = self.session_cred_manager.config_dir / "credentials.yaml"
                    creds_list = self.session_cred_manager.load_credentials(creds_path)

                    # Update credential
                    for i, cred in enumerate(creds_list):
                        if cred['uuid'] == updated_cred['uuid']:
                            creds_list[i] = updated_cred
                            break

                    self.session_cred_manager.save_credentials(creds_list, creds_path)
                    self.load_session_credentials()
                    self.credentials_updated.emit()

                except Exception as e:
                    logger.error(f"Failed to update session credential: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to update credential: {e}")

    def edit_network_credential(self):
        """Edit selected network credential"""
        current_row = self.network_table.currentRow()
        if current_row >= 0:
            cred_data = self.network_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)

            dialog = NetworkCredentialDialog(cred_data, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    updated_cred = dialog.get_credential_data()

                    creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"
                    creds_list = self.network_cred_manager.load_credentials(creds_path)

                    # Update credential
                    for i, cred in enumerate(creds_list):
                        if cred.get('name') == updated_cred['name']:
                            creds_list[i] = updated_cred
                            break

                    self.network_cred_manager.save_credentials(creds_list, creds_path)
                    self.load_network_credentials()
                    self.credentials_updated.emit()

                except Exception as e:
                    logger.error(f"Failed to update network credential: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to update credential: {e}")

    def delete_session_credential(self):
        """Delete selected session credential"""
        current_row = self.session_table.currentRow()
        if current_row >= 0:
            cred_data = self.session_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete credential for '{cred_data['display_name']}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                try:
                    creds_path = self.session_cred_manager.config_dir / "credentials.yaml"
                    creds_list = self.session_cred_manager.load_credentials(creds_path)
                    creds_list = [c for c in creds_list if c['uuid'] != cred_data['uuid']]

                    self.session_cred_manager.save_credentials(creds_list, creds_path)
                    self.load_session_credentials()
                    self.credentials_updated.emit()

                except Exception as e:
                    logger.error(f"Failed to delete session credential: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to delete credential: {e}")

    def delete_network_credential(self):
        """Delete selected network credential"""
        current_row = self.network_table.currentRow()
        if current_row >= 0:
            cred_data = self.network_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete network credential '{cred_data['name']}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                try:
                    creds_path = self.network_cred_manager.config_dir / "network_credentials.yaml"
                    creds_list = self.network_cred_manager.load_credentials(creds_path)
                    creds_list = [c for c in creds_list if c['name'] != cred_data['name']]

                    self.network_cred_manager.save_credentials(creds_list, creds_path)
                    self.load_network_credentials()
                    self.credentials_updated.emit()

                except Exception as e:
                    logger.error(f"Failed to delete network credential: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to delete credential: {e}")

    def import_session_credentials(self):
        """Enhanced session credentials import"""
        if not self.session_cred_manager.is_unlocked():
            if not self.unlock_credential_store_with_reset('session'):
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Session Credentials",
            "",
            "YAML Files (*.yaml *.yml);;JSON Files (*.json);;All Files (*)"
        )

        if not file_path:
            return

        try:
            # Load and parse file
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.lower().endswith('.json'):
                    import_data = json.load(f)
                else:
                    import_data = yaml.safe_load(f)

            if not import_data:
                QMessageBox.warning(self, "Import Error", "File appears to be empty or invalid.")
                return

            # Handle different import formats
            credentials_to_import = []

            # Check for legacy termtel_credentials.yaml format (like your uploaded file)
            if isinstance(import_data, dict) and 'credentials' in import_data and 'last_modified' in import_data:
                credentials_to_import = import_data['credentials']
            # Check for direct credentials array
            elif isinstance(import_data, dict) and 'credentials' in import_data:
                credentials_to_import = import_data['credentials']
            # Check for array at root level
            elif isinstance(import_data, list):
                credentials_to_import = import_data
            else:
                QMessageBox.warning(self, "Import Error", "Unrecognized file format.")
                return

            if not credentials_to_import:
                QMessageBox.information(self, "No Data", "No credentials found in file.")
                return

            # Convert and validate credentials
            converted_creds = []
            skipped_count = 0

            for i, cred in enumerate(credentials_to_import):
                try:
                    converted_cred = {
                        'uuid': cred.get('uuid', str(uuid.uuid4())),
                        'display_name': cred.get('display_name', f'Imported {i + 1}'),
                        'username': cred.get('username', ''),
                        'password': ''
                    }

                    # Handle different password formats
                    if cred.get('password'):
                        password = cred['password']

                        # Check if it's already encrypted (Fernet token starts with gAAAAAB)
                        if isinstance(password, str) and password.startswith('gAAAAAB'):
                            try:
                                # Try to decrypt with current manager (same master password)
                                from cryptography.fernet import Fernet
                                decrypted_bytes = self.session_cred_manager._fernet.decrypt(password.encode())
                                converted_cred['password'] = decrypted_bytes.decode('utf-8')
                            except Exception:
                                # If decryption fails, treat as plaintext (different master password or corrupted)
                                converted_cred['password'] = password
                        else:
                            # Treat as plaintext
                            converted_cred['password'] = str(password)

                    # Validate and clean up display name
                    if not converted_cred['display_name'].strip():
                        converted_cred['display_name'] = f'Imported {i + 1}'

                    converted_creds.append(converted_cred)

                except Exception as e:
                    logger.warning(f"Skipping invalid credential at index {i}: {e}")
                    skipped_count += 1
                    continue

            if not converted_creds:
                QMessageBox.warning(self, "Import Error", "No valid credentials found in file.")
                return

            # Load existing credentials and check for conflicts
            creds_path = self.session_cred_manager.config_dir / "credentials.yaml"
            existing_creds = self.session_cred_manager.load_credentials(creds_path)

            # Check for conflicts by UUID and display name
            uuid_conflicts = []
            name_conflicts = []

            for new_cred in converted_creds:
                uuid_conflict = any(existing['uuid'] == new_cred['uuid'] for existing in existing_creds)
                name_conflict = any(existing['display_name'] == new_cred['display_name'] for existing in existing_creds)

                if uuid_conflict:
                    uuid_conflicts.append(new_cred['display_name'])
                elif name_conflict:
                    name_conflicts.append(new_cred['display_name'])

            all_conflicts = list(set(uuid_conflicts + name_conflicts))
            if all_conflicts:
                reply = QMessageBox.question(
                    self,
                    "Import Conflicts",
                    f"Found {len(all_conflicts)} conflicts:\n{', '.join(all_conflicts[:5])}"
                    + ("..." if len(all_conflicts) > 5 else "") + "\n\n"
                                                                  f"Yes - Overwrite existing\nNo - Skip conflicts\nCancel - Abort",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                )

                if reply == QMessageBox.StandardButton.Cancel:
                    return
                elif reply == QMessageBox.StandardButton.No:
                    # Rename conflicts
                    timestamp = datetime.now().strftime('%m%d_%H%M')
                    for cred in converted_creds:
                        if cred['display_name'] in name_conflicts:
                            cred['display_name'] += f" (imported {timestamp})"
                        if cred['uuid'] in [existing['uuid'] for existing in existing_creds]:
                            cred['uuid'] = str(uuid.uuid4())
                else:
                    # Remove existing conflicting credentials
                    existing_creds = [c for c in existing_creds
                                      if not (c['uuid'] in [new['uuid'] for new in converted_creds] or
                                              c['display_name'] in [new['display_name'] for new in converted_creds])]

            # Save merged credentials
            final_creds = existing_creds + converted_creds
            self.session_cred_manager.save_credentials(final_creds, creds_path)

            # Refresh UI
            self.load_session_credentials()
            self.credentials_updated.emit()

            # Show results
            result_msg = f"Import completed!\n\n"
            result_msg += f"✅ Imported: {len(converted_creds)} credentials\n"
            if skipped_count > 0:
                result_msg += f"⚠️ Skipped: {skipped_count} invalid entries\n"
            result_msg += f"\n📁 Source: {Path(file_path).name}"

            QMessageBox.information(self, "Import Complete", result_msg)

        except Exception as e:
            logger.error(f"Failed to import session credentials: {e}")
            QMessageBox.critical(self, "Import Error", f"Failed to import session credentials:\n{str(e)}")

    def export_session_credentials(self):
        """Enhanced session credentials export"""
        if not self.session_cred_manager.is_unlocked():
            QMessageBox.warning(self, "Access Required", "Session credentials must be unlocked to export.")
            return

        try:
            # Load current credentials
            creds_path = self.session_cred_manager.config_dir / "credentials.yaml"
            creds_list = self.session_cred_manager.load_credentials(creds_path)

            if not creds_list:
                QMessageBox.information(self, "No Data", "No session credentials to export.")
                return

            # Choose export format
            format_reply = QMessageBox.question(
                self,
                "Export Format",
                f"Choose export format for {len(creds_list)} credentials:\n\n"
                f"Yes - Encrypted format (secure, requires same master password)\n"
                f"No - Legacy format (compatible, plaintext passwords)\n"
                f"Cancel - Abort export",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )

            if format_reply == QMessageBox.StandardButton.Cancel:
                return

            use_encrypted_format = format_reply == QMessageBox.StandardButton.Yes

            # Get export location
            default_filename = f"session_credentials_{'encrypted' if use_encrypted_format else 'legacy'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Session Credentials",
                default_filename,
                "YAML Files (*.yaml *.yml);;All Files (*)"
            )

            if not file_path:
                return

            # Create export data
            if use_encrypted_format:
                # Modern encrypted export format
                export_data = {
                    'export_info': {
                        'type': 'termtel_session_credentials',
                        'version': '2.0',
                        'created': datetime.now().isoformat(),
                        'app_name': self.session_cred_manager.app_name,
                        'credential_count': len(creds_list),
                        'encryption': 'fernet',
                        'note': 'Passwords are encrypted and require the same master password to decrypt'
                    },
                    'credentials': []
                }

                # Encrypt passwords for export using Fernet directly
                for cred in creds_list:
                    export_cred = cred.copy()
                    if export_cred.get('password'):
                        # Use Fernet directly to match your credslib format
                        encrypted = self.session_cred_manager._fernet.encrypt(export_cred['password'].encode())
                        export_cred['password'] = encrypted.decode('utf-8')
                    export_data['credentials'].append(export_cred)

            else:
                # Legacy format (similar to your uploaded termtel_credentials.yaml)
                export_data = {
                    'credentials': [],
                    'last_modified': datetime.now().isoformat()
                }

                # Keep passwords as plaintext for legacy compatibility
                for cred in creds_list:
                    legacy_cred = {
                        'uuid': cred['uuid'],
                        'display_name': cred['display_name'],
                        'username': cred['username'],
                        'password': cred.get('password', '')  # Store in plaintext for legacy compatibility
                    }
                    export_data['credentials'].append(legacy_cred)

            # Save to file
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(export_data, f, default_flow_style=False, indent=2, allow_unicode=True)

            # Show completion message
            security_note = ""
            if use_encrypted_format:
                security_note = "\n🔒 Passwords are encrypted and require the same master password to import."
            else:
                security_note = "\n⚠️ This file contains PLAINTEXT passwords! Keep it secure."

            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {len(creds_list)} session credentials.\n\n"
                f"📁 File: {Path(file_path).name}\n"
                f"📍 Location: {Path(file_path).parent}{security_note}"
            )

        except Exception as e:
            logger.error(f"Failed to export session credentials: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export session credentials:\n{str(e)}")

    def reset_credential_store(self, store_type: str):
        """Reset a credential store using the MasterPasswordResetDialog"""
        manager = self.session_cred_manager if store_type == 'session' else self.network_cred_manager

        reset_dialog = MasterPasswordResetDialog(store_type, manager, self)
        if reset_dialog.exec() == QDialog.DialogCode.Accepted:
            # Password was successfully reset, reload everything
            self.load_all_credentials()
            self.update_security_status()

    # Placeholder methods - implement these based on your specific network credential needs
    def import_legacy_network_config(self):
        """Import from legacy collector_config.yaml"""
        QMessageBox.information(self, "Coming Soon",
                                "Legacy network config import will be implemented based on your specific format.")

    def export_network_credentials(self):
        """Export network credentials"""
        QMessageBox.information(self, "Coming Soon", "Network credential export will be implemented.")

    def scan_and_migrate_legacy(self):
        """Scan for and migrate legacy configuration files"""
        legacy_files = self.find_legacy_config_files()

        if not legacy_files:
            QMessageBox.information(self, "Scan Complete", "No legacy configuration files found.")
            return

        files_text = "\n".join(f"  - {f}" for f in legacy_files)
        QMessageBox.information(
            self,
            "Legacy Files Found",
            f"Found {len(legacy_files)} legacy configuration files:\n\n{files_text}\n\n"
            f"Use the Import buttons to migrate credentials from these files."
        )

    def backup_all_credentials(self):
        """Backup all credentials to encrypted archive"""
        QMessageBox.information(self, "Coming Soon", "Full backup functionality will be implemented.")

    def restore_all_credentials(self):
        """Restore all credentials from backup"""
        QMessageBox.information(self, "Coming Soon", "Full restore functionality will be implemented.")