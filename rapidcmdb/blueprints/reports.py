#!/usr/bin/env python3
"""
Reports Blueprint - Scan file analysis and reporting
Updated to use vendor-device combinations as stable keys instead of sys_descr
"""
import urllib.parse
from flask import Blueprint, render_template, jsonify, request, send_file, flash, redirect, url_for
import os
import json
import sqlite3
from datetime import datetime, timedelta
import logging
from collections import defaultdict, Counter
import re
from typing import Dict, List, Tuple
import tempfile
from io import StringIO

reports_bp = Blueprint('reports', __name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCANS_FOLDER = 'scans'


class DeviceAnalyzer:
    """Enhanced analyzer using vendor-device combinations as stable keys"""

    def __init__(self):
        # NAPALM supported vendor/device combinations
        self.napalm_support_map = {
            'cisco_router': True,
            'cisco_switch': True,
            'cisco_firewall': True,
            'arista_switch': True,
            'arista_router': True,
            'juniper_router': True,
            'juniper_switch': True,
            'juniper_firewall': True,
            'palo_alto_firewall': True,
            'fortinet_firewall': True,
            'dell_switch': True,
            'hp_switch': True,
            'aruba_switch': True,
            'aruba_access_point': True,
            'aruba_wireless_controller': True,
            'ion_sdwan_gateway': True,
            'palo_alto_sdwan_gateway': True,
        }

        # Network infrastructure types for better categorization
        self.network_infrastructure_types = {
            'router', 'switch', 'firewall', 'sdwan_gateway', 'load_balancer',
            'access_point', 'wireless_controller', 'edge_device', 'wan_optimizer'
        }

        # Security device types
        self.security_device_types = {
            'firewall', 'ips', 'ids', 'waf', 'proxy'
        }

        # Management device types
        self.management_device_types = {
            'server_management', 'bmc', 'ipmi', 'idrac', 'ilo'
        }

    def _normalize_sys_descr(self, sys_descr: str) -> str:
        """Normalize system description for better grouping - kept for compatibility"""
        if not sys_descr:
            return ''

        normalized = sys_descr

        # Remove version-specific details but keep major versions
        normalized = re.sub(r'Version\s+(\d+\.\d+)\([^)]+\)[^,]*', r'Version \1.x',
                            normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'(\d+\.\d+)\([^)]+\)', r'\1.x', normalized)

        # Remove build dates and compilation info
        normalized = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '[DATE]', normalized)
        normalized = re.sub(r'Compiled\s+\w+\s+\d+-\w+-\d+\s+\d+:\d+\s+by\s+[^\r\n]+', '[BUILD_INFO]',
                            normalized, flags=re.IGNORECASE)

        # Remove serial numbers and specific hardware IDs
        normalized = re.sub(r'\b[A-Z0-9]{8,}\b', '[ID]', normalized)

        # Remove IP addresses
        normalized = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', normalized)

        # Remove carriage returns and normalize whitespace
        normalized = re.sub(r'\r\n|\r|\n', '\n', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()

    def normalize_sys_descr(self, sys_descr: str) -> str:
        """Normalize system description for better grouping"""
        return self._normalize_sys_descr(sys_descr)

    def _is_napalm_supported(self, vendor: str, device_type: str) -> bool:
        """Check if vendor/device combination is supported by NAPALM"""
        vendor = str(vendor).lower().strip()
        device_type = str(device_type).lower().strip()

        combo_key = f"{vendor}_{device_type}"

        # Check exact combination first
        if combo_key in self.napalm_support_map:
            return self.napalm_support_map[combo_key]

        # Check vendor-level support for network devices
        napalm_vendors = ['cisco', 'arista', 'juniper', 'fortinet', 'palo_alto', 'dell', 'hp', 'aruba']
        network_types = ['router', 'switch', 'firewall', 'load_balancer', 'access_point', 'wireless_controller']

        return vendor in napalm_vendors and device_type in network_types

    def is_napalm_supported(self, vendor: str, device_type: str) -> bool:
        """Check if device is supported by NAPALM"""
        return self._is_napalm_supported(vendor, device_type)

    def _get_device_category(self, device_type: str) -> str:
        """Categorize device for better organization"""
        device_type = str(device_type).lower()

        if device_type in self.network_infrastructure_types:
            return 'network_infrastructure'
        elif device_type in self.security_device_types:
            return 'security'
        elif device_type in self.management_device_types:
            return 'management'
        elif device_type in ['printer', 'multifunction_printer', 'label_printer']:
            return 'printing'
        elif device_type in ['server', 'vm', 'container']:
            return 'compute'
        elif device_type in ['ups', 'pdu', 'environmental']:
            return 'power_environmental'
        else:
            return 'other'

    def clean_schema_field(self, value: str) -> str:
        """Clean and normalize schema field values"""
        if not value:
            return 'unknown'

        value = str(value).strip().lower()

        # Handle empty/null values
        if value in ['', 'none', 'null', 'n/a']:
            return 'unknown'

        return value

    def enhance_device_type_detection(self, vendor: str, device_type: str, sys_descr: str) -> str:
        """Enhanced device type detection based on system description patterns"""
        sys_descr_lower = sys_descr.lower()

        # If we already have a valid device type from schema, use it unless we can improve it
        if device_type != 'unknown':
            # Special case: Aruba devices marked as "switch" but are actually access points
            if vendor == 'aruba' and device_type == 'switch':
                if any(pattern in sys_descr_lower for pattern in
                       ['arubaos', 'model: 515', 'model: 535', 'model: 325', 'model: 555']):
                    return 'wireless_controller'  # Aruba wireless controllers
                elif 'ap' in sys_descr_lower or 'access point' in sys_descr_lower:
                    return 'access_point'

            # Return the schema device type if no enhancement needed
            return device_type

        # If device_type is unknown, try to determine from sys_descr
        type_patterns = {
            'router': ['router', 'routing', 'asr', 'isr', 'mx', 'crs'],
            'switch': ['switch', 'switching', 'catalyst', 'nexus', 'ex', 'qfx', 'powerconnect'],
            'firewall': ['firewall', 'asa', 'palo alto', 'fortigate', 'checkpoint', 'srx'],
            'wireless_controller': ['wireless controller', 'wlc', 'airwave', 'arubaos'],
            'access_point': ['access point', 'ap ', 'aironet'],
            'server': ['server', 'linux', 'windows', 'ubuntu', 'centos', 'redhat'],
            'printer': ['printer', 'print', 'laserjet', 'inkjet'],
            'ups': ['ups', 'uninterruptible', 'battery'],
            'load_balancer': ['load balancer', 'f5', 'bigip', 'ltm'],
            'sdwan_gateway': ['sdwan', 'sd-wan', 'viptela', 'silver-peak'],
        }

        # Check patterns
        for detected_type, patterns in type_patterns.items():
            for pattern in patterns:
                if pattern in sys_descr_lower:
                    return detected_type

        return 'unknown'

    def calculate_confidence_boost(self, device_info: dict, vendor: str, device_type: str) -> int:
        """Calculate confidence boost based on available data"""
        base_confidence = device_info.get('confidence_score', 50)

        # Don't modify if confidence is already very high
        if base_confidence >= 90:
            return base_confidence

        confidence_boost = 0

        # Has system description
        if device_info.get('sys_descr'):
            confidence_boost += 5

        # Has hostname
        if device_info.get('sys_name'):
            confidence_boost += 5

        # Has model info
        if device_info.get('model'):
            confidence_boost += 5

        # Has serial number
        if device_info.get('serial_number'):
            confidence_boost += 5

        # Vendor is not unknown
        if vendor != 'unknown':
            confidence_boost += 5

        # Device type is not unknown
        if device_type != 'unknown':
            confidence_boost += 5

        # Definitive detection method
        detection_method = device_info.get('detection_method', '')
        if 'definitive' in detection_method.lower():
            confidence_boost += 10
        elif detection_method in ['snmp', 'ssh']:
            confidence_boost += 5

        # Cap at 95%
        return min(95, base_confidence + confidence_boost)

    def get_combined_vendor_type(self, vendor: str, device_type: str) -> str:
        """Get combined vendor_devicetype string for display"""
        vendor = str(vendor).lower().strip()
        device_type = str(device_type).lower().strip()

        # Handle unknown cases
        if vendor == 'unknown' and device_type == 'unknown':
            return 'unknown'
        elif vendor == 'unknown':
            return f"unknown_{device_type}"
        elif device_type == 'unknown':
            return f"{vendor}_unknown"
        else:
            return f"{vendor}_{device_type}"

    def analyze_scan_file(self, scan_file_path: str) -> Dict:
        """Enhanced scan file analysis using device IDs and vendor/device combinations as keys"""
        logger.info(f"Analyzing scan file: {scan_file_path}")

        with open(scan_file_path, 'r', encoding='utf-8') as f:
            scan_data = json.load(f)

        devices = scan_data.get('devices', {})
        logger.info(f"Found {len(devices)} total devices")

        # Group devices by vendor_device combination for better analysis
        vendor_device_groups = defaultdict(list)
        individual_devices = {}

        # Track vendor_device combinations from schema
        vendor_device_combinations = defaultdict(int)

        for device_id, device_info in devices.items():
            # Read vendor and device_type directly from schema
            schema_vendor = self.clean_schema_field(device_info.get('vendor', 'unknown'))
            schema_device_type = self.clean_schema_field(device_info.get('device_type', 'unknown'))

            # Enhanced device type detection for better accuracy
            sys_descr = device_info.get('sys_descr', '').strip()
            enhanced_device_type = self.enhance_device_type_detection(schema_vendor, schema_device_type, sys_descr)

            # Use schema vendor as-is (it's usually correct)
            final_vendor = schema_vendor
            final_device_type = enhanced_device_type

            # Create a stable key based on vendor_device combination
            vendor_device_combo = f"{final_vendor}_{final_device_type}"
            vendor_device_combinations[vendor_device_combo] += 1

            # Calculate enhanced confidence
            enhanced_confidence = self.calculate_confidence_boost(
                device_info, final_vendor, final_device_type
            )

            # Check if NAPALM supported
            napalm_supported = self.is_napalm_supported(final_vendor, final_device_type)

            # Get combined vendor_type for display
            combined_vendor_type = self.get_combined_vendor_type(final_vendor, final_device_type)

            # Store individual device with enhanced info
            individual_device = {
                'device_id': device_id,
                'device_info': device_info,
                'primary_ip': device_info.get('primary_ip', ''),
                'sys_name': device_info.get('sys_name', ''),
                'sys_descr': sys_descr,
                'vendor_device_combo': vendor_device_combo,
                'final_vendor': final_vendor,
                'final_device_type': final_device_type,
                'combined_vendor_type': combined_vendor_type,
                'enhanced_confidence': enhanced_confidence,
                'napalm_supported': napalm_supported,
                'detection_method': device_info.get('detection_method', 'unknown')
            }

            individual_devices[device_id] = individual_device
            vendor_device_groups[vendor_device_combo].append(individual_device)

        logger.info(f"Grouped into {len(vendor_device_groups)} vendor-device combinations")

        # Create signatures based on vendor-device combinations
        signatures = {}

        for vendor_device_key, device_group in vendor_device_groups.items():
            # Use first device as representative
            representative = device_group[0]
            device_info = representative['device_info']

            signature = {
                'group_key': vendor_device_key,  # Stable key for API calls
                'sys_descr': representative['sys_descr'] or '',
                'count': len(device_group),
                'original_vendor': device_info.get('vendor', 'unknown') or 'unknown',
                'enhanced_vendor': representative['final_vendor'] or 'unknown',
                'device_type': representative['final_device_type'] or 'unknown',
                'combined_vendor_type': representative['combined_vendor_type'],
                'vendor_device_combo': vendor_device_key,
                'original_confidence': device_info.get('confidence_score', 50) or 50,
                'enhanced_confidence': representative['enhanced_confidence'] or 50,
                'napalm_supported': bool(representative['napalm_supported']),
                'detection_method': representative['detection_method'] or 'unknown',
                'sample_ips': [d['primary_ip'] for d in device_group[:5] if d['primary_ip']],
                'sample_names': [d['sys_name'] for d in device_group[:3] if d['sys_name']],
                'device_ids': [d['device_id'] for d in device_group]  # List of device IDs in this group
            }

            signatures[vendor_device_key] = signature

        # Extract scan metadata
        scan_metadata = scan_data.get('scan_metadata', {})

        return {
            'scan_file': scan_file_path,
            'scan_metadata': scan_metadata,
            'total_devices': len(devices),
            'unique_signatures': len(signatures),
            'signatures': signatures,
            'individual_devices': individual_devices,  # Individual device lookup
            'vendor_device_combinations': dict(vendor_device_combinations),
            'analysis_timestamp': datetime.now().isoformat()
        }

    def enhance_vendor_detection(self, device_info: dict) -> str:
        """Enhanced vendor detection logic"""
        sys_descr = device_info.get('sys_descr', '').lower()
        original_vendor = device_info.get('vendor', 'unknown').lower()

        # Enhanced vendor detection based on system description
        vendor_patterns = {
            'cisco': ['cisco', 'ios', 'nx-os', 'asa'],
            'arista': ['arista', 'eos'],
            'juniper': ['juniper', 'junos'],
            'palo_alto': ['palo alto', 'pan-os'],
            'fortinet': ['fortinet', 'fortigate', 'fortios'],
            'hp': ['hp ', 'hewlett', 'procurve', 'comware'],
            'dell': ['dell', 'powerconnect', 'force10'],
            'aruba': ['aruba', 'airwave'],
            'checkpoint': ['checkpoint', 'gaia'],
            'vmware': ['vmware', 'vsphere', 'esx'],
        }

        # Check system description for vendor clues
        for vendor, patterns in vendor_patterns.items():
            for pattern in patterns:
                if pattern in sys_descr:
                    return vendor

        # Return original vendor if no enhancement found
        return original_vendor if original_vendor != 'unknown' else 'unknown'

    def determine_device_type(self, vendor: str, sys_descr: str, ip: str = '') -> str:
        """Determine device type based on vendor and system description"""
        sys_descr_lower = sys_descr.lower()

        # Device type patterns
        type_patterns = {
            'router': ['router', 'routing', 'asr', 'isr', 'mx', 'srx', 'crs'],
            'switch': ['switch', 'switching', 'catalyst', 'nexus', 'ex', 'qfx', 'powerconnect'],
            'firewall': ['firewall', 'asa', 'palo alto', 'fortigate', 'checkpoint', 'srx'],
            'wireless_controller': ['wireless', 'wlc', 'airwave', 'controller'],
            'access_point': ['access point', 'ap ', 'aironet'],
            'server': ['server', 'linux', 'windows', 'ubuntu', 'centos', 'redhat'],
            'printer': ['printer', 'print', 'laserjet', 'inkjet'],
            'ups': ['ups', 'uninterruptible', 'battery'],
            'load_balancer': ['load balancer', 'f5', 'bigip', 'ltm'],
            'sdwan_gateway': ['sdwan', 'sd-wan', 'viptela', 'silver-peak'],
        }

        # Check patterns
        for device_type, patterns in type_patterns.items():
            for pattern in patterns:
                if pattern in sys_descr_lower:
                    return device_type

        # Vendor-specific defaults
        if vendor in ['cisco', 'arista', 'juniper']:
            if 'ios' in sys_descr_lower or 'eos' in sys_descr_lower:
                return 'switch'  # Default for network vendors

        return 'unknown'

    def calculate_confidence(self, device_info: dict, enhanced_vendor: str, device_type: str) -> int:
        """Calculate enhanced confidence score"""
        base_confidence = device_info.get('confidence_score', 50)

        # Confidence boosters
        confidence_boost = 0

        # Has system description
        if device_info.get('sys_descr'):
            confidence_boost += 10

        # Has hostname
        if device_info.get('sys_name'):
            confidence_boost += 5

        # Has model info
        if device_info.get('model'):
            confidence_boost += 10

        # Has serial number
        if device_info.get('serial_number'):
            confidence_boost += 10

        # Vendor enhancement worked
        if enhanced_vendor != 'unknown' and enhanced_vendor != device_info.get('vendor', 'unknown'):
            confidence_boost += 15

        # Device type determined
        if device_type != 'unknown':
            confidence_boost += 10

        # Multiple detection methods
        if device_info.get('detection_method') in ['snmp', 'ssh']:
            confidence_boost += 5

        # Cap at 95%
        return min(95, base_confidence + confidence_boost)


def get_scan_files():
    """Get list of scan files with metadata"""
    scan_files = []

    if not os.path.exists(SCANS_FOLDER):
        return scan_files

    for filename in os.listdir(SCANS_FOLDER):
        if filename.endswith('.json'):
            filepath = os.path.join(SCANS_FOLDER, filename)
            try:
                # Get file stats
                stat = os.stat(filepath)

                # Try to read basic metadata from file
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                devices_count = len(data.get('devices', {}))
                scan_metadata = data.get('scan_metadata', {})

                scan_files.append({
                    'filename': filename,
                    'filepath': filepath,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime),
                    'devices_count': devices_count,
                    'scan_metadata': scan_metadata
                })

            except Exception as e:
                logger.error(f"Error reading scan file {filename}: {e}")
                continue

    # Sort by modification date (newest first)
    scan_files.sort(key=lambda x: x['modified'], reverse=True)
    return scan_files


