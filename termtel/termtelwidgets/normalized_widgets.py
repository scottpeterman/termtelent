"""
Normalized Telemetry Widgets with Template Editor Integration
These widgets can handle both raw output parsing and normalized data structures
Now includes gear buttons to open template editors for each widget
"""
import csv
from datetime import datetime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem, QTextEdit,
                             QComboBox, QPushButton, QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QColor
from typing import List, Dict, Optional
import os

# Import the base widget classes and data structures
# These would come from your controller file
from dataclasses import dataclass


@dataclass
class NormalizedNeighborData:
    """Normalized neighbor data structure across all platforms"""
    local_interface: str
    neighbor_device: str
    neighbor_interface: str
    neighbor_ip: str = ""
    neighbor_platform: str = ""
    neighbor_capability: str = ""
    protocol_used: str = ""


@dataclass
class NormalizedArpData:
    """Normalized ARP data structure across all platforms"""
    ip_address: str
    mac_address: str
    interface: str
    age: str = ""
    type: str = ""
    state: str = ""


@dataclass
class NormalizedRouteData:
    """Normalized route data structure across all platforms"""
    network: str
    next_hop: str
    protocol: str
    mask: str = ""
    interface: str = ""
    metric: str = ""
    admin_distance: str = ""
    age: str = ""
    vrf: str = "default"



