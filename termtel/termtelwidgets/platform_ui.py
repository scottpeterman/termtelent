#!/usr/bin/env python3
"""
TerminalTelemetry Platform Configuration Tool
Standalone application for managing platform configurations

This is an advanced tool for power users to add new network device platforms,
customize commands, field mappings, and capabilities.

WARNING: Incorrect platform configurations can break telemetry functionality.
         Always backup your platforms.json before making changes.
"""

import sys
import os
import json
import traceback
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QMenuBar, QStatusBar, QMessageBox, QFileDialog,
                             QPushButton, QLabel, QTextEdit, QTabWidget, QSplitter,
                             QGroupBox, QFormLayout, QLineEdit, QDialog, QComboBox,
                             QCheckBox, QTableWidget, QTableWidgetItem, QScrollArea,
                             QSpinBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QFont, QPixmap
from typing import Dict, Any

# Try to import from the main package, with fallbacks
try:
    from termtel.termtelwidgets.platform_config_manager import PlatformConfigManager
    from termtel.helpers.resource_manager import resource_manager

    PACKAGE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import from termtel package: {e}")
    print("Running in standalone mode with limited functionality...")
    PACKAGE_AVAILABLE = False


    # Minimal fallback implementations
    class PlatformConfigManager:
        def __init__(self, config_path=None):
            self.platforms = {}
            self.config_path = config_path or "config"

        def get_available_platforms(self):
            return list(self.platforms.keys())

        def get_platform(self, platform_name):
            return self.platforms.get(platform_name)

        def validate_platform_config(self, config):
            errors = []
            if not config.get('name'):
                errors.append("Platform name is required")
            if not config.get('display_name'):
                errors.append("Display name is required")
            if not config.get('netmiko', {}).get('device_type'):
                errors.append("Netmiko device type is required")
            return errors

        def add_user_platform(self, config):
            # Basic implementation - would need to save to file
            platform_name = config['name']
            self.platforms[platform_name] = config
            return True


    # Create minimal resource_manager if not available
    class ResourceManager:
        def get_resource_path(self, *args):
            return None

        def get_platforms_config(self):
            return None


    resource_manager = ResourceManager()


# ============================================================================
# Platform Configuration Dialog Classes
# ============================================================================

