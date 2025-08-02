import sys
import json
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QMenu, QLineEdit, QFormLayout, QComboBox,
                             QWidget, QLabel, QMessageBox, QSpinBox, QFileDialog, QApplication, QInputDialog,
                             QToolBar, QMainWindow)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
import yaml
from pathlib import Path

# Import the resource manager
from termtel.helpers.resource_manager import resource_manager

# Import the CMDB import dialog
from termtel.widgets.cmdb_import_dialog import CMDBImportDialog


class RestrictedTreeWidget(QTreeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        print("Tree widget initialized")

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)

        drop_item = self.itemAt(event.position().toPoint())
        drag_item = self.currentItem()

        if not drag_item or not drop_item:
            event.ignore()
            return

        drag_data = drag_item.data(0, Qt.ItemDataRole.UserRole)
        drop_data = drop_item.data(0, Qt.ItemDataRole.UserRole)

        # If we're dropping ON an item...
        if self.dropIndicatorPosition() == self.DropIndicatorPosition.OnItem:
            # Only allow if we're dropping a session onto a folder
            if drag_data['type'] == 'session' and drop_data['type'] == 'folder':
                event.acceptProposedAction()
            else:
                event.ignore()
            return

        # For between-item drops, validate same-folder for sessions
        if drag_data['type'] == 'session':
            if drag_item.parent() != drop_item.parent():
                event.ignore()
                return

        event.acceptProposedAction()

    def dropEvent(self, event):
        drop_item = self.itemAt(event.position().toPoint())
        drag_item = self.currentItem()

        if not drag_item or not drop_item:
            event.ignore()
            return

        drag_data = drag_item.data(0, Qt.ItemDataRole.UserRole)
        drop_data = drop_item.data(0, Qt.ItemDataRole.UserRole)

        # If we're dropping ON an item...
        if self.dropIndicatorPosition() == self.DropIndicatorPosition.OnItem:
            # Only allow if we're dropping a session onto a folder
            if not (drag_data['type'] == 'session' and drop_data['type'] == 'folder'):
                event.ignore()
                return

        # For between-item drops, validate same-folder for sessions
        elif drag_data['type'] == 'session':
            if drag_item.parent() != drop_item.parent():
                event.ignore()
                return

        super().dropEvent(event)


