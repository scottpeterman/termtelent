#!/usr/bin/env python3
"""
CMDB Scanner Import GUI Tool - Enhanced with Vendor Normalization
A standalone GUI for importing SNMP discovery scan data into NAPALM CMDB
with advanced filtering, preview capabilities, domain name stripping, and vendor normalization
"""

import sys
import os
import json
import yaml
import sqlite3
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import asdict

from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QProgressBar, QCheckBox,
    QComboBox, QSpinBox, QGroupBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QSplitter, QHeaderView, QFrame, QScrollArea,
    QLineEdit, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon

from termtel.themes3 import ThemeLibrary

# Import the scanner classes
try:
    from rapidcmdb.db_scan_import_enhanced import ScanImporter, ImportedDevice, VendorFingerprintManager

    SCANNER_AVAILABLE = True
except ImportError:
    print("Warning: Scanner modules not available. Some features may be limited.")
    SCANNER_AVAILABLE = False


class VendorNormalizer:
    """Utility class for normalizing vendor names"""

    def __init__(self):
        # Comprehensive vendor mapping from your db_maint.py with additions
        self.vendor_mapping = {
            'cisco': ['Cisco', 'CISCO', 'cisco', 'Cisco Systems', 'cisco systems'],
            'juniper': ['Juniper', 'JUNIPER', 'juniper', 'Juniper Networks', 'juniper networks'],
            'arista': ['Arista', 'ARISTA', 'arista', 'Arista Networks', 'arista networks'],
            'hp': ['HP', 'hp', 'Hewlett Packard', 'HPE', 'hewlett-packard', 'Hewlett-Packard'],
            'palo_alto': ['Palo Alto', 'palo_alto', 'PALO_ALTO', 'Palo Alto Networks', 'palo alto networks'],
            'fortinet': ['Fortinet', 'FORTINET', 'fortinet', 'FortiNet'],
            'zebra': ['Zebra', 'ZEBRA', 'zebra', 'Zebra Technologies'],
            'lexmark': ['Lexmark', 'LEXMARK', 'lexmark', 'Lexmark International'],
            'apc': ['APC', 'apc', 'American Power Conversion', 'Schneider Electric'],
            'bluecat': ['BlueCat', 'bluecat', 'BLUECAT', 'BlueCat Networks'],
            'aruba': ['Aruba', 'aruba_ap', 'aruba_wireless', 'Aruba Networks', 'ARUBA'],
            'dell': ['Dell', 'DELL', 'dell', 'Dell Inc', 'Dell Technologies'],
            'netgear': ['Netgear', 'NETGEAR', 'netgear', 'NETGEAR Inc'],
            'ubiquiti': ['Ubiquiti', 'UBIQUITI', 'ubiquiti', 'Ubiquiti Networks'],
            'mikrotik': ['MikroTik', 'mikrotik', 'MIKROTIK', 'Mikrotik'],
            'extreme': ['Extreme', 'EXTREME', 'extreme', 'Extreme Networks'],
            'brocade': ['Brocade', 'BROCADE', 'brocade', 'Brocade Communications'],
            'f5': ['F5', 'f5', 'F5 Networks', 'f5 networks'],
            'sonicwall': ['SonicWall', 'sonicwall', 'SONICWALL', 'SonicWALL'],
            'checkpoint': ['Check Point', 'checkpoint', 'CHECK POINT', 'CheckPoint'],
            'vmware': ['VMware', 'vmware', 'VMWARE', 'VMWare'],
            'microsoft': ['Microsoft', 'microsoft', 'MICROSOFT', 'Microsoft Corporation'],
            'linux': ['Linux', 'linux', 'LINUX', 'GNU/Linux'],
            'windows': ['Windows', 'windows', 'WINDOWS', 'Microsoft Windows'],
            'qnap': ['QNAP', 'qnap', 'Qnap'],
            'synology': ['Synology', 'synology', 'SYNOLOGY'],
            'unknown': ['Unknown', 'unknown', 'UNKNOWN', '', None, 'N/A', 'n/a']
        }

        # Create reverse mapping for quick lookups
        self.reverse_mapping = {}
        for normalized, variants in self.vendor_mapping.items():
            for variant in variants:
                if variant is not None:  # Handle None case
                    self.reverse_mapping[variant] = normalized

    def normalize_vendor(self, vendor_name: str) -> str:
        """
        Normalize a vendor name to standard format

        Args:
            vendor_name: Raw vendor name from device scan

        Returns:
            Normalized vendor name
        """
        if not vendor_name:
            return 'unknown'

        # First try exact match
        if vendor_name in self.reverse_mapping:
            return self.reverse_mapping[vendor_name]

        # Try case-insensitive match
        vendor_lower = vendor_name.lower()
        for variant, normalized in self.reverse_mapping.items():
            if variant and variant.lower() == vendor_lower:
                return normalized

        # Try partial matches for complex vendor strings
        for normalized, variants in self.vendor_mapping.items():
            for variant in variants:
                if variant and variant.lower() in vendor_lower:
                    return normalized

        # If no match found, return original but cleaned up
        return vendor_name.strip().title()

    def get_normalization_stats(self, vendors: List[str]) -> Dict[str, Dict]:
        """
        Get statistics on how many vendors would be normalized

        Args:
            vendors: List of vendor names from scan data

        Returns:
            Dictionary with normalization statistics
        """
        stats = {
            'total_vendors': len(set(vendors)),
            'normalizations': {},
            'unchanged': 0,
            'normalized_count': 0
        }

        vendor_counts = {}
        for vendor in vendors:
            vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1

        for vendor, count in vendor_counts.items():
            normalized = self.normalize_vendor(vendor)
            if normalized != vendor:
                stats['normalizations'][f"{vendor} -> {normalized}"] = count
                stats['normalized_count'] += count
            else:
                stats['unchanged'] += count

        return stats

    def add_custom_mapping(self, normalized_name: str, variants: List[str]):
        """Add custom vendor mapping"""
        if normalized_name not in self.vendor_mapping:
            self.vendor_mapping[normalized_name] = []

        self.vendor_mapping[normalized_name].extend(variants)

        # Update reverse mapping
        for variant in variants:
            self.reverse_mapping[variant] = normalized_name


class DomainStripper:
    """Utility class for stripping domain names from device names"""

    def __init__(self):
        # Common domain patterns to strip
        self.domain_patterns = [
            r'\.local$',
            r'\.corp$',
            r'\.com$',
            r'\.net$',
            r'\.org$',
            r'\.edu$',
            r'\.gov$',
            r'\.mil$',
            r'\.int$',
            r'\.example\.com$',
            r'\.example\.org$',
            r'\.test$',
            r'\.localhost$',
            # Custom patterns for common corporate domains
            r'\.internal$',
            r'\.intranet$',
            r'\.domain$',
            r'\.lan$',
            # Generic TLD pattern (catches most domains)
            r'\.[a-zA-Z]{2,}(\.[a-zA-Z]{2,})*$'
        ]

        # Compile patterns for better performance
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.domain_patterns]

    def strip_domain(self, hostname: str) -> str:
        """
        Strip domain name from hostname, returning just the hostname part

        Args:
            hostname: Full hostname potentially including domain

        Returns:
            Hostname with domain stripped
        """
        if not hostname:
            return hostname

        original_hostname = hostname.strip()
        stripped_hostname = original_hostname

        # Try each pattern until we find a match
        for pattern in self.compiled_patterns:
            if pattern.search(stripped_hostname):
                stripped_hostname = pattern.sub('', stripped_hostname)
                break

        # If nothing was stripped by patterns, try simple dot splitting
        # This handles cases where the domain doesn't match our patterns
        if stripped_hostname == original_hostname and '.' in stripped_hostname:
            parts = stripped_hostname.split('.')
            if len(parts) > 1:
                # Only take the first part if it looks like a hostname
                # (not an IP address)
                first_part = parts[0]
                if not self._is_ip_address(first_part):
                    stripped_hostname = first_part

        return stripped_hostname

    def _is_ip_address(self, text: str) -> bool:
        """Check if text looks like an IP address"""
        try:
            parts = text.split('.')
            if len(parts) == 4:
                for part in parts:
                    num = int(part)
                    if not (0 <= num <= 255):
                        return False
                return True
        except (ValueError, AttributeError):
            pass
        return False

    def add_custom_domain(self, domain: str):
        """Add a custom domain pattern to strip"""
        if not domain.startswith('.'):
            domain = '.' + domain
        pattern = re.escape(domain) + '$'
        self.compiled_patterns.append(re.compile(pattern, re.IGNORECASE))


# Basic theme management
class SimpleThemeManager:
    """Simple theme manager for standalone operation"""

    def __init__(self):
        self.themes = {
            'cyberpunk': {
                'background': '#0a0a0a',
                'surface': '#1a1a1a',
                'primary': '#00ffff',
                'secondary': '#ff00ff',
                'text': '#ffffff',
                'text_secondary': '#cccccc',
                'border': '#333333',
                'success': '#00ff00',
                'warning': '#ffff00',
                'error': '#ff0000'
            },
            'dark_mode': {
                'background': '#2b2b2b',
                'surface': '#3c3c3c',
                'primary': '#0078d4',
                'secondary': '#6264a7',
                'text': '#ffffff',
                'text_secondary': '#cccccc',
                'border': '#555555',
                'success': '#16c60c',
                'warning': '#ffb900',
                'error': '#d13438'
            },
            'light_mode': {
                'background': '#ffffff',
                'surface': '#f5f5f5',
                'primary': '#0078d4',
                'secondary': '#6264a7',
                'text': '#000000',
                'text_secondary': '#666666',
                'border': '#cccccc',
                'success': '#16c60c',
                'warning': '#ffb900',
                'error': '#d13438'
            }
        }
        self.current_theme = 'cyberpunk'

    def get_colors(self, theme_name: str = None) -> Dict[str, str]:
        """Get color palette for theme"""
        theme_name = theme_name or self.current_theme
        return self.themes.get(theme_name, self.themes['cyberpunk'])

    def get_theme_names(self) -> List[str]:
        """Get available theme names"""
        return list(self.themes.keys())