@reports_bp.route('/')
def index():
    """Reports index page - list scan files"""
    try:
        scan_files = get_scan_files()
        logger.info(f"Found {len(scan_files)} scan files")
        return render_template('reports/index.html', scan_files=scan_files)
    except Exception as e:
        logger.error(f"Error in reports index: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"""
        <h1>Reports Debug</h1>
        <p>Error: {str(e)}</p>
        <p>Found {len(get_scan_files()) if 'get_scan_files' in locals() else 0} scan files</p>
        <p>Please check that templates/reports/index.html exists</p>
        """


@reports_bp.route('/analyze/<filename>')
def analyze_scan(filename):
    """Analyze a specific scan file - enhanced to show vendor_device combinations"""
    try:
        # Validate filename
        if not filename.endswith('.json'):
            flash('Invalid file type', 'error')
            return redirect(url_for('reports.index'))

        filepath = os.path.join(SCANS_FOLDER, filename)
        if not os.path.exists(filepath):
            flash('Scan file not found', 'error')
            return redirect(url_for('reports.index'))

        # Analyze the scan file
        analyzer = DeviceAnalyzer()
        analysis_results = analyzer.analyze_scan_file(filepath)

        # Calculate summary statistics for template
        signatures = analysis_results['signatures']
        vendor_counts = {}
        device_type_counts = {}
        combined_vendor_type_counts = {}
        vendor_device_combinations = analysis_results.get('vendor_device_combinations', {})

        # Initialize summary counters
        high_confidence_count = 0
        napalm_supported_count = 0
        network_infrastructure_count = 0

        for sig_key, sig_data in signatures.items():
            vendor = sig_data.get('enhanced_vendor', 'unknown')
            device_type = sig_data.get('device_type', 'unknown')
            combined_vendor_type = sig_data.get('combined_vendor_type', 'unknown')
            count = sig_data.get('count', 0)

            vendor_counts[vendor] = vendor_counts.get(vendor, 0) + count
            device_type_counts[device_type] = device_type_counts.get(device_type, 0) + count
            combined_vendor_type_counts[combined_vendor_type] = combined_vendor_type_counts.get(combined_vendor_type,
                                                                                                0) + count

            # Calculate summary statistics
            confidence = sig_data.get('enhanced_confidence', 0)
            napalm = sig_data.get('napalm_supported', False)

            if confidence >= 80:
                high_confidence_count += count

            if napalm:
                napalm_supported_count += count

            if device_type in ['router', 'switch', 'firewall', 'sdwan', 'load_balancer', 'access_point',
                               'wireless_controller', 'sdwan_gateway', 'edge_device']:
                network_infrastructure_count += count

        # Add calculated stats to analysis results
        analysis_results['vendor_counts'] = vendor_counts
        analysis_results['device_type_counts'] = device_type_counts
        analysis_results['combined_vendor_type_counts'] = combined_vendor_type_counts
        analysis_results['vendor_device_combinations'] = vendor_device_combinations

        # Add summary statistics to analysis results
        analysis_results['summary_stats'] = {
            'high_confidence_count': high_confidence_count,
            'napalm_supported_count': napalm_supported_count,
            'network_infrastructure_count': network_infrastructure_count,
            'high_confidence_percentage': (high_confidence_count / analysis_results['total_devices'] * 100) if
            analysis_results['total_devices'] > 0 else 0,
            'napalm_percentage': (napalm_supported_count / analysis_results['total_devices'] * 100) if analysis_results[
                                                                                                           'total_devices'] > 0 else 0,
            'network_percentage': (network_infrastructure_count / analysis_results['total_devices'] * 100) if
            analysis_results['total_devices'] > 0 else 0
        }

        # Clean the data to ensure JSON serialization works
        def clean_for_json(obj):
            """Clean object to ensure JSON serialization, handling Jinja2 Undefined objects"""
            from jinja2 import Undefined

            if obj is None or isinstance(obj, Undefined):
                return ''
            elif isinstance(obj, (str, int, float, bool)):
                return obj
            elif isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items() if not isinstance(v, Undefined)}
            elif isinstance(obj, list):
                return [clean_for_json(item) for item in obj if not isinstance(item, Undefined)]
            else:
                return str(obj)

        # Clean the analysis results
        analysis_results = clean_for_json(analysis_results)
        vendor_counts = clean_for_json(vendor_counts)
        device_type_counts = clean_for_json(device_type_counts)
        combined_vendor_type_counts = clean_for_json(combined_vendor_type_counts)
        vendor_device_combinations = clean_for_json(vendor_device_combinations)

        return render_template('reports/analysis.html',
                               analysis=analysis_results,
                               filename=filename,
                               vendor_counts=vendor_counts,
                               device_type_counts=device_type_counts,
                               combined_vendor_type_counts=combined_vendor_type_counts,
                               vendor_device_combinations=vendor_device_combinations)

    except Exception as e:
        logger.error(f"Error analyzing scan file {filename}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        flash(f'Error analyzing scan file: {str(e)}', 'error')
        return redirect(url_for('reports.index'))


@reports_bp.route('/api/device-details/<filename>/<group_key>')
def api_device_details(filename, group_key):
    """Enhanced API endpoint using group keys instead of sys_descr"""
    try:
        # Simple decoding since we're using stable group keys now
        decoded_group_key = urllib.parse.unquote_plus(group_key)
        logger.info(f"Looking for group key: {decoded_group_key}")

        filepath = os.path.join(SCANS_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': 'Scan file not found'}), 404

        # Load and analyze with enhanced analyzer
        analyzer = DeviceAnalyzer()
        analysis_results = analyzer.analyze_scan_file(filepath)

        signatures = analysis_results['signatures']
        individual_devices = analysis_results.get('individual_devices', {})

        logger.info(f"Available group keys: {list(signatures.keys())}")

        # Find matching signature using stable group key
        if decoded_group_key not in signatures:
            return jsonify({
                'error': 'Group key not found',
                'requested_key': decoded_group_key,
                'available_keys': list(signatures.keys())
            }), 404

        signature_data = signatures[decoded_group_key]

        # Get all devices in this group using device IDs
        device_ids = signature_data.get('device_ids', [])
        matching_devices = []

        for device_id in device_ids:
            if device_id in individual_devices:
                device_detail = individual_devices[device_id]
                device_info = device_detail['device_info']

                # Enhanced device details for API response
                enhanced_device = {
                    'device_id': device_id,
                    'primary_ip': device_detail['primary_ip'],
                    'all_ips': device_info.get('all_ips', []),
                    'sys_name': device_detail['sys_name'],
                    'sys_descr': device_detail['sys_descr'],
                    'vendor': device_detail['final_vendor'],
                    'device_type': device_detail['final_device_type'],
                    'vendor_device_combo': device_detail['vendor_device_combo'],
                    'category': analyzer._get_device_category(device_detail['final_device_type']),
                    'model': device_info.get('model', ''),
                    'serial_number': device_info.get('serial_number', ''),
                    'os_version': device_info.get('os_version', ''),
                    'confidence_score': device_detail['enhanced_confidence'],
                    'detection_method': device_detail['detection_method'],
                    'napalm_supported': device_detail['napalm_supported'],
                    'first_seen': device_info.get('first_seen', ''),
                    'last_seen': device_info.get('last_seen', ''),
                    'scan_count': device_info.get('scan_count', 0),
                    'interfaces': device_info.get('interfaces', {}),
                    'mac_addresses': device_info.get('mac_addresses', []),
                    'snmp_version_used': device_info.get('snmp_version_used', 'unknown'),
                    'snmp_data_by_ip': device_info.get('snmp_data_by_ip', {})
                }

                matching_devices.append(enhanced_device)

        # Sort by IP address
        matching_devices.sort(key=lambda x: x.get('primary_ip', ''))

        response_data = {
            'group_key': decoded_group_key,
            'signature_info': signature_data,
            'matching_devices': matching_devices,
            'device_count': len(matching_devices),
            'scan_file': filename,
            'enhanced_stats': {
                'napalm_count': sum(1 for d in matching_devices if d['napalm_supported']),
                'high_confidence_count': sum(1 for d in matching_devices if d['confidence_score'] >= 80),
                'categories': Counter(d['category'] for d in matching_devices),
                'detection_methods': Counter(d['detection_method'] for d in matching_devices)
            }
        }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error getting device details: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/api/analyze/<filename>')
def api_analyze_scan(filename):
    """API endpoint to analyze scan file"""
    try:
        filepath = os.path.join(SCANS_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404

        analyzer = DeviceAnalyzer()
        analysis_results = analyzer.analyze_scan_file(filepath)

        return jsonify(analysis_results)

    except Exception as e:
        logger.error(f"API error analyzing {filename}: {e}")
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/download/<filename>')
def download_report(filename):
    """Download analysis report as text file"""
    try:
        filepath = os.path.join(SCANS_FOLDER, filename)
        if not os.path.exists(filepath):
            flash('Scan file not found', 'error')
            return redirect(url_for('reports.index'))

        # Analyze the scan file
        analyzer = DeviceAnalyzer()
        analysis_results = analyzer.analyze_scan_file(filepath)

        # Generate text report
        report_text = generate_text_report(analysis_results)

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(report_text)
            temp_path = f.name

        # Generate download filename
        base_name = os.path.splitext(filename)[0]
        download_filename = f"{base_name}_analysis_report.txt"

        return send_file(temp_path, as_attachment=True, download_name=download_filename,
                         mimetype='text/plain')

    except Exception as e:
        logger.error(f"Error generating report for {filename}: {e}")
        flash(f'Error generating report: {str(e)}', 'error')
        return redirect(url_for('reports.index'))


def generate_text_report(analysis_results: Dict) -> str:
    """Generate comprehensive analysis report text"""
    signatures = analysis_results['signatures']

    # Sort signatures by enhanced confidence and count
    sorted_signatures = sorted(
        signatures.items(),
        key=lambda x: (x[1]['enhanced_confidence'], x[1]['count']),
        reverse=True
    )

    lines = []
    lines.append("NETWORK DISCOVERY ANALYSIS REPORT")
    lines.append("=" * 80)
    lines.append(f"Analysis Date: {analysis_results['analysis_timestamp']}")
    lines.append(f"Scan File: {analysis_results['scan_file']}")
    lines.append(f"Total Devices: {analysis_results['total_devices']:,}")
    lines.append(f"Unique Device Signatures: {analysis_results['unique_signatures']:,}")
    lines.append("")

    # Add scan metadata if available
    scan_metadata = analysis_results.get('scan_metadata', {})
    if scan_metadata:
        lines.append("SCAN METADATA")
        lines.append("-" * 40)
        for key, value in scan_metadata.items():
            lines.append(f"{key}: {value}")
        lines.append("")

    # Calculate summary statistics
    vendor_counts = Counter()
    device_type_counts = Counter()
    combined_vendor_type_counts = Counter()
    high_confidence_count = 0
    napalm_supported_count = 0

    for sig_key, sig_data in signatures.items():
        vendor_counts[sig_data['enhanced_vendor']] += sig_data['count']
        device_type_counts[sig_data['device_type']] += sig_data['count']
        combined_vendor_type_counts[sig_data['combined_vendor_type']] += sig_data['count']

        if sig_data['enhanced_confidence'] >= 80:
            high_confidence_count += sig_data['count']
        if sig_data['napalm_supported']:
            napalm_supported_count += sig_data['count']

    lines.append("SUMMARY STATISTICS")
    lines.append("-" * 40)
    lines.append(f"High Confidence Devices (>=80%): {high_confidence_count:,}")
    lines.append(f"NAPALM Supported Devices: {napalm_supported_count:,}")
    lines.append(
        f"Network Infrastructure: {sum(device_type_counts[dt] for dt in ['router', 'switch', 'firewall', 'sdwan', 'load_balancer', 'access_point', 'wireless_controller']):,}")
    lines.append("")

    lines.append("VENDOR DISTRIBUTION")
    lines.append("-" * 40)
    for vendor, count in vendor_counts.most_common(15):
        percentage = (count / analysis_results['total_devices']) * 100
        lines.append(f"{vendor:<20}: {count:>5,} devices ({percentage:>5.1f}%)")
    lines.append("")

    lines.append("DEVICE TYPE DISTRIBUTION")
    lines.append("-" * 40)
    for device_type, count in device_type_counts.most_common(15):
        percentage = (count / analysis_results['total_devices']) * 100
        lines.append(f"{device_type:<20}: {count:>5,} devices ({percentage:>5.1f}%)")
    lines.append("")

    lines.append("VENDOR_TYPE COMBINATIONS")
    lines.append("-" * 40)
    for combined_type, count in combined_vendor_type_counts.most_common(20):
        percentage = (count / analysis_results['total_devices']) * 100
        lines.append(f"{combined_type:<25}: {count:>5,} devices ({percentage:>5.1f}%)")
    lines.append("")

    lines.append("TOP DEVICE DISCOVERIES")
    lines.append("=" * 100)
    lines.append(f"{'#':<3} {'Vendor_Type':<20} {'Count':<7} {'Conf':<6} {'NAPALM':<6} {'Sample IPs'}")
    lines.append("-" * 100)

    for i, (sig_key, sig_data) in enumerate(sorted_signatures[:20], 1):
        combined_type = sig_data['combined_vendor_type'][:19]
        count = f"{sig_data['count']:,}"
        confidence = f"{sig_data['enhanced_confidence']}%"
        napalm = "Yes" if sig_data['napalm_supported'] else "No"
        sample_ips = ", ".join(sig_data['sample_ips'][:2])

        lines.append(f"{i:<3} {combined_type:<20} {count:<7} {confidence:<6} {napalm:<6} {sample_ips}")

    lines.append("")
    lines.append("DETAILED DEVICE SIGNATURES")
    lines.append("=" * 80)

    for i, (sig_key, sig_data) in enumerate(sorted_signatures[:10], 1):
        lines.append(f"\n[{i}] {sig_data['combined_vendor_type'].upper()}")
        lines.append(f"    Device Count: {sig_data['count']:,}")
        lines.append(f"    Confidence: {sig_data['original_confidence']}% -> {sig_data['enhanced_confidence']}%")
        lines.append(f"    NAPALM Support: {'Yes' if sig_data['napalm_supported'] else 'No'}")
        lines.append(f"    Detection Method: {sig_data['detection_method']}")
        lines.append(f"    Sample IPs: {', '.join(sig_data['sample_ips'])}")
        lines.append(f"    Sample Names: {', '.join(sig_data.get('sample_names', []))}")
        lines.append(f"    Group Key: {sig_data['group_key']}")

    return '\n'.join(lines)


@reports_bp.route('/compare')
def compare_scans():
    """Compare multiple scan files"""
    return render_template('reports/compare.html')


@reports_bp.route('/summary')
def summary():
    """Summary of all scan files"""
    try:
        scan_files = get_scan_files()

        summary_data = {
            'total_scans': len(scan_files),
            'total_devices': sum(f['devices_count'] for f in scan_files),
            'latest_scan': scan_files[0] if scan_files else None,
            'scan_files': scan_files[:10]  # Latest 10 scans
        }

        return render_template('reports/summary.html', summary=summary_data)

    except Exception as e:
        logger.error(f"Error in summary: {e}")
        flash(f'Error generating summary: {str(e)}', 'error')
        return redirect(url_for('reports.index'))