class TemplateEditableWidget:
    """Mixin class to add template editing capability to widgets"""

    def __init__(self, widget_type: str, controller, theme_library=None):
        self.widget_type = widget_type
        self.controller = controller
        self.theme_library = theme_library

        # Create gear button
        self.gear_button = QPushButton("⚙️")
        self.gear_button.setMaximumWidth(30)
        self.gear_button.setMaximumHeight(30)
        self.gear_button.setToolTip(f"Edit template for {widget_type}")
        self.gear_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                border-radius: 15px;
                font-size: 14px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border-color: #00ffff;
                color: #00ffff;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
        """)
        self.gear_button.clicked.connect(self._open_template_editor)

    def _open_template_editor(self):
        """Open template editor for this widget"""
        try:
            from termtel.termtelwidgets.template_editor import WidgetTemplateEditor
            editor = WidgetTemplateEditor(self.widget_type, self.controller, self.theme_library, self.parent())
            editor.template_saved.connect(self._on_template_saved)
            editor.exec()
        except ImportError as e:
            QMessageBox.critical(self.parent(), "Import Error",
                                 f"Template editor not available: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self.parent(), "Error",
                                 f"Failed to open template editor: {str(e)}")

    def _on_template_saved(self, widget_type: str, platform: str, template_content: str):
        """Handle template save - refresh widget data"""
        print(f" Template saved for {widget_type} on platform {platform}")
        if hasattr(self, 'data_source_label'):
            self.data_source_label.setText("Template Updated")
            self.data_source_label.setStyleSheet("font-size: 10px; color: #00ffff; font-weight: bold;")
        if hasattr(self.controller, 'collect_telemetry_data'):
            QTimer.singleShot(1000, self.controller.collect_telemetry_data)


class EnhancedNeighborWidget(TemplateEditableWidget, QWidget):
    """Enhanced neighbor widget that handles both raw and normalized data"""

    def __init__(self, controller, theme_library=None, parent=None):
        QWidget.__init__(self, parent)
        TemplateEditableWidget.__init__(self, 'neighbor_widget', controller, theme_library)

        self.controller = controller
        self.theme_library = theme_library

        # Connect to both raw and normalized signals
        self.controller.raw_cdp_output.connect(self.process_raw_neighbor_output)
        self.controller.normalized_neighbors_ready.connect(self.update_with_normalized_data)
        self.controller.theme_changed.connect(self.on_theme_changed)

        self._setup_widget()
        self._current_data = []  # Store current data for theme updates

    def _setup_widget(self):
        """Setup the widget UI"""
        layout = QVBoxLayout(self)

        # Title with status indicator and gear button
        title_layout = QHBoxLayout()

        self.title_label = QLabel("CDP/LLDP NEIGHBORS")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(self.title_label)

        # Data source indicator
        self.data_source_label = QLabel("Raw")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #888888;")
        title_layout.addWidget(self.data_source_label)

        title_layout.addStretch()

        # Template editor gear button
        title_layout.addWidget(self.gear_button)

        # NEW: CSV Export button for Neighbors
        self._create_neighbor_export_button()
        title_layout.addWidget(self.export_button)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setMaximumWidth(80)
        self.refresh_button.clicked.connect(self._request_refresh)
        # title_layout.addWidget(self.refresh_button)

        layout.addLayout(title_layout)

        # Neighbor table with enhanced columns
        self.neighbors_table = QTableWidget(0, 7)
        self.neighbors_table.setHorizontalHeaderLabels([
            "Local Interface", "Neighbor Device", "Remote Interface",
            "IP Address", "Platform", "Protocol", "Capabilities"
        ])

        # Set column widths
        header = self.neighbors_table.horizontalHeader()
        header.setStretchLastSection(True)

        layout.addWidget(self.neighbors_table)

        # Status bar
        status_layout = QHBoxLayout()

        self.platform_label = QLabel("Platform: Unknown")
        self.platform_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.platform_label)

        status_layout.addStretch()

        self.count_label = QLabel("Neighbors: 0")
        self.count_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.count_label)

        layout.addLayout(status_layout)

    def _create_neighbor_export_button(self):
        """Create CSV export button for neighbor table"""
        self.export_button = QPushButton("Export CSV")
        self.export_button.setMaximumWidth(100)
        self.export_button.setToolTip("Export neighbor table to CSV file")
        self.export_button.clicked.connect(self._export_neighbors_to_csv)
        self.export_button.setEnabled(False)  # Disabled until we have data

        # Style to match your theme
        self.export_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border-color: #00ffff;
                color: #00ffff;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                border-color: #333333;
                color: #666666;
            }
        """)

    def _export_neighbors_to_csv(self):
        """Export current neighbor table data to CSV file"""
        try:
            # Check if we have data to export
            if self.neighbors_table.rowCount() == 0:
                QMessageBox.information(self, "Export Info", "No neighbor data to export")
                return

            # Get save location with timestamp
            default_filename = f"neighbors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Neighbor Table to CSV",
                default_filename,
                "CSV Files (*.csv);;All Files (*)"
            )

            if not filename:
                return

            # Write CSV file with metadata
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Write metadata as comments
                writer.writerow([f"# CDP/LLDP Neighbors Export"])
                writer.writerow([f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
                writer.writerow([f"# {self.platform_label.text()}"])
                writer.writerow([f"# Data Source: {self.data_source_label.text()}"])
                writer.writerow([f"# Total Neighbors: {self.neighbors_table.rowCount()}"])
                writer.writerow([])  # Empty row separator

                # Write headers
                headers = []
                for col in range(self.neighbors_table.columnCount()):
                    header_item = self.neighbors_table.horizontalHeaderItem(col)
                    headers.append(header_item.text() if header_item else f"Column {col}")
                writer.writerow(headers)

                # Write data rows
                for row in range(self.neighbors_table.rowCount()):
                    row_data = []
                    for col in range(self.neighbors_table.columnCount()):
                        item = self.neighbors_table.item(row, col)
                        cell_value = item.text() if item else ""
                        row_data.append(cell_value)
                    writer.writerow(row_data)

            # Success message
            QMessageBox.information(
                self,
                "Export Successful",
                f"Neighbor table exported successfully!\n\n"
                f"File: {os.path.basename(filename)}\n"
                f"Neighbors exported: {self.neighbors_table.rowCount()}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{str(e)}")

    @pyqtSlot(object)  # RawCommandOutput
    def process_raw_neighbor_output(self, raw_output):
        """Process raw neighbor output - fallback when templates fail"""
        self.platform_label.setText(f"Platform: {raw_output.platform} | Command: {raw_output.command}")
        self.data_source_label.setText("Raw")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #ff6600;")

        # Use basic parsing if normalized data isn't available
        if not raw_output.parsed_successfully:
            neighbors = self._parse_raw_output(raw_output)
            self._update_table_with_raw_data(neighbors)

    @pyqtSlot(list)  # List[NormalizedNeighborData]
    def update_with_normalized_data(self, normalized_neighbors):
        """Update widget with normalized neighbor data"""
        self.data_source_label.setText("Normalized")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #00ff00;")

        self._current_data = normalized_neighbors
        self._update_table_with_normalized_data(normalized_neighbors)
        self.count_label.setText(f"Neighbors: {len(normalized_neighbors)}")

        # NEW: Enable export button when we have data
        self.export_button.setEnabled(len(normalized_neighbors) > 0)

    def _update_table_with_normalized_data(self, neighbors: List[NormalizedNeighborData]):
        """Update table with normalized neighbor data"""
        self.neighbors_table.setRowCount(len(neighbors))

        for row, neighbor in enumerate(neighbors):
            # Set each column with proper data
            self.neighbors_table.setItem(row, 0, QTableWidgetItem(neighbor.local_interface))
            self.neighbors_table.setItem(row, 1, QTableWidgetItem(neighbor.neighbor_device))
            self.neighbors_table.setItem(row, 2, QTableWidgetItem(neighbor.neighbor_interface))
            self.neighbors_table.setItem(row, 3, QTableWidgetItem(neighbor.neighbor_ip))
            self.neighbors_table.setItem(row, 4, QTableWidgetItem(neighbor.neighbor_platform))
            self.neighbors_table.setItem(row, 5, QTableWidgetItem(neighbor.protocol_used))
            self.neighbors_table.setItem(row, 6, QTableWidgetItem(neighbor.neighbor_capability))

            # Color-code by protocol
            protocol_colors = {
                'CDP': '#00ff88',
                'LLDP': '#88aaff',
                '': '#ffffff'
            }

            protocol_color = protocol_colors.get(neighbor.protocol_used, '#ffffff')
            protocol_item = self.neighbors_table.item(row, 5)
            if protocol_item:
                protocol_item.setForeground(QColor(protocol_color))

        # Auto-resize columns
        self.neighbors_table.resizeColumnsToContents()

    def _update_table_with_raw_data(self, neighbors: List[Dict]):
        """Update table with raw parsed data (fallback)"""
        self.neighbors_table.setRowCount(len(neighbors))

        for row, neighbor in enumerate(neighbors):
            # Map raw data to table columns as best as possible
            self.neighbors_table.setItem(row, 0, QTableWidgetItem(neighbor.get('local_interface', 'Unknown')))
            self.neighbors_table.setItem(row, 1, QTableWidgetItem(
                neighbor.get('device_id', neighbor.get('neighbor', 'Unknown'))))
            self.neighbors_table.setItem(row, 2, QTableWidgetItem(
                neighbor.get('remote_interface', neighbor.get('neighbor_interface', 'Unknown'))))
            self.neighbors_table.setItem(row, 3, QTableWidgetItem(
                neighbor.get('ip_address', neighbor.get('neighbor_ip', 'Unknown'))))
            self.neighbors_table.setItem(row, 4, QTableWidgetItem(neighbor.get('platform', 'Unknown')))
            self.neighbors_table.setItem(row, 5, QTableWidgetItem('Raw'))
            self.neighbors_table.setItem(row, 6, QTableWidgetItem(neighbor.get('capabilities', 'Unknown')))

        self.count_label.setText(f"Neighbors: {len(neighbors)} (Raw)")
        self.neighbors_table.resizeColumnsToContents()

        # NEW: Enable export button for raw data too
        self.export_button.setEnabled(len(neighbors) > 0)

    def _parse_raw_output(self, raw_output) -> List[Dict]:
        """Basic parsing of raw output when templates fail"""
        # This is the same parsing logic from your original widget
        neighbors = []
        output = raw_output.output
        platform = raw_output.platform

        if platform.startswith('cisco') and 'cdp' in raw_output.command.lower():
            devices = output.split('-------------------------')
            for device_block in devices:
                if 'Device ID:' in device_block:
                    neighbor = self._parse_cisco_cdp_block(device_block)
                    if neighbor:
                        neighbors.append(neighbor)

        return neighbors

    def _parse_cisco_cdp_block(self, block: str) -> Optional[Dict]:
        """Parse individual Cisco CDP device block"""
        try:
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            neighbor = {}

            for line in lines:
                if line.startswith('Device ID:'):
                    neighbor['device_id'] = line.split('Device ID:')[1].strip()
                elif line.startswith('Interface:'):
                    parts = line.split(',')
                    neighbor['local_interface'] = parts[0].split('Interface:')[1].strip()
                    if 'Port ID' in parts[1]:
                        neighbor['remote_interface'] = parts[1].split('Port ID (outgoing port):')[1].strip()
                elif line.startswith('Platform:'):
                    neighbor['platform'] = line.split('Platform:')[1].split(',')[0].strip()
                elif 'IP address:' in line:
                    neighbor['ip_address'] = line.split('IP address:')[1].strip()

            if 'device_id' in neighbor:
                return neighbor
        except Exception as e:
            print(f"Error parsing CDP block: {e}")
        return None

    def _request_refresh(self):
        """Request data refresh"""
        if hasattr(self.controller, 'collect_telemetry_data'):
            self.controller.collect_telemetry_data()

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)

            # Reapply data-specific colors
            if self._current_data:
                self._update_table_with_normalized_data(self._current_data)


class EnhancedArpWidget(TemplateEditableWidget, QWidget):
    """Enhanced ARP widget that handles both raw and normalized data"""

    def __init__(self, controller, theme_library=None, parent=None):
        QWidget.__init__(self, parent)
        TemplateEditableWidget.__init__(self, 'arp_widget', controller, theme_library)

        self.controller = controller
        self.theme_library = theme_library

        # Connect to both raw and normalized signals
        self.controller.raw_arp_output.connect(self.process_raw_arp_output)
        self.controller.normalized_arp_ready.connect(self.update_with_normalized_data)
        self.controller.theme_changed.connect(self.on_theme_changed)

        self._setup_widget()
        self._current_data = []

    def _setup_widget(self):
        """Setup the widget UI"""
        layout = QVBoxLayout(self)

        # Title with indicators and gear button
        title_layout = QHBoxLayout()

        self.title_label = QLabel("ARP TABLE")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(self.title_label)

        self.data_source_label = QLabel("Raw")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #888888;")
        title_layout.addWidget(self.data_source_label)

        title_layout.addStretch()

        # Template editor gear button
        title_layout.addWidget(self.gear_button)

        # NEW: CSV Export button for ARP
        self._create_arp_export_button()
        title_layout.addWidget(self.export_button)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setMaximumWidth(80)
        self.refresh_button.clicked.connect(self._request_refresh)
        # title_layout.addWidget(self.refresh_button)

        layout.addLayout(title_layout)

        # ARP table with enhanced columns
        self.arp_table = QTableWidget(0, 6)
        self.arp_table.setHorizontalHeaderLabels([
            "IP Address", "MAC Address", "Interface", "Age", "Type", "State"
        ])

        layout.addWidget(self.arp_table)

        # Status bar
        status_layout = QHBoxLayout()

        self.platform_label = QLabel("Platform: Unknown")
        self.platform_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.platform_label)

        status_layout.addStretch()

        self.count_label = QLabel("Entries: 0")
        self.count_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.count_label)

        layout.addLayout(status_layout)

    def _create_arp_export_button(self):
        """Create CSV export button for ARP table"""
        self.export_button = QPushButton("Export CSV")
        self.export_button.setMaximumWidth(100)
        self.export_button.setToolTip("Export ARP table to CSV file")
        self.export_button.clicked.connect(self._export_arp_to_csv)
        self.export_button.setEnabled(False)  # Disabled until we have data

        # Style to match your theme
        self.export_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border-color: #00ffff;
                color: #00ffff;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                border-color: #333333;
                color: #666666;
            }
        """)

    def _export_arp_to_csv(self):
        """Export current ARP table data to CSV file"""
        try:
            # Check if we have data to export
            if self.arp_table.rowCount() == 0:
                QMessageBox.information(self, "Export Info", "No ARP data to export")
                return

            # Get save location with timestamp
            default_filename = f"arp_table_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export ARP Table to CSV",
                default_filename,
                "CSV Files (*.csv);;All Files (*)"
            )

            if not filename:
                return

            # Write CSV file with metadata
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Write metadata as comments
                writer.writerow([f"# ARP Table Export"])
                writer.writerow([f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
                writer.writerow([f"# {self.platform_label.text()}"])
                writer.writerow([f"# Data Source: {self.data_source_label.text()}"])
                writer.writerow([f"# Total Entries: {self.arp_table.rowCount()}"])
                writer.writerow([])  # Empty row separator

                # Write headers
                headers = []
                for col in range(self.arp_table.columnCount()):
                    header_item = self.arp_table.horizontalHeaderItem(col)
                    headers.append(header_item.text() if header_item else f"Column {col}")
                writer.writerow(headers)

                # Write data rows
                for row in range(self.arp_table.rowCount()):
                    row_data = []
                    for col in range(self.arp_table.columnCount()):
                        item = self.arp_table.item(row, col)
                        cell_value = item.text() if item else ""
                        row_data.append(cell_value)
                    writer.writerow(row_data)

            # Success message
            QMessageBox.information(
                self,
                "Export Successful",
                f"ARP table exported successfully!\n\n"
                f"File: {os.path.basename(filename)}\n"
                f"Entries exported: {self.arp_table.rowCount()}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{str(e)}")
    @pyqtSlot(object)  # RawCommandOutput
    def process_raw_arp_output(self, raw_output):
        """Process raw ARP output"""
        self.platform_label.setText(f"Platform: {raw_output.platform} | Command: {raw_output.command}")
        self.data_source_label.setText("Raw")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #ff6600;")

        if not raw_output.parsed_successfully:
            arp_entries = self._parse_raw_arp_output(raw_output)
            self._update_table_with_raw_data(arp_entries)

    @pyqtSlot(list)  # List[NormalizedArpData]
    def update_with_normalized_data(self, normalized_arp):
        """Update widget with normalized ARP data"""
        self.data_source_label.setText("Normalized")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #00ff00;")

        self._current_data = normalized_arp
        self._update_table_with_normalized_data(normalized_arp)
        self.count_label.setText(f"Entries: {len(normalized_arp)}")

        # NEW: Enable export button when we have data
        self.export_button.setEnabled(len(normalized_arp) > 0)

    def _update_table_with_normalized_data(self, arp_entries: List[NormalizedArpData]):
        """Update table with normalized ARP data"""
        self.arp_table.setRowCount(len(arp_entries))

        for row, entry in enumerate(arp_entries):
            self.arp_table.setItem(row, 0, QTableWidgetItem(entry.ip_address))
            self.arp_table.setItem(row, 1, QTableWidgetItem(entry.mac_address))
            self.arp_table.setItem(row, 2, QTableWidgetItem(entry.interface))
            self.arp_table.setItem(row, 3, QTableWidgetItem(entry.age))
            self.arp_table.setItem(row, 4, QTableWidgetItem(entry.type))
            self.arp_table.setItem(row, 5, QTableWidgetItem(entry.state))

            # Color-code by state
            state_colors = {
                'Active': '#00ff00',
                'Incomplete': '#ffff00',
                'REACHABLE': '#00ff00',
                'STALE': '#ff6600'
            }

            state_color = state_colors.get(entry.state, '#ffffff')
            state_item = self.arp_table.item(row, 5)
            if state_item:
                state_item.setForeground(QColor(state_color))

        self.arp_table.resizeColumnsToContents()

    def _update_table_with_raw_data(self, entries: List[Dict]):
        """Update table with raw parsed data"""
        self.arp_table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            self.arp_table.setItem(row, 0, QTableWidgetItem(entry.get('ip', entry.get('ip_address', 'Unknown'))))
            self.arp_table.setItem(row, 1, QTableWidgetItem(entry.get('mac', entry.get('mac_address', 'Unknown'))))
            self.arp_table.setItem(row, 2, QTableWidgetItem(entry.get('interface', 'Unknown')))
            self.arp_table.setItem(row, 3, QTableWidgetItem(entry.get('age', '')))
            self.arp_table.setItem(row, 4, QTableWidgetItem(entry.get('type', '')))
            self.arp_table.setItem(row, 5, QTableWidgetItem(entry.get('state', '')))

        self.count_label.setText(f"Entries: {len(entries)} (Raw)")
        self.arp_table.resizeColumnsToContents()

        # NEW: Enable export button for raw data too
        self.export_button.setEnabled(len(entries) > 0)

    def _parse_raw_arp_output(self, raw_output) -> List[Dict]:
        """Parse raw ARP output when templates fail"""
        entries = []
        output = raw_output.output
        platform = raw_output.platform

        if platform.startswith('cisco'):
            lines = output.split('\n')
            for line in lines:
                if 'Internet' in line and 'ARPA' in line:
                    parts = line.split()
                    if len(parts) >= 6:
                        entries.append({
                            'ip': parts[1],
                            'mac': parts[3],
                            'interface': parts[5],
                            'age': parts[2] if parts[2].isdigit() else '',
                            'type': 'ARPA'
                        })

        elif platform.startswith('linux'):
            lines = output.split('\n')
            for line in lines:
                if 'lladdr' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        entries.append({
                            'ip': parts[0],
                            'mac': parts[4],
                            'interface': parts[2],
                            'state': parts[5] if len(parts) > 5 else ''
                        })

        return entries

    def _request_refresh(self):
        """Request data refresh"""
        if hasattr(self.controller, 'collect_telemetry_data'):
            self.controller.collect_telemetry_data()

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)

            if self._current_data:
                self._update_table_with_normalized_data(self._current_data)


class FixedRouteWidget(TemplateEditableWidget, QWidget):
    """
    Drop-in replacement for the existing FixedRouteWidget with CSV export functionality
    Maintains all existing functionality while adding export capability
    """

    def __init__(self, controller, theme_library=None, parent=None):
        QWidget.__init__(self, parent)
        TemplateEditableWidget.__init__(self, 'route_widget', controller, theme_library)

        self.controller = controller
        self.theme_library = theme_library
        self.current_platform = None

        # Connect to controller signals
        self._connect_controller_signals()

        self.available_vrfs = ["default"]
        self._current_data = []
        self._available_protocols = set()  # Track available protocols
        self._setup_widget()

    def _connect_controller_signals(self):
        """Connect to controller signals"""

        # Route data signals
        route_signal_names = [
            'normalized_routes_ready',
            'route_table_ready',
            'routes_ready'
        ]

        for signal_name in route_signal_names:
            try:
                signal = getattr(self.controller, signal_name)
                signal.connect(self.update_with_normalized_data)
                print(f" Connected to {signal_name}")
                break  # Only connect to the first one found
            except AttributeError:
                continue

        # Other signals
        other_signals = [
            ('raw_route_output', self.process_raw_route_output),
            ('raw_vrf_list_output', self.process_vrf_list_output),
            ('theme_changed', self.on_theme_changed),
            ('connection_status_changed', self._on_connection_status_changed),
            ('device_info_updated', self._on_device_info_updated)
        ]

        for signal_name, slot_method in other_signals:
            try:
                signal = getattr(self.controller, signal_name)
                signal.connect(slot_method)
                print(f" Connected to {signal_name}")
            except AttributeError:
                pass

    def _setup_widget(self):
        """Setup the widget UI with export functionality"""
        layout = QVBoxLayout(self)

        # Title and controls with gear button and export button
        title_layout = QHBoxLayout()

        self.title_label = QLabel("ROUTE TABLE")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(self.title_label)

        self.data_source_label = QLabel("Waiting...")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #888888;")
        title_layout.addWidget(self.data_source_label)

        title_layout.addStretch()

        # Template editor gear button
        title_layout.addWidget(self.gear_button)

        # NEW: CSV Export button
        self._create_export_button()
        title_layout.addWidget(self.export_button)

        layout.addLayout(title_layout)

        # VRF and controls
        controls_layout = QHBoxLayout()

        vrf_label = QLabel("VRF:")
        controls_layout.addWidget(vrf_label)

        self.vrf_combo = QComboBox()
        self.vrf_combo.addItems(self.available_vrfs)
        self.vrf_combo.currentTextChanged.connect(self.on_vrf_changed)
        controls_layout.addWidget(self.vrf_combo)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_route_table)
        # controls_layout.addWidget(self.refresh_button)

        # Filter controls - FIXED: Initialize properly
        self.protocol_filter = QComboBox()
        self.protocol_filter.addItem("All Protocols")
        self.protocol_filter.currentTextChanged.connect(self._apply_filters)
        controls_layout.addWidget(self.protocol_filter)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # Route table
        self.route_table = QTableWidget(0, 8)
        self.route_table.setHorizontalHeaderLabels([
            "Network", "Mask", "Next Hop", "Interface", "Protocol",
            "Metric", "Admin Dist", "Age"
        ])
        layout.addWidget(self.route_table)

        # Status bar
        status_layout = QHBoxLayout()

        self.platform_label = QLabel("Platform: Unknown")
        self.platform_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.platform_label)

        status_layout.addStretch()

        self.count_label = QLabel("Routes: 0")
        self.count_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.count_label)

        self.selected_vrf_label = QLabel("VRF: default")
        self.selected_vrf_label.setStyleSheet("font-size: 10px; color: #00ffff;")
        status_layout.addWidget(self.selected_vrf_label)

        layout.addLayout(status_layout)

    # NEW EXPORT FUNCTIONALITY
    def _create_export_button(self):
        """Create CSV export button"""
        self.export_button = QPushButton("Export CSV")
        self.export_button.setMaximumWidth(100)
        self.export_button.setToolTip("Export route table to CSV file")
        self.export_button.clicked.connect(self._export_to_csv)
        self.export_button.setEnabled(False)  # Disabled until we have data

        # Style to match your theme
        self.export_button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border-color: #00ffff;
                color: #00ffff;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                border-color: #333333;
                color: #666666;
            }
        """)

    def _export_to_csv(self):
        """Export current route table data to CSV file"""
        try:
            # Check if we have data to export
            if self.route_table.rowCount() == 0:
                QMessageBox.information(self, "Export Info", "No route data to export")
                return

            # Get save location with timestamp
            default_filename = f"route_table_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Route Table to CSV",
                default_filename,
                "CSV Files (*.csv);;All Files (*)"
            )

            if not filename:
                return

            # Write CSV file with metadata
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Write metadata as comments
                writer.writerow([f"# Route Table Export"])
                writer.writerow([f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
                writer.writerow([f"# {self.platform_label.text()}"])
                writer.writerow([f"# VRF: {self.vrf_combo.currentText()}"])
                writer.writerow([f"# Protocol Filter: {self.protocol_filter.currentText()}"])
                writer.writerow([f"# Data Source: {self.data_source_label.text()}"])
                writer.writerow([f"# Total Routes Displayed: {self.route_table.rowCount()}"])
                writer.writerow([])  # Empty row separator

                # Write headers
                headers = []
                for col in range(self.route_table.columnCount()):
                    header_item = self.route_table.horizontalHeaderItem(col)
                    headers.append(header_item.text() if header_item else f"Column {col}")
                writer.writerow(headers)

                # Write data rows
                for row in range(self.route_table.rowCount()):
                    row_data = []
                    for col in range(self.route_table.columnCount()):
                        item = self.route_table.item(row, col)
                        cell_value = item.text() if item else ""
                        row_data.append(cell_value)
                    writer.writerow(row_data)

            # Success message
            QMessageBox.information(
                self,
                "Export Successful",
                f"Route table exported successfully!\n\n"
                f"File: {os.path.basename(filename)}\n"
                f"Routes exported: {self.route_table.rowCount()}\n"
                f"VRF: {self.vrf_combo.currentText()}\n"
                f"Filter: {self.protocol_filter.currentText()}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{str(e)}")

    # EXISTING FUNCTIONALITY (maintained exactly as before)
    @pyqtSlot(str, str)
    def _on_connection_status_changed(self, device_ip, status):
        """Handle connection status changes"""
        if status == "connected":
            if hasattr(self.controller, 'current_platform'):
                self.current_platform = self.controller.current_platform
                self.platform_label.setText(f"Platform: {self.current_platform}")
        elif status == "disconnected":
            self.current_platform = None
            self.platform_label.setText("Platform: Disconnected")
            # NEW: Disable export when disconnected
            self.export_button.setEnabled(False)

    @pyqtSlot(object)
    def _on_device_info_updated(self, device_info):
        """Handle device info updates"""
        if hasattr(device_info, 'platform'):
            self.current_platform = device_info.platform
            self.platform_label.setText(f"Platform: {self.current_platform}")

    @pyqtSlot(object)
    def process_raw_route_output(self, raw_output):
        """Process raw route output"""
        print(f" Processing raw route output: {raw_output.command}")
        self.platform_label.setText(f"Platform: {raw_output.platform} | Command: {raw_output.command}")
        self.data_source_label.setText("Raw")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #ff6600;")

    @pyqtSlot(object)
    def process_vrf_list_output(self, raw_output):
        """Process VRF list output"""
        print(f" Processing VRF list output: {raw_output.command}")

    @pyqtSlot(list)
    def update_with_normalized_data(self, normalized_routes):
        """Update widget with normalized route data - FIXED VERSION"""
        print(f"\n Normalized route data received: {len(normalized_routes)} routes")

        # Update the UI to show we received normalized data
        self.data_source_label.setText("Normalized")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #00ff00; font-weight: bold;")

        self._current_data = normalized_routes

        # FIXED: Update protocol filter BEFORE applying filters
        self._update_protocol_filter(normalized_routes)

        # FIXED: Update table (this will apply current filter)
        self._update_table_with_normalized_data(normalized_routes)

        # Update count
        self.count_label.setText(f"Routes: {len(normalized_routes)}")

        # NEW: Enable export button when we have data
        self.export_button.setEnabled(len(normalized_routes) > 0)

        # Debug: Print available protocols
        protocols = set()
        for route in normalized_routes:
            if route.protocol:
                protocols.add(route.protocol)
        print(f" Available protocols: {sorted(protocols)}")

    def _update_table_with_normalized_data(self, routes):
        """Update table with normalized route data - FIXED FILTERING"""
        print(f" Updating route table with {len(routes)} routes")

        # FIXED: Apply current filter properly
        filtered_routes = self._apply_current_filter(routes)
        print(f" After filtering: {len(filtered_routes)} routes")
        print(f" Current filter: '{self.protocol_filter.currentText()}'")

        self.route_table.setRowCount(len(filtered_routes))

        for row, route in enumerate(filtered_routes):
            self.route_table.setItem(row, 0, QTableWidgetItem(route.network))
            self.route_table.setItem(row, 1, QTableWidgetItem(route.mask))
            self.route_table.setItem(row, 2, QTableWidgetItem(route.next_hop))
            self.route_table.setItem(row, 3, QTableWidgetItem(route.interface))
            self.route_table.setItem(row, 4, QTableWidgetItem(route.protocol))
            self.route_table.setItem(row, 5, QTableWidgetItem(route.metric))
            self.route_table.setItem(row, 6, QTableWidgetItem(route.admin_distance))
            self.route_table.setItem(row, 7, QTableWidgetItem(route.age))

            # Color-code by protocol
            protocol_colors = {
                'Static': '#ffff00',
                'Connected': '#00ff00',
                'Local': '#00ff88',
                'OSPF': '#ff8800',
                'BGP': '#ff0088',
                'EIGRP': '#8800ff',
                'RIP': '#0088ff'
            }

            protocol_color = protocol_colors.get(route.protocol, '#ffffff')
            protocol_item = self.route_table.item(row, 4)
            if protocol_item:
                protocol_item.setForeground(QColor(protocol_color))

        self.route_table.resizeColumnsToContents()

        # NEW: Update export button state based on filtered data
        self.export_button.setEnabled(len(filtered_routes) > 0)

        print(f" Route table updated successfully")

    def _update_protocol_filter(self, routes):
        """Update protocol filter dropdown - FIXED VERSION"""
        print(f" Updating protocol filter...")

        # Get all unique protocols from routes
        protocols = set(['All Protocols'])
        for route in routes:
            if route.protocol and route.protocol.strip():
                protocols.add(route.protocol)

        print(f" Found protocols: {sorted(protocols)}")

        # Store current selection
        current_filter = self.protocol_filter.currentText()
        print(f" Current filter: '{current_filter}'")

        # FIXED: Temporarily disconnect signal to avoid triggering filter during update
        self.protocol_filter.currentTextChanged.disconnect()

        # Clear and repopulate
        self.protocol_filter.clear()
        sorted_protocols = sorted(list(protocols))
        self.protocol_filter.addItems(sorted_protocols)

        # Restore selection if it still exists, otherwise default to "All Protocols"
        if current_filter in protocols:
            self.protocol_filter.setCurrentText(current_filter)
            print(f" Restored filter: '{current_filter}'")
        else:
            self.protocol_filter.setCurrentText("All Protocols")
            print(f" Reset filter to: 'All Protocols'")

        # Reconnect signal
        self.protocol_filter.currentTextChanged.connect(self._apply_filters)

        # Store available protocols for filtering
        self._available_protocols = protocols

    def _apply_current_filter(self, routes):
        """Apply current protocol filter to routes - FIXED VERSION"""
        current_filter = self.protocol_filter.currentText()
        print(f" Applying filter: '{current_filter}' to {len(routes)} routes")

        if current_filter == "All Protocols":
            print(f" No filter applied, returning all {len(routes)} routes")
            return routes

        filtered_routes = []
        for route in routes:
            if route.protocol == current_filter:
                filtered_routes.append(route)

        print(f" Filter '{current_filter}' matched {len(filtered_routes)} routes")

        # Debug: Show what protocols we actually have
        actual_protocols = set()
        for route in routes:
            actual_protocols.add(route.protocol)
        print(f" Actual protocols in data: {sorted(actual_protocols)}")

        return filtered_routes

    def _apply_filters(self):
        """Apply filters to current data - triggered by filter change"""
        print(f" Filter changed, reapplying to {len(self._current_data)} routes...")
        if self._current_data:
            self._update_table_with_normalized_data(self._current_data)

    @pyqtSlot(str)
    def on_vrf_changed(self, vrf_name: str):
        """Handle VRF selection change"""
        print(f" VRF changed to: {vrf_name}")
        self.selected_vrf_label.setText(f"VRF: {vrf_name}")

    def refresh_route_table(self):
        """Refresh route table"""
        print(f" Refresh button clicked")
        if hasattr(self.controller, 'collect_telemetry_data'):
            self.controller.collect_telemetry_data()

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)
            if self._current_data:
                self._update_table_with_normalized_data(self._current_data)


class EnhancedRouteWidget(TemplateEditableWidget, QWidget):
    """Enhanced route widget with VRF support and normalized data handling"""

    def __init__(self, controller, theme_library=None, parent=None):
        QWidget.__init__(self, parent)
        TemplateEditableWidget.__init__(self, 'route_widget', controller, theme_library)

        self.controller = controller
        self.theme_library = theme_library

        # Connect to signals
        self.controller.raw_route_output.connect(self.process_raw_route_output)
        self.controller.raw_vrf_list_output.connect(self.process_vrf_list_output)
        self.controller.normalized_routes_ready.connect(self.update_with_normalized_data)
        self.controller.theme_changed.connect(self.on_theme_changed)

        self.available_vrfs = ["default"]
        self._current_data = []
        self._setup_widget()

    def _setup_widget(self):
        """Setup the widget UI"""
        layout = QVBoxLayout(self)

        # Title and controls with gear button
        title_layout = QHBoxLayout()

        self.title_label = QLabel("ROUTE TABLE")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(self.title_label)

        self.data_source_label = QLabel("Raw")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #888888;")
        title_layout.addWidget(self.data_source_label)

        title_layout.addStretch()

        # Template editor gear button
        title_layout.addWidget(self.gear_button)

        layout.addLayout(title_layout)

        # VRF and controls
        controls_layout = QHBoxLayout()

        vrf_label = QLabel("VRF:")
        controls_layout.addWidget(vrf_label)

        self.vrf_combo = QComboBox()
        self.vrf_combo.addItems(self.available_vrfs)
        self.vrf_combo.currentTextChanged.connect(self.on_vrf_changed)
        controls_layout.addWidget(self.vrf_combo)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_route_table)
        # controls_layout.addWidget(self.refresh_button)

        # Filter controls
        self.protocol_filter = QComboBox()
        self.protocol_filter.addItem("All Protocols")
        self.protocol_filter.currentTextChanged.connect(self._apply_filters)
        controls_layout.addWidget(self.protocol_filter)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # Route table with enhanced columns
        self.route_table = QTableWidget(0, 8)
        self.route_table.setHorizontalHeaderLabels([
            "Network", "Mask", "Next Hop", "Interface", "Protocol",
            "Metric", "Admin Dist", "Age"
        ])

        layout.addWidget(self.route_table)

        # Status bar
        status_layout = QHBoxLayout()

        self.platform_label = QLabel("Platform: Unknown")
        self.platform_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.platform_label)

        status_layout.addStretch()

        self.count_label = QLabel("Routes: 0")
        self.count_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.count_label)

        self.selected_vrf_label = QLabel("VRF: default")
        self.selected_vrf_label.setStyleSheet("font-size: 10px; color: #00ffff;")
        status_layout.addWidget(self.selected_vrf_label)

        layout.addLayout(status_layout)

    @pyqtSlot(object)  # RawCommandOutput
    def process_vrf_list_output(self, raw_output):
        """Process VRF list output and populate dropdown"""
        vrfs = self._parse_vrf_list(raw_output)
        self.available_vrfs = vrfs

        current_selection = self.vrf_combo.currentText()
        self.vrf_combo.clear()
        self.vrf_combo.addItems(self.available_vrfs)

        if current_selection in self.available_vrfs:
            self.vrf_combo.setCurrentText(current_selection)

    @pyqtSlot(object)  # RawCommandOutput
    def process_raw_route_output(self, raw_output):
        """Process raw route output"""
        self.platform_label.setText(f"Platform: {raw_output.platform} | Command: {raw_output.command}")
        self.data_source_label.setText("Raw")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #ff6600;")

        if not raw_output.parsed_successfully:
            routes = self._parse_raw_route_output(raw_output)
            self._update_table_with_raw_data(routes)

    @pyqtSlot(list)  # List[NormalizedRouteData]
    def update_with_normalized_data(self, normalized_routes):
        """Update widget with normalized route data"""
        self.data_source_label.setText("Normalized")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #00ff00;")

        self._current_data = normalized_routes
        self._update_table_with_normalized_data(normalized_routes)
        self._update_protocol_filter(normalized_routes)
        self.count_label.setText(f"Routes: {len(normalized_routes)}")

    # In normalized_widgets.py, update the protocol_colors in FixedRouteWidget._update_table_with_normalized_data:

    def _update_table_with_normalized_data(self, routes):
        """Update table with normalized route data - FIXED FILTERING"""
        print(f" Updating route table with {len(routes)} routes")

        # Apply current filter properly
        filtered_routes = self._apply_current_filter(routes)
        print(f" After filtering: {len(filtered_routes)} routes")

        # DEBUG: Show what protocols we're getting
        if filtered_routes:
            protocols_in_data = set()
            for route in filtered_routes[:5]:  # First 5 routes
                protocols_in_data.add(route.protocol)
                print(f"  Route: {route.network} via {route.next_hop} ({route.protocol})")
            print(f" Protocols in filtered data: {sorted(protocols_in_data)}")

        self.route_table.setRowCount(len(filtered_routes))

        for row, route in enumerate(filtered_routes):
            self.route_table.setItem(row, 0, QTableWidgetItem(route.network))
            self.route_table.setItem(row, 1, QTableWidgetItem(route.mask))
            self.route_table.setItem(row, 2, QTableWidgetItem(route.next_hop))
            self.route_table.setItem(row, 3, QTableWidgetItem(route.interface))
            self.route_table.setItem(row, 4, QTableWidgetItem(route.protocol))
            self.route_table.setItem(row, 5, QTableWidgetItem(route.metric))
            self.route_table.setItem(row, 6, QTableWidgetItem(route.admin_distance))
            self.route_table.setItem(row, 7, QTableWidgetItem(route.age))

            # ENHANCED: Color-code by protocol - EXACT SAME AS TEMPLATE EDITOR
            protocol_colors = {
                # Static routes
                'Static': '#ffff00',
                'Static Default': '#ffff00',

                # Connected/Local
                'Connected': '#00ff00',
                'Local': '#00ff88',

                # OSPF variants
                'OSPF': '#ff8800',
                'OSPF Inter-Area': '#ff8800',
                'OSPF External': '#ff8800',
                'OSPF NSSA': '#ff8800',

                # BGP variants
                'BGP': '#ff0088',
                'BGP Internal': '#ff0088',
                'BGP External': '#ff0088',
                'B E': '#ff0088',

                # Other protocols
                'EIGRP': '#8800ff',
                'RIP': '#0088ff',
                'ISIS': '#00ffff',
                'ISIS Level-1': '#00ffff',
                'ISIS Level-2': '#00ffff',
                'Kernel': '#888888',
                'Mobile': '#ff8888',
                'IGRP': '#8888ff',
                'NAT': '#ff88ff'
            }

            protocol_color = protocol_colors.get(route.protocol, '#ffffff')
            protocol_item = self.route_table.item(row, 4)
            if protocol_item:
                protocol_item.setForeground(QColor(protocol_color))
                # DEBUG: Show coloring for first few rows
                if row < 3:
                    print(f"  Row {row}: Protocol '{route.protocol}' -> Color {protocol_color}")

        self.route_table.resizeColumnsToContents()


        print(f" Route table updated successfully")
    def _update_table_with_raw_data(self, routes: List[Dict]):
        """Update table with raw parsed data"""
        self.route_table.setRowCount(len(routes))

        for row, route in enumerate(routes):
            self.route_table.setItem(row, 0, QTableWidgetItem(route.get('network', 'Unknown')))
            self.route_table.setItem(row, 1, QTableWidgetItem(route.get('mask', '')))
            self.route_table.setItem(row, 2, QTableWidgetItem(route.get('next_hop', 'Unknown')))
            self.route_table.setItem(row, 3, QTableWidgetItem(route.get('interface', 'Unknown')))
            self.route_table.setItem(row, 4, QTableWidgetItem(route.get('protocol', 'Unknown')))
            self.route_table.setItem(row, 5, QTableWidgetItem(route.get('metric', '')))
            self.route_table.setItem(row, 6, QTableWidgetItem(route.get('admin_distance', '')))
            self.route_table.setItem(row, 7, QTableWidgetItem(route.get('age', '')))

        self.count_label.setText(f"Routes: {len(routes)} (Raw)")
        self.route_table.resizeColumnsToContents()

    def _update_protocol_filter(self, routes: List[NormalizedRouteData]):
        """Update protocol filter dropdown with available protocols"""
        protocols = set(['All Protocols'])
        for route in routes:
            if route.protocol:
                protocols.add(route.protocol)

        current_filter = self.protocol_filter.currentText()
        self.protocol_filter.clear()
        self.protocol_filter.addItems(sorted(list(protocols)))

        if current_filter in protocols:
            self.protocol_filter.setCurrentText(current_filter)

    def _apply_current_filter(self, routes: List[NormalizedRouteData]) -> List[NormalizedRouteData]:
        """Apply current protocol filter to routes"""
        current_filter = self.protocol_filter.currentText()

        if current_filter == "All Protocols":
            return routes

        return [route for route in routes if route.protocol == current_filter]

    def _apply_filters(self):
        """Apply filters to current data"""
        if self._current_data:
            self._update_table_with_normalized_data(self._current_data)

    def _parse_vrf_list(self, raw_output) -> List[str]:
        """Parse VRF list from platform output"""
        vrfs = ["default"]
        output = raw_output.output
        platform = raw_output.platform

        try:
            if platform.startswith('cisco'):
                lines = output.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('Name') and not line.startswith('---'):
                        parts = line.split()
                        if parts and parts[0] not in ['<not', 'Name']:
                            vrf_name = parts[0]
                            if vrf_name not in vrfs:
                                vrfs.append(vrf_name)

            elif platform.startswith('linux'):
                lines = output.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and line not in ['default', 'local', 'main']:
                        vrfs.append(line)

        except Exception as e:
            print(f"Error parsing VRF list: {e}")

        return sorted(vrfs)

    def _parse_raw_route_output(self, raw_output) -> List[Dict]:
        """Parse raw route output when templates fail"""
        routes = []
        output = raw_output.output
        platform = raw_output.platform

        try:
            if platform.startswith('cisco'):
                routes = self._parse_cisco_routes(output)
            elif platform.startswith('linux'):
                routes = self._parse_linux_routes(output)
        except Exception as e:
            print(f"Error parsing route table: {e}")

        return routes

    def _parse_cisco_routes(self, output: str) -> List[Dict]:
        """Parse Cisco route table format"""
        routes = []
        lines = output.split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('Codes:') or line.startswith('Gateway'):
                continue

            if any(line.startswith(code) for code in ['S*', 'S ', 'C ', 'L ', 'O ', 'B ', 'D ', 'R ']):
                route = self._parse_cisco_route_line(line)
                if route:
                    routes.append(route)

        return routes

    def _parse_cisco_route_line(self, line: str) -> Optional[Dict]:
        """Parse individual Cisco route line"""
        try:
            parts = line.split()
            if len(parts) < 2:
                return None

            route_code = parts[0]
            network = parts[1]

            protocol_map = {
                'S': 'Static', 'C': 'Connected', 'L': 'Local',
                'O': 'OSPF', 'B': 'BGP', 'D': 'EIGRP', 'R': 'RIP'
            }
            protocol = protocol_map.get(route_code[0], route_code)

            next_hop = "Directly Connected"
            interface = ""
            metric = ""
            admin_distance = ""

            if "via" in line:
                via_idx = line.find("via")
                next_hop_part = line[via_idx + 3:].split(',')[0].strip()
                next_hop = next_hop_part.split()[0] if next_hop_part.split() else next_hop

            if "directly connected" in line.lower():
                if ',' in line:
                    interface = line.split(',')[-1].strip()

            import re
            metric_match = re.search(r'\[(\d+)/(\d+)\]', line)
            if metric_match:
                admin_distance = metric_match.group(1)
                metric = metric_match.group(2)

            return {
                'network': network,
                'next_hop': next_hop,
                'interface': interface,
                'protocol': protocol,
                'metric': metric,
                'admin_distance': admin_distance
            }

        except Exception as e:
            print(f"Error parsing route line '{line}': {e}")
            return None

    def _parse_linux_routes(self, output: str) -> List[Dict]:
        """Parse Linux route table format"""
        routes = []
        lines = output.split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            route = self._parse_linux_route_line(line)
            if route:
                routes.append(route)

        return routes

    def _parse_linux_route_line(self, line: str) -> Optional[Dict]:
        """Parse individual Linux route line"""
        try:
            parts = line.split()
            if len(parts) < 2:
                return None

            network = parts[0]
            if network == "default":
                network = "0.0.0.0/0"

            next_hop = "Directly Connected"
            interface = ""
            protocol = ""
            metric = ""

            i = 1
            while i < len(parts):
                if parts[i] == "via" and i + 1 < len(parts):
                    next_hop = parts[i + 1]
                    i += 2
                elif parts[i] == "dev" and i + 1 < len(parts):
                    interface = parts[i + 1]
                    i += 2
                elif parts[i] == "proto" and i + 1 < len(parts):
                    protocol = parts[i + 1]
                    i += 2
                elif parts[i] == "metric" and i + 1 < len(parts):
                    metric = parts[i + 1]
                    i += 2
                else:
                    i += 1

            return {
                'network': network,
                'next_hop': next_hop,
                'interface': interface,
                'protocol': protocol.title() if protocol else "Unknown",
                'metric': metric,
                'admin_distance': ""
            }

        except Exception as e:
            print(f"Error parsing Linux route line '{line}': {e}")
            return None

    @pyqtSlot(str)
    def on_vrf_changed(self, vrf_name: str):
        """Handle VRF selection change"""
        self.selected_vrf_label.setText(f"VRF: {vrf_name}")
        self.refresh_route_table()

    def refresh_route_table(self):
        """Refresh route table for selected VRF"""
        selected_vrf = self.vrf_combo.currentText()
        if hasattr(self.controller, 'get_route_table_for_vrf'):
            self.controller.get_route_table_for_vrf(selected_vrf)

    def _request_refresh(self):
        """Request data refresh"""
        self.refresh_route_table()

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)

            if self._current_data:
                self._update_table_with_normalized_data(self._current_data)