class VendorNormalizationDialog(QDialog):
    """Dialog for previewing and configuring vendor normalization"""

    def __init__(self, vendor_stats: Dict, vendor_normalizer: VendorNormalizer, parent=None):
        super().__init__(parent)
        self.vendor_stats = vendor_stats
        self.vendor_normalizer = vendor_normalizer
        self.setWindowTitle("Vendor Normalization Preview")
        self.setModal(True)
        self.resize(800, 600)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Summary section
        summary_group = QGroupBox("Normalization Summary")
        summary_layout = QGridLayout(summary_group)

        summary_layout.addWidget(QLabel("Total Unique Vendors:"), 0, 0)
        summary_layout.addWidget(QLabel(str(self.vendor_stats['total_vendors'])), 0, 1)

        summary_layout.addWidget(QLabel("Vendors to Normalize:"), 1, 0)
        summary_layout.addWidget(QLabel(str(len(self.vendor_stats['normalizations']))), 1, 1)

        summary_layout.addWidget(QLabel("Devices Affected:"), 2, 0)
        summary_layout.addWidget(QLabel(str(self.vendor_stats['normalized_count'])), 2, 1)

        layout.addWidget(summary_group)

        # Normalization preview table
        preview_group = QGroupBox("Normalization Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.normalization_table = QTableWidget()
        self.normalization_table.setColumnCount(3)
        self.normalization_table.setHorizontalHeaderLabels([
            "Original Vendor", "Normalized Vendor", "Device Count"
        ])

        # Populate table
        normalizations = self.vendor_stats['normalizations']
        self.normalization_table.setRowCount(len(normalizations))

        for row, (change, count) in enumerate(normalizations.items()):
            original, normalized = change.split(' -> ')
            self.normalization_table.setItem(row, 0, QTableWidgetItem(original))
            self.normalization_table.setItem(row, 1, QTableWidgetItem(normalized))
            self.normalization_table.setItem(row, 2, QTableWidgetItem(str(count)))

        self.normalization_table.resizeColumnsToContents()
        preview_layout.addWidget(self.normalization_table)
        layout.addWidget(preview_group)

        # Custom mapping section
        custom_group = QGroupBox("Custom Vendor Mappings")
        custom_layout = QVBoxLayout(custom_group)

        custom_form = QHBoxLayout()
        custom_form.addWidget(QLabel("Normalize:"))
        self.original_vendor_edit = QLineEdit()
        self.original_vendor_edit.setPlaceholderText("Original vendor name")
        custom_form.addWidget(self.original_vendor_edit)

        custom_form.addWidget(QLabel("To:"))
        self.normalized_vendor_edit = QLineEdit()
        self.normalized_vendor_edit.setPlaceholderText("Normalized vendor name")
        custom_form.addWidget(self.normalized_vendor_edit)

        self.add_mapping_btn = QPushButton("Add Mapping")
        self.add_mapping_btn.clicked.connect(self.add_custom_mapping)
        custom_form.addWidget(self.add_mapping_btn)

        custom_layout.addLayout(custom_form)
        layout.addWidget(custom_group)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def add_custom_mapping(self):
        """Add a custom vendor mapping"""
        original = self.original_vendor_edit.text().strip()
        normalized = self.normalized_vendor_edit.text().strip()

        if not original or not normalized:
            QMessageBox.warning(self, "Invalid Input", "Please enter both original and normalized vendor names")
            return

        # Add to normalizer
        self.vendor_normalizer.add_custom_mapping(normalized, [original])

        # Add to table
        row = self.normalization_table.rowCount()
        self.normalization_table.insertRow(row)
        self.normalization_table.setItem(row, 0, QTableWidgetItem(original))
        self.normalization_table.setItem(row, 1, QTableWidgetItem(normalized))
        self.normalization_table.setItem(row, 2, QTableWidgetItem("Custom"))

        # Clear inputs
        self.original_vendor_edit.clear()
        self.normalized_vendor_edit.clear()

        QMessageBox.information(self, "Mapping Added", f"Added mapping: {original} -> {normalized}")


class ScanDataPreviewDialog(QDialog):
    """Dialog for previewing scan data before import"""

    def __init__(self, scan_data: Dict, domain_stripper: DomainStripper = None,
                 vendor_normalizer: VendorNormalizer = None, parent=None):
        super().__init__(parent)
        self.scan_data = scan_data
        self.domain_stripper = domain_stripper or DomainStripper()
        self.vendor_normalizer = vendor_normalizer or VendorNormalizer()
        self.setWindowTitle("Scan Data Preview")
        self.setModal(True)
        self.resize(1000, 700)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Summary section
        summary_group = QGroupBox("Scan Summary")
        summary_layout = QGridLayout(summary_group)

        devices = self.scan_data.get('devices', {})
        summary_layout.addWidget(QLabel("Total Devices:"), 0, 0)
        summary_layout.addWidget(QLabel(str(len(devices))), 0, 1)

        # Count by vendor (both original and normalized)
        vendors = {}
        normalized_vendors = {}
        device_types = {}
        for device_data in devices.values():
            vendor = device_data.get('vendor', 'unknown')
            normalized_vendor = self.vendor_normalizer.normalize_vendor(vendor)
            device_type = device_data.get('device_type', 'unknown')

            vendors[vendor] = vendors.get(vendor, 0) + 1
            normalized_vendors[normalized_vendor] = normalized_vendors.get(normalized_vendor, 0) + 1
            device_types[device_type] = device_types.get(device_type, 0) + 1

        summary_layout.addWidget(QLabel("Original Vendors:"), 1, 0)
        summary_layout.addWidget(QLabel(str(len(vendors))), 1, 1)

        summary_layout.addWidget(QLabel("Normalized Vendors:"), 2, 0)
        summary_layout.addWidget(QLabel(str(len(normalized_vendors))), 2, 1)

        summary_layout.addWidget(QLabel("Device Types:"), 3, 0)
        summary_layout.addWidget(QLabel(str(len(device_types))), 3, 1)

        layout.addWidget(summary_group)

        # Data preview table
        preview_group = QGroupBox("Device Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(11)
        self.preview_table.setHorizontalHeaderLabels([
            "Device Name (Original)", "Device Name (Stripped)", "IP Address", "Vendor (Original)",
            "Vendor (Normalized)", "Model", "Device Type", "Serial", "Confidence", "Method", "Notes"
        ])

        # Populate table with device data
        self.preview_table.setRowCount(len(devices))
        for row, (device_id, device_data) in enumerate(devices.items()):
            original_name = device_data.get('sys_name', device_id)
            stripped_name = self.domain_stripper.strip_domain(original_name)
            original_vendor = device_data.get('vendor', '')
            normalized_vendor = self.vendor_normalizer.normalize_vendor(original_vendor)

            self.preview_table.setItem(row, 0, QTableWidgetItem(original_name))
            self.preview_table.setItem(row, 1, QTableWidgetItem(stripped_name))
            self.preview_table.setItem(row, 2, QTableWidgetItem(
                device_data.get('primary_ip', device_data.get('ip_address', ''))
            ))
            self.preview_table.setItem(row, 3, QTableWidgetItem(original_vendor))

            # Highlight normalized vendors that changed
            normalized_item = QTableWidgetItem(normalized_vendor)
            if normalized_vendor != original_vendor:
                normalized_item.setBackground(QColor(200, 255, 200))  # Light green
            self.preview_table.setItem(row, 4, normalized_item)

            self.preview_table.setItem(row, 5, QTableWidgetItem(
                device_data.get('model', '')
            ))
            self.preview_table.setItem(row, 6, QTableWidgetItem(
                device_data.get('device_type', '')
            ))
            self.preview_table.setItem(row, 7, QTableWidgetItem(
                device_data.get('serial_number', '')
            ))
            self.preview_table.setItem(row, 8, QTableWidgetItem(
                str(device_data.get('confidence_score', 0))
            ))
            self.preview_table.setItem(row, 9, QTableWidgetItem(
                device_data.get('detection_method', '')
            ))

            notes = []
            if stripped_name != original_name:
                notes.append("Domain stripped")
            if normalized_vendor != original_vendor:
                notes.append("Vendor normalized")
            self.preview_table.setItem(row, 10, QTableWidgetItem("; ".join(notes)))

        self.preview_table.resizeColumnsToContents()
        preview_layout.addWidget(self.preview_table)
        layout.addWidget(preview_group)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


class ImportWorkerThread(QThread):
    """Worker thread for import operations"""

    progress_updated = pyqtSignal(int, str)
    import_completed = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, scan_files: List[str], db_path: str,
                 filters: Dict, fingerprint_file: str, domain_stripper: DomainStripper,
                 vendor_normalizer: VendorNormalizer, dry_run: bool = False):
        super().__init__()
        self.scan_files = scan_files
        self.db_path = db_path
        self.filters = filters
        self.fingerprint_file = fingerprint_file
        self.domain_stripper = domain_stripper
        self.vendor_normalizer = vendor_normalizer
        self.dry_run = dry_run

    def extract_site_code(self, hostname: str, primary_ip: str) -> str:
        """Extract site code from hostname - hostname patterns only"""
        if not hostname:
            hostname = ""

        hostname_lower = hostname.lower()

        # Priority 1: Look for patterns with site prefix + number (e.g., us-0548-wap-02)
        # For 2-char prefixes, combine with number for uniqueness
        site_with_number = re.match(r'^([a-z]{2,4})-(\d+)', hostname_lower)
        if site_with_number:
            site_prefix = site_with_number.group(1).upper()
            site_number = site_with_number.group(2)

            # Always combine prefix with number for uniqueness (e.g., US0548)
            return site_prefix + site_number[:4]

        # Priority 2: Look for 3+ character prefixes without numbers (e.g., frc-device, usc-switch)
        # Only accept 3+ char prefixes to avoid ambiguous 2-char codes
        site_prefix_only = re.match(r'^([a-z]{3,4})-', hostname_lower)
        if site_prefix_only:
            site_prefix = site_prefix_only.group(1).upper()
            return site_prefix

        # Fallback: Unknown site
        return 'UNK'

    def _extract_error_details_from_importer(self, importer, file_stats: Dict, detailed_stats: Dict, file_name: str):
        """Extract error details from the importer object"""

        # List of potential error attributes in the scanner
        error_attributes = [
            'error_log', 'errors_encountered', 'import_errors', 'processing_errors',
            'failed_devices', 'device_errors', 'validation_errors', 'constraint_errors',
            'duplicate_errors', 'scan_errors', 'db_errors'
        ]

        for attr_name in error_attributes:
            if hasattr(importer, attr_name):
                error_data = getattr(importer, attr_name)
                if error_data:
                    print(
                        f"Found error data in {attr_name}: {type(error_data)} with {len(error_data) if hasattr(error_data, '__len__') else '?'} items")

                    if isinstance(error_data, list):
                        for error in error_data:
                            if isinstance(error, dict):
                                # Error is already in dict format
                                error_detail = error.copy()
                                error_detail['error_type'] = error_detail.get('error_type', attr_name)
                            else:
                                # Convert string/other to dict format
                                error_detail = {
                                    'device_id': f'Unknown ({file_name})',
                                    'error': str(error),
                                    'error_type': attr_name
                                }

                            file_stats['error_details'].append(error_detail)
                            detailed_stats['error_details'].append(error_detail)

                    elif isinstance(error_data, dict):
                        for key, value in error_data.items():
                            error_detail = {
                                'device_id': key,
                                'error': str(value),
                                'error_type': attr_name
                            }
                            file_stats['error_details'].append(error_detail)
                            detailed_stats['error_details'].append(error_detail)

                    else:
                        # Handle other types
                        error_detail = {
                            'device_id': f'Scanner ({file_name})',
                            'error': str(error_data),
                            'error_type': attr_name
                        }
                        file_stats['error_details'].append(error_detail)
                        detailed_stats['error_details'].append(error_detail)

                    break  # Use the first error source we find

    def _final_error_extraction(self, importer, detailed_stats: Dict):
        """Final attempt to extract any error information from the importer"""

        # If we still don't have detailed errors but the stats show errors,
        # let's do a comprehensive search
        if detailed_stats.get('errors', 0) > 0 and not detailed_stats.get('error_details'):
            print("No detailed errors found, doing comprehensive search...")

            # Check all attributes that might contain error info
            if hasattr(importer, '__dict__'):
                for attr_name, attr_value in importer.__dict__.items():
                    if (('error' in attr_name.lower() or
                         'fail' in attr_name.lower() or
                         'exception' in attr_name.lower()) and
                            attr_value):

                        print(f"Found potential error attribute: {attr_name} = {attr_value}")

                        if isinstance(attr_value, (list, tuple)) and attr_value:
                            for error in attr_value:
                                detailed_stats['error_details'].append({
                                    'device_id': 'Scanner',
                                    'error': str(error),
                                    'error_type': attr_name
                                })
                        elif isinstance(attr_value, dict) and attr_value:
                            for key, value in attr_value.items():
                                detailed_stats['error_details'].append({
                                    'device_id': str(key),
                                    'error': str(value),
                                    'error_type': attr_name
                                })
                        elif isinstance(attr_value, str) and attr_value.strip():
                            detailed_stats['error_details'].append({
                                'device_id': 'Scanner',
                                'error': attr_value,
                                'error_type': attr_name
                            })

    def run(self):
        """Enhanced run method with detailed error collection using ErrorCapturingScanImporter"""
        import time
        import tempfile
        import os

        start_time = time.time()

        try:
            if not SCANNER_AVAILABLE:
                self.error_occurred.emit("Scanner modules not available")
                return

            # Initialize our ENHANCED importer that captures errors
            importer = ErrorCapturingScanImporter(
                self.db_path,
                self.fingerprint_file,
                dry_run=self.dry_run
            )

            # Extract hostname filters
            hostname_filters = self.filters.pop('hostnames', None)
            scanner_filters = self.filters.copy()

            total_files = len(self.scan_files)

            # Initialize detailed statistics tracking
            detailed_stats = {
                'devices_processed': 0,
                'devices_imported': 0,
                'devices_updated': 0,
                'devices_skipped': 0,
                'duplicates_found': 0,
                'errors': 0,
                'error_details': [],
                'warnings': [],
                'file_results': {},
                'processing_details': {
                    'vendors_normalized': 0,
                    'domains_stripped': 0,
                    'vendor_normalizations': {}
                }
            }

            for i, scan_file in enumerate(self.scan_files):
                file_name = Path(scan_file).name
                self.progress_updated.emit(
                    int((i / total_files) * 100),
                    f"Processing {file_name}..."
                )

                try:
                    # Load and process the scan file
                    with open(scan_file, 'r', encoding='utf-8') as f:
                        scan_data = json.load(f)

                    # Track original device count
                    original_devices = scan_data.get('devices', {}).copy()

                    # Normalize scan data first
                    scan_data = importer.normalize_scan_data(scan_data)

                    # Normalize vendor names and track changes
                    scan_data = self._normalize_vendors_in_scan_data_with_tracking(
                        scan_data, detailed_stats
                    )

                    # Strip domains from device names and track changes
                    scan_data = self._strip_domains_from_scan_data_with_tracking(
                        scan_data, detailed_stats
                    )

                    devices = scan_data.get('devices', {})

                    # Apply hostname filtering if specified
                    if hostname_filters:
                        filtered_devices = {}
                        for device_id, device_data in devices.items():
                            if self._passes_hostname_filter(device_data, hostname_filters):
                                filtered_devices[device_id] = device_data
                        devices = filtered_devices
                        scan_data['devices'] = devices

                    # Create a temporary file with processed data
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                        json.dump(scan_data, temp_file, indent=2)
                        temp_file_path = temp_file.name

                    try:
                        print(f"\n📥 CALLING enhanced import_scan_file({temp_file_path}, {scanner_filters})")

                        # Import using our enhanced scanner that captures errors
                        import_result = importer.import_scan_file(temp_file_path, scanner_filters)

                        print(f"📤 Enhanced import_scan_file returned: {import_result}")

                        # Extract file statistics from the enhanced result
                        if isinstance(import_result, dict):
                            file_stats = {
                                'devices': len(original_devices),
                                'imported': import_result.get('stats', {}).get('devices_imported', 0),
                                'updated': import_result.get('stats', {}).get('devices_updated', 0),
                                'skipped': import_result.get('stats', {}).get('devices_skipped', 0),
                                'errors': import_result.get('stats', {}).get('errors', 0),
                                'error_details': import_result.get('error_details', [])
                            }

                            # Add file errors to overall error tracking
                            if import_result.get('error_details'):
                                for error in import_result['error_details']:
                                    # Add file context to error
                                    error_with_context = error.copy()
                                    error_with_context['file'] = file_name
                                    detailed_stats['error_details'].append(error_with_context)

                            # Also add processing errors
                            if import_result.get('processing_errors'):
                                for error in import_result['processing_errors']:
                                    error_with_context = error.copy()
                                    error_with_context['file'] = file_name
                                    detailed_stats['error_details'].append(error_with_context)

                        else:
                            # Fallback for boolean result
                            file_stats = {
                                'devices': len(original_devices),
                                'imported': 0,
                                'updated': 0,
                                'skipped': 0,
                                'errors': 0,
                                'error_details': []
                            }

                    finally:
                        # Clean up temp file
                        try:
                            os.unlink(temp_file_path)
                        except:
                            pass

                except Exception as e:
                    # Handle file processing errors
                    error_detail = {
                        'device_id': f'FILE:{file_name}',
                        'error': str(e),
                        'error_type': 'File Processing',
                        'file': file_name
                    }
                    file_stats = {
                        'devices': 0,
                        'imported': 0,
                        'updated': 0,
                        'skipped': 0,
                        'errors': 1,
                        'error_details': [error_detail]
                    }
                    detailed_stats['error_details'].append(error_detail)
                    print(f"Error processing file {file_name}: {e}")

                # Update overall statistics
                detailed_stats['devices_processed'] += file_stats.get('devices', 0)
                detailed_stats['devices_imported'] += file_stats.get('imported', 0)
                detailed_stats['devices_updated'] += file_stats.get('updated', 0)
                detailed_stats['devices_skipped'] += file_stats.get('skipped', 0)
                detailed_stats['errors'] += file_stats.get('errors', 0)

                detailed_stats['file_results'][file_name] = file_stats

            # Final progress update
            self.progress_updated.emit(100, "Import completed")

            # Get final stats from importer
            final_importer_stats = getattr(importer, 'stats', {})

            # Merge importer stats with our detailed stats
            for key in ['duplicates_found', 'warnings']:
                if key in final_importer_stats:
                    detailed_stats[key] = final_importer_stats[key]

            # Add performance metrics
            detailed_stats['performance'] = {
                'duration': time.time() - start_time,
                'start_time': start_time,
                'end_time': time.time()
            }

            # Debug output
            if detailed_stats.get('errors', 0) > 0:
                print(f"\n=== FINAL IMPORT DEBUG INFO ===")
                print(f"Total errors found: {detailed_stats.get('errors', 0)}")
                print(f"Error details collected: {len(detailed_stats.get('error_details', []))}")
                if detailed_stats.get('error_details'):
                    print("Collected errors:")
                    for i, error in enumerate(detailed_stats['error_details']):
                        print(f"  {i + 1}: {error}")
                print(f"=== END FINAL DEBUG INFO ===\n")

            # Emit the completed signal with detailed stats
            self.import_completed.emit(detailed_stats)

        except Exception as e:
            print(f"Fatal error in import thread: {e}")
            self.error_occurred.emit(str(e))

    # Add the helper methods as well:
    def _normalize_vendors_in_scan_data_with_tracking(self, scan_data: Dict, stats: Dict) -> Dict:
        """Normalize vendor names and track changes"""
        devices = scan_data.get('devices', {})
        modified_devices = {}
        vendor_changes = {}

        for device_id, device_data in devices.items():
            modified_device = device_data.copy()

            if 'vendor' in modified_device:
                original_vendor = modified_device['vendor']
                normalized_vendor = self.vendor_normalizer.normalize_vendor(original_vendor)
                modified_device['vendor'] = normalized_vendor

                if normalized_vendor != original_vendor:
                    modified_device['original_vendor'] = original_vendor
                    vendor_changes[original_vendor] = normalized_vendor
                    stats['processing_details']['vendors_normalized'] += 1

            modified_devices[device_id] = modified_device

        # Track vendor changes
        stats['processing_details']['vendor_normalizations'].update(vendor_changes)

        modified_scan_data = scan_data.copy()
        modified_scan_data['devices'] = modified_devices
        return modified_scan_data

    def _strip_domains_from_scan_data_with_tracking(self, scan_data: Dict, stats: Dict) -> Dict:
        """Strip domains and track changes"""
        devices = scan_data.get('devices', {})
        modified_devices = {}

        for device_id, device_data in devices.items():
            modified_device = device_data.copy()

            # Strip domain from sys_name
            if 'sys_name' in modified_device and modified_device['sys_name']:
                original_name = modified_device['sys_name']
                stripped_name = self.domain_stripper.strip_domain(original_name)
                modified_device['sys_name'] = stripped_name

                if stripped_name != original_name:
                    modified_device['original_sys_name'] = original_name
                    stats['processing_details']['domains_stripped'] += 1

            # Strip domain from device_name if present
            if 'device_name' in modified_device and modified_device['device_name']:
                original_name = modified_device['device_name']
                stripped_name = self.domain_stripper.strip_domain(original_name)
                modified_device['device_name'] = stripped_name

                if stripped_name != original_name and 'original_device_name' not in modified_device:
                    modified_device['original_device_name'] = original_name

            # Use stripped name as the new device ID if the original device ID was a hostname
            new_device_id = device_id
            if device_id in [device_data.get('sys_name'), device_data.get('device_name')]:
                new_device_id = modified_device.get('sys_name') or modified_device.get('device_name') or device_id

            modified_devices[new_device_id] = modified_device

        modified_scan_data = scan_data.copy()
        modified_scan_data['devices'] = modified_devices
        return modified_scan_data

    def _passes_hostname_filter(self, device_data: Dict, hostname_filters: List[str]) -> bool:
        """Check if device passes hostname filter"""
        device_name = device_data.get('sys_name', '').lower()
        if not device_name:
            device_name = device_data.get('device_name', '').lower()
        if not device_name:
            device_name = device_data.get('primary_ip', device_data.get('ip_address', '')).lower()

        for hostname_pattern in hostname_filters:
            if hostname_pattern in device_name:
                return True
        return False


class CMDBImportWidget(QWidget):
    """Main CMDB import widget"""

    def __init__(self, parent=None, theme_manager=None):
        super().__init__(parent)
        self.parent = parent
        # Use the real ThemeLibrary if available, otherwise create a fallback
        if theme_manager:
            self.theme_manager = theme_manager
        else:
            self.theme_manager = ThemeLibrary()

        self.current_theme = 'cyberpunk'

        # Initialize domain stripper and vendor normalizer
        self.domain_stripper = DomainStripper()
        self.vendor_normalizer = VendorNormalizer()

        # State variables
        self.scan_files = []
        self.loaded_scan_data = {}
        self.db_path = "napalm_cmdb.db"
        self.fingerprint_file = "vendor_fingerprints.yaml"

        # Settings
        self.settings = QSettings("TerminalTelemetry", "CMDBImport")

        self.setup_ui()
        self.apply_theme()
        self.load_settings()

    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Title
        title_label = QLabel("CMDB Scanner Import Tool - Enhanced with Vendor Normalization")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Main splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(main_splitter)

        # Left panel - Configuration
        left_panel = self.create_config_panel()
        main_splitter.addWidget(left_panel)

        # Right panel - Data preview and results
        right_panel = self.create_preview_panel()
        main_splitter.addWidget(right_panel)

        # Set splitter proportions
        main_splitter.setSizes([400, 800])

        # Bottom panel - Progress and controls
        bottom_panel = self.create_control_panel()
        layout.addWidget(bottom_panel)

    def create_config_panel(self) -> QWidget:
        """Create the configuration panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # File selection group
        file_group = QGroupBox("Scan Files")
        file_layout = QVBoxLayout(file_group)

        # File selection buttons
        file_button_layout = QHBoxLayout()
        self.add_files_btn = QPushButton("Add Files...")
        self.add_files_btn.clicked.connect(self.add_scan_files)
        file_button_layout.addWidget(self.add_files_btn)

        self.add_directory_btn = QPushButton("Add Directory...")
        self.add_directory_btn.clicked.connect(self.add_scan_directory)
        file_button_layout.addWidget(self.add_directory_btn)

        self.clear_files_btn = QPushButton("Clear")
        self.clear_files_btn.clicked.connect(self.clear_scan_files)
        file_button_layout.addWidget(self.clear_files_btn)

        file_layout.addLayout(file_button_layout)

        # File list
        self.files_list = QTreeWidget()
        self.files_list.setHeaderLabels(["Scan Files", "Status"])
        self.files_list.itemDoubleClicked.connect(self.preview_scan_file)
        file_layout.addWidget(self.files_list)

        layout.addWidget(file_group)

        # Database settings group
        db_group = QGroupBox("Database Settings")
        db_layout = QGridLayout(db_group)

        db_layout.addWidget(QLabel("Database Path:"), 0, 0)
        self.db_path_edit = QLineEdit(self.db_path)
        db_layout.addWidget(self.db_path_edit, 0, 1)

        self.db_browse_btn = QPushButton("Browse...")
        self.db_browse_btn.clicked.connect(self.browse_database)
        db_layout.addWidget(self.db_browse_btn, 0, 2)

        db_layout.addWidget(QLabel("Fingerprint File:"), 1, 0)
        self.fingerprint_edit = QLineEdit(self.fingerprint_file)
        db_layout.addWidget(self.fingerprint_edit, 1, 1)

        self.fingerprint_browse_btn = QPushButton("Browse...")
        self.fingerprint_browse_btn.clicked.connect(self.browse_fingerprint_file)
        db_layout.addWidget(self.fingerprint_browse_btn, 1, 2)

        layout.addWidget(db_group)

        # Data Processing Settings Group
        processing_group = QGroupBox("Data Processing")
        processing_layout = QVBoxLayout(processing_group)

        # Domain stripping settings
        domain_section = QGroupBox("Domain Name Processing")
        domain_layout = QVBoxLayout(domain_section)

        # Enable domain stripping checkbox
        self.strip_domains_check = QCheckBox("Strip domain names from device names")
        self.strip_domains_check.setChecked(True)
        self.strip_domains_check.setToolTip("Remove domain suffixes (e.g., .local, .corp, .com) from device names")
        domain_layout.addWidget(self.strip_domains_check)

        # Custom domain input
        custom_domain_layout = QHBoxLayout()
        custom_domain_layout.addWidget(QLabel("Custom domains to strip:"))
        self.custom_domains_edit = QLineEdit()
        self.custom_domains_edit.setPlaceholderText("e.g., mycompany.com,internal.local (comma-separated)")
        self.custom_domains_edit.textChanged.connect(self.update_custom_domains)
        custom_domain_layout.addWidget(self.custom_domains_edit)
        domain_layout.addLayout(custom_domain_layout)

        processing_layout.addWidget(domain_section)

        # Vendor normalization settings
        vendor_section = QGroupBox("Vendor Name Normalization")
        vendor_layout = QVBoxLayout(vendor_section)

        # Enable vendor normalization checkbox
        self.normalize_vendors_check = QCheckBox("Normalize vendor names")
        self.normalize_vendors_check.setChecked(True)
        self.normalize_vendors_check.setToolTip(
            "Standardize vendor names (e.g., 'CISCO' -> 'cisco', 'Hewlett Packard' -> 'hp')")
        vendor_layout.addWidget(self.normalize_vendors_check)

        # Vendor normalization preview button
        vendor_button_layout = QHBoxLayout()
        self.preview_vendor_norm_btn = QPushButton("Preview Vendor Normalization...")
        self.preview_vendor_norm_btn.clicked.connect(self.preview_vendor_normalization)
        self.preview_vendor_norm_btn.setEnabled(False)
        vendor_button_layout.addWidget(self.preview_vendor_norm_btn)
        vendor_button_layout.addStretch()
        vendor_layout.addLayout(vendor_button_layout)

        processing_layout.addWidget(vendor_section)
        layout.addWidget(processing_group)

        # Filter settings group
        filter_group = QGroupBox("Import Filters")
        filter_layout = QVBoxLayout(filter_group)

        # Vendor filter
        vendor_layout = QHBoxLayout()
        vendor_layout.addWidget(QLabel("Vendors:"))
        self.vendor_filter = QLineEdit()
        self.vendor_filter.setPlaceholderText("e.g., cisco,hp,aruba (leave empty for all)")
        vendor_layout.addWidget(self.vendor_filter)
        filter_layout.addLayout(vendor_layout)

        # Device type filter
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Device Types:"))
        self.type_filter = QLineEdit()
        self.type_filter.setPlaceholderText("e.g., switch,router,ups (leave empty for all)")
        type_layout.addWidget(self.type_filter)
        filter_layout.addLayout(type_layout)

        # Hostname filter
        hostname_layout = QHBoxLayout()
        hostname_layout.addWidget(QLabel("Hostnames:"))
        self.hostname_filter = QLineEdit()
        self.hostname_filter.setPlaceholderText("e.g., sw-01,rtr-,core- (partial matches, leave empty for all)")
        hostname_layout.addWidget(self.hostname_filter)
        filter_layout.addLayout(hostname_layout)

        # Confidence threshold
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Min Confidence:"))
        self.confidence_spin = QSpinBox()
        self.confidence_spin.setRange(0, 100)
        self.confidence_spin.setValue(0)
        self.confidence_spin.setSuffix("%")
        conf_layout.addWidget(self.confidence_spin)
        conf_layout.addStretch()
        filter_layout.addLayout(conf_layout)

        layout.addWidget(filter_group)

        # Options group
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)

        self.dry_run_check = QCheckBox("Dry Run (Preview Only)")
        self.dry_run_check.setChecked(True)
        options_layout.addWidget(self.dry_run_check)

        layout.addWidget(options_group)

        # Theme selection - only show if theme manager is available
        if self.theme_manager:
            theme_group = QGroupBox("Theme")
            theme_layout = QHBoxLayout(theme_group)

            self.theme_combo = QComboBox()
            self.theme_combo.addItems(self.theme_manager.get_theme_names())
            self.theme_combo.setCurrentText(self.current_theme)
            self.theme_combo.currentTextChanged.connect(self.change_theme)
            theme_layout.addWidget(self.theme_combo)
            theme_group.setVisible(False)
            layout.addWidget(theme_group)

        layout.addStretch()
        return panel

    def update_custom_domains(self):
        """Update the domain stripper with custom domains"""
        custom_domains_text = self.custom_domains_edit.text().strip()

        # Reset domain stripper to default patterns
        self.domain_stripper = DomainStripper()

        # Add custom domains if specified
        if custom_domains_text:
            domains = [d.strip() for d in custom_domains_text.split(',') if d.strip()]
            for domain in domains:
                self.domain_stripper.add_custom_domain(domain)

    def preview_vendor_normalization(self):
        """Preview vendor normalization for loaded scan data"""
        if not hasattr(self, 'loaded_scan_data') or not self.loaded_scan_data:
            QMessageBox.warning(self, "Warning", "Please load device preview first")
            return

        devices = self.loaded_scan_data.get('devices', {})
        vendors = [device_data.get('vendor', '') for device_data in devices.values()]

        vendor_stats = self.vendor_normalizer.get_normalization_stats(vendors)

        if not vendor_stats['normalizations']:
            QMessageBox.information(self, "Vendor Normalization", "No vendor names need normalization!")
            return

        dialog = VendorNormalizationDialog(vendor_stats, self.vendor_normalizer, self)

        # Apply theme to dialog if theme manager is available
        if self.theme_manager:
            self.theme_manager.apply_theme(dialog, self.current_theme)

        dialog.exec()

    def create_preview_panel(self) -> QWidget:
        """Create the data preview panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Tab widget for different views
        self.preview_tabs = QTabWidget()

        # Device preview tab
        self.device_preview_tab = self.create_device_preview_tab()
        self.preview_tabs.addTab(self.device_preview_tab, "Device Preview")

        # Statistics tab
        self.stats_tab = self.create_stats_tab()
        self.preview_tabs.addTab(self.stats_tab, "Statistics")

        # Log tab
        self.log_tab = self.create_log_tab()
        self.preview_tabs.addTab(self.log_tab, "Import Log")

        layout.addWidget(self.preview_tabs)
        return panel

    def create_device_preview_tab(self) -> QWidget:
        """Create device preview tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_layout = QHBoxLayout()
        self.load_preview_btn = QPushButton("Load Preview")
        self.load_preview_btn.clicked.connect(self.load_device_preview)
        controls_layout.addWidget(self.load_preview_btn)

        self.export_preview_btn = QPushButton("Export Preview...")
        self.export_preview_btn.clicked.connect(self.export_preview)
        self.export_preview_btn.setEnabled(False)
        controls_layout.addWidget(self.export_preview_btn)

        controls_layout.addStretch()

        # Device count label
        self.device_count_label = QLabel("No devices loaded")
        controls_layout.addWidget(self.device_count_label)

        layout.addLayout(controls_layout)

        # Device table
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(13)
        self.device_table.setHorizontalHeaderLabels([
            "Device Name (Original)", "Device Name (Stripped)", "IP Address",
            "Vendor (Original)", "Vendor (Normalized)", "Model", "Serial",
            "Device Type", "Site", "Confidence", "Method", "Processing", "Notes"
        ])
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setSortingEnabled(True)
        self.device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # Set column widths
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        layout.addWidget(self.device_table)
        return tab

    def create_stats_tab(self) -> QWidget:
        """Create statistics tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Statistics tree
        self.stats_tree = QTreeWidget()
        self.stats_tree.setHeaderLabels(["Category", "Count", "Details"])
        layout.addWidget(self.stats_tree)

        return tab

    def create_log_tab(self) -> QWidget:
        """Create import log tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Log controls
        log_controls = QHBoxLayout()
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        log_controls.addWidget(self.clear_log_btn)

        self.save_log_btn = QPushButton("Save Log...")
        self.save_log_btn.clicked.connect(self.save_log)
        log_controls.addWidget(self.save_log_btn)

        log_controls.addStretch()
        layout.addLayout(log_controls)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)

        return tab

    def create_control_panel(self) -> QWidget:
        """Create control panel with progress and import button"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Progress label
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # Control buttons
        button_layout = QHBoxLayout()

        self.validate_btn = QPushButton("Validate Configuration")
        self.validate_btn.clicked.connect(self.validate_configuration)
        button_layout.addWidget(self.validate_btn)

        button_layout.addStretch()

        self.import_btn = QPushButton("Start Import")
        self.import_btn.clicked.connect(self.start_import)
        self.import_btn.setEnabled(False)
        button_layout.addWidget(self.import_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_import)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)
        return panel

    def add_scan_files(self):
        """Add individual scan files"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Scan Files",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        for file_path in files:
            if file_path not in self.scan_files:
                self.scan_files.append(file_path)

        self.update_files_list()

    def add_scan_directory(self):
        """Add all JSON files from a directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Scan Directory"
        )

        if directory:
            scan_dir = Path(directory)
            json_files = list(scan_dir.glob("*.json"))

            for file_path in json_files:
                file_str = str(file_path)
                if file_str not in self.scan_files:
                    self.scan_files.append(file_str)

            self.update_files_list()

    def clear_scan_files(self):
        """Clear all scan files"""
        self.scan_files.clear()
        self.loaded_scan_data.clear()
        self.update_files_list()
        self.device_table.setRowCount(0)
        self.device_count_label.setText("No devices loaded")
        self.export_preview_btn.setEnabled(False)
        self.preview_vendor_norm_btn.setEnabled(False)

    def update_files_list(self):
        """Update the files list widget"""
        self.files_list.clear()

        for file_path in self.scan_files:
            item = QTreeWidgetItem()
            item.setText(0, Path(file_path).name)
            item.setText(1, "Ready")
            item.setData(0, Qt.ItemDataRole.UserRole, file_path)
            self.files_list.addTopLevelItem(item)

        # Enable/disable import button based on file count
        self.import_btn.setEnabled(len(self.scan_files) > 0)

    def preview_scan_file(self, item):
        """Preview a scan file when double-clicked"""
        file_path = item.data(0, Qt.ItemDataRole.UserRole)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                scan_data = json.load(f)

            dialog = ScanDataPreviewDialog(scan_data, self.domain_stripper, self.vendor_normalizer, self)

            # Apply theme to dialog if theme manager is available
            if self.theme_manager:
                self.theme_manager.apply_theme(dialog, self.current_theme)

            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to preview file:\n{str(e)}")

    def browse_database(self):
        """Browse for database file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Database File",
            self.db_path,
            "SQLite Database (*.db);;All Files (*)"
        )

        if file_path:
            self.db_path_edit.setText(file_path)
            self.db_path = file_path

    def browse_fingerprint_file(self):
        """Browse for fingerprint file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Fingerprint File",
            self.fingerprint_file,
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )

        if file_path:
            self.fingerprint_edit.setText(file_path)
            self.fingerprint_file = file_path

    def get_filters(self) -> Dict:
        """Get current filter settings"""
        filters = {}

        # Vendor filter
        vendors = self.vendor_filter.text().strip()
        if vendors:
            filters['vendors'] = [v.strip().lower() for v in vendors.split(',')]

        # Device type filter
        types = self.type_filter.text().strip()
        if types:
            filters['device_types'] = [t.strip().lower() for t in types.split(',')]

        # Hostname filter
        hostnames = self.hostname_filter.text().strip()
        if hostnames:
            filters['hostnames'] = [h.strip().lower() for h in hostnames.split(',')]

        # Confidence filter
        min_confidence = self.confidence_spin.value()
        if min_confidence > 0:
            filters['min_confidence'] = min_confidence

        return filters

    def validate_configuration(self):
        """Validate the current configuration"""
        issues = []

        # Check if files are selected
        if not self.scan_files:
            issues.append("No scan files selected")

        # Check database path
        db_path = self.db_path_edit.text().strip()
        if not db_path:
            issues.append("Database path not specified")
        elif not Path(db_path).exists():
            issues.append(f"Database file does not exist: {db_path}")

        # Check fingerprint file
        fp_path = self.fingerprint_edit.text().strip()
        if fp_path and not Path(fp_path).exists():
            issues.append(f"Fingerprint file does not exist: {fp_path}")

        # Check if SCANNER is available
        if not SCANNER_AVAILABLE:
            issues.append("Scanner modules not available - some features may be limited")

        if issues:
            QMessageBox.warning(
                self,
                "Configuration Issues",
                "The following issues were found:\n\n" + "\n".join(f"• {issue}" for issue in issues)
            )
        else:
            QMessageBox.information(
                self,
                "Configuration Valid",
                "Configuration is valid and ready for import."
            )

    def normalize_vendors_in_devices(self, devices: Dict) -> Dict:
        """Normalize vendor names in device data for preview"""
        if not self.normalize_vendors_check.isChecked():
            return devices

        normalized_devices = {}

        for device_id, device_data in devices.items():
            # Create a copy of device data
            normalized_device = device_data.copy()

            # Normalize vendor name
            if 'vendor' in normalized_device:
                original_vendor = normalized_device['vendor']
                normalized_vendor = self.vendor_normalizer.normalize_vendor(original_vendor)
                normalized_device['vendor'] = normalized_vendor

                # Keep track of original vendor if it was changed
                if normalized_vendor != original_vendor:
                    normalized_device['original_vendor'] = original_vendor

            normalized_devices[device_id] = normalized_device

        return normalized_devices

    def strip_domains_from_devices(self, devices: Dict) -> Dict:
        """Strip domains from device data for preview"""
        if not self.strip_domains_check.isChecked():
            return devices

        stripped_devices = {}

        for device_id, device_data in devices.items():
            # Create a copy of device data
            stripped_device = device_data.copy()

            # Strip domain from sys_name
            if 'sys_name' in stripped_device and stripped_device['sys_name']:
                original_name = stripped_device['sys_name']
                stripped_name = self.domain_stripper.strip_domain(original_name)
                stripped_device['sys_name'] = stripped_name

                # Keep track of original name
                if stripped_name != original_name:
                    stripped_device['original_sys_name'] = original_name

            # Strip domain from device_name if present
            if 'device_name' in stripped_device and stripped_device['device_name']:
                original_name = stripped_device['device_name']
                stripped_name = self.domain_stripper.strip_domain(original_name)
                stripped_device['device_name'] = stripped_name

                if stripped_name != original_name:
                    stripped_device['original_device_name'] = original_name

            # Use the stripped name for device ID if it was hostname-based
            new_device_id = device_id
            if device_id in [device_data.get('sys_name'), device_data.get('device_name')]:
                new_device_id = stripped_device.get('sys_name') or stripped_device.get('device_name') or device_id

            stripped_devices[new_device_id] = stripped_device

        return stripped_devices

    def load_device_preview(self):
        """Load device preview from scan files"""
        if not self.scan_files:
            QMessageBox.warning(self, "Warning", "No scan files selected")
            return

        try:
            self.log("Loading device preview...")

            # Update custom domains
            self.update_custom_domains()

            # Clear existing data
            self.loaded_scan_data.clear()
            all_devices = {}

            # Load all scan files
            for file_path in self.scan_files:
                self.log(f"Loading {Path(file_path).name}...")

                with open(file_path, 'r', encoding='utf-8') as f:
                    scan_data = json.load(f)

                # Normalize scan data if needed
                if SCANNER_AVAILABLE:
                    importer = ScanImporter(
                        self.db_path_edit.text().strip(),
                        self.fingerprint_edit.text().strip(),
                        dry_run=True
                    )
                    scan_data = importer.normalize_scan_data(scan_data)

                devices = scan_data.get('devices', {})
                all_devices.update(devices)

            # Apply data processing
            processed_devices = all_devices.copy()

            # Normalize vendor names
            processed_devices = self.normalize_vendors_in_devices(processed_devices)

            # Strip domains from device names
            processed_devices = self.strip_domains_from_devices(processed_devices)

            self.loaded_scan_data = {'devices': processed_devices}

            # Apply filters
            filters = self.get_filters()
            filtered_devices = self.apply_preview_filters(processed_devices, filters)

            # Update device table
            self.populate_device_table(filtered_devices, all_devices)

            # Update statistics
            self.update_statistics(processed_devices, filtered_devices)

            # Enable vendor normalization preview
            self.preview_vendor_norm_btn.setEnabled(True)

            processing_info = []
            if self.normalize_vendors_check.isChecked():
                processing_info.append("vendor normalization")
            if self.strip_domains_check.isChecked():
                processing_info.append("domain stripping")

            processing_text = f" with {' and '.join(processing_info)}" if processing_info else " without processing"

            self.log(
                f"Preview loaded: {len(filtered_devices)} devices (filtered from {len(all_devices)}){processing_text}")

        except Exception as e:
            self.log(f"Error loading preview: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load preview:\n{str(e)}")

    def apply_preview_filters(self, devices: Dict, filters: Dict) -> Dict:
        """Apply filters to device data for preview"""
        if not filters:
            return devices

        filtered = {}

        for device_id, device_data in devices.items():
            # Vendor filter (use normalized vendor if available)
            if 'vendors' in filters:
                device_vendor = device_data.get('vendor', '').lower()
                if device_vendor not in filters['vendors']:
                    continue

            # Device type filter
            if 'device_types' in filters:
                device_type = device_data.get('device_type', '').lower()
                if device_type not in filters['device_types']:
                    continue

            # Confidence filter
            if 'min_confidence' in filters:
                confidence = device_data.get('confidence_score', 0)
                if confidence < filters['min_confidence']:
                    continue

            # Hostname filter (partial matching) - use processed names
            if 'hostnames' in filters:
                device_name = device_data.get('sys_name', '').lower()
                # If no sys_name, try to get from device_id or ip
                if not device_name:
                    device_name = device_id.lower()

                # Check if any hostname filter matches (partial matching)
                hostname_match = False
                for hostname_pattern in filters['hostnames']:
                    if hostname_pattern in device_name:
                        hostname_match = True
                        break

                if not hostname_match:
                    continue

            filtered[device_id] = device_data

        return filtered

    def populate_device_table(self, devices: Dict, original_devices: Dict = None):
        """Populate the device table with device data"""
        self.device_table.setRowCount(len(devices))

        for row, (device_id, device_data) in enumerate(devices.items()):
            # Original Device Name
            original_name = device_data.get('original_sys_name', device_data.get('sys_name', device_id))
            self.device_table.setItem(row, 0, QTableWidgetItem(original_name))

            # Stripped Device Name
            stripped_name = device_data.get('sys_name', device_id)
            if stripped_name != original_name:
                item = QTableWidgetItem(stripped_name)
                # Highlight cells where domain was stripped
                theme_colors = self.theme_manager.get_colors(self.current_theme) if self.theme_manager else None

                if theme_colors:
                    highlight_color = QColor(theme_colors.get('success', '#00ff00'))
                    highlight_color.setAlpha(100)  # Semi-transparent
                    item.setBackground(highlight_color)
                else:
                    item.setBackground(QColor(200, 255, 200))
                self.device_table.setItem(row, 1, item)
            else:
                self.device_table.setItem(row, 1, QTableWidgetItem(stripped_name))

            # IP Address
            self.device_table.setItem(row, 2, QTableWidgetItem(
                device_data.get('primary_ip', device_data.get('ip_address', ''))
            ))

            # Original Vendor
            original_vendor = device_data.get('original_vendor', device_data.get('vendor', ''))
            self.device_table.setItem(row, 3, QTableWidgetItem(original_vendor))

            # Normalized Vendor
            normalized_vendor = device_data.get('vendor', '')
            if 'original_vendor' in device_data and normalized_vendor != original_vendor:
                item = QTableWidgetItem(normalized_vendor)
                # Highlight normalized vendors
                theme_colors = self.theme_manager.get_colors(self.current_theme) if self.theme_manager else None
                if theme_colors:
                    highlight_color = QColor(theme_colors.get('warning', '#ffff00'))
                    highlight_color.setAlpha(100)
                    item.setBackground(highlight_color)
                else:
                    item.setBackground(QColor(255, 255, 200))
                self.device_table.setItem(row, 4, item)
            else:
                self.device_table.setItem(row, 4, QTableWidgetItem(normalized_vendor))

            # Model
            self.device_table.setItem(row, 5, QTableWidgetItem(
                device_data.get('model', '')
            ))

            # Serial
            self.device_table.setItem(row, 6, QTableWidgetItem(
                device_data.get('serial_number', '')
            ))

            # Device Type
            self.device_table.setItem(row, 7, QTableWidgetItem(
                device_data.get('device_type', '')
            ))

            # Site (would need extraction logic)
            self.device_table.setItem(row, 8, QTableWidgetItem(''))

            # Confidence
            self.device_table.setItem(row, 9, QTableWidgetItem(
                str(device_data.get('confidence_score', 0))
            ))

            # Method
            self.device_table.setItem(row, 10, QTableWidgetItem(
                device_data.get('detection_method', '')
            ))

            # Processing Applied
            processing = []
            if 'original_sys_name' in device_data:
                processing.append("Domain stripped")
            if 'original_vendor' in device_data:
                processing.append("Vendor normalized")
            self.device_table.setItem(row, 11, QTableWidgetItem("; ".join(processing)))

            # Notes
            notes = f"From: {device_id}"
            if 'original_sys_name' in device_data:
                notes += f" (stripped from: {device_data['original_sys_name']})"
            if 'original_vendor' in device_data:
                notes += f" (vendor: {device_data['original_vendor']} -> {normalized_vendor})"
            self.device_table.setItem(row, 12, QTableWidgetItem(notes))

        self.device_table.resizeColumnsToContents()
        self.device_count_label.setText(f"{len(devices)} devices")
        self.export_preview_btn.setEnabled(len(devices) > 0)

    def update_statistics(self, all_devices: Dict, filtered_devices: Dict):
        """Update the statistics tree"""
        self.stats_tree.clear()

        # Overall stats
        overall = QTreeWidgetItem(["Overall", "", ""])
        overall.addChild(QTreeWidgetItem(["Total Devices", str(len(all_devices)), ""]))
        overall.addChild(QTreeWidgetItem(["Filtered Devices", str(len(filtered_devices)), ""]))

        # Count devices with stripped domains
        stripped_count = sum(1 for device in all_devices.values()
                             if 'original_sys_name' in device or 'original_device_name' in device)
        overall.addChild(QTreeWidgetItem(["Domains Stripped", str(stripped_count), ""]))

        # Count devices with normalized vendors
        normalized_count = sum(1 for device in all_devices.values() if 'original_vendor' in device)
        overall.addChild(QTreeWidgetItem(["Vendors Normalized", str(normalized_count), ""]))

        self.stats_tree.addTopLevelItem(overall)

        # Vendor breakdown (using normalized vendors)
        vendors = {}
        original_vendors = {}
        device_types = {}

        for device_data in filtered_devices.values():
            vendor = device_data.get('vendor', 'unknown')
            original_vendor = device_data.get('original_vendor', vendor)
            device_type = device_data.get('device_type', 'unknown')

            vendors[vendor] = vendors.get(vendor, 0) + 1
            original_vendors[original_vendor] = original_vendors.get(original_vendor, 0) + 1
            device_types[device_type] = device_types.get(device_type, 0) + 1

        # Normalized vendor tree
        vendor_item = QTreeWidgetItem(["Normalized Vendors", str(len(vendors)), ""])
        for vendor, count in sorted(vendors.items()):
            vendor_item.addChild(QTreeWidgetItem([vendor, str(count), ""]))
        self.stats_tree.addTopLevelItem(vendor_item)

        # Original vendor tree (if different from normalized)
        if original_vendors != vendors:
            orig_vendor_item = QTreeWidgetItem(["Original Vendors", str(len(original_vendors)), ""])
            for vendor, count in sorted(original_vendors.items()):
                orig_vendor_item.addChild(QTreeWidgetItem([vendor, str(count), ""]))
            self.stats_tree.addTopLevelItem(orig_vendor_item)

        # Device type tree
        type_item = QTreeWidgetItem(["Device Types", str(len(device_types)), ""])
        for device_type, count in sorted(device_types.items()):
            type_item.addChild(QTreeWidgetItem([device_type, str(count), ""]))
        self.stats_tree.addTopLevelItem(type_item)

        # Expand all items
        self.stats_tree.expandAll()

    def export_preview(self):
        """Export the current preview to a file"""
        if not hasattr(self, 'loaded_scan_data') or not self.loaded_scan_data:
            QMessageBox.warning(self, "Warning", "No preview data to export")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Preview",
            "device_preview.json",
            "JSON Files (*.json);;CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        try:
            if file_path.lower().endswith('.csv'):
                # Export as CSV
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)

                    # Write header
                    writer.writerow([
                        "Original Device Name", "Stripped Device Name", "IP Address",
                        "Original Vendor", "Normalized Vendor", "Model", "Serial",
                        "Device Type", "Confidence", "Method", "Domain Stripped", "Vendor Normalized"
                    ])

                    # Write data
                    devices = self.loaded_scan_data.get('devices', {})
                    for device_id, device_data in devices.items():
                        original_name = device_data.get('original_sys_name', device_data.get('sys_name', device_id))
                        stripped_name = device_data.get('sys_name', device_id)
                        original_vendor = device_data.get('original_vendor', device_data.get('vendor', ''))
                        normalized_vendor = device_data.get('vendor', '')

                        domain_stripped = "Yes" if 'original_sys_name' in device_data else "No"
                        vendor_normalized = "Yes" if 'original_vendor' in device_data else "No"

                        writer.writerow([
                            original_name,
                            stripped_name,
                            device_data.get('primary_ip', device_data.get('ip_address', '')),
                            original_vendor,
                            normalized_vendor,
                            device_data.get('model', ''),
                            device_data.get('serial_number', ''),
                            device_data.get('device_type', ''),
                            device_data.get('confidence_score', 0),
                            device_data.get('detection_method', ''),
                            domain_stripped,
                            vendor_normalized
                        ])
            else:
                # Export as JSON
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.loaded_scan_data, f, indent=2)

            self.log(f"Preview exported to {file_path}")
            QMessageBox.information(self, "Export Complete", f"Preview exported to:\n{file_path}")

        except Exception as e:
            self.log(f"Export error: {str(e)}")
            QMessageBox.critical(self, "Export Error", f"Failed to export preview:\n{str(e)}")

    def start_import(self):
        """Start the import process"""
        if not self.scan_files:
            QMessageBox.warning(self, "Warning", "No scan files selected")
            return

        # Validate configuration first
        db_path = self.db_path_edit.text().strip()
        if not db_path:
            QMessageBox.warning(self, "Warning", "Database path not specified")
            return

        # Update custom domains
        self.update_custom_domains()

        # Get settings
        filters = self.get_filters()
        fingerprint_file = self.fingerprint_edit.text().strip()
        dry_run = self.dry_run_check.isChecked()

        # Confirm import
        if not dry_run:
            processing_info = []
            if self.normalize_vendors_check.isChecked():
                processing_info.append("vendor normalization")
            if self.strip_domains_check.isChecked():
                processing_info.append("domain stripping")

            processing_text = f" with {' and '.join(processing_info)}" if processing_info else ""

            reply = QMessageBox.question(
                self,
                "Confirm Import",
                f"This will import {len(self.scan_files)} scan files into the database{processing_text}.\n"
                f"Database: {db_path}\n"
                f"Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        # Start import worker thread
        self.import_thread = ImportWorkerThread(
            self.scan_files, db_path, filters, fingerprint_file,
            self.domain_stripper, self.vendor_normalizer, dry_run
        )

        self.import_thread.progress_updated.connect(self.update_progress)
        self.import_thread.import_completed.connect(self.import_completed)
        self.import_thread.error_occurred.connect(self.import_error)

        # Update UI
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.import_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        processing_info = []
        if self.normalize_vendors_check.isChecked():
            processing_info.append("vendor normalization")
        if self.strip_domains_check.isChecked():
            processing_info.append("domain stripping")

        processing_text = f" with {' and '.join(processing_info)}" if processing_info else ""

        self.log(f"Starting import: {len(self.scan_files)} files, dry_run={dry_run}{processing_text}")
        self.import_thread.start()

    def cancel_import(self):
        """Cancel the current import"""
        if hasattr(self, 'import_thread') and self.import_thread.isRunning():
            self.import_thread.terminate()
            self.import_thread.wait(5000)  # Wait up to 5 seconds

        self.import_completed({"cancelled": True})

    def update_progress(self, percentage: int, message: str):
        """Update progress bar and message"""
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(message)
        self.log(f"Progress: {percentage}% - {message}")

    def import_completed(self, stats: Dict):
        """Handle import completion with detailed error logging - REPLACE EXISTING METHOD"""
        # Update UI
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.import_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if stats.get("cancelled"):
            self.log("Import cancelled by user")
            QMessageBox.information(self, "Import Cancelled", "Import operation was cancelled")
            return

        # Log detailed statistics
        self.log("=" * 60)
        self.log("IMPORT COMPLETED - DETAILED RESULTS")
        self.log("=" * 60)

        # Basic statistics
        devices_processed = stats.get('devices_processed', 0)
        devices_imported = stats.get('devices_imported', 0)
        devices_updated = stats.get('devices_updated', 0)
        devices_skipped = stats.get('devices_skipped', 0)
        duplicates_found = stats.get('duplicates_found', 0)
        error_count = stats.get('errors', 0)

        self.log(f"Devices processed: {devices_processed:,}")
        self.log(f"Devices imported: {devices_imported:,}")
        self.log(f"Devices updated: {devices_updated:,}")
        self.log(f"Devices skipped: {devices_skipped:,}")
        self.log(f"Duplicates found: {duplicates_found:,}")
        self.log(f"Errors encountered: {error_count:,}")

        # Log detailed errors if available
        if error_count > 0:
            self.log("")
            self.log("ERROR DETAILS:")
            self.log("-" * 40)

            # Check for error_details in stats
            error_details = stats.get('error_details', [])
            if error_details:
                for i, error in enumerate(error_details, 1):
                    if isinstance(error, dict):
                        device_id = error.get('device_id', 'Unknown')
                        error_msg = error.get('error', 'Unknown error')
                        error_type = error.get('error_type', 'General')
                        self.log(f"Error {i}: [{error_type}] Device '{device_id}': {error_msg}")
                    else:
                        self.log(f"Error {i}: {str(error)}")
            else:
                # If no detailed errors, check for error_messages
                error_messages = stats.get('error_messages', [])
                if error_messages:
                    for i, msg in enumerate(error_messages, 1):
                        self.log(f"Error {i}: {msg}")
                else:
                    self.log("Error details not available from scanner - check scanner logs")
                    # Try to provide some helpful information
                    if hasattr(self, 'last_import_errors'):
                        for i, error in enumerate(self.last_import_errors, 1):
                            self.log(f"Error {i}: {error}")

        # Log processing details if available
        processing_details = stats.get('processing_details', {})
        if processing_details:
            self.log("")
            self.log("PROCESSING DETAILS:")
            self.log("-" * 40)

            vendors_normalized = processing_details.get('vendors_normalized', 0)
            domains_stripped = processing_details.get('domains_stripped', 0)

            if vendors_normalized > 0:
                self.log(f"Vendor names normalized: {vendors_normalized}")

            if domains_stripped > 0:
                self.log(f"Domain names stripped: {domains_stripped}")

            # Log vendor normalization details
            vendor_changes = processing_details.get('vendor_normalizations', {})
            if vendor_changes:
                self.log("Vendor normalization changes:")
                for original, normalized in vendor_changes.items():
                    self.log(f"  {original} → {normalized}")

        # Log file-specific results if available
        file_results = stats.get('file_results', {})
        if file_results:
            self.log("")
            self.log("FILE-SPECIFIC RESULTS:")
            self.log("-" * 40)
            for filename, file_stats in file_results.items():
                self.log(f"File: {filename}")
                self.log(f"  Devices: {file_stats.get('devices', 0)}")
                self.log(f"  Imported: {file_stats.get('imported', 0)}")
                self.log(f"  Updated: {file_stats.get('updated', 0)}")
                self.log(f"  Skipped: {file_stats.get('skipped', 0)}")
                self.log(f"  Errors: {file_stats.get('errors', 0)}")

        # Log warnings if available
        warnings = stats.get('warnings', [])
        if warnings:
            self.log("")
            self.log("WARNINGS:")
            self.log("-" * 40)
            for i, warning in enumerate(warnings, 1):
                self.log(f"Warning {i}: {warning}")

        # Log performance metrics if available
        performance = stats.get('performance', {})
        if performance:
            self.log("")
            self.log("PERFORMANCE METRICS:")
            self.log("-" * 40)
            duration = performance.get('duration', 0)
            if duration > 0:
                self.log(f"Total duration: {duration:.2f} seconds")
                if devices_processed > 0:
                    rate = devices_processed / duration
                    self.log(f"Processing rate: {rate:.1f} devices/second")

        self.log("=" * 60)

        # Show results dialog with enhanced information
        if SCANNER_AVAILABLE:
            # Determine success level
            if error_count == 0:
                icon = QMessageBox.Icon.Information
                title = "Import Completed Successfully"
            elif error_count < devices_processed:
                icon = QMessageBox.Icon.Warning
                title = "Import Completed with Warnings"
            else:
                icon = QMessageBox.Icon.Critical
                title = "Import Completed with Errors"

            result_text = f"""Import completed!

    Statistics:
    • Devices processed: {devices_processed:,}
    • Devices imported: {devices_imported:,}
    • Devices updated: {devices_updated:,}
    • Devices skipped: {devices_skipped:,}
    • Duplicates found: {duplicates_found:,}
    • Errors: {error_count:,}

    {f"⚠️  {error_count} errors occurred. Check the Import Log tab for details." if error_count > 0 else "✅ All devices processed successfully!"}
    """

            msg = QMessageBox(icon, title, result_text)
            msg.exec()
        else:
            result_text = "Import process completed (limited functionality due to missing scanner modules)"
            QMessageBox.information(self, "Import Complete", result_text)

        # Switch to log tab if there were errors
        if error_count > 0:
            self.preview_tabs.setCurrentWidget(self.log_tab)



    def import_error(self, error_message: str):
        """Handle import error"""
        # Update UI
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.import_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        self.log(f"Import error: {error_message}")
        QMessageBox.critical(self, "Import Error", f"Import failed:\n{error_message}")

    def log(self, message: str):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_text.append(log_entry)

        # Auto-scroll to bottom
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def clear_log(self):
        """Clear the log"""
        self.log_text.clear()

    def save_log(self):
        """Save log to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log",
            f"import_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                QMessageBox.information(self, "Log Saved", f"Log saved to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save log:\n{str(e)}")

    def change_theme(self, theme_name: str):
        """Change the current theme"""
        self.current_theme = theme_name
        self.apply_theme()

    def apply_theme(self, theme_manager=None, theme_name=None):
        """Apply the current theme - compatible with both calling patterns"""

        # Handle parameter updates
        if theme_manager is not None:
            self.theme_manager = theme_manager
        if theme_name is not None:
            self.current_theme = theme_name

        # Apply theme using the real ThemeLibrary
        if self.theme_manager:
            try:
                # Get the theme to use - prefer current_theme, fallback to parent.theme
                theme_to_use = self.current_theme
                if hasattr(self, 'parent') and hasattr(self.parent, 'theme'):
                    theme_to_use = self.parent.theme

                theme = self.theme_manager.get_theme(theme_to_use)
                if theme:
                    stylesheet = self.theme_manager.generate_stylesheet(theme)
                    self.setStyleSheet(stylesheet)
                    print(f"Successfully applied theme: {theme_to_use}")
                else:
                    print(f"Theme '{theme_to_use}' not found")
                    self._apply_fallback_theme()

            except Exception as e:
                print(f"Error applying theme: {e}")
                self._apply_fallback_theme()
        else:
            self._apply_fallback_theme()

    def _apply_fallback_theme(self):
        """Apply basic fallback theme when ThemeLibrary is not available"""
        fallback_style = """
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555555;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #3c3c3c;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #0078d4;
            }
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 8px 16px;
                font-weight: bold;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #0078d4;
                color: #2b2b2b;
            }
            QPushButton:pressed {
                background-color: #6264a7;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #cccccc;
                border-color: #cccccc;
            }
            QTableWidget {
                background-color: #3c3c3c;
                alternate-background-color: #2b2b2b;
                selection-background-color: #0078d4;
                selection-color: #2b2b2b;
                gridline-color: #555555;
            }
            QTableWidget::item {
                padding: 5px;
                border-bottom: 1px solid #555555;
            }
            QHeaderView::section {
                background-color: #0078d4;
                color: #2b2b2b;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QTreeWidget {
                background-color: #3c3c3c;
                selection-background-color: #0078d4;
                selection-color: #2b2b2b;
            }
            QTreeWidget::item {
                padding: 3px;
                border-bottom: 1px solid #555555;
            }
            QTreeWidget::item:selected {
                background-color: #0078d4;
                color: #2b2b2b;
            }
            QTextEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                border: 2px solid #555555;
                width: 6px;
                height: 6px;
            }
            QSpinBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 3px;
                text-align: center;
                background-color: #3c3c3c;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 2px;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #3c3c3c;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                border: 1px solid #555555;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #0078d4;
                color: #2b2b2b;
            }
            QScrollBar:vertical {
                background-color: #3c3c3c;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #0078d4;
            }
        """
        self.setStyleSheet(fallback_style)

    def load_settings(self):
        """Load settings from QSettings"""
        # Load last used paths
        self.db_path = self.settings.value("db_path", self.db_path)
        self.db_path_edit.setText(self.db_path)

        self.fingerprint_file = self.settings.value("fingerprint_file", self.fingerprint_file)
        self.fingerprint_edit.setText(self.fingerprint_file)

        # Load processing settings
        self.strip_domains_check.setChecked(self.settings.value("strip_domains", True, type=bool))
        self.normalize_vendors_check.setChecked(self.settings.value("normalize_vendors", True, type=bool))
        self.custom_domains_edit.setText(self.settings.value("custom_domains", ""))

        # Load theme
        if hasattr(self, 'theme_combo'):
            saved_theme = self.settings.value("theme", self.current_theme)
            if saved_theme in self.theme_manager.get_theme_names():
                self.current_theme = saved_theme
                self.theme_combo.setCurrentText(saved_theme)

    def save_settings(self):
        """Save settings to QSettings"""
        self.settings.setValue("db_path", self.db_path_edit.text())
        self.settings.setValue("fingerprint_file", self.fingerprint_edit.text())
        self.settings.setValue("strip_domains", self.strip_domains_check.isChecked())
        self.settings.setValue("normalize_vendors", self.normalize_vendors_check.isChecked())
        self.settings.setValue("custom_domains", self.custom_domains_edit.text())
        self.settings.setValue("theme", self.current_theme)

    def closeEvent(self, event):
        """Handle close event"""
        self.save_settings()

        # Stop any running import
        if hasattr(self, 'import_thread') and self.import_thread.isRunning():
            self.import_thread.terminate()
            self.import_thread.wait(5000)

        event.accept()


class CMDBImportMainWindow(QMainWindow):
    """Main window wrapper for the import widget"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CMDB Scanner Import Tool - Enhanced with Vendor Normalization & Domain Stripping")
        self.setMinimumSize(1400, 800)

        # Create theme manager
        try:
            self.theme_manager = ThemeLibrary()
        except:
            self.theme_manager = SimpleThemeManager()

        # Create central widget
        self.import_widget = CMDBImportWidget(self, self.theme_manager)
        self.setCentralWidget(self.import_widget)

        # Create menu bar
        self.create_menu_bar()

        # Apply initial theme
        if hasattr(self.theme_manager, 'apply_theme'):
            try:
                self.theme_manager.apply_theme(self, self.theme_manager.current_theme)
            except:
                pass

    def create_menu_bar(self):
        """Create the application menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu('File')

        # Add files action
        add_files_action = file_menu.addAction('Add Scan Files...')
        add_files_action.setShortcut('Ctrl+O')
        add_files_action.triggered.connect(self.import_widget.add_scan_files)

        # Add directory action
        add_dir_action = file_menu.addAction('Add Scan Directory...')
        add_dir_action.setShortcut('Ctrl+D')
        add_dir_action.triggered.connect(self.import_widget.add_scan_directory)

        file_menu.addSeparator()

        # Export preview action
        export_action = file_menu.addAction('Export Preview...')
        export_action.setShortcut('Ctrl+E')
        export_action.triggered.connect(self.import_widget.export_preview)

        file_menu.addSeparator()

        # Exit action
        exit_action = file_menu.addAction('Exit')
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)

        # Tools menu
        tools_menu = menubar.addMenu('Tools')

        # Validate configuration action
        validate_action = tools_menu.addAction('Validate Configuration')
        validate_action.setShortcut('F5')
        validate_action.triggered.connect(self.import_widget.validate_configuration)

        # Load preview action
        preview_action = tools_menu.addAction('Load Device Preview')
        preview_action.setShortcut('F6')
        preview_action.triggered.connect(self.import_widget.load_device_preview)

        # Vendor normalization preview
        vendor_norm_action = tools_menu.addAction('Preview Vendor Normalization...')
        vendor_norm_action.setShortcut('F7')
        vendor_norm_action.triggered.connect(self.import_widget.preview_vendor_normalization)

        tools_menu.addSeparator()

        # Clear log action
        clear_log_action = tools_menu.addAction('Clear Log')
        clear_log_action.triggered.connect(self.import_widget.clear_log)

        # Help menu
        help_menu = menubar.addMenu('Help')

        # About action
        about_action = help_menu.addAction('About')
        about_action.triggered.connect(self.show_about)

    def show_about(self):
        """Show about dialog"""
        about_text = """
