"""
Enhanced NAPALM Testing Widget for TerminalTelemetry
Native integration with NAPALM Connection Dialog and comprehensive NAPALM getter coverage
"""
import json
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

import napalm
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTextEdit, QMessageBox, QTabWidget,
    QScrollArea, QGroupBox, QCheckBox, QSpinBox, QProgressBar,
    QSplitter, QFrame, QTreeWidget, QTreeWidgetItem, QDialog, QFormLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QPalette, QColor, QTextCharFormat, QSyntaxHighlighter

from termtel.widgets.napalm_connection_dialog import NapalmConnectionDialog

logger = logging.getLogger('termtel.napalm_widget')


class JSONSyntaxHighlighter(QSyntaxHighlighter):
    """JSON syntax highlighter for better output readability"""

    def __init__(self, parent=None, theme_colors=None):
        super().__init__(parent)
        self.theme_colors = theme_colors or {
            'string': '#98C379',  # Green
            'number': '#D19A66',  # Orange
            'keyword': '#C678DD',  # Purple
            'brace': '#ABB2BF'  # Light gray
        }
        self.setup_formats()

    def setup_formats(self):
        """Setup text formats for JSON highlighting"""
        # String format
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor(self.theme_colors['string']))

        # Number format
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor(self.theme_colors['number']))

        # Keyword format (true, false, null)
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor(self.theme_colors['keyword']))
        self.keyword_format.setFontWeight(QFont.Weight.Bold)

        # Brace format
        self.brace_format = QTextCharFormat()
        self.brace_format.setForeground(QColor(self.theme_colors['brace']))
        self.brace_format.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text):
        """Apply syntax highlighting to text block"""
        import re

        # Highlight strings
        string_pattern = r'"[^"\\]*(\\.[^"\\]*)*"'
        for match in re.finditer(string_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)

        # Highlight numbers
        number_pattern = r'\b\d+\.?\d*\b'
        for match in re.finditer(number_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)

        # Highlight keywords
        keyword_pattern = r'\b(true|false|null)\b'
        for match in re.finditer(keyword_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)

        # Highlight braces and brackets
        brace_pattern = r'[{}[\](),:]'
        for match in re.finditer(brace_pattern, text):
            self.setFormat(match.start(), match.end() - match.start(), self.brace_format)




class NapalmWorkerThread(QThread):
    """Worker thread for NAPALM operations to prevent UI blocking"""

    operation_completed = pyqtSignal(str, object)  # operation_name, result
    operation_failed = pyqtSignal(str, str)  # operation_name, error_message
    progress_updated = pyqtSignal(int)  # progress percentage

    def __init__(self, connection_params, operation, operation_name):
        super().__init__()
        self.connection_params = connection_params
        self.operation = operation
        self.operation_name = operation_name
        self.device = None

    def run(self):
        """Execute NAPALM operation in background thread"""
        try:
            self.progress_updated.emit(10)

            # Initialize driver
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

            self.progress_updated.emit(30)

            # Create device connection
            self.device = driver(**driver_opts)

            self.progress_updated.emit(50)

            # Open connection
            self.device.open()

            self.progress_updated.emit(70)

            # Execute operation
            if hasattr(self.device, self.operation):
                getter = getattr(self.device, self.operation)
                result = getter()
                self.progress_updated.emit(90)
                self.operation_completed.emit(self.operation_name, result)
            else:
                self.operation_failed.emit(self.operation_name, f"Operation '{self.operation}' not supported")

            self.progress_updated.emit(100)

        except Exception as e:
            self.operation_failed.emit(self.operation_name, str(e))
        finally:
            # Clean up connection
            if self.device:
                try:
                    self.device.close()
                except:
                    pass


