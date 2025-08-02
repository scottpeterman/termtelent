import sys
import sqlite3
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QLabel, QMessageBox,
                             QFileDialog, QCheckBox, QGroupBox, QTextEdit,
                             QApplication, QProgressDialog, QComboBox, QFormLayout)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import yaml


class CMDBImportThread(QThread):
    """Background thread for importing devices from CMDB"""
    progress_updated = pyqtSignal(int, str)
    import_completed = pyqtSignal(list)
    import_failed = pyqtSignal(str)

    def __init__(self, db_path, selected_sites, credential_mapping):
        super().__init__()
        self.db_path = db_path
        self.selected_sites = selected_sites
        self.credential_mapping = credential_mapping

    def run(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            imported_data = []
            total_sites = len(self.selected_sites)

            for i, site_code in enumerate(self.selected_sites):
                self.progress_updated.emit(
                    int((i / total_sites) * 100),
                    f"Processing site: {site_code}"
                )

                # Query devices for this site with latest device information
                query = """
                SELECT DISTINCT
                    d.device_name,
                    d.hostname,
                    d.fqdn,
                    d.vendor,
                    d.model,
                    d.serial_number,
                    d.os_version,
                    d.site_code,
                    d.device_role,
                    di.ip_address as primary_ip,
                    di.ip_type,
                    cr.napalm_driver
                FROM devices d
                LEFT JOIN device_ips di ON d.id = di.device_id AND di.is_primary = 1
                LEFT JOIN (
                    SELECT device_id, napalm_driver,
                           ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY collection_time DESC) as rn
                    FROM collection_runs
                    WHERE success = 1
                ) cr ON d.id = cr.device_id AND cr.rn = 1
                WHERE d.site_code = ? AND d.is_active = 1
                ORDER BY d.device_name
                """

                cursor.execute(query, (site_code,))
                devices = cursor.fetchall()

                if devices:
                    sessions = []
                    for device in devices:
                        # Determine the best host to use for connection
                        host = device['primary_ip'] or device['hostname'] or device['fqdn'] or device['device_name']

                        # Map NAPALM driver to DeviceType
                        device_type = self._map_napalm_driver(device['napalm_driver'])

                        # Get credential ID for this site/device type
                        creds_id = self.credential_mapping.get(f"{site_code}_{device_type}",
                                                               self.credential_mapping.get('default', ''))

                        session = {
                            'display_name': device['device_name'] or device['hostname'] or host,
                            'host': host,
                            'port': '22',  # Default SSH port
                            'DeviceType': device_type,
                            'Model': device['model'] or '',
                            'SerialNumber': device['serial_number'] or '',
                            'SoftwareVersion': device['os_version'] or '',
                            'Vendor': device['vendor'] or '',
                            'credsid': creds_id
                        }
                        sessions.append(session)

                    folder_data = {
                        'folder_name': f"{site_code} ({len(sessions)} devices)",
                        'sessions': sessions
                    }
                    imported_data.append(folder_data)

            conn.close()
            self.progress_updated.emit(100, "Import completed")
            self.import_completed.emit(imported_data)

        except Exception as e:
            self.import_failed.emit(str(e))

    def _map_napalm_driver(self, napalm_driver):
        """Map NAPALM driver names to session DeviceType"""
        driver_mapping = {
            'ios': 'cisco_ios',
            'iosxr': 'cisco_ios_xr',
            'nxos': 'cisco_nxos',
            'eos': 'arista_eos',
            'junos': 'juniper_junos',
            'vyos': 'vyos',
            'fortios': 'fortinet',
            'panos': 'palo_alto_panos'
        }
        return driver_mapping.get(napalm_driver, napalm_driver or 'linux')


class CMDBImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db_path = None
        self.sites_data = []
        self.credential_mapping = {}
        self.imported_data = []
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Import Devices from RapidCMDB")
        self.setMinimumSize(700, 600)

        layout = QVBoxLayout(self)

        # Database selection
        db_group = QGroupBox("CMDB Database")
        db_layout = QVBoxLayout(db_group)

        db_select_layout = QHBoxLayout()
        self.db_path_label = QLabel("No database selected")
        select_db_btn = QPushButton("Select Database")
        select_db_btn.clicked.connect(self.select_database)

        db_select_layout.addWidget(QLabel("Database:"))
        db_select_layout.addWidget(self.db_path_label, 1)
        db_select_layout.addWidget(select_db_btn)

        db_layout.addLayout(db_select_layout)
        layout.addWidget(db_group)

        # Site selection
        sites_group = QGroupBox("Site Selection")
        sites_layout = QVBoxLayout(sites_group)

        # Site tree
        self.sites_tree = QTreeWidget()
        self.sites_tree.setHeaderLabels(["Site Code", "Device Count", "Last Updated"])
        self.sites_tree.setRootIsDecorated(False)
        sites_layout.addWidget(self.sites_tree)

        # Site selection buttons
        site_btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_sites)
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self.select_none_sites)
        refresh_btn = QPushButton("Refresh Sites")
        refresh_btn.clicked.connect(self.load_sites)

        site_btn_layout.addWidget(select_all_btn)
        site_btn_layout.addWidget(select_none_btn)
        site_btn_layout.addWidget(refresh_btn)
        site_btn_layout.addStretch()

        sites_layout.addLayout(site_btn_layout)
        layout.addWidget(sites_group)

        # Credential mapping
        creds_group = QGroupBox("Credential Mapping")
        creds_layout = QFormLayout(creds_group)

        self.default_creds = QComboBox()
        self.default_creds.setEditable(True)
        self.default_creds.addItems(['1', '2', '3', '4', '5'])  # Common credential IDs
        creds_layout.addRow("Default Credential ID:", self.default_creds)

        creds_help = QLabel("Devices will use this credential ID unless site-specific mapping is configured.")
        creds_help.setStyleSheet("color: #666; font-size: 10px;")
        creds_help.setWordWrap(True)
        creds_layout.addRow(creds_help)

        layout.addWidget(creds_group)

        # Import options
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)

        self.merge_sessions = QCheckBox("Merge with existing sessions")
        self.merge_sessions.setChecked(True)
        self.merge_sessions.setToolTip("Add imported devices to current session file, or create new file")

        self.create_backup = QCheckBox("Create backup of existing session file")
        self.create_backup.setChecked(True)

        options_layout.addWidget(self.merge_sessions)
        options_layout.addWidget(self.create_backup)
        layout.addWidget(options_group)

        # Preview area
        preview_group = QGroupBox("Import Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_text = QTextEdit()
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Select sites to see import preview...")

        preview_layout.addWidget(self.preview_text)
        layout.addWidget(preview_group)

        # Buttons
        button_layout = QHBoxLayout()

        preview_btn = QPushButton("Preview Import")
        preview_btn.clicked.connect(self.preview_import)

        import_btn = QPushButton("Import Devices")
        import_btn.clicked.connect(self.import_devices)
        import_btn.setDefault(True)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(preview_btn)
        button_layout.addStretch()
        button_layout.addWidget(import_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Connect signals
        self.sites_tree.itemChanged.connect(self.update_preview)

    def select_database(self):
        """Select the CMDB database file"""
        db_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select RapidCMDB Database",
            str(Path.home()),
            "SQLite Database (*.db);;All Files (*.*)"
        )

        if db_path and Path(db_path).exists():
            self.db_path = db_path
            self.db_path_label.setText(Path(db_path).name)
            self.load_sites()
        else:
            self.db_path = None
            self.db_path_label.setText("No database selected")
            self.sites_tree.clear()

    def load_sites(self):
        """Load available sites from the database"""
        if not self.db_path:
            QMessageBox.warning(self, "Warning", "Please select a database file first.")
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Query to get site information with device counts
            query = """
            SELECT 
                d.site_code,
                COUNT(d.id) as device_count,
                MAX(d.last_updated) as last_updated
            FROM devices d
            WHERE d.is_active = 1
            GROUP BY d.site_code
            ORDER BY d.site_code
            """

            cursor.execute(query)
            sites = cursor.fetchall()
            conn.close()

            # Populate the tree
            self.sites_tree.clear()
            for site_code, device_count, last_updated in sites:
                item = QTreeWidgetItem(self.sites_tree)
                item.setText(0, site_code)
                item.setText(1, str(device_count))
                item.setText(2, last_updated or "Unknown")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)

                # Store site data
                item.setData(0, Qt.ItemDataRole.UserRole, {
                    'site_code': site_code,
                    'device_count': device_count,
                    'last_updated': last_updated
                })

            self.sites_tree.resizeColumnToContents(0)
            self.sites_tree.resizeColumnToContents(1)

            if not sites:
                QMessageBox.information(self, "Info", "No active devices found in the database.")

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load sites: {str(e)}")

    def select_all_sites(self):
        """Select all sites"""
        for i in range(self.sites_tree.topLevelItemCount()):
            item = self.sites_tree.topLevelItem(i)
            item.setCheckState(0, Qt.CheckState.Checked)

    def select_none_sites(self):
        """Deselect all sites"""
        for i in range(self.sites_tree.topLevelItemCount()):
            item = self.sites_tree.topLevelItem(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)

    def get_selected_sites(self):
        """Get list of selected site codes"""
        selected = []
        for i in range(self.sites_tree.topLevelItemCount()):
            item = self.sites_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                site_data = item.data(0, Qt.ItemDataRole.UserRole)
                selected.append(site_data['site_code'])
        return selected

    def update_preview(self):
        """Update the preview text based on selection"""
        selected_sites = self.get_selected_sites()

        if not selected_sites:
            self.preview_text.setPlainText("No sites selected for import.")
            return

        total_devices = 0
        preview_lines = [f"Import Summary:"]
        preview_lines.append(f"Selected Sites: {len(selected_sites)}")
        preview_lines.append("")

        for i in range(self.sites_tree.topLevelItemCount()):
            item = self.sites_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                site_data = item.data(0, Qt.ItemDataRole.UserRole)
                site_code = site_data['site_code']
                device_count = site_data['device_count']
                total_devices += device_count

                preview_lines.append(f"• {site_code}: {device_count} devices")

        preview_lines.append("")
        preview_lines.append(f"Total Devices to Import: {total_devices}")
        preview_lines.append(f"Default Credential ID: {self.default_creds.currentText()}")

        self.preview_text.setPlainText("\n".join(preview_lines))

    def preview_import(self):
        """Show a detailed preview of what will be imported"""
        if not self.db_path:
            QMessageBox.warning(self, "Warning", "Please select a database file first.")
            return

        selected_sites = self.get_selected_sites()
        if not selected_sites:
            QMessageBox.warning(self, "Warning", "Please select at least one site to import.")
            return

        # Prepare credential mapping
        self.credential_mapping = {
            'default': self.default_creds.currentText() or '1'
        }

        # Show progress dialog
        progress = QProgressDialog("Loading preview...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        # Start import thread for preview
        self.import_thread = CMDBImportThread(self.db_path, selected_sites, self.credential_mapping)
        self.import_thread.progress_updated.connect(progress.setValue)
        self.import_thread.import_completed.connect(lambda data: self.show_preview_results(data, progress))
        self.import_thread.import_failed.connect(lambda error: self.handle_import_error(error, progress))
        self.import_thread.start()

    def show_preview_results(self, data, progress):
        """Show preview results in a dialog"""
        progress.close()

        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle("Import Preview")
        preview_dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(preview_dialog)

        # Create preview tree
        preview_tree = QTreeWidget()
        preview_tree.setHeaderLabels(["Name", "Host", "Type", "Vendor", "Model"])

        total_devices = 0
        for folder_data in data:
            folder_item = QTreeWidgetItem(preview_tree)
            folder_item.setText(0, folder_data['folder_name'])
            folder_item.setExpanded(True)

            for session in folder_data['sessions']:
                session_item = QTreeWidgetItem(folder_item)
                session_item.setText(0, session['display_name'])
                session_item.setText(1, session['host'])
                session_item.setText(2, session['DeviceType'])
                session_item.setText(3, session['Vendor'])
                session_item.setText(4, session['Model'])
                total_devices += 1

        layout.addWidget(QLabel(f"Preview: {total_devices} devices from {len(data)} sites"))
        layout.addWidget(preview_tree)

        # Buttons
        button_layout = QHBoxLayout()
        import_btn = QPushButton("Proceed with Import")
        import_btn.clicked.connect(lambda: (setattr(self, 'imported_data', data),
                                            preview_dialog.accept(),
                                            self.finalize_import()))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(preview_dialog.reject)

        button_layout.addStretch()
        button_layout.addWidget(import_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        preview_tree.resizeColumnToContents(0)
        preview_tree.resizeColumnToContents(1)

        preview_dialog.exec()

    def import_devices(self):
        """Import selected devices"""
        if not self.db_path:
            QMessageBox.warning(self, "Warning", "Please select a database file first.")
            return

        selected_sites = self.get_selected_sites()
        if not selected_sites:
            QMessageBox.warning(self, "Warning", "Please select at least one site to import.")
            return

        # Prepare credential mapping
        self.credential_mapping = {
            'default': self.default_creds.currentText() or '1'
        }

        # Show progress dialog
        progress = QProgressDialog("Importing devices...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        # Start import thread
        self.import_thread = CMDBImportThread(self.db_path, selected_sites, self.credential_mapping)
        self.import_thread.progress_updated.connect(
            lambda value, text: (progress.setValue(value), progress.setLabelText(text)))
        self.import_thread.import_completed.connect(lambda data: self.handle_import_success(data, progress))
        self.import_thread.import_failed.connect(lambda error: self.handle_import_error(error, progress))
        self.import_thread.start()

    def handle_import_success(self, data, progress):
        """Handle successful import"""
        progress.close()
        self.imported_data = data
        self.finalize_import()

    def finalize_import(self):
        """Finalize the import process"""
        if not self.imported_data:
            return

        total_devices = sum(len(folder['sessions']) for folder in self.imported_data)

        QMessageBox.information(
            self,
            "Import Completed",
            f"Successfully imported {total_devices} devices from {len(self.imported_data)} sites."
        )

        self.accept()

    def handle_import_error(self, error, progress):
        """Handle import error"""
        progress.close()
        QMessageBox.critical(self, "Import Error", f"Failed to import devices: {error}")

    def get_imported_data(self):
        """Return the imported session data"""
        return self.imported_data


def main():
    """Test the import dialog"""
    app = QApplication(sys.argv)

    dialog = CMDBImportDialog()
    if dialog.exec() == QDialog.DialogCode.Accepted:
        imported = dialog.get_imported_data()
        print(f"Imported {len(imported)} folders")
        for folder in imported:
            print(f"  {folder['folder_name']}: {len(folder['sessions'])} sessions")

    sys.exit(0)


if __name__ == "__main__":
    main()