<h3>CMDB Scanner Import Tool</h3>
<p><b>Enhanced with Vendor Normalization & Domain Name Stripping</b></p>
<p>Version 2.1</p>

<p>A standalone GUI application for importing SNMP discovery scan data into NAPALM CMDB 
with advanced filtering, preview capabilities, vendor normalization, and domain name processing.</p>

<h4>Key Features:</h4>
<ul>
<li>Import multiple scan files or entire directories</li>
<li>Advanced device filtering by vendor, type, hostname, and confidence</li>
<li>Intelligent vendor name normalization (CISCO → cisco, HP → hp, etc.)</li>
<li>Domain name stripping with customizable patterns</li>
<li>Real-time preview with before/after processing</li>
<li>Export capabilities (JSON/CSV)</li>
<li>Dry-run mode for safe testing</li>
<li>Comprehensive logging and statistics</li>
<li>Custom vendor mapping configuration</li>
</ul>

<h4>Data Processing:</h4>
<p><b>Vendor Normalization:</b> Automatically standardizes vendor names to eliminate 
variations like 'CISCO' vs 'cisco' vs 'Cisco Systems'. Includes mappings for major 
network equipment vendors and supports custom mappings.</p>

<p><b>Domain Stripping:</b> Removes common domain suffixes (.local, .corp, .com, etc.) 
from device names before normalization and deduplication. Supports custom 
domain patterns for organization-specific domains.</p>