class NapalmWidget(QWidget):
    """Enhanced NAPALM testing widget with native connection dialog integration"""

    # Theme change signal
    theme_changed = pyqtSignal(str)

    def __init__(self, parent=None, theme_manager=None, theme_name="cyberpunk"):
        super().__init__(parent)
        self.parent_window = parent
        self.theme_manager = theme_manager
        self.current_theme = theme_name
        self.current_operation = None
        self.highlighter = None

        # Store validated connection parameters
        self._connection_params = {}
        self._connection_valid = False

        # NAPALM operation categories with comprehensive coverage
        self.napalm_operations = {
            "Connection & Basic": {
                "Test Connection": "get_facts",
                "Get Facts": "get_facts",
                "Get Config": "get_config"
            },
            "Network Discovery": {
                "Get Interfaces": "get_interfaces",
                "Get Interfaces IP": "get_interfaces_ip",
                "Get LLDP Neighbors": "get_lldp_neighbors",
                "Get LLDP Neighbors Detail": "get_lldp_neighbors_detail",
                "Get ARP Table": "get_arp_table",
                "Get MAC Address Table": "get_mac_address_table",
                "Get Network Instances": "get_network_instances"
            },
            "Routing & BGP": {
                "Get Route Table": "get_route_to",
                "Get BGP Config": "get_bgp_config",
                "Get BGP Neighbors": "get_bgp_neighbors",
                "Get BGP Neighbors Detail": "get_bgp_neighbors_detail"
            },
            "System & Environment": {
                "Get Users": "get_users",
                "Get Environment": "get_environment",
                "Get SNMP Information": "get_snmp_information",
                "Get NTP Servers": "get_ntp_servers",
                "Get NTP Stats": "get_ntp_stats"
            },
            "VLANs & Spanning Tree": {
                "Get VLANs": "get_vlans",
                "Get Spanning Tree": "get_spanning_tree"
            },
            "Firewall & Security": {
                "Get Firewall Policies": "get_firewall_policies",
                "Get IPV6 Neighbors Table": "get_ipv6_neighbors_table"
            },
            "OSPF": {
                "Get OSPF Neighbors": "get_ospf_neighbors",
                "Get OSPF Database": "get_ospf_database"
            },
            "Advanced Operations": {
                "Get Probes Config": "get_probes_config",
                "Get Probes Results": "get_probes_results",
                "Get Optics": "get_optics"
            }
        }

        self.init_ui()
        self.apply_theme(theme_name)

    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)

        # Connection parameters section - NATIVE INTEGRATION
        self.create_connection_section(layout)

        # Main content area with splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left side: Operation buttons
        self.create_operations_section(splitter)

        # Right side: Output area
        self.create_output_section(splitter)

        # Bottom: Progress and controls
        self.create_controls_section(layout)

        # Set splitter proportions
        splitter.setSizes([300, 500])

    def create_connection_section(self, layout):
        """Create connection parameters section with native dialog integration"""
        conn_frame = QFrame()
        conn_frame.setFrameStyle(QFrame.Shape.Box)
        conn_layout = QVBoxLayout(conn_frame)

        # Connection status display
        status_layout = QHBoxLayout()

        self.connection_status_label = QLabel("No Connection Configured")
        self.connection_status_label.setStyleSheet("QLabel { font-weight: bold; padding: 5px; }")
        status_layout.addWidget(self.connection_status_label)

        # Connection configuration button - MAIN INTEGRATION POINT
        self.configure_connection_btn = QPushButton("Configure Connection...")
        self.configure_connection_btn.clicked.connect(self.show_connection_dialog)
        status_layout.addWidget(self.configure_connection_btn)

        # Quick test button
        self.quick_test_btn = QPushButton("Quick Test")
        self.quick_test_btn.clicked.connect(self.quick_test_connection)
        self.quick_test_btn.setEnabled(False)
        status_layout.addWidget(self.quick_test_btn)

        conn_layout.addLayout(status_layout)

        # Quick connection override (for manual testing)
        override_group = QGroupBox("Quick Override (Optional)")
        override_group.setCheckable(True)
        override_group.setChecked(False)
        override_layout = QGridLayout(override_group)

        # Basic connection parameters for quick override
        override_layout.addWidget(QLabel("Hostname:"), 0, 0)
        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText("Override configured hostname")
        override_layout.addWidget(self.hostname_input, 0, 1)

        override_layout.addWidget(QLabel("Username:"), 0, 2)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Override username")
        override_layout.addWidget(self.username_input, 0, 3)

        override_layout.addWidget(QLabel("Password:"), 1, 0)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Override password")
        override_layout.addWidget(self.password_input, 1, 1)

        override_layout.addWidget(QLabel("Driver:"), 1, 2)
        self.driver_combo = QComboBox()
        self._populate_driver_combo()
        override_layout.addWidget(self.driver_combo, 1, 3)

        # Connect the group toggle to enable/disable quick override
        override_group.toggled.connect(self._toggle_quick_override)

        conn_layout.addWidget(override_group)
        layout.addWidget(conn_frame)

    def _populate_driver_combo(self):
        """Populate driver combo for quick override"""
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

    def _toggle_quick_override(self, enabled):
        """Handle quick override toggle"""
        if enabled:
            self.status_label.setText("Quick override enabled - using manual fields")
        else:
            self._update_status_from_connection()

    def show_connection_dialog(self):
        """Show the native connection configuration dialog"""
        # Get current parameters (either from stored config or quick override)
        current_params = self.get_connection_params()

        # Create and show dialog
        dialog = NapalmConnectionDialog(
            parent=self,
            theme_library=self.theme_manager,
            current_params=current_params
        )

        # Connect the configuration signal
        dialog.connection_configured.connect(self.apply_connection_configuration)

        # Show dialog
        dialog.exec()

    def apply_connection_configuration(self, params):
        """Apply connection configuration from dialog"""
        # Store the validated connection parameters
        self._connection_params = params
        self._connection_valid = True

        # Update status
        self._update_status_from_connection()

        # Enable quick test
        self.quick_test_btn.setEnabled(True)

        # Clear any quick override to use the configured connection
        override_group = self.findChild(QGroupBox, "Quick Override (Optional)")
        if override_group:
            override_group.setChecked(False)

        # Update status
        hostname = params.get('hostname', 'Unknown')
        driver = params.get('driver', 'Unknown')
        self.status_label.setText(f"Connection configured: {hostname} ({driver})")

    def _update_status_from_connection(self):
        """Update status label from stored connection"""
        if self._connection_valid and self._connection_params:
            hostname = self._connection_params.get('hostname', 'Unknown')
            driver = self._connection_params.get('driver', 'Unknown')
            self.connection_status_label.setText(f"✓ {hostname} ({driver})")
            self.connection_status_label.setStyleSheet(
                "QLabel { color: #00ff88; font-weight: bold; padding: 5px; }"
            )
        else:
            self.connection_status_label.setText("No Connection Configured")
            self.connection_status_label.setStyleSheet(
                "QLabel { color: #ff6666; font-weight: bold; padding: 5px; }"
            )

    def get_connection_params(self) -> Dict[str, str]:
        """Get current connection parameters (from config or quick override)"""
        # Check if quick override is enabled
        override_group = self.findChild(QGroupBox)
        if override_group and override_group.isChecked() and override_group.title() == "Quick Override (Optional)":
            # Use quick override values
            return {
                'hostname': self.hostname_input.text().strip(),
                'username': self.username_input.text().strip(),
                'password': self.password_input.text(),
                'driver': self.driver_combo.currentData() or 'ios',
                'timeout': 30  # Default timeout
            }
        elif self._connection_valid and self._connection_params:
            # Use configured connection parameters
            return self._connection_params.copy()
        else:
            # No valid connection
            return {}

    def quick_test_connection(self):
        """Quick test of the configured connection"""
        if not self._connection_valid:
            QMessageBox.warning(self, "No Configuration",
                              "Please configure a connection first.")
            return

        self.execute_operation("get_facts", "Quick Connection Test")

    def create_operations_section(self, splitter):
        """Create operations section with categorized buttons"""
        ops_widget = QWidget()
        ops_layout = QVBoxLayout(ops_widget)

        # Create tabbed interface for operation categories
        self.ops_tabs = QTabWidget()

        for category, operations in self.napalm_operations.items():
            tab_widget = QWidget()
            tab_layout = QVBoxLayout(tab_widget)

            # Create buttons for this category
            for display_name, method_name in operations.items():
                button = QPushButton(display_name)
                button.clicked.connect(lambda checked, op=method_name, name=display_name:
                                       self.execute_operation(op, name))
                tab_layout.addWidget(button)

            # Add stretch to push buttons to top
            tab_layout.addStretch()

            self.ops_tabs.addTab(tab_widget, category)

        ops_layout.addWidget(self.ops_tabs)

        # Add operation options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.auto_format_json = QCheckBox("Auto-format JSON")
        self.auto_format_json.setChecked(True)
        options_layout.addWidget(self.auto_format_json)

        self.syntax_highlight = QCheckBox("Syntax highlighting")
        self.syntax_highlight.setChecked(True)
        self.syntax_highlight.toggled.connect(self.toggle_syntax_highlighting)
        options_layout.addWidget(self.syntax_highlight)

        ops_layout.addWidget(options_group)

        splitter.addWidget(ops_widget)

    def create_output_section(self, splitter):
        """Create output section with tabs for different views"""
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)

        # Output tabs
        self.output_tabs = QTabWidget()

        # Raw output tab
        self.raw_output = QTextEdit()
        self.raw_output.setReadOnly(True)
        self.raw_output.setFont(QFont("Consolas", 10))
        self.output_tabs.addTab(self.raw_output, "Raw Output")

        # Formatted output tab
        self.formatted_output = QTextEdit()
        self.formatted_output.setReadOnly(True)
        self.formatted_output.setFont(QFont("Consolas", 10))
        self.output_tabs.addTab(self.formatted_output, "Formatted JSON")

        # Tree view tab for structured data
        self.tree_output = QTreeWidget()
        self.tree_output.setHeaderLabels(["Key", "Value", "Type"])
        self.output_tabs.addTab(self.tree_output, "Tree View")

        output_layout.addWidget(self.output_tabs)

        # Output controls
        controls_layout = QHBoxLayout()

        clear_button = QPushButton("Clear Output")
        clear_button.clicked.connect(self.clear_output)
        controls_layout.addWidget(clear_button)

        save_button = QPushButton("Save Output")
        save_button.clicked.connect(self.save_output)
        controls_layout.addWidget(save_button)

        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(self.copy_to_clipboard)
        controls_layout.addWidget(copy_button)

        controls_layout.addStretch()
        output_layout.addLayout(controls_layout)

        splitter.addWidget(output_widget)

    def create_controls_section(self, layout):
        """Create bottom controls section"""
        controls_frame = QFrame()
        controls_frame.setFrameStyle(QFrame.Shape.Box)
        controls_layout = QHBoxLayout(controls_frame)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        controls_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready")
        controls_layout.addWidget(self.status_label)

        controls_layout.addStretch()

        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_operation)
        controls_layout.addWidget(self.cancel_button)

        layout.addWidget(controls_frame)

    def execute_operation(self, operation: str, operation_name: str):
        """Execute a NAPALM operation in background thread"""
        params = self.get_connection_params()

        if not params or not all([params.get('hostname'), params.get('username'), params.get('password')]):
            QMessageBox.warning(self, "Missing Parameters",
                                "Please configure connection parameters first.")
            return

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.cancel_button.setEnabled(True)
        self.status_label.setText(f"Executing {operation_name}...")

        # Start worker thread
        self.current_operation = NapalmWorkerThread(params, operation, operation_name)
        self.current_operation.operation_completed.connect(self.handle_operation_success)
        self.current_operation.operation_failed.connect(self.handle_operation_error)
        self.current_operation.progress_updated.connect(self.progress_bar.setValue)
        self.current_operation.finished.connect(self.operation_finished)
        self.current_operation.start()

    def handle_operation_success(self, operation_name: str, result: Any):
        """Handle successful operation completion"""
        try:
            # Convert result to JSON string
            json_str = json.dumps(result, indent=2, default=str)

            # Update raw output
            self.raw_output.append(f"\n{'-' * 60}")
            self.raw_output.append(f"{operation_name} - Success")
            self.raw_output.append(f"{'-' * 60}\n")
            self.raw_output.append(str(result))

            # Update formatted output
            if self.auto_format_json.isChecked():
                self.formatted_output.append(f"\n{'-' * 60}")
                self.formatted_output.append(f"{operation_name} - Formatted JSON")
                self.formatted_output.append(f"{'-' * 60}\n")
                self.formatted_output.append(json_str)

            # Update tree view
            self.populate_tree_view(operation_name, result)

            self.status_label.setText(f"{operation_name} completed successfully")

        except Exception as e:
            self.handle_operation_error(operation_name, f"Failed to process result: {str(e)}")

    def handle_operation_error(self, operation_name: str, error_message: str):
        """Handle operation error"""
        self.raw_output.append(f"\n{'-' * 60}")
        self.raw_output.append(f"{operation_name} - ERROR")
        self.raw_output.append(f"{'-' * 60}\n")
        self.raw_output.append(f"Error: {error_message}")

        self.status_label.setText(f"{operation_name} failed: {error_message}")

        # Show error dialog for critical errors
        if "connection" in error_message.lower() or "authentication" in error_message.lower():
            QMessageBox.critical(self, "Connection Error",
                                 f"{operation_name} failed:\n{error_message}")

    def operation_finished(self):
        """Clean up after operation completion"""
        self.progress_bar.setVisible(False)
        self.cancel_button.setEnabled(False)
        self.current_operation = None

    def cancel_operation(self):
        """Cancel current operation"""
        if self.current_operation and self.current_operation.isRunning():
            self.current_operation.terminate()
            self.current_operation.wait()
            self.status_label.setText("Operation cancelled")
            self.operation_finished()

    def populate_tree_view(self, operation_name: str, data: Any):
        """Populate tree view with structured data"""
        # Clear existing items
        self.tree_output.clear()

        # Create root item
        root = QTreeWidgetItem(self.tree_output)
        root.setText(0, operation_name)
        root.setText(1, str(type(data).__name__))
        root.setText(2, "Result")

        # Recursively populate tree
        self._add_tree_items(root, data)

        # Expand first level
        root.setExpanded(True)

    def _add_tree_items(self, parent: QTreeWidgetItem, data: Any, max_depth: int = 3, current_depth: int = 0):
        """Recursively add items to tree view"""
        if current_depth >= max_depth:
            return

        if isinstance(data, dict):
            for key, value in data.items():
                item = QTreeWidgetItem(parent)
                item.setText(0, str(key))
                item.setText(2, type(value).__name__)

                if isinstance(value, (dict, list)) and len(str(value)) > 100:
                    item.setText(1, f"<{type(value).__name__} with {len(value)} items>")
                    self._add_tree_items(item, value, max_depth, current_depth + 1)
                else:
                    item.setText(1, str(value)[:100] + "..." if len(str(value)) > 100 else str(value))

        elif isinstance(data, list):
            for i, value in enumerate(data):
                item = QTreeWidgetItem(parent)
                item.setText(0, f"[{i}]")
                item.setText(2, type(value).__name__)

                if isinstance(value, (dict, list)) and len(str(value)) > 100:
                    item.setText(1, f"<{type(value).__name__}>")
                    self._add_tree_items(item, value, max_depth, current_depth + 1)
                else:
                    item.setText(1, str(value)[:100] + "..." if len(str(value)) > 100 else str(value))

    def toggle_syntax_highlighting(self, enabled: bool):
        """Toggle syntax highlighting on formatted output"""
        if enabled and self.theme_manager:
            # Get theme colors for syntax highlighting
            colors = self.theme_manager.get_colors(self.current_theme)
            theme_colors = {
                'string': colors.get('success', '#98C379'),
                'number': colors.get('warning', '#D19A66'),
                'keyword': colors.get('primary', '#C678DD'),
                'brace': colors.get('text', '#ABB2BF')
            }

            self.highlighter = JSONSyntaxHighlighter(self.formatted_output.document(), theme_colors)
        else:
            if self.highlighter:
                self.highlighter.setDocument(None)
                self.highlighter = None

    def clear_output(self):
        """Clear all output areas"""
        self.raw_output.clear()
        self.formatted_output.clear()
        self.tree_output.clear()
        self.status_label.setText("Output cleared")

    def save_output(self):
        """Save current output to file"""
        from PyQt6.QtWidgets import QFileDialog

        current_tab = self.output_tabs.currentIndex()

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Output", "",
            "Text Files (*.txt);;JSON Files (*.json);;All Files (*)"
        )

        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    if current_tab == 0:  # Raw output
                        f.write(self.raw_output.toPlainText())
                    elif current_tab == 1:  # Formatted output
                        f.write(self.formatted_output.toPlainText())
                    else:  # Tree view - export as text representation
                        f.write("Tree View Export:\n\n")
                        self._export_tree_text(self.tree_output.invisibleRootItem(), f, 0)

                self.status_label.setText(f"Output saved to {filename}")

            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save output:\n{str(e)}")

    def _export_tree_text(self, item: QTreeWidgetItem, file, indent: int):
        """Export tree view as text"""
        for i in range(item.childCount()):
            child = item.child(i)
            prefix = "  " * indent
            file.write(f"{prefix}{child.text(0)}: {child.text(1)} ({child.text(2)})\n")
            if child.childCount() > 0:
                self._export_tree_text(child, file, indent + 1)

    def copy_to_clipboard(self):
        """Copy current output to clipboard"""
        from PyQt6.QtWidgets import QApplication

        current_tab = self.output_tabs.currentIndex()

        if current_tab == 0:
            text = self.raw_output.toPlainText()
        elif current_tab == 1:
            text = self.formatted_output.toPlainText()
        else:
            # For tree view, copy a text representation
            text = "Tree View Data:\n\n"
            # Simple tree export - could be enhanced
            text += str(self.tree_output.topLevelItemCount()) + " top-level items"

        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.status_label.setText("Output copied to clipboard")

    def apply_theme(self, theme_name: str):
        """Apply theme to the widget"""
        self.current_theme = theme_name

        if not self.theme_manager:
            return

        try:
            # Apply theme to main widget
            self.theme_manager.apply_theme(self, theme_name)

            # Update syntax highlighting with new theme colors
            if self.syntax_highlight.isChecked():
                self.toggle_syntax_highlighting(True)

            # Update connection status styling
            self._update_status_from_connection()

            # Emit theme change signal for any child components
            self.theme_changed.emit(theme_name)

        except Exception as e:
            logger.warning(f"Failed to apply theme '{theme_name}': {e}")

    def set_theme_from_parent(self, theme_name: str):
        """Set theme from parent window (TerminalTelemetry integration)"""
        self.apply_theme(theme_name)

    def cleanup(self):
        """Clean up resources when widget is closed"""
        # Cancel any running operations
        if self.current_operation and self.current_operation.isRunning():
            self.current_operation.terminate()
            self.current_operation.wait()

        # Clean up syntax highlighter
        if self.highlighter:
            self.highlighter.setDocument(None)

        logger.info("NAPALM widget cleaned up")