class SessionPropertyDialog(QDialog):
    def __init__(self, session_data=None, parent=None):
        super().__init__(parent)
        self.session_data = session_data or {}
        self.available_platforms = self._load_available_platforms()
        self.setup_ui()
        self.load_data()

    def _load_available_platforms(self):
        """
        Load available platforms from platforms.json via resource manager
        Returns list of platform keys for the dropdown
        """
        platforms = []

        try:
            # Get platforms config content
            config_content = resource_manager.get_platforms_config()

            if config_content:
                config_data = json.loads(config_content)

                # Extract platform keys and their display names
                if 'platforms' in config_data:
                    platforms_dict = config_data['platforms']

                    # Create list of tuples (key, display_name) for better UX
                    platform_items = []
                    for key, platform_config in platforms_dict.items():
                        display_name = platform_config.get('display_name', key)
                        platform_items.append((key, display_name))

                    # Sort by display name for better user experience
                    platform_items.sort(key=lambda x: x[1])

                    # Extract just the keys for the combo box
                    platforms = [item[0] for item in platform_items]

                    print(f"Loaded {len(platforms)} platforms from config")
                    for key, display in platform_items:
                        print(f"  - {key}: {display}")

            else:
                print("Could not load platforms config, using fallback list")

        except json.JSONDecodeError as e:
            print(f"Error parsing platforms.json: {e}")
        except Exception as e:
            print(f"Error loading platforms: {e}")

        # Fallback to basic list if config loading fails
        if not platforms:
            platforms = [
                "linux",
                "cisco_ios",
                "cisco_ios_xe",
                "cisco_nxos",
                "arista_eos",
                "hp_procurve",
                "juniper_junos",
                "aruba_aos_s",
                "aruba_aos_cx"
            ]
            print(f"Using fallback platform list: {platforms}")

        return platforms

    def setup_ui(self):
        self.setWindowTitle("Edit Session Properties")
        self.setMinimumWidth(400)  # Make dialog a bit wider
        layout = QFormLayout(self)

        # Create form fields
        self.fields = {
            'display_name': QLineEdit(),
            'host': QLineEdit(),
            'port': QSpinBox(),
            'DeviceType': QComboBox(),  # This will be populated dynamically
            'Model': QLineEdit(),
            'SerialNumber': QLineEdit(),
            'SoftwareVersion': QLineEdit(),
            'Vendor': QLineEdit(),
            'credsid': QLineEdit()
        }

        # Configure widgets
        self.fields['port'].setRange(1, 65535)
        self.fields['port'].setValue(22)  # Default SSH port

        # Configure DeviceType combo box
        device_combo = self.fields['DeviceType']
        device_combo.setEditable(True)  # Allow custom entries
        device_combo.setInsertPolicy(QComboBox.InsertPolicy.InsertAlphabetically)

        # Add platforms to combo box
        device_combo.addItems(self.available_platforms)

        # Set up auto-completion for better UX
        device_combo.setDuplicatesEnabled(False)
        device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

        # Add tooltip explaining the field
        device_combo.setToolTip(
            "Select a platform type for telemetry support, or enter custom value for terminal-only use.\n"
            "Platform types enable network monitoring features."
        )

        # Add fields to layout with better labels
        layout.addRow("Display Name:", self.fields['display_name'])
        layout.addRow("Host/IP:", self.fields['host'])
        layout.addRow("SSH Port:", self.fields['port'])
        layout.addRow("Platform Type:", self.fields['DeviceType'])
        layout.addRow("Model:", self.fields['Model'])
        layout.addRow("Serial Number:", self.fields['SerialNumber'])
        layout.addRow("Software Version:", self.fields['SoftwareVersion'])
        layout.addRow("Vendor:", self.fields['Vendor'])
        layout.addRow("Credentials ID:", self.fields['credsid'])

        # Add helpful text
        help_label = QLabel(
            "Platform Type: Select from list for telemetry support, or enter custom value for terminal-only sessions."
        )
        help_label.setStyleSheet("color: #666; font-size: 10px; margin: 5px;")
        help_label.setWordWrap(True)
        layout.addRow(help_label)

        # Add buttons
        button_box = QHBoxLayout()

        # Add refresh platforms button
        refresh_btn = QPushButton("Refresh Platforms")
        refresh_btn.clicked.connect(self._refresh_platforms)
        refresh_btn.setToolTip("Reload platform list from configuration")

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        save_btn.setDefault(True)  # Make this the default button

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        button_box.addWidget(refresh_btn)
        button_box.addStretch()
        button_box.addWidget(save_btn)
        button_box.addWidget(cancel_btn)

        layout.addRow(button_box)

    def _refresh_platforms(self):
        """Refresh the platform list from config"""
        device_combo = self.fields['DeviceType']
        current_text = device_combo.currentText()

        # Clear and reload platforms
        device_combo.clear()
        self.available_platforms = self._load_available_platforms()
        device_combo.addItems(self.available_platforms)

        # Restore previous selection if it exists
        if current_text:
            index = device_combo.findText(current_text)
            if index >= 0:
                device_combo.setCurrentIndex(index)
            else:
                # If not found in list, set as custom text
                device_combo.setCurrentText(current_text)

        QMessageBox.information(self, "Platforms Refreshed",
                                f"Loaded {len(self.available_platforms)} platform types from configuration.")

    def load_data(self):
        """Load session data into form fields"""
        for key, widget in self.fields.items():
            value = self.session_data.get(key, '')

            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QComboBox):
                # For combo box, try to find the value in the list
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
                else:
                    # If not in list, set as custom text (editable combo box)
                    widget.setCurrentText(str(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value) if value else 22)

    def get_data(self):
        """Extract data from form fields"""
        data = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                data[key] = widget.text()
            elif isinstance(widget, QComboBox):
                # Get the current text (works for both selected and custom entries)
                data[key] = widget.currentText()
            elif isinstance(widget, QSpinBox):
                data[key] = str(widget.value())
        return data

    def validate_data(self):
        """Validate form data before saving"""
        data = self.get_data()

        # Required fields
        if not data.get('display_name', '').strip():
            QMessageBox.warning(self, "Validation Error", "Display Name is required.")
            return False

        if not data.get('host', '').strip():
            QMessageBox.warning(self, "Validation Error", "Host/IP is required.")
            return False

        # Validate port range
        try:
            port = int(data.get('port', 22))
            if not (1 <= port <= 65535):
                QMessageBox.warning(self, "Validation Error", "Port must be between 1 and 65535.")
                return False
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Port must be a valid number.")
            return False

        return True

    def accept(self):
        """Override accept to add validation"""
        if self.validate_data():
            super().accept()