class PlatformConfigDialog(QDialog):
    """Dialog for creating/editing platform configurations"""

    platform_created = pyqtSignal(str, dict)  # platform_name, config_data

    def __init__(self, platform_config_manager, existing_platform=None, parent=None):
        super().__init__(parent)
        self.config_manager = platform_config_manager
        self.existing_platform = existing_platform
        self.is_editing = existing_platform is not None

        self.setWindowTitle("Platform Configuration" + (" - Edit" if self.is_editing else " - New"))
        self.setModal(True)
        self.resize(900, 700)

        self._setup_ui()

        if self.is_editing:
            self._load_existing_platform()

    def _setup_ui(self):
        """Setup the configuration UI"""
        layout = QVBoxLayout(self)

        # Create tab widget for different configuration sections
        tabs = QTabWidget()

        # Basic Info Tab
        basic_tab = self._create_basic_info_tab()
        tabs.addTab(basic_tab, "Basic Info")

        # Netmiko Configuration Tab
        netmiko_tab = self._create_netmiko_tab()
        tabs.addTab(netmiko_tab, "Connection")

        # Commands Tab
        commands_tab = self._create_commands_tab()
        tabs.addTab(commands_tab, "Commands")

        # Field Mappings Tab
        mappings_tab = self._create_mappings_tab()
        tabs.addTab(mappings_tab, "Field Mappings")

        # Capabilities Tab
        capabilities_tab = self._create_capabilities_tab()
        tabs.addTab(capabilities_tab, "Capabilities")

        # Template Configuration Tab
        template_tab = self._create_template_tab()
        tabs.addTab(template_tab, "Templates")

        layout.addWidget(tabs)

        # Buttons
        button_layout = self._create_button_layout()
        layout.addLayout(button_layout)

    def _create_basic_info_tab(self):
        """Create basic information tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Platform name
        self.platform_name_edit = QLineEdit()
        self.platform_name_edit.setPlaceholderText("e.g., fortinet_fortigate")
        layout.addRow("Platform Name:", self.platform_name_edit)

        # Display name
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setPlaceholderText("e.g., Fortinet FortiGate")
        layout.addRow("Display Name:", self.display_name_edit)

        # Description
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(100)
        self.description_edit.setPlaceholderText("Brief description of the platform")
        layout.addRow("Description:", self.description_edit)

        return tab

    def _create_netmiko_tab(self):
        """Create netmiko configuration tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Device type (most important - must match netmiko supported types)
        self.device_type_combo = QComboBox()
        self.device_type_combo.setEditable(True)

        # Populate with known netmiko device types
        netmiko_types = [
            "cisco_ios", "cisco_xe", "cisco_nxos", "cisco_asa",
            "arista_eos", "juniper_junos", "hp_comware", "hp_procurve",
            "fortinet", "paloalto_panos", "checkpoint_gaia",
            "linux", "mikrotik_routeros", "vyos", "dell_force10",
            "alcatel_aos", "avaya_ers", "avaya_vsp", "brocade_fastiron",
            "brocade_netiron", "brocade_nos", "brocade_vdx", "brocade_vyos",
            "calix_b6", "ciena_saos", "cisco_s300", "dell_os6", "dell_os9",
            "dell_os10", "dell_powerconnect", "eltex", "enterasys",
            "extreme", "extreme_ers", "extreme_exos", "extreme_netiron",
            "extreme_nos", "extreme_slx", "extreme_vdx", "extreme_vsp",
            "extreme_wing", "f5_ltm", "f5_tmsh", "huawei", "huawei_olt",
            "huawei_smartax", "huawei_vrpv8", "mellanox", "netapp_cdot",
            "netscaler", "ovs_linux", "pluribus", "quanta_mesh",
            "ruckus_fastiron", "ubiquiti_edge", "ubiquiti_edgeswitch"
        ]

        self.device_type_combo.addItems(sorted(netmiko_types))
        layout.addRow("Netmiko Device Type:", self.device_type_combo)

        # Fast CLI
        self.fast_cli_check = QCheckBox()
        layout.addRow("Fast CLI:", self.fast_cli_check)

        # Timeouts
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        layout.addRow("Command Timeout (sec):", self.timeout_spin)

        self.auth_timeout_spin = QSpinBox()
        self.auth_timeout_spin.setRange(5, 60)
        self.auth_timeout_spin.setValue(10)
        layout.addRow("Auth Timeout (sec):", self.auth_timeout_spin)

        # Help text
        help_text = QTextEdit()
        help_text.setMaximumHeight(100)
        help_text.setReadOnly(True)
        help_text.setPlainText(
            "Device Type must match a netmiko supported driver. "
            "Fast CLI enables faster command execution but may not work on all devices. "
            "Adjust timeouts based on device response times."
        )
        layout.addRow("Help:", help_text)

        return tab

    def _create_commands_tab(self):
        """Create commands configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Instructions
        instructions = QTextEdit()
        instructions.setMaximumHeight(80)
        instructions.setReadOnly(True)
        instructions.setPlainText(
            "Define commands for each telemetry function. Use {parameter_name} for dynamic parameters. "
            "Template filename should match your TextFSM template in templates/textfsm/{platform}/"
        )
        layout.addWidget(instructions)

        # Commands table
        self.commands_table = QTableWidget(0, 5)
        self.commands_table.setHorizontalHeaderLabels([
            "Function", "Command", "Template File", "Timeout", "Description"
        ])

        # Pre-populate with standard functions
        standard_functions = [
            ("system_info", "show version", "show_version.textfsm", "15", "System information"),
            ("cdp_neighbors", "show cdp neighbors detail", "show_cdp_neighbors_detail.textfsm", "30", "CDP neighbors"),
            ("lldp_neighbors", "show lldp neighbors detail", "show_lldp_neighbors_detail.textfsm", "30",
             "LLDP neighbors"),
            ("arp_table", "show ip arp", "show_ip_arp.textfsm", "20", "ARP table"),
            ("route_table", "show ip route", "show_ip_route.textfsm", "30", "Routing table"),
            ("route_table_vrf", "show ip route vrf {vrf_name}", "show_ip_route.textfsm", "30", "VRF routing table"),
            ("vrf_list", "show vrf", "show_vrf.textfsm", "15", "VRF list"),
            (
            "interface_status", "show ip interface brief", "show_ip_interface_brief.textfsm", "20", "Interface status"),
            ("cpu_utilization", "show processes cpu", "show_processes_cpu.textfsm", "15", "CPU utilization"),
            ("logs", "show logging", "show_logging.textfsm", "20", "System logs")
        ]

        self.commands_table.setRowCount(len(standard_functions))
        for row, (function, command, template, timeout, description) in enumerate(standard_functions):
            self.commands_table.setItem(row, 0, QTableWidgetItem(function))
            self.commands_table.setItem(row, 1, QTableWidgetItem(command))
            self.commands_table.setItem(row, 2, QTableWidgetItem(template))
            self.commands_table.setItem(row, 3, QTableWidgetItem(timeout))
            self.commands_table.setItem(row, 4, QTableWidgetItem(description))

        self.commands_table.resizeColumnsToContents()
        layout.addWidget(self.commands_table)

        # Add/Remove buttons
        button_layout = QHBoxLayout()

        add_cmd_btn = QPushButton("Add Command")
        add_cmd_btn.clicked.connect(self._add_command_row)
        button_layout.addWidget(add_cmd_btn)

        remove_cmd_btn = QPushButton("Remove Selected")
        remove_cmd_btn.clicked.connect(self._remove_command_row)
        button_layout.addWidget(remove_cmd_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        return tab

    def _create_mappings_tab(self):
        """Create field mappings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Scrollable area for mappings
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Protocol mappings
        protocol_group = QGroupBox("Protocol Mappings")
        protocol_layout = QVBoxLayout(protocol_group)

        self.protocol_mappings_table = QTableWidget(0, 2)
        self.protocol_mappings_table.setHorizontalHeaderLabels(["Device Code", "Normalized Name"])

        # Common protocol mappings
        common_protocols = [
            ("S", "Static"), ("C", "Connected"), ("L", "Local"),
            ("O", "OSPF"), ("B", "BGP"), ("D", "EIGRP"), ("R", "RIP"),
            ("I", "IGRP"), ("M", "Mobile"), ("N", "NAT")
        ]

        self.protocol_mappings_table.setRowCount(len(common_protocols))
        for row, (code, name) in enumerate(common_protocols):
            self.protocol_mappings_table.setItem(row, 0, QTableWidgetItem(code))
            self.protocol_mappings_table.setItem(row, 1, QTableWidgetItem(name))

        protocol_layout.addWidget(self.protocol_mappings_table)

        # Protocol mapping buttons
        protocol_btn_layout = QHBoxLayout()
        add_protocol_btn = QPushButton("Add Mapping")
        add_protocol_btn.clicked.connect(lambda: self._add_mapping_row(self.protocol_mappings_table))
        protocol_btn_layout.addWidget(add_protocol_btn)

        remove_protocol_btn = QPushButton("Remove Selected")
        remove_protocol_btn.clicked.connect(lambda: self._remove_mapping_row(self.protocol_mappings_table))
        protocol_btn_layout.addWidget(remove_protocol_btn)
        protocol_btn_layout.addStretch()

        protocol_layout.addLayout(protocol_btn_layout)
        scroll_layout.addWidget(protocol_group)

        # Interface type mappings
        interface_group = QGroupBox("Interface Type Mappings (Optional)")
        interface_layout = QVBoxLayout(interface_group)

        self.interface_mappings_table = QTableWidget(0, 2)
        self.interface_mappings_table.setHorizontalHeaderLabels(["Abbreviation", "Full Name"])

        # Common interface mappings
        common_interfaces = [
            ("Gi", "GigabitEthernet"), ("Te", "TenGigabitEthernet"),
            ("Fa", "FastEthernet"), ("Et", "Ethernet"),
            ("Se", "Serial"), ("Lo", "Loopback")
        ]

        self.interface_mappings_table.setRowCount(len(common_interfaces))
        for row, (abbrev, full) in enumerate(common_interfaces):
            self.interface_mappings_table.setItem(row, 0, QTableWidgetItem(abbrev))
            self.interface_mappings_table.setItem(row, 1, QTableWidgetItem(full))

        interface_layout.addWidget(self.interface_mappings_table)

        # Interface mapping buttons
        interface_btn_layout = QHBoxLayout()
        add_interface_btn = QPushButton("Add Mapping")
        add_interface_btn.clicked.connect(lambda: self._add_mapping_row(self.interface_mappings_table))
        interface_btn_layout.addWidget(add_interface_btn)

        remove_interface_btn = QPushButton("Remove Selected")
        remove_interface_btn.clicked.connect(lambda: self._remove_mapping_row(self.interface_mappings_table))
        interface_btn_layout.addWidget(remove_interface_btn)
        interface_btn_layout.addStretch()

        interface_layout.addLayout(interface_btn_layout)
        scroll_layout.addWidget(interface_group)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        return tab

    def _create_capabilities_tab(self):
        """Create capabilities configuration tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # VRF support
        self.supports_vrf_check = QCheckBox()
        layout.addRow("Supports VRF:", self.supports_vrf_check)

        # CDP support
        self.supports_cdp_check = QCheckBox()
        layout.addRow("Supports CDP:", self.supports_cdp_check)

        # LLDP support
        self.supports_lldp_check = QCheckBox()
        layout.addRow("Supports LLDP:", self.supports_lldp_check)

        # Temperature monitoring
        self.supports_temperature_check = QCheckBox()
        layout.addRow("Supports Temperature:", self.supports_temperature_check)

        # Primary neighbor protocol
        self.neighbor_protocol_combo = QComboBox()
        self.neighbor_protocol_combo.addItems(["cdp", "lldp", "both"])
        layout.addRow("Primary Neighbor Protocol:", self.neighbor_protocol_combo)

        # Help text
        help_text = QTextEdit()
        help_text.setMaximumHeight(120)
        help_text.setReadOnly(True)
        help_text.setPlainText(
            "Capabilities help the system understand what features this platform supports:\n\n"
            "• VRF: Can the device handle multiple routing tables?\n"
            "• CDP: Does it support Cisco Discovery Protocol?\n"
            "• LLDP: Does it support Link Layer Discovery Protocol?\n"
            "• Temperature: Can we monitor temperature sensors?\n"
            "• Neighbor Protocol: Which protocol should be used primarily for neighbor discovery?"
        )
        layout.addRow("Help:", help_text)

        return tab

    def _create_template_tab(self):
        """Create template configuration tab"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # Template platform
        self.template_platform_edit = QLineEdit()
        self.template_platform_edit.setPlaceholderText("e.g., fortinet_fortigate")
        layout.addRow("Template Platform Name:", self.template_platform_edit)

        # Base path
        self.template_base_path_edit = QLineEdit()
        self.template_base_path_edit.setText("templates/textfsm")
        layout.addRow("Template Base Path:", self.template_base_path_edit)

        # Help text
        help_text = QTextEdit()
        help_text.setMaximumHeight(120)
        help_text.setReadOnly(True)
        help_text.setPlainText(
            "Template configuration tells the system where to find TextFSM templates:\n\n"
            "• Template Platform Name: Used as prefix for template files\n"
            "• Base Path: Directory containing template files\n\n"
            "Templates should be named: {platform}_{command}.textfsm\n"
            "Example: fortinet_fortigate_show_version.textfsm"
        )
        layout.addRow("Help:", help_text)

        return tab

    def _create_button_layout(self):
        """Create dialog buttons"""
        layout = QHBoxLayout()

        # Test Connection button
        test_btn = QPushButton("Test Configuration")
        test_btn.clicked.connect(self._test_configuration)
        layout.addWidget(test_btn)

        # Export button
        export_btn = QPushButton("Export JSON")
        export_btn.clicked.connect(self._export_configuration)
        layout.addWidget(export_btn)

        layout.addStretch()

        # Cancel and Save
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save Platform")
        save_btn.clicked.connect(self._save_platform)
        layout.addWidget(save_btn)

        return layout

    def _add_command_row(self):
        """Add new command row"""
        row = self.commands_table.rowCount()
        self.commands_table.insertRow(row)

        # Set default values
        self.commands_table.setItem(row, 0, QTableWidgetItem("new_command"))
        self.commands_table.setItem(row, 1, QTableWidgetItem("show something"))
        self.commands_table.setItem(row, 2, QTableWidgetItem("show_something.textfsm"))
        self.commands_table.setItem(row, 3, QTableWidgetItem("30"))
        self.commands_table.setItem(row, 4, QTableWidgetItem("Description"))

    def _remove_command_row(self):
        """Remove selected command row"""
        current_row = self.commands_table.currentRow()
        if current_row >= 0:
            self.commands_table.removeRow(current_row)

    def _add_mapping_row(self, table):
        """Add new mapping row"""
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(""))
        table.setItem(row, 1, QTableWidgetItem(""))

    def _remove_mapping_row(self, table):
        """Remove selected mapping row"""
        current_row = table.currentRow()
        if current_row >= 0:
            table.removeRow(current_row)

    def _collect_configuration(self) -> Dict[str, Any]:
        """Collect all configuration data from UI"""
        config = {
            "name": self.platform_name_edit.text().strip(),
            "display_name": self.display_name_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "netmiko": {
                "device_type": self.device_type_combo.currentText(),
                "fast_cli": self.fast_cli_check.isChecked(),
                "timeout": self.timeout_spin.value(),
                "auth_timeout": self.auth_timeout_spin.value()
            },
            "templates": {
                "platform": self.template_platform_edit.text().strip(),
                "base_path": self.template_base_path_edit.text().strip()
            },
            "commands": {},
            "field_mappings": {
                "protocols": {},
                "interface_types": {}
            },
            "capabilities": {
                "supports_vrf": self.supports_vrf_check.isChecked(),
                "supports_cdp": self.supports_cdp_check.isChecked(),
                "supports_lldp": self.supports_lldp_check.isChecked(),
                "supports_temperature": self.supports_temperature_check.isChecked(),
                "neighbor_protocol": self.neighbor_protocol_combo.currentText()
            }
        }

        # Collect commands
        for row in range(self.commands_table.rowCount()):
            function_item = self.commands_table.item(row, 0)
            command_item = self.commands_table.item(row, 1)
            template_item = self.commands_table.item(row, 2)
            timeout_item = self.commands_table.item(row, 3)
            desc_item = self.commands_table.item(row, 4)

            if function_item and command_item and template_item:
                function_name = function_item.text().strip()
                if function_name:
                    config["commands"][function_name] = {
                        "command": command_item.text().strip(),
                        "template": template_item.text().strip(),
                        "timeout": int(timeout_item.text()) if timeout_item and timeout_item.text().isdigit() else 30,
                        "description": desc_item.text().strip() if desc_item else ""
                    }

        # Collect protocol mappings
        for row in range(self.protocol_mappings_table.rowCount()):
            code_item = self.protocol_mappings_table.item(row, 0)
            name_item = self.protocol_mappings_table.item(row, 1)

            if code_item and name_item:
                code = code_item.text().strip()
                name = name_item.text().strip()
                if code and name:
                    config["field_mappings"]["protocols"][code] = name

        # Collect interface mappings
        for row in range(self.interface_mappings_table.rowCount()):
            abbrev_item = self.interface_mappings_table.item(row, 0)
            full_item = self.interface_mappings_table.item(row, 1)

            if abbrev_item and full_item:
                abbrev = abbrev_item.text().strip()
                full = full_item.text().strip()
                if abbrev and full:
                    config["field_mappings"]["interface_types"][abbrev] = full

        return config

    def _test_configuration(self):
        """Test the configuration for validity"""
        config = self._collect_configuration()
        errors = self.config_manager.validate_platform_config(config)

        if errors:
            error_text = "Configuration errors found:\n\n" + "\n".join(f"• {error}" for error in errors)
            QMessageBox.warning(self, "Configuration Errors", error_text)
        else:
            QMessageBox.information(self, "Configuration Valid", "Platform configuration is valid!")

    def _export_configuration(self):
        """Export configuration as JSON"""
        config = self._collect_configuration()

        try:
            json_text = json.dumps(config, indent=2)

            # Show in a dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Platform Configuration JSON")
            dialog.resize(600, 500)

            layout = QVBoxLayout(dialog)

            text_edit = QTextEdit()
            text_edit.setFont(QFont("Consolas", 10))
            text_edit.setPlainText(json_text)
            layout.addWidget(text_edit)

            button_layout = QHBoxLayout()
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            button_layout.addStretch()
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)
            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export configuration:\n{str(e)}")

    def _save_platform(self):
        """Save the platform configuration"""
        config = self._collect_configuration()

        # Validate first
        errors = self.config_manager.validate_platform_config(config)
        if errors:
            error_text = "Please fix these errors before saving:\n\n" + "\n".join(f"• {error}" for error in errors)
            QMessageBox.warning(self, "Configuration Errors", error_text)
            return

        # Save the configuration
        try:
            success = self.config_manager.add_user_platform(config)
            if success:
                platform_name = config["name"]
                self.platform_created.emit(platform_name, config)
                QMessageBox.information(self, "Success", f"Platform '{platform_name}' saved successfully!")
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to save platform configuration.")

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Error saving platform:\n{str(e)}")

    def _load_existing_platform(self):
        """Load existing platform data for editing"""
        if not self.existing_platform:
            return

        platform_def = self.config_manager.get_platform(self.existing_platform)
        if not platform_def:
            return

        # Load basic info - handle both dict and object formats
        if hasattr(platform_def, 'name'):
            # Object format
            self.platform_name_edit.setText(platform_def.name)
            self.display_name_edit.setText(platform_def.display_name)
            self.description_edit.setPlainText(platform_def.description)
        else:
            # Dict format
            self.platform_name_edit.setText(platform_def.get('name', ''))
            self.display_name_edit.setText(platform_def.get('display_name', ''))
            self.description_edit.setPlainText(platform_def.get('description', ''))


