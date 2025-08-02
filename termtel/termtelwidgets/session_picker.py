"""
session_picker.py - Session Selection Dialog for Telemetry
Standalone dialog for selecting sessions from parent app's session file
"""

import yaml
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                             QListWidgetItem, QPushButton, QLabel, QLineEdit,
                             QGroupBox, QMessageBox, QSplitter, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class SessionPickerDialog(QDialog):
    """Dialog for selecting sessions from the parent app's session file"""

    session_selected = pyqtSignal(dict)  # Emits selected session data

    def __init__(self, session_file_path, theme_library=None, parent=None):
        super().__init__(parent)
        self.session_file_path = session_file_path
        self.theme_library = theme_library
        self.sessions_data = []

        self.setWindowTitle("Select Session")
        self.setModal(True)
        self.setFixedSize(600, 450)

        self._setup_ui()
        self._load_sessions()

        # Apply theme if available
        if theme_library and hasattr(parent, 'current_theme'):
            current_theme = getattr(parent, 'current_theme', 'cyberpunk')
            theme_library.apply_theme(self, current_theme)
            self._apply_cyberpunk_styling()

    def _setup_ui(self):
        """Setup the session picker UI"""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Select a session to populate connection details:")
        header.setStyleSheet("font-weight: bold; font-size: 12px; padding: 5px;")
        layout.addWidget(header)

        # Main content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left side - session tree
        left_panel = self._create_session_panel()
        splitter.addWidget(left_panel)

        # Right side - session details
        right_panel = self._create_details_panel()
        splitter.addWidget(right_panel)

        # Set splitter proportions
        splitter.setSizes([300, 300])

        # Button layout
        button_layout = QHBoxLayout()

        self.select_button = QPushButton("Select Session")
        self.select_button.clicked.connect(self._select_session)
        self.select_button.setEnabled(False)
        button_layout.addWidget(self.select_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def _create_session_panel(self):
        """Create the session list panel"""
        panel = QGroupBox("Available Sessions")
        layout = QVBoxLayout(panel)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search sessions...")
        self.search_box.textChanged.connect(self._filter_sessions)
        layout.addWidget(self.search_box)

        # Session list
        self.session_list = QListWidget()
        self.session_list.itemSelectionChanged.connect(self._on_session_selected)
        self.session_list.itemDoubleClicked.connect(self._select_session)
        layout.addWidget(self.session_list)

        return panel

    def _create_details_panel(self):
        """Create the session details panel"""
        panel = QGroupBox("Session Details")
        layout = QVBoxLayout(panel)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(200)
        layout.addWidget(self.details_text)

        # Quick info labels
        self.info_layout = QVBoxLayout()
        layout.addLayout(self.info_layout)

        return panel

    def _load_sessions(self):
        """Load sessions from the YAML file"""
        try:
            if not Path(self.session_file_path).exists():
                QMessageBox.warning(self, "Sessions Not Found",
                                    f"Session file not found: {self.session_file_path}")
                return

            with open(self.session_file_path, 'r', encoding='utf-8') as f:
                self.sessions_data = yaml.safe_load(f) or []

            self._populate_session_list()

        except Exception as e:
            QMessageBox.critical(self, "Error Loading Sessions",
                                 f"Failed to load sessions: {str(e)}")

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

                # Apply filter
                if filter_text and filter_text.lower() not in display_name.lower() and \
                        filter_text.lower() not in host.lower():
                    continue

                # Create list item
                item_text = f"{display_name} ({host})"
                item = QListWidgetItem(item_text)

                # Store session data with the item
                session_data = {
                    'folder': folder_name,
                    'display_name': display_name,
                    'host': host,
                    'port': session.get('port', '22'),
                    'device_type': device_type,
                    'vendor': session.get('Vendor', ''),
                    'model': session.get('Model', ''),
                    'credsid': session.get('credsid', ''),
                    'full_session': session
                }
                item.setData(Qt.ItemDataRole.UserRole, session_data)

                # Add tooltip
                tooltip = f"Host: {host}\nType: {device_type}\nFolder: {folder_name}"
                item.setToolTip(tooltip)

                self.session_list.addItem(item)

    def _filter_sessions(self, text):
        """Filter sessions based on search text"""
        self._populate_session_list(text)

    def _on_session_selected(self):
        """Handle session selection"""
        current_item = self.session_list.currentItem()
        if not current_item:
            self.select_button.setEnabled(False)
            self.details_text.clear()
            return

        self.select_button.setEnabled(True)

        # Get session data
        session_data = current_item.data(Qt.ItemDataRole.UserRole)

        # Update details panel
        details = f"""Session: {session_data['display_name']}
Host: {session_data['host']}
Port: {session_data['port']}
Device Type: {session_data['device_type']}
Vendor: {session_data['vendor']}
Model: {session_data['model']}
Folder: {session_data['folder']}
Credential ID: {session_data['credsid']}"""

        self.details_text.setPlainText(details)

    def _select_session(self):
        """Select the current session and close dialog"""
        current_item = self.session_list.currentItem()
        if not current_item:
            return

        session_data = current_item.data(Qt.ItemDataRole.UserRole)
        self.session_selected.emit(session_data)
        self.accept()

    def _apply_cyberpunk_styling(self):
        """Apply cyberpunk styling to the dialog"""
        # Enhanced styling for session picker
        list_style = """
            QListWidget {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 4px;
                color: #ffffff;
                font-size: 11px;
                padding: 3px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 2px;
                margin: 1px;
            }
            QListWidget::item:hover {
                background-color: #00ffff;
                color: #000000;
            }
            QListWidget::item:selected {
                background-color: #00ff88;
                color: #000000;
                font-weight: bold;
            }
        """

        text_edit_style = """
            QTextEdit {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 4px;
                color: #ffffff;
                font-size: 10px;
                padding: 5px;
                font-family: 'Courier New', monospace;
            }
        """

        search_style = """
            QLineEdit {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #00ff88;
                background-color: #222222;
            }
            QLineEdit::placeholder {
                color: #666666;
            }
        """

        self.session_list.setStyleSheet(list_style)
        self.details_text.setStyleSheet(text_edit_style)
        self.search_box.setStyleSheet(search_style)