class ConnectionStatusWidget(QWidget):
    """Widget to display connection status and device information"""

    def __init__(self, controller, theme_library=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.theme_library = theme_library

        # Connect to signals
        self.controller.device_info_updated.connect(self.update_device_info)
        self.controller.connection_status_changed.connect(self.update_connection_status)
        self.controller.theme_changed.connect(self.on_theme_changed)

        self._setup_widget()

    def _setup_widget(self):
        """Setup the widget UI"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("CONNECTION STATUS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        layout.addWidget(title)

        # Status indicator
        self.status_indicator = QLabel("")
        self.status_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_indicator.setStyleSheet("font-size: 24px; color: #ff4400;")
        layout.addWidget(self.status_indicator)

        self.status_text = QLabel("Disconnected")
        self.status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_text.setStyleSheet("font-weight: bold; color: #ff4400;")
        layout.addWidget(self.status_text)

        # Device information
        self.device_info_display = QTextEdit()
        self.device_info_display.setMaximumHeight(200)
        self.device_info_display.setReadOnly(True)
        layout.addWidget(self.device_info_display)

        # Data collection status
        self.data_status = QLabel("Data Collection: Stopped")
        self.data_status.setStyleSheet("font-size: 10px; color: #888888;")
        layout.addWidget(self.data_status)

    @pyqtSlot(object)  # DeviceInfo
    def update_device_info(self, device_info):
        """Update device information display"""
        info_text = f"""Device Information:

Hostname: {device_info.hostname}
IP Address: {device_info.ip_address}
Platform: {device_info.platform}
Model: {device_info.model}
Version: {device_info.version}
Serial: {device_info.serial}
Uptime: {device_info.uptime}

Connection: {device_info.connection_status}
"""
        self.device_info_display.setPlainText(info_text)

        if device_info.connection_status == "connected":
            self.data_status.setText("Data Collection: Active")
            self.data_status.setStyleSheet("font-size: 10px; color: #00ff00;")
        else:
            self.data_status.setText("Data Collection: Stopped")
            self.data_status.setStyleSheet("font-size: 10px; color: #ff4400;")

    @pyqtSlot(str, str)
    def update_connection_status(self, device_ip, status):
        """Update connection status indicator"""
        status_colors = {
            "connected": "#00ff00",
            "connecting": "#ffff00",
            "disconnected": "#888888",
            "failed": "#ff4400"
        }

        color = status_colors.get(status, "#888888")
        self.status_indicator.setStyleSheet(f"font-size: 24px; color: {color};")
        self.status_text.setText(status.title())
        self.status_text.setStyleSheet(f"font-weight: bold; color: {color};")

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)


# System Information Widget with Template Editor Support
class EnhancedSystemWidget(TemplateEditableWidget, QWidget):
    """Enhanced system information widget with template editing capability"""

    def __init__(self, controller, theme_library=None, parent=None):
        QWidget.__init__(self, parent)
        TemplateEditableWidget.__init__(self, 'system_widget', controller, theme_library)

        self.controller = controller
        self.theme_library = theme_library

        # Connect to signals
        self.controller.raw_system_info_output.connect(self.process_raw_system_output)
        self.controller.device_info_updated.connect(self.update_device_info)
        self.controller.theme_changed.connect(self.on_theme_changed)

        self._setup_widget()
        self._current_data = {}

    def _setup_widget(self):
        """Setup the widget UI"""
        layout = QVBoxLayout(self)

        # Title with gear button
        title_layout = QHBoxLayout()

        self.title_label = QLabel("SYSTEM INFORMATION")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(self.title_label)

        self.data_source_label = QLabel("Raw")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #888888;")
        title_layout.addWidget(self.data_source_label)

        title_layout.addStretch()

        # Template editor gear button
        title_layout.addWidget(self.gear_button)

        layout.addLayout(title_layout)

        # System info display
        self.system_info_display = QTextEdit()
        self.system_info_display.setMaximumHeight(300)
        self.system_info_display.setReadOnly(True)
        layout.addWidget(self.system_info_display)

        # Status bar
        status_layout = QHBoxLayout()

        self.platform_label = QLabel("Platform: Unknown")
        self.platform_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.platform_label)

        status_layout.addStretch()

        self.update_time_label = QLabel("Last Update: Never")
        self.update_time_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.update_time_label)

        layout.addLayout(status_layout)

    @pyqtSlot(object)  # RawCommandOutput
    def process_raw_system_output(self, raw_output):
        """Process raw system information output"""
        self.platform_label.setText(f"Platform: {raw_output.platform} | Command: {raw_output.command}")

        if raw_output.parsed_successfully:
            self.data_source_label.setText("Normalized")
            self.data_source_label.setStyleSheet("font-size: 10px; color: #00ff00;")
        else:
            self.data_source_label.setText("Raw")
            self.data_source_label.setStyleSheet("font-size: 10px; color: #ff6600;")

        # Update timestamp
        import time
        timestamp = time.strftime("%H:%M:%S")
        self.update_time_label.setText(f"Last Update: {timestamp}")

    @pyqtSlot(object)  # DeviceInfo
    def update_device_info(self, device_info):
        """Update system information display"""
        self._current_data = device_info

        info_text = f"""System Information:

Hostname: {device_info.hostname}
IP Address: {device_info.ip_address}
Platform: {device_info.platform}
Hardware Model: {device_info.model}
Software Version: {device_info.version}
Serial Number: {device_info.serial}
Uptime: {device_info.uptime}
Connection Status: {device_info.connection_status}
"""
        self.system_info_display.setPlainText(info_text)

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)