class PlatformManagerWidget(QWidget):
    """Widget for managing platform configurations in the main application"""

    def __init__(self, platform_config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = platform_config_manager
        self._setup_ui()

    def _setup_ui(self):
        """Setup platform manager UI"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Platform Configuration Manager")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title)

        # Platform list
        self.platform_table = QTableWidget(0, 4)
        self.platform_table.setHorizontalHeaderLabels([
            "Platform Name", "Display Name", "Netmiko Type", "Capabilities"
        ])
        layout.addWidget(self.platform_table)

        # Buttons
        button_layout = QHBoxLayout()

        self.add_platform_btn = QPushButton("Add New Platform")
        self.add_platform_btn.clicked.connect(self._add_new_platform)
        button_layout.addWidget(self.add_platform_btn)

        self.edit_platform_btn = QPushButton("Edit Selected")
        self.edit_platform_btn.clicked.connect(self._edit_selected_platform)
        button_layout.addWidget(self.edit_platform_btn)

        self.delete_platform_btn = QPushButton("Delete Selected")
        self.delete_platform_btn.clicked.connect(self._delete_selected_platform)
        button_layout.addWidget(self.delete_platform_btn)

        button_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_platform_list)
        button_layout.addWidget(self.refresh_btn)

        layout.addLayout(button_layout)

        # Load initial data
        self._refresh_platform_list()

    def _refresh_platform_list(self):
        """Refresh the platform list"""
        platforms = self.config_manager.get_available_platforms()
        self.platform_table.setRowCount(len(platforms))

        for row, platform_name in enumerate(platforms):
            platform_def = self.config_manager.get_platform(platform_name)
            if platform_def:
                # Platform name
                self.platform_table.setItem(row, 0, QTableWidgetItem(platform_name))

                # Handle both dict and object formats
                if hasattr(platform_def, 'display_name'):
                    # Object format
                    display_name = platform_def.display_name
                    device_type = platform_def.netmiko.device_type
                    capabilities = []
                    if platform_def.capabilities.supports_vrf:
                        capabilities.append("VRF")
                    if platform_def.capabilities.supports_cdp:
                        capabilities.append("CDP")
                    if platform_def.capabilities.supports_lldp:
                        capabilities.append("LLDP")
                    if platform_def.capabilities.supports_temperature:
                        capabilities.append("Temp")
                else:
                    # Dict format
                    display_name = platform_def.get('display_name', platform_name)
                    device_type = platform_def.get('netmiko', {}).get('device_type', 'unknown')
                    capabilities_data = platform_def.get('capabilities', {})
                    capabilities = []
                    if capabilities_data.get('supports_vrf'):
                        capabilities.append("VRF")
                    if capabilities_data.get('supports_cdp'):
                        capabilities.append("CDP")
                    if capabilities_data.get('supports_lldp'):
                        capabilities.append("LLDP")
                    if capabilities_data.get('supports_temperature'):
                        capabilities.append("Temp")

                # Display name
                self.platform_table.setItem(row, 1, QTableWidgetItem(display_name))

                # Netmiko type
                self.platform_table.setItem(row, 2, QTableWidgetItem(device_type))

                # Capabilities summary
                capabilities_text = ", ".join(capabilities) if capabilities else "Basic"
                self.platform_table.setItem(row, 3, QTableWidgetItem(capabilities_text))

        self.platform_table.resizeColumnsToContents()

    def _add_new_platform(self):
        """Add new platform configuration"""
        dialog = PlatformConfigDialog(self.config_manager, parent=self)
        dialog.platform_created.connect(self._on_platform_created)
        dialog.exec()

    def _edit_selected_platform(self):
        """Edit selected platform"""
        current_row = self.platform_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "No Selection", "Please select a platform to edit.")
            return

        platform_name_item = self.platform_table.item(current_row, 0)
        if platform_name_item:
            platform_name = platform_name_item.text()
            dialog = PlatformConfigDialog(self.config_manager, existing_platform=platform_name, parent=self)
            dialog.platform_created.connect(self._on_platform_updated)
            dialog.exec()

    def _delete_selected_platform(self):
        """Delete selected platform"""
        current_row = self.platform_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "No Selection", "Please select a platform to delete.")
            return

        platform_name_item = self.platform_table.item(current_row, 0)
        if platform_name_item:
            platform_name = platform_name_item.text()

            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete platform '{platform_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Delete platform (implementation would depend on config manager)
                self._refresh_platform_list()

    def _on_platform_created(self, platform_name: str, config_data: dict):
        """Handle new platform creation"""
        self._refresh_platform_list()
        QMessageBox.information(self, "Platform Added", f"Platform '{platform_name}' has been added successfully!")

    def _on_platform_updated(self, platform_name: str, config_data: dict):
        """Handle platform update"""
        self._refresh_platform_list()
        QMessageBox.information(self, "Platform Updated", f"Platform '{platform_name}' has been updated successfully!")


# ============================================================================
# Main Application Window
# ============================================================================

class PlatformConfigToolMainWindow(QMainWindow):
    """Main window for the platform configuration tool"""

    def __init__(self):
        super().__init__()

        # Initialize configuration manager
        self.config_manager = None
        self.platforms_file = None
        self.backup_created = False

        self.setWindowTitle("TerminalTelemetry Platform Configuration Tool v1.0")
        self.setGeometry(100, 100, 1400, 900)

        # Set application icon if available
        self._set_application_icon()

        self._setup_ui()
        self._create_menus()
        self._create_status_bar()

        # Load configuration
        self._initialize_configuration()

        # Show warning on startup
        QTimer.singleShot(500, self._show_startup_warning)

    def _set_application_icon(self):
        """Set application icon if available"""
        try:
            # Try to get icon from package resources
            if PACKAGE_AVAILABLE:
                icon_path = resource_manager.get_resource_path('', 'icon.ico')
                if icon_path and os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
                    return

            # Fallback to system icon
            style = self.style()
            icon = style.standardIcon(style.StandardPixmap.SP_ComputerIcon)
            self.setWindowIcon(icon)
        except Exception:
            pass  # No icon, no problem

    def _setup_ui(self):
        """Setup the main UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Header with warning
        header_group = QGroupBox()
        header_layout = QVBoxLayout(header_group)

        title_label = QLabel(" Platform Configuration Tool")
        title_label.setProperty("titleLabel", True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)

        warning_label = QLabel(
            " WARNING: This is an advanced configuration tool. "
            "Incorrect settings can break telemetry functionality. "
            "Always backup your configuration before making changes."
        )
        warning_label.setProperty("warningLabel", True)
        warning_label.setWordWrap(True)
        header_layout.addWidget(warning_label)

        layout.addWidget(header_group)

        # Main content tabs
        self.tab_widget = QTabWidget()

        # Platform Manager Tab
        self.platform_manager_tab = QWidget()
        self._setup_platform_manager_tab()
        self.tab_widget.addTab(self.platform_manager_tab, " Platform Manager")

        # Configuration Editor Tab
        self.config_editor_tab = QWidget()
        self._setup_config_editor_tab()
        self.tab_widget.addTab(self.config_editor_tab, " Raw Configuration")

        # Validation Tab
        self.validation_tab = QWidget()
        self._setup_validation_tab()
        self.tab_widget.addTab(self.validation_tab, " Validation & Testing")

        # Help Tab
        self.help_tab = QWidget()
        self._setup_help_tab()
        self.tab_widget.addTab(self.help_tab, " Help & Documentation")

        layout.addWidget(self.tab_widget)

    def _setup_platform_manager_tab(self):
        """Setup the platform manager tab"""
        layout = QVBoxLayout(self.platform_manager_tab)

        # Quick actions
        actions_layout = QHBoxLayout()

        add_platform_btn = QPushButton(" Add New Platform")
        add_platform_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        add_platform_btn.clicked.connect(self._add_new_platform)
        actions_layout.addWidget(add_platform_btn)

        backup_btn = QPushButton(" Create Backup")
        backup_btn.clicked.connect(self._create_backup)
        actions_layout.addWidget(backup_btn)

        restore_btn = QPushButton(" Restore Backup")
        restore_btn.clicked.connect(self._restore_backup)
        actions_layout.addWidget(restore_btn)

        actions_layout.addStretch()

        reload_btn = QPushButton(" Reload Config")
        reload_btn.clicked.connect(self._reload_configuration)
        actions_layout.addWidget(reload_btn)

        layout.addLayout(actions_layout)

        # Platform manager widget (will be created after config manager is ready)
        self.platform_manager_widget = None
        self.platform_manager_placeholder = QLabel("Loading platform configurations...")
        self.platform_manager_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.platform_manager_placeholder.setStyleSheet("font-size: 16px; color: #666666; padding: 50px;")
        layout.addWidget(self.platform_manager_placeholder)

    def _setup_config_editor_tab(self):
        """Setup the raw configuration editor tab"""
        layout = QVBoxLayout(self.config_editor_tab)

        # Instructions
        instructions = QLabel(
            "Direct JSON editor for advanced users. Changes here will be applied "
            "to the platforms.json file when saved."
        )
        instructions.setStyleSheet("font-style: italic; color: #666666; padding: 10px;")
        layout.addWidget(instructions)

        # Editor controls
        editor_controls = QHBoxLayout()

        load_btn = QPushButton(" Load from File")
        load_btn.clicked.connect(self._load_config_file)
        editor_controls.addWidget(load_btn)

        save_btn = QPushButton(" Save to File")
        save_btn.clicked.connect(self._save_config_file)
        editor_controls.addWidget(save_btn)

        validate_btn = QPushButton(" Validate JSON")
        validate_btn.clicked.connect(self._validate_json)
        editor_controls.addWidget(validate_btn)

        editor_controls.addStretch()

        format_btn = QPushButton(" Format JSON")
        format_btn.clicked.connect(self._format_json)
        editor_controls.addWidget(format_btn)

        layout.addLayout(editor_controls)

        # JSON editor
        self.json_editor = QTextEdit()
        self.json_editor.setFont(QFont("Consolas", 10))
        self.json_editor.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.json_editor)

    def _setup_validation_tab(self):
        """Setup the validation and testing tab"""
        layout = QVBoxLayout(self.validation_tab)

        # Validation controls
        validation_controls = QHBoxLayout()

        validate_all_btn = QPushButton(" Validate All Platforms")
        validate_all_btn.clicked.connect(self._validate_all_platforms)
        validation_controls.addWidget(validate_all_btn)

        test_templates_btn = QPushButton(" Check Templates")
        test_templates_btn.clicked.connect(self._check_templates)
        validation_controls.addWidget(test_templates_btn)

        export_report_btn = QPushButton(" Export Report")
        export_report_btn.clicked.connect(self._export_validation_report)
        validation_controls.addWidget(export_report_btn)

        validation_controls.addStretch()
        layout.addLayout(validation_controls)

        # Results display
        self.validation_results = QTextEdit()
        self.validation_results.setReadOnly(True)
        self.validation_results.setFont(QFont("Consolas", 10))
        layout.addWidget(self.validation_results)

    def _setup_help_tab(self):
        """Setup the help and documentation tab"""
        layout = QVBoxLayout(self.help_tab)

        help_content = QTextEdit()
        help_content.setReadOnly(True)
        help_content.setHtml("""
        <h2>Platform Configuration Tool Help</h2>

        <h3>Overview</h3>
        <p>This tool allows you to add new network device platforms and customize telemetry collection
        for TerminalTelemetry. Each platform configuration defines:</p>
        <ul>
        <li><b>Connection parameters</b> - How to connect via netmiko</li>
        <li><b>Commands</b> - What commands to run for each telemetry function</li>
        <li><b>Templates</b> - Which TextFSM templates to use for parsing</li>
        <li><b>Field mappings</b> - How to normalize vendor-specific output</li>
        <li><b>Capabilities</b> - What features the platform supports</li>
        </ul>

        <h3>Adding a New Platform</h3>
        <ol>
        <li>Click "Add New Platform" in the Platform Manager tab</li>
        <li>Fill in basic information (name, display name, description)</li>
        <li>Configure netmiko connection parameters</li>
        <li>Define commands and their corresponding TextFSM templates</li>
        <li>Set up field mappings for protocol codes and interface types</li>
        <li>Specify platform capabilities</li>
        <li>Test and save the configuration</li>
        </ol>

        <h3>TextFSM Templates</h3>
        <p>Templates should be placed in <code>templates/textfsm/</code> with naming convention:</p>
        <p><code>{platform}_{command}.textfsm</code></p>
        <p>Example: <code>fortinet_fortigate_show_version.textfsm</code></p>

        <h3>Safety Tips</h3>
        <ul>
        <li>Always create a backup before making changes</li>
        <li>Test configurations on non-production devices first</li>
        <li>Validate all platforms after making changes</li>
        <li>Keep netmiko device types accurate - they must match supported drivers</li>
        <li>Use the validation tab to check for errors</li>
        </ul>

        <h3>Troubleshooting</h3>
        <p><b>Platform not appearing in connection dialog:</b></p>
        <ul><li>Check that the platform name is valid and unique</li>
        <li>Ensure netmiko device_type is correct</li>
        <li>Reload the main application</li></ul>

        <p><b>Commands not working:</b></p>
        <ul><li>Verify command syntax for the target platform</li>
        <li>Check that TextFSM templates exist and are valid</li>
        <li>Test commands manually via SSH first</li></ul>

        <p><b>Templates not parsing:</b></p>
        <ul><li>Use the template editor in the main application</li>
        <li>Verify template field names match expected values</li>
        <li>Check template syntax with TextFSM documentation</li></ul>
        """)
        layout.addWidget(help_content)

    def _create_menus(self):
        """Create application menus"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open Configuration", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_configuration_file)
        file_menu.addAction(open_action)

        save_action = QAction("Save Configuration", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_configuration_file)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        backup_action = QAction("Create Backup", self)
        backup_action.triggered.connect(self._create_backup)
        file_menu.addAction(backup_action)

        restore_action = QAction("Restore Backup", self)
        restore_action.triggered.connect(self._restore_backup)
        file_menu.addAction(restore_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Tools menu
        tools_menu = menubar.addMenu("Tools")

        validate_action = QAction("Validate All Platforms", self)
        validate_action.triggered.connect(self._validate_all_platforms)
        tools_menu.addAction(validate_action)

        reload_action = QAction("Reload Configuration", self)
        reload_action.triggered.connect(self._reload_configuration)
        tools_menu.addAction(reload_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _create_status_bar(self):
        """Create status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _initialize_configuration(self):
        """Initialize the configuration manager"""
        try:
            # Try to find platforms.json
            possible_paths = [
                "config/platforms.json",
                "termtel/config/platforms.json",
                "platforms.json"
            ]

            self.platforms_file = None
            for path in possible_paths:
                if os.path.exists(path):
                    self.platforms_file = path
                    break

            if not self.platforms_file and PACKAGE_AVAILABLE:
                # Try package resources
                try:
                    platforms_content = resource_manager.get_platforms_config()
                    if platforms_content:
                        # Create local copy for editing
                        self.platforms_file = "platforms.json"
                        with open(self.platforms_file, 'w') as f:
                            f.write(platforms_content)
                except Exception:
                    pass

            if self.platforms_file:
                self.config_manager = PlatformConfigManager(os.path.dirname(self.platforms_file))
                self._update_platform_manager()
                self._load_json_editor()
                self.status_bar.showMessage(f"Loaded configuration from: {self.platforms_file}")
            else:
                self.status_bar.showMessage("No platforms.json found - create new configuration")
                self._create_new_configuration()

        except Exception as e:
            QMessageBox.critical(self, "Initialization Error",
                                 f"Failed to initialize configuration:\n{str(e)}")
            self.status_bar.showMessage("Configuration initialization failed")

    def _create_new_configuration(self):
        """Create a new configuration file"""
        reply = QMessageBox.question(
            self, "Create New Configuration",
            "No platforms.json file found. Create a new one?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Create minimal configuration
            minimal_config = {
                "platforms": {
                    "cisco_ios": {
                        "display_name": "Cisco IOS",
                        "description": "Cisco IOS devices",
                        "netmiko": {
                            "device_type": "cisco_ios",
                            "fast_cli": False,
                            "timeout": 30,
                            "auth_timeout": 10
                        },
                        "templates": {
                            "platform": "cisco_ios",
                            "base_path": "templates/textfsm"
                        },
                        "commands": {},
                        "field_mappings": {
                            "protocols": {"S": "Static", "C": "Connected"}
                        },
                        "capabilities": {
                            "supports_vrf": False,
                            "supports_cdp": True,
                            "supports_lldp": False,
                            "supports_temperature": False,
                            "neighbor_protocol": "cdp"
                        }
                    }
                },
                "global_settings": {
                    "template_search_paths": ["templates/textfsm"],
                    "default_timeouts": {"command": 30, "auth": 10, "connection": 15}
                }
            }

            self.platforms_file = "platforms.json"
            with open(self.platforms_file, 'w') as f:
                json.dump(minimal_config, f, indent=2)

            self._initialize_configuration()

    def _update_platform_manager(self):
        """Update the platform manager widget"""
        if self.config_manager and hasattr(self, 'platform_manager_placeholder'):
            # Remove placeholder and add real platform manager
            layout = self.platform_manager_tab.layout()
            layout.removeWidget(self.platform_manager_placeholder)
            self.platform_manager_placeholder.deleteLater()

            # Create platform manager widget
            self.platform_manager_widget = PlatformManagerWidget(self.config_manager)
            layout.addWidget(self.platform_manager_widget)

    def _load_json_editor(self):
        """Load current configuration into JSON editor"""
        if self.platforms_file and os.path.exists(self.platforms_file):
            try:
                with open(self.platforms_file, 'r') as f:
                    content = f.read()
                self.json_editor.setPlainText(content)
            except Exception as e:
                self.json_editor.setPlainText(f"Error loading file: {str(e)}")

    def _show_startup_warning(self):
        """Show startup warning dialog"""
        warning_msg = QMessageBox(self)
        warning_msg.setIcon(QMessageBox.Icon.Warning)
        warning_msg.setWindowTitle("Platform Configuration Tool")
        warning_msg.setText(" Advanced Configuration Tool")
        warning_msg.setInformativeText(
            "This tool allows direct modification of platform configurations.\n\n"
            "Incorrect configurations can break telemetry functionality.\n"
            "Always create backups before making changes.\n\n"
            "Continue only if you understand the risks."
        )
        warning_msg.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        warning_msg.setDefaultButton(QMessageBox.StandardButton.Cancel)

        if warning_msg.exec() == QMessageBox.StandardButton.Cancel:
            self.close()

    def _add_new_platform(self):
        """Add a new platform configuration"""
        if not self.config_manager:
            QMessageBox.warning(self, "No Configuration",
                                "Please load or create a configuration first.")
            return

        dialog = PlatformConfigDialog(self.config_manager, parent=self)
        dialog.platform_created.connect(self._on_platform_added)
        dialog.exec()

    def _on_platform_added(self, platform_name: str, config_data: dict):
        """Handle new platform addition"""
        self._reload_configuration()
        self.status_bar.showMessage(f"Added platform: {platform_name}")

    def _create_backup(self):
        """Create a backup of the current configuration"""
        if not self.platforms_file:
            QMessageBox.warning(self, "No Configuration", "No configuration file to backup.")
            return

        try:
            import shutil
            from datetime import datetime

            # Create backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"platforms_backup_{timestamp}.json"

            shutil.copy2(self.platforms_file, backup_name)

            QMessageBox.information(self, "Backup Created",
                                    f"Backup created successfully:\n{backup_name}")
            self.backup_created = True
            self.status_bar.showMessage(f"Backup created: {backup_name}")

        except Exception as e:
            QMessageBox.critical(self, "Backup Error",
                                 f"Failed to create backup:\n{str(e)}")

    def _restore_backup(self):
        """Restore from a backup file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Backup File", "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                import shutil

                # Validate the backup file first
                with open(file_path, 'r') as f:
                    backup_data = json.load(f)

                if 'platforms' not in backup_data:
                    QMessageBox.warning(self, "Invalid Backup",
                                        "Selected file is not a valid platform configuration backup.")
                    return

                # Create backup of current file
                if self.platforms_file and os.path.exists(self.platforms_file):
                    current_backup = f"{self.platforms_file}.pre_restore_backup"
                    shutil.copy2(self.platforms_file, current_backup)

                # Restore the backup
                shutil.copy2(file_path, self.platforms_file or "platforms.json")
                self.platforms_file = self.platforms_file or "platforms.json"

                # Reload configuration
                self._reload_configuration()

                QMessageBox.information(self, "Restore Complete",
                                        "Configuration restored successfully from backup.")
                self.status_bar.showMessage(f"Restored from: {os.path.basename(file_path)}")

            except Exception as e:
                QMessageBox.critical(self, "Restore Error",
                                     f"Failed to restore backup:\n{str(e)}")

    def _reload_configuration(self):
        """Reload the configuration from file"""
        self._initialize_configuration()

    def _validate_all_platforms(self):
        """Validate all platform configurations"""
        if not self.config_manager:
            self.validation_results.setPlainText("No configuration loaded.")
            return

        results = []
        results.append("=== Platform Validation Report ===\n")

        platforms = self.config_manager.get_available_platforms()
        results.append(f"Found {len(platforms)} platforms to validate:\n")

        errors_found = 0
        for platform_name in platforms:
            results.append(f"Validating {platform_name}...")

            try:
                validation = self.config_manager.validate_platform_config(platform_name)

                if validation['valid']:
                    results.append(f"   {platform_name}: Valid")
                    results.append(f"     Commands: {len(validation['available_commands'])}")
                    if validation['missing_templates']:
                        results.append(f"     Missing templates: {len(validation['missing_templates'])}")
                else:
                    results.append(f"   {platform_name}: Invalid")
                    for error in validation['errors']:
                        results.append(f"     • {error}")
                    errors_found += 1

            except Exception as e:
                results.append(f"   {platform_name}: Exception - {str(e)}")
                errors_found += 1

            results.append("")

        results.append(f"\n=== Summary ===")
        results.append(f"Total platforms: {len(platforms)}")
        results.append(f"Valid platforms: {len(platforms) - errors_found}")
        results.append(f"Invalid platforms: {errors_found}")

        if errors_found == 0:
            results.append("\n All platforms are valid!")
        else:
            results.append(f"\n Found {errors_found} platforms with issues.")

        self.validation_results.setPlainText("\n".join(results))
        self.tab_widget.setCurrentWidget(self.validation_tab)

    def _check_templates(self):
        """Check template availability"""
        # Implementation would check if templates exist
        self.validation_results.setPlainText("Template checking not yet implemented.")

    def _export_validation_report(self):
        """Export validation report to file"""
        content = self.validation_results.toPlainText()
        if not content:
            QMessageBox.information(self, "No Report", "Run validation first to generate a report.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Validation Report", "validation_report.txt",
            "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(content)
                QMessageBox.information(self, "Export Complete",
                                        f"Report exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error",
                                     f"Failed to export report:\n{str(e)}")

    def _load_config_file(self):
        """Load configuration from file into JSON editor"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Configuration File", "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                self.json_editor.setPlainText(content)
                self.status_bar.showMessage(f"Loaded: {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "Load Error",
                                     f"Failed to load file:\n{str(e)}")

    def _save_config_file(self):
        """Save JSON editor content to file"""
        if not self._validate_json():
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Configuration File", "platforms.json",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                content = self.json_editor.toPlainText()
                with open(file_path, 'w') as f:
                    f.write(content)
                QMessageBox.information(self, "Save Complete",
                                        f"Configuration saved to:\n{file_path}")
                self.status_bar.showMessage(f"Saved: {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error",
                                     f"Failed to save file:\n{str(e)}")

    def _validate_json(self):
        """Validate JSON syntax in editor"""
        try:
            content = self.json_editor.toPlainText()
            json.loads(content)
            QMessageBox.information(self, "Valid JSON", "JSON syntax is valid!")
            return True
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON",
                                f"JSON syntax error:\n{str(e)}")
            return False

    def _format_json(self):
        """Format JSON in editor"""
        try:
            content = self.json_editor.toPlainText()
            parsed = json.loads(content)
            formatted = json.dumps(parsed, indent=2)
            self.json_editor.setPlainText(formatted)
            self.status_bar.showMessage("JSON formatted")
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Format Error",
                                f"Cannot format invalid JSON:\n{str(e)}")

    def _open_configuration_file(self):
        """Open a configuration file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Configuration File", "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            self.platforms_file = file_path
            self._initialize_configuration()

    def _save_configuration_file(self):
        """Save current configuration"""
        if self.platforms_file:
            try:
                # Save JSON editor content to current file
                content = self.json_editor.toPlainText()
                with open(self.platforms_file, 'w') as f:
                    f.write(content)
                QMessageBox.information(self, "Saved", "Configuration saved successfully!")
                self._reload_configuration()
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save:\n{str(e)}")
        else:
            self._save_config_file()

    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About Platform Configuration Tool",
                          "TerminalTelemetry Platform Configuration Tool v1.0\n\n"
                          "Advanced configuration tool for adding and managing "
                          "network device platforms in TerminalTelemetry.\n\n"
                          " Use with caution - incorrect configurations can "
                          "break telemetry functionality.")

    def closeEvent(self, event):
        """Handle application close"""
        if not self.backup_created:
            reply = QMessageBox.question(
                self, "Exit Without Backup",
                "You haven't created a backup. Exit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        event.accept()


def main():
    """Main entry point for the platform configuration tool"""
    app = QApplication(sys.argv)

    # Set application properties
    app.setApplicationName("TerminalTelemetry Platform Config Tool")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("TerminalTelemetry")

    # Apply modern dark theme styling
    app.setStyleSheet("""
        /* Main application styling */
        QMainWindow {
            background-color: #2b2b2b;
            color: #ffffff;
        }

        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            selection-background-color: #007ACC;
            selection-color: #ffffff;
        }

        /* Tab widget styling */
        QTabWidget::pane {
            border: 1px solid #404040;
            background-color: #333333;
            border-radius: 4px;
        }

        QTabBar::tab {
            background-color: #404040;
            color: #ffffff;
            padding: 10px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            min-width: 100px;
        }

        QTabBar::tab:hover {
            background-color: #4a4a4a;
        }

        QTabBar::tab:selected {
            background-color: #007ACC;
            color: #ffffff;
            border-bottom: 2px solid #007ACC;
        }

        /* Group box styling */
        QGroupBox {
            font-weight: bold;
            border: 1px solid #555555;
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 12px;
            background-color: #333333;
            color: #ffffff;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            color: #ffffff;
            background-color: #333333;
        }

        /* Button styling */
        QPushButton {
            background-color: #404040;
            color: #ffffff;
            border: 1px solid #555555;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            min-height: 20px;
        }

        QPushButton:hover {
            background-color: #4a4a4a;
            border-color: #007ACC;
        }

        QPushButton:pressed {
            background-color: #007ACC;
        }

        QPushButton:disabled {
            background-color: #2a2a2a;
            color: #666666;
            border-color: #3a3a3a;
        }

        /* Input field styling */
        QLineEdit, QTextEdit, QSpinBox, QComboBox {
            background-color: #404040;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 6px;
            selection-background-color: #007ACC;
        }

        QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {
            border-color: #007ACC;
            background-color: #4a4a4a;
        }

        QComboBox::drop-down {
            border: none;
            background-color: #555555;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
            width: 20px;
        }

        QComboBox::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid #ffffff;
            margin: 0px;
        }

        QComboBox QAbstractItemView {
            background-color: #404040;
            color: #ffffff;
            border: 1px solid #555555;
            selection-background-color: #007ACC;
            outline: none;
        }

        /* Table styling */
        QTableWidget {
            background-color: #333333;
            alternate-background-color: #383838;
            color: #ffffff;
            gridline-color: #555555;
            border: 1px solid #555555;
            border-radius: 4px;
        }

        QTableWidget::item {
            padding: 8px;
            border: none;
        }

        QTableWidget::item:selected {
            background-color: #007ACC;
            color: #ffffff;
        }

        QTableWidget::item:hover {
            background-color: #4a4a4a;
        }

        QHeaderView::section {
            background-color: #404040;
            color: #ffffff;
            padding: 8px;
            border: 1px solid #555555;
            font-weight: bold;
        }

        /* Checkbox styling */
        QCheckBox {
            color: #ffffff;
            spacing: 8px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #555555;
            border-radius: 3px;
            background-color: #404040;
        }

        QCheckBox::indicator:checked {
            background-color: #007ACC;
            border-color: #007ACC;
        }

        QCheckBox::indicator:checked::after {
            content: "";
            color: white;
            font-weight: bold;
        }

        /* Label styling */
        QLabel {
            color: #ffffff;
            background-color: transparent;
        }

        /* Scroll area styling */
        QScrollArea {
            background-color: #333333;
            border: 1px solid #555555;
            border-radius: 4px;
        }

        QScrollBar:vertical {
            background-color: #404040;
            width: 12px;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical {
            background-color: #666666;
            border-radius: 6px;
            min-height: 20px;
        }

        QScrollBar::handle:vertical:hover {
            background-color: #777777;
        }

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            border: none;
            background: none;
        }

        /* Menu bar styling */
        QMenuBar {
            background-color: #2b2b2b;
            color: #ffffff;
            border-bottom: 1px solid #555555;
        }

        QMenuBar::item {
            background-color: transparent;
            padding: 6px 12px;
        }

        QMenuBar::item:selected {
            background-color: #007ACC;
        }

        QMenu {
            background-color: #404040;
            color: #ffffff;
            border: 1px solid #555555;
        }

        QMenu::item {
            padding: 6px 20px;
        }

        QMenu::item:selected {
            background-color: #007ACC;
        }

        /* Status bar styling */
        QStatusBar {
            background-color: #404040;
            color: #ffffff;
            border-top: 1px solid #555555;
        }

        /* Message box styling */
        QMessageBox {
            background-color: #333333;
            color: #ffffff;
        }

        QMessageBox QPushButton {
            min-width: 80px;
        }

        /* Dialog styling */
        QDialog {
            background-color: #2b2b2b;
            color: #ffffff;
        }

        /* Form layout styling */
        QFormLayout QLabel {
            color: #ffffff;
            font-weight: bold;
        }

        /* Special styling for warning/error elements */
        QLabel[warningLabel="true"] {
            background-color: rgba(255, 102, 0, 0.1);
            border: 2px solid #ff6600;
            border-radius: 6px;
            padding: 12px;
            color: #ffaa55;
            font-weight: bold;
        }

        QLabel[titleLabel="true"] {
            font-size: 24px;
            font-weight: bold;
            color: #ff6600;
            padding: 10px;
        }
    """)

    try:
        # Create and show main window
        window = PlatformConfigToolMainWindow()
        window.show()

        # Run application
        sys.exit(app.exec())

    except Exception as e:
        # Show error dialog if something goes wrong
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Icon.Critical)
        error_dialog.setWindowTitle("Startup Error")
        error_dialog.setText("Failed to start Platform Configuration Tool")
        error_dialog.setDetailedText(f"Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}")
        error_dialog.exec()
        sys.exit(1)


if __name__ == "__main__":
    main()