<p>Built with PyQt6 and designed for network administrators and CMDB managers.</p>
        """

        QMessageBox.about(self, "About CMDB Import Tool", about_text)


class ErrorCapturingScanImporter(ScanImporter):
    """
    Enhanced ScanImporter that captures detailed error information
    """

    def __init__(self, db_path: str, fingerprint_file: str = 'vendor_fingerprints.yaml', dry_run: bool = False):
        super().__init__(db_path, fingerprint_file, dry_run)

        # Add error tracking
        self.error_details = []
        self.device_errors = {}
        self.processing_errors = []

        # Set up custom logger to capture error messages
        self._setup_error_capture()

    def _setup_error_capture(self):
        """Set up logging to capture error messages"""
        self.error_handler = ErrorCaptureHandler(self)

        # Get the logger used by the scanner
        scanner_logger = logging.getLogger('rapidcmdb.db_scan_import_enhanced')
        scanner_logger.addHandler(self.error_handler)
        scanner_logger.setLevel(logging.DEBUG)

        # Also capture root logger errors
        root_logger = logging.getLogger()
        root_logger.addHandler(self.error_handler)

    def import_device(self, device):
        """Override import_device to capture individual device errors"""
        device_name = getattr(device, 'device_name', 'unknown')
        device_id = getattr(device, 'device_key', device_name)

        try:
            # Call original import_device method
            result = super().import_device(device)

            if not result:
                # If import failed but no exception was thrown, it was likely a validation error
                error_detail = {
                    'device_id': device_name,
                    'error': f'Device import failed - likely validation error (vendor: {getattr(device, "vendor", "unknown")}, serial: {getattr(device, "serial_number", "unknown")})',
                    'error_type': 'Import Validation'
                }
                self.error_details.append(error_detail)
                self.device_errors[device_id] = error_detail['error']

            return result

        except Exception as e:
            # Capture the exception details
            error_detail = {
                'device_id': device_name,
                'error': str(e),
                'error_type': 'Import Exception'
            }
            self.error_details.append(error_detail)
            self.device_errors[device_id] = str(e)

            # Still increment error count and re-raise or handle as original would
            self.stats['errors'] += 1
            return False

    def parse_device_from_scan(self, device_id: str, device_data: Dict):
        """Override parse_device_from_scan to capture parsing errors"""
        try:
            result = super().parse_device_from_scan(device_id, device_data)

            if result is None:
                # Device was skipped or failed to parse
                error_detail = {
                    'device_id': device_id,
                    'error': 'Device parsing failed or device was skipped (insufficient data, server detection, etc.)',
                    'error_type': 'Parsing/Skipped'
                }
                self.error_details.append(error_detail)
                self.device_errors[device_id] = error_detail['error']

            return result

        except Exception as e:
            error_detail = {
                'device_id': device_id,
                'error': f'Parsing exception: {str(e)}',
                'error_type': 'Parsing Exception'
            }
            self.error_details.append(error_detail)
            self.device_errors[device_id] = str(e)
            return None

    def import_scan_file(self, scan_file: str, filters: Dict = None):
        """Override import_scan_file to return detailed results"""
        # Clear previous errors
        self.error_details.clear()
        self.device_errors.clear()
        self.processing_errors.clear()

        # Store initial stats
        initial_stats = self.stats.copy()

        # Call original method
        result = super().import_scan_file(scan_file, filters)

        # Calculate what happened
        stats_diff = {
            'devices_processed': self.stats['devices_processed'] - initial_stats['devices_processed'],
            'devices_imported': self.stats['devices_imported'] - initial_stats['devices_imported'],
            'devices_updated': self.stats['devices_updated'] - initial_stats['devices_updated'],
            'devices_skipped': self.stats['devices_skipped'] - initial_stats['devices_skipped'],
            'duplicates_found': self.stats['duplicates_found'] - initial_stats['duplicates_found'],
            'errors': self.stats['errors'] - initial_stats['errors']
        }

        # Return enhanced result with error details
        return {
            'success': result,
            'stats': stats_diff,
            'error_details': self.error_details.copy(),
            'device_errors': self.device_errors.copy(),
            'processing_errors': self.processing_errors.copy()
        }


class ErrorCaptureHandler(logging.Handler):
    """Custom logging handler to capture error messages"""

    def __init__(self, scanner):
        super().__init__()
        self.scanner = scanner

    def emit(self, record):
        """Capture log records that contain error information"""
        if record.levelno >= logging.ERROR:
            # This is an error-level message
            error_msg = self.format(record)

            # Try to extract device information from the message
            device_id = 'Unknown'
            if hasattr(record, 'device_id'):
                device_id = record.device_id
            else:
                # Try to extract device ID from the message
                import re
                device_match = re.search(r'device\s+([^\s:]+)', error_msg, re.IGNORECASE)
                if device_match:
                    device_id = device_match.group(1)

            error_detail = {
                'device_id': device_id,
                'error': error_msg,
                'error_type': 'Logged Error'
            }

            # Add to scanner's error tracking
            if error_detail not in self.scanner.processing_errors:
                self.scanner.processing_errors.append(error_detail)
                if device_id not in self.scanner.device_errors:
                    self.scanner.device_errors[device_id] = error_msg


def main():
    """Main entry point for standalone operation"""
    app = QApplication(sys.argv)
    app.setApplicationName("CMDB Import Tool")
    app.setOrganizationName("TerminalTelemetry")

    # Set application icon if available
    try:
        app.setWindowIcon(QIcon("icon.png"))
    except:
        pass

    # Create and show main window
    window = CMDBImportMainWindow()
    window.show()

    # Add some helpful startup logging
    print("CMDB Scanner Import Tool started")
    print("Enhanced with vendor normalization and domain name stripping functionality")
    if not SCANNER_AVAILABLE:
        print("Warning: Scanner modules not available - some features may be limited")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
