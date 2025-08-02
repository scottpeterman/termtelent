#!/usr/bin/env python3
"""
Vendor Fingerprint YAML Editor Widget - Data Preservation Version
A sophisticated tabbed interface for editing vendor fingerprint YAML files
with complete data preservation and selective field updates
"""

import sys
import yaml
import logging
import traceback
from pathlib import Path
from typing import Dict, List, Any, Optional
from copy import deepcopy
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QLineEdit, QPushButton, QLabel, QGroupBox, QFormLayout, QComboBox,
    QSpinBox, QCheckBox, QSplitter, QFrame, QScrollArea, QMessageBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog, QMenu, QApplication,
    QPlainTextEdit, QProgressBar, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, QObject, QDateTime
from PyQt6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat, QTextDocument, QAction

logger = logging.getLogger(__name__)


class YAMLSyntaxHighlighter(QSyntaxHighlighter):
    """YAML syntax highlighter for better readability"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # Define text formats
        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#0066cc"))
        key_format.setFontWeight(QFont.Weight.Bold)

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#009900"))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#cc6600"))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#888888"))
        comment_format.setFontItalic(True)

        # Define highlighting rules
        self.highlighting_rules = [
            # YAML keys
            (r'^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', key_format),
            # Strings in quotes
            (r'"[^"]*"', string_format),
            (r"'[^']*'", string_format),
            # Numbers
            (r'\b\d+\.?\d*\b', number_format),
            # Comments
            (r'#.*$', comment_format),
        ]

    def highlightBlock(self, text):
        import re
        for pattern, format_obj in self.highlighting_rules:
            expression = re.compile(pattern, re.MULTILINE)
            for match in expression.finditer(text):
                start = match.start()
                length = len(match.group())
                self.setFormat(start, length, format_obj)


class VendorEditorWidget(QWidget):
    """Widget for editing a single vendor configuration with complete data preservation"""

    vendor_changed = pyqtSignal(str, dict)  # vendor_name, vendor_data

    def __init__(self, vendor_name: str = "", vendor_data: Dict = None, parent=None):
        super().__init__(parent)
        self.vendor_name = vendor_name
        self.original_vendor_data = deepcopy(vendor_data) if vendor_data else {}  # Preserve original
        self.vendor_data = deepcopy(vendor_data) if vendor_data else {}
        self._loading_data = False  # Flag to prevent infinite signal loops
        self._form_dirty = False  # Track if form has unsaved changes

        # Fields that the UI manages (all others will be preserved as-is)
        self.ui_managed_fields = {
            'display_name', 'enterprise_oid', 'definitive_patterns',
            'detection_patterns', 'exclusion_patterns', 'fingerprint_oids',
            'device_types', 'model_extraction', 'serial_extraction',
            'firmware_extraction', 'device_rules'
        }

        self.setup_ui()
        self.connect_signals()
        self.load_vendor_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Vendor basic info
        basic_group = QGroupBox("Basic Information")
        basic_layout = QFormLayout(basic_group)

        self.display_name_edit = QLineEdit()
        self.enterprise_oid_edit = QLineEdit()

        basic_layout.addRow("Display Name:", self.display_name_edit)
        basic_layout.addRow("Enterprise OID:", self.enterprise_oid_edit)

        layout.addWidget(basic_group)

        # Add preservation warning
        preservation_label = QLabel("⚠️ Note: This editor preserves all existing YAML fields not shown in the UI")
        preservation_label.setStyleSheet("color: #666; font-style: italic; padding: 5px;")
        layout.addWidget(preservation_label)

        # Tabbed interface for different sections
        self.tab_widget = QTabWidget()

        # Detection Patterns Tab
        self.setup_detection_tab()

        # OID Fingerprints Tab
        self.setup_oids_tab()

        # Device Types Tab
        self.setup_device_types_tab()

        # Field Extraction Tab
        self.setup_extraction_tab()

        # Raw YAML Tab
        self.setup_raw_yaml_tab()

        layout.addWidget(self.tab_widget)

    def connect_signals(self):
        """Connect all signals to track changes"""
        # Basic info signals
        self.display_name_edit.textChanged.connect(self.on_form_changed)
        self.enterprise_oid_edit.textChanged.connect(self.on_form_changed)

        # Table change signals
        self.definitive_table.itemChanged.connect(self.on_form_changed)
        self.detection_list.itemChanged.connect(self.on_form_changed)
        self.exclusion_list.itemChanged.connect(self.on_form_changed)
        self.oids_table.itemChanged.connect(self.on_form_changed)
        self.device_types_list.itemChanged.connect(self.on_form_changed)
        self.model_extraction_table.itemChanged.connect(self.on_form_changed)
        self.serial_extraction_table.itemChanged.connect(self.on_form_changed)
        self.firmware_extraction_table.itemChanged.connect(self.on_form_changed)

        # Raw YAML editor
        self.raw_yaml_editor.textChanged.connect(self.on_raw_yaml_changed)

    def setup_detection_tab(self):
        """Setup the detection patterns tab"""
        detection_widget = QWidget()
        layout = QVBoxLayout(detection_widget)

        # Definitive patterns
        def_group = QGroupBox("Definitive Patterns (100% confidence)")
        def_layout = QVBoxLayout(def_group)

        self.definitive_table = QTableWidget(0, 3)
        self.definitive_table.setHorizontalHeaderLabels(["Pattern", "Confidence", "Description"])
        self.definitive_table.horizontalHeader().setStretchLastSection(True)

        def_buttons = QHBoxLayout()
        add_def_btn = QPushButton("Add Definitive Pattern")
        remove_def_btn = QPushButton("Remove Selected")
        add_def_btn.clicked.connect(lambda: self.add_pattern_row(self.definitive_table, True))
        remove_def_btn.clicked.connect(lambda: self.remove_selected_rows(self.definitive_table))

        def_buttons.addWidget(add_def_btn)
        def_buttons.addWidget(remove_def_btn)
        def_buttons.addStretch()

        def_layout.addWidget(self.definitive_table)
        def_layout.addLayout(def_buttons)

        # Detection patterns
        detect_group = QGroupBox("Detection Patterns")
        detect_layout = QVBoxLayout(detect_group)

        self.detection_list = QTableWidget(0, 1)
        self.detection_list.setHorizontalHeaderLabels(["Pattern"])
        self.detection_list.horizontalHeader().setStretchLastSection(True)

        detect_buttons = QHBoxLayout()
        add_detect_btn = QPushButton("Add Detection Pattern")
        remove_detect_btn = QPushButton("Remove Selected")
        add_detect_btn.clicked.connect(lambda: self.add_simple_pattern(self.detection_list))
        remove_detect_btn.clicked.connect(lambda: self.remove_selected_rows(self.detection_list))

        detect_buttons.addWidget(add_detect_btn)
        detect_buttons.addWidget(remove_detect_btn)
        detect_buttons.addStretch()

        detect_layout.addWidget(self.detection_list)
        detect_layout.addLayout(detect_buttons)

        # Exclusion patterns
        excl_group = QGroupBox("Exclusion Patterns")
        excl_layout = QVBoxLayout(excl_group)

        self.exclusion_list = QTableWidget(0, 1)
        self.exclusion_list.setHorizontalHeaderLabels(["Pattern"])
        self.exclusion_list.horizontalHeader().setStretchLastSection(True)

        excl_buttons = QHBoxLayout()
        add_excl_btn = QPushButton("Add Exclusion Pattern")
        remove_excl_btn = QPushButton("Remove Selected")
        add_excl_btn.clicked.connect(lambda: self.add_simple_pattern(self.exclusion_list))
        remove_excl_btn.clicked.connect(lambda: self.remove_selected_rows(self.exclusion_list))

        excl_buttons.addWidget(add_excl_btn)
        excl_buttons.addWidget(remove_excl_btn)
        excl_buttons.addStretch()

        excl_layout.addWidget(self.exclusion_list)
        excl_layout.addLayout(excl_buttons)

        layout.addWidget(def_group)
        layout.addWidget(detect_group)
        layout.addWidget(excl_group)

        self.tab_widget.addTab(detection_widget, "Detection Patterns")

    def setup_oids_tab(self):
        """Setup the OID fingerprints tab"""
        oids_widget = QWidget()
        layout = QVBoxLayout(oids_widget)

        self.oids_table = QTableWidget(0, 5)
        self.oids_table.setHorizontalHeaderLabels(["Name", "OID", "Priority", "Description", "Definitive"])
        self.oids_table.horizontalHeader().setStretchLastSection(True)

        oids_buttons = QHBoxLayout()
        add_oid_btn = QPushButton("Add OID")
        remove_oid_btn = QPushButton("Remove Selected")
        import_oid_btn = QPushButton("Import from Template")

        add_oid_btn.clicked.connect(self.add_oid_row)
        remove_oid_btn.clicked.connect(lambda: self.remove_selected_rows(self.oids_table))
        import_oid_btn.clicked.connect(self.import_oid_template)

        oids_buttons.addWidget(add_oid_btn)
        oids_buttons.addWidget(remove_oid_btn)
        oids_buttons.addWidget(import_oid_btn)
        oids_buttons.addStretch()

        layout.addWidget(self.oids_table)
        layout.addLayout(oids_buttons)

        self.tab_widget.addTab(oids_widget, "OID Fingerprints")

    def setup_device_types_tab(self):
        """Setup the device types tab"""
        device_widget = QWidget()
        layout = QVBoxLayout(device_widget)

        # Device types list
        types_group = QGroupBox("Supported Device Types")
        types_layout = QVBoxLayout(types_group)

        self.device_types_list = QTableWidget(0, 1)
        self.device_types_list.setHorizontalHeaderLabels(["Device Type"])
        self.device_types_list.horizontalHeader().setStretchLastSection(True)

        types_buttons = QHBoxLayout()
        add_type_btn = QPushButton("Add Device Type")
        remove_type_btn = QPushButton("Remove Selected")

        add_type_btn.clicked.connect(lambda: self.add_simple_pattern(self.device_types_list))
        remove_type_btn.clicked.connect(lambda: self.remove_selected_rows(self.device_types_list))

        types_buttons.addWidget(add_type_btn)
        types_buttons.addWidget(remove_type_btn)
        types_buttons.addStretch()

        types_layout.addWidget(self.device_types_list)
        types_layout.addLayout(types_buttons)

        # Device type rules
        rules_group = QGroupBox("Device Type Rules")
        rules_layout = QVBoxLayout(rules_group)

        self.device_rules_tree = QTreeWidget()
        self.device_rules_tree.setHeaderLabels(["Rule Name", "Priority", "Description"])

        rules_buttons = QHBoxLayout()
        add_rule_btn = QPushButton("Add Rule")
        edit_rule_btn = QPushButton("Edit Selected")
        remove_rule_btn = QPushButton("Remove Selected")

        add_rule_btn.clicked.connect(self.add_device_rule)
        edit_rule_btn.clicked.connect(self.edit_device_rule)
        remove_rule_btn.clicked.connect(self.remove_device_rule)

        rules_buttons.addWidget(add_rule_btn)
        rules_buttons.addWidget(edit_rule_btn)
        rules_buttons.addWidget(remove_rule_btn)
        rules_buttons.addStretch()

        rules_layout.addWidget(self.device_rules_tree)
        rules_layout.addLayout(rules_buttons)

        layout.addWidget(types_group)
        layout.addWidget(rules_group)

        self.tab_widget.addTab(device_widget, "Device Types")

    def setup_extraction_tab(self):
        """Setup the field extraction tab"""
        extraction_widget = QWidget()
        layout = QVBoxLayout(extraction_widget)

        # Model extraction
        model_group = QGroupBox("Model Extraction Rules")
        model_layout = QVBoxLayout(model_group)

        self.model_extraction_table = QTableWidget(0, 4)
        self.model_extraction_table.setHorizontalHeaderLabels(["Regex", "Priority", "Capture Group", "Description"])
        self.model_extraction_table.horizontalHeader().setStretchLastSection(True)

        model_buttons = QHBoxLayout()
        add_model_btn = QPushButton("Add Model Rule")
        remove_model_btn = QPushButton("Remove Selected")

        add_model_btn.clicked.connect(lambda: self.add_extraction_row(self.model_extraction_table))
        remove_model_btn.clicked.connect(lambda: self.remove_selected_rows(self.model_extraction_table))

        model_buttons.addWidget(add_model_btn)
        model_buttons.addWidget(remove_model_btn)
        model_buttons.addStretch()

        model_layout.addWidget(self.model_extraction_table)
        model_layout.addLayout(model_buttons)

        # Serial extraction
        serial_group = QGroupBox("Serial Number Extraction Rules")
        serial_layout = QVBoxLayout(serial_group)

        self.serial_extraction_table = QTableWidget(0, 4)
        self.serial_extraction_table.setHorizontalHeaderLabels(["Regex", "Priority", "Capture Group", "Description"])
        self.serial_extraction_table.horizontalHeader().setStretchLastSection(True)

        serial_buttons = QHBoxLayout()
        add_serial_btn = QPushButton("Add Serial Rule")
        remove_serial_btn = QPushButton("Remove Selected")

        add_serial_btn.clicked.connect(lambda: self.add_extraction_row(self.serial_extraction_table))
        remove_serial_btn.clicked.connect(lambda: self.remove_selected_rows(self.serial_extraction_table))

        serial_buttons.addWidget(add_serial_btn)
        serial_buttons.addWidget(remove_serial_btn)
        serial_buttons.addStretch()

        serial_layout.addWidget(self.serial_extraction_table)
        serial_layout.addLayout(serial_buttons)

        # Firmware extraction
        firmware_group = QGroupBox("Firmware Extraction Rules")
        firmware_layout = QVBoxLayout(firmware_group)

        self.firmware_extraction_table = QTableWidget(0, 4)
        self.firmware_extraction_table.setHorizontalHeaderLabels(["Regex", "Priority", "Capture Group", "Description"])
        self.firmware_extraction_table.horizontalHeader().setStretchLastSection(True)

        firmware_buttons = QHBoxLayout()
        add_firmware_btn = QPushButton("Add Firmware Rule")
        remove_firmware_btn = QPushButton("Remove Selected")

        add_firmware_btn.clicked.connect(lambda: self.add_extraction_row(self.firmware_extraction_table))
        remove_firmware_btn.clicked.connect(lambda: self.remove_selected_rows(self.firmware_extraction_table))

        firmware_buttons.addWidget(add_firmware_btn)
        firmware_buttons.addWidget(remove_firmware_btn)
        firmware_buttons.addStretch()

        firmware_layout.addWidget(self.firmware_extraction_table)
        firmware_layout.addLayout(firmware_buttons)

        layout.addWidget(model_group)
        layout.addWidget(serial_group)
        layout.addWidget(firmware_group)

        self.tab_widget.addTab(extraction_widget, "Field Extraction")

    def setup_raw_yaml_tab(self):
        """Setup the raw YAML editor tab"""
        yaml_widget = QWidget()
        layout = QVBoxLayout(yaml_widget)

        # Raw YAML editor
        self.raw_yaml_editor = QPlainTextEdit()
        self.yaml_highlighter = YAMLSyntaxHighlighter(self.raw_yaml_editor.document())

        yaml_buttons = QHBoxLayout()
        validate_btn = QPushButton("Validate YAML")
        format_btn = QPushButton("Format YAML")
        sync_from_ui_btn = QPushButton("Sync from UI")
        sync_to_ui_btn = QPushButton("Sync to UI")

        validate_btn.clicked.connect(self.validate_yaml)
        format_btn.clicked.connect(self.format_yaml)
        sync_from_ui_btn.clicked.connect(self.sync_from_ui_to_yaml)
        sync_to_ui_btn.clicked.connect(self.sync_from_yaml_to_ui)

        yaml_buttons.addWidget(validate_btn)
        yaml_buttons.addWidget(format_btn)
        yaml_buttons.addWidget(sync_from_ui_btn)
        yaml_buttons.addWidget(sync_to_ui_btn)
        yaml_buttons.addStretch()

        layout.addWidget(self.raw_yaml_editor)
        layout.addLayout(yaml_buttons)

        self.tab_widget.addTab(yaml_widget, "Raw YAML")

    def set_vendor_data(self, vendor_name: str, vendor_data: Dict):
        """Set vendor data and reload the form while preserving all original data"""
        # Save current data before switching if dirty
        if self._form_dirty and self.vendor_name:
            current_data = self.get_vendor_data_preserved()
            self.vendor_changed.emit(self.vendor_name, current_data)

        self.vendor_name = vendor_name
        self.original_vendor_data = deepcopy(vendor_data) if vendor_data else {}
        self.vendor_data = deepcopy(vendor_data) if vendor_data else {}
        self._form_dirty = False
        self.load_vendor_data()

    def clear_form(self):
        """Clear all form data"""
        self._loading_data = True

        # Clear basic info
        self.display_name_edit.clear()
        self.enterprise_oid_edit.clear()

        # Clear all tables
        self.definitive_table.setRowCount(0)
        self.detection_list.setRowCount(0)
        self.exclusion_list.setRowCount(0)
        self.oids_table.setRowCount(0)
        self.device_types_list.setRowCount(0)
        self.model_extraction_table.setRowCount(0)
        self.serial_extraction_table.setRowCount(0)
        self.firmware_extraction_table.setRowCount(0)
        self.device_rules_tree.clear()

        # Clear YAML editor
        self.raw_yaml_editor.clear()

        self._loading_data = False
        self._form_dirty = False

    def load_vendor_data(self):
        """Load vendor data into the UI while preserving all existing fields"""
        self._loading_data = True

        try:
            self.clear_form()

            if not self.vendor_data:
                return

            # Load basic info
            self.display_name_edit.setText(self.vendor_data.get('display_name', ''))
            self.enterprise_oid_edit.setText(self.vendor_data.get('enterprise_oid', ''))

            # Load definitive patterns
            def_patterns = self.vendor_data.get('definitive_patterns', [])
            for pattern_data in def_patterns:
                row = self.definitive_table.rowCount()
                self.definitive_table.insertRow(row)
                self.definitive_table.setItem(row, 0, QTableWidgetItem(pattern_data.get('pattern', '')))
                self.definitive_table.setItem(row, 1, QTableWidgetItem(str(pattern_data.get('confidence', 100))))
                self.definitive_table.setItem(row, 2, QTableWidgetItem(pattern_data.get('description', '')))

            # Load detection patterns
            detection_patterns = self.vendor_data.get('detection_patterns', [])
            for pattern in detection_patterns:
                row = self.detection_list.rowCount()
                self.detection_list.insertRow(row)
                self.detection_list.setItem(row, 0, QTableWidgetItem(pattern))

            # Load exclusion patterns
            exclusion_patterns = self.vendor_data.get('exclusion_patterns', [])
            for pattern in exclusion_patterns:
                row = self.exclusion_list.rowCount()
                self.exclusion_list.insertRow(row)
                self.exclusion_list.setItem(row, 0, QTableWidgetItem(pattern))

            # Load OIDs
            fingerprint_oids = self.vendor_data.get('fingerprint_oids', [])
            for oid_data in fingerprint_oids:
                row = self.oids_table.rowCount()
                self.oids_table.insertRow(row)
                self.oids_table.setItem(row, 0, QTableWidgetItem(oid_data.get('name', '')))
                self.oids_table.setItem(row, 1, QTableWidgetItem(oid_data.get('oid', '')))
                self.oids_table.setItem(row, 2, QTableWidgetItem(str(oid_data.get('priority', 1))))
                self.oids_table.setItem(row, 3, QTableWidgetItem(oid_data.get('description', '')))

                checkbox = QCheckBox()
                checkbox.setChecked(oid_data.get('definitive', False))
                checkbox.stateChanged.connect(self.on_form_changed)
                self.oids_table.setCellWidget(row, 4, checkbox)

            # Load device types
            device_types = self.vendor_data.get('device_types', [])
            for device_type in device_types:
                row = self.device_types_list.rowCount()
                self.device_types_list.insertRow(row)
                self.device_types_list.setItem(row, 0, QTableWidgetItem(device_type))

            # Load extraction rules
            self.load_extraction_rules('model_extraction', self.model_extraction_table)
            self.load_extraction_rules('serial_extraction', self.serial_extraction_table)
            self.load_extraction_rules('firmware_extraction', self.firmware_extraction_table)

            # Load device type rules
            self.load_device_rules()

            # Update raw YAML to show complete data (including preserved fields)
            self.sync_from_ui_to_yaml()

        finally:
            self._loading_data = False
            self._form_dirty = False

    def load_extraction_rules(self, rule_type: str, table: QTableWidget):
        """Load extraction rules into table"""
        rules = self.vendor_data.get(rule_type, [])
        for rule in rules:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(rule.get('regex', '')))
            table.setItem(row, 1, QTableWidgetItem(str(rule.get('priority', 1))))
            table.setItem(row, 2, QTableWidgetItem(str(rule.get('capture_group', 1))))
            table.setItem(row, 3, QTableWidgetItem(rule.get('description', '')))

    def load_device_rules(self):
        """Load device type rules"""
        device_rules = self.vendor_data.get('device_rules', [])
        for rule in device_rules:
            item = QTreeWidgetItem([
                rule.get('name', ''),
                str(rule.get('priority', 1)),
                rule.get('description', '')
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, rule)
            self.device_rules_tree.addTopLevelItem(item)

    def on_form_changed(self):
        """Handle form changes - update only managed fields"""
        if not self._loading_data:
            self._form_dirty = True
            # Auto-save current vendor data with preservation
            if self.vendor_name:
                vendor_data = self.get_vendor_data_preserved()
                self.vendor_changed.emit(self.vendor_name, vendor_data)

    def on_raw_yaml_changed(self):
        """Handle raw YAML changes"""
        if not self._loading_data:
            self._form_dirty = True

    def get_vendor_data_preserved(self) -> Dict:
        """Get vendor data from UI while preserving all non-UI-managed fields"""
        # Start with original data to preserve all fields
        preserved_data = deepcopy(self.original_vendor_data)

        # Update only the fields that the UI manages
        ui_updates = self.get_ui_managed_data()

        # Merge UI changes with preserved data
        for field, value in ui_updates.items():
            if value is not None:  # Only update if we have actual data
                preserved_data[field] = value
            elif field in preserved_data and not value:
                # Remove field if UI shows it as empty/None
                if field in self.ui_managed_fields:
                    del preserved_data[field]

        return preserved_data

    def get_ui_managed_data(self) -> Dict:
        """Get only the data that the UI actually manages"""
        ui_data = {}

        # Basic info
        display_name = self.display_name_edit.text().strip()
        enterprise_oid = self.enterprise_oid_edit.text().strip()

        if display_name:
            ui_data['display_name'] = display_name
        if enterprise_oid:
            ui_data['enterprise_oid'] = enterprise_oid

        # Get definitive patterns
        def_patterns = []
        for row in range(self.definitive_table.rowCount()):
            pattern_item = self.definitive_table.item(row, 0)
            confidence_item = self.definitive_table.item(row, 1)
            description_item = self.definitive_table.item(row, 2)

            if pattern_item and pattern_item.text().strip():
                pattern_data = {
                    'pattern': pattern_item.text().strip(),
                    'confidence': int(
                        confidence_item.text()) if confidence_item and confidence_item.text().strip() else 100,
                }
                if description_item and description_item.text().strip():
                    pattern_data['description'] = description_item.text().strip()
                def_patterns.append(pattern_data)

        if def_patterns:
            ui_data['definitive_patterns'] = def_patterns

        # Get detection patterns
        detection_patterns = []
        for row in range(self.detection_list.rowCount()):
            pattern_item = self.detection_list.item(row, 0)
            if pattern_item and pattern_item.text().strip():
                detection_patterns.append(pattern_item.text().strip())

        if detection_patterns:
            ui_data['detection_patterns'] = detection_patterns

        # Get exclusion patterns
        exclusion_patterns = []
        for row in range(self.exclusion_list.rowCount()):
            pattern_item = self.exclusion_list.item(row, 0)
            if pattern_item and pattern_item.text().strip():
                exclusion_patterns.append(pattern_item.text().strip())

        if exclusion_patterns:
            ui_data['exclusion_patterns'] = exclusion_patterns

        # Get OIDs
        fingerprint_oids = []
        for row in range(self.oids_table.rowCount()):
            name_item = self.oids_table.item(row, 0)
            oid_item = self.oids_table.item(row, 1)
            priority_item = self.oids_table.item(row, 2)
            description_item = self.oids_table.item(row, 3)
            definitive_checkbox = self.oids_table.cellWidget(row, 4)

            if name_item and name_item.text().strip() and oid_item and oid_item.text().strip():
                oid_data = {
                    'name': name_item.text().strip(),
                    'oid': oid_item.text().strip(),
                    'priority': int(priority_item.text()) if priority_item and priority_item.text().strip() else 1,
                }

                if description_item and description_item.text().strip():
                    oid_data['description'] = description_item.text().strip()

                if definitive_checkbox and definitive_checkbox.isChecked():
                    oid_data['definitive'] = True

                fingerprint_oids.append(oid_data)

        if fingerprint_oids:
            ui_data['fingerprint_oids'] = fingerprint_oids

        # Get device types
        device_types = []
        for row in range(self.device_types_list.rowCount()):
            device_type_item = self.device_types_list.item(row, 0)
            if device_type_item and device_type_item.text().strip():
                device_types.append(device_type_item.text().strip())

        if device_types:
            ui_data['device_types'] = device_types

        # Get extraction rules
        model_extraction = self.get_extraction_rules(self.model_extraction_table)
        if model_extraction:
            ui_data['model_extraction'] = model_extraction

        serial_extraction = self.get_extraction_rules(self.serial_extraction_table)
        if serial_extraction:
            ui_data['serial_extraction'] = serial_extraction

        firmware_extraction = self.get_extraction_rules(self.firmware_extraction_table)
        if firmware_extraction:
            ui_data['firmware_extraction'] = firmware_extraction

        # Get device rules
        device_rules = self.get_device_rules()
        if device_rules:
            ui_data['device_rules'] = device_rules

        return ui_data

    def sync_from_ui_to_yaml(self):
        """Sync UI data to raw YAML editor while preserving all fields"""
        if self._loading_data:
            return

        self._loading_data = True
        try:
            vendor_data = self.get_vendor_data_preserved()
            yaml_text = yaml.dump(vendor_data, default_flow_style=False, sort_keys=False, indent=2)
            self.raw_yaml_editor.setPlainText(yaml_text)
        finally:
            self._loading_data = False

    def sync_from_yaml_to_ui(self):
        """Sync raw YAML to UI"""
        try:
            yaml_text = self.raw_yaml_editor.toPlainText()
            if yaml_text.strip():
                vendor_data = yaml.safe_load(yaml_text)
                if vendor_data:
                    # Update both original and current data
                    self.original_vendor_data = deepcopy(vendor_data)
                    self.vendor_data = deepcopy(vendor_data)
                    self.load_vendor_data()
                    if self.vendor_name:
                        self.vendor_changed.emit(self.vendor_name, vendor_data)
                    QMessageBox.information(self, "Sync", "UI updated from YAML successfully!")
                else:
                    QMessageBox.warning(self, "Sync Error", "Empty or invalid YAML data")
            else:
                QMessageBox.warning(self, "Sync Error", "No YAML data to sync")
        except yaml.YAMLError as e:
            QMessageBox.critical(self, "YAML Error", f"Failed to parse YAML:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to sync from YAML:\n{e}")

    def get_extraction_rules(self, table: QTableWidget) -> List[Dict]:
        """Get extraction rules from table"""
        rules = []
        for row in range(table.rowCount()):
            regex_item = table.item(row, 0)
            priority_item = table.item(row, 1)
            capture_group_item = table.item(row, 2)
            description_item = table.item(row, 3)

            if regex_item and regex_item.text().strip():
                rule = {
                    'regex': regex_item.text().strip(),
                    'priority': int(priority_item.text()) if priority_item and priority_item.text().strip() else 1,
                    'capture_group': int(
                        capture_group_item.text()) if capture_group_item and capture_group_item.text().strip() else 1,
                }

                if description_item and description_item.text().strip():
                    rule['description'] = description_item.text().strip()

                rules.append(rule)

        return rules

    def get_device_rules(self) -> List[Dict]:
        """Get device rules from tree widget"""
        rules = []
        for i in range(self.device_rules_tree.topLevelItemCount()):
            item = self.device_rules_tree.topLevelItem(i)
            rule_data = item.data(0, Qt.ItemDataRole.UserRole)
            if rule_data:
                rules.append(rule_data)
        return rules

    # Button handlers (same as before but with proper change tracking)
    def add_pattern_row(self, table: QTableWidget, is_definitive: bool = False):
        """Add a new pattern row to the table"""
        row = table.rowCount()
        table.insertRow(row)

        if is_definitive:
            table.setItem(row, 0, QTableWidgetItem(""))  # Pattern
            table.setItem(row, 1, QTableWidgetItem("100"))  # Confidence
            table.setItem(row, 2, QTableWidgetItem(""))  # Description
        else:
            table.setItem(row, 0, QTableWidgetItem(""))  # Pattern

        self.on_form_changed()

    def add_simple_pattern(self, table: QTableWidget):
        """Add a simple pattern row"""
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(""))
        self.on_form_changed()

    def add_oid_row(self):
        """Add a new OID row"""
        row = self.oids_table.rowCount()
        self.oids_table.insertRow(row)

        self.oids_table.setItem(row, 0, QTableWidgetItem(""))  # Name
        self.oids_table.setItem(row, 1, QTableWidgetItem(""))  # OID
        self.oids_table.setItem(row, 2, QTableWidgetItem("1"))  # Priority
        self.oids_table.setItem(row, 3, QTableWidgetItem(""))  # Description

        # Definitive checkbox
        checkbox = QCheckBox()
        checkbox.stateChanged.connect(self.on_form_changed)
        self.oids_table.setCellWidget(row, 4, checkbox)

        self.on_form_changed()

    def add_extraction_row(self, table: QTableWidget):
        """Add a new extraction rule row"""
        row = table.rowCount()
        table.insertRow(row)

        table.setItem(row, 0, QTableWidgetItem(""))  # Regex
        table.setItem(row, 1, QTableWidgetItem("1"))  # Priority
        table.setItem(row, 2, QTableWidgetItem("1"))  # Capture Group
        table.setItem(row, 3, QTableWidgetItem(""))  # Description

        self.on_form_changed()

    def remove_selected_rows(self, table: QTableWidget):
        """Remove selected rows from table"""
        selected_rows = set()
        for item in table.selectedItems():
            selected_rows.add(item.row())

        for row in sorted(selected_rows, reverse=True):
            table.removeRow(row)

        if selected_rows:
            self.on_form_changed()

    def add_device_rule(self):
        """Add a new device type rule"""
        rule_name, ok = QInputDialog.getText(self, "New Device Rule", "Enter rule name:")
        if ok and rule_name.strip():
            rule = {
                'name': rule_name.strip(),
                'priority': 1,
                'description': '',
                'conditions': []
            }

            item = QTreeWidgetItem([rule['name'], str(rule['priority']), rule['description']])
            item.setData(0, Qt.ItemDataRole.UserRole, rule)
            self.device_rules_tree.addTopLevelItem(item)
            self.on_form_changed()

    def edit_device_rule(self):
        """Edit selected device rule"""
        current_item = self.device_rules_tree.currentItem()
        if current_item:
            rule_data = current_item.data(0, Qt.ItemDataRole.UserRole)
            # Implementation for editing device rules would go here
            # For now, just allow name editing
            new_name, ok = QInputDialog.getText(self, "Edit Rule", "Rule name:", text=rule_data.get('name', ''))
            if ok and new_name.strip():
                rule_data['name'] = new_name.strip()
                current_item.setText(0, new_name.strip())
                current_item.setData(0, Qt.ItemDataRole.UserRole, rule_data)
                self.on_form_changed()

    def remove_device_rule(self):
        """Remove selected device rule"""
        selected_items = self.device_rules_tree.selectedItems()
        for item in selected_items:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                self.device_rules_tree.takeTopLevelItem(
                    self.device_rules_tree.indexOfTopLevelItem(item)
                )

        if selected_items:
            self.on_form_changed()

    def import_oid_template(self):
        """Import OID template"""
        templates = {
            "Standard Entity MIB": [
                ("Entity Model Name", "1.3.6.1.2.1.47.1.1.1.1.13.1", "1", "Standard Entity MIB model name"),
                ("Entity Serial Number", "1.3.6.1.2.1.47.1.1.1.1.11.1", "1", "Standard Entity MIB serial number"),
                (
                    "Entity Hardware Revision", "1.3.6.1.2.1.47.1.1.1.1.8.1", "2",
                    "Standard Entity MIB hardware revision"),
            ],
            "Standard System MIB": [
                ("System Description", "1.3.6.1.2.1.1.1.0", "1", "System description"),
                ("System Object ID", "1.3.6.1.2.1.1.2.0", "1", "System object identifier"),
                ("System Name", "1.3.6.1.2.1.1.5.0", "2", "System name"),
                ("System Contact", "1.3.6.1.2.1.1.4.0", "3", "System contact"),
                ("System Location", "1.3.6.1.2.1.1.6.0", "3", "System location"),
            ]
        }

        template_name, ok = QInputDialog.getItem(
            self, "Import OID Template", "Select template:",
            list(templates.keys()), 0, False
        )

        if ok and template_name:
            for name, oid, priority, description in templates[template_name]:
                row = self.oids_table.rowCount()
                self.oids_table.insertRow(row)

                self.oids_table.setItem(row, 0, QTableWidgetItem(name))
                self.oids_table.setItem(row, 1, QTableWidgetItem(oid))
                self.oids_table.setItem(row, 2, QTableWidgetItem(priority))
                self.oids_table.setItem(row, 3, QTableWidgetItem(description))

                checkbox = QCheckBox()
                checkbox.stateChanged.connect(self.on_form_changed)
                self.oids_table.setCellWidget(row, 4, checkbox)

            self.on_form_changed()

    def validate_yaml(self):
        """Validate the raw YAML"""
        try:
            yaml.safe_load(self.raw_yaml_editor.toPlainText())
            QMessageBox.information(self, "Validation", "YAML is valid!")
        except yaml.YAMLError as e:
            QMessageBox.warning(self, "Validation Error", f"YAML validation failed:\n{e}")

    def format_yaml(self):
        """Format the raw YAML"""
        try:
            data = yaml.safe_load(self.raw_yaml_editor.toPlainText())
            formatted = yaml.dump(data, default_flow_style=False, sort_keys=False, indent=2)
            self.raw_yaml_editor.setPlainText(formatted)
        except yaml.YAMLError as e:
            QMessageBox.warning(self, "Format Error", f"Cannot format invalid YAML:\n{e}")


class VendorFingerprintEditor(QWidget):
    """Main vendor fingerprint editor widget with complete data preservation"""

    def __init__(self, parent=None, theme_manager=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.current_theme = 'cyberpunk'
        self.yaml_data = {}
        self.yaml_file = None
        self.current_vendor = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()

        new_btn = QPushButton("New")
        open_btn = QPushButton("Open")
        save_btn = QPushButton("Save")
        save_as_btn = QPushButton("Save As...")
        validate_btn = QPushButton("Validate All")
        export_btn = QPushButton("Export")

        new_btn.clicked.connect(self.new_file)
        open_btn.clicked.connect(self.open_file)
        save_btn.clicked.connect(self.save_file)
        save_as_btn.clicked.connect(self.save_as_file)
        validate_btn.clicked.connect(self.validate_all)
        export_btn.clicked.connect(self.export_file)

        toolbar.addWidget(new_btn)
        toolbar.addWidget(open_btn)
        toolbar.addWidget(save_btn)
        toolbar.addWidget(save_as_btn)
        toolbar.addWidget(validate_btn)
        toolbar.addWidget(export_btn)
        toolbar.addStretch()

        layout.addLayout(toolbar)

        # Data preservation notice
        notice = QLabel("🛡️ DATA PRESERVATION MODE: All existing YAML fields are preserved during editing")
        notice.setStyleSheet(
            "background: #e8f5e8; color: #2d5a2d; padding: 8px; border: 1px solid #4caf50; border-radius: 4px; font-weight: bold;")
        layout.addWidget(notice)

        # Main content area
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - vendor list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        left_layout.addWidget(QLabel("Vendors:"))

        self.vendor_list = QTreeWidget()
        self.vendor_list.setHeaderLabels(["Vendor", "Enterprise OID"])
        self.vendor_list.itemClicked.connect(self.on_vendor_selected)

        vendor_buttons = QHBoxLayout()
        add_vendor_btn = QPushButton("Add Vendor")
        remove_vendor_btn = QPushButton("Remove Vendor")
        clone_vendor_btn = QPushButton("Clone Vendor")

        add_vendor_btn.clicked.connect(self.add_vendor)
        remove_vendor_btn.clicked.connect(self.remove_vendor)
        clone_vendor_btn.clicked.connect(self.clone_vendor)

        vendor_buttons.addWidget(add_vendor_btn)
        vendor_buttons.addWidget(remove_vendor_btn)
        vendor_buttons.addWidget(clone_vendor_btn)

        left_layout.addWidget(self.vendor_list)
        left_layout.addLayout(vendor_buttons)

        # Right panel - vendor editor
        self.vendor_editor = VendorEditorWidget()
        self.vendor_editor.vendor_changed.connect(self.on_vendor_changed)

        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(self.vendor_editor)
        main_splitter.setSizes([300, 700])

        layout.addWidget(main_splitter)

        # Status bar
        self.status_label = QLabel("Ready - Data preservation mode active")
        layout.addWidget(self.status_label)

    def apply_theme(self, theme_manager=None, theme_name: str = None):
        """Apply theme to the widget"""
        if theme_manager:
            self.theme_manager = theme_manager
        if theme_name:
            self.current_theme = theme_name

        if self.theme_manager and self.current_theme:
            try:
                self.theme_manager.apply_theme(self, self.current_theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to vendor fingerprint editor: {e}")

    def new_file(self):
        """Create a new fingerprint file"""
        self.yaml_data = {
            'version': '2.2',
            'metadata': {
                'description': 'Custom SNMP vendor fingerprinting configuration',
                'last_updated': '2025-01-01',
                'contributors': ['user']
            },
            'vendors': {}
        }
        self.yaml_file = None
        self.current_vendor = None
        self.vendor_editor.clear_form()
        self.load_vendor_list()
        self.status_label.setText("New file created - Data preservation mode active")

    def open_file(self):
        """Open an existing fingerprint file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Vendor Fingerprint File", "",
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.yaml_data = yaml.safe_load(f)

                self.yaml_file = file_path
                self.current_vendor = None
                self.vendor_editor.clear_form()
                self.load_vendor_list()

                vendor_count = len(self.yaml_data.get('vendors', {}))
                self.status_label.setText(f"Opened: {file_path} ({vendor_count} vendors) - Data preservation active")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

    def save_file(self):
        """Save the current file"""
        if not self.yaml_file:
            self.save_as_file()
            return

        try:
            # Ensure current vendor data is saved with preservation
            if self.current_vendor and self.vendor_editor._form_dirty:
                current_data = self.vendor_editor.get_vendor_data_preserved()
                self.yaml_data.setdefault('vendors', {})[self.current_vendor] = current_data

            with open(self.yaml_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.yaml_data, f, default_flow_style=False, sort_keys=False, indent=2)

            self.vendor_editor._form_dirty = False
            self.status_label.setText(f"Saved: {self.yaml_file} - All data preserved")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")

    def save_as_file(self):
        """Save the file with a new name"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Vendor Fingerprint File", "",
            "YAML Files (*.yaml);;All Files (*)"
        )

        if file_path:
            self.yaml_file = file_path
            self.save_file()

    def validate_all(self):
        """Validate all vendor configurations with enhanced device type checking"""
        errors = []

        # Ensure current vendor is saved first
        if self.current_vendor and self.vendor_editor._form_dirty:
            current_data = self.vendor_editor.get_vendor_data_preserved()
            self.yaml_data.setdefault('vendors', {})[self.current_vendor] = current_data

        vendors = self.yaml_data.get('vendors', {})
        for vendor_name, vendor_data in vendors.items():
            # Basic validation
            if not vendor_data.get('display_name'):
                errors.append(f"{vendor_name}: Missing display name")

            if not vendor_data.get('enterprise_oid'):
                errors.append(f"{vendor_name}: Missing enterprise OID")

            # Validate detection patterns
            detection_patterns = vendor_data.get('detection_patterns', [])
            exclusion_patterns = vendor_data.get('exclusion_patterns', [])

            if not detection_patterns and not vendor_data.get('definitive_patterns'):
                errors.append(f"{vendor_name}: No detection or definitive patterns defined")

            # Validate OIDs
            fingerprint_oids = vendor_data.get('fingerprint_oids', [])
            for i, oid in enumerate(fingerprint_oids):
                if not oid.get('name'):
                    errors.append(f"{vendor_name}: OID {i + 1} missing name")
                if not oid.get('oid'):
                    errors.append(f"{vendor_name}: OID {i + 1} missing OID string")

            # CRITICAL: Validate device_types vs device_type_rules consistency
            device_types = vendor_data.get('device_types', [])
            device_type_rules = vendor_data.get('device_type_rules', {})

            # Check for device types without corresponding rules
            for device_type in device_types:
                if device_type not in device_type_rules:
                    errors.append(
                        f"{vendor_name}: Device type '{device_type}' has no matching rule in device_type_rules (will show as 'device')")

            # Check for rules without corresponding device types (less critical)
            for rule_name in device_type_rules.keys():
                if rule_name not in device_types:
                    errors.append(
                        f"{vendor_name}: Device rule '{rule_name}' has no matching entry in device_types (rule unused)")

            # Validate device type rules structure
            for rule_name, rule_data in device_type_rules.items():
                if not isinstance(rule_data, dict):
                    errors.append(f"{vendor_name}: Device rule '{rule_name}' must be a dictionary")
                    continue

                if 'priority' not in rule_data:
                    errors.append(f"{vendor_name}: Device rule '{rule_name}' missing priority")

                if 'definitive_patterns' not in rule_data and 'mandatory_patterns' not in rule_data:
                    errors.append(f"{vendor_name}: Device rule '{rule_name}' has no patterns defined")

        # Show results in detailed dialog
        if errors:
            self.show_validation_results(errors, len(vendors))
        else:
            QMessageBox.information(self, "Validation", f"✅ All {len(vendors)} vendor configurations are valid!")

    def show_validation_results(self, errors: List[str], vendor_count: int):
        """Show detailed validation results in a dialog with copy functionality"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Validation Results")
        dialog.resize(800, 600)

        # Apply theme to the entire dialog
        if hasattr(self, 'theme_manager') and self.theme_manager:
            try:
                self.theme_manager.apply_theme(dialog, self.current_theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to validation dialog: {e}")

        layout = QVBoxLayout(dialog)

        # Header with summary - use palette colors instead of hardcoded
        header_label = QLabel(f"Found {len(errors)} validation issues across {vendor_count} vendors:")
        header_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        # Scrollable text area with all errors
        text_area = QPlainTextEdit()
        text_area.setPlainText("\n".join(errors))
        text_area.setReadOnly(True)
        text_area.setFont(QFont("Consolas", 10))  # Monospace font for better readability

        # Apply theme-aware styling - let the theme manager handle colors
        if hasattr(self, 'theme_manager') and self.theme_manager:
            try:
                # Apply current theme to the text area
                self.theme_manager.apply_theme(text_area, self.current_theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to validation dialog text area: {e}")

        # Only set minimal styling that doesn't conflict with themes
        text_area.setStyleSheet("""
            QPlainTextEdit {
                border: 1px solid palette(mid);
                padding: 10px;
                font-family: "Consolas", "Monaco", "Courier New", monospace;
            }
        """)

        layout.addWidget(text_area)

        # Button layout
        button_layout = QHBoxLayout()

        # Copy to clipboard button
        copy_button = QPushButton("Copy All Errors")
        copy_button.clicked.connect(lambda: self.copy_to_clipboard("\n".join(errors)))

        # Save to file button
        save_button = QPushButton("Save to File")
        save_button.clicked.connect(lambda: self.save_errors_to_file(errors))

        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        close_button.setDefault(True)

        button_layout.addWidget(copy_button)
        button_layout.addWidget(save_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

        # Show dialog
        dialog.exec()

    def copy_to_clipboard(self, text: str):
        """Copy text to system clipboard"""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            # Show brief confirmation
            self.status_label.setText("Validation errors copied to clipboard")
            QTimer.singleShot(3000, lambda: self.status_label.setText("Ready - Data preservation mode active"))

        except Exception as e:
            QMessageBox.warning(self, "Copy Error", f"Failed to copy to clipboard:\n{e}")

    def save_errors_to_file(self, errors: List[str]):
        """Save validation errors to a file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Validation Errors",
            "validation_errors.txt",
            "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"Validation Errors Report\n")
                    f.write(f"Generated: {QDateTime.currentDateTime().toString()}\n")
                    f.write(f"Total Errors: {len(errors)}\n")
                    f.write("=" * 50 + "\n\n")

                    for i, error in enumerate(errors, 1):
                        f.write(f"{i:3d}. {error}\n")

                self.status_label.setText(f"Validation errors saved to: {file_path}")
                QTimer.singleShot(3000, lambda: self.status_label.setText("Ready - Data preservation mode active"))

            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save errors to file:\n{e}")

    def export_file(self):
        """Export to different formats"""
        QMessageBox.information(self, "Export", "Export functionality not yet implemented")

    def load_vendor_list(self):
        """Load the vendor list from YAML data"""
        self.vendor_list.clear()

        vendors = self.yaml_data.get('vendors', {})
        for vendor_name, vendor_data in vendors.items():
            item = QTreeWidgetItem([
                vendor_data.get('display_name', vendor_name),
                vendor_data.get('enterprise_oid', '')
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, vendor_name)
            self.vendor_list.addTopLevelItem(item)

    def on_vendor_selected(self, item: QTreeWidgetItem):
        """Handle vendor selection with data preservation"""
        vendor_name = item.data(0, Qt.ItemDataRole.UserRole)

        # Don't reload if same vendor is selected
        if vendor_name == self.current_vendor:
            return

        vendor_data = self.yaml_data.get('vendors', {}).get(vendor_name, {})

        # Update the vendor editor with preserved data
        self.current_vendor = vendor_name
        self.vendor_editor.set_vendor_data(vendor_name, vendor_data)

        self.status_label.setText(
            f"Editing vendor: {vendor_data.get('display_name', vendor_name)} - Data preservation active")

    def on_vendor_changed(self, vendor_name: str, vendor_data: Dict):
        """Handle vendor data changes with preservation"""
        if 'vendors' not in self.yaml_data:
            self.yaml_data['vendors'] = {}

        # Store the complete preserved data
        self.yaml_data['vendors'][vendor_name] = vendor_data

        # Update the vendor list display
        for i in range(self.vendor_list.topLevelItemCount()):
            item = self.vendor_list.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == vendor_name:
                item.setText(0, vendor_data.get('display_name', vendor_name))
                item.setText(1, vendor_data.get('enterprise_oid', ''))
                break

    def add_vendor(self):
        """Add a new vendor"""
        vendor_name, ok = QInputDialog.getText(
            self, "New Vendor", "Enter vendor name:"
        )

        if ok and vendor_name.strip():
            vendor_name = vendor_name.strip().lower().replace(' ', '_')

            if vendor_name in self.yaml_data.get('vendors', {}):
                QMessageBox.warning(self, "Error", "Vendor already exists!")
                return

            if 'vendors' not in self.yaml_data:
                self.yaml_data['vendors'] = {}

            self.yaml_data['vendors'][vendor_name] = {
                'display_name': vendor_name.replace('_', ' ').title(),
                'enterprise_oid': '',
                'detection_patterns': [],
                'device_types': []
            }

            self.load_vendor_list()

            # Select the new vendor
            for i in range(self.vendor_list.topLevelItemCount()):
                item = self.vendor_list.topLevelItem(i)
                if item.data(0, Qt.ItemDataRole.UserRole) == vendor_name:
                    self.vendor_list.setCurrentItem(item)
                    self.on_vendor_selected(item)
                    break

    def remove_vendor(self):
        """Remove the selected vendor"""
        current_item = self.vendor_list.currentItem()
        if not current_item:
            return

        vendor_name = current_item.data(0, Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete vendor '{vendor_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if 'vendors' in self.yaml_data and vendor_name in self.yaml_data['vendors']:
                del self.yaml_data['vendors'][vendor_name]

                # Clear editor if this was the current vendor
                if vendor_name == self.current_vendor:
                    self.current_vendor = None
                    self.vendor_editor.clear_form()

                self.load_vendor_list()
                self.status_label.setText(f"Deleted vendor: {vendor_name} - Data preservation active")

    def clone_vendor(self):
        """Clone the selected vendor"""
        current_item = self.vendor_list.currentItem()
        if not current_item:
            return

        original_vendor = current_item.data(0, Qt.ItemDataRole.UserRole)

        new_name, ok = QInputDialog.getText(
            self, "Clone Vendor", "Enter new vendor name:"
        )

        if ok and new_name.strip():
            new_name = new_name.strip().lower().replace(' ', '_')

            if new_name in self.yaml_data.get('vendors', {}):
                QMessageBox.warning(self, "Error", "Vendor already exists!")
                return

            # Deep copy the vendor data to preserve everything
            original_data = self.yaml_data['vendors'][original_vendor]
            cloned_data = deepcopy(original_data)
            cloned_data['display_name'] = new_name.replace('_', ' ').title()

            self.yaml_data['vendors'][new_name] = cloned_data
            self.load_vendor_list()

            # Select the cloned vendor
            for i in range(self.vendor_list.topLevelItemCount()):
                item = self.vendor_list.topLevelItem(i)
                if item.data(0, Qt.ItemDataRole.UserRole) == new_name:
                    self.vendor_list.setCurrentItem(item)
                    self.on_vendor_selected(item)
                    break


# Wrapper class for integration with terminal tabs
class VendorFingerprintWrapper:
    """Wrapper class to standardize vendor fingerprint editor interface"""

    def __init__(self, editor_widget):
        self.editor = editor_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.editor, 'cleanup'):
            self.editor.cleanup()

    def apply_theme(self, theme_manager, theme_name):
        """Apply theme to the editor widget"""
        try:
            self.editor.apply_theme(theme_manager, theme_name)
        except Exception as e:
            logger.warning(f"Could not apply theme to vendor fingerprint editor: {e}")


# Example usage and testing
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Create and show the widget
    editor = VendorFingerprintEditor()
    editor.setWindowTitle("Vendor Fingerprint Editor - Data Preservation Version")
    editor.resize(1200, 800)
    editor.show()

    sys.exit(app.exec())