# Integration functions remain the same but now use the enhanced widget
def create_napalm_tab(terminal_tabs, parent_window):
    """Create NAPALM testing tab in TerminalTelemetry"""
    try:
        # Get theme manager from parent
        theme_manager = getattr(parent_window, 'theme_manager', None)
        current_theme = getattr(parent_window, 'theme', 'cyberpunk')

        # Create enhanced NAPALM widget with native connection dialog
        napalm_widget = NapalmWidget(
            parent=parent_window,
            theme_manager=theme_manager,
            theme_name=current_theme
        )

        # Add as tab
        from PyQt6.QtGui import QIcon

        # Create icon if available
        icon_path = Path(__file__).parent / 'icons' / 'napalm.svg'
        if icon_path.exists():
            tab_icon = QIcon(str(icon_path))
            index = terminal_tabs.addTab(napalm_widget, tab_icon, "NAPALM Tester")
        else:
            index = terminal_tabs.addTab(napalm_widget, "NAPALM Tester")

        terminal_tabs.setTabToolTip(index, "NAPALM Device Testing and Validation")

        # Store reference for theme updates
        if not hasattr(parent_window, 'napalm_widgets'):
            parent_window.napalm_widgets = []
        parent_window.napalm_widgets.append(napalm_widget)

        logger.info("Enhanced NAPALM testing tab created successfully")
        return napalm_widget

    except Exception as e:
        logger.error(f"Failed to create NAPALM tab: {e}")
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            parent_window,
            "NAPALM Error",
            f"Failed to create NAPALM testing tab:\n{str(e)}"
        )
        return None