class SessionEditorDialog(QDialog):
    def __init__(self, parent=None, session_file=None):
        super().__init__(parent)
        self.session_file = session_file
        self.sessions_data = []
        self.setup_ui()
        if session_file:
            self.load_sessions()

    def setup_ui(self):
        self.setWindowTitle("Edit Sessions")
        self.resize(900, 700)

        layout = QVBoxLayout(self)

        # Add toolbar
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)

        # File operations
        new_file_btn = QPushButton("New File")
        new_file_btn.clicked.connect(self.new_file)
        new_file_btn.setToolTip("Create a new session file")

        open_file_btn = QPushButton("Open File")
        open_file_btn.clicked.connect(self.open_file)
        open_file_btn.setToolTip("Open an existing session file")

        save_file_btn = QPushButton("Save")
        save_file_btn.clicked.connect(self.save_sessions)
        save_file_btn.setToolTip("Save current sessions")

        save_as_btn = QPushButton("Save As")
        save_as_btn.clicked.connect(self.save_as)
        save_as_btn.setToolTip("Save sessions to a new file")

        # Separator
        separator1 = QLabel("|")
        separator1.setStyleSheet("color: #999; margin: 0 10px;")

        # CMDB Import
        import_cmdb_btn = QPushButton("Import from CMDB")
        import_cmdb_btn.clicked.connect(self.import_from_cmdb)
        import_cmdb_btn.setToolTip("Import devices from RapidCMDB database")
        import_cmdb_btn.setStyleSheet("font-weight: bold; color: #2E8B57;")

        # Separator
        separator2 = QLabel("|")
        separator2.setStyleSheet("color: #999; margin: 0 10px;")

        # Session operations
        add_folder_btn = QPushButton("Add Folder")
        add_folder_btn.clicked.connect(self.add_folder)

        add_session_btn = QPushButton("Add Session")
        add_session_btn.clicked.connect(self.add_session)

        toolbar_layout.addWidget(new_file_btn)
        toolbar_layout.addWidget(open_file_btn)
        toolbar_layout.addWidget(save_file_btn)
        toolbar_layout.addWidget(save_as_btn)
        toolbar_layout.addWidget(separator1)
        toolbar_layout.addWidget(import_cmdb_btn)
        toolbar_layout.addWidget(separator2)
        toolbar_layout.addWidget(add_folder_btn)
        toolbar_layout.addWidget(add_session_btn)
        toolbar_layout.addStretch()

        layout.addWidget(toolbar_widget)

        # File info
        self.file_info = QLabel("No file loaded")
        self.file_info.setStyleSheet("color: #666; font-size: 11px; margin: 5px 0;")
        layout.addWidget(self.file_info)

        # Tree widget
        self.tree = RestrictedTreeWidget()
        self.tree.setHeaderLabel("Sessions")
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemDoubleClicked.connect(self.edit_item)
        layout.addWidget(self.tree)

        # Bottom buttons
        button_layout = QHBoxLayout()

        # Statistics
        self.stats_label = QLabel()
        self.update_statistics()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.stats_label)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        self.update_file_info()

    def update_file_info(self):
        """Update the file information display"""
        if self.session_file:
            file_path = Path(self.session_file)
            self.file_info.setText(f"File: {file_path.name} ({file_path.parent})")
        else:
            self.file_info.setText("No file loaded - create new or open existing")

    def update_statistics(self):
        """Update the statistics display"""
        folder_count = self.tree.topLevelItemCount()
        session_count = 0

        for i in range(folder_count):
            folder_item = self.tree.topLevelItem(i)
            session_count += folder_item.childCount()

        self.stats_label.setText(f"Folders: {folder_count} | Sessions: {session_count}")

    def new_file(self):
        """Create a new session file"""
        if self.has_unsaved_changes():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save before creating a new file?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                if not self.save_sessions():
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.session_file = None
        self.sessions_data = []
        self.tree.clear()
        self.update_file_info()
        self.update_statistics()

    def open_file(self):
        """Open an existing session file"""
        if self.has_unsaved_changes():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save before opening another file?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                if not self.save_sessions():
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Session File",
            str(Path.home()),
            "YAML Files (*.yaml *.yml);;All Files (*.*)"
        )

        if file_path:
            self.session_file = file_path
            self.load_sessions()
            self.update_file_info()

    def save_as(self):
        """Save sessions to a new file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session File As",
            str(Path.home() / "sessions.yaml"),
            "YAML Files (*.yaml *.yml);;All Files (*.*)"
        )

        if file_path:
            # Ensure .yaml extension
            if not file_path.endswith(('.yaml', '.yml')):
                file_path += '.yaml'

            self.session_file = file_path
            if self.save_sessions():
                self.update_file_info()
                return True
        return False

    def has_unsaved_changes(self):
        """Check if there are unsaved changes (simplified check)"""
        # This is a basic implementation - in a full app you'd track modifications
        return self.tree.topLevelItemCount() > 0 and not self.session_file

    def import_from_cmdb(self):
        """Import devices from RapidCMDB database"""
        import_dialog = CMDBImportDialog(self)

        if import_dialog.exec() == QDialog.DialogCode.Accepted:
            imported_data = import_dialog.get_imported_data()

            if imported_data:
                # Check if we should merge or replace
                merge_mode = True
                if self.tree.topLevelItemCount() > 0:
                    reply = QMessageBox.question(
                        self, "Import Method",
                        "How would you like to import the devices?\n\n"
                        "Merge: Add to existing sessions\n"
                        "Replace: Clear existing and import only new devices",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Yes
                    )

                    if reply == QMessageBox.StandardButton.Cancel:
                        return
                    elif reply == QMessageBox.StandardButton.No:  # Replace
                        self.tree.clear()
                        self.sessions_data = []
                        merge_mode = False

                # Add imported folders to tree
                total_imported_sessions = 0
                for folder_data in imported_data:
                    folder_item = QTreeWidgetItem(self.tree)
                    folder_item.setText(0, folder_data['folder_name'])
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'folder'})

                    for session in folder_data.get('sessions', []):
                        session_item = QTreeWidgetItem(folder_item)
                        session_item.setText(0, session.get('display_name', session.get('host', 'New Session')))
                        session_item.setData(0, Qt.ItemDataRole.UserRole, {
                            'type': 'session',
                            'data': session
                        })
                        total_imported_sessions += 1

                self.tree.expandAll()
                self.update_statistics()

                # Show import success message
                QMessageBox.information(
                    self, "Import Successful",
                    f"Successfully imported {total_imported_sessions} devices from {len(imported_data)} sites.\n\n"
                    f"The devices have been {'merged with' if merge_mode else 'loaded as'} your session data."
                )

                # Always prompt to save the updated sessions
                if self.session_file:
                    # File already exists - ask if they want to save changes
                    reply = QMessageBox.question(
                        self, "Save Changes",
                        f"Would you like to save the imported devices to '{Path(self.session_file).name}'?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        if self.save_sessions():
                            QMessageBox.information(
                                self, "Saved",
                                f"Sessions with imported devices saved to {Path(self.session_file).name}"
                            )
                else:
                    # No file open - must save as new file
                    reply = QMessageBox.question(
                        self, "Save Imported Sessions",
                        "You need to save the imported sessions to a file.\n\n"
                        "Would you like to save them now?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        if self.save_as():
                            QMessageBox.information(
                                self, "Saved",
                                f"Imported sessions saved to {Path(self.session_file).name}"
                            )

    def edit_item(self, item):
        """Handle double-click editing of items"""
        item_data = item.data(0, Qt.ItemDataRole.UserRole)

        if item_data['type'] == 'folder':
            # Simple folder name edit
            name, ok = QInputDialog.getText(
                self, "Edit Folder", "Folder name:",
                QLineEdit.EchoMode.Normal, item.text(0)
            )
            if ok and name:
                item.setText(0, name)
                self.update_statistics()
        else:
            # Show session property dialog
            dialog = SessionPropertyDialog(item_data['data'], self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_data = dialog.get_data()
                item_data['data'] = new_data
                item.setData(0, Qt.ItemDataRole.UserRole, item_data)
                item.setText(0, new_data.get('display_name', new_data.get('host', 'New Session')))

    def load_sessions(self):
        try:
            with open(self.session_file) as f:
                self.sessions_data = yaml.safe_load(f) or []

            self.tree.clear()
            for folder in self.sessions_data:
                folder_item = QTreeWidgetItem(self.tree)
                folder_item.setText(0, folder.get('folder_name', 'Unnamed Folder'))
                folder_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'folder'})

                for session in folder.get('sessions', []):
                    session_item = QTreeWidgetItem(folder_item)
                    session_item.setText(0, session.get('display_name', session.get('host', 'New Session')))
                    session_item.setData(0, Qt.ItemDataRole.UserRole, {
                        'type': 'session',
                        'data': session
                    })

            self.tree.expandAll()
            self.update_statistics()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load sessions: {str(e)}")

    def save_sessions(self):
        if not self.session_file:
            return self.save_as()

        try:
            # Create backup if requested and file exists
            if Path(self.session_file).exists():
                backup_path = f"{self.session_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.session_file, backup_path)

            new_data = []
            for folder_idx in range(self.tree.topLevelItemCount()):
                folder_item = self.tree.topLevelItem(folder_idx)
                folder_data = {
                    'folder_name': folder_item.text(0),
                    'sessions': []
                }

                for session_idx in range(folder_item.childCount()):
                    session_item = folder_item.child(session_idx)
                    session_data = session_item.data(0, Qt.ItemDataRole.UserRole)['data']
                    folder_data['sessions'].append(session_data)

                new_data.append(folder_data)

            # Ensure directory exists
            Path(self.session_file).parent.mkdir(parents=True, exist_ok=True)

            with open(self.session_file, 'w') as f:
                yaml.safe_dump(new_data, f, default_flow_style=False, sort_keys=False)

            self.sessions_data = new_data
            if hasattr(self.parent(), 'session_navigator'):
                self.parent().session_navigator.load_sessions(new_data)
            return True

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save sessions: {str(e)}")
            return False

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return

        menu = QMenu(self)
        menu.addAction("Edit", lambda: self.edit_item(item))
        if item.data(0, Qt.ItemDataRole.UserRole)['type'] == 'folder':
            menu.addAction("Add Session", lambda: self.add_session(item))
        menu.addAction("Delete", lambda: self.delete_item(item))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def add_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            folder_item = QTreeWidgetItem(self.tree)
            folder_item.setText(0, name)
            folder_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'folder'})
            self.tree.setCurrentItem(folder_item)
            self.update_statistics()

    def add_session(self, parent_folder=None):
        if not parent_folder:
            selected = self.tree.selectedItems()
            parent_folder = selected[0] if selected and selected[0].data(0, Qt.ItemDataRole.UserRole)[
                'type'] == 'folder' else None

        if not parent_folder:
            QMessageBox.warning(self, "Warning", "Please select a folder first")
            return

        # Create new session with defaults
        session_data = {
            'display_name': 'New Session',
            'host': '',
            'port': '22',
            'DeviceType': 'linux',
            'Model': '',
            'SerialNumber': '',
            'SoftwareVersion': '',
            'Vendor': '',
            'credsid': ''
        }

        # Show property dialog for new session
        dialog = SessionPropertyDialog(session_data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            session_data = dialog.get_data()
            session_item = QTreeWidgetItem(parent_folder)
            session_item.setText(0, session_data.get('display_name', session_data.get('host', 'New Session')))
            session_item.setData(0, Qt.ItemDataRole.UserRole, {
                'type': 'session',
                'data': session_data
            })
            self.tree.setCurrentItem(session_item)
            self.update_statistics()

    def delete_item(self, item):
        if QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete {item.text(0)}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
            self.update_statistics()


def main():
    app = QApplication(sys.argv)

    # Prompt for file selection or new file
    reply = QMessageBox.question(
        None, "Session Editor",
        "Would you like to open an existing session file?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
    )

    session_file = None
    if reply == QMessageBox.StandardButton.Yes:
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select Session File",
            str(Path.home()),
            "YAML Files (*.yaml *.yml);;All Files (*.*)"
        )
        if file_path:
            session_file = file_path
        else:
            sys.exit(0)
    elif reply == QMessageBox.StandardButton.Cancel:
        sys.exit(0)

    try:
        editor = SessionEditorDialog(session_file=session_file)
        editor.exec()

    except Exception as e:
        QMessageBox.critical(None, "Error", f"An error occurred: {str(e)}")

    sys.exit(0)


if __name__ == "__main